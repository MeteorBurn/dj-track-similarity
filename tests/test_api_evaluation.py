from __future__ import annotations

from pathlib import Path
import sqlite3

import numpy as np
from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
)
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_schema_v7 import SCHEMA_VERSION
from dj_track_similarity.track_models import FileTags, ScannedFile


def test_evaluation_summary_keeps_feedback_in_core_and_sessions_in_sidecar(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    seed = _track(database, tmp_path / "seed.wav")
    candidate = _track(database, tmp_path / "candidate.wav")
    session_id = database.create_search_session(
        "evaluation_candidate_pool",
        (seed.track_id,),
        {"catalog_uuid": database.catalog_uuid},
    )
    database.record_search_result_event(
        session_id,
        candidate.track_id,
        rank=1,
        total_score=0.9,
        score_breakdown={"sources": {"mert": {"rank": 1}}},
    )
    database.upsert_track_pair_feedback(
        seed.track_id,
        candidate.track_id,
        3,
        reason_tags=("strong",),
    )
    database.add_transition_feedback(
        seed.track_id,
        candidate.track_id,
        2,
        risk_tags=("energy",),
    )

    response = _client(monkeypatch, db_path).get("/api/evaluation/summary")

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": SCHEMA_VERSION,
        "counts": {
            "pair_feedback": 1,
            "transition_feedback": 1,
            "search_sessions": 1,
            "search_session_seeds": 1,
            "search_result_events": 1,
            "calibration_runs": 0,
        },
    }
    assert database.evaluation_path.is_file()


def test_evaluation_feedback_endpoints_validate_and_preserve_seed_scope(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    first_seed = _track(database, tmp_path / "first.wav")
    second_seed = _track(database, tmp_path / "second.wav")
    candidate = _track(database, tmp_path / "candidate.wav")
    client = _client(monkeypatch, db_path)

    pair = client.post(
        "/api/evaluation/feedback/pair",
        json={
            "seed_track_ids": [first_seed.track_id, second_seed.track_id],
            "candidate_track_id": candidate.track_id,
            "rating": 3,
            "reason_tags": ["good_groove"],
            "source": "hybrid_ui",
        },
    )
    duplicate = client.post(
        "/api/evaluation/feedback/pair",
        json={
            "seed_track_ids": [first_seed.track_id, first_seed.track_id],
            "candidate_track_id": candidate.track_id,
            "rating": 2,
        },
    )
    transition = client.post(
        "/api/evaluation/feedback/transition",
        json={
            "outgoing_track_id": first_seed.track_id,
            "incoming_track_id": candidate.track_id,
            "rating": 2,
            "risk_tags": ["energy"],
        },
    )

    assert pair.status_code == 200
    assert pair.json()["ids"]
    assert duplicate.status_code == 422
    assert transition.status_code == 200
    feedback = LibraryDatabase(db_path).get_pair_feedback_map()
    assert {
        key[0]
        for key in feedback
        if key[1:] == (candidate.track_id, "hybrid_ui")
    } == {first_seed.track_id, second_seed.track_id}


def test_weighted_candidate_preview_uses_typed_targets_without_sidecar_write(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    seed = _track(database, tmp_path / "seed.wav")
    close = _track(database, tmp_path / "close.wav")
    far = _track(database, tmp_path / "far.wav")
    output = current_embedding_analysis_output("mert")
    database.register_analysis_outputs((output,))
    for identity, vector in (
        (seed, _vector(1.0, 0.0)),
        (close, _vector(0.99, 0.1)),
        (far, _vector(0.0, 1.0)),
    ):
        assert database.save_embedding_results(
            (
                EmbeddingWrite(
                    target=AnalysisTarget(
                        catalog_uuid=identity.catalog_uuid,
                        track_id=identity.track_id,
                        track_uuid=identity.track_uuid,
                        content_generation=identity.content_generation,
                    ),
                    output=EmbeddingOutput(
                        contract=output.contract,
                        vector=vector,
                        analyzed_at="2026-07-24T12:00:00Z",
                    ),
                ),
            )
        )[0].ok

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/run/weighted-candidates",
        json={
            "name": "typed-preview",
            "weights": {"mert": 1.0},
            "seed_track_ids": [seed.track_id],
            "per_source": 2,
            "limit_per_seed": 1,
            "record_session": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_ids"] == []
    assert payload["rows_returned"] == 1
    assert payload["rows"][0]["candidate_track_id"] != seed.track_id
    assert not database.evaluation_path.exists()


def test_evaluation_api_rejects_unselected_and_legacy_core(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    unselected = TestClient(create_app()).get("/api/evaluation/summary")
    legacy_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(legacy_path) as connection:
        connection.execute("PRAGMA user_version = 3")
        connection.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY)")

    legacy = TestClient(create_app()).post(
        "/api/database/switch",
        json={"path": str(legacy_path)},
    )

    assert unselected.status_code == 400
    assert unselected.json()["detail"] == "Database is not selected"
    assert legacy.status_code == 409
    assert "schema version 3 is not supported" in legacy.json()["detail"]
    assert "expected 7" in legacy.json()["detail"]


def test_evaluation_feedback_does_not_touch_audio_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    absent_audio = tmp_path / "not-created.wav"
    seed = _track(database, absent_audio)
    candidate = _track(database, tmp_path / "candidate.wav")

    response = _client(monkeypatch, db_path).post(
        "/api/evaluation/feedback/pair",
        json={
            "seed_track_ids": [seed.track_id],
            "candidate_track_id": candidate.track_id,
            "rating": 2,
        },
    )

    assert response.status_code == 200
    assert not absent_audio.exists()


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    return TestClient(create_app(db_path))


def _track(database: LibraryDatabase, path: Path):
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=10,
            file_modified_ns=1_000,
            audio_format="wav",
        ),
        tags=FileTags(title=path.stem, artist="Evaluation fixture"),
    ).identity


def _vector(first: float, second: float) -> np.ndarray:
    vector = np.zeros(768, dtype=np.float32)
    vector[:2] = (first, second)
    vector /= np.linalg.norm(vector)
    return vector
