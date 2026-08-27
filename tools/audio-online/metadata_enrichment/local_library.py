"""Read local genre evidence without modifying a library database."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from .models import LocalEvidence, TrackInput


def read_local_evidence(db_path: Path, track: TrackInput) -> LocalEvidence:
    """Return tags and at most three MAEST genres from one unambiguous local track."""

    database_uri = db_path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as connection:
        connection.row_factory = sqlite3.Row
        row = _find_by_path(connection, track) if track.file_path else _find_by_metadata(connection, track)
    if row is None:
        return LocalEvidence()
    tags = tuple(value for value in json.loads(row["tags_json"] or "[]") if isinstance(value, str))
    maest = tuple(
        (item["label"], float(item["score"]))
        for item in json.loads(row["maest_json"] or "[]")[:3]
        if isinstance(item, dict) and isinstance(item.get("label"), str) and isinstance(item.get("score"), (int, float))
    )
    return LocalEvidence(file_tags=tags, maest=maest, matched_path=row["file_path"])


def _find_by_path(connection: sqlite3.Connection, track: TrackInput) -> sqlite3.Row | None:
    assert track.file_path is not None
    path = str(track.file_path)
    path_variants = tuple(dict.fromkeys((path, path.replace("\\", "/"), path.replace("/", "\\"))))
    placeholders = ", ".join("?" for _ in path_variants)
    sql = f"""
        SELECT tracks.file_path, tags.genres_json AS tags_json, maest_genres.genres_json AS maest_json
        FROM tracks
        LEFT JOIN tags ON tags.track_id = tracks.track_id
        LEFT JOIN maest_genres ON maest_genres.track_id = tracks.track_id
        WHERE tracks.file_path IN ({placeholders})
        ORDER BY CASE tracks.file_path
            WHEN ? THEN 0
            WHEN ? THEN 1
            ELSE 2
        END
        LIMIT 1
        """
    return connection.execute(sql, (*path_variants, path, path.replace("\\", "/"))).fetchone()


def _find_by_metadata(connection: sqlite3.Connection, track: TrackInput) -> sqlite3.Row | None:
    if not track.artist or not track.title:
        return None
    rows = connection.execute(
        """
        SELECT tracks.file_path, tags.genres_json AS tags_json, maest_genres.genres_json AS maest_json
        FROM tracks
        JOIN tags ON tags.track_id = tracks.track_id
        LEFT JOIN maest_genres ON maest_genres.track_id = tracks.track_id
        WHERE lower(trim(tags.artist)) = lower(trim(?))
          AND lower(trim(tags.title)) = lower(trim(?))
        LIMIT 2
        """,
        (track.artist, track.title),
    ).fetchall()
    return rows[0] if len(rows) == 1 else None
