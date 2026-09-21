from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dj_track_similarity.api import application as api_module
from dj_track_similarity.api.state import AppDatabaseState, DatabaseBusy
from dj_track_similarity.classifier.jobs import ClassifierJobManager
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.scan_jobs import ScanJobManager
from dj_track_similarity.tags import GenreTagJobManager
from dj_track_similarity.track_models import FileTags, ScannedFile


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api_module, "configure_shared_ffmpeg_runtime", lambda: None)
    return TestClient(api_module.create_app(db_path))


def _track(database: LibraryDatabase, audio_path: Path):
    audio_path.write_bytes(b"audio")
    stat = audio_path.stat()
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(audio_path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
        ),
        tags=FileTags(
            title="Typed Track",
            artist="API Fixture",
        ),
    ).identity


def test_track_responses_expose_current_identity_and_split_coverage(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    identity = _track(database, tmp_path / "track.wav")

    response = _client(monkeypatch, db_path).get("/api/tracks")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["track_id"] == identity.track_id
    assert item["catalog_uuid"] == identity.catalog_uuid
    assert item["track_uuid"] == identity.track_uuid
    assert item["analysis_coverage"] == {
        "sonara_core": False,
        "maest_analysis": False,
        "maest_embedding": False,
        "muq": False,
        "mert_v2": False,
        "muq": False,
        "mulan": False,
        "clap": False,
    }


def test_tag_refresh_job_rejects_stale_file_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    audio_path = tmp_path / "track.wav"
    identity = _track(database, audio_path)
    queued_stat = audio_path.stat()

    def run_tag_refresh_synchronously(
        manager: ScanJobManager,
        *,
        workers: int = 1,
    ):
        job_id = manager.create_tag_refresh_job(workers=workers)
        return manager.run_tag_refresh_job(job_id)

    def update_file_then_return_stale_read(path: Path, **_kwargs):
        assert path == audio_path.resolve()
        path.write_bytes(b"newer-audio")
        current_stat = path.stat()
        mutation = database.upsert_scanned_track(
            file=ScannedFile(
                file_path=str(path),
                file_size_bytes=current_stat.st_size,
                file_modified_ns=current_stat.st_mtime_ns,
                audio_format="wav",
            ),
            tags=FileTags(title="New metadata"),
        )
        assert mutation.action == "updated"
        assert mutation.identity.track_id == identity.track_id
        return {"title": "Stale metadata"}, queued_stat

    monkeypatch.setattr(
        ScanJobManager,
        "start_tag_refresh",
        run_tag_refresh_synchronously,
    )
    monkeypatch.setattr(
        "dj_track_similarity.scan_jobs.read_audio_metadata_stable",
        update_file_then_return_stale_read,
    )

    response = _client(monkeypatch, db_path).post(
        "/api/library/tags/refresh",
        json={"workers": 1},
    )

    assert response.status_code == 200
    status = response.json()
    assert status["state"] == "completed"
    assert status["processed"] == 1
    assert status["updated"] == 0
    assert status["failed"] == 1
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT ft.title
            FROM tracks AS t
            JOIN tags AS ft ON ft.track_id = t.track_id
            WHERE t.track_id = ?
            """,
            (identity.track_id,),
        ).fetchone()
    assert row["title"] == "New metadata"


def test_database_switch_creates_a_missing_bundle_only_on_request(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api_module, "configure_shared_ffmpeg_runtime", lambda: None)
    monkeypatch.chdir(tmp_path)
    client = TestClient(api_module.create_app())
    core_path = tmp_path / "selected.sqlite"

    current = client.get("/api/database/current")

    assert current.status_code == 200
    assert current.json() == {
        "path": None,
        "evaluation_path": None,
        "catalog_uuid": None,
        "selected": False,
    }
    assert not (tmp_path / "dj-track-similarity.sqlite").exists()

    refused = client.post(
        "/api/database/switch",
        json={"path": str(core_path)},
    )

    assert refused.status_code == 404
    assert refused.json() == {
        "detail": f"Library database not found: {core_path.resolve()}"
    }
    assert not core_path.exists()
    assert client.get("/api/database/current").json()["selected"] is False

    response = client.post(
        "/api/database/switch",
        json={"path": str(core_path), "create": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == str(core_path.resolve())
    assert payload["catalog_uuid"]
    assert payload["selected"] is True
    assert core_path.is_file()


def test_reset_and_summary_use_analysis_family_names(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    client = _client(monkeypatch, db_path)

    reset = client.post(
        "/api/analysis/reset",
        json={"analysis_family": "muq"},
    )
    legacy = client.post(
        "/api/analysis/reset",
        json={"adapter": "muq"},
    )
    summary = client.get("/api/library/summary")

    assert reset.status_code == 200
    assert reset.json() == {
        "feature_rows_deleted": 0,
        "embedding_rows_deleted": 0,
        "classifier_rows_deleted": 0,
    }
    assert legacy.status_code == 422
    assert summary.status_code == 200
    assert summary.json() == {
        "tracks": 0,
        "sonara": 0,
        "maest_analysis": 0,
        "maest_embedding": 0,
        "muq": 0,
        "mert_v2": 0,
        "muq": 0,
        "mulan": 0,
        "clap": 0,
        "liked": 0,
        "classifiers": 0,
        "sonara_bpm_min": None,
        "sonara_bpm_max": None,
    }


def test_classifier_preflight_conflict_returns_http_409_before_start(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def reject_inputs(_manager, **_kwargs) -> None:
        raise RuntimeError("classifier inputs are not available")

    monkeypatch.setattr(
        api_module,
        "promoted_classifiers",
        lambda: [{"classifier_key": "voice_presence"}],
    )
    monkeypatch.setattr(ClassifierJobManager, "start", reject_inputs)
    client = _client(monkeypatch, tmp_path / "library.sqlite")

    response = client.post(
        "/api/classifiers/voice_presence/analyze",
        json={"limit": 0},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "classifier inputs are not available"
    }


def test_exclusive_database_operation_blocks_new_jobs(
    tmp_path: Path,
) -> None:
    state = AppDatabaseState(tmp_path / "library.sqlite")

    with state.exclusive_db("prepare a SONARA release"):
        with pytest.raises(DatabaseBusy, match="prepare a SONARA release"):
            state.require_analysis_jobs()

    assert state.require_analysis_jobs() is not None


def test_job_start_reservation_closes_exclusive_operation_toctou(
    tmp_path: Path,
) -> None:
    state = AppDatabaseState(tmp_path / "library.sqlite")
    reservation_entered = threading.Event()
    release_reservation = threading.Event()
    exclusive_finished = threading.Event()
    exclusive_result: list[str] = []

    def reserve_and_queue() -> None:
        with state.job_start(state.require_genre_tag_jobs, "write genre tags") as manager:
            reservation_entered.set()
            assert release_reservation.wait(timeout=5)
            manager.create_job()

    def try_exclusive_operation() -> None:
        try:
            with state.exclusive_db("prepare a SONARA release"):
                exclusive_result.append("entered")
        except DatabaseBusy:
            exclusive_result.append("blocked")
        finally:
            exclusive_finished.set()

    start_thread = threading.Thread(target=reserve_and_queue)
    prepare_thread = threading.Thread(target=try_exclusive_operation)
    start_thread.start()
    assert reservation_entered.wait(timeout=5)
    prepare_thread.start()

    assert not exclusive_finished.wait(timeout=0.1)
    release_reservation.set()
    start_thread.join(timeout=5)
    prepare_thread.join(timeout=5)

    assert not start_thread.is_alive()
    assert not prepare_thread.is_alive()
    assert exclusive_result == ["blocked"]


def test_start_is_refused_with_409_while_the_same_or_a_conflicting_job_is_active(
    monkeypatch,
    tmp_path: Path,
) -> None:
    # The first writer never leaves "queued", like a job still waiting to run.
    monkeypatch.setattr(GenreTagJobManager, "run_job", lambda _manager, _job_id: None)
    monkeypatch.setattr(ScanJobManager, "run_job", lambda _manager, _job_id: None)
    scan_root = tmp_path / "music"
    scan_root.mkdir()
    client = _client(monkeypatch, tmp_path / "library.sqlite")

    first = client.post("/api/tags/genres/jobs", json={})
    second = client.post("/api/tags/genres/jobs", json={})
    scan = client.post("/api/library/scan", json={"root": str(scan_root), "workers": 1})
    latest = client.get("/api/tags/genres/jobs/latest")
    latest_scan = client.get("/api/library/scan/jobs/latest")

    assert first.status_code == 200
    assert second.status_code == 409
    assert first.json()["job_id"] in second.json()["detail"]
    # Scanning reads the files the genre writer rewrites.
    assert scan.status_code == 409
    assert first.json()["job_id"] in scan.json()["detail"]
    # start() creates the job before it spawns the thread, so the refused
    # requests left neither another job nor another thread behind.
    assert latest.json()["job_id"] == first.json()["job_id"]
    assert latest_scan.json() is None


def test_state_close_drains_inline_pipeline_children_outside_state_lock(
    monkeypatch, tmp_path: Path,
) -> None:
    state = AppDatabaseState(tmp_path / "pipeline.sqlite")
    audio = state.require_analysis_jobs()
    pipeline = state.require_analysis_pipeline_jobs()
    queue = state.analysis_queue
    entered = threading.Event()
    release = threading.Event()
    joining = threading.Event()
    closed = threading.Event()
    second_closed = threading.Event()
    joined = queue._thread.join
    order = []
    interrupt = KeyboardInterrupt("state drain interrupted")
    interrupted = False
    close_errors = []

    def observe_join(*args, **kwargs):
        nonlocal interrupted
        joining.set()
        if not interrupted:
            interrupted = True
            raise interrupt
        return joined(*args, **kwargs)

    def execute(job_id):
        models = audio.get(job_id).models
        order.append(models)
        if models == ["sonara"]:
            with pytest.raises(RuntimeError, match="worker"):
                state.close()
            assert state.require_analysis_jobs() is audio
            entered.set()
            assert release.wait(5)
            with pytest.raises(RuntimeError, match="worker"):
                state.close()
        # This lock acquisition must remain possible while shutdown is joining.
        assert state.current()["selected"]
        audio._update(job_id, state="completed")
        return audio.get(job_id)

    monkeypatch.setattr(queue._thread, "join", observe_join)
    monkeypatch.setattr(audio, "_execute_job", execute)
    monkeypatch.setattr(audio, "current_sonara_track_count", lambda: 1)

    def close():
        try:
            state.close()
        except BaseException as error:
            close_errors.append(error.with_traceback(None))
        finally:
            closed.set()

    closer = threading.Thread(target=close, daemon=True)
    second_close = threading.Thread(target=lambda: (state.close(), second_closed.set()), daemon=True)
    try:
        job = pipeline.start(stage="sonara", limit=None)
        # SONARA and ML never share a pipeline, so the ML run is queued behind
        # it as its own pipeline; closing must still drain both.
        ml_job = pipeline.start(stage="ml", limit=None, ml={"models": ["muq"]})
        assert entered.wait(5)
        closer.start()
        assert joining.wait(5)
        second_close.start()
        assert not closed.wait(0.1)
        with pytest.raises(DatabaseBusy, match="closed"):
            with state.exclusive_db("late operation"):
                pytest.fail("closed state admitted an exclusive operation")
    finally:
        release.set()
        if closer.ident is None:
            closer.start()
        closer.join(5)
        if second_close.ident is not None:
            second_close.join(5)
    assert not closer.is_alive()
    assert not second_close.is_alive()
    assert second_closed.is_set()
    assert not queue._thread.is_alive()
    assert closed.is_set()
    assert close_errors == [interrupt]
    assert pipeline.get(job.job_id).state == "completed"
    assert pipeline.get(ml_job.job_id).state == "completed"
    assert order == [["sonara"], ["muq"]]
    with pytest.raises(RuntimeError, match="closed"):
        audio.run_sync(models=["muq"], device="cpu")
