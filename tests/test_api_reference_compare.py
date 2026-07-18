from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np

import dj_track_similarity.api as api
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_contract import expected_sonara_analysis_signature


def test_reference_compare_returns_separate_model_groups(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db, track_ids = _reference_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/reference/compare",
        json={"seed_track_id": track_ids["seed"], "limit": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["seed_track_id"] == track_ids["seed"]
    assert [group["model"] for group in payload["groups"]] == ["clap", "mert", "muq", "maest", "sonara"]
    groups = {group["model"]: group for group in payload["groups"]}
    assert groups["clap"]["available"] is True
    assert groups["clap"]["results"][0]["track"]["id"] == track_ids["clap_top"]
    assert groups["mert"]["results"][0]["track"]["id"] == track_ids["mert_top"]
    assert groups["muq"]["results"][0]["track"]["id"] == track_ids["muq_top"]
    assert groups["maest"]["results"][0]["track"]["id"] == track_ids["maest_top"]
    assert groups["sonara"]["results"][0]["track"]["id"] == track_ids["sonara_top"]
    assert db.count_evaluation_rows()["search_sessions"] == 0


def test_reference_compare_marks_missing_model_without_error(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _track(db, tmp_path, "seed")
    _embedding(db, seed_id, "mert", [1.0, 0.0, 0.0])
    candidate_id = _track(db, tmp_path, "candidate")
    _embedding(db, candidate_id, "mert", [0.9, 0.1, 0.0])

    response = _client(monkeypatch, db_path).post(
        "/api/reference/compare",
        json={"seed_track_id": seed_id, "models": ["mert", "clap", "sonara"], "limit": 3},
    )

    assert response.status_code == 200
    groups = {group["model"]: group for group in response.json()["groups"]}
    assert groups["mert"]["available"] is True
    assert groups["mert"]["results"][0]["track"]["id"] == candidate_id
    assert groups["clap"]["available"] is False
    assert groups["clap"]["results"] == []
    assert groups["sonara"]["available"] is False
    assert "missing" in groups["sonara"]["reason"]


def test_reference_compare_verdict_persists_pair_feedback(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _track(db, tmp_path, "seed")
    candidate_id = _track(db, tmp_path, "candidate")

    response = _client(monkeypatch, db_path).post(
        "/api/reference/compare/verdict",
        json={
            "seed_track_id": seed_id,
            "candidate_track_id": candidate_id,
            "model": "muq",
            "verdict": "palette",
            "notes": "same pressure and texture",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["seed_track_id"] == seed_id
    assert payload["candidate_track_id"] == candidate_id
    assert payload["model"] == "muq"
    assert payload["verdict"] == "palette"
    assert payload["source"] == "reference_compare:muq"
    feedback = LibraryDatabase(db_path).get_pair_feedback_map()[(seed_id, candidate_id, "reference_compare:muq")]
    assert feedback["rating"] == 2
    assert feedback["reason_tags"] == ["palette"]
    assert feedback["notes"] == "same pressure and texture"


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    return TestClient(create_app(db_path))


def _reference_library(db_path: Path, tmp_path: Path) -> tuple[LibraryDatabase, dict[str, int]]:
    db = LibraryDatabase(db_path)
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "clap_top": _track(db, tmp_path, "clap_top"),
        "mert_top": _track(db, tmp_path, "mert_top"),
        "muq_top": _track(db, tmp_path, "muq_top"),
        "maest_top": _track(db, tmp_path, "maest_top"),
        "sonara_top": _track(db, tmp_path, "sonara_top"),
    }
    _embedding(db, track_ids["seed"], "clap", [1.0, 0.0, 0.0])
    _embedding(db, track_ids["clap_top"], "clap", [0.98, 0.02, 0.0])
    _embedding(db, track_ids["seed"], "mert", [0.0, 1.0, 0.0])
    _embedding(db, track_ids["mert_top"], "mert", [0.02, 0.98, 0.0])
    _embedding(db, track_ids["seed"], "muq", [0.0, 0.0, 1.0])
    _embedding(db, track_ids["muq_top"], "muq", [0.02, 0.0, 0.98])
    _embedding(db, track_ids["seed"], "maest", [0.7, 0.7, 0.0])
    _embedding(db, track_ids["maest_top"], "maest", [0.69, 0.71, 0.0])
    signature = expected_sonara_analysis_signature([])
    db.save_sonara_features(
        track_ids["seed"],
        {"energy": 0.8, "danceability": 0.8},
        energy=0.8,
        analysis_signature=signature,
    )
    db.save_sonara_features(
        track_ids["sonara_top"],
        {"energy": 0.79, "danceability": 0.79},
        energy=0.79,
        analysis_signature=signature,
    )
    return db, track_ids


def _track(db: LibraryDatabase, tmp_path: Path, name: str) -> int:
    return db.upsert_track(path=tmp_path / f"{name}.wav", size=100, mtime=1, metadata={"title": name})


def _embedding(db: LibraryDatabase, track_id: int, embedding_key: str, values: list[float]) -> None:
    db.save_embedding(track_id, np.asarray(values, dtype=np.float32), f"{embedding_key}-test", 3, embedding_key=embedding_key)
