from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "optimize_database.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("optimize_database", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_optimize_database_script_optimizes_current_schema_without_project_imports(tmp_path: Path) -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "dj_track_similarity" not in source
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = db.upsert_track(
        path=tmp_path / "track.wav",
        size=10,
        mtime=1,
        metadata={
            "title": "Track",
            "sonara_features": {},
            "maest_genres": [{"label": "Breakbeat"}],
            "maest_syncopated_rhythm": True,
        },
    )
    db.save_embedding(track_id, [1.0], "mert-model", 1, embedding_key="mert")

    summary = module.optimize_database(db_path)

    assert summary.backup_path.exists()
    assert summary.database_kind == "library"
    assert summary.integrity_before == "ok"
    assert summary.integrity_after == "ok"
    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        track_indexes = {row[1] for row in connection.execute("PRAGMA index_list(tracks)").fetchall()}
        embedding_indexes = {row[1] for row in connection.execute("PRAGMA index_list(embeddings)").fetchall()}
        classifier_indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(track_classifier_scores)").fetchall()
        }
        embedding_keys = [row[0] for row in connection.execute("SELECT embedding_key FROM embeddings ORDER BY embedding_key")]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    assert version == 2
    assert "library_settings" in tables
    assert "track_classifier_scores" in tables
    assert embedding_keys == ["mert"]
    assert {
        "idx_tracks_sort_artist_title_path",
        "idx_tracks_sonara_present",
        "idx_tracks_maest_present",
        "idx_tracks_syncopated_sort",
        "idx_tracks_sonara_missing_sort",
        "idx_tracks_maest_missing_sort",
    }.issubset(track_indexes)
    assert "idx_embeddings_key_track" in embedding_indexes
    assert "idx_classifier_scores_lookup" in classifier_indexes
    assert integrity == "ok"


def test_optimize_database_script_optimizes_rhythm_lab_database(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "rhythm_lab.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE classifier_profiles (
                classifier_key TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );
            CREATE TABLE classifier_labels (
                classifier_key TEXT NOT NULL,
                source_track_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                PRIMARY KEY(classifier_key, source_track_id)
            );
            CREATE TABLE classifier_predictions (
                classifier_key TEXT NOT NULL,
                source_track_id INTEGER NOT NULL,
                feature_set TEXT NOT NULL,
                model_artifact TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL,
                PRIMARY KEY(classifier_key, source_track_id, feature_set, model_artifact)
            );
            CREATE TABLE classifier_training_checkpoints (
                classifier_key TEXT PRIMARY KEY,
                counts_json TEXT NOT NULL
            );
            INSERT INTO classifier_profiles(classifier_key, name) VALUES ('break_energy', 'Break Energy');
            INSERT INTO classifier_labels(classifier_key, source_track_id, label)
            VALUES ('break_energy', 1, 'broken');
            """
        )

    summary = module.optimize_database(db_path)

    assert summary.database_kind == "rhythm_lab"
    assert summary.backup_path.exists()
    assert summary.integrity_before == "ok"
    assert summary.integrity_after == "ok"
    with sqlite3.connect(db_path) as connection:
        labels = connection.execute("SELECT label FROM classifier_labels").fetchall()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    assert labels == [("broken",)]
    assert integrity == "ok"


def test_optimize_database_script_optimizes_supported_library_schema_without_migrating(tmp_path: Path) -> None:
    module = _load_script()
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
            INSERT INTO tracks (path, size, mtime, title, metadata_json)
            VALUES ('track.wav', 10, 1, 'Track', '{}');
            """
        )

    summary = module.optimize_database(db_path)

    assert summary.database_kind == "library"
    assert summary.backup_path.exists()
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]

    assert tables == {"tracks", "embeddings"}
    assert version == 0


def test_optimize_database_script_rejects_unknown_sqlite_database(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "other.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE unrelated(id INTEGER PRIMARY KEY)")

    with pytest.raises(RuntimeError, match="Unsupported SQLite database"):
        module.optimize_database(db_path)

    assert not list(tmp_path.glob("other.sqlite.bak-*"))
