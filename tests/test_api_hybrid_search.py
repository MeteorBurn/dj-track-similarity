from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import numpy as np

import dj_track_similarity.api as api
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase


def test_hybrid_search_endpoint_returns_unified_diagnostics(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db, track_ids = _hybrid_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest"],
            "weights": {"mert": 0.0, "maest": 1.0},
            "per_source": 3,
            "limit": 2,
            "include_diagnostics": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["weights_used"] == {"mert": 0.0, "maest": 1.0}
    assert payload["sources"] == ["mert", "maest"]
    assert payload["results"][0]["track"]["id"] == track_ids["maest_top"]
    assert payload["results"][0]["rank"] == 1
    assert payload["results"][0]["score"] == 1.0
    assert payload["results"][0]["adjusted_score"] == payload["results"][0]["score"]
    assert payload["results"][0]["transition_risk_weight"] == 0.0
    assert payload["results"][0]["transition_risk_penalty"] == 0.0
    assert payload["results"][0]["transition_risk"] is not None
    assert payload["results"][0]["transition_diagnostics"]["supporting_seed_count"] == 1
    assert "maest" in payload["results"][0]["score_breakdown"]
    assert payload["results"][0]["match_character"]["source_count"] >= 1
    assert payload["results"][0]["feedback"] is None
    assert payload["session_id"] is None
    assert "not calibrated confidence" in " ".join(payload["limitations"])
    assert db.count_evaluation_rows()["search_sessions"] == 0


def test_hybrid_search_records_session_events_and_hydrates_feedback(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db, track_ids = _hybrid_library(db_path, tmp_path)
    db.upsert_track_pair_feedback(
        track_ids["seed"],
        track_ids["maest_top"],
        2,
        reason_tags=("good_groove", "good_density"),
        source="hybrid_ui",
    )

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest"],
            "weights": {"mert": 0.0, "maest": 1.0},
            "per_source": 3,
            "limit": 2,
            "record_session": True,
            "include_diagnostics": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["session_id"], int)
    assert payload["results"][0]["track"]["id"] == track_ids["maest_top"]
    assert payload["results"][0]["feedback"]["source"] == "hybrid_ui"
    assert payload["results"][0]["feedback"]["rating"] == 2
    assert payload["results"][0]["feedback"]["reason_tags"] == ["good_groove", "good_density"]
    counts = LibraryDatabase(db_path).count_evaluation_rows()
    assert counts["search_sessions"] == 1
    assert counts["search_result_events"] == len(payload["results"])
    session = LibraryDatabase(db_path).list_search_sessions_with_events()[0]
    assert session["mode"] == "hybrid_search_preview"
    assert session["seed_track_ids"] == [track_ids["seed"]]
    assert session["request"]["feedback_source"] == "hybrid_ui"
    assert session["request"]["record_session"] is True
    first_event_breakdown = session["events"][0]["score_breakdown"]
    assert first_event_breakdown["score_kind"] == "weighted_rrf"
    assert first_event_breakdown["adjusted_score"] == payload["results"][0]["adjusted_score"]
    assert first_event_breakdown["raw_rrf_score"] == payload["results"][0]["raw_rrf_score"]
    assert first_event_breakdown["transition_risk_weight"] == 0.0
    assert first_event_breakdown["sources"]["maest"]["rank"] == 1
    assert "score" in first_event_breakdown["sources"]["maest"]
    assert "confidence" not in first_event_breakdown


def test_hybrid_search_endpoint_rejects_invalid_weights(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _hybrid_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest"],
            "weights": {"mert": 0.0, "maest": 0.0},
        },
    )

    assert response.status_code == 400
    assert "positive" in response.json()["detail"]


def test_hybrid_search_endpoint_rejects_invalid_transition_risk_weight(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _hybrid_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={"seed_track_ids": [track_ids["seed"]], "transition_risk_weight": 1.01},
    )

    assert response.status_code == 422


def test_hybrid_search_endpoint_accepts_clap_as_neutral_missing_source(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _hybrid_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest", "clap"],
            "per_source": 3,
            "limit": 2,
            "include_diagnostics": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources"] == ["mert", "maest", "clap"]
    assert payload["results"]
    assert any("source=clap returned no candidates" in warning for warning in payload["warnings"])
    assert payload["results"][0]["transition_diagnostics"]["components"]["source_disagreement_risk"] == 0.0


def test_hybrid_search_endpoint_does_not_touch_audio_paths(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    audio_path = tmp_path / "not-created.wav"
    db = LibraryDatabase(db_path)
    seed_id = db.upsert_track(path=audio_path, size=0, mtime=1, metadata={"title": "Missing Source"})

    response = _client(monkeypatch, db_path).post(
        "/api/search/hybrid",
        json={"seed_track_ids": [seed_id], "sources": ["mert"], "per_source": 5},
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert not audio_path.exists()
    assert LibraryDatabase(db_path).count_evaluation_rows()["search_sessions"] == 0


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    return TestClient(create_app(db_path))


def _hybrid_library(db_path: Path, tmp_path: Path) -> tuple[LibraryDatabase, dict[str, int]]:
    db = LibraryDatabase(db_path)
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "mert_top": _track(db, tmp_path, "mert_top"),
        "maest_top": _track(db, tmp_path, "maest_top"),
        "shared": _track(db, tmp_path, "shared"),
    }
    _save_embeddings(db, track_ids["seed"], mert=[1.0, 0.0], maest=[0.0, 1.0])
    _save_embeddings(db, track_ids["mert_top"], mert=[0.99, 0.01], maest=[1.0, 0.0])
    _save_embeddings(db, track_ids["maest_top"], mert=[0.0, 1.0], maest=[0.01, 0.99])
    _save_embeddings(db, track_ids["shared"], mert=[0.8, 0.2], maest=[0.2, 0.8])
    return db, track_ids


def _track(db: LibraryDatabase, tmp_path: Path, stem: str) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.replace("_", " ").title()},
    )


def _save_embeddings(db: LibraryDatabase, track_id: int, *, mert: list[float], maest: list[float]) -> None:
    db.save_embedding(track_id, np.asarray(mert, dtype=np.float32), "test-mert", embedding_key="mert")
    db.save_embedding(track_id, np.asarray(maest, dtype=np.float32), "test-maest", embedding_key="maest")
