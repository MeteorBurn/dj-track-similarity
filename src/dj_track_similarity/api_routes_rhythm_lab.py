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
