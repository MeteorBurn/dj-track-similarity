from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .api_route_utils import query_classifier_min_scores, valid_classifier_min_scores
from .api_schemas import FilteredTracksRequest, RelocateLibraryRequest, ScanRequest, TagRefreshRequest, TrackLikedRequest
from .api_state import AppDatabaseState
from .media_preview import AudioPreviewError, transcoded_wav_file_response


AIFF_PREVIEW_SUFFIXES = {".aif", ".aiff"}


def register_library_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    ffmpeg_path: str,
    promoted_classifiers: Callable[[], list[dict[str, object]]],
) -> None:
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
        search_mode: str = Query(default="like", pattern="^(like|fts)$"),
        classifier_min_scores: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        include_metadata: bool = False,
    ):
        return state.require_db().list_tracks_page(
            query=q,
            preset=preset,
            liked_only=liked,
            classifier_min_scores=query_classifier_min_scores(classifier_min_scores),
            limit=limit,
            offset=offset,
            include_metadata=include_metadata,
            search_mode=search_mode,
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
            classifier_min_scores=valid_classifier_min_scores(request.classifier_min_scores),
            search_mode=request.search_mode,
        )

    @app.get("/api/library/summary")
    def library_summary():
        classifier_keys = [
            str(classifier["classifier_key"])
            for classifier in promoted_classifiers()
            if bool(classifier.get("is_scoring_compatible", True))
        ]
        return state.require_db().library_summary(classifier_keys=classifier_keys)

    @app.get("/media/{track_id}")
    def media(track_id: int):
        track = state.require_db().get_track(track_id)
        path = Path(track.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Audio file is missing")
        try:
            if path.suffix.lower() in AIFF_PREVIEW_SUFFIXES:
                return transcoded_wav_file_response(path, ffmpeg_path)
            return FileResponse(path)
        except AudioPreviewError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except OSError as error:
            raise HTTPException(status_code=422, detail=f"Audio preview failed: {error}") from error
