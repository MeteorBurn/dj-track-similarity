from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase


def test_diagnose_metadata_size_reports_top_level_and_sonara_feature_bytes(tmp_path: Path) -> None:
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
                "beats": {"value": None, "type": "list", "summary": {"mean": 10.0}},
            },
            "maest_genres": [{"label": "Techno", "score": 0.9}],
        },
    )

    report = module.diagnose_database(db_path, top=5)

    assert report.track_count == 1
    assert report.metadata_total_bytes > 0
    assert report.top_level["sonara_features"].bytes > report.top_level["maest_genres"].bytes
    assert report.sonara_features["bpm"].count == 1
    assert report.sonara_features["beats"].count == 1
    assert report.largest_rows[0].track_id == track_id


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_metadata_size.py"
    spec = importlib.util.spec_from_file_location("diagnose_metadata_size", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
