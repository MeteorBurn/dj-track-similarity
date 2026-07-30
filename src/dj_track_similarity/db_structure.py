"""Structural validation for the current SQLite databases.

The project intentionally does not assign application-level version numbers to
database layouts.  Compatibility is determined from the tables, columns,
indexes, triggers, and catalog binding that the current code actually needs.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping


DatabaseRole = Literal["core", "artifacts", "evaluation"]


@dataclass(frozen=True, slots=True)
class ColumnDifference:
    expected: tuple[str, ...]
    actual: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StructureReport:
    role: DatabaseRole
    missing_tables: tuple[str, ...]
    extra_tables: tuple[str, ...]
    column_mismatches: Mapping[str, ColumnDifference]
    missing_indexes: tuple[str, ...]
    extra_indexes: tuple[str, ...]
    missing_triggers: tuple[str, ...]
    extra_triggers: tuple[str, ...]
    definition_mismatches: tuple[str, ...]
    unexpected_views: tuple[str, ...]
    data_issues: tuple[str, ...]
    catalog_uuid: str | None

    @property
    def is_current(self) -> bool:
        return not (
            self.missing_tables
            or self.extra_tables
            or self.column_mismatches
            or self.missing_indexes
            or self.extra_indexes
            or self.missing_triggers
            or self.extra_triggers
            or self.definition_mismatches
            or self.unexpected_views
            or self.data_issues
        )


class DatabaseStructureError(RuntimeError):
    """Raised when a database requires the explicit migration command."""


@dataclass(frozen=True, slots=True)
class _ExpectedStructure:
    columns: Mapping[str, tuple[str, ...]]
    additional_tables: frozenset[str]
    indexes: frozenset[str]
    triggers: frozenset[str]
    catalog_table: str


def inspect_database_structure(
    connection: sqlite3.Connection,
    role: DatabaseRole,
) -> StructureReport:
    expected = _expected_structure(role)
    actual_tables = _named_objects(connection, "table")
    expected_tables = set(expected.columns) | set(expected.additional_tables)
    column_mismatches: dict[str, ColumnDifference] = {}
    for table, expected_columns in expected.columns.items():
        if table not in actual_tables:
            continue
        actual_columns = tuple(
            str(row[1])
            for row in connection.execute(f'PRAGMA table_info("{table}")')
        )
        if actual_columns != expected_columns:
            column_mismatches[table] = ColumnDifference(
                expected=expected_columns,
                actual=actual_columns,
            )

    actual_indexes = _named_objects(connection, "index")
    actual_triggers = _named_objects(connection, "trigger")
    actual_views = _named_objects(connection, "view")
    actual_definitions = _normalized_definitions(connection)
    expected_definitions = _expected_definitions(role)
    definition_mismatches = tuple(
        sorted(
            f"{object_type}:{name}"
            for (object_type, name), expected_sql in expected_definitions.items()
            if (actual_sql := actual_definitions.get((object_type, name))) is not None
            and actual_sql != expected_sql
        )
    )
    catalog_uuid, data_issues = _catalog_identity(
        connection,
        expected.catalog_table,
        table_exists=expected.catalog_table in actual_tables,
    )
    return StructureReport(
        role=role,
        missing_tables=tuple(sorted(expected_tables - actual_tables)),
        extra_tables=tuple(sorted(actual_tables - expected_tables)),
        column_mismatches=MappingProxyType(column_mismatches),
        missing_indexes=tuple(sorted(set(expected.indexes) - actual_indexes)),
        extra_indexes=tuple(sorted(actual_indexes - set(expected.indexes))),
        missing_triggers=tuple(sorted(set(expected.triggers) - actual_triggers)),
        extra_triggers=tuple(sorted(actual_triggers - set(expected.triggers))),
        definition_mismatches=definition_mismatches,
        unexpected_views=tuple(sorted(actual_views)),
        data_issues=data_issues,
        catalog_uuid=catalog_uuid,
    )


def require_current_structure(
    connection: sqlite3.Connection,
    role: DatabaseRole,
    database_path: str | Path,
) -> str:
    report = inspect_database_structure(connection, role)
    if report.is_current and report.catalog_uuid is not None:
        return report.catalog_uuid
    path = Path(database_path)
    details = _report_details(report)
    raise DatabaseStructureError(
        f"SQLite {role.title()} structure is not current at {path}: {details}. "
        f"Inspect the explicit migration first with: "
        f'dj-sim migrate-database --db "{path}" --dry-run'
    )


def _expected_structure(role: DatabaseRole) -> _ExpectedStructure:
    if role == "core":
        from . import db_schema

        return _ExpectedStructure(
            columns=db_schema._CORE_COLUMNS,
            additional_tables=frozenset(db_schema._FTS_SHADOW_TABLES),
            indexes=frozenset(db_schema._CORE_INDEXES),
            triggers=frozenset(db_schema._CORE_TRIGGERS),
            catalog_table="library_catalog",
        )
    if role == "artifacts":
        from . import db_artifacts

        return _ExpectedStructure(
            columns=db_artifacts._ARTIFACT_COLUMNS,
            additional_tables=frozenset(),
            indexes=frozenset(db_artifacts._ARTIFACT_INDEXES),
            triggers=frozenset(db_artifacts._ARTIFACT_TRIGGERS),
            catalog_table="storage_metadata",
        )
    if role == "evaluation":
        from . import db_evaluation_sidecar

        return _ExpectedStructure(
            columns=db_evaluation_sidecar._SIDECAR_COLUMNS,
            additional_tables=frozenset(),
            indexes=frozenset(db_evaluation_sidecar._SIDECAR_INDEXES),
            triggers=frozenset(db_evaluation_sidecar._SIDECAR_TRIGGERS),
            catalog_table="storage_metadata",
        )
    raise ValueError(f"unsupported database role: {role!r}")


def _named_objects(connection: sqlite3.Connection, object_type: str) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = ?
          AND name NOT LIKE 'sqlite_%'
        """,
        (object_type,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _normalized_definitions(
    connection: sqlite3.Connection,
) -> dict[tuple[str, str], str]:
    rows = connection.execute(
        """
        SELECT type, name, sql
        FROM sqlite_master
        WHERE type IN ('table', 'index', 'trigger', 'view')
          AND name NOT LIKE 'sqlite_%'
          AND sql IS NOT NULL
        ORDER BY type, name
        """
    ).fetchall()
    return {
        (str(object_type), str(name)): " ".join(str(sql).split())
        for object_type, name, sql in rows
    }


@lru_cache(maxsize=3)
def _expected_definitions(role: DatabaseRole) -> dict[tuple[str, str], str]:
    connection = sqlite3.connect(":memory:")
    try:
        if role == "core":
            from .db_ddl import create_core_schema

            create_core_schema(connection)
        elif role == "artifacts":
            from .db_artifacts import create_artifacts_sidecar_schema

            create_artifacts_sidecar_schema(
                connection,
                catalog_uuid="expected-artifacts-catalog",
            )
        elif role == "evaluation":
            from .db_evaluation_sidecar import create_evaluation_sidecar_schema

            create_evaluation_sidecar_schema(
                connection,
                catalog_uuid="expected-evaluation-catalog",
            )
        else:
            raise ValueError(f"unsupported database role: {role!r}")
        return _normalized_definitions(connection)
    finally:
        connection.close()


def _catalog_identity(
    connection: sqlite3.Connection,
    table: str,
    *,
    table_exists: bool,
) -> tuple[str | None, tuple[str, ...]]:
    if not table_exists:
        return None, (f"{table} is missing",)
    rows = connection.execute(
        f'SELECT singleton_id, catalog_uuid FROM "{table}"'
    ).fetchall()
    if len(rows) != 1 or int(rows[0][0]) != 1:
        return None, (f"{table} must contain exactly singleton_id=1",)
    catalog_uuid = str(rows[0][1]).strip()
    if not catalog_uuid:
        return None, (f"{table}.catalog_uuid must be non-empty",)
    return catalog_uuid, ()


def _report_details(report: StructureReport) -> str:
    parts: list[str] = []
    for name in (
        "missing_tables",
        "extra_tables",
        "missing_indexes",
        "extra_indexes",
        "missing_triggers",
        "extra_triggers",
        "definition_mismatches",
        "unexpected_views",
        "data_issues",
    ):
        values = getattr(report, name)
        if values:
            parts.append(f"{name.replace('_', ' ')}={list(values)}")
    if report.column_mismatches:
        parts.append(
            "column mismatches="
            + repr(
                {
                    table: {
                        "expected": list(difference.expected),
                        "actual": list(difference.actual),
                    }
                    for table, difference in report.column_mismatches.items()
                }
            )
        )
    return ", ".join(parts) or "catalog identity is unavailable"
