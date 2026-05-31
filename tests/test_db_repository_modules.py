from __future__ import annotations

import importlib
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase


REPOSITORY_MODULES = {
    "dj_track_similarity.db_tracks": "TrackRepository",
    "dj_track_similarity.db_analysis": "AnalysisRepository",
    "dj_track_similarity.db_summary": "SummaryRepository",
}


def test_database_repositories_are_split_behind_library_database_facade() -> None:
    for module_name, class_name in REPOSITORY_MODULES.items():
        module = importlib.import_module(module_name)
        repository_class = getattr(module, class_name)

        assert issubclass(LibraryDatabase, repository_class)


def test_database_facade_no_longer_defines_repository_methods_inline() -> None:
    source = Path("src/dj_track_similarity/database.py").read_text(encoding="utf-8")

    assert "def list_tracks_page(" not in source
    assert "def save_embedding(" not in source
    assert "def library_summary(" not in source
