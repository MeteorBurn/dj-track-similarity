from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_storage import storage_database_paths
from dj_track_similarity.track_models import FileTags, ScannedFile


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
    mutation = db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / "track.wav"),
            file_size_bytes=10,
            file_modified_ns=1,
            audio_format="wav",
        ),
        tags=FileTags(title="Track", artist="Artist", genres=("Breakbeat",)),
    )
    evaluation = db.connect_evaluation(create=True)
    assert evaluation is not None
    evaluation.close()

    summary = module.optimize_database(db_path)

    assert all(path.exists() for path in summary.backup_paths)
    assert [item.role for item in summary.files] == ["core", "artifacts", "evaluation"]
    assert summary.database_kind == "library"
    assert summary.integrity_before == "ok"
    assert summary.integrity_after == "ok"
    with sqlite3.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        stored_track = connection.execute(
            "SELECT track_uuid, content_generation FROM tracks WHERE track_id = ?",
            (mutation.identity.track_id,),
        ).fetchone()
        core_catalog_uuid = connection.execute(
            "SELECT catalog_uuid FROM library_catalog WHERE singleton_id = 1"
        ).fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    sidecars = storage_database_paths(db_path)
    with sqlite3.connect(sidecars.artifacts) as connection:
        artifacts_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        artifacts_catalog_uuid = connection.execute(
            "SELECT catalog_uuid FROM storage_metadata WHERE singleton_id = 1"
        ).fetchone()[0]
        artifacts_integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    with sqlite3.connect(sidecars.evaluation) as connection:
        evaluation_catalog_uuid = connection.execute(
            "SELECT catalog_uuid FROM storage_metadata WHERE singleton_id = 1"
        ).fetchone()[0]
        evaluation_integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    assert version == 7
    assert stored_track == (
        mutation.identity.track_uuid,
        mutation.identity.content_generation,
    )
    assert "library_settings" in tables
    assert "classifier_scores" in tables
    assert "mert_embeddings" in artifacts_tables
    assert "sonara_timeline" in artifacts_tables
    assert core_catalog_uuid == artifacts_catalog_uuid == evaluation_catalog_uuid
    assert integrity == "ok"
    assert artifacts_integrity == "ok"
    assert evaluation_integrity == "ok"


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
            CREATE TABLE classifier_profile_labels (
                classifier_key TEXT NOT NULL,
                label_key TEXT NOT NULL,
                PRIMARY KEY(classifier_key, label_key)
            );
            CREATE TABLE classifier_labels (
                classifier_key TEXT NOT NULL,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                content_generation INTEGER NOT NULL,
                label TEXT NOT NULL,
                PRIMARY KEY(
                    classifier_key,
                    catalog_uuid,
                    track_uuid,
                    content_generation
                )
            );
            CREATE TABLE classifier_predictions (
                classifier_key TEXT NOT NULL,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                content_generation INTEGER NOT NULL,
                feature_set TEXT NOT NULL,
                model_artifact TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL,
                PRIMARY KEY(
                    classifier_key,
                    catalog_uuid,
                    track_uuid,
                    content_generation,
                    feature_set,
                    model_artifact
                )
            );
            CREATE TABLE classifier_training_checkpoints (
                classifier_key TEXT PRIMARY KEY,
                counts_json TEXT NOT NULL
            );
            INSERT INTO classifier_profiles(classifier_key, name) VALUES ('break_energy', 'Break Energy');
            INSERT INTO classifier_labels(
                classifier_key,
                catalog_uuid,
                track_uuid,
                content_generation,
                label
            )
            VALUES ('break_energy', 'catalog-1', 'track-1', 1, 'broken');
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


def test_optimize_database_script_rejects_removed_single_file_library_schema(tmp_path: Path) -> None:
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

    with pytest.raises(RuntimeError, match="Unsupported SQLite database"):
        module.optimize_database(db_path)

    assert not list(tmp_path.glob("library.sqlite.bak-*"))


def test_optimize_database_script_rejects_unknown_sqlite_database(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "other.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE unrelated(id INTEGER PRIMARY KEY)")

    with pytest.raises(RuntimeError, match="Unsupported SQLite database"):
        module.optimize_database(db_path)

    assert not list(tmp_path.glob("other.sqlite.bak-*"))
