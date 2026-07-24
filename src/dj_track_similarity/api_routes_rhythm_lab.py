from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .api_schemas import TrackIdentityRequestV7
from .api_state import AppDatabaseState
from .rhythm_lab_collections import (
    RhythmLabCollections,
    build_rhythm_lab_collection_selection_exact,
    default_rhythm_lab_labels_path,
)
from .rhythm_lab_launcher import RhythmLabSourceBinding
from .track_models import TrackIdentity


class RhythmLabCollectionSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    tracks: list[TrackIdentityRequestV7] = Field(min_length=1)
    source: str = "main_ui_playlist"
    note: str | None = None
    mode: Literal["append", "replace"] = "append"

    @model_validator(mode="after")
    def reject_duplicate_tracks(self) -> "RhythmLabCollectionSaveRequest":
        identities = {
            (
                track.catalog_uuid,
                track.track_uuid,
                track.content_generation,
            )
            for track in self.tracks
        }
        if len(identities) != len(self.tracks):
            raise ValueError("tracks must contain unique v7 identities")
        return self


def register_rhythm_lab_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    launch_rhythm_lab: Callable[
        [RhythmLabSourceBinding | None],
        dict[str, object],
    ],
    stop_rhythm_lab: Callable[[], dict[str, object]],
    rhythm_lab_status: Callable[[], dict[str, object]],
) -> None:
    @app.get("/api/rhythm-lab/status")
    def get_rhythm_lab_status():
        return rhythm_lab_status()

    @app.post("/api/rhythm-lab/launch")
    def launch_rhythm_lab_server():
        source = None
        if state.db_path is not None:
            db = state.require_db()
            source = RhythmLabSourceBinding(
                source_db=db.path,
                catalog_uuid=db.catalog_uuid,
            )
        try:
            return launch_rhythm_lab(source)
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
            expected_identities = [
                TrackIdentity(
                    catalog_uuid=track.catalog_uuid,
                    track_id=track.track_id,
                    track_uuid=track.track_uuid,
                    content_generation=track.content_generation,
                )
                for track in request.tracks
            ]
            selection = build_rhythm_lab_collection_selection_exact(
                db,
                expected_identities,
            )
            collection = RhythmLabCollections(default_rhythm_lab_labels_path()).save_collection(
                request.name,
                selection,
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
