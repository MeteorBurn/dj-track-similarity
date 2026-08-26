from __future__ import annotations

import importlib

from dj_track_similarity.database import LibraryDatabase


REPOSITORY_MODULES = {
    "dj_track_similarity.db_tracks": "TrackRepository",
    "dj_track_similarity.db_analysis": "AnalysisRepository",
    "dj_track_similarity.db_summary": "SummaryRepository",
}

# LibraryDatabase owns connection setup, so it may redefine this one.
FACADE_OWNED = {"connect"}


def test_database_repositories_are_split_behind_library_database_facade() -> None:
    for module_name, class_name in REPOSITORY_MODULES.items():
        module = importlib.import_module(module_name)
        repository_class = getattr(module, class_name)

        assert issubclass(LibraryDatabase, repository_class)


def test_library_database_inherits_repository_methods_instead_of_redefining_them() -> None:
    for module_name, class_name in REPOSITORY_MODULES.items():
        repository_class = getattr(importlib.import_module(module_name), class_name)

        for name, member in vars(repository_class).items():
            if name.startswith("_") or name in FACADE_OWNED or not callable(member):
                continue

            assert getattr(LibraryDatabase, name) is member
