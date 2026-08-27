"""Optional SQLite storage for evaluation-only records.

The sidecar is absent until an Evaluation command or API path writes to it.
It has no automatic migration or fixed-schema admission check: a new file is
created in the current shape, while an existing file is left untouched.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Collection
from contextlib import closing
from pathlib import Path

from .db_connection import _exclusive_file_lock


_SQLITE_BUSY_TIMEOUT_MILLISECONDS = 30_000


_DDL_EVALUATION_PROFILES = """
CREATE TABLE evaluation_profiles (
    profile_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_name TEXT    NOT NULL,
    profile_json TEXT    NOT NULL CHECK(json_valid(profile_json)),
    created_at   TEXT    NOT NULL
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
    PRIMARY KEY(session_id, position)
);
CREATE INDEX idx_search_seeds_identity
    ON search_session_seeds(track_uuid, session_id);
"""

_DDL_SEARCH_RESULT_EVENTS = """
CREATE TABLE search_result_events (
    search_result_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id             INTEGER NOT NULL REFERENCES search_sessions ON DELETE CASCADE,
    rank                   INTEGER NOT NULL CHECK(rank >= 0),
    track_id               INTEGER NOT NULL,
    track_uuid             TEXT    NOT NULL,
    total_score            REAL    NOT NULL,
    score_breakdown_json   TEXT    NOT NULL CHECK(json_valid(score_breakdown_json)),
    created_at             TEXT    NOT NULL,
    UNIQUE(session_id, rank)
);
CREATE INDEX idx_search_events_identity
    ON search_result_events(track_uuid, session_id);
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

_DELETE_CHUNK_SIZE = 800
_ALL_DDL = (
    _DDL_EVALUATION_PROFILES,
    _DDL_SEARCH_SESSIONS,
    _DDL_SEARCH_SESSION_SEEDS,
    _DDL_SEARCH_RESULT_EVENTS,
    _DDL_CALIBRATION_RUNS,
)


def create_evaluation_sidecar_schema(db: sqlite3.Connection | str | Path) -> None:
    """Create the current schema in a freshly chosen evaluation database."""

    if isinstance(db, (str, Path)):
        path = Path(db).expanduser().resolve(strict=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(path)) as connection:
            _configure_connection(connection)
            _apply_schema(connection)
        return
    _configure_connection(db)
    _apply_schema(db)


def connect_evaluation_sidecar(
    path: str | Path,
    *,
    create: bool = False,
) -> sqlite3.Connection | None:
    """Open the optional Evaluation database without creating it on reads."""

    resolved = Path(path).expanduser().resolve(strict=False)
    if create:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with _exclusive_file_lock(
            _creation_lock_path(resolved),
            description="Evaluation database creation lock",
        ):
            if not resolved.exists():
                create_evaluation_sidecar_schema(resolved)
    elif not resolved.is_file():
        return None
    if not resolved.is_file():
        raise ValueError(f"Evaluation database path must be a file: {resolved}")

    connection = sqlite3.connect(
        f"{resolved.as_uri()}?mode=rw",
        uri=True,
        timeout=_SQLITE_BUSY_TIMEOUT_MILLISECONDS / 1000,
    )
    try:
        _configure_connection(connection)
        _enforce_wal(connection)
        return connection
    except BaseException:
        connection.close()
        raise


# Sidecar rows name a track but cannot reference it: the catalog lives in another
# file, so SQLite cannot cascade the delete for us.
_EVALUATION_TRACK_TABLES = ("search_session_seeds", "search_result_events")


def delete_evaluation_track_rows(
    connection: sqlite3.Connection,
    track_ids: Collection[int],
) -> int:
    """Remove every evaluation row that names one of these tracks."""
    selected = sorted({int(track_id) for track_id in track_ids})
    if not selected:
        return 0
    deleted = 0
    for table in _EVALUATION_TRACK_TABLES:
        for index in range(0, len(selected), _DELETE_CHUNK_SIZE):
            chunk = selected[index : index + _DELETE_CHUNK_SIZE]
            placeholders = ",".join("?" for _ in chunk)
            cursor = connection.execute(
                f"DELETE FROM {table} WHERE track_id IN ({placeholders})",
                chunk,
            )
            deleted += int(cursor.rowcount or 0)
    return deleted


def _apply_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        connection.executescript("\n".join(("BEGIN IMMEDIATE;", *_ALL_DDL, "COMMIT;")))
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise


def _configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
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
