from __future__ import annotations

import json
import re
import sqlite3


SEARCH_MODES = {"like", "fts"}
_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)

_BATCH_SIZE = 500


def normalize_search_mode(search_mode: str) -> str:
    mode = (search_mode or "like").strip().lower()
    if mode not in SEARCH_MODES:
        raise ValueError(f"Unknown track search mode: {search_mode}")
    return mode


def fts_match_query(query: str) -> str:
    tokens = _TOKEN_PATTERN.findall(query.casefold())
    return " ".join(f'"{token}"' for token in tokens)


def create_track_search_fts(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS track_search_fts USING fts5(
            track_id UNINDEXED,
            search_text,
            tokenize = 'unicode61'
        )
        """
    )


def upsert_track_search_fts(connection: sqlite3.Connection, track_id: int) -> None:
    connection.execute("DELETE FROM track_search_fts WHERE rowid = ?", (int(track_id),))
    connection.execute(
        """
        INSERT INTO track_search_fts(rowid, track_id, search_text)
        SELECT
            t.id,
            t.id,
            COALESCE(t.artist, '') || ' ' ||
            COALESCE(t.title, '') || ' ' ||
            COALESCE(t.album, '') || ' ' ||
            t.path || ' ' ||
            t.metadata_json
        FROM tracks t
        WHERE t.id = ?
        """,
        (int(track_id),),
    )


def rebuild_track_search_fts(connection: sqlite3.Connection) -> int:
    connection.execute("DELETE FROM track_search_fts")
    connection.execute(
        """
        INSERT INTO track_search_fts(rowid, track_id, search_text)
        SELECT
            t.id,
            t.id,
            COALESCE(t.artist, '') || ' ' ||
            COALESCE(t.title, '') || ' ' ||
            COALESCE(t.album, '') || ' ' ||
            t.path || ' ' ||
            t.metadata_json
        FROM tracks t
        ORDER BY t.id
        """
    )
    return int(connection.execute("SELECT COUNT(*) FROM track_search_fts").fetchone()[0])


# ---------------------------------------------------------------------------
# v7 FTS rebuild — human-readable sources only
# ---------------------------------------------------------------------------

def _parse_file_genres(genres_json: str | None) -> str:
    """Parse a JSON array of genre strings from file_tags.genres_json.

    Returns a comma-joined string of genre names, or empty string on failure.
    """
    if not genres_json:
        return ""
    try:
        items = json.loads(genres_json)
        if isinstance(items, list):
            return ", ".join(str(g) for g in items if g)
    except (json.JSONDecodeError, TypeError):
        pass
    return ""


def _parse_maest_genres(genres_json: str | None) -> str:
    """Parse a JSON array of MAEST genre objects from maest_scores.genres_json.

    Each element is expected to be an object with a ``genre_name`` key.
    Returns a comma-joined string of genre names, or empty string on failure.
    """
    if not genres_json:
        return ""
    try:
        items = json.loads(genres_json)
        if isinstance(items, list):
            names = []
            for item in items:
                if isinstance(item, dict):
                    name = item.get("genre_name")
                    if name:
                        names.append(str(name))
                elif isinstance(item, str) and item:
                    # Tolerate plain-string arrays too
                    names.append(item)
            return ", ".join(names)
    except (json.JSONDecodeError, TypeError):
        pass
    return ""


def rebuild_track_search_fts_v7(core_conn: sqlite3.Connection) -> int:
    """Rebuild ``track_search_fts`` for a v7 Core schema database.

    Populates the FTS5 virtual table exclusively from human-readable sources:

    * ``tracks.file_path``
    * ``file_tags``: title, artist, album, comment, label, catalog_number,
      country, isrc, year (as text), track_number, disc_number
    * ``file_tags.genres_json`` — JSON array of genre strings → ``file_genres``
    * ``maest_scores.genres_json`` — JSON array of ``{genre_name, ...}`` objects
      → ``maest_genres``

    Numeric SONARA features, contract hashes, model IDs, and BLOB content are
    intentionally excluded.

    The rebuild runs inside a single transaction using batched deletes + inserts
    so that a partial failure leaves the table in a consistent state.

    Args:
        core_conn: An open :class:`sqlite3.Connection` to a v7 Core database.

    Returns:
        The number of rows inserted into ``track_search_fts``.
    """
    # Fetch all track IDs ordered for deterministic batching
    track_ids: list[int] = [
        row[0]
        for row in core_conn.execute("SELECT track_id FROM tracks ORDER BY track_id").fetchall()
    ]

    with core_conn:
        # Clear existing FTS content in one shot
        core_conn.execute("DELETE FROM track_search_fts")

        for batch_start in range(0, len(track_ids), _BATCH_SIZE):
            batch = track_ids[batch_start : batch_start + _BATCH_SIZE]
            placeholders = ",".join("?" * len(batch))

            rows = core_conn.execute(
                f"""
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
                    ft.genres_json        AS file_genres_json,
                    ms.genres_json        AS maest_genres_json
                FROM tracks t
                LEFT JOIN file_tags   ft ON ft.track_id = t.track_id
                LEFT JOIN maest_scores ms ON ms.track_id = t.track_id
                WHERE t.track_id IN ({placeholders})
                ORDER BY t.track_id
                """,
                batch,
            ).fetchall()

            insert_rows = []
            for row in rows:
                (
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
                    file_genres_json,
                    maest_genres_json,
                ) = row

                file_genres = _parse_file_genres(file_genres_json)
                maest_genres = _parse_maest_genres(maest_genres_json)
                year_text = str(year) if year is not None else ""

                insert_rows.append((
                    track_id,   # rowid
                    track_id,   # track_id UNINDEXED
                    file_path or "",
                    title or "",
                    artist or "",
                    album or "",
                    comment or "",
                    label or "",
                    catalog_number or "",
                    country or "",
                    isrc or "",
                    year_text,
                    track_number or "",
                    disc_number or "",
                    file_genres,
                    maest_genres,
                ))

            core_conn.executemany(
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
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                insert_rows,
            )

    return int(core_conn.execute("SELECT COUNT(*) FROM track_search_fts").fetchone()[0])
