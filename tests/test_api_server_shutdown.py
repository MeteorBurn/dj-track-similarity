from __future__ import annotations

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


def test_shutdown_route_schedules_shutdown_after_acknowledgement() -> None:
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
