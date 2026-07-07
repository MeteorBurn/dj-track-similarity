from __future__ import annotations

from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
import dj_track_similarity.api_state as api_state
import dj_track_similarity.audio_dedup_jobs as audio_dedup_jobs
from dj_track_similarity.database import LibraryDatabase


class SynchronousAudioDedupManager:
    last_request: dict[str, object] = {}

    def __init__(self, db):
        self.db = db

    def start(
        self,
        *,
        root,
        path_contains=None,
        preset="safe",
        min_score=None,
        min_similarity=None,
        limit_groups=None,
        out_dir=None,
        apply=False,
        confirmation=None,
    ):
        type(self).last_request = {
            "root": root,
            "path_contains": path_contains,
            "preset": preset,
            "min_score": min_score,
            "min_similarity": min_similarity,
            "limit_groups": limit_groups,
            "out_dir": out_dir,
            "apply": apply,
            "confirmation": confirmation,
        }
        return _status()

    def latest(self):
        return _status()

    def get(self, job_id):
        if job_id != "dedup-job-1":
            raise KeyError(job_id)
        return _status()

    def cancel(self, job_id):
        payload = self.get(job_id)
        payload["state"] = "cancelled"
        return payload


def _status():
    return {
        "job_id": "dedup-job-1",
        "state": "completed",
        "root": "D:/Music",
        "path_contains": ["mastered"],
        "preset": "balanced",
        "min_score": 0.95,
        "min_similarity": 0.98,
        "limit_groups": 12,
        "apply": False,
        "total": 8,
        "processed": 8,
        "groups": 2,
        "safe_candidates": 1,
        "deleted": 0,
        "skipped": 0,
        "failed": 0,
        "current_path": None,
        "json_path": "E:/Projects/dj-track-similarity/tools/audio-dedup/data/reports/audio_dedup_report.json",
        "xlsx_path": "E:/Projects/dj-track-similarity/tools/audio-dedup/data/reports/audio_dedup_report.xlsx",
        "log_path": "E:/Projects/dj-track-similarity/tools/audio-dedup/data/reports/audio_dedup_report.log",
        "started_at": 1,
        "finished_at": 2,
        "avg_seconds_per_item": 0.1,
        "errors": [],
        "events": [],
        "cancel_requested": False,
    }


def test_api_starts_audio_dedup_job_from_selected_database(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api_state, "AudioDedupJobManager", SynchronousAudioDedupManager)
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/audio-dedup/jobs",
        json={
            "root": "D:/Music",
            "path_contains": ["mastered"],
            "preset": "balanced",
            "min_score": 0.95,
            "min_similarity": 0.98,
            "limit_groups": 12,
        },
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == "dedup-job-1"
    assert SynchronousAudioDedupManager.last_request == {
        "root": "D:/Music",
        "path_contains": ["mastered"],
        "preset": "balanced",
        "min_score": 0.95,
        "min_similarity": 0.98,
        "limit_groups": 12,
        "out_dir": None,
        "apply": False,
        "confirmation": None,
    }


def test_api_rejects_audio_dedup_apply_without_exact_confirmation(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    SynchronousAudioDedupManager.last_request = {}
    monkeypatch.setattr(api_state, "AudioDedupJobManager", SynchronousAudioDedupManager)
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/audio-dedup/jobs",
        json={"root": "D:/Music", "apply": True, "confirmation": "delete"},
    )

    assert response.status_code == 400
    assert "APPLY DELETE" in response.json()["detail"]
    assert SynchronousAudioDedupManager.last_request == {}


def test_api_accepts_audio_dedup_apply_only_with_exact_confirmation(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    SynchronousAudioDedupManager.last_request = {}
    monkeypatch.setattr(api_state, "AudioDedupJobManager", SynchronousAudioDedupManager)
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/audio-dedup/jobs",
        json={"root": "D:/Music", "apply": True, "confirmation": "APPLY DELETE"},
    )

    assert response.status_code == 200
    assert SynchronousAudioDedupManager.last_request["apply"] is True
    assert SynchronousAudioDedupManager.last_request["confirmation"] == "APPLY DELETE"


def test_audio_dedup_manager_rejects_apply_without_exact_confirmation(tmp_path: Path) -> None:
    manager = audio_dedup_jobs.AudioDedupJobManager(LibraryDatabase(tmp_path / "library.sqlite"))

    try:
        manager.create_job(root=tmp_path, apply=True, confirmation="DELETE")
    except ValueError as error:
        assert str(error) == 'Type exactly "APPLY DELETE" to run apply mode'
    else:  # pragma: no cover - protects the fail-closed contract
        raise AssertionError("Audio Dedup apply must require exact confirmation")


def test_audio_dedup_apply_deletes_only_safe_temp_fixture_candidate(tmp_path: Path) -> None:
    core = audio_dedup_jobs._load_audio_dedup_core()
    audio_dir = tmp_path / "library"
    audio_dir.mkdir()
    keep_path = audio_dir / "keep.wav"
    delete_path = audio_dir / "delete.wav"
    outside_path = tmp_path / "outside.wav"
    keep_path.write_bytes(b"keep")
    delete_path.write_bytes(b"delete")
    outside_path.write_bytes(b"outside")
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    keep_id = db.upsert_track(path=keep_path, size=keep_path.stat().st_size, mtime=1, metadata={"title": "Keep"})
    delete_id = db.upsert_track(path=delete_path, size=delete_path.stat().st_size, mtime=1, metadata={"title": "Delete"})
    outside_id = db.upsert_track(path=outside_path, size=outside_path.stat().st_size, mtime=1, metadata={"title": "Outside"})
    payload = {
        "groups": [
            {
                "candidate_deletes": [
                    {
                        "track_id": delete_id,
                        "path": str(delete_path),
                        "decision": "delete_candidate",
                        "safe_to_delete": "true_candidate",
                    },
                    {
                        "track_id": outside_id,
                        "path": str(outside_path),
                        "decision": "delete_candidate",
                        "safe_to_delete": "true_candidate",
                    },
                    {
                        "track_id": keep_id,
                        "path": str(keep_path),
                        "decision": "review",
                        "safe_to_delete": "false",
                    },
                ]
            }
        ]
    }

    result = core.apply_duplicate_deletions(db_path=db_path, root=audio_dir, payload=payload, rhythm_lab_db=tmp_path / "missing-lab.sqlite")

    assert result.deleted_track_ids == (delete_id,)
    assert result.deleted_paths == (str(delete_path),)
    assert result.skipped == (f"track_id={outside_id}: path outside root",)
    assert result.failed == ()
    assert keep_path.exists()
    assert outside_path.exists()
    assert not delete_path.exists()
    with sqlite3.connect(db_path) as connection:
        remaining_ids = [row[0] for row in connection.execute("SELECT id FROM tracks ORDER BY id")]
    assert remaining_ids == [keep_id, outside_id]
