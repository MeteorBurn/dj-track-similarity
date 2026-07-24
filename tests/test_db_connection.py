from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing

from dj_track_similarity.db_connection import (
    connect_artifacts_database,
    connect_database,
    ensure_database_schema,
    write_lock_for_path,
)
from dj_track_similarity.db_storage import storage_database_paths


def test_runtime_connections_apply_pragmas_to_bound_v7_pair(tmp_path) -> None:
    core_path = tmp_path / "library.sqlite"
    catalog_uuid = ensure_database_schema(core_path)
    artifacts_path = storage_database_paths(core_path).artifacts

    with closing(
        connect_database(
            core_path,
            expected_catalog_uuid=catalog_uuid,
        )
    ) as core_connection, closing(
        connect_artifacts_database(
            artifacts_path,
            expected_catalog_uuid=catalog_uuid,
        )
    ) as artifacts_connection:
        core_row = core_connection.execute("SELECT 1 AS value").fetchone()
        artifacts_row = artifacts_connection.execute(
            "SELECT 1 AS value"
        ).fetchone()
        connection_facts = [
            (
                connection.execute("PRAGMA foreign_keys").fetchone()[0],
                connection.execute("PRAGMA busy_timeout").fetchone()[0],
                connection.execute("PRAGMA synchronous").fetchone()[0],
                connection.execute("PRAGMA temp_store").fetchone()[0],
                connection.execute("PRAGMA journal_mode").fetchone()[0],
            )
            for connection in (core_connection, artifacts_connection)
        ]

    assert isinstance(core_row, sqlite3.Row)
    assert isinstance(artifacts_row, sqlite3.Row)
    assert core_row["value"] == artifacts_row["value"] == 1
    for (
        foreign_keys,
        busy_timeout,
        synchronous,
        temp_store,
        journal_mode,
    ) in connection_facts:
        assert foreign_keys == 1
        assert busy_timeout >= 30_000
        assert synchronous == 1
        assert temp_store == 2
        assert str(journal_mode).lower() == "wal"


def test_write_lock_for_path_reuses_resolved_database_path(tmp_path) -> None:
    db_path = tmp_path / "data" / ".." / "library.sqlite"

    first = write_lock_for_path(db_path)
    second = write_lock_for_path(tmp_path / "library.sqlite")

    assert first is second


def test_write_lock_for_path_is_scoped_to_resolved_database_path(
    tmp_path,
) -> None:
    first = write_lock_for_path(tmp_path / "first.sqlite")
    second = write_lock_for_path(tmp_path / "second.sqlite")

    assert first is not second


def test_ensure_database_schema_creates_bound_v7_pair(tmp_path) -> None:
    core_path = tmp_path / "nested" / "library.sqlite"
    paths = storage_database_paths(core_path)
    lock = write_lock_for_path(core_path)

    catalog_uuid = ensure_database_schema(core_path, lock)

    assert str(uuid.UUID(catalog_uuid)) == catalog_uuid
    assert core_path.is_file()
    assert paths.artifacts.is_file()
    assert not paths.evaluation.exists()
    with closing(
        connect_database(
            core_path,
            expected_catalog_uuid=catalog_uuid,
        )
    ) as core_connection, closing(
        connect_artifacts_database(
            paths.artifacts,
            expected_catalog_uuid=catalog_uuid,
        )
    ) as artifacts_connection:
        core_version = core_connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        artifacts_version = artifacts_connection.execute(
            "PRAGMA user_version"
        ).fetchone()[0]
        stored_core_uuid = core_connection.execute(
            """
            SELECT catalog_uuid
            FROM library_catalog
            WHERE singleton_id = 1
            """
        ).fetchone()[0]
        stored_artifacts_uuid = artifacts_connection.execute(
            """
            SELECT catalog_uuid
            FROM storage_metadata
            WHERE singleton_id = 1
            """
        ).fetchone()[0]

    assert int(core_version) == 7
    assert int(artifacts_version) == 1
    assert stored_core_uuid == stored_artifacts_uuid == catalog_uuid
