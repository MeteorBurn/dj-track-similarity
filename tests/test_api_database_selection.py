from __future__ import annotations

import logging
import threading
import weakref
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dj_track_similarity.api import application as api_module
from dj_track_similarity.api import state as api_state
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.logging_config import (
    install_asyncio_exception_logging,
)
from dj_track_similarity.track_models import FileTags, ScannedFile


@pytest.fixture(autouse=True)
def _shared_ffmpeg(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "configure_shared_ffmpeg_runtime", lambda: None)


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
            sample_rate_hz=44_100,
            channel_count=2,
            audio_duration_seconds=1.0,
        ),
        tags=FileTags(title=title, artist="Database Selection Fixture"),
    ).identity


def _selected_state(database: LibraryDatabase) -> dict[str, object]:
    return {
        "path": str(database.path),
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


def test_database_switch_creates_selected_current_bundle(tmp_path: Path) -> None:
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
    assert not database.evaluation_path.exists()
    assert client.get("/api/library/summary").json() == {
        "tracks": 0,
        "sonara": 0,
        "maest_analysis": 0,
        "maest_embedding": 0,
        "mert": 0,
        "muq": 0,
        "mulan": 0,
        "clap": 0,
        "liked": 0,
        "classifiers": 0,
        "sonara_bpm_min": None,
        "sonara_bpm_max": None,
    }


def test_database_switch_reads_existing_current_bundle_and_identity(
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
    assert tracks["items"][0]["title"] == "Stored Track"


def test_database_file_dialog_switches_to_selected_current_bundle(
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
        **kwargs: object,
    ):
        return manager.run_sync(root, **kwargs)

    monkeypatch.setattr(
        api_state.ScanJobManager,
        "start",
        run_synchronously,
    )
    client = TestClient(api_module.create_app(db_path))
    before = client.get("/api/database/current").json()

    response = client.post(
        "/api/library/scan",
        json={"root": str(scan_root), "workers": 1, "limit": 1},
    )

    assert response.status_code == 200
    assert response.json()["state"] == "completed"
    assert response.json()["limit"] == 1
    assert response.json()["root"].casefold() == str(
        scan_root.resolve()
    ).casefold()
    assert client.get("/api/database/current").json() == before


def test_scan_forwards_format_and_duration_filters_to_job_manager(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    scan_root = tmp_path / "music"
    scan_root.mkdir()
    captured: dict[str, object] = {}

    def capture_start(
        manager: api_state.ScanJobManager,
        root: str | Path,
        **kwargs: object,
    ):
        captured["root"] = root
        captured.update(kwargs)
        return manager.run_sync(root)

    monkeypatch.setattr(api_state.ScanJobManager, "start", capture_start)
    client = TestClient(api_module.create_app(db_path))

    response = client.post(
        "/api/library/scan",
        json={
            "root": str(scan_root),
            "workers": 3,
            "extensions": [".mp3", ".flac"],
            "min_duration_seconds": 120,
            "max_duration_seconds": 1200,
        },
    )

    assert response.status_code == 200
    assert captured == {
        "root": str(scan_root),
        "workers": 3,
        "limit": None,
        "extensions": {".mp3", ".flac"},
        "min_duration_seconds": 120,
        "max_duration_seconds": 1200,
    }


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
        **kwargs: object,
    ):
        job_id = manager.create_job(root, **kwargs)
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


def test_idle_switch_releases_previous_owners_and_failed_switch_keeps_state(
    monkeypatch, tmp_path: Path,
) -> None:
    state = api_state.AppDatabaseState(tmp_path / "first.sqlite")
    first_queue = state.analysis_queue
    first_worker = first_queue._thread
    retiring = threading.Event()
    rejected_self_close = threading.Event()
    first_join = first_worker.join

    def observe_retirement(*args, **kwargs):
        retiring.set()
        return first_join(*args, **kwargs)

    def old_callback():
        assert retiring.wait(5)
        with pytest.raises(RuntimeError, match="worker"):
            state.close()
        rejected_self_close.set()

    monkeypatch.setattr(first_worker, "join", observe_retirement)
    first_queue.submit(old_callback)
    first_queue_ref = weakref.ref(first_queue)
    first_manager_ref = weakref.ref(state.analysis_jobs)
    first_manager_close = api_state.AnalysisJobManager.close

    def close_old_manager(manager):
        with pytest.raises(RuntimeError, match="replacement cleanup"):
            state.close()
        first_manager_close(manager)

    del first_queue
    with monkeypatch.context() as close_observer:
        close_observer.setattr(api_state.AnalysisJobManager, "close", close_old_manager)
        state.switch(tmp_path / "second.sqlite")
    assert rejected_self_close.is_set()
    assert not first_worker.is_alive()
    assert first_queue_ref() is None
    assert first_manager_ref() is None
    before = state.current()
    current_manager = state.require_analysis_jobs()
    partial_workers = []
    partial_owners = []
    queue_factory = api_state.AnalysisStageQueue
    manager_factory = api_state.AnalysisJobManager

    def capture_queue():
        queue = queue_factory()
        partial_workers.append(queue._thread)
        partial_owners.append(weakref.ref(queue))
        return queue

    def capture_manager(*args, **kwargs):
        manager = manager_factory(*args, **kwargs)
        partial_owners.append(weakref.ref(manager))
        return manager

    def fail_later_owner(_database):
        raise RuntimeError("replacement construction failed")

    monkeypatch.setattr(api_state, "AnalysisStageQueue", capture_queue)
    monkeypatch.setattr(api_state, "AnalysisJobManager", capture_manager)
    monkeypatch.setattr(api_state, "GenreTagJobManager", fail_later_owner)
    try:
        with pytest.raises(RuntimeError, match="replacement construction failed"):
            state.switch(tmp_path / "failed.sqlite")
        assert state.current() == before
        assert state.require_analysis_jobs() is current_manager
        assert all(not worker.is_alive() for worker in partial_workers)
        assert all(owner() is None for owner in partial_owners)
        completed = threading.Event()
        state.analysis_queue.submit(completed.set)
        assert completed.wait(5)
    finally:
        state.close()
    state.close()
    with pytest.raises(api_state.DatabaseBusy, match="closed"):
        state.switch(tmp_path / "late.sqlite")


@pytest.mark.parametrize("fail_close", [False, True])
def test_app_lifespan_closes_state_and_text_cache_even_on_cleanup_error(
    monkeypatch, tmp_path: Path, fail_close: bool,
) -> None:
    events = []
    states = []

    class ObservedState(api_state.AppDatabaseState):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            states.append(self)

        def close(self):
            super().close()
            events.append("state")
            if fail_close:
                raise RuntimeError("cleanup failure")

    cache_close = api_module.TextEmbeddingAdapterCache.close

    def close_cache(cache):
        cache_close(cache)
        events.append("text-cache")

    monkeypatch.setattr(api_module, "AppDatabaseState", ObservedState)
    monkeypatch.setattr(api_module.TextEmbeddingAdapterCache, "close", close_cache)
    app = api_module.create_app(tmp_path / "lifespan.sqlite")
    queue_worker = states[0].analysis_queue._thread

    def use_app():
        with TestClient(app) as client:
            assert client.get("/api/database/current").status_code == 200
            assert queue_worker.is_alive()

    if fail_close:
        with pytest.raises(RuntimeError, match="cleanup failure"):
            use_app()
    else:
        use_app()
    assert sorted(events) == ["state", "text-cache"]
    assert not queue_worker.is_alive()
    with pytest.raises(api_state.DatabaseBusy, match="closed"):
        with states[0].job_start():
            pytest.fail("closed state admitted work")
