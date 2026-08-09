from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
import dj_track_similarity.api_state as api_state
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
        sources=None,
        weights=None,
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
            "sources": sources,
            "weights": weights,
            "preset": preset,
            "min_score": min_score,
            "min_similarity": min_similarity,
            "limit_groups": limit_groups,
            "out_dir": out_dir,
            "apply": apply,
            "confirmation": confirmation,
        }
        return _status(sources=sources, weights=weights)

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


def _status(
    *,
    sources=None,
    weights=None,
):
    return {
        "job_id": "dedup-job-1",
        "state": "completed",
        "root": "D:/Music",
        "path_contains": ["mastered"],
        "sources": sources or ["mert", "maest", "muq", "clap"],
        "weights": weights or {
            "mert": 0.43,
            "maest": 0.32,
            "muq": 0.12,
            "clap": 0.04,
        },
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
        "json_path": "C:/projects/dj-track-similarity/tools/audio-dedup/data/reports/audio_dedup_report.json",
        "xlsx_path": "C:/projects/dj-track-similarity/tools/audio-dedup/data/reports/audio_dedup_report.xlsx",
        "log_path": "C:/projects/dj-track-similarity/tools/audio-dedup/data/reports/audio_dedup_report.log",
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
            "sources": ["mert", "maest", "clap"],
            "weights": {
                "mert": 0.43,
                "maest": 0.32,
                "clap": 0.04,
            },
            "preset": "balanced",
            "min_score": 0.95,
            "min_similarity": 0.98,
            "limit_groups": 12,
        },
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == "dedup-job-1"
    assert response.json()["sources"] == ["mert", "maest", "clap"]
    assert response.json()["weights"] == {
        "mert": 0.43,
        "maest": 0.32,
        "clap": 0.04,
    }
    assert SynchronousAudioDedupManager.last_request == {
        "root": "D:/Music",
        "path_contains": ["mastered"],
        "sources": ["mert", "maest", "clap"],
        "weights": {
            "mert": 0.43,
            "maest": 0.32,
            "clap": 0.04,
        },
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
