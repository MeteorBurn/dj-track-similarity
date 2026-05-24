from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import sqlite3

import numpy as np

from dj_track_similarity.database import DEFAULT_EMBEDDING_KEY, LibraryDatabase
from dj_track_similarity.db_schema import TRACK_SELECT_FIELDS, TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR
from dj_track_similarity.models import Track


REQUIRED_TRACK_COLUMNS = {
    "id",
    "path",
    "size",
    "mtime",
    "artist",
    "title",
    "album",
    "bpm",
    "musical_key",
    "energy",
    "duration",
    "metadata_json",
}
REQUIRED_EMBEDDING_COLUMNS = {"track_id", "embedding_key", "model_name", "dim", "vector"}


class SourceDatabase:
    """Read-only view over a main dj-track-similarity SQLite database."""

    def __init__(self, path: str | Path) -> None:
        selected = Path(_clean_path_text(path)).expanduser()
        if not str(selected).strip() or not selected.name:
            raise ValueError("Source database path is required")
        if not selected.exists():
            raise FileNotFoundError(f"Source database does not exist: {selected}")
        if not selected.is_file():
            raise ValueError("Source database path must be an existing file")
        self.path = selected.resolve(strict=True)
        self._validate_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA query_only = ON")
        return connection

    def count_tracks(self) -> int:
        with self.connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])

    def count_embeddings(self, embedding_key: str) -> int:
        with self.connect() as connection:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM embeddings WHERE embedding_key = ?",
                    (embedding_key,),
                ).fetchone()[0]
            )

    def get_track(self, track_id: int) -> Track:
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE t.id = ?
                """,
                (DEFAULT_EMBEDDING_KEY, track_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown track id: {track_id}")
        return LibraryDatabase._row_to_track(row)

    def tracks_by_ids(self, track_ids: Iterable[int]) -> dict[int, Track]:
        unique_ids = list(dict.fromkeys(int(track_id) for track_id in track_ids))
        if not unique_ids:
            return {}
        result: dict[int, Track] = {}
        with self.connect() as connection:
            for start in range(0, len(unique_ids), 900):
                chunk = unique_ids[start : start + 900]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""
                    SELECT {TRACK_SELECT_FIELDS}
                    FROM tracks t
                    LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                    WHERE t.id IN ({placeholders})
                    """,
                    (DEFAULT_EMBEDDING_KEY, *chunk),
                ).fetchall()
                for row in rows:
                    track = LibraryDatabase._row_to_track(row)
                    result[int(track.id)] = track
        return result

    def list_tracks(self) -> list[Track]:
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                """,
                (DEFAULT_EMBEDDING_KEY,),
            ).fetchall()
        return [LibraryDatabase._row_to_track(row) for row in rows]

    def list_tracks_page(
        self,
        *,
        labels_db_path: str | Path,
        query: str = "",
        syncopated: str = "all",
        label: str = "all",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, object]:
        where_parts, params = _track_page_filter_sql(query=query, syncopated=syncopated, label=label)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        labels_uri = f"file:{Path(labels_db_path).expanduser().resolve(strict=False).as_posix()}?mode=ro"
        with self.connect() as connection:
            connection.execute("ATTACH DATABASE ? AS labels", (labels_uri,))
            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM tracks t
                    LEFT JOIN labels.rhythm_labels rl ON rl.source_track_id = t.id
                    {where_sql}
                    """,
                    params,
                ).fetchone()[0]
            )
            rows = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS},
                       rl.label AS rhythm_label,
                       emert.track_id IS NOT NULL AS has_mert_embedding,
                       emaest.track_id IS NOT NULL AS has_maest_embedding
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                LEFT JOIN embeddings emert ON emert.track_id = t.id AND emert.embedding_key = 'mert'
                LEFT JOIN embeddings emaest ON emaest.track_id = t.id AND emaest.embedding_key = 'maest'
                LEFT JOIN labels.rhythm_labels rl ON rl.source_track_id = t.id
                {where_sql}
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                LIMIT ? OFFSET ?
                """,
                (DEFAULT_EMBEDDING_KEY, *params, bounded_limit, bounded_offset),
            ).fetchall()
        return {
            "items": [_track_page_item(row) for row in rows],
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    def embedding_track_ids(self, embedding_key: str) -> set[int]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT track_id FROM embeddings WHERE embedding_key = ?",
                (embedding_key,),
            ).fetchall()
        return {int(row["track_id"]) for row in rows}

    def load_embedding_matrix(self, embedding_key: str = DEFAULT_EMBEDDING_KEY) -> tuple[list[Track], np.ndarray]:
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR}
                FROM tracks t
                JOIN embeddings e ON e.track_id = t.id
                WHERE e.embedding_key = ?
                ORDER BY e.track_id
                """,
                (embedding_key,),
            ).fetchall()
        if not rows:
            return [], np.zeros((0, 0), dtype=np.float32)
        tracks = [LibraryDatabase._row_to_track(row, include_metadata=False) for row in rows]
        vectors = [np.frombuffer(row["vector"], dtype=np.float32).copy() for row in rows]
        return tracks, np.vstack(vectors).astype(np.float32)

    def _validate_schema(self) -> None:
        with self.connect() as connection:
            tables = {
                str(row["name"])
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            if "tracks" not in tables:
                raise ValueError("Source database is missing tracks table")
            if "embeddings" not in tables:
                raise ValueError("Source database is missing embeddings table")
            track_columns = _columns(connection, "tracks")
            embedding_columns = _columns(connection, "embeddings")
            missing_track = sorted(REQUIRED_TRACK_COLUMNS - track_columns)
            missing_embedding = sorted(REQUIRED_EMBEDDING_COLUMNS - embedding_columns)
            if missing_track:
                raise ValueError(f"Source tracks table is missing columns: {', '.join(missing_track)}")
            if missing_embedding:
                raise ValueError(f"Source embeddings table is missing columns: {', '.join(missing_embedding)}")


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _clean_path_text(path: str | Path) -> str:
    text = str(path).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text


def _track_page_filter_sql(*, query: str, syncopated: str, label: str) -> tuple[list[str], list[object]]:
    where_parts: list[str] = []
    params: list[object] = []
    needle = query.strip().casefold()
    if needle:
        like = f"%{needle}%"
        searchable_columns = (
            "LOWER(COALESCE(t.artist, ''))",
            "LOWER(COALESCE(t.title, ''))",
            "LOWER(COALESCE(t.album, ''))",
            "LOWER(t.path)",
            "LOWER(t.metadata_json)",
        )
        where_parts.append("(" + " OR ".join(f"{column} LIKE ?" for column in searchable_columns) + ")")
        params.extend([like] * len(searchable_columns))
    if syncopated == "yes":
        where_parts.append("json_extract(t.metadata_json, '$.maest_syncopated_rhythm') = 1")
    elif syncopated == "no":
        where_parts.append("COALESCE(json_extract(t.metadata_json, '$.maest_syncopated_rhythm'), 0) != 1")
    elif syncopated != "all":
        raise ValueError(f"Unknown syncopated filter: {syncopated}")
    if label == "unlabeled":
        where_parts.append("rl.label IS NULL")
    elif label in {"broken", "straight", "ambiguous"}:
        where_parts.append("rl.label = ?")
        params.append(label)
    elif label != "all":
        raise ValueError(f"Unknown label filter: {label}")
    return where_parts, params


def _track_page_item(row: sqlite3.Row) -> dict[str, object]:
    track = LibraryDatabase._row_to_track(row)
    metadata = track.metadata or {}
    return {
        "id": track.id,
        "path": track.path,
        "artist": track.artist,
        "title": track.title,
        "album": track.album,
        "bpm": track.bpm,
        "musical_key": track.musical_key,
        "genres": track.genres,
        "genre_scores": track.genre_scores,
        "label": row["rhythm_label"],
        "maest_syncopated_rhythm": metadata.get("maest_syncopated_rhythm") is True,
        "feature_status": {
            "sonara": isinstance(metadata.get("sonara_features"), dict),
            "mert": bool(row["has_mert_embedding"]),
            "maest": bool(row["has_maest_embedding"]),
        },
    }
