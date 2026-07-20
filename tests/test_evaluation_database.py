from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_evaluation import PROMOTED_SCORE_PROFILE_SETTING_KEY
from dj_track_similarity.db_schema import CURRENT_SCHEMA_VERSION


def test_evaluation_repository_records_sessions_results_feedback_and_calibration(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1, metadata={"title": "Seed"})
    candidate_id = db.upsert_track(
        path=tmp_path / "candidate.wav",
        size=10,
        mtime=1,
        metadata={"title": "Candidate"},
    )

    session_id = db.create_search_session("mert", [seed_id], {"query": "Seed", "limit": 5})
    event_id = db.record_search_result_event(
        session_id,
        candidate_id,
        rank=1,
        total_score=0.875,
        score_breakdown={"mert": 0.8, "sonara": 0.95},
    )
    pair_feedback_id = db.upsert_track_pair_feedback(
        seed_id,
        candidate_id,
        3,
        reason_tags=(" groove ", "mixable"),
        notes="works",
    )
    transition_feedback_id = db.add_transition_feedback(
        seed_id,
        candidate_id,
        2,
        risk_tags=("energy",),
        notes="watch outro",
    )
    calibration_run_id = db.record_calibration_run(
        "default",
        "mert",
        {"weights": {"mert": 1.0}},
        {"precision_at_10": 0.5},
    )

    with db.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        session = connection.execute("SELECT * FROM search_sessions WHERE id = ?", (session_id,)).fetchone()
        event = connection.execute("SELECT * FROM search_result_events WHERE id = ?", (event_id,)).fetchone()
        pair_feedback = connection.execute(
            "SELECT * FROM track_pair_feedback WHERE id = ?",
            (pair_feedback_id,),
        ).fetchone()
        transition_feedback = connection.execute(
            "SELECT * FROM transition_feedback WHERE id = ?",
            (transition_feedback_id,),
        ).fetchone()
        calibration_run = connection.execute(
            "SELECT * FROM calibration_runs WHERE id = ?",
            (calibration_run_id,),
        ).fetchone()

    assert version == CURRENT_SCHEMA_VERSION == 6
    assert json.loads(session["seed_track_ids_json"]) == [seed_id]
    assert json.loads(session["request_json"]) == {"limit": 5, "query": "Seed"}
    assert event["track_id"] == candidate_id
    assert json.loads(event["score_breakdown_json"]) == {"mert": 0.8, "sonara": 0.95}
    assert pair_feedback["rating"] == 3
    assert json.loads(pair_feedback["reason_tags_json"]) == ["groove", "mixable"]
    assert transition_feedback["rating"] == 2
    assert json.loads(transition_feedback["risk_tags_json"]) == ["energy"]
    assert json.loads(calibration_run["config_json"]) == {"weights": {"mert": 1.0}}
    assert json.loads(calibration_run["metrics_json"]) == {"precision_at_10": 0.5}


def test_track_pair_feedback_upsert_reuses_row_and_updates_rating(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1, metadata={"title": "Seed"})
    candidate_id = db.upsert_track(
        path=tmp_path / "candidate.wav",
        size=10,
        mtime=1,
        metadata={"title": "Candidate"},
    )

    first_id = db.upsert_track_pair_feedback(seed_id, candidate_id, 1, reason_tags=("rough",), source="manual")
    second_id = db.upsert_track_pair_feedback(seed_id, candidate_id, 3, reason_tags=("strong",), source="manual")

    with db.connect() as connection:
        rows = connection.execute("SELECT id, rating, reason_tags_json FROM track_pair_feedback").fetchall()

    assert second_id == first_id
    assert len(rows) == 1
    assert rows[0]["rating"] == 3
    assert json.loads(rows[0]["reason_tags_json"]) == ["strong"]


def test_evaluation_repository_rejects_invalid_rating_before_sqlite_check(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1, metadata={"title": "Seed"})
    candidate_id = db.upsert_track(
        path=tmp_path / "candidate.wav",
        size=10,
        mtime=1,
        metadata={"title": "Candidate"},
    )

    with pytest.raises(ValueError, match="Rating must be an integer between 0 and 3"):
        db.upsert_track_pair_feedback(seed_id, candidate_id, 4)

    with db.connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM track_pair_feedback").fetchone()[0]
    assert count == 0


def test_evaluation_repository_stores_promoted_score_profile_marker(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    promoted_profile = {
        "profile_name": "judged_default",
        "source": "judged_feedback",
        "promotion_source": "score_profile_optimizer",
        "weights": {"mert": 1.0},
        "risk_weights": {"transition_risk": 0.0},
    }

    stored_profile = db.set_promoted_score_profile(promoted_profile)

    assert stored_profile == promoted_profile
    assert db.get_promoted_score_profile() == promoted_profile
    with db.connect() as connection:
        row = connection.execute(
            "SELECT value FROM library_settings WHERE key = ?",
            (PROMOTED_SCORE_PROFILE_SETTING_KEY,),
        ).fetchone()
    assert json.loads(row["value"]) == promoted_profile


def test_evaluation_foreign_keys_cascade_with_tracks_and_sessions(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1, metadata={"title": "Seed"})
    candidate_id = db.upsert_track(
        path=tmp_path / "candidate.wav",
        size=10,
        mtime=1,
        metadata={"title": "Candidate"},
    )
    session_id = db.create_search_session("mert", [seed_id], {"limit": 5})
    db.record_search_result_event(session_id, candidate_id, rank=1, total_score=1.0, score_breakdown={"mert": 1.0})
    db.upsert_track_pair_feedback(seed_id, candidate_id, 2)
    db.add_transition_feedback(seed_id, candidate_id, 2)

    with db._write_lock, db.connect() as connection:
        connection.execute("DELETE FROM search_sessions WHERE id = ?", (session_id,))
        result_events = connection.execute("SELECT COUNT(*) FROM search_result_events").fetchone()[0]
        connection.execute("DELETE FROM tracks WHERE id = ?", (candidate_id,))
        pair_feedback = connection.execute("SELECT COUNT(*) FROM track_pair_feedback").fetchone()[0]
        transition_feedback = connection.execute("SELECT COUNT(*) FROM transition_feedback").fetchone()[0]

    assert result_events == 0
    assert pair_feedback == 0
    assert transition_feedback == 0


def test_existing_v3_database_is_rejected_instead_of_runtime_migrated(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                artist TEXT,
                title TEXT,
                album TEXT,
                bpm REAL,
                musical_key TEXT,
                energy REAL,
                duration REAL,
                has_sonara_analysis INTEGER NOT NULL DEFAULT 0,
                has_maest_embedding INTEGER NOT NULL DEFAULT 0,
                has_mert_embedding INTEGER NOT NULL DEFAULT 0,
                has_clap_embedding INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE embeddings (
                track_id INTEGER NOT NULL,
                embedding_key TEXT NOT NULL DEFAULT 'mert',
                model_name TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector BLOB NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(track_id, embedding_key),
                FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );
            CREATE TABLE library_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE VIRTUAL TABLE track_search_fts USING fts5(
                track_id UNINDEXED,
                search_text,
                tokenize = 'unicode61'
            );
            PRAGMA user_version = 3;
            """
        )

    with pytest.raises(RuntimeError, match="schema is not current"):
        LibraryDatabase(db_path)

    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert version == 3
    assert "search_sessions" not in tables
