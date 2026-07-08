from __future__ import annotations

import sqlite3

from fastapi import FastAPI, HTTPException

from .api_schemas import ReferenceCompareRequest, ReferenceCompareVerdictRequest
from .api_state import AppDatabaseState
from .reference_compare import ReferenceCompareQuery, build_reference_compare, record_reference_compare_verdict


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
            return record_reference_compare_verdict(
                state.require_db(),
                seed_track_id=request.seed_track_id,
                candidate_track_id=request.candidate_track_id,
                model=request.model,
                verdict=request.verdict,
                notes=request.notes,
            )
        except (ValueError, sqlite3.IntegrityError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    _ = reference_compare
    _ = reference_compare_verdict
