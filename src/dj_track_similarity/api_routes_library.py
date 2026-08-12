from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .api_route_utils import (
    current_classifier_specifications,
    query_classifier_min_scores,
    valid_classifier_min_scores,
)
from .api_schemas import (
    ClearLibraryResponse,
    FilteredTracksRequest,
    LibrarySummaryResponse,
    RelocateLibraryRequest,
    ScanRequest,
    TagRefreshRequest,
    TrackDetailResponse,
    TrackLikedRequest,
    TrackPageResponse,
    TrackSummaryResponse,
)
from .api_state import AppDatabaseState
from .media_preview import AudioPreviewError, requires_browser_preview_transcode, transcoded_wav_file_response
from .track_models import TrackIdentity


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
            with state.job_start():
                return state.require_scan_jobs().start(
                    request.root,
                    workers=request.workers,
                    limit=request.limit,
                )
        except (FileNotFoundError, NotADirectoryError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/library/tags/refresh")
    def refresh_tags(request: TagRefreshRequest):
        with state.job_start():
            return state.require_scan_jobs().start_tag_refresh(workers=request.workers)

    @app.post("/api/library/relocate")
    def relocate_library(request: RelocateLibraryRequest):
        try:
            if not request.apply:
                return state.require_db().relocate_library(
                    request.old_root,
                    request.new_root,
                    apply=False,
                )
            with state.exclusive_db("relocate the library") as database:
                return database.relocate_library(
                    request.old_root,
                    request.new_root,
                    apply=True,
                )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post(
        "/api/database/clear",
        response_model=ClearLibraryResponse,
    )
    def clear_database():
        with state.exclusive_db("clear the library") as database:
            return database.clear_library()

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

    @app.get("/api/tracks", response_model=TrackPageResponse)
    def tracks(
        q: str = "",
        preset: str = Query(default="all", pattern="^(all|syncopated)$"),
        liked: bool = False,
        search_mode: str = Query(default="like", pattern="^(like|fts)$"),
        classifier_min_scores: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ):
        classifier_specifications = current_classifier_specifications(
            promoted_classifiers()
        )
        return state.require_db().paginate_track_summaries(
            query=q,
            syncopated_only=preset == "syncopated",
            liked_only=liked,
            classifier_min_scores=query_classifier_min_scores(classifier_min_scores),
            limit=limit,
            offset=offset,
            search_mode=search_mode,
            classifier_specifications=classifier_specifications,
        )

    @app.post("/api/tracks/{track_id}/liked", response_model=TrackSummaryResponse)
    def set_track_liked(track_id: int, request: TrackLikedRequest):
        try:
            classifier_specifications = current_classifier_specifications(
                promoted_classifiers()
            )
            return state.require_db().set_track_liked(
                expected=TrackIdentity(
                    catalog_uuid=request.catalog_uuid,
                    track_id=track_id,
                    track_uuid=request.track_uuid,
                    content_generation=request.expected_content_generation,
                ),
                liked=request.liked,
                classifier_specifications=classifier_specifications,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/tracks/{track_id}", response_model=TrackDetailResponse)
    def track(track_id: int):
        try:
            classifier_specifications = current_classifier_specifications(
                promoted_classifiers()
            )
            return state.require_db().get_track_detail(
                track_id,
                classifier_specifications=classifier_specifications,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/tracks/filtered", response_model=list[TrackSummaryResponse])
    def filtered_tracks(request: FilteredTracksRequest):
        classifier_specifications = current_classifier_specifications(
            promoted_classifiers()
        )
        return state.require_db().filter_track_summaries(
            query=request.query,
            syncopated_only=request.preset == "syncopated",
            liked_only=request.liked,
            classifier_min_scores=valid_classifier_min_scores(request.classifier_min_scores),
            search_mode=request.search_mode,
            classifier_specifications=classifier_specifications,
        )

    @app.get("/api/library/summary", response_model=LibrarySummaryResponse)
    def library_summary():
        return state.require_db().library_summary()

    @app.get("/media/{track_id}")
    def media(track_id: int):
        try:
            path = state.require_db().get_media_path(track_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if not path.exists():
            raise HTTPException(status_code=404, detail="Audio file is missing")
        try:
            if requires_browser_preview_transcode(path):
                return transcoded_wav_file_response(path, ffmpeg_path)
            return FileResponse(path)
        except AudioPreviewError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except OSError as error:
            raise HTTPException(status_code=422, detail=f"Audio preview failed: {error}") from error
