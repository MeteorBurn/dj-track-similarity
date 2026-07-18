from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.api_schemas import SetBuilderGenerateRequest
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.set_builder import SetBuilderConfig
from dj_track_similarity.sonara_contract import expected_sonara_analysis_signature


def test_set_builder_endpoint_generates_ordered_preview(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    monkeypatch.setattr(api, "promoted_classifiers", lambda: [{"classifier_key": "break_energy", "name": "Break Energy"}])
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _complete_track(db, tmp_path, "seed.wav", [1, 0])
    candidate_id = _complete_track(db, tmp_path, "candidate.wav", [0.99, 0.01])
    db.save_classifier_score(
        candidate_id,
        classifier="break_energy",
        score=0.91,
        label="high",
        confidence=0.91,
        probabilities={"broken": 0.91, "straight": 0.09},
        feature_set="combined",
        model_id="model.joblib",
    )

    response = TestClient(create_app(db_path)).post(
        "/api/set-builder/generate",
        json={
            "seed_mode": "manual",
            "seed_track_ids": [seed_id],
            "limit": 2,
            "classifier_preferences": {"break_energy": 0.8},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["seed_track_ids"] == [seed_id]
    assert [item["track"]["id"] for item in payload["items"]] == [seed_id, candidate_id]
    assert [item["position"] for item in payload["items"]] == [1, 2]
    assert payload["items"][1]["classifier_scores"]["break_energy"] == 0.91
    assert payload["items"][1]["score_breakdown"]["classifier_preference"] > 0
    assert payload["coverage"]["eligible_tracks"] == 2


def test_set_builder_api_defaults_match_backend_config() -> None:
    request = SetBuilderGenerateRequest()
    config = SetBuilderConfig()

    assert request.seed_mode == config.seed_mode == "manual"
    assert request.seed_track_ids == config.seed_track_ids == []
    assert request.auto_seed_count == config.auto_seed_count == 5
    assert request.mode == config.mode == "balanced_set"
    assert request.limit == config.limit == 24
    assert request.diversity == config.diversity == 0.35
    assert request.energy_curve == config.energy_curve == "balanced"
    assert request.bpm_mode == config.bpm_mode == "general"
    assert request.bpm_change == config.bpm_change == "medium"
    assert request.bpm_start == config.bpm_start is None
    assert request.bpm_target == config.bpm_target is None
    assert request.classifier_preferences == config.classifier_preferences == {}
    assert request.classifier_flows == config.classifier_flows == {}


def test_set_builder_endpoint_rejects_invalid_manual_seed_count(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/set-builder/generate", json={"seed_mode": "manual", "seed_track_ids": []})

    assert response.status_code == 400
    assert "1-5 seed tracks" in response.json()["detail"]


def test_set_builder_endpoint_rejects_unknown_classifier(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    monkeypatch.setattr(api, "promoted_classifiers", lambda: [])
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _complete_track(db, tmp_path, "seed.wav", [1, 0])

    response = TestClient(create_app(db_path)).post(
        "/api/set-builder/generate",
        json={"seed_mode": "manual", "seed_track_ids": [seed_id], "classifier_preferences": {"missing": 0.7}},
    )

    assert response.status_code == 400
    assert "Unknown classifier" in response.json()["detail"]


def test_set_builder_endpoint_rejects_incompatible_classifier_manifest(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    monkeypatch.setattr(
        api,
        "promoted_classifiers",
        lambda: [{"classifier_key": "draft_profile", "name": "Draft", "is_scoring_compatible": False}],
    )
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _complete_track(db, tmp_path, "seed.wav", [1, 0])

    response = TestClient(create_app(db_path)).post(
        "/api/set-builder/generate",
        json={"seed_mode": "manual", "seed_track_ids": [seed_id], "classifier_flows": {"draft_profile": "rise"}},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Classifier manifest is invalid: draft_profile"}


def test_set_builder_endpoint_rejects_extra_fields(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/set-builder/generate", json={"seed_mode": "auto", "unexpected": True})

    assert response.status_code == 422


def test_set_builder_endpoint_auto_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    for index in range(4):
        _complete_track(db, tmp_path, f"track-{index}.wav", [1, index / 10])

    response = TestClient(create_app(db_path)).post(
        "/api/set-builder/generate",
        json={"seed_mode": "auto", "auto_seed_count": 3, "limit": 4},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["seed_mode"] == "auto"
    assert len(payload["seed_track_ids"]) == 3
    assert len(payload["items"]) == 4


def test_set_builder_endpoint_accepts_single_random_auto_anchor(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    for index in range(4):
        _complete_track(db, tmp_path, f"track-{index}.wav", [1, index / 10])

    response = TestClient(create_app(db_path)).post(
        "/api/set-builder/generate",
        json={"seed_mode": "auto", "auto_seed_count": 1, "limit": 4, "random_seed": 42},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["seed_track_ids"]) == 1
    assert len(payload["items"]) == 4


def test_set_builder_endpoint_accepts_bpm_trajectory_controls(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _complete_track(db, tmp_path, "seed.wav", [1, 0])
    for index in range(3):
        _complete_track(db, tmp_path, f"candidate-{index}.wav", [1, index / 10])

    response = TestClient(create_app(db_path)).post(
        "/api/set-builder/generate",
        json={
            "seed_mode": "manual",
            "seed_track_ids": [seed_id],
            "limit": 4,
            "bpm_mode": "low_to_high",
            "bpm_change": "slow",
            "bpm_start": 90,
            "bpm_target": 150,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["seed_track_ids"] == [seed_id]
    assert len(payload["items"]) == 4


def test_set_builder_endpoint_reports_missing_seed_features(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _track(db, tmp_path, "seed.wav")

    response = TestClient(create_app(db_path)).post(
        "/api/set-builder/generate",
        json={"seed_mode": "manual", "seed_track_ids": [seed_id]},
    )

    assert response.status_code == 400
    assert "missing required analysis" in response.json()["detail"]


def _track(db: LibraryDatabase, tmp_path: Path, filename: str) -> int:
    path = tmp_path / filename
    path.write_bytes(b"audio")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1.0, metadata={"title": filename, "bpm": 128, "key": "8A"})


def _complete_track(db: LibraryDatabase, tmp_path: Path, filename: str, vector: list[float]) -> int:
    track_id = _track(db, tmp_path, filename)
    db.save_sonara_features(
        track_id,
        {
            "bpm": {"type": "float", "value": 128.0},
            "energy": {"type": "float", "value": 0.6},
            "danceability": {"type": "float", "value": 0.7},
            "onset_density": {"type": "float", "value": 0.4},
            "spectral_centroid_mean": {"type": "float", "value": 1500.0},
            "mfcc_mean": {"type": "ndarray", "value": None, "summary": {"min": 0.1, "max": 0.3, "mean": 0.2, "std": 0.04}},
            "chroma_mean": {"type": "ndarray", "value": None, "summary": {"min": 0.2, "max": 0.4, "mean": 0.3, "std": 0.05}},
        },
        bpm=128,
        musical_key="8A",
        energy=0.6,
        duration=360,
        model_name="sonara-test",
        analysis_signature=expected_sonara_analysis_signature([]),
    )
    for key in ("mert", "maest", "clap"):
        db.save_embedding(track_id, np.asarray(vector, dtype=np.float32), f"{key}-test", embedding_key=key)
    return track_id
