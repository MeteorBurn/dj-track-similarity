from __future__ import annotations

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dj_track_similarity import api as api_module
from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.api_state import AppDatabaseState, DatabaseBusy
from dj_track_similarity.classifier_jobs import ClassifierJobManager
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.scan_jobs import ScanJobManager
from dj_track_similarity.track_models import FileTags, ScannedFile


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg")
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


def test_track_responses_expose_v7_identity_and_split_coverage(
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
    assert item["content_generation"] == identity.content_generation
    assert item["analysis_coverage"] == {
        "sonara_core": False,
        "timeline": False,
        "sonara_embedding": False,
        "fingerprint": False,
        "maest_analysis": False,
        "maest_embedding": False,
        "mert": False,
        "muq": False,
        "clap": False,
    }


def test_tag_refresh_job_rejects_stale_snapshot_after_generation_race(
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

    def advance_generation_then_return_stale_read(path: Path, **_kwargs):
        assert path == audio_path.resolve()
        path.write_bytes(b"generation-two-audio")
        current_stat = path.stat()
        mutation = database.upsert_scanned_track(
            file=ScannedFile(
                file_path=str(path),
                file_size_bytes=current_stat.st_size,
                file_modified_ns=current_stat.st_mtime_ns,
                audio_format="wav",
            ),
            tags=FileTags(title="Generation 2"),
        )
        assert mutation.action == "updated"
        assert mutation.identity.track_id == identity.track_id
        assert mutation.identity.content_generation == 2
        return {"title": "Stale generation 1"}, queued_stat

    monkeypatch.setattr(
        ScanJobManager,
        "start_tag_refresh",
        run_tag_refresh_synchronously,
    )
    monkeypatch.setattr(
        "dj_track_similarity.scan_jobs.read_audio_metadata_stable",
        advance_generation_then_return_stale_read,
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
            SELECT t.content_generation, ft.title
            FROM tracks AS t
            JOIN file_tags AS ft ON ft.track_id = t.track_id
            WHERE t.track_id = ?
            """,
            (identity.track_id,),
        ).fetchone()
    assert int(row["content_generation"]) == 2
    assert row["title"] == "Generation 2"


def test_database_switch_bootstraps_clean_selected_v7_bundle(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.chdir(tmp_path)
    client = TestClient(api_module.create_app())
    core_path = tmp_path / "selected.sqlite"

    current = client.get("/api/database/current")

    assert current.status_code == 200
    assert current.json() == {
        "path": None,
        "artifacts_path": None,
        "evaluation_path": None,
        "catalog_uuid": None,
        "selected": False,
    }
    assert not (tmp_path / "dj-track-similarity.sqlite").exists()
    assert not (tmp_path / "dj-track-similarity.artifacts.sqlite").exists()

    response = client.post(
        "/api/database/switch",
        json={"path": str(core_path)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["path"] == str(core_path.resolve())
    assert payload["artifacts_path"] == str(
        core_path.with_suffix(".artifacts.sqlite").resolve()
    )
    assert payload["catalog_uuid"]
    assert payload["selected"] is True
    assert core_path.is_file()
    assert core_path.with_suffix(".artifacts.sqlite").is_file()


def test_liked_mutation_requires_current_composite_identity(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    identity = _track(database, tmp_path / "track.wav")
    client = _client(monkeypatch, db_path)
    url = f"/api/tracks/{identity.track_id}/liked"
    payload = {
        "catalog_uuid": identity.catalog_uuid,
        "track_uuid": identity.track_uuid,
        "expected_content_generation": identity.content_generation,
        "liked": True,
    }

    stale = client.post(
        url,
        json={**payload, "expected_content_generation": 2},
    )
    current = client.post(url, json=payload)

    assert stale.status_code == 409
    assert "content generation changed" in stale.json()["detail"]
    assert current.status_code == 200
    assert current.json()["liked"] is True
    assert current.json()["track_uuid"] == identity.track_uuid


def test_prepare_sonara_release_uses_selected_database_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from dj_track_similarity import prepare_sonara_release as prepare_module

    db_path = tmp_path / "library.sqlite"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    captured: dict[str, object] = {}

    def fake_prepare(database, *, backup_dir: Path, confirm: str):
        captured["database"] = database
        captured["backup_dir"] = backup_dir
        captured["confirm"] = confirm
        return {
            "receipt_version": 1,
            "operation_id": "sha256:" + "1" * 64,
            "stage": "completed",
            "catalog_uuid": database.catalog_uuid,
            "core_path": str(database.path),
            "artifacts_path": str(database.artifacts_path),
            "backup_dir": str(backup_dir),
            "release_hash": "sha256:" + "2" * 64,
            "contract_hashes": {
                "core": "sha256:" + "3" * 64,
                "timeline": "sha256:" + "4" * 64,
                "embedding": "sha256:" + "5" * 64,
                "fingerprint": "sha256:" + "6" * 64,
            },
            "backups": {
                "core": {
                    "path": str(backup_dir / "core.sqlite"),
                    "sha256": "sha256:" + "7" * 64,
                    "size_bytes": 100,
                },
                "artifacts": {
                    "path": str(backup_dir / "artifacts.sqlite"),
                    "sha256": "sha256:" + "8" * 64,
                    "size_bytes": 200,
                },
            },
            "activation_result": {
                "core_rows_deleted": 1,
                "artifact_rows_deleted": 2,
                "classifier_rows_deleted": 3,
            },
            "started_at": "2026-07-24T12:00:00+00:00",
            "updated_at": "2026-07-24T12:00:01+00:00",
            "completed_at": "2026-07-24T12:00:01+00:00",
        }

    monkeypatch.setattr(
        prepare_module,
        "prepare_sonara_release",
        fake_prepare,
    )
    client = _client(monkeypatch, db_path)
    catalog_uuid = client.get("/api/database/current").json()["catalog_uuid"]

    response = client.post(
        "/api/analysis/sonara/releases/prepare",
        json={
            "catalog_uuid": catalog_uuid,
            "backup_dir": str(backup_dir),
            "confirm": "PREPARE SONARA RELEASE",
        },
    )
    rejected = client.post(
        "/api/analysis/sonara/releases/prepare",
        json={
            "db": str(tmp_path / "other.sqlite"),
            "catalog_uuid": catalog_uuid,
            "backup_dir": str(backup_dir),
            "confirm": "PREPARE SONARA RELEASE",
        },
    )

    assert response.status_code == 200
    assert captured["database"].path == db_path.resolve()
    assert captured["backup_dir"] == backup_dir
    assert captured["confirm"] == "PREPARE SONARA RELEASE"
    assert response.json()["contract_hashes"]["fingerprint"] == (
        "sha256:" + "6" * 64
    )
    assert response.json()["activation_result"] == {
        "core_rows_deleted": 1,
        "artifact_rows_deleted": 2,
        "classifier_rows_deleted": 3,
    }
    assert rejected.status_code == 422


def test_prepare_sonara_release_rejects_stale_catalog_before_mutation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from dj_track_similarity import prepare_sonara_release as prepare_module

    first_path = tmp_path / "first.sqlite"
    second_path = tmp_path / "second.sqlite"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    prepared_catalogs: list[str] = []

    def fake_prepare(database, **_kwargs):
        prepared_catalogs.append(database.catalog_uuid)
        raise AssertionError("stale catalog must be rejected before preparation")

    monkeypatch.setattr(
        prepare_module,
        "prepare_sonara_release",
        fake_prepare,
    )
    client = _client(monkeypatch, first_path)
    first_catalog = client.get("/api/database/current").json()["catalog_uuid"]

    switched = client.post(
        "/api/database/switch",
        json={"path": str(second_path)},
    )
    stale = client.post(
        "/api/analysis/sonara/releases/prepare",
        json={
            "catalog_uuid": first_catalog,
            "backup_dir": str(backup_dir),
            "confirm": "PREPARE SONARA RELEASE",
        },
    )

    assert switched.status_code == 200
    assert switched.json()["catalog_uuid"] != first_catalog
    assert stale.status_code == 409
    assert stale.json() == {
        "detail": (
            "SONARA_CATALOG_CHANGED: the selected catalog changed; "
            "refresh SONARA release status before preparing"
        )
    }
    assert prepared_catalogs == []


def test_prepare_sonara_release_returns_409_while_job_is_active(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from dj_track_similarity import prepare_sonara_release as prepare_module

    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    prepare_called = False

    def active_job(_manager):
        return type("_ActiveJob", (), {"state": "queued"})()

    def fake_prepare(*_args, **_kwargs):
        nonlocal prepare_called
        prepare_called = True
        raise AssertionError("preparation must not run while a job is active")

    monkeypatch.setattr(AnalysisJobManager, "latest", active_job)
    monkeypatch.setattr(
        prepare_module,
        "prepare_sonara_release",
        fake_prepare,
    )
    client = _client(monkeypatch, db_path)

    response = client.post(
        "/api/analysis/sonara/releases/prepare",
        json={
            "catalog_uuid": database.catalog_uuid,
            "backup_dir": str(backup_dir),
            "confirm": "PREPARE SONARA RELEASE",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Cannot prepare a SONARA release while jobs are running"
    }
    assert prepare_called is False


def test_reset_and_summary_contracts_use_v7_family_names(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    client = _client(monkeypatch, db_path)

    reset = client.post(
        "/api/analysis/reset",
        json={"analysis_family": "mert"},
    )
    legacy = client.post(
        "/api/analysis/reset",
        json={"adapter": "mert"},
    )
    summary = client.get("/api/library/summary")

    assert reset.status_code == 200
    assert reset.json() == {
        "core_rows_deleted": 0,
        "artifact_rows_deleted": 0,
        "classifier_rows_deleted": 0,
    }
    assert legacy.status_code == 422
    assert summary.status_code == 200
    assert summary.json() == {
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


def test_sonara_analysis_unavailable_conflict_is_not_mislabeled_as_preparation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def reject_release(_manager) -> None:
        raise RuntimeError(
            "SONARA release status is unavailable: runtime package is not installed"
        )

    monkeypatch.setattr(
        AnalysisJobManager,
        "validate_sonara_preflight",
        reject_release,
    )
    client = _client(monkeypatch, tmp_path / "library.sqlite")

    response = client.post(
        "/api/analysis/jobs",
        json={"models": ["sonara"]},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "SONARA release status is unavailable: runtime package is not installed"
    )


def test_classifier_preflight_conflict_returns_http_409_before_start(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def reject_inputs(_manager, **_kwargs) -> None:
        raise RuntimeError("classifier input contracts are not active")

    monkeypatch.setattr(
        api_module,
        "promoted_classifiers",
        lambda: [{"classifier_key": "voice_presence"}],
    )
    monkeypatch.setattr(ClassifierJobManager, "start", reject_inputs)
    client = _client(monkeypatch, tmp_path / "library.sqlite")

    response = client.post(
        "/api/classifiers/analyze",
        json={"classifier_keys": ["voice_presence"]},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "classifier input contracts are not active"
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
    monkeypatch,
    tmp_path: Path,
) -> None:
    state = AppDatabaseState(tmp_path / "library.sqlite")
    manager = state.require_analysis_jobs()
    reservation_entered = threading.Event()
    release_reservation = threading.Event()
    queued = threading.Event()
    exclusive_finished = threading.Event()
    exclusive_result: list[str] = []

    monkeypatch.setattr(
        manager,
        "latest",
        lambda: (
            None
            if not queued.is_set()
            else type("_QueuedJob", (), {"state": "queued"})()
        ),
    )

    def reserve_and_queue() -> None:
        with state.job_start():
            reservation_entered.set()
            assert release_reservation.wait(timeout=5)
            queued.set()

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
