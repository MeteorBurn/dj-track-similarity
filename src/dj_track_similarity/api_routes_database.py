from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .api_schemas import DatabaseStateResponse, DatabaseSwitchRequest
from .api_state import AppDatabaseState


def register_database_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    open_database_file_dialog: Callable[[], Path | None],
) -> None:
    @app.get("/api/database/current", response_model=DatabaseStateResponse)
    def current_database():
        return state.current()

    @app.post("/api/database/switch", response_model=DatabaseStateResponse)
    def switch_database(request: DatabaseSwitchRequest):
        try:
            return state.switch(request.path)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/database/dialog", response_model=DatabaseStateResponse)
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
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
