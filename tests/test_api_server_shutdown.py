from __future__ import annotations

import json
import subprocess
import sys
import textwrap

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_shutdown_route_requires_explicit_action_header() -> None:
    from dj_track_similarity.api.routes_server import register_server_routes

    calls: list[str] = []
    app = FastAPI()
    register_server_routes(app, shutdown_server=lambda: calls.append("shutdown"))

    response = TestClient(app).post("/api/server/shutdown")

    assert response.status_code == 403
    assert calls == []


def test_shutdown_route_acknowledges_and_runs_graceful_process_cleanup() -> None:
    from dj_track_similarity.api.routes_server import register_server_routes

    calls: list[str] = []
    app = FastAPI()
    register_server_routes(app, shutdown_server=lambda: calls.append("shutdown"))

    response = TestClient(app).post(
        "/api/server/shutdown",
        headers={"X-DJ-Track-Similarity-Action": "shutdown-server"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "shutdown_requested"}
    assert calls == ["shutdown"]

    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent("""
            import asyncio
            import json
            import signal
            import socket

            from starlette.background import BackgroundTask
            from dj_track_similarity.api.routes_server import (
                shutdown_current_process,
                shutdown_server_and_dependents,
            )

            events = []

            async def main():
                stopped = asyncio.Event()

                def handle_shutdown(signum, frame):
                    events.append("shutdown handled")
                    stopped.set()

                signal.signal(signal.SIGTERM, handle_shutdown)
                listener = socket.socket()
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                address = listener.getsockname()
                try:
                    await BackgroundTask(
                        shutdown_server_and_dependents,
                        shutdown_server=shutdown_current_process,
                        stop_rhythm_lab=None,
                    )()
                    await asyncio.wait_for(stopped.wait(), timeout=5)
                finally:
                    listener.close()
                    events.append("cleanup completed")
                with socket.socket() as restarted:
                    restarted.bind(address)
                    restarted.listen()
                    events.append("port reusable")

            asyncio.run(main())
            print(json.dumps(events))
        """)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout) == [
        "shutdown handled", "cleanup completed", "port reusable",
    ]


def test_shutdown_route_stops_managed_dependencies_before_server() -> None:
    from dj_track_similarity.api.routes_server import register_server_routes

    calls: list[str] = []
    app = FastAPI()
    register_server_routes(
        app,
        shutdown_server=lambda: calls.append("server"),
        stop_rhythm_lab=lambda: calls.append("rhythm-lab") or {},
    )

    response = TestClient(app).post(
        "/api/server/shutdown",
        headers={"X-DJ-Track-Similarity-Action": "shutdown-server"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "shutdown_requested"}
    assert calls == ["rhythm-lab", "server"]


def test_shutdown_route_still_stops_server_when_dependency_cleanup_fails() -> None:
    from dj_track_similarity.api.routes_server import register_server_routes

    calls: list[str] = []

    def fail_rhythm_lab_stop() -> dict[str, object]:
        calls.append("rhythm-lab")
        raise RuntimeError("Rhythm Lab refused to stop")

    app = FastAPI()
    register_server_routes(
        app,
        shutdown_server=lambda: calls.append("server"),
        stop_rhythm_lab=fail_rhythm_lab_stop,
    )

    response = TestClient(app, raise_server_exceptions=False).post(
        "/api/server/shutdown",
        headers={"X-DJ-Track-Similarity-Action": "shutdown-server"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "shutdown_requested"}
    assert calls == ["rhythm-lab", "server"]
