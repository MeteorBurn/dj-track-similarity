from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

import numpy as np

from .models import Track


DEFAULT_EMBEDDING_KEY = "mert"


def normalize_path(path: str | Path) -> str:
    return Path(path).as_posix()


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class LibraryDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _ensure_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    size INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    artist TEXT,
                    title TEXT,
                    album TEXT,
                    bpm REAL,
                    musical_key TEXT,
                    energy REAL,
                    duration REAL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS embeddings (
                    track_id INTEGER NOT NULL,
                    embedding_key TEXT NOT NULL DEFAULT 'mert',
                    model_name TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(track_id, embedding_key),
                    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS playlist_tracks (
                    playlist_id INTEGER NOT NULL,
                    track_id INTEGER NOT NULL,
                    position INTEGER NOT NULL,
                    PRIMARY KEY(playlist_id, position),
                    FOREIGN KEY(playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                    FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
                );
                """
            )
            self._migrate_embedding_schema(connection)

    def _migrate_embedding_schema(self, connection: sqlite3.Connection) -> None:
        columns = connection.execute("PRAGMA table_info(embeddings)").fetchall()
        if any(str(column["name"]) == "embedding_key" for column in columns):
            return
        connection.executescript(
            """
            ALTER TABLE embeddings RENAME TO embeddings_legacy;

            CREATE TABLE embeddings (
                track_id INTEGER NOT NULL,
                embedding_key TEXT NOT NULL DEFAULT 'mert',
                model_name TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector BLOB NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(track_id, embedding_key),
                FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );

            INSERT INTO embeddings (track_id, embedding_key, model_name, dim, vector, updated_at)
            SELECT track_id, 'mert', model_name, dim, vector, updated_at
            FROM embeddings_legacy;

            DROP TABLE embeddings_legacy;
            """
        )

    def get_track_by_path(self, path: str | Path) -> Track | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT t.*, e.model_name AS embedding_model, e.dim AS embedding_dim
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE t.path = ?
                """,
                (DEFAULT_EMBEDDING_KEY, normalize_path(path)),
            ).fetchone()
        return self._row_to_track(row) if row else None

    def get_track(self, track_id: int) -> Track:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT t.*, e.model_name AS embedding_model, e.dim AS embedding_dim
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE t.id = ?
                """,
                (DEFAULT_EMBEDDING_KEY, track_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown track id: {track_id}")
        return self._row_to_track(row)

    def upsert_track(
        self,
        *,
        path: str | Path,
        size: int,
        mtime: float,
        metadata: dict[str, object] | None = None,
        bpm: float | None = None,
        musical_key: str | None = None,
        energy: float | None = None,
        duration: float | None = None,
    ) -> int:
        metadata = metadata or {}
        normalized = normalize_path(path)
        artist = _string_or_none(metadata.get("artist"))
        title = _string_or_none(metadata.get("title")) or Path(path).stem
        album = _string_or_none(metadata.get("album"))
        bpm = bpm if bpm is not None else _optional_float(metadata.get("bpm"))
        musical_key = musical_key or _string_or_none(metadata.get("key")) or _string_or_none(metadata.get("initialkey"))
        duration = duration if duration is not None else _optional_float(metadata.get("duration"))
        metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO tracks (
                    path, size, mtime, artist, title, album, bpm, musical_key,
                    energy, duration, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    size = excluded.size,
                    mtime = excluded.mtime,
                    artist = excluded.artist,
                    title = excluded.title,
                    album = excluded.album,
                    bpm = excluded.bpm,
                    musical_key = excluded.musical_key,
                    energy = excluded.energy,
                    duration = excluded.duration,
                    metadata_json = excluded.metadata_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    normalized,
                    int(size),
                    float(mtime),
                    artist,
                    title,
                    album,
                    bpm,
                    musical_key,
                    energy,
                    duration,
                    metadata_json,
                ),
            )
            row = connection.execute("SELECT id FROM tracks WHERE path = ?", (normalized,)).fetchone()
        if row is None:
            raise RuntimeError(f"Failed to upsert track: {normalized}")
        return int(row["id"])

    def list_tracks(self, *, with_embeddings: bool | None = None, embedding_key: str = DEFAULT_EMBEDDING_KEY) -> list[Track]:
        where = ""
        if with_embeddings is True:
            where = "WHERE e.track_id IS NOT NULL"
        elif with_embeddings is False:
            where = "WHERE e.track_id IS NULL"
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT t.*, e.model_name AS embedding_model, e.dim AS embedding_dim
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                {where}
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                """,
                (embedding_key,),
            ).fetchall()
        return [self._row_to_track(row) for row in rows]

    def save_embedding(
        self,
        track_id: int,
        vector: np.ndarray,
        model_name: str,
        dim: int | None = None,
        *,
        embedding_key: str = DEFAULT_EMBEDDING_KEY,
    ) -> None:
        normalized = np.asarray(vector, dtype=np.float32).reshape(-1)
        norm = float(np.linalg.norm(normalized))
        if norm == 0:
            raise ValueError("Embedding vector must not be zero")
        normalized = normalized / norm
        actual_dim = int(dim or normalized.shape[0])
        if actual_dim != normalized.shape[0]:
            raise ValueError(f"Embedding dim mismatch: {actual_dim} != {normalized.shape[0]}")
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO embeddings (track_id, embedding_key, model_name, dim, vector)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(track_id, embedding_key) DO UPDATE SET
                    model_name = excluded.model_name,
                    dim = excluded.dim,
                    vector = excluded.vector,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (track_id, embedding_key, model_name, actual_dim, normalized.astype(np.float32).tobytes()),
            )

    def load_embedding_matrix(self, embedding_key: str = DEFAULT_EMBEDDING_KEY) -> tuple[list[Track], np.ndarray]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT t.*, e.model_name AS embedding_model, e.dim AS embedding_dim, e.vector
                FROM tracks t
                JOIN embeddings e ON e.track_id = t.id
                WHERE e.embedding_key = ?
                ORDER BY t.id
                """,
                (embedding_key,),
            ).fetchall()
        if not rows:
            return [], np.zeros((0, 0), dtype=np.float32)
        tracks = [self._row_to_track(row) for row in rows]
        vectors = [np.frombuffer(row["vector"], dtype=np.float32).copy() for row in rows]
        return tracks, np.vstack(vectors).astype(np.float32)

    def create_playlist(self, name: str, track_ids: Iterable[int]) -> int:
        ordered_ids = list(track_ids)
        with self.connect() as connection:
            cursor = connection.execute("INSERT INTO playlists (name) VALUES (?)", (name,))
            playlist_id = int(cursor.lastrowid)
            connection.executemany(
                "INSERT INTO playlist_tracks (playlist_id, track_id, position) VALUES (?, ?, ?)",
                [(playlist_id, track_id, index) for index, track_id in enumerate(ordered_ids)],
            )
        return playlist_id

    def get_playlist_name(self, playlist_id: int) -> str:
        with self.connect() as connection:
            row = connection.execute("SELECT name FROM playlists WHERE id = ?", (playlist_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown playlist id: {playlist_id}")
        return str(row["name"])

    def get_playlist_tracks(self, playlist_id: int) -> list[Track]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT t.*, e.model_name AS embedding_model, e.dim AS embedding_dim
                FROM playlist_tracks pt
                JOIN tracks t ON t.id = pt.track_id
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE pt.playlist_id = ?
                ORDER BY pt.position
                """,
                (DEFAULT_EMBEDDING_KEY, playlist_id),
            ).fetchall()
        if not rows and self.get_playlist_name(playlist_id) is None:
            raise KeyError(f"Unknown playlist id: {playlist_id}")
        return [self._row_to_track(row) for row in rows]

    @staticmethod
    def _row_to_track(row: sqlite3.Row) -> Track:
        return Track(
            id=int(row["id"]),
            path=str(row["path"]),
            size=int(row["size"]),
            mtime=float(row["mtime"]),
            artist=row["artist"],
            title=row["title"],
            album=row["album"],
            bpm=row["bpm"],
            musical_key=row["musical_key"],
            energy=row["energy"],
            duration=row["duration"],
            embedding_model=row["embedding_model"] if "embedding_model" in row.keys() else None,
            embedding_dim=row["embedding_dim"] if "embedding_dim" in row.keys() else None,
        )


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None
