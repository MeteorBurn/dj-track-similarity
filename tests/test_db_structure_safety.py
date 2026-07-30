from __future__ import annotations

import sqlite3

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_structure import DatabaseStructureError


def test_structure_rejection_does_not_mutate_or_create_bundle_files(tmp_path) -> None:
    core_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(core_path) as connection:
        connection.execute("CREATE TABLE legacy_tracks(track_id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO legacy_tracks(track_id) VALUES (1)")
        connection.execute("PRAGMA user_version = 6")

    bytes_before = core_path.read_bytes()
    entries_before = {path.name for path in tmp_path.iterdir()}

    with pytest.raises(DatabaseStructureError):
        LibraryDatabase(core_path)

    assert core_path.read_bytes() == bytes_before
    assert {path.name for path in tmp_path.iterdir()} == entries_before
    assert not core_path.with_suffix(".artifacts.sqlite").exists()
    assert not core_path.with_name(f".{core_path.name}.bootstrap.lock").exists()
    assert not core_path.with_name(f".{core_path.name}.bootstrap.json").exists()
