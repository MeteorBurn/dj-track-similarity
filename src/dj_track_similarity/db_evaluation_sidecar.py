"""Evaluation sidecar schema DDL — ``library.evaluation.sqlite``.

This module is standalone — it does NOT import from any other dj_track_similarity
module so it can be used independently without circular dependencies.

The evaluation sidecar is OPTIONAL.  Most users will never have this file.
It is created only when the search-result recorder or calibration optimizer is
explicitly invoked.  Normal search operations must NOT auto-create it.

Tables (emission order matches FK dependency order):
  1.  storage_metadata        — singleton, catalog UUID + schema version binding
  2.  search_sessions         — one row per recorded search invocation
  3.  search_session_seeds    — seed tracks for each session
  4.  search_result_events    — ranked result rows for each session
  5.  calibration_runs        — optimizer calibration run records
  6.  evaluation_settings     — key-value settings for the evaluation subsystem

``PRAGMA user_version = 1`` is set at the end of
``create_evaluation_sidecar_schema()``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

SIDECAR_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# DDL strings — one per table/index group, in FK-safe emission order
# ---------------------------------------------------------------------------

_DDL_STORAGE_METADATA = """
CREATE TABLE storage_metadata (
    singleton_id   INTEGER PRIMARY KEY CHECK(singleton_id = 1),
    catalog_uuid   TEXT    NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
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
    content_generation INTEGER NOT NULL CHECK(content_generation >= 0),
    snapshot_state     TEXT    NOT NULL CHECK(snapshot_state IN ('current','missing')),
    CHECK((snapshot_state='current' AND content_generation >= 1) OR (snapshot_state='missing' AND content_generation = 0)),
    PRIMARY KEY(session_id, position)
);
"""

_DDL_SEARCH_RESULT_EVENTS = """
CREATE TABLE search_result_events (
    search_result_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id             INTEGER NOT NULL REFERENCES search_sessions ON DELETE CASCADE,
    rank                   INTEGER NOT NULL CHECK(rank >= 0),
    track_id               INTEGER NOT NULL,
    track_uuid             TEXT    NOT NULL,
    content_generation     INTEGER NOT NULL CHECK(content_generation >= 0),
    snapshot_state         TEXT    NOT NULL CHECK(snapshot_state IN ('current','missing')),
    total_score            REAL    NOT NULL,
    score_breakdown_json   TEXT    NOT NULL CHECK(json_valid(score_breakdown_json)),
    created_at             TEXT    NOT NULL,
    UNIQUE(session_id, rank),
    CHECK((snapshot_state='current' AND content_generation >= 1) OR (snapshot_state='missing' AND content_generation = 0))
);
CREATE INDEX idx_search_events_track_snapshot ON search_result_events(track_uuid, content_generation, session_id);
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
CREATE INDEX idx_calibration_profile_created ON calibration_runs(profile_name, search_mode, created_at, calibration_run_id);
"""

_DDL_EVALUATION_SETTINGS = """
CREATE TABLE evaluation_settings (
    setting_key TEXT NOT NULL PRIMARY KEY,
    value_json  TEXT NOT NULL CHECK(json_valid(value_json)),
    updated_at  TEXT NOT NULL
);
"""

# Ordered list of all DDL blocks to execute
_ALL_DDL: list[str] = [
    _DDL_STORAGE_METADATA,
    _DDL_SEARCH_SESSIONS,
    _DDL_SEARCH_SESSION_SEEDS,
    _DDL_SEARCH_RESULT_EVENTS,
    _DDL_CALIBRATION_RUNS,
    _DDL_EVALUATION_SETTINGS,
]

# ---------------------------------------------------------------------------
# Schema creation function
# ---------------------------------------------------------------------------


def create_evaluation_sidecar_schema(
    db: "sqlite3.Connection | str",
    catalog_uuid: Optional[str] = None,
) -> None:
    """Create the evaluation sidecar schema in *db*.

    Args:
        db: An open :class:`sqlite3.Connection` or a path string (including
            ``':memory:'``).  When a path string is given a new connection is
            opened, the schema is created, and the connection is closed.
        catalog_uuid: When provided, inserts the ``storage_metadata`` singleton
            row binding this sidecar to the given catalog UUID.  When ``None``
            the singleton row is not inserted (caller is responsible for
            inserting it before first use).

    The function sets ``PRAGMA user_version = 1``, enables WAL journal mode,
    ``synchronous = NORMAL``, and ``foreign_keys = ON``.

    This function must NOT be called at module import time.  The evaluation
    sidecar is optional — callers must invoke this function explicitly only
    when they intend to create or initialise the sidecar file.
    """
    if isinstance(db, str):
        conn = sqlite3.connect(db)
        try:
            _apply_sidecar_schema(conn, catalog_uuid=catalog_uuid)
        finally:
            conn.close()
    else:
        _apply_sidecar_schema(db, catalog_uuid=catalog_uuid)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_sidecar_schema(
    conn: sqlite3.Connection,
    catalog_uuid: Optional[str],
) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")

    for ddl_block in _ALL_DDL:
        for statement in _split_statements(ddl_block):
            conn.execute(statement)

    conn.execute(f"PRAGMA user_version = {SIDECAR_SCHEMA_VERSION}")

    if catalog_uuid is not None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn.execute(
            """
            INSERT INTO storage_metadata
                (singleton_id, catalog_uuid, schema_version, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?)
            """,
            (catalog_uuid, SIDECAR_SCHEMA_VERSION, now, now),
        )

    conn.commit()


def _split_statements(ddl: str) -> list[str]:
    """Split a DDL block into individual statements, stripping SQL comments."""
    lines = []
    for line in ddl.splitlines():
        stripped = line.split("--")[0]
        lines.append(stripped)
    cleaned = "\n".join(lines)
    statements = [s.strip() for s in cleaned.split(";")]
    return [s for s in statements if s]
