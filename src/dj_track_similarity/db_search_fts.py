"""V7 track-search FTS maintenance.

The FTS index contains only text a person can reasonably search for. Analysis
hashes, model identifiers, numeric features, and binary payloads are excluded.
Missing tracks remain indexed so returning files can reuse the same row; search
queries apply ``tracks.missing_since IS NULL`` when selecting visible results.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable


SEARCH_MODES = {"like", "fts"}
_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
_BATCH_SIZE = 500


def fts_match_query(query: str) -> str:
    tokens = _TOKEN_PATTERN.findall(query.casefold())
    return " ".join(f'"{token}"' for token in tokens)


def _file_genres_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        items = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(items, list):
        return ""
    return ", ".join(str(item) for item in items if isinstance(item, str) and item)


def _maest_genres_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        items = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(items, list):
        return ""

    names: list[str] = []
    for item in items:
        if isinstance(item, str) and item:
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("genre_name")
            if isinstance(name, str) and name:
                names.append(name)
    return ", ".join(names)


def _track_search_row(
    connection: sqlite3.Connection,
    track_id: int,
) -> tuple[object, ...] | None:
    row = connection.execute(
        """
        SELECT
            t.track_id,
            t.file_path,
            ft.title,
            ft.artist,
            ft.album,
            ft.comment,
            ft.label,
            ft.catalog_number,
            ft.country,
            ft.isrc,
            ft.year,
            ft.track_number,
            ft.disc_number,
            ft.genres_json AS file_genres_json,
            ms.genres_json AS maest_genres_json
        FROM tracks AS t
        LEFT JOIN file_tags AS ft
          ON ft.track_id = t.track_id
        LEFT JOIN maest_scores AS ms
          ON ms.track_id = t.track_id
         AND ms.content_generation = t.content_generation
        WHERE t.track_id = ?
        """,
        (int(track_id),),
    ).fetchone()
    if row is None:
        return None

    values = tuple(row)
    return (
        int(values[0]),
        int(values[0]),
        values[1] or "",
        values[2] or "",
        values[3] or "",
        values[4] or "",
        values[5] or "",
        values[6] or "",
        values[7] or "",
        values[8] or "",
        values[9] or "",
        str(values[10]) if values[10] is not None else "",
        values[11] or "",
        values[12] or "",
        _file_genres_text(values[13]),
        _maest_genres_text(values[14]),
    )


def delete_track_search_fts(
    connection: sqlite3.Connection,
    track_id: int,
) -> None:
    """Delete one track from the live FTS index without committing."""

    connection.execute(
        "DELETE FROM track_search_fts WHERE rowid = ?",
        (int(track_id),),
    )


def upsert_track_search_fts(
    connection: sqlite3.Connection,
    track_id: int,
) -> None:
    """Refresh one track's human-text FTS row without committing."""

    delete_track_search_fts(connection, track_id)
    row = _track_search_row(connection, track_id)
    if row is None:
        return
    connection.execute(
        """
        INSERT INTO track_search_fts(
            rowid,
            track_id,
            file_path,
            title,
            artist,
            album,
            comment,
            label,
            catalog_number,
            country,
            isrc,
            year,
            track_number,
            disc_number,
            file_genres,
            maest_genres
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        row,
    )


def _track_id_batches(
    connection: sqlite3.Connection,
) -> Iterable[list[int]]:
    track_ids = [
        int(row[0])
        for row in connection.execute(
            "SELECT track_id FROM tracks ORDER BY track_id"
        )
    ]
    for start in range(0, len(track_ids), _BATCH_SIZE):
        yield track_ids[start : start + _BATCH_SIZE]


def rebuild_track_search_fts(connection: sqlite3.Connection) -> int:
    """Rebuild the v7 human-text FTS index atomically.

    If the caller already owns a transaction, the rebuild participates in that
    transaction. Otherwise it obtains a Core write reservation itself.
    """

    owns_transaction = not connection.in_transaction
    if owns_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        connection.execute("DELETE FROM track_search_fts")
        for batch in _track_id_batches(connection):
            for track_id in batch:
                upsert_track_search_fts(connection, track_id)
        count = int(
            connection.execute(
                "SELECT COUNT(*) FROM track_search_fts"
            ).fetchone()[0]
        )
        if owns_transaction:
            connection.commit()
        return count
    except BaseException:
        if owns_transaction and connection.in_transaction:
            connection.rollback()
        raise
