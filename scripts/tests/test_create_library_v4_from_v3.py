from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "create_library_v4_from_v3.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("create_library_v4_from_v3", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_create_library_v4_script_has_no_project_runtime_imports() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "dj_track_similarity" not in source


def test_create_library_v4_dry_run_reports_plan_without_writing(tmp_path: Path) -> None:
    module = _load_script()
    source_path = tmp_path / "library_v3.sqlite"
    dest_path = tmp_path / "library_v4.sqlite"
    _create_v3_library_database(source_path)

    summary = module.create_library_v4_from_v3(source_path, dest_path, apply=False)

    assert summary.dry_run is True
    assert summary.source_version == 3
    assert summary.dest_version == 4
    assert summary.source_tracks == 2
    assert summary.source_integrity == "ok"
    assert summary.dest_integrity is None
    assert dest_path.exists() is False
    with sqlite3.connect(source_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert version == 3
    assert "search_sessions" not in tables


def test_create_library_v4_apply_copies_source_and_adds_evaluation_schema(tmp_path: Path) -> None:
    module = _load_script()
    source_path = tmp_path / "library_v3.sqlite"
    dest_path = tmp_path / "library_v4.sqlite"
    track_ids = _create_v3_library_database(source_path)

    summary = module.create_library_v4_from_v3(source_path, dest_path, apply=True)

    assert summary.dry_run is False
    assert summary.source_version == 3
    assert summary.dest_version == 4
    assert summary.dest_integrity == "ok"
    assert summary.evaluation_tables == (
        "calibration_runs",
        "search_result_events",
        "search_sessions",
        "track_pair_feedback",
        "transition_feedback",
    )
    with sqlite3.connect(dest_path) as connection:
        connection.row_factory = sqlite3.Row
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        copied_paths = [row["path"] for row in connection.execute("SELECT path FROM tracks ORDER BY id").fetchall()]
        source_like = connection.execute("SELECT COUNT(*) FROM track_likes WHERE track_id = ?", (track_ids["seed"],)).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    assert version == 4
    assert set(summary.evaluation_tables).issubset(tables)
    assert copied_paths == ["seed.wav", "candidate.wav"]
    assert source_like == 1
    assert integrity == "ok"


def test_create_library_v4_apply_leaves_source_v3_unchanged(tmp_path: Path) -> None:
    module = _load_script()
    source_path = tmp_path / "library_v3.sqlite"
    dest_path = tmp_path / "library_v4.sqlite"
    _create_v3_library_database(source_path)

    module.create_library_v4_from_v3(source_path, dest_path, apply=True)

    with sqlite3.connect(source_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    assert version == 3
    assert "search_sessions" not in tables
    assert integrity == "ok"


def test_create_library_v4_apply_rejects_existing_dest_unless_forced(tmp_path: Path) -> None:
    module = _load_script()
    source_path = tmp_path / "library_v3.sqlite"
    dest_path = tmp_path / "library_v4.sqlite"
    _create_v3_library_database(source_path)
    dest_path.write_text("already here", encoding="utf-8")

    with pytest.raises(FileExistsError, match="Destination already exists"):
        module.create_library_v4_from_v3(source_path, dest_path, apply=True)

    summary = module.create_library_v4_from_v3(source_path, dest_path, apply=True, force=True)

    assert summary.dest_existed is True
    with sqlite3.connect(dest_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 4


def test_create_library_v4_rejects_non_v3_source_without_creating_dest(tmp_path: Path) -> None:
    module = _load_script()
    source_path = tmp_path / "library_v2.sqlite"
    dest_path = tmp_path / "library_v4.sqlite"
    _create_v3_library_database(source_path, version=2)

    with pytest.raises(RuntimeError, match="Expected source schema version 3"):
        module.create_library_v4_from_v3(source_path, dest_path, apply=True)

    assert dest_path.exists() is False


def _create_v3_library_database(path: Path, *, version: int = 3) -> dict[str, int]:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            f"""
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
                metadata_json TEXT NOT NULL DEFAULT '{{}}' CHECK (json_valid(metadata_json)),
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
            CREATE VIRTUAL TABLE track_search_fts USING fts5(
                track_id UNINDEXED,
                search_text,
                tokenize = 'unicode61'
            );
            CREATE INDEX idx_embeddings_key_track
            ON embeddings(embedding_key, track_id);
            CREATE INDEX idx_classifier_scores_lookup
            ON track_classifier_scores(classifier, score DESC, track_id);
            PRAGMA user_version = {version};
            """
        )
        track_ids: dict[str, int] = {}
        for key, path_text, title in (
            ("seed", "seed.wav", "Seed"),
            ("candidate", "candidate.wav", "Candidate"),
        ):
            cursor = connection.execute(
                """
                INSERT INTO tracks(path, size, mtime, title, metadata_json)
                VALUES (?, 10, 1, ?, '{}')
                """,
                (path_text, title),
            )
            track_ids[key] = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO track_search_fts(rowid, track_id, search_text)
                VALUES (?, ?, ?)
                """,
                (track_ids[key], track_ids[key], f"{title} {path_text}"),
            )
        connection.execute("INSERT INTO track_likes(track_id) VALUES (?)", (track_ids["seed"],))
    return track_ids
