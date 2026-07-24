from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .api_schemas import (
    ExportRequest,
    GenreTagApplyResultV7,
    GenreTagRequest,
)
from .api_state import AppDatabaseState
from .exporter import export_tracks
from .tags import apply_genre_tags_to_tracks


def register_tags_export_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    open_folder_dialog: Callable[[], Path | None],
) -> None:
    @app.post("/api/export")
    def export(request: ExportRequest):
        db = state.require_db()
        try:
            tracks = db.export_track_rows(request.track_ids)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        path = export_tracks(request.name, tracks, request.output_dir, request.format)
        return {"path": str(path)}

    @app.post(
        "/api/tags/genres/apply",
        response_model=list[GenreTagApplyResultV7],
    )
    def genre_tags_apply(_request: GenreTagRequest):
        with state.exclusive_db("write genre tags") as database:
            candidates = database.list_genre_tag_candidates()
            results = apply_genre_tags_to_tracks(database, candidates)
        candidate_by_id = {
            candidate.track_id: candidate for candidate in candidates
        }
        return [
            {
                "catalog_uuid": candidate_by_id[result.track_id].catalog_uuid,
                "track_id": result.track_id,
                "track_uuid": candidate_by_id[result.track_id].track_uuid,
                "content_generation": candidate_by_id[
                    result.track_id
                ].content_generation,
                "file_path": result.path,
                "tags": result.tags,
                "status": result.status,
                "message": result.message,
                "error": result.error,
            }
            for result in results
        ]

    @app.post("/api/tags/genres/jobs")
    def genre_tags_job_start(_request: GenreTagRequest):
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
