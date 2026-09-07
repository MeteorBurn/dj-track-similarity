"""Bootstrap and minimal identity checks for a single library database."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone


SQLITE_BUSY_TIMEOUT_SECONDS = 30


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def insert_library(
    connection: sqlite3.Connection,
    catalog_uuid: str,
    *,
    roots: Iterable[str] = (),
    created_at: str | None = None,
) -> str:
    """Initialize the one metadata row of a freshly created library."""

    if not isinstance(catalog_uuid, str):
        raise ValueError("catalog_uuid must be a string")
    clean_uuid = catalog_uuid.strip()
    if not clean_uuid:
        raise ValueError("catalog_uuid must be a non-empty string")
    clean_roots = _roots_json(roots)
    if connection.execute("SELECT COUNT(*) FROM library").fetchone()[0] != 0:
        raise RuntimeError("library is already initialized")
    timestamp = created_at or _utc_timestamp()
    connection.execute(
        """
        INSERT INTO library(
            singleton_id, catalog_uuid, created_at, updated_at, schema_version, roots_json
        )
        VALUES (1, ?, ?, ?, 1, ?)
        """,
        (clean_uuid, timestamp, timestamp, clean_roots),
    )
    return clean_uuid


def validate_library_schema(
    connection: sqlite3.Connection,
    *,
    expected_catalog_uuid: str | None = None,
    database_path: str = "<connected library database>",
) -> str:
    """Validate only the library identity needed to bind the open database.

    The application intentionally does not maintain an allow-list of tables,
    columns, indexes, or triggers.  New database capabilities may add schema
    without making existing libraries fail this open-time check.
    """

    try:
        rows = connection.execute(
            "SELECT singleton_id, catalog_uuid FROM library"
        ).fetchall()
    except sqlite3.Error as error:
        raise RuntimeError(
            f"Library metadata is unavailable in {database_path}: {error}"
        ) from error
    if len(rows) != 1 or int(rows[0][0]) != 1:
        raise RuntimeError("library must contain exactly singleton_id=1")
    catalog_uuid = str(rows[0][1]).strip()
    if not catalog_uuid:
        raise RuntimeError("library.catalog_uuid must be non-empty")
    if expected_catalog_uuid is not None and catalog_uuid != expected_catalog_uuid:
        raise RuntimeError("Library database belongs to another library catalog")
    return catalog_uuid


def _roots_json(roots: Iterable[str]) -> str:
    clean_roots: list[str] = []
    for root in roots:
        if not isinstance(root, str):
            raise ValueError("Library roots must be strings")
        clean_root = root.strip()
        if not clean_root:
            raise ValueError("Library roots must be non-empty strings")
        clean_roots.append(clean_root)
    return json.dumps(clean_roots, separators=(",", ":"), ensure_ascii=False)
