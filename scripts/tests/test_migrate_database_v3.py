from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "migrate_database_v3.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("migrate_database_v3", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_script_has_no_project_runtime_imports() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "dj_track_similarity" not in source


def test_migration_script_dry_run_reports_v2_to_v3_without_mutating(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    _create_v2_library_database(db_path)

    summary = module.migrate_database_v3(db_path, apply=False)

    assert summary.dry_run is True
    assert summary.version_before == 2
    assert summary.version_after == 2
    assert summary.backup_path is None
    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(tracks)").fetchall()}
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 2
    assert "has_sonara_analysis" not in columns
    assert not list(tmp_path.glob("library.sqlite.bak-*"))


def test_migration_script_applies_v3_flags_indexes_and_backfill(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    track_ids = _create_v2_library_database(db_path)

    summary = module.migrate_database_v3(db_path, apply=True)

    assert summary.dry_run is False
    assert summary.version_before == 2
    assert summary.version_after == 3
    assert summary.backup_path is not None
    assert summary.backup_path.exists()
    assert summary.tracks == 4
    assert summary.sonara == 1
    assert summary.maest == 1
    assert summary.mert == 2
    assert summary.clap == 1
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        track_indexes = {row["name"] for row in connection.execute("PRAGMA index_list(tracks)").fetchall()}
        flags = {
            row["id"]: {
                "has_sonara_analysis": row["has_sonara_analysis"],
                "has_maest_embedding": row["has_maest_embedding"],
                "has_mert_embedding": row["has_mert_embedding"],
                "has_clap_embedding": row["has_clap_embedding"],
            }
            for row in connection.execute(
                """
                SELECT id, has_sonara_analysis, has_maest_embedding, has_mert_embedding, has_clap_embedding
                FROM tracks
                ORDER BY id
                """
            ).fetchall()
        }
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    assert version == 3
    assert flags == {
        track_ids["sonara"]: {
            "has_sonara_analysis": 1,
            "has_maest_embedding": 0,
            "has_mert_embedding": 0,
            "has_clap_embedding": 0,
        },
        track_ids["maest"]: {
            "has_sonara_analysis": 0,
            "has_maest_embedding": 1,
            "has_mert_embedding": 0,
            "has_clap_embedding": 0,
        },
        track_ids["mert_clap"]: {
            "has_sonara_analysis": 0,
            "has_maest_embedding": 0,
            "has_mert_embedding": 1,
            "has_clap_embedding": 1,
        },
        track_ids["mert"]: {
            "has_sonara_analysis": 0,
            "has_maest_embedding": 0,
            "has_mert_embedding": 1,
            "has_clap_embedding": 0,
        },
    }
    assert {
        "idx_tracks_missing_sonara_flag_sort",
        "idx_tracks_missing_maest_embedding_flag_sort",
        "idx_tracks_missing_mert_embedding_flag_sort",
        "idx_tracks_missing_clap_embedding_flag_sort",
        "idx_tracks_present_sonara_flag",
        "idx_tracks_present_maest_embedding_flag",
        "idx_tracks_present_mert_embedding_flag",
        "idx_tracks_present_clap_embedding_flag",
    }.issubset(track_indexes)
    assert not {
        "idx_tracks_sonara_present",
        "idx_tracks_maest_present",
        "idx_tracks_sonara_missing_sort",
        "idx_tracks_maest_missing_sort",
    }.intersection(track_indexes)
    assert integrity == "ok"


def test_migration_script_dry_run_reports_missing_v3_fts_without_mutating(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    _create_v3_library_database_without_fts(db_path)

    summary = module.migrate_database_v3(db_path, apply=False)

    assert summary.dry_run is True
    assert summary.version_before == 3
    assert summary.version_after == 3
    assert summary.backup_path is None
    assert summary.tracks == 2
    assert summary.fts_rows == 0
    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert version == 3
    assert "track_search_fts" not in tables
    assert not list(tmp_path.glob("library.sqlite.bak-*"))


def test_migration_script_applies_v3_fts_to_existing_v3_database(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    track_ids = _create_v3_library_database_without_fts(db_path)

    summary = module.migrate_database_v3(db_path, apply=True)

    assert summary.dry_run is False
    assert summary.version_before == 3
    assert summary.version_after == 3
    assert summary.backup_path is not None
    assert summary.backup_path.exists()
    assert summary.tracks == 2
    assert summary.fts_rows == 2
    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        fts_ids = [
            int(row["track_id"])
            for row in connection.execute(
                """
                SELECT f.track_id
                FROM track_search_fts f
                WHERE track_search_fts MATCH ?
                ORDER BY f.track_id
                """,
                ('"warehouse"',),
            ).fetchall()
        ]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    assert version == 3
    assert "track_search_fts" in tables
    assert fts_ids == [track_ids["warehouse"]]
    assert integrity == "ok"


def _create_v2_library_database(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
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
            CREATE TABLE library_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE track_classifier_scores (
                track_id INTEGER NOT NULL,
                classifier TEXT NOT NULL,
                score REAL NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
                feature_set TEXT NOT NULL,
                model_id TEXT NOT NULL,
                analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(track_id, classifier),
                FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );
            CREATE TABLE track_likes (
                track_id INTEGER PRIMARY KEY,
                liked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );
            CREATE INDEX idx_tracks_sort_artist_title_path
            ON tracks (COALESCE(artist, ''), COALESCE(title, ''), path);
            CREATE INDEX idx_tracks_sonara_present
            ON tracks(id)
            WHERE json_type(metadata_json, '$.sonara_features') IS NOT NULL;
            CREATE INDEX idx_tracks_maest_present
            ON tracks(id)
            WHERE json_type(metadata_json, '$.maest_genres') IS NOT NULL;
            CREATE INDEX idx_tracks_syncopated_sort
            ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
            WHERE json_extract(metadata_json, '$.maest_syncopated_rhythm') = 1;
            CREATE INDEX idx_tracks_sonara_missing_sort
            ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
            WHERE json_type(metadata_json, '$.sonara_features') IS NULL;
            CREATE INDEX idx_tracks_maest_missing_sort
            ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
            WHERE (
                json_type(metadata_json, '$.maest_genres') IS NULL
                OR json_type(metadata_json, '$.maest_genres') != 'array'
                OR json_array_length(json_extract(metadata_json, '$.maest_genres')) = 0
            );
            CREATE INDEX idx_embeddings_key_track
            ON embeddings(embedding_key, track_id);
            CREATE INDEX idx_classifier_scores_lookup
            ON track_classifier_scores(classifier, score DESC, track_id);
            PRAGMA user_version = 2;
            """
        )
        rows = {
            "sonara": ("sonara.wav", "Sonara", '{"sonara_features":{"tempo":128},"sonara_model":"sonara"}'),
            "maest": ("maest.wav", "MAEST", "{}"),
            "mert_clap": ("mert-clap.wav", "MERT CLAP", "{}"),
            "mert": ("mert.wav", "MERT", "{}"),
        }
        track_ids = {}
        for key, (path_text, title, metadata_json) in rows.items():
            cursor = connection.execute(
                """
                INSERT INTO tracks(path, size, mtime, title, metadata_json)
                VALUES (?, 10, 1, ?, ?)
                """,
                (path_text, title, metadata_json),
            )
            track_ids[key] = int(cursor.lastrowid)
        for track_key, embedding_key in (("maest", "maest"), ("mert_clap", "mert"), ("mert_clap", "clap"), ("mert", "mert")):
            connection.execute(
                """
                INSERT INTO embeddings(track_id, embedding_key, model_name, dim, vector)
                VALUES (?, ?, ?, 1, ?)
                """,
                (track_ids[track_key], embedding_key, f"{embedding_key}-model", b"\x00\x00\x80?"),
            )
    return track_ids


def _create_v3_library_database_without_fts(path: Path) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
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
            CREATE TABLE track_classifier_scores (
                track_id INTEGER NOT NULL,
                classifier TEXT NOT NULL,
                score REAL NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
                feature_set TEXT NOT NULL,
                model_id TEXT NOT NULL,
                analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(track_id, classifier),
                FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );
            CREATE TABLE track_likes (
                track_id INTEGER PRIMARY KEY,
                liked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );
            PRAGMA user_version = 3;
            """
        )
        rows = {
            "warehouse": ("warehouse.wav", "DJ One", "Dark Room", '{"comment":"warehouse"}'),
            "radio": ("radio.wav", "DJ Two", "Radio Edit", '{"comment":"daytime"}'),
        }
        track_ids = {}
        for key, (path_text, artist, title, metadata_json) in rows.items():
            cursor = connection.execute(
                """
                INSERT INTO tracks(path, size, mtime, artist, title, metadata_json)
                VALUES (?, 10, 1, ?, ?, ?)
                """,
                (path_text, artist, title, metadata_json),
            )
            track_ids[key] = int(cursor.lastrowid)
    return track_ids
