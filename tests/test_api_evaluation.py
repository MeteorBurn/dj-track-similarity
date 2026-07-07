from __future__ import annotations

from pathlib import Path
import sqlite3

from fastapi.testclient import TestClient
import numpy as np
import pytest

import dj_track_similarity.api as api
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_schema import CURRENT_SCHEMA_VERSION


def test_evaluation_summary_returns_v4_counts(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _track(db, tmp_path, "seed")
    candidate_id = _track(db, tmp_path, "candidate")
    session_id = db.create_search_session("evaluation_candidate_pool", [seed_id], {"feedback_source": "manual"})
    db.record_search_result_event(session_id, candidate_id, rank=1, total_score=0.9, score_breakdown={"sources": {"mert": {"rank": 1}}})
    db.upsert_track_pair_feedback(seed_id, candidate_id, 3, reason_tags=("strong",), source="manual")
    db.add_transition_feedback(seed_id, candidate_id, 2, risk_tags=("energy",), source="manual")
    db.record_calibration_run("manual_feedback", "evaluation_candidate_pool", {"k": [5]}, {"status": "ok"})

    response = _client(monkeypatch, db_path).get("/api/evaluation/summary")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": CURRENT_SCHEMA_VERSION,
        "counts": {
            "search_sessions": 1,
            "search_result_events": 1,
            "track_pair_feedback": 1,
            "transition_feedback": 1,
            "calibration_runs": 1,
        },
    }


def test_pair_feedback_endpoint_upserts_and_validates_rating(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _track(db, tmp_path, "seed")
    second_seed_id = _track(db, tmp_path, "seed_two")
    candidate_id = _track(db, tmp_path, "candidate")
    client = _client(monkeypatch, db_path)

    first = client.post(
        "/api/evaluation/feedback/pair",
        json={
            "session_id": None,
            "seed_track_ids": [seed_id, second_seed_id],
            "candidate_track_id": candidate_id,
            "rating": 1,
            "reason_tags": ["interesting_adjacent"],
            "notes": "initial audit",
            "source": "hybrid_ui",
        },
    )
    second = client.post(
        "/api/evaluation/feedback/pair",
        json={
            "seed_track_ids": [seed_id, second_seed_id],
            "candidate_track_id": candidate_id,
            "rating": 3,
            "reason_tags": ["good_groove"],
            "source": "hybrid_ui",
        },
    )
    invalid = client.post(
        "/api/evaluation/feedback/pair",
        json={"seed_track_ids": [seed_id], "candidate_track_id": candidate_id, "rating": 4},
    )
    invalid_reason = client.post(
        "/api/evaluation/feedback/pair",
        json={"seed_track_ids": [seed_id], "candidate_track_id": candidate_id, "rating": 2, "reason_tags": ["rough"]},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["ids"] == second.json()["ids"]
    assert second.json()["seed_track_ids"] == [seed_id, second_seed_id]
    assert second.json()["source"] == "hybrid_ui"
    assert invalid.status_code == 422
    assert invalid_reason.status_code == 422
    feedback_map = LibraryDatabase(db_path).get_pair_feedback_map()
    assert LibraryDatabase(db_path).count_evaluation_rows()["track_pair_feedback"] == 2
    feedback = feedback_map[(seed_id, candidate_id, "hybrid_ui")]
    second_seed_feedback = feedback_map[(second_seed_id, candidate_id, "hybrid_ui")]
    assert feedback["rating"] == 3
    assert feedback["reason_tags"] == ["good_groove"]
    assert second_seed_feedback["rating"] == 3


def test_transition_feedback_endpoint_appends_manual_audit_row(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    outgoing_id = _track(db, tmp_path, "outgoing")
    incoming_id = _track(db, tmp_path, "incoming")

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/feedback/transition",
        json={
            "outgoing_track_id": outgoing_id,
            "incoming_track_id": incoming_id,
            "rating": 2,
            "risk_tags": ["energy"],
            "notes": "usable but risky",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["rating"] == 2
    assert payload["source"] == "manual"
    assert LibraryDatabase(db_path).count_evaluation_rows()["transition_feedback"] == 1


def test_pair_feedback_endpoint_rejects_duplicate_seed_ids(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _track(db, tmp_path, "seed")
    candidate_id = _track(db, tmp_path, "candidate")

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/feedback/pair",
        json={"seed_track_ids": [seed_id, seed_id], "candidate_track_id": candidate_id, "rating": 2},
    )

    assert response.status_code == 422
    assert "seed_track_ids must be unique" in response.text


def test_source_profile_endpoint_returns_internal_weights_without_labels(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _profile_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/run/source-profile",
        json={
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest"],
            "per_source": 2,
            "top_k": [1, 2],
            "profile_name": "api-test-profile",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    weights = payload["source_profile"]["recommended_weights"]["weights"]
    score_profile = payload["score_profile"]
    assert payload["source_profile"]["weight_kind"] == "unsupervised_internal_profile"
    assert sum(weights.values()) == pytest.approx(1.0)
    assert score_profile["name"] == "api-test-profile"
    assert score_profile["weight_kind"] == "unsupervised_internal_profile"
    assert LibraryDatabase(db_path).count_evaluation_rows()["track_pair_feedback"] == 0


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("sample_count", 201),
        ("per_source", 101),
    ),
)
def test_source_profile_endpoint_rejects_expensive_counts(monkeypatch, tmp_path: Path, field_name: str, value: int) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    request = {field_name: value}

    response = _client(monkeypatch, db_path).post("/api/evaluation/run/source-profile", json=request)

    assert response.status_code == 422


def test_source_profile_endpoint_rejects_too_many_seed_ids(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/run/source-profile",
        json={"seed_track_ids": list(range(1, 202))},
    )

    assert response.status_code == 422


def test_source_profile_endpoint_rejects_unsupported_source(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/run/source-profile",
        json={"sources": ["mert", "bogus"]},
    )

    assert response.status_code == 422
    assert "mert" in response.text
    assert "maest" in response.text
    assert "sonara" in response.text
    assert "clap" in response.text


def test_source_profile_endpoint_accepts_clap_without_coverage(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _profile_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/run/source-profile",
        json={
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest", "clap"],
            "per_source": 2,
        },
    )

    assert response.status_code == 200
    source_profile = response.json()["source_profile"]
    assert source_profile["recommended_weights"]["weights"]["clap"] == 0.0
    assert any("source=clap has no coverage" in warning for warning in source_profile["warnings"])


def test_apply_score_profile_endpoint_reports_insufficient_labels(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _track(db, tmp_path, "seed")
    candidate_id = _track(db, tmp_path, "candidate")
    session_id = db.create_search_session("evaluation_candidate_pool", [seed_id], {"feedback_source": "manual"})
    db.record_search_result_event(
        session_id,
        candidate_id,
        rank=1,
        total_score=0.0,
        score_breakdown={"sources": {"mert": {"rank": 1, "score": 0.9}}},
    )

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/run/apply-score-profile",
        json={"name": "inline", "weights": {"mert": 1.0}, "k": [5, 10], "rrf_k": 60},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["label_status"] == "insufficient_data"
    assert payload["ranked_session_count"] == 1
    assert payload["judged_results"] == 0
    assert payload["weights"] == {"mert": 1.0}


def test_weighted_candidates_endpoint_returns_capped_preview_without_recording(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _profile_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/run/weighted-candidates",
        json={
            "name": "inline-weighted",
            "weights": {"mert": 1.0},
            "seed_track_ids": [track_ids["seed"]],
            "per_source": 2,
            "limit_per_seed": 1,
            "random_seed": 123,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["score_profile"]["name"] == "inline-weighted"
    assert payload["rows_total"] == 2
    assert payload["rows_returned"] == 1
    assert payload["rows"][0]["profile_rank"] == 1
    assert payload["transition_risk_weight"] == 0.0
    assert payload["rows"][0]["transition_risk_weight"] == 0.0
    assert payload["rows"][0]["transition_risk_penalty"] == 0.0
    assert "adjusted_score" in payload["rows"][0]
    assert "raw_rrf_score" in payload["rows"][0]
    assert payload["rows"][0]["candidate_track_id"] != track_ids["seed"]
    assert payload["session_ids"] == []
    assert LibraryDatabase(db_path).count_evaluation_rows()["search_sessions"] == 0


def test_weighted_candidates_endpoint_rejects_sources_missing_from_profile(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _profile_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/run/weighted-candidates",
        json={
            "name": "inline-weighted",
            "weights": {"mert": 1.0},
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "maest"],
            "per_source": 2,
        },
    )

    assert response.status_code == 400
    assert "no score profile weight" in response.json()["detail"]


def test_weighted_candidates_endpoint_missing_clap_is_neutral_for_risk(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _, track_ids = _profile_library(db_path, tmp_path)

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/run/weighted-candidates",
        json={
            "name": "inline-weighted",
            "weights": {"mert": 1.0, "clap": 0.0},
            "seed_track_ids": [track_ids["seed"]],
            "sources": ["mert", "clap"],
            "per_source": 2,
            "transition_risk_weight": 1.0,
            "limit_per_seed": 1,
        },
    )

    assert response.status_code == 200
    row = response.json()["rows"][0]
    assert row["source_count"] == 1
    assert row["transition_risk"] == 0.0
    assert row["transition_risk_penalty"] == 0.0


def test_latest_evaluation_reports_endpoint_returns_empty_report_contract(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)

    response = _client(monkeypatch, db_path).get("/api/evaluation/reports/latest")

    assert response.status_code == 200
    assert response.json() == {
        "status": "no_persisted_reports",
        "summary": "No persisted evaluation reports were found. CLI JSON report directories are not scanned by the API.",
        "calibration_runs": [],
    }


def test_weighted_candidates_endpoint_rejects_ambiguous_profile_inputs(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/run/weighted-candidates",
        json={"profile": {"name": "inline"}, "weights": {"mert": 1.0}},
    )

    assert response.status_code == 422
    assert "Provide exactly one of profile or weights" in response.text


def test_evaluation_endpoints_report_unselected_or_old_schema_clearly(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    unselected = TestClient(create_app()).get("/api/evaluation/summary")
    old_db_path = tmp_path / "old.sqlite"
    _old_schema_database(old_db_path)
    old_schema = TestClient(create_app()).post("/api/database/switch", json={"path": str(old_db_path)})

    assert unselected.status_code == 400
    assert unselected.json()["detail"] == "Database is not selected"
    assert old_schema.status_code == 409
    assert "SQLite database schema is not current" in old_schema.json()["detail"]


def test_evaluation_api_does_not_touch_audio_paths(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    audio_path = tmp_path / "not-created.wav"
    db = LibraryDatabase(db_path)
    seed_id = db.upsert_track(path=audio_path, size=0, mtime=1, metadata={"title": "Missing Source"})
    candidate_id = _track(db, tmp_path, "candidate")

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/feedback/pair",
        json={"seed_track_ids": [seed_id], "candidate_track_id": candidate_id, "rating": 2},
    )

    assert response.status_code == 200
    assert not audio_path.exists()


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    return TestClient(create_app(db_path))


def _track(db: LibraryDatabase, tmp_path: Path, stem: str) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.replace("_", " ").title()},
        bpm=120.0,
        musical_key="1A",
        energy=0.5,
    )


def _profile_library(db_path: Path, tmp_path: Path) -> tuple[LibraryDatabase, dict[str, int]]:
    db = LibraryDatabase(db_path)
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "shared": _track(db, tmp_path, "shared"),
        "mert_only": _track(db, tmp_path, "mert_only"),
        "maest_only": _track(db, tmp_path, "maest_only"),
    }
    _save_embeddings(db, track_ids["seed"], mert=[1.0, 0.0], maest=[0.0, 1.0])
    _save_embeddings(db, track_ids["shared"], mert=[0.99, 0.1], maest=[0.1, 0.99])
    _save_embeddings(db, track_ids["mert_only"], mert=[0.8, 0.2], maest=[1.0, 0.0])
    _save_embeddings(db, track_ids["maest_only"], mert=[0.0, 1.0], maest=[0.2, 0.8])
    return db, track_ids


def _save_embeddings(db: LibraryDatabase, track_id: int, *, mert: list[float], maest: list[float]) -> None:
    db.save_embedding(track_id, np.asarray(mert, dtype=np.float32), "test-mert", embedding_key="mert")
    db.save_embedding(track_id, np.asarray(maest, dtype=np.float32), "test-maest", embedding_key="maest")


def _old_schema_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 3")
        connection.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, path TEXT NOT NULL)")
        connection.execute("CREATE TABLE embeddings (track_id INTEGER NOT NULL, embedding_key TEXT NOT NULL)")
