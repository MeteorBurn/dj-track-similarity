"""Optional v7 Evaluation sidecar schema, validation, and connection helpers.

The sidecar is deliberately absent for users who never record evaluation
sessions, calibration runs, or evaluation-specific settings.  Merely importing
this module, opening a library, searching, or reading evaluation state must not
create the file.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .db_connection import _exclusive_file_lock


SIDECAR_SCHEMA_VERSION = 1
_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 30_000


_DDL_STORAGE_METADATA = """
CREATE TABLE storage_metadata (
    singleton_id   INTEGER PRIMARY KEY CHECK(singleton_id = 1),
    catalog_uuid   TEXT    NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
CREATE TRIGGER storage_metadata_singleton_insert
BEFORE INSERT ON storage_metadata
WHEN EXISTS(SELECT 1 FROM storage_metadata)
BEGIN
    SELECT RAISE(ABORT, 'storage_metadata is immutable');
END;
CREATE TRIGGER storage_metadata_immutable_update
BEFORE UPDATE ON storage_metadata
BEGIN
    SELECT RAISE(ABORT, 'storage_metadata is immutable');
END;
CREATE TRIGGER storage_metadata_immutable_delete
BEFORE DELETE ON storage_metadata
BEGIN
    SELECT RAISE(ABORT, 'storage_metadata is immutable');
END;
"""

_DDL_SEARCH_SESSIONS = """
CREATE TABLE search_sessions (
    session_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    mode         TEXT    NOT NULL,
    request_json TEXT    NOT NULL CHECK(json_valid(request_json)),
    created_at   TEXT    NOT NULL
);
CREATE INDEX idx_search_sessions_created ON search_sessions(created_at, session_id);
"""

_DDL_SEARCH_SESSION_SEEDS = """
CREATE TABLE search_session_seeds (
    session_id         INTEGER NOT NULL REFERENCES search_sessions ON DELETE CASCADE,
    position           INTEGER NOT NULL CHECK(position >= 0),
    track_id           INTEGER NOT NULL,
    track_uuid         TEXT    NOT NULL,
    content_generation INTEGER NOT NULL CHECK(content_generation >= 1),
    PRIMARY KEY(session_id, position)
);
CREATE INDEX idx_search_seeds_identity
    ON search_session_seeds(track_uuid, content_generation, session_id);
"""

_DDL_SEARCH_RESULT_EVENTS = """
CREATE TABLE search_result_events (
    search_result_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id             INTEGER NOT NULL REFERENCES search_sessions ON DELETE CASCADE,
    rank                   INTEGER NOT NULL CHECK(rank >= 0),
    track_id               INTEGER NOT NULL,
    track_uuid             TEXT    NOT NULL,
    content_generation     INTEGER NOT NULL CHECK(content_generation >= 1),
    total_score            REAL    NOT NULL,
    score_breakdown_json   TEXT    NOT NULL CHECK(json_valid(score_breakdown_json)),
    created_at             TEXT    NOT NULL,
    UNIQUE(session_id, rank)
);
CREATE INDEX idx_search_events_identity
    ON search_result_events(track_uuid, content_generation, session_id);
"""

_DDL_CALIBRATION_RUNS = """
CREATE TABLE calibration_runs (
    calibration_run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name       TEXT    NOT NULL,
    search_mode        TEXT    NOT NULL,
    config_json        TEXT    NOT NULL CHECK(json_valid(config_json)),
    metrics_json       TEXT    NOT NULL CHECK(json_valid(metrics_json)),
    created_at         TEXT    NOT NULL
);
CREATE INDEX idx_calibration_profile_created
    ON calibration_runs(profile_name, search_mode, created_at, calibration_run_id);
"""

_DDL_EVALUATION_SETTINGS = """
CREATE TABLE evaluation_settings (
    setting_key TEXT NOT NULL PRIMARY KEY,
    value_json  TEXT NOT NULL CHECK(json_valid(value_json)),
    updated_at  TEXT NOT NULL
);
"""

_ALL_DDL: tuple[str, ...] = (
    _DDL_STORAGE_METADATA,
    _DDL_SEARCH_SESSIONS,
    _DDL_SEARCH_SESSION_SEEDS,
    _DDL_SEARCH_RESULT_EVENTS,
    _DDL_CALIBRATION_RUNS,
    _DDL_EVALUATION_SETTINGS,
)

_EVALUATION_COLUMNS: dict[str, tuple[str, ...]] = {
    "storage_metadata": (
        "singleton_id",
        "catalog_uuid",
        "schema_version",
        "created_at",
        "updated_at",
    ),
    "search_sessions": ("session_id", "mode", "request_json", "created_at"),
    "search_session_seeds": (
        "session_id",
        "position",
        "track_id",
        "track_uuid",
        "content_generation",
    ),
    "search_result_events": (
        "search_result_event_id",
        "session_id",
        "rank",
        "track_id",
        "track_uuid",
        "content_generation",
        "total_score",
        "score_breakdown_json",
        "created_at",
    ),
    "calibration_runs": (
        "calibration_run_id",
        "profile_name",
        "search_mode",
        "config_json",
        "metrics_json",
        "created_at",
    ),
    "evaluation_settings": ("setting_key", "value_json", "updated_at"),
}

_EVALUATION_INDEXES = {
    "idx_search_sessions_created",
    "idx_search_seeds_identity",
    "idx_search_events_identity",
    "idx_calibration_profile_created",
}

_EVALUATION_TRIGGERS = {
    "storage_metadata_singleton_insert",
    "storage_metadata_immutable_update",
    "storage_metadata_immutable_delete",
}


def create_evaluation_sidecar_schema(
    db: sqlite3.Connection | str | Path,
    *,
    catalog_uuid: str,
) -> None:
    """Create one empty Evaluation sidecar bound to ``catalog_uuid``."""

    clean_catalog_uuid = _required_catalog_uuid(catalog_uuid)
    if isinstance(db, (str, Path)):
        path = Path(db).expanduser().resolve(strict=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
        try:
            _configure_connection(connection)
            _apply_sidecar_schema(connection, catalog_uuid=clean_catalog_uuid)
            _enforce_wal(connection)
        finally:
            connection.close()
        return
    _configure_connection(db)
    _apply_sidecar_schema(db, catalog_uuid=clean_catalog_uuid)


def connect_evaluation_sidecar(
    path: str | Path,
    *,
    expected_catalog_uuid: str,
    create: bool = False,
) -> sqlite3.Connection | None:
    """Open and exactly validate the optional sidecar.

    ``None`` is returned when the file is absent and ``create`` is false.  The
    create path is the only path in this module that may materialise the file.
    """

    clean_catalog_uuid = _required_catalog_uuid(expected_catalog_uuid)
    resolved = Path(path).expanduser().resolve(strict=False)
    if create:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with _exclusive_file_lock(
            _creation_lock_path(resolved),
            description="Evaluation database creation lock",
        ):
            if not resolved.is_file():
                create_evaluation_sidecar_schema(
                    resolved,
                    catalog_uuid=clean_catalog_uuid,
                )
    elif not resolved.is_file():
        return None

    connection = sqlite3.connect(
        f"{resolved.as_uri()}?mode=rw",
        uri=True,
        timeout=_SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000,
    )
    try:
        _configure_connection(connection)
        validate_evaluation_sidecar_schema(
            connection,
            expected_catalog_uuid=clean_catalog_uuid,
        )
        _enforce_wal(connection)
    except BaseException:
        connection.close()
        raise
    return connection


def validate_evaluation_sidecar_schema(
    connection: sqlite3.Connection,
    *,
    expected_catalog_uuid: str | None = None,
) -> str:
    """Validate the complete schema definition and Core catalog binding."""

    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != SIDECAR_SCHEMA_VERSION:
        raise RuntimeError(
            f"SQLite Evaluation schema version {version} is not supported; "
            f"expected {SIDECAR_SCHEMA_VERSION}"
        )

    actual_views = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        )
    }
    if actual_views:
        raise RuntimeError(
            f"SQLite Evaluation contains unexpected views: {sorted(actual_views)}"
        )

    actual_tables = _user_tables(connection)
    expected_tables = set(_EVALUATION_COLUMNS)
    if actual_tables != expected_tables:
        raise RuntimeError(
            "SQLite Evaluation table set mismatch; "
            f"missing={sorted(expected_tables - actual_tables)}, "
            f"extra={sorted(actual_tables - expected_tables)}"
        )

    for table, expected_columns in _EVALUATION_COLUMNS.items():
        actual_columns = tuple(
            str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
        )
        if actual_columns != expected_columns:
            raise RuntimeError(
                f"SQLite Evaluation columns mismatch for {table}; "
                f"expected={list(expected_columns)}, actual={list(actual_columns)}"
            )

    actual_indexes = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if actual_indexes != _EVALUATION_INDEXES:
        raise RuntimeError(
            "SQLite Evaluation index set mismatch; "
            f"missing={sorted(_EVALUATION_INDEXES - actual_indexes)}, "
            f"extra={sorted(actual_indexes - _EVALUATION_INDEXES)}"
        )

    actual_triggers = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )
    }
    if actual_triggers != _EVALUATION_TRIGGERS:
        raise RuntimeError(
            "SQLite Evaluation trigger set mismatch; "
            f"missing={sorted(_EVALUATION_TRIGGERS - actual_triggers)}, "
            f"extra={sorted(actual_triggers - _EVALUATION_TRIGGERS)}"
        )

    actual_definitions = _normalized_schema_definitions(connection)
    expected_definitions = _expected_schema_definitions()
    if actual_definitions != expected_definitions:
        raise RuntimeError(
            "SQLite Evaluation schema definition fingerprint mismatch; "
            f"expected={_schema_definition_fingerprint(expected_definitions)}, "
            f"actual={_schema_definition_fingerprint(actual_definitions)}"
        )

    metadata_rows = connection.execute(
        "SELECT singleton_id, catalog_uuid, schema_version FROM storage_metadata"
    ).fetchall()
    if len(metadata_rows) != 1 or int(metadata_rows[0][0]) != 1:
        raise RuntimeError("storage_metadata must contain exactly singleton_id=1")
    catalog_uuid = str(metadata_rows[0][1]).strip()
    if not catalog_uuid:
        raise RuntimeError("storage_metadata.catalog_uuid must be non-empty")
    if int(metadata_rows[0][2]) != SIDECAR_SCHEMA_VERSION:
        raise RuntimeError(
            "storage_metadata.schema_version does not match PRAGMA user_version"
        )
    if expected_catalog_uuid is not None and catalog_uuid != _required_catalog_uuid(
        expected_catalog_uuid
    ):
        raise RuntimeError("Evaluation database belongs to another library catalog")

    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise RuntimeError(
            f"SQLite Evaluation foreign-key violations: {foreign_key_errors[:5]}"
        )
    return catalog_uuid


def _apply_sidecar_schema(
    connection: sqlite3.Connection,
    *,
    catalog_uuid: str,
) -> None:
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA foreign_keys = ON")
    script = "\n".join(
        (
            "BEGIN IMMEDIATE;",
            *_ALL_DDL,
            f"PRAGMA user_version = {SIDECAR_SCHEMA_VERSION};",
        )
    )
    try:
        connection.executescript(script)
        timestamp = _utc_timestamp()
        connection.execute(
            """
            INSERT INTO storage_metadata(
                singleton_id, catalog_uuid, schema_version, created_at, updated_at
            )
            VALUES (1, ?, ?, ?, ?)
            """,
            (
                catalog_uuid,
                SIDECAR_SCHEMA_VERSION,
                timestamp,
                timestamp,
            ),
        )
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise


def _configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA recursive_triggers = ON")
    connection.execute(f"PRAGMA busy_timeout = {_SQLITE_BUSY_TIMEOUT_MILLISECONDS}")
    connection.execute("PRAGMA synchronous = NORMAL")


def _enforce_wal(connection: sqlite3.Connection) -> None:
    journal_mode_row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
    journal_mode = "" if journal_mode_row is None else str(journal_mode_row[0]).lower()
    if journal_mode != "wal":
        raise RuntimeError(
            "SQLite Evaluation database could not enter WAL journal mode; "
            f"got {journal_mode!r}"
        )


def _creation_lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.create.lock")


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }


def _normalized_schema_definitions(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, str, str], ...]:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE type IN ('table', 'index', 'trigger', 'view')
          AND name NOT LIKE 'sqlite_%'
          AND sql IS NOT NULL
        ORDER BY type, name
        """
    ).fetchall()
    return tuple(
        (
            str(object_type),
            str(name),
            str(table_name),
            " ".join(str(sql).split()),
        )
        for object_type, name, table_name, sql in rows
    )


def _schema_definition_fingerprint(
    definitions: tuple[tuple[str, str, str, str], ...],
) -> str:
    payload = json.dumps(
        definitions,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@lru_cache(maxsize=1)
def _expected_schema_definitions() -> tuple[tuple[str, str, str, str], ...]:
    connection = sqlite3.connect(":memory:")
    try:
        create_evaluation_sidecar_schema(
            connection,
            catalog_uuid="expected-evaluation-catalog",
        )
        return _normalized_schema_definitions(connection)
    finally:
        connection.close()


def _required_catalog_uuid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("catalog_uuid must be a string")
    clean_value = value.strip()
    if not clean_value:
        raise ValueError("catalog_uuid must be a non-empty string")
    return clean_value


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
