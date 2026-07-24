from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dj_track_similarity import api as api_module
from dj_track_similarity import api_state
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.logging_config import (
    install_asyncio_exception_logging,
)
from dj_track_similarity.track_models import FileTags, ScannedFile


@pytest.fixture(autouse=True)
def _ffmpeg(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg")


def _add_track(
    database: LibraryDatabase,
    path: Path,
    *,
    title: str,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")
    stat = path.stat()
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
            audio_codec="pcm_s16le",
            sample_rate_hz=44_100,
            channel_count=2,
            audio_duration_seconds=1.0,
        ),
        tags=FileTags(title=title, artist="Database Selection Fixture"),
    ).identity


def _selected_state(database: LibraryDatabase) -> dict[str, object]:
    return {
        "path": str(database.path),
        "artifacts_path": str(database.artifacts_path),
        "evaluation_path": str(database.evaluation_path),
        "catalog_uuid": database.catalog_uuid,
        "selected": True,
    }


def test_app_without_db_starts_unselected_and_blocks_database_endpoints() -> None:
    client = TestClient(api_module.create_app())

    current = client.get("/api/database/current")
    summary = client.get("/api/library/summary")

    assert current.status_code == 200
    assert current.json() == {
        "path": None,
        "artifacts_path": None,
        "evaluation_path": None,
        "catalog_uuid": None,
        "selected": False,
    }
    assert summary.status_code == 400
    assert summary.json() == {"detail": "Database is not selected"}


@pytest.mark.parametrize(
    ("method", "path", "json_payload"),
    [
        ("post", "/api/database/clear", {}),
        ("get", "/api/library/summary", None),
        ("get", "/api/tracks", None),
        ("post", "/api/tracks/filtered", {"query": "", "liked": False}),
        ("get", "/media/1", None),
    ],
)
def test_selected_database_required_endpoints_return_api_error_without_traceback(
    method: str,
    path: str,
    json_payload: dict[str, object] | None,
) -> None:
    client = TestClient(
        api_module.create_app(),
        raise_server_exceptions=False,
    )

    response = client.request(method.upper(), path, json=json_payload)

    assert response.status_code == 400
    assert response.json() == {"detail": "Database is not selected"}
    assert "Traceback" not in response.text


def test_app_registers_asyncio_exception_logging_startup() -> None:
    app = api_module.create_app()

    assert install_asyncio_exception_logging in app.router.on_startup


def test_http_error_responses_are_written_to_app_log(
    monkeypatch,
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "app.log"
    monkeypatch.setenv("DJ_TRACK_SIMILARITY_LOG", str(log_path))
    client = TestClient(api_module.create_app())

    response = client.get("/api/library/summary")

    assert response.status_code == 400
    for handler in logging.getLogger("dj_track_similarity").handlers:
        handler.flush()
    contents = log_path.read_text(encoding="utf-8")
    assert (
        "HTTP request returned error method=GET "
        "path=/api/library/summary status=400"
    ) in contents


def test_database_switch_creates_selected_v7_bundle(tmp_path: Path) -> None:
    db_path = tmp_path / "new-library.sqlite"
    client = TestClient(api_module.create_app())

    response = client.post(
        "/api/database/switch",
        json={"path": str(db_path)},
    )

    assert response.status_code == 200
    database = LibraryDatabase(db_path)
    assert response.json() == _selected_state(database)
    assert database.path.is_file()
    assert database.artifacts_path.is_file()
    assert not database.evaluation_path.exists()
    assert client.get("/api/library/summary").json() == {
        "tracks": 0,
        "sonara": 0,
        "maest_analysis": 0,
        "maest_embedding": 0,
        "mert": 0,
        "muq": 0,
        "clap": 0,
        "liked": 0,
        "classifiers": 0,
    }


def test_database_switch_reads_existing_v7_bundle_and_identity(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "existing.sqlite"
    database = LibraryDatabase(db_path)
    identity = _add_track(
        database,
        tmp_path / "track.wav",
        title="Stored Track",
    )
    client = TestClient(api_module.create_app())

    response = client.post(
        "/api/database/switch",
        json={"path": str(db_path)},
    )

    assert response.status_code == 200
    assert response.json() == _selected_state(database)
    tracks = client.get("/api/tracks").json()
    assert tracks["total"] == 1
    assert tracks["items"][0]["track_id"] == identity.track_id
    assert tracks["items"][0]["catalog_uuid"] == identity.catalog_uuid
    assert tracks["items"][0]["track_uuid"] == identity.track_uuid
    assert tracks["items"][0]["content_generation"] == 1
    assert tracks["items"][0]["title"] == "Stored Track"


def test_database_file_dialog_switches_to_selected_v7_bundle(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selected = tmp_path / "picked.sqlite"
    monkeypatch.setattr(
        api_module,
        "open_database_file_dialog",
        lambda: selected,
    )
    client = TestClient(api_module.create_app())

    response = client.post("/api/database/dialog")

    assert response.status_code == 200
    database = LibraryDatabase(selected)
    assert response.json() == _selected_state(database)
    assert database.path.is_file()
    assert database.artifacts_path.is_file()


def test_database_file_dialog_cancel_preserves_unselected_state(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        api_module,
        "open_database_file_dialog",
        lambda: None,
    )
    client = TestClient(api_module.create_app())

    response = client.post("/api/database/dialog")

    assert response.status_code == 200
    assert response.json()["selected"] is False
    assert response.json()["catalog_uuid"] is None


def test_scan_accepts_existing_directory_without_persisting_request_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    scan_root = tmp_path / "music"
    scan_root.mkdir()

    def run_synchronously(
        manager: api_state.ScanJobManager,
        root: str | Path,
        *,
        workers: int = 1,
    ):
        return manager.run_sync(root, workers=workers)

    monkeypatch.setattr(
        api_state.ScanJobManager,
        "start",
        run_synchronously,
    )
    client = TestClient(api_module.create_app(db_path))
    before = client.get("/api/database/current").json()

    response = client.post(
        "/api/library/scan",
        json={"root": str(scan_root), "workers": 1},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "completed"
    assert response.json()["root"].casefold() == str(
        scan_root.resolve()
    ).casefold()
    assert client.get("/api/database/current").json() == before


def test_scan_rejects_missing_directory_without_mutating_selected_bundle(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    client = TestClient(api_module.create_app(db_path))
    before = client.get("/api/database/current").json()

    response = client.post(
        "/api/library/scan",
        json={"root": str(tmp_path / "missing"), "workers": 1},
    )

    assert response.status_code == 400
    assert "missing" in response.json()["detail"]
    assert client.get("/api/database/current").json() == before


def test_database_switch_is_rejected_while_scan_job_is_queued(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    next_db_path = tmp_path / "next.sqlite"
    scan_root = tmp_path / "music"
    scan_root.mkdir()

    def queue_without_running(
        manager: api_state.ScanJobManager,
        root: str | Path,
        *,
        workers: int = 1,
    ):
        job_id = manager.create_job(root, workers=workers)
        return manager.get(job_id)

    monkeypatch.setattr(
        api_state.ScanJobManager,
        "start",
        queue_without_running,
    )
    client = TestClient(api_module.create_app(db_path))

    scan_response = client.post(
        "/api/library/scan",
        json={"root": str(scan_root), "workers": 1},
    )
    switch_response = client.post(
        "/api/database/switch",
        json={"path": str(next_db_path)},
    )

    assert scan_response.status_code == 200
    assert scan_response.json()["state"] == "queued"
    assert switch_response.status_code == 409
    assert switch_response.json() == {
        "detail": "Cannot switch database while jobs are running"
    }
