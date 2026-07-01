from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .api_state import AppDatabaseState
from .rhythm_lab_collections import RhythmLabCollections, default_rhythm_lab_labels_path


class RhythmLabCollectionSaveRequest(BaseModel):
    name: str
    track_ids: list[int]
    source: str = "main_ui_playlist"
    note: str | None = None
    mode: str = "append"


def register_rhythm_lab_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    launch_rhythm_lab: Callable[[Path | None], dict[str, object]],
    stop_rhythm_lab: Callable[[], dict[str, object]],
    rhythm_lab_status: Callable[[], dict[str, object]],
) -> None:
    @app.get("/api/rhythm-lab/status")
    def get_rhythm_lab_status():
        return rhythm_lab_status()

    @app.post("/api/rhythm-lab/launch")
    def launch_rhythm_lab_server():
        source_db = state.db_path
        try:
            return launch_rhythm_lab(source_db)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post("/api/rhythm-lab/stop")
    def stop_rhythm_lab_server():
        try:
            return stop_rhythm_lab()
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post("/api/rhythm-lab/collections")
    def save_rhythm_lab_collection(request: RhythmLabCollectionSaveRequest):
        try:
            db = state.require_db()
            for track_id in request.track_ids:
                db.get_track(int(track_id))
            collection = RhythmLabCollections(default_rhythm_lab_labels_path()).save_collection(
                request.name,
                request.track_ids,
                source=request.source,
                note=request.note,
                mode=request.mode,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {
            "id": collection.id,
            "name": collection.name,
            "source": collection.source,
            "track_count": collection.track_count,
            "updated_at": collection.updated_at,
        }
