from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Iterable

from dj_track_similarity.track_models import TrackIdentity

from . import report_selection as report_selection_module
from . import values as values_module


def cleanup_rhythm_lab_database(
    rhythm_lab_db: Path | None,
    identities: Iterable[TrackIdentity],
) -> int:
    selected_identities = report_selection_module._unique_identities(identities)
    if not selected_identities or rhythm_lab_db is None:
        return 0
    selected_db = Path(rhythm_lab_db).expanduser().resolve(strict=False)
    if not selected_db.exists():
        return 0
    deleted_rows = 0
    connection = sqlite3.connect(selected_db)
    try:
        connection.execute("PRAGMA busy_timeout = 30000")
        table_names = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        ]
        for table_name in table_names:
            quoted_table = _quote_sqlite_identifier(table_name)
            columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({quoted_table})").fetchall()}
            if not _has_identity_columns(columns):
                continue
            for chunk in values_module._chunks(list(selected_identities), 200):
                identity_sql, parameters = _identity_predicate(chunk)
                cursor = connection.execute(
                    f"DELETE FROM {quoted_table} WHERE {identity_sql}",
                    parameters,
                )
                deleted_rows += int(cursor.rowcount if cursor.rowcount is not None else 0)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()
    return deleted_rows


def _quote_sqlite_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _has_identity_columns(columns: Iterable[str]) -> bool:
    return {
        "catalog_uuid",
        "track_uuid",
    }.issubset(set(columns))


def _identity_predicate(
    identities: list[TrackIdentity],
) -> tuple[str, tuple[object, ...]]:
    if not identities:
        raise ValueError("At least one identity is required")
    predicates: list[str] = []
    parameters: list[object] = []
    for identity in identities:
        predicates.append(
            "(catalog_uuid = ? AND track_uuid = ?)"
        )
        parameters.extend(
            (
                identity.catalog_uuid,
                identity.track_uuid,
            )
        )
    return " OR ".join(predicates), tuple(parameters)
