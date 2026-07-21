from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.database import LibraryDatabase


def _client(tmp_path: Path) -> TestClient:
    return TestClient(api.create_app(tmp_path / "library.sqlite"))


def test_api_starts_selected_ml_job_without_classifier_fields(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/analysis/jobs",
        json={
            "models": ["maest", "mert"],
            "limit": 0,
            "device": "cpu",
            "top_k": 4,
            "track_batch_size": 5,
            "inference_batch_size": 18,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["models"] == ["maest", "mert"]
    assert "classifier_keys" not in payload
    assert payload["track_batch_size"] == 5
    assert payload["inference_batch_size"] == 18


def test_api_rejects_classifier_scoring_inside_audio_job(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/analysis/jobs",
        json={"models": ["mert"], "classifier_keys": ["break_energy"]},
    )
    assert response.status_code == 422


def test_api_defaults_sonara_to_core_and_native_batch_64(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/analysis/jobs",
        json={"models": ["sonara"], "limit": 0},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sonara_outputs"] == ["core"]
    assert payload["sonara_batch_size"] == 64


def test_api_passes_explicit_sonara_outputs_and_batch_size(tmp_path: Path) -> None:
    response = _client(tmp_path).post(
        "/api/analysis/jobs",
        json={
            "models": ["sonara"],
            "limit": 0,
            "sonara_outputs": ["timeline", "representations"],
            "sonara_batch_size": 17,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["sonara_outputs"] == ["timeline", "representations"]
    assert payload["sonara_batch_size"] == 17


def test_api_defaults_audio_job_to_ml_models_only(tmp_path: Path) -> None:
    response = _client(tmp_path).post("/api/analysis/jobs", json={"limit": 0})
    assert response.status_code == 200
    assert response.json()["models"] == ["maest", "mert", "muq", "clap"]


def test_api_exposes_analysis_job_lookup_latest_and_cancel(tmp_path: Path) -> None:
    client = _client(tmp_path)
    started = client.post("/api/analysis/jobs", json={"models": ["mert"], "limit": 0}).json()
    job_id = started["job_id"]

    assert client.get("/api/analysis/jobs/latest").status_code == 200
    assert client.get(f"/api/analysis/jobs/{job_id}").status_code == 200
    assert client.post(f"/api/analysis/jobs/{job_id}/cancel").status_code == 200
    assert client.get("/api/analysis/jobs/missing-job").status_code == 404


def test_api_aggregate_classifiers_empty_selection_requires_compatible_artifact(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "promoted_classifiers", lambda: [])
    response = _client(tmp_path).post("/api/classifiers/analyze", json={"classifier_keys": [], "limit": 0})
    assert response.status_code == 400
    assert "scoring-compatible" in response.json()["detail"]


def test_api_rejects_incompatible_classifier_with_manifest_reason(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        api,
        "promoted_classifiers",
        lambda: [{
            "classifier_key": "break_energy",
            "is_scoring_compatible": False,
            "manifest_errors": ["SONARA signature is stale"],
        }],
    )
    response = _client(tmp_path).post(
        "/api/classifiers/analyze",
        json={"classifier_keys": ["break_energy"], "limit": 0},
    )
    assert response.status_code == 400
    assert "SONARA signature is stale" in response.json()["detail"]


def test_api_pipeline_preserves_fixed_stage_order(tmp_path: Path) -> None:
    client = _client(tmp_path)
    response = client.post(
        "/api/analysis/pipelines",
        json={
            "stages": ["classifiers", "ml"],
            "limit": 0,
            "ml": {"models": ["mert"], "device": "cpu", "top_k": 3, "track_batch_size": 2, "inference_batch_size": 4},
            "classifiers": {"classifier_keys": ["live_instrumentation"]},
        },
    )
    assert response.status_code == 200
    assert response.json()["order"] == ["ml", "classifiers"]


def test_api_sonara_preflight_blocks_old_contract_until_reset(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    path = tmp_path / "old.wav"
    path.write_bytes(b"RIFF0000WAVE")
    track_id = db.upsert_track(path=path, size=path.stat().st_size, mtime=1, metadata={})
    db.save_sonara_features(
        track_id,
        {"bpm": {"value": 128.0}},
        analysis_signature={
            "sonara_version": "0.2.9", "schema_version": 4, "mode": "playlist",
            "sample_rate": 22050, "bpm_range": [70, 180], "requested_features": [],
            "project_feature_revision": 3, "signature_id": "old",
        },
    )
    client = TestClient(api.create_app(db_path))

    blocked = client.post("/api/analysis/jobs", json={"models": ["sonara"], "limit": 0})
    assert blocked.status_code == 409
    assert "Back up the database" in blocked.json()["detail"]
    assert client.post("/api/analysis/reset", json={"adapter": "sonara"}).status_code == 200
    assert client.post("/api/analysis/jobs", json={"models": ["sonara"], "limit": 0}).status_code == 200


def test_api_rejects_legacy_batch_size_and_unknown_device(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.post("/api/analysis/jobs", json={"models": ["mert"], "batch_size": 4}).status_code == 422
    assert client.post("/api/analysis/jobs", json={"models": ["mert"], "device": "gpu"}).status_code == 422
