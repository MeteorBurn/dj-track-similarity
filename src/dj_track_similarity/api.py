from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .analysis_jobs import AnalysisJobManager
from .classifier_jobs import ClassifierJobManager
from .database import LibraryDatabase
from .dependencies import require_ffmpeg
from .embedding import ClapEmbeddingAdapter
from .exporter import export_tracks
from .genre_jobs import GenreAnalysisJobManager
from .logging_config import configure_logging
from .scan_jobs import ScanJobManager
from .search import SearchFilters, SimilaritySearch
from .sonara_similarity import SonaraSimilaritySearch
from .sonara_jobs import SonaraFeatureJobManager
from .tags import GenreTagJobManager, apply_genre_tags_to_tracks


LOGGER = logging.getLogger(__name__)


class ScanRequest(BaseModel):
    root: str
    workers: int = Field(default=1, ge=1, le=64)


class TagRefreshRequest(BaseModel):
    workers: int = Field(default=1, ge=1, le=64)


class RelocateLibraryRequest(BaseModel):
    old_root: str
    new_root: str
    apply: bool = False


class DatabaseSwitchRequest(BaseModel):
    path: str


class AnalyzeRequest(BaseModel):
    limit: int | None = None
    adapter: str = Field(default="mert", pattern="^(mert|clap)$")
    device: str = Field(default="auto", pattern="^(auto|cpu|cuda)$")
    batch_size: int = Field(default=4, ge=1, le=64)
    workers: int | None = Field(default=None, ge=1, le=64)


class GenreAnalyzeRequest(BaseModel):
    limit: int | None = None
    device: str = Field(default="auto", pattern="^(auto|cpu|cuda)$")
    top_k: int = Field(default=3, ge=1, le=10)
    batch_size: int = Field(default=4, ge=1, le=64)


class SonaraAnalyzeRequest(BaseModel):
    limit: int | None = None
    batch_size: int = Field(default=1, ge=1, le=64)


class ClassifierAnalyzeRequest(BaseModel):
    limit: int | None = None


class AnalysisResetRequest(BaseModel):
    adapter: str = Field(pattern="^(sonara|maest|mert|clap)$")


class SearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    seed_track_ids: list[int]
    lookback_track_ids: list[int] = Field(default_factory=list)
    limit: int = 5
    bpm_tolerance: float | None = None
    key_compatibility: str | None = None
    energy_min: float | None = None
    energy_max: float | None = None
    min_similarity: float | None = None
    epsilon: float | None = Field(default=None, alias="Epsilon")
    noise: float = 0.0


class SonaraMixerWeights(BaseModel):
    timbre: float = Field(default=1.0, ge=0.0, le=5.0)
    rhythm: float = Field(default=1.0, ge=0.0, le=5.0)
    dynamics: float = Field(default=0.8, ge=0.0, le=5.0)
    harmonic: float = Field(default=0.8, ge=0.0, le=5.0)
    tempo: float = Field(default=0.35, ge=0.0, le=5.0)


class SonaraModifiers(BaseModel):
    energy: float = Field(default=0.0, ge=-1.0, le=1.0)
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    acousticness: float = Field(default=0.0, ge=-1.0, le=1.0)
    brightness: float = Field(default=0.0, ge=-1.0, le=1.0)
    rhythm_density: float = Field(default=0.0, ge=-1.0, le=1.0)
    dynamic_range: float = Field(default=0.0, ge=-1.0, le=1.0)
    loudness: float = Field(default=0.0, ge=-1.0, le=1.0)


class SonaraSearchRequest(BaseModel):
    seed_track_ids: list[int]
    lookback_track_ids: list[int] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=500)
    mode: str = Field(default="balanced", pattern="^(balanced|vibe|sound|dj_transition|custom)$")
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    mixer_weights: SonaraMixerWeights | None = None
    modifiers: SonaraModifiers | None = None


class TextSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=500)
    min_similarity: float | None = None
    device: str = Field(default="auto", pattern="^(auto|cpu|cuda)$")


class FilteredTracksRequest(BaseModel):
    query: str = ""
    preset: str = Field(default="all", pattern="^(all|syncopated)$")
    min_break_energy: float | None = Field(default=None, ge=0.0, le=1.0)


class ExportRequest(BaseModel):
    name: str
    track_ids: list[int]
    output_dir: str
    format: str = Field(default="m3u", pattern="^(m3u|csv)$")


class GenreTagRequest(BaseModel):
    track_ids: list[int] | None = None


class DatabaseNotSelected(RuntimeError):
    pass


class DatabaseBusy(RuntimeError):
    pass


ACTIVE_JOB_STATES = {"queued", "running"}
AIFF_PREVIEW_SUFFIXES = {".aif", ".aiff"}


class AppDatabaseState:
    def __init__(self, db_path: str | Path | None) -> None:
        self._lock = threading.RLock()
        self.db_path: Path | None = None
        self.db: LibraryDatabase | None = None
        self.analysis_jobs: AnalysisJobManager | None = None
        self.genre_jobs: GenreAnalysisJobManager | None = None
        self.classifier_jobs: ClassifierJobManager | None = None
        self.sonara_jobs: SonaraFeatureJobManager | None = None
        self.scan_jobs: ScanJobManager | None = None
        self.genre_tag_jobs: GenreTagJobManager | None = None
        if db_path is not None:
            self.switch(db_path)

    def current(self) -> dict[str, object]:
        with self._lock:
            music_root = self.db.get_library_root() if self.db is not None else None
            return {
                "path": str(self.db_path) if self.db_path is not None else None,
                "selected": self.db is not None,
                "music_root": music_root,
            }

    def switch(self, path: str | Path) -> dict[str, object]:
        selected = Path(path).expanduser()
        if not str(selected).strip() or not selected.name:
            raise ValueError("Database path is required")
        if selected.exists() and selected.is_dir():
            raise ValueError("Database path must be a file")
        selected = selected.resolve(strict=False)
        with self._lock:
            if self._has_active_jobs():
                raise DatabaseBusy("Cannot switch database while jobs are running")
            db = LibraryDatabase(selected)
            self.db_path = db.path
            self.db = db
            self.analysis_jobs = AnalysisJobManager(db)
            self.genre_jobs = GenreAnalysisJobManager(db)
            self.classifier_jobs = ClassifierJobManager(db)
            self.sonara_jobs = SonaraFeatureJobManager(db)
            self.scan_jobs = ScanJobManager(db)
            self.genre_tag_jobs = GenreTagJobManager(db)
            return self.current()

    def require_db(self) -> LibraryDatabase:
        if self.db is None:
            raise DatabaseNotSelected("Database is not selected")
        return self.db

    def require_analysis_jobs(self) -> AnalysisJobManager:
        self.require_db()
        assert self.analysis_jobs is not None
        return self.analysis_jobs

    def require_genre_jobs(self) -> GenreAnalysisJobManager:
        self.require_db()
        assert self.genre_jobs is not None
        return self.genre_jobs

    def require_sonara_jobs(self) -> SonaraFeatureJobManager:
        self.require_db()
        assert self.sonara_jobs is not None
        return self.sonara_jobs

    def require_classifier_jobs(self) -> ClassifierJobManager:
        self.require_db()
        assert self.classifier_jobs is not None
        return self.classifier_jobs

    def require_scan_jobs(self) -> ScanJobManager:
        self.require_db()
        assert self.scan_jobs is not None
        return self.scan_jobs

    def require_genre_tag_jobs(self) -> GenreTagJobManager:
        self.require_db()
        assert self.genre_tag_jobs is not None
        return self.genre_tag_jobs

    def _has_active_jobs(self) -> bool:
        managers = [
            self.analysis_jobs,
            self.genre_jobs,
            self.classifier_jobs,
            self.sonara_jobs,
            self.scan_jobs,
            self.genre_tag_jobs,
        ]
        for manager in managers:
            if manager is None:
                continue
            latest = manager.latest()
            if latest is not None and getattr(latest, "state", None) in ACTIVE_JOB_STATES:
                return True
        return False


def open_folder_dialog() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:  # pragma: no cover - depends on local Python GUI support.
        raise RuntimeError("Native folder dialog is unavailable") from error

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        root.update()
        selected = filedialog.askdirectory(parent=root, title="Выберите папку с музыкой", mustexist=True)
    finally:
        root.destroy()
    return Path(selected) if selected else None


def open_database_file_dialog() -> Path | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as error:  # pragma: no cover - depends on local Python GUI support.
        raise RuntimeError("Native database file dialog is unavailable") from error

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        root.update()
        selected = filedialog.asksaveasfilename(
            parent=root,
            title="Выберите SQLite базу",
            defaultextension=".sqlite",
            filetypes=[("SQLite database", "*.sqlite"), ("All files", "*.*")],
            confirmoverwrite=False,
        )
    finally:
        root.destroy()
    if not selected:
        return None
    path = Path(selected)
    return path.with_suffix(".sqlite") if not path.suffix else path


def create_app(
    db_path: str | Path | None = None,
    *,
    log_level: int | str | None = None,
    log_track_events: bool | None = None,
) -> FastAPI:
    log_path = configure_logging(level=log_level, log_track_events=log_track_events)
    ffmpeg_path = require_ffmpeg()
    LOGGER.info("API app created db_path=%s log_path=%s", db_path, log_path)
    LOGGER.debug("ffmpeg available path=%s", ffmpeg_path)
    state = AppDatabaseState(db_path)
    app = FastAPI(title="dj-track-similarity Utility")

    @app.exception_handler(DatabaseNotSelected)
    async def database_not_selected(_: Request, error: DatabaseNotSelected):
        return JSONResponse(status_code=400, content={"detail": str(error)})

    @app.exception_handler(DatabaseBusy)
    async def database_busy(_: Request, error: DatabaseBusy):
        return JSONResponse(status_code=409, content={"detail": str(error)})

    @app.get("/api/database/current")
    def current_database():
        return state.current()

    @app.post("/api/database/switch")
    def switch_database(request: DatabaseSwitchRequest):
        try:
            return state.switch(request.path)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/database/dialog")
    def database_dialog():
        try:
            selected = open_database_file_dialog()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if selected is None:
            return state.current()
        try:
            return state.switch(selected)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/library/scan")
    def scan(request: ScanRequest):
        try:
            job = state.require_scan_jobs().start(request.root, workers=request.workers)
        except (FileNotFoundError, NotADirectoryError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        state.require_db().set_library_root(request.root)
        return job

    @app.post("/api/library/tags/refresh")
    def refresh_tags(request: TagRefreshRequest):
        return state.require_scan_jobs().start_tag_refresh(workers=request.workers)

    @app.post("/api/library/relocate")
    def relocate_library(request: RelocateLibraryRequest):
        try:
            return state.require_db().relocate_library(request.old_root, request.new_root, apply=request.apply)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/database/clear")
    def clear_database():
        return state.require_db().clear_library()

    @app.get("/api/library/scan/jobs/latest")
    def latest_scan_job():
        return state.require_scan_jobs().latest()

    @app.get("/api/library/scan/jobs/{job_id}")
    def scan_job(job_id: str):
        try:
            return state.require_scan_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/library/scan/jobs/{job_id}/cancel")
    def cancel_scan_job(job_id: str):
        try:
            return state.require_scan_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/tracks")
    def tracks(
        q: str = "",
        preset: str = Query(default="all", pattern="^(all|syncopated)$"),
        min_break_energy: float | None = Query(default=None, ge=0.0, le=1.0),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        include_metadata: bool = False,
    ):
        return state.require_db().list_tracks_page(
            query=q,
            preset=preset,
            min_break_energy=min_break_energy,
            limit=limit,
            offset=offset,
            include_metadata=include_metadata,
        )

    @app.get("/api/tracks/{track_id}")
    def track(track_id: int):
        try:
            return state.require_db().get_track(track_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/tracks/filtered")
    def filtered_tracks(request: FilteredTracksRequest):
        return state.require_db().list_filtered_tracks(
            query=request.query,
            preset=request.preset,
            min_break_energy=request.min_break_energy,
        )

    @app.get("/api/library/summary")
    def library_summary():
        return state.require_db().library_summary()

    @app.post("/api/analysis/reset")
    def reset_analysis(request: AnalysisResetRequest):
        try:
            return state.require_db().reset_analysis(request.adapter)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/analyze")
    def analyze(request: AnalyzeRequest):
        return state.require_analysis_jobs().start(
            adapter_name=request.adapter,
            limit=request.limit,
            batch_size=request.batch_size,
            workers=request.workers,
            device=request.device,
        )

    @app.post("/api/sonara/analyze")
    def analyze_sonara(request: SonaraAnalyzeRequest):
        return state.require_sonara_jobs().start(limit=request.limit, batch_size=request.batch_size)

    @app.post("/api/classifiers/break-energy/analyze")
    def analyze_break_energy(request: ClassifierAnalyzeRequest):
        return state.require_classifier_jobs().start(limit=request.limit)

    @app.get("/api/classifiers/break-energy/analyze/jobs/latest")
    def latest_break_energy_job():
        return state.require_classifier_jobs().latest()

    @app.get("/api/classifiers/break-energy/analyze/jobs/{job_id}")
    def break_energy_job(job_id: str):
        try:
            return state.require_classifier_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/classifiers/break-energy/analyze/jobs/{job_id}/cancel")
    def cancel_break_energy_job(job_id: str):
        try:
            return state.require_classifier_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/sonara/analyze/jobs/latest")
    def latest_sonara_job():
        return state.require_sonara_jobs().latest()

    @app.get("/api/sonara/analyze/jobs/{job_id}")
    def sonara_job(job_id: str):
        try:
            return state.require_sonara_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/sonara/analyze/jobs/{job_id}/cancel")
    def cancel_sonara_job(job_id: str):
        try:
            return state.require_sonara_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/analyze/jobs/latest")
    def latest_analyze_job():
        return state.require_analysis_jobs().latest()

    @app.get("/api/analyze/jobs/{job_id}")
    def analyze_job(job_id: str):
        try:
            return state.require_analysis_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/analyze/jobs/{job_id}/cancel")
    def cancel_analyze_job(job_id: str):
        try:
            return state.require_analysis_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/genres/analyze")
    def analyze_genres(request: GenreAnalyzeRequest):
        return state.require_genre_jobs().start(
            limit=request.limit,
            device=request.device,
            top_k=request.top_k,
            batch_size=request.batch_size,
        )

    @app.get("/api/genres/analyze/jobs/latest")
    def latest_genre_job():
        return state.require_genre_jobs().latest()

    @app.get("/api/genres/analyze/jobs/{job_id}")
    def genre_job(job_id: str):
        try:
            return state.require_genre_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/genres/analyze/jobs/{job_id}/cancel")
    def cancel_genre_job(job_id: str):
        try:
            return state.require_genre_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/search")
    def search(request: SearchRequest):
        filters = SearchFilters(
            bpm_tolerance=request.bpm_tolerance,
            key_compatibility=request.key_compatibility,
            energy_min=request.energy_min,
            energy_max=request.energy_max,
            min_similarity=request.min_similarity,
            epsilon=request.epsilon,
            noise=request.noise,
        )
        try:
            return SimilaritySearch(state.require_db()).search(
                request.seed_track_ids,
                lookback_track_ids=request.lookback_track_ids,
                filters=filters,
                limit=request.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/search/sonara")
    def sonara_search(request: SonaraSearchRequest):
        try:
            return SonaraSimilaritySearch(state.require_db()).search(
                request.seed_track_ids,
                lookback_track_ids=request.lookback_track_ids,
                mode=request.mode,  # type: ignore[arg-type]
                mixer_weights=request.mixer_weights.model_dump() if request.mixer_weights else None,
                modifiers=request.modifiers.model_dump() if request.modifiers else None,
                min_similarity=request.min_similarity,
                limit=request.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/search/text")
    def text_search(request: TextSearchRequest):
        query = request.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="Text query is required")
        adapter = ClapEmbeddingAdapter(device=request.device)
        vector = adapter.embed_text(query)
        filters = SearchFilters(min_similarity=request.min_similarity)
        try:
            return SimilaritySearch(state.require_db(), embedding_key=adapter.embedding_key).search_vector(
                vector,
                filters=filters,
                limit=request.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/export")
    def export(request: ExportRequest):
        db = state.require_db()
        try:
            tracks = [db.get_track(track_id) for track_id in request.track_ids]
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        path = export_tracks(request.name, tracks, request.output_dir, request.format)
        return {"path": str(path)}

    @app.post("/api/tags/genres/apply")
    def genre_tags_apply(request: GenreTagRequest):
        db = state.require_db()
        if request.track_ids is not None:
            raise HTTPException(status_code=400, detail="Writing MAEST genres to specific tracks is no longer supported")
        return apply_genre_tags_to_tracks(db, db.list_tracks_with_maest_genres())

    @app.post("/api/tags/genres/jobs")
    def genre_tags_job_start(request: GenreTagRequest):
        if request.track_ids is not None:
            raise HTTPException(status_code=400, detail="Writing MAEST genres to specific tracks is no longer supported")
        return state.require_genre_tag_jobs().start(request.track_ids)

    @app.get("/api/tags/genres/jobs/latest")
    def latest_genre_tags_job():
        return state.require_genre_tag_jobs().latest()

    @app.get("/api/tags/genres/jobs/{job_id}")
    def genre_tags_job(job_id: str):
        try:
            return state.require_genre_tag_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/tags/genres/jobs/{job_id}/cancel")
    def cancel_genre_tags_job(job_id: str):
        try:
            return state.require_genre_tag_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/dialog/folder")
    def folder_dialog():
        try:
            selected = open_folder_dialog()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return {"path": str(selected) if selected else None}

    @app.get("/media/{track_id}")
    def media(track_id: int):
        track = state.require_db().get_track(track_id)
        path = Path(track.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Audio file is missing")
        if path.suffix.lower() in AIFF_PREVIEW_SUFFIXES:
            return _transcoded_wav_response(path, ffmpeg_path)
        return FileResponse(path)

    package_path = Path(__file__).resolve()
    static_candidates = [
        package_path.parents[2] / "frontend" / "dist",
        package_path.parent.parent / "frontend" / "dist",
    ]
    static_dir = next((candidate for candidate in static_candidates if candidate.exists()), None)
    if static_dir is not None:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app


def _transcoded_wav_response(path: Path, ffmpeg_path: str) -> StreamingResponse:
    command = [
        ffmpeg_path,
        "-v",
        "error",
        "-i",
        str(path),
        "-vn",
        "-f",
        "wav",
        "-codec:a",
        "pcm_s16le",
        "pipe:1",
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def iter_wav_chunks():
        try:
            if process.stdout is None:
                return
            while True:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                yield chunk
            return_code = process.wait()
            if return_code != 0:
                LOGGER.warning("ffmpeg preview transcode failed path=%s return_code=%s", path, return_code)
        finally:
            if process.poll() is None:
                process.kill()

    return StreamingResponse(iter_wav_chunks(), media_type="audio/wav")
