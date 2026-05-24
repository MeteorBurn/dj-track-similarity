from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


def _load_migration_module():
    script_path = Path(__file__).resolve().parents[1] / "migrate_sonara_brightness.py"
    spec = importlib.util.spec_from_file_location("migrate_sonara_brightness", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _insert_metadata(path: Path, metadata: dict[str, object]) -> int:
    with sqlite3.connect(path) as connection:
        cursor = connection.execute(
            "INSERT INTO tracks(metadata_json) VALUES (?)",
            (json.dumps(metadata, ensure_ascii=False),),
        )
        return int(cursor.lastrowid)


def _metadata(path: Path, track_id: int) -> dict[str, object]:
    with sqlite3.connect(path) as connection:
        value = connection.execute("SELECT metadata_json FROM tracks WHERE id = ?", (track_id,)).fetchone()[0]
    return json.loads(value)


def test_migration_dry_run_reports_brightness_without_updating(tmp_path: Path) -> None:
    module = _load_migration_module()
    db_path = tmp_path / "library.sqlite"
    _create_db(db_path)
    track_id = _insert_metadata(db_path, {"sonara_features": {"brightness": {"value": 3200.0, "type": "float"}}})

    summary = module.migrate_database(db_path)

    assert summary.tracks_scanned == 1
    assert summary.tracks_updated == 1
    assert summary.moved == 1
    assert summary.dry_run is True
    assert "brightness" in _metadata(db_path, track_id)["sonara_features"]


def test_migration_apply_moves_brightness_to_spectral_centroid_mean(tmp_path: Path) -> None:
    module = _load_migration_module()
    db_path = tmp_path / "library.sqlite"
    _create_db(db_path)
    track_id = _insert_metadata(db_path, {"sonara_features": {"brightness": {"value": 3200.0, "type": "float"}}})

    summary = module.migrate_database(db_path, apply=True)
    features = _metadata(db_path, track_id)["sonara_features"]

    assert summary.dry_run is False
    assert summary.moved == 1
    assert "brightness" not in features
    assert features["spectral_centroid_mean"] == {"value": 3200.0, "type": "float"}


def test_migration_does_not_overwrite_existing_spectral_centroid(tmp_path: Path) -> None:
    module = _load_migration_module()
    db_path = tmp_path / "library.sqlite"
    _create_db(db_path)
    track_id = _insert_metadata(
        db_path,
        {
            "sonara_features": {
                "brightness": {"value": 9999.0, "type": "float"},
                "spectral_centroid_mean": {"value": 3200.0, "type": "float"},
            }
        },
    )

    summary = module.migrate_database(db_path, apply=True)
    features = _metadata(db_path, track_id)["sonara_features"]

    assert summary.conflicts == 1
    assert summary.moved == 0
    assert features["brightness"] == {"value": 9999.0, "type": "float"}
    assert features["spectral_centroid_mean"] == {"value": 3200.0, "type": "float"}
