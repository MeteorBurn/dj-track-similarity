from __future__ import annotations

import re
import sqlite3


SEARCH_MODES = {"like", "fts"}
_TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)


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
