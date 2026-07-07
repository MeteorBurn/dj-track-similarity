from __future__ import annotations

import sqlite3

from dj_track_similarity.db_connection import connect_database, ensure_database_schema, write_lock_for_path
from dj_track_similarity.db_schema import CURRENT_SCHEMA_VERSION


def test_connect_database_applies_runtime_pragmas(tmp_path) -> None:
    db_path = tmp_path / "library.sqlite"

    with connect_database(db_path) as connection:
        row = connection.execute("SELECT 1 AS value").fetchone()
        foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
        temp_store = connection.execute("PRAGMA temp_store").fetchone()[0]

    assert isinstance(row, sqlite3.Row)
    assert row["value"] == 1
    assert foreign_keys == 1
    assert busy_timeout >= 30_000
    assert synchronous == 1
    assert temp_store == 2


def test_write_lock_for_path_reuses_resolved_database_path(tmp_path) -> None:
    db_path = tmp_path / "data" / ".." / "library.sqlite"

    first = write_lock_for_path(db_path)
    second = write_lock_for_path(tmp_path / "library.sqlite")

    assert first is second


def test_write_lock_for_path_is_scoped_to_resolved_database_path(tmp_path) -> None:
    first = write_lock_for_path(tmp_path / "first.sqlite")
    second = write_lock_for_path(tmp_path / "second.sqlite")

    assert first is not second


def test_ensure_database_schema_creates_parent_and_current_schema(tmp_path) -> None:
    db_path = tmp_path / "nested" / "library.sqlite"
    lock = write_lock_for_path(db_path)

    ensure_database_schema(db_path, lock)

    with connect_database(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert version == CURRENT_SCHEMA_VERSION
    assert str(journal_mode).lower() == "wal"
