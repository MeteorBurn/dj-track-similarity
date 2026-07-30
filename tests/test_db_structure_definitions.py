from __future__ import annotations

import sqlite3

from dj_track_similarity.db_ddl import create_core_schema
from dj_track_similarity.db_schema import insert_library_catalog
from dj_track_similarity.db_structure import inspect_database_structure


def test_structure_reports_changed_definition_with_the_same_object_name() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_core_schema(connection)
        insert_library_catalog(connection, "catalog-for-definition-test")
        connection.execute("DROP INDEX idx_tracks_missing")
        connection.execute(
            "CREATE INDEX idx_tracks_missing ON tracks(track_id)"
        )

        report = inspect_database_structure(connection, "core")

        assert not report.is_current
        assert report.definition_mismatches == ("index:idx_tracks_missing",)
    finally:
        connection.close()
