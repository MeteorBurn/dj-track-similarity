from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from dj_track_similarity import api
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.database_optimization_jobs import DatabaseOptimizationJobManager
from dj_track_similarity.database_validation_jobs import DatabaseValidationJobManager
from dj_track_similarity.track_models import FileTags, ScannedFile


def test_optimization_job_api_backs_up_and_reports_the_library(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(database_path)
    mutation = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / "track.wav"),
            file_size_bytes=1,
            file_modified_ns=1,
            audio_format="wav",
        ),
        tags=FileTags(title="Fixture", artist="Artist"),
    )
    monkeypatch.setattr(DatabaseOptimizationJobManager, "start", DatabaseOptimizationJobManager.run_sync)
    client = TestClient(api.create_app(database_path))

    started = client.post("/api/database/optimization/jobs")

    assert started.status_code == 200
    payload = started.json()
    assert payload["state"] == "completed"
    assert payload["error"] is None
    assert payload["database_kind"] == "library"
    assert payload["size_before"] > 0 and payload["size_after"] > 0
    assert [item["role"] for item in payload["files"]] == ["library"]
    library_file = payload["files"][0]
    assert Path(library_file["backup_path"]).is_file()
    assert library_file["journal_mode"] == "wal"
    assert library_file["checkpoint"] == "complete"
    assert any(event["level"] == "ok" and "Backup of library verified" in event["message"] for event in payload["events"])
    with database.connect() as connection:
        assert connection.execute(
            "SELECT track_uuid FROM tracks WHERE track_id = ?",
            (mutation.identity.track_id,),
        ).fetchone()[0] == mutation.identity.track_uuid

    latest = client.get("/api/database/optimization/jobs/latest")

    assert latest.status_code == 200
    assert latest.json()["job_id"] == payload["job_id"]


def test_optimization_job_refuses_to_start_while_another_job_is_active(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "library.sqlite"
    LibraryDatabase(database_path)
    release = threading.Event()

    def hold(self: DatabaseValidationJobManager, job_id: str):
        # Keep the validation job queued until the test lets it go, so the
        # database counts as busy while the optimizer is asked to start.
        release.wait(timeout=10)
        self._store.update(job_id, state="cancelled", finished_at=time.time())
        return self.get(job_id)

    monkeypatch.setattr(DatabaseValidationJobManager, "run_job", hold)
    client = TestClient(api.create_app(database_path))
    assert client.post("/api/database/validation/jobs").status_code == 200

    try:
        refused = client.post("/api/database/optimization/jobs")
    finally:
        release.set()

    assert refused.status_code == 409
    assert "optimize the database" in refused.json()["detail"]
