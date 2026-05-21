from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .analysis_jobs import AnalysisJobManager
from .database import LibraryDatabase
from .dependencies import require_ffmpeg
from .embedding import ClapEmbeddingAdapter
from .exporter import export_playlist
from .genre_jobs import GenreAnalysisJobManager
from .logging_config import configure_logging
from .scan_jobs import ScanJobManager
from .search import SearchFilters, SimilaritySearch
from .sonara_similarity import SonaraSimilaritySearch
from .sonara_jobs import SonaraFeatureJobManager
from .tags import GenreTagJobManager, apply_custom_tags, apply_genre_tags, apply_genre_tags_to_tracks, build_tag_preview


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


class AnalyzeRequest(BaseModel):
    limit: int | None = None
    adapter: str = Field(default="mert", pattern="^(mert|clap|fake)$")
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


class AnalysisResetRequest(BaseModel):
    adapter: str = Field(pattern="^(sonara|maest|mert|clap|fake)$")


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


class PlaylistRequest(BaseModel):
    name: str
    track_ids: list[int]


class ExportRequest(BaseModel):
    playlist_id: int
    output_dir: str
    format: str = Field(default="m3u", pattern="^(m3u|csv)$")


class TagRequest(BaseModel):
    track_ids: list[int]


class GenreTagRequest(BaseModel):
    track_ids: list[int] | None = None


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


def create_app(
    db_path: str | Path = "dj-track-similarity.sqlite",
    *,
    log_level: int | str | None = None,
    log_track_events: bool | None = None,
) -> FastAPI:
    log_path = configure_logging(level=log_level, log_track_events=log_track_events)
    ffmpeg_path = require_ffmpeg()
    LOGGER.info("API app created db_path=%s log_path=%s", db_path, log_path)
    LOGGER.debug("ffmpeg available path=%s", ffmpeg_path)
    db = LibraryDatabase(db_path)
    analysis_jobs = AnalysisJobManager(db)
    genre_jobs = GenreAnalysisJobManager(db)
    sonara_jobs = SonaraFeatureJobManager(db)
    scan_jobs = ScanJobManager(db)
    genre_tag_jobs = GenreTagJobManager(db)
    app = FastAPI(title="dj-track-similarity Utility")

    @app.post("/api/library/scan")
    def scan(request: ScanRequest):
        return scan_jobs.start(request.root, workers=request.workers)

    @app.post("/api/library/tags/refresh")
    def refresh_tags(request: TagRefreshRequest):
        return scan_jobs.start_tag_refresh(workers=request.workers)

    @app.post("/api/library/relocate")
    def relocate_library(request: RelocateLibraryRequest):
        try:
            return db.relocate_library(request.old_root, request.new_root, apply=request.apply)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/database/clear")
    def clear_database():
        return db.clear_library()

    @app.get("/api/library/scan/jobs/latest")
    def latest_scan_job():
        return scan_jobs.latest()

    @app.get("/api/library/scan/jobs/{job_id}")
    def scan_job(job_id: str):
        try:
            return scan_jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/library/scan/jobs/{job_id}/cancel")
    def cancel_scan_job(job_id: str):
        try:
            return scan_jobs.cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/tracks")
    def tracks(
        q: str = "",
        preset: str = Query(default="all", pattern="^(all|syncopated)$"),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        include_metadata: bool = False,
    ):
        return db.list_tracks_page(
            query=q,
            preset=preset,
            limit=limit,
            offset=offset,
            include_metadata=include_metadata,
        )

    @app.get("/api/tracks/{track_id}")
    def track(track_id: int):
        try:
            return db.get_track(track_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/library/summary")
    def library_summary():
        return db.library_summary()

    @app.post("/api/analysis/reset")
    def reset_analysis(request: AnalysisResetRequest):
        try:
            return db.reset_analysis(request.adapter)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/analyze")
    def analyze(request: AnalyzeRequest):
        return analysis_jobs.start(
            adapter_name=request.adapter,
            limit=request.limit,
            batch_size=request.batch_size,
            workers=request.workers,
            device=request.device,
        )

    @app.post("/api/sonara/analyze")
    def analyze_sonara(request: SonaraAnalyzeRequest):
        return sonara_jobs.start(limit=request.limit, batch_size=request.batch_size)

    @app.get("/api/sonara/analyze/jobs/latest")
    def latest_sonara_job():
        return sonara_jobs.latest()

    @app.get("/api/sonara/analyze/jobs/{job_id}")
    def sonara_job(job_id: str):
        try:
            return sonara_jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/sonara/analyze/jobs/{job_id}/cancel")
    def cancel_sonara_job(job_id: str):
        try:
            return sonara_jobs.cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/analyze/jobs/latest")
    def latest_analyze_job():
        return analysis_jobs.latest()

    @app.get("/api/analyze/jobs/{job_id}")
    def analyze_job(job_id: str):
        try:
            return analysis_jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/analyze/jobs/{job_id}/cancel")
    def cancel_analyze_job(job_id: str):
        try:
            return analysis_jobs.cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/genres/analyze")
    def analyze_genres(request: GenreAnalyzeRequest):
        return genre_jobs.start(
            limit=request.limit,
            device=request.device,
            top_k=request.top_k,
            batch_size=request.batch_size,
        )

    @app.get("/api/genres/analyze/jobs/latest")
    def latest_genre_job():
        return genre_jobs.latest()

    @app.get("/api/genres/analyze/jobs/{job_id}")
    def genre_job(job_id: str):
        try:
            return genre_jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/genres/analyze/jobs/{job_id}/cancel")
    def cancel_genre_job(job_id: str):
        try:
            return genre_jobs.cancel(job_id)
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
            return SimilaritySearch(db).search(
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
            return SonaraSimilaritySearch(db).search(
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
            return SimilaritySearch(db, embedding_key=adapter.embedding_key).search_vector(
                vector,
                filters=filters,
                limit=request.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/playlists")
    def playlists(request: PlaylistRequest):
        playlist_id = db.create_playlist(request.name, request.track_ids)
        return {"id": playlist_id, "name": request.name, "track_ids": request.track_ids}

    @app.post("/api/export")
    def export(request: ExportRequest):
        path = export_playlist(db, request.playlist_id, request.output_dir, request.format)
        return {"path": str(path)}

    @app.post("/api/tags/preview")
    def tags_preview(request: TagRequest):
        return build_tag_preview(db, request.track_ids)

    @app.post("/api/tags/apply")
    def tags_apply(request: TagRequest):
        return apply_custom_tags(db, request.track_ids)

    @app.post("/api/tags/genres/apply")
    def genre_tags_apply(request: GenreTagRequest):
        if request.track_ids is None:
            return apply_genre_tags_to_tracks(db, db.list_tracks_with_maest_genres())
        return apply_genre_tags(db, request.track_ids)

    @app.post("/api/tags/genres/jobs")
    def genre_tags_job_start(request: GenreTagRequest):
        return genre_tag_jobs.start(request.track_ids)

    @app.get("/api/tags/genres/jobs/latest")
    def latest_genre_tags_job():
        return genre_tag_jobs.latest()

    @app.get("/api/tags/genres/jobs/{job_id}")
    def genre_tags_job(job_id: str):
        try:
            return genre_tag_jobs.get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/tags/genres/jobs/{job_id}/cancel")
    def cancel_genre_tags_job(job_id: str):
        try:
            return genre_tag_jobs.cancel(job_id)
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
        track = db.get_track(track_id)
        path = Path(track.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Audio file is missing")
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
