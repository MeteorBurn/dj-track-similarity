from __future__ import annotations

import sqlite3

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_artifacts import create_artifacts_sidecar_schema
from dj_track_similarity.db_ddl import create_core_schema
from dj_track_similarity.db_evaluation_sidecar import (
    create_evaluation_sidecar_schema,
    validate_evaluation_sidecar_schema,
)
from dj_track_similarity.db_schema import insert_library_catalog
from dj_track_similarity.db_structure import (
    DatabaseStructureError,
    inspect_database_structure,
)


def test_core_structure_does_not_use_sqlite_user_version() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_core_schema(connection)
        insert_library_catalog(connection, "catalog-for-structure-test")
        connection.execute("PRAGMA user_version = 999")

        report = inspect_database_structure(connection, "core")

        assert report.is_current
        assert report.catalog_uuid == "catalog-for-structure-test"
    finally:
        connection.close()


def test_artifacts_structure_has_no_project_schema_version() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_artifacts_sidecar_schema(
            connection,
            catalog_uuid="catalog-for-structure-test",
        )
        connection.execute("PRAGMA user_version = 999")

        report = inspect_database_structure(connection, "artifacts")
        metadata_columns = tuple(
            str(row[1])
            for row in connection.execute("PRAGMA table_info(storage_metadata)")
        )

        assert report.is_current
        assert report.catalog_uuid == "catalog-for-structure-test"
        assert "schema_version" not in metadata_columns
    finally:
        connection.close()


def test_evaluation_structure_ignores_sqlite_user_version() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_evaluation_sidecar_schema(
            connection,
            catalog_uuid="catalog-for-structure-test",
        )
        connection.execute("PRAGMA user_version = 999")

        assert (
            validate_evaluation_sidecar_schema(
                connection,
                expected_catalog_uuid="catalog-for-structure-test",
            )
            == "catalog-for-structure-test"
        )
        report = inspect_database_structure(connection, "evaluation")
        metadata_columns = tuple(
            str(row[1])
            for row in connection.execute("PRAGMA table_info(storage_metadata)")
        )

        assert report.is_current
        assert report.catalog_uuid == "catalog-for-structure-test"
        assert metadata_columns == (
            "singleton_id",
            "catalog_uuid",
            "created_at",
            "updated_at",
        )
    finally:
        connection.close()


def test_old_structure_fails_with_explicit_migration_command(tmp_path) -> None:
    path = tmp_path / "old-core.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE legacy_tracks(track_id INTEGER PRIMARY KEY)")
        connection.execute("PRAGMA user_version = 6")

    with pytest.raises(
        DatabaseStructureError,
        match=r"dj-sim migrate-database --db",
    ):
        LibraryDatabase(path)
