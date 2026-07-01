from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
import dj_track_similarity.api_state as api_state
from dj_track_similarity.database import LibraryDatabase


class SynchronousAudioDoctorManager:
    last_request: dict[str, object] = {}
    xlsx_path: Path | None = None

    def __init__(self, db):
        self.db = db

    def start(
        self,
        *,
        source_mode,
        folder=None,
        db_roots=None,
        file_root=None,
        keep_id3="first",
        limit=None,
        workers=1,
        reasons=None,
        out_dir=None,
        state_path=None,
        apply=False,
        confirmation=None,
    ):
        type(self).last_request = {
            "source_mode": source_mode,
            "folder": folder,
            "db_roots": db_roots,
            "file_root": file_root,
            "keep_id3": keep_id3,
            "limit": limit,
            "workers": workers,
            "reasons": reasons,
            "out_dir": out_dir,
            "state_path": state_path,
            "apply": apply,
            "confirmation": confirmation,
        }
        return _status(self.db.path, type(self).xlsx_path)

    def latest(self):
        return _status(self.db.path, type(self).xlsx_path)

    def get(self, job_id):
        if job_id != "doctor-job-1":
            raise KeyError(job_id)
        return _status(self.db.path, type(self).xlsx_path)

    def cancel(self, job_id):
        payload = self.get(job_id)
        payload["state"] = "cancelled"
        return payload


def _status(db_path: Path, xlsx_path: Path | None = None):
    return {
        "job_id": "doctor-job-1",
        "state": "completed",
        "source_mode": "db",
        "db_path": str(db_path),
        "folder": None,
        "db_roots": ["D:/Music"],
        "file_root": None,
        "keep_id3": "first",
        "limit": 12,
        "workers": 2,
        "reasons": ["OVERSIZED_DATA"],
        "apply": False,
        "total": 8,
        "processed": 8,
        "ok": 4,
        "notice": 1,
        "repairable": 2,
        "repaired": 0,
        "suspicious": 1,
        "tag_error": 0,
        "failed": 0,
        "skipped_state": 0,
        "skipped_reason": 0,
        "missing_db_files": 0,
        "current_path": None,
        "current_step": "Completed",
        "json_path": "E:/Projects/dj-track-similarity/tools/audio-doctor/data/reports/audio_doctor_report.json",
        "xlsx_path": str(xlsx_path) if xlsx_path else None,
        "log_path": "E:/Projects/dj-track-similarity/tools/audio-doctor/data/reports/audio_doctor_report.log",
        "state_path": "E:/Projects/dj-track-similarity/tools/audio-doctor/data/state/state.db.json",
        "started_at": 1,
        "finished_at": 2,
        "avg_seconds_per_item": 0.1,
        "errors": [],
        "events": [],
        "cancel_requested": False,
    }


def test_api_starts_audio_doctor_job_from_selected_database(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api_state, "AudioDoctorJobManager", SynchronousAudioDoctorManager, raising=False)
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/audio-doctor/jobs",
        json={
            "source_mode": "db",
            "db_roots": ["D:/Music"],
            "keep_id3": "last",
            "limit": 12,
            "workers": 2,
            "reasons": ["OVERSIZED_DATA"],
        },
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == "doctor-job-1"
    assert SynchronousAudioDoctorManager.last_request == {
        "source_mode": "db",
        "folder": None,
        "db_roots": ["D:/Music"],
        "file_root": None,
        "keep_id3": "last",
        "limit": 12,
        "workers": 2,
        "reasons": ["OVERSIZED_DATA"],
        "out_dir": None,
        "state_path": None,
        "apply": False,
        "confirmation": None,
    }


def test_api_rejects_audio_doctor_apply_without_exact_confirmation(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api_state, "AudioDoctorJobManager", SynchronousAudioDoctorManager, raising=False)
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/audio-doctor/jobs",
        json={"source_mode": "db", "apply": True, "confirmation": "repair"},
    )

    assert response.status_code == 400
    assert "APPLY REPAIR" in response.json()["detail"]


def test_api_audio_doctor_latest_get_cancel_and_xlsx(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    xlsx_path = tmp_path / "audio_doctor_report.xlsx"
    xlsx_path.write_bytes(b"xlsx")
    LibraryDatabase(db_path)
    SynchronousAudioDoctorManager.xlsx_path = xlsx_path
    monkeypatch.setattr(api_state, "AudioDoctorJobManager", SynchronousAudioDoctorManager, raising=False)
    client = TestClient(api.create_app(db_path))

    latest = client.get("/api/audio-doctor/jobs/latest")
    job = client.get("/api/audio-doctor/jobs/doctor-job-1")
    cancelled = client.post("/api/audio-doctor/jobs/doctor-job-1/cancel")
    report = client.get("/api/audio-doctor/jobs/doctor-job-1/report/xlsx")

    assert latest.status_code == 200
    assert latest.json()["job_id"] == "doctor-job-1"
    assert job.status_code == 200
    assert job.json()["xlsx_path"] == str(xlsx_path)
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert report.status_code == 200
    assert report.content == b"xlsx"
