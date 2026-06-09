from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .api_state import AppDatabaseState


def register_rhythm_lab_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    launch_rhythm_lab: Callable[[Path | None], dict[str, object]],
) -> None:
    @app.post("/api/rhythm-lab/launch")
    def launch_rhythm_lab_server():
        source_db = state.db_path
        try:
            return launch_rhythm_lab(source_db)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
