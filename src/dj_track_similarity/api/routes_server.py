from __future__ import annotations

import asyncio
import logging
import signal
from collections.abc import Callable
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException
from fastapi.concurrency import run_in_threadpool


SHUTDOWN_ACTION_HEADER = "shutdown-server"
LOGGER = logging.getLogger(__name__)


def shutdown_current_process(delay_seconds: float = 0.25) -> None:
    # Deliver the signal on the event-loop thread so Uvicorn can drain its
    # lifespan handlers. os.kill(..., SIGTERM) forcibly terminates on Windows.
    asyncio.get_running_loop().call_later(delay_seconds, signal.raise_signal, signal.SIGTERM)


async def shutdown_server_and_dependents(
    *,
    shutdown_server: Callable[[], None],
    stop_rhythm_lab: Callable[[], dict[str, object]] | None,
) -> None:
    try:
        if stop_rhythm_lab is not None:
            await run_in_threadpool(stop_rhythm_lab)
    except Exception:
        LOGGER.exception("Dependent Rhythm Lab server cleanup failed during application shutdown")
    finally:
        shutdown_server()


def register_server_routes(
    app: FastAPI,
    *,
    shutdown_server: Callable[[], None] = shutdown_current_process,
    stop_rhythm_lab: Callable[[], dict[str, object]] | None = None,
) -> None:
    @app.post("/api/server/shutdown")
    def shutdown_server_route(
        background_tasks: BackgroundTasks,
        action: Annotated[str | None, Header(alias="X-DJ-Track-Similarity-Action")] = None,
    ):
        if action != SHUTDOWN_ACTION_HEADER:
            raise HTTPException(status_code=403, detail="Server shutdown requires the explicit shutdown action header")
        LOGGER.info("Server shutdown requested from UI")
        background_tasks.add_task(
            shutdown_server_and_dependents,
            shutdown_server=shutdown_server,
            stop_rhythm_lab=stop_rhythm_lab,
        )
        return {"status": "shutdown_requested"}
