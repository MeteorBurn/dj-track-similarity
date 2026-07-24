from __future__ import annotations

import sqlite3

from fastapi import FastAPI, HTTPException

from .api_schemas import ReferenceCompareRequest, ReferenceCompareVerdictRequest
from .api_state import AppDatabaseState
from .reference_compare import (
    ReferenceCompareQuery,
    build_reference_compare,
    record_reference_compare_verdict_exact,
)
from .track_models import TrackIdentity


def register_reference_compare_routes(app: FastAPI, state: AppDatabaseState) -> None:
    @app.post("/api/reference/compare")
    def reference_compare(request: ReferenceCompareRequest):
        try:
            return build_reference_compare(
                state.require_db(),
                ReferenceCompareQuery(
                    seed_track_id=request.seed_track_id,
                    models=tuple(request.models),
                    limit=request.limit,
                ),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/reference/compare/verdict")
    def reference_compare_verdict(request: ReferenceCompareVerdictRequest):
        try:
            database = state.require_db()
            seed = TrackIdentity(
                catalog_uuid=request.seed.catalog_uuid,
                track_id=request.seed.track_id,
                track_uuid=request.seed.track_uuid,
                content_generation=request.seed.content_generation,
            )
            candidate = TrackIdentity(
                catalog_uuid=request.candidate.catalog_uuid,
                track_id=request.candidate.track_id,
                track_uuid=request.candidate.track_uuid,
                content_generation=request.candidate.content_generation,
            )
            return record_reference_compare_verdict_exact(
                database,
                seed=seed,
                candidate=candidate,
                model=request.model,
                verdict=request.verdict,
                notes=request.notes,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    _ = reference_compare
    _ = reference_compare_verdict
