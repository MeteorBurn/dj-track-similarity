from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dj_track_similarity import api
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.database_validation_jobs import DatabaseValidationJobManager
from dj_track_similarity.track_models import FileTags, ScannedFile


def test_validation_job_api_exposes_completed_job_and_its_ui_events(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(database_path)
    database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / "missing.wav"),
            file_size_bytes=1,
            file_modified_ns=1,
            audio_format="wav",
        ),
        tags=FileTags(title="Missing fixture"),
    )
    monkeypatch.setattr(DatabaseValidationJobManager, "start", DatabaseValidationJobManager.run_sync)
    client = TestClient(api.create_app(database_path))

    started = client.post("/api/database/validation/jobs")

    assert started.status_code == 200
    payload = started.json()
    assert payload["state"] == "completed"
    assert payload["checked"] >= 1
    assert any(event["level"] == "ok" for event in payload["events"])
    assert payload["failures"][0]["code"] == "track_path_missing"
    assert payload["failures"][0]["track_id"] == 1
    assert payload["failures_omitted"] == 0

    latest = client.get("/api/database/validation/jobs/latest")

    assert latest.status_code == 200
    assert latest.json()["job_id"] == payload["job_id"]
