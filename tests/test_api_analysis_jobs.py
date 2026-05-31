from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.database import LibraryDatabase


class SynchronousAnalysisManager:
    last_request: dict[str, object] = {}

    def __init__(self, db):
        self.db = db

    def start(self, *, models=None, limit=None, device="auto", top_k=3, batch_size=1):
        type(self).last_request = {
            "models": models,
            "limit": limit,
            "device": device,
            "top_k": top_k,
            "batch_size": batch_size,
        }
        return _status(models or ["sonara", "maest", "mert", "clap"], batch_size=batch_size, device=device, top_k=top_k)

    def latest(self):
        return _status(["sonara"])

    def get(self, job_id):
        if job_id != "job-1":
            raise KeyError(job_id)
        return _status(["sonara"])

    def cancel(self, job_id):
        if job_id != "job-1":
            raise KeyError(job_id)
        payload = _status(["sonara"])
        payload["state"] = "cancelled"
        return payload


def _status(models, *, batch_size=4, device="cpu", top_k=3):
    return {
        "job_id": "job-1",
        "state": "completed",
        "adapter_name": "multi",
        "embedding_key": "multi",
        "models": models,
        "current_model": None,
        "model_progress": {
            model: {"total": 1, "processed": 1, "analyzed": 1, "failed": 0, "skipped": 0}
            for model in models
        },
        "model_name": None,
        "device": device,
        "device_requested": device,
        "total": 1,
        "processed": 1,
        "analyzed": 1,
        "failed": 0,
        "skipped": 0,
        "current_path": None,
        "started_at": 1,
        "finished_at": 2,
        "avg_seconds_per_track": 1,
        "errors": [],
        "events": [],
        "cancel_requested": False,
        "workers": batch_size,
        "batch_size": batch_size,
        "top_k": top_k,
    }


def test_api_starts_selected_multi_model_analysis_job(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api, "AnalysisJobManager", SynchronousAnalysisManager)
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/analysis/jobs",
        json={"models": ["maest", "mert"], "limit": 2, "device": "cpu", "top_k": 4, "batch_size": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter_name"] == "multi"
    assert payload["models"] == ["maest", "mert"]
    assert payload["model_progress"]["maest"]["total"] == 1
    assert payload["batch_size"] == 5
    assert SynchronousAnalysisManager.last_request == {
        "models": ["maest", "mert"],
        "limit": 2,
        "device": "cpu",
        "top_k": 4,
        "batch_size": 5,
    }


def test_api_defaults_multi_model_analysis_to_all_models(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api, "AnalysisJobManager", SynchronousAnalysisManager)
    client = TestClient(api.create_app(db_path))

    response = client.post("/api/analysis/jobs", json={})

    assert response.status_code == 200
    assert response.json()["models"] == ["sonara", "maest", "mert", "clap"]
    assert SynchronousAnalysisManager.last_request["models"] == ["sonara", "maest", "mert", "clap"]


def test_old_individual_analysis_start_endpoints_are_removed(tmp_path: Path) -> None:
    client = TestClient(api.create_app(tmp_path / "library.sqlite"))

    assert client.post("/api/analyze", json={"adapter": "mert"}).status_code in {404, 405}
    assert client.post("/api/sonara/analyze", json={}).status_code in {404, 405}
    assert client.post("/api/genres/analyze", json={}).status_code in {404, 405}
