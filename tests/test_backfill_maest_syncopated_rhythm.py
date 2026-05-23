from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase


def test_backfill_maest_syncopated_rhythm_updates_existing_metadata(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    breaks_id = db.upsert_track(
        path=tmp_path / "breaks.wav",
        size=10,
        mtime=1,
        metadata={
            "title": "Breaks",
            "maest_genres": [{"label": "Electronic---Breakbeat", "score": 0.9}],
            "maest_model": "legacy-maest",
        },
    )
    house_id = db.upsert_track(
        path=tmp_path / "house.wav",
        size=10,
        mtime=1,
        metadata={
            "title": "House",
            "maest_genres": [{"label": "Tech House", "score": 0.8}],
            "maest_model": "legacy-maest",
        },
    )
    db.upsert_track(path=tmp_path / "plain.wav", size=10, mtime=1, metadata={"title": "Plain"})

    dry_run = module.backfill_database(db_path)
    assert dry_run.updated == 2
    assert dry_run.dry_run is True
    assert "maest_syncopated_rhythm" not in db.get_track(breaks_id).metadata

    summary = module.backfill_database(db_path, apply=True)

    assert summary.scanned == 3
    assert summary.updated == 2
    assert summary.dry_run is False
    assert summary.skipped_without_maest == 1
    assert summary.syncopated_true == 1
    assert summary.syncopated_false == 1
    assert db.get_track(breaks_id).metadata["maest_syncopated_rhythm"] is True
    assert db.get_track(house_id).metadata["maest_syncopated_rhythm"] is False

    with db.connect() as connection:
        metadata_json = connection.execute("SELECT metadata_json FROM tracks WHERE id = ?", (breaks_id,)).fetchone()["metadata_json"]
    assert list(json.loads(metadata_json).keys())[-3:] == ["maest_model", "maest_genres", "maest_syncopated_rhythm"]


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "backfill_maest_syncopated_rhythm.py"
    spec = importlib.util.spec_from_file_location("backfill_maest_syncopated_rhythm", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
