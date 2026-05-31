from __future__ import annotations

import logging
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .analysis_config import normalize_analysis_models
from .api_schemas import (
    AnalysisJobRequest,
    AnalysisResetRequest,
    ClassifierAnalyzeRequest,
    ClassifierResetRequest,
    DatabaseSwitchRequest,
    ExportRequest,
    FilteredTracksRequest,
    GenreTagRequest,
    RelocateLibraryRequest,
    ScanRequest,
    SearchRequest,
    SonaraSearchRequest,
    TagRefreshRequest,
    TextSearchRequest,
    TrackLikedRequest,
)
from .api_state import AppDatabaseState, DatabaseBusy, DatabaseNotSelected
from .classifier_scoring import promoted_classifiers
from .dependencies import require_ffmpeg
from .embedding import ClapEmbeddingAdapter
from .exporter import export_tracks
from .logging_config import configure_logging
from .media_preview import transcoded_wav_file_response
from .search import SearchFilters, SimilaritySearch
from .sonara_similarity import SonaraSimilaritySearch
from .tags import apply_genre_tags_to_tracks


LOGGER = logging.getLogger(__name__)


AIFF_PREVIEW_SUFFIXES = {".aif", ".aiff"}


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
        liked: bool = False,
        classifier_min_scores: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        include_metadata: bool = False,
    ):
        return state.require_db().list_tracks_page(
            query=q,
            preset=preset,
            liked_only=liked,
            classifier_min_scores=_query_classifier_min_scores(classifier_min_scores),
            limit=limit,
            offset=offset,
            include_metadata=include_metadata,
        )

    @app.post("/api/tracks/{track_id}/liked")
    def set_track_liked(track_id: int, request: TrackLikedRequest):
        try:
            return state.require_db().set_track_liked(track_id, request.liked)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

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
            liked_only=request.liked,
            classifier_min_scores=_valid_classifier_min_scores(request.classifier_min_scores),
        )

    @app.get("/api/library/summary")
    def library_summary():
        classifier_keys = [str(classifier["classifier_key"]) for classifier in promoted_classifiers()]
        return state.require_db().library_summary(classifier_keys=classifier_keys)

    @app.post("/api/analysis/reset")
    def reset_analysis(request: AnalysisResetRequest):
        try:
            return state.require_db().reset_analysis(request.adapter)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/analysis/jobs")
    def analyze(request: AnalysisJobRequest):
        try:
            models = list(normalize_analysis_models(request.models))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return state.require_analysis_jobs().start(
            models=models,
            limit=request.limit,
            track_batch_size=request.track_batch_size,
            inference_batch_size=request.inference_batch_size,
            device=request.device,
            top_k=request.top_k,
        )

    @app.get("/api/classifiers")
    def classifiers():
        return promoted_classifiers()

    @app.post("/api/classifiers/{classifier_key}/analyze")
    def analyze_classifier(classifier_key: str, request: ClassifierAnalyzeRequest):
        return state.require_classifier_jobs().start(classifier=classifier_key, limit=request.limit)

    @app.post("/api/classifiers/reset")
    def reset_classifiers(request: ClassifierResetRequest):
        return state.require_db().reset_classifier_scores(request.classifiers)

    @app.get("/api/classifiers/{classifier_key}/analyze/jobs/latest")
    def latest_classifier_job(classifier_key: str):
        return state.require_classifier_jobs().latest(classifier=classifier_key)

    @app.get("/api/classifiers/{classifier_key}/analyze/jobs/{job_id}")
    def classifier_job(classifier_key: str, job_id: str):
        try:
            return state.require_classifier_jobs().get(job_id, classifier=classifier_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/classifiers/{classifier_key}/analyze/jobs/{job_id}/cancel")
    def cancel_classifier_job(classifier_key: str, job_id: str):
        try:
            return state.require_classifier_jobs().cancel(job_id, classifier=classifier_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/analysis/jobs/latest")
    def latest_analyze_job():
        return state.require_analysis_jobs().latest()

    @app.get("/api/analysis/jobs/{job_id}")
    def analyze_job(job_id: str):
        try:
            return state.require_analysis_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/analysis/jobs/{job_id}/cancel")
    def cancel_analyze_job(job_id: str):
        try:
            return state.require_analysis_jobs().cancel(job_id)
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
        return state.require_genre_tag_jobs().start()

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
            return transcoded_wav_file_response(path, ffmpeg_path)
        return FileResponse(path)

    package_path = Path(__file__).resolve()
    docs_candidates = [
        package_path.parents[2] / "docs" / "dj-track-similarity" / "site",
        package_path.parent.parent / "docs" / "dj-track-similarity" / "site",
    ]
    docs_dir = next((candidate for candidate in docs_candidates if candidate.exists()), None)
    if docs_dir is not None:
        app.mount("/docs", StaticFiles(directory=docs_dir, html=True), name="docs")

    static_candidates = [
        package_path.parents[2] / "frontend" / "dist",
        package_path.parent.parent / "frontend" / "dist",
    ]
    static_dir = next((candidate for candidate in static_candidates if candidate.exists()), None)
    if static_dir is not None:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app


def _query_classifier_min_scores(raw: str | None) -> dict[str, float]:
    if raw is None or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail="classifier_min_scores must be a JSON object") from error
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="classifier_min_scores must be a JSON object")
    return _valid_classifier_min_scores(parsed)


def _valid_classifier_min_scores(scores: dict[str, float]) -> dict[str, float]:
    result: dict[str, float] = {}
    for classifier, value in scores.items():
        score = float(value)
        if score < 0.0 or score > 1.0:
            raise HTTPException(status_code=422, detail=f"Classifier threshold out of range: {classifier}")
        result[str(classifier)] = score
    return result
