from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
import dj_track_similarity.api_state as api_state
from dj_track_similarity.analysis_config import DEFAULT_SONARA_FEATURE_FAMILIES
from dj_track_similarity.database import LibraryDatabase


class SynchronousAnalysisManager:
    last_request: dict[str, object] = {}

    def __init__(self, db):
        self.db = db

    def start(
        self,
        *,
        models=None,
        limit=None,
        device="auto",
        top_k=3,
        track_batch_size=4,
        inference_batch_size=24,
        classifier_keys=None,
        sonara_features=None,
    ):
        type(self).last_request = {
            "models": models,
            "limit": limit,
            "device": device,
            "top_k": top_k,
            "track_batch_size": track_batch_size,
            "inference_batch_size": inference_batch_size,
            "classifier_keys": classifier_keys,
            "sonara_features": sonara_features,
        }
        return _status(
            models or ["maest", "mert", "muq", "clap"],
            track_batch_size=track_batch_size,
            inference_batch_size=inference_batch_size,
            device=device,
            top_k=top_k,
            classifier_keys=classifier_keys,
        )

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


def _status(models, *, track_batch_size=4, inference_batch_size=24, device="cpu", top_k=3, classifier_keys=None):
    return {
        "job_id": "job-1",
        "state": "completed",
        "adapter_name": "multi",
        "embedding_key": "multi",
        "models": models,
        "classifier_keys": classifier_keys or [],
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
        "workers": track_batch_size,
        "track_batch_size": track_batch_size,
        "inference_batch_size": inference_batch_size,
        "top_k": top_k,
    }


def test_api_starts_selected_multi_model_analysis_job(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api_state, "AnalysisJobManager", SynchronousAnalysisManager)
    monkeypatch.setattr(
        api,
        "promoted_classifiers",
        lambda: [{"classifier_key": "break_energy", "name": "Break Energy"}],
    )
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/analysis/jobs",
        json={
            "models": ["maest", "mert"],
            "limit": 2,
            "device": "cpu",
            "top_k": 4,
            "track_batch_size": 5,
            "inference_batch_size": 18,
            "classifier_keys": ["break_energy"],
            "sonara_features": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["adapter_name"] == "multi"
    assert payload["models"] == ["maest", "mert"]
    assert payload["classifier_keys"] == ["break_energy"]
    assert payload["model_progress"]["maest"]["total"] == 1
    assert "batch_size" not in payload
    assert payload["track_batch_size"] == 5
    assert payload["inference_batch_size"] == 18
    assert SynchronousAnalysisManager.last_request == {
        "models": ["maest", "mert"],
        "limit": 2,
        "device": "cpu",
        "top_k": 4,
        "track_batch_size": 5,
        "inference_batch_size": 18,
        "classifier_keys": ["break_energy"],
        "sonara_features": [],
    }


def test_api_allows_classifier_only_unified_analysis_job(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api_state, "AnalysisJobManager", SynchronousAnalysisManager)
    monkeypatch.setattr(
        api,
        "promoted_classifiers",
        lambda: [{"classifier_key": "break_energy", "name": "Break Energy"}],
    )
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/analysis/jobs",
        json={"models": [], "classifier_keys": ["break_energy"]},
    )

    assert response.status_code == 200
    assert SynchronousAnalysisManager.last_request["models"] == []
    assert SynchronousAnalysisManager.last_request["classifier_keys"] == ["break_energy"]
    assert SynchronousAnalysisManager.last_request["sonara_features"] == []


def test_api_rejects_classifier_analysis_when_required_inputs_are_missing(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track = tmp_path / "missing-inputs.wav"
    track.write_bytes(b"RIFF0000WAVE")
    db.upsert_track(path=track, size=track.stat().st_size, mtime=track.stat().st_mtime, metadata={"title": "missing"})
    monkeypatch.setattr(
        api,
        "promoted_classifiers",
        lambda: [{"classifier_key": "break_energy", "name": "Break Energy"}],
    )
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/analysis/jobs",
        json={"models": [], "classifier_keys": ["break_energy"]},
    )

    assert response.status_code == 400
    assert "SONARA, MAEST, and MERT" in response.json()["detail"]


def test_api_defaults_analysis_to_ml_models_only(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api_state, "AnalysisJobManager", SynchronousAnalysisManager)
    client = TestClient(api.create_app(db_path))

    response = client.post("/api/analysis/jobs", json={})

    assert response.status_code == 200
    assert response.json()["models"] == ["maest", "mert", "muq", "clap"]
    assert SynchronousAnalysisManager.last_request["models"] == ["maest", "mert", "muq", "clap"]
    assert SynchronousAnalysisManager.last_request["track_batch_size"] == 4
    assert SynchronousAnalysisManager.last_request["inference_batch_size"] == 24
    assert SynchronousAnalysisManager.last_request["classifier_keys"] == []
    assert SynchronousAnalysisManager.last_request["sonara_features"] == []


def test_api_exposes_analysis_job_lookup_latest_and_cancel_contract(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api_state, "AnalysisJobManager", SynchronousAnalysisManager)
    client = TestClient(api.create_app(db_path))

    latest = client.get("/api/analysis/jobs/latest")
    fetched = client.get("/api/analysis/jobs/job-1")
    cancelled = client.post("/api/analysis/jobs/job-1/cancel", json={})
    missing = client.get("/api/analysis/jobs/missing-job")

    assert latest.status_code == 200
    assert latest.json()["job_id"] == "job-1"
    assert fetched.status_code == 200
    assert fetched.json()["models"] == ["sonara"]
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert missing.status_code == 404
    assert "missing-job" in missing.json()["detail"]


def test_api_rejects_unknown_analysis_classifier_key(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api_state, "AnalysisJobManager", SynchronousAnalysisManager)
    monkeypatch.setattr(api, "promoted_classifiers", lambda: [])
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/analysis/jobs",
        json={"models": ["sonara"], "classifier_keys": ["missing_profile"]},
    )

    assert response.status_code == 400
    assert "missing_profile" in response.json()["detail"]


def test_api_rejects_invalid_manifest_classifier_key_for_unified_analysis(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(api_state, "AnalysisJobManager", SynchronousAnalysisManager)
    monkeypatch.setattr(
        api,
        "promoted_classifiers",
        lambda: [
            {
                "classifier_key": "break_energy",
                "is_scoring_compatible": False,
                "manifest_errors": ["model.json positive_label is required"],
            }
        ],
    )
    client = TestClient(api.create_app(db_path))

    response = client.post(
        "/api/analysis/jobs",
        json={"models": [], "classifier_keys": ["break_energy"]},
    )

    assert response.status_code == 400
    assert "positive_label" in response.json()["detail"]


def test_real_analysis_job_status_does_not_emit_legacy_batch_size(tmp_path: Path) -> None:
    client = TestClient(api.create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/analysis/jobs", json={"models": ["mert"], "limit": 0})

    assert response.status_code == 200
    payload = response.json()
    assert "batch_size" not in payload
    assert payload["track_batch_size"] == 4
    assert payload["inference_batch_size"] == 24


def test_api_rejects_legacy_analysis_batch_size(tmp_path: Path) -> None:
    client = TestClient(api.create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/analysis/jobs", json={"models": ["mert"], "batch_size": 4})

    assert response.status_code == 422


def test_api_rejects_unknown_analysis_device(tmp_path: Path) -> None:
    client = TestClient(api.create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/analysis/jobs", json={"models": ["mert"], "device": "gpu"})

    assert response.status_code == 422


def test_old_individual_analysis_start_endpoints_are_removed(tmp_path: Path) -> None:
    client = TestClient(api.create_app(tmp_path / "library.sqlite"))

    assert client.post("/api/analyze", json={"adapter": "mert"}).status_code in {404, 405}
    assert client.post("/api/sonara/analyze", json={}).status_code in {404, 405}
    assert client.post("/api/genres/analyze", json={}).status_code in {404, 405}
