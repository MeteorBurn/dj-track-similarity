from __future__ import annotations

import os
import signal
import threading
from collections.abc import Callable
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException


SHUTDOWN_ACTION_HEADER = "shutdown-server"


def shutdown_current_process(delay_seconds: float = 0.25) -> None:
    def terminate() -> None:
        os.kill(os.getpid(), signal.SIGTERM)

    timer = threading.Timer(delay_seconds, terminate)
    timer.daemon = True
    timer.start()


def register_server_routes(
    app: FastAPI,
    *,
    shutdown_server: Callable[[], None] = shutdown_current_process,
) -> None:
    @app.post("/api/server/shutdown")
    def shutdown_server_route(
        background_tasks: BackgroundTasks,
        action: Annotated[str | None, Header(alias="X-DJ-Track-Similarity-Action")] = None,
    ):
        if action != SHUTDOWN_ACTION_HEADER:
            raise HTTPException(status_code=403, detail="Server shutdown requires the explicit shutdown action header")
        background_tasks.add_task(shutdown_server)
        return {"status": "shutdown_requested"}
