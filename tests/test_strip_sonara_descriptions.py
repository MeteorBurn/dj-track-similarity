from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase


def test_strip_sonara_descriptions_dry_run_and_apply_removes_descriptions_and_chord_sequence(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = db.upsert_track(
        path=tmp_path / "one.wav",
        size=10,
        mtime=1,
        metadata={
            "title": "One",
            "sonara_features": {
                "bpm": {"value": 128.0, "type": "float", "description": "tempo"},
                "energy": {"value": 0.7, "type": "float", "description": "intensity"},
                "chord_sequence": {"value": ["Am", "F", "C", "G"], "type": "list", "length": 4},
            },
            "comment": "keep me",
        },
    )

    dry_run = module.strip_sonara_descriptions(db_path, apply=False)

    assert dry_run.tracks_scanned == 1
    assert dry_run.tracks_updated == 1
    assert dry_run.descriptions_removed == 2
    assert dry_run.chord_sequences_removed == 1
    assert dry_run.dry_run is True
    assert "description" in db.get_track(track_id).metadata["sonara_features"]["bpm"]
    assert "chord_sequence" in db.get_track(track_id).metadata["sonara_features"]

    applied = module.strip_sonara_descriptions(db_path, apply=True)

    metadata = db.get_track(track_id).metadata
    assert applied.tracks_scanned == 1
    assert applied.tracks_updated == 1
    assert applied.descriptions_removed == 2
    assert applied.chord_sequences_removed == 1
    assert applied.dry_run is False
    assert metadata["comment"] == "keep me"
    assert metadata["sonara_features"]["bpm"] == {"value": 128.0, "type": "float"}
    assert metadata["sonara_features"]["energy"] == {"value": 0.7, "type": "float"}
    assert "chord_sequence" not in metadata["sonara_features"]


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "strip_sonara_descriptions.py"
    spec = importlib.util.spec_from_file_location("strip_sonara_descriptions", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
