from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "optimize_database.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("optimize_database", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_optimize_database_script_updates_schema_and_indexes_without_project_imports(tmp_path: Path) -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "dj_track_similarity" not in source
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
            CREATE TABLE playlists (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL);
            CREATE TABLE playlist_tracks (playlist_id INTEGER NOT NULL, track_id INTEGER NOT NULL, position INTEGER NOT NULL);
            INSERT INTO tracks (path, size, mtime, title, metadata_json)
            VALUES ('track.wav', 10, 1, 'Track', '{"sonara_features": {}, "maest_genres": [{"label": "Breakbeat"}], "maest_syncopated_rhythm": true}');
            INSERT INTO embeddings (track_id, embedding_key, model_name, dim, vector)
            VALUES (1, 'fake', 'fake-model', 1, x'00000000');
            INSERT INTO embeddings (track_id, embedding_key, model_name, dim, vector)
            VALUES (1, 'mert', 'mert-model', 1, x'00000000');
            """
        )

    summary = module.optimize_database(db_path)

    assert summary.backup_path.exists()
    assert summary.integrity_before == "ok"
    assert summary.integrity_after == "ok"
    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        track_indexes = {row[1] for row in connection.execute("PRAGMA index_list(tracks)").fetchall()}
        embedding_indexes = {row[1] for row in connection.execute("PRAGMA index_list(embeddings)").fetchall()}
        embedding_keys = [row[0] for row in connection.execute("SELECT embedding_key FROM embeddings ORDER BY embedding_key")]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    assert version == module.CURRENT_SCHEMA_VERSION
    assert "library_settings" in tables
    assert "playlists" not in tables
    assert "playlist_tracks" not in tables
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
    assert integrity == "ok"
