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
                SELECT t.*, e.model_name AS embedding_model, e.dim AS embedding_dim,
                    (
                        SELECT json_group_array(embedding_key)
                        FROM embeddings
                        WHERE track_id = t.id
                    ) AS embedding_keys_json
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
                SELECT t.*, e.model_name AS embedding_model, e.dim AS embedding_dim,
                    (
                        SELECT json_group_array(embedding_key)
                        FROM embeddings
                        WHERE track_id = t.id
                    ) AS embedding_keys_json
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
                SELECT t.*, e.model_name AS embedding_model, e.dim AS embedding_dim,
                    (
                        SELECT json_group_array(embedding_key)
                        FROM embeddings
                        WHERE track_id = t.id
                    ) AS embedding_keys_json
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

    def save_genres(self, track_id: int, genres: list[dict[str, object]], *, model_name: str) -> None:
        cleaned = []
        for genre in genres:
            label = _string_or_none(genre.get("label"))
            if not label:
                continue
            score = _optional_float(genre.get("score"))
            cleaned.append({"label": label, "score": float(score or 0.0)})
        with self.connect() as connection:
            row = connection.execute("SELECT metadata_json FROM tracks WHERE id = ?", (track_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown track id: {track_id}")
            try:
                metadata = json.loads(str(row["metadata_json"] or "{}"))
            except json.JSONDecodeError:
                metadata = {}
            metadata["maest_genres"] = cleaned
            metadata["maest_model"] = model_name
            connection.execute(
                "UPDATE tracks SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=False, sort_keys=True), track_id),
            )

    def save_sonara_features(
        self,
        track_id: int,
        features: dict[str, object],
        *,
        bpm: float | None = None,
        musical_key: str | None = None,
        energy: float | None = None,
        duration: float | None = None,
        model_name: str = "sonara",
    ) -> None:
        with self.connect() as connection:
            row = connection.execute("SELECT metadata_json FROM tracks WHERE id = ?", (track_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown track id: {track_id}")
            try:
                metadata = json.loads(str(row["metadata_json"] or "{}"))
            except json.JSONDecodeError:
                metadata = {}
            metadata["sonara_features"] = features
            metadata["sonara_model"] = model_name
            connection.execute(
                """
                UPDATE tracks
                SET bpm = COALESCE(?, bpm),
                    musical_key = COALESCE(?, musical_key),
                    energy = COALESCE(?, energy),
                    duration = COALESCE(?, duration),
                    metadata_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    bpm,
                    musical_key,
                    energy,
                    duration,
                    json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    track_id,
                ),
            )

    def refresh_track_file_metadata(
        self,
        track_id: int,
        *,
        size: int,
        mtime: float,
        metadata: dict[str, object],
        replace_metadata_keys: Iterable[str],
    ) -> None:
        with self.connect() as connection:
            row = connection.execute("SELECT metadata_json FROM tracks WHERE id = ?", (track_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown track id: {track_id}")
            existing_metadata = _metadata_from_json(row["metadata_json"])
            for key in replace_metadata_keys:
                existing_metadata.pop(key, None)
            existing_metadata.update(metadata)
            has_sonara = bool(existing_metadata.get("sonara_features"))
            bpm = _optional_float(metadata.get("bpm"))
            musical_key = _string_or_none(metadata.get("key")) or _string_or_none(metadata.get("initialkey"))
            duration = _optional_float(metadata.get("duration"))
            connection.execute(
                """
                UPDATE tracks
                SET size = ?,
                    mtime = ?,
                    artist = ?,
                    title = ?,
                    album = ?,
                    bpm = CASE WHEN ? THEN bpm ELSE ? END,
                    musical_key = CASE WHEN ? THEN musical_key ELSE ? END,
                    duration = CASE WHEN ? THEN duration ELSE ? END,
                    metadata_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    int(size),
                    float(mtime),
                    _string_or_none(metadata.get("artist")),
                    _string_or_none(metadata.get("title")) or Path(_string_or_none(existing_metadata.get("path")) or "").stem,
                    _string_or_none(metadata.get("album")),
                    1 if has_sonara else 0,
                    bpm,
                    1 if has_sonara else 0,
                    musical_key,
                    1 if has_sonara else 0,
                    duration,
                    json.dumps(existing_metadata, ensure_ascii=False, sort_keys=True),
                    track_id,
                ),
            )

    def reset_analysis(self, adapter: str) -> dict[str, object]:
        adapter = adapter.strip().lower()
        if adapter in {"mert", "clap", "fake"}:
            with self.connect() as connection:
                cursor = connection.execute("DELETE FROM embeddings WHERE embedding_key = ?", (adapter,))
                return {"adapter": adapter, "tracks_updated": 0, "embeddings_deleted": cursor.rowcount}
        if adapter == "maest":
            return self._reset_metadata_analysis(adapter, ("maest_genres", "maest_model"))
        if adapter == "sonara":
            return self._reset_sonara_analysis()
        raise ValueError(f"Unsupported analysis adapter reset: {adapter}")

    def clear_library(self) -> dict[str, int]:
        with self.connect() as connection:
            counts = {
                "tracks_deleted": int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]),
                "embeddings_deleted": int(connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]),
                "playlists_deleted": int(connection.execute("SELECT COUNT(*) FROM playlists").fetchone()[0]),
                "playlist_tracks_deleted": int(connection.execute("SELECT COUNT(*) FROM playlist_tracks").fetchone()[0]),
            }
            connection.execute("DELETE FROM playlist_tracks")
            connection.execute("DELETE FROM playlists")
            connection.execute("DELETE FROM embeddings")
            connection.execute("DELETE FROM tracks")
        return counts

    def _reset_metadata_analysis(self, adapter: str, keys: tuple[str, ...]) -> dict[str, object]:
        updated = 0
        with self.connect() as connection:
            rows = connection.execute("SELECT id, metadata_json FROM tracks").fetchall()
            for row in rows:
                metadata = _metadata_from_json(row["metadata_json"])
                if not any(key in metadata for key in keys):
                    continue
                for key in keys:
                    metadata.pop(key, None)
                connection.execute(
                    "UPDATE tracks SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (json.dumps(metadata, ensure_ascii=False, sort_keys=True), row["id"]),
                )
                updated += 1
        return {"adapter": adapter, "tracks_updated": updated, "embeddings_deleted": 0}

    def _reset_sonara_analysis(self) -> dict[str, object]:
        updated = 0
        keys = ("sonara_features", "sonara_features_file", "sonara_model")
        with self.connect() as connection:
            rows = connection.execute("SELECT id, metadata_json FROM tracks").fetchall()
            for row in rows:
                metadata = _metadata_from_json(row["metadata_json"])
                if not any(key in metadata for key in keys):
                    continue
                for key in keys:
                    metadata.pop(key, None)
                connection.execute(
                    """
                    UPDATE tracks
                    SET bpm = ?,
                        musical_key = ?,
                        energy = ?,
                        duration = ?,
                        metadata_json = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        _optional_float(metadata.get("bpm")),
                        _string_or_none(metadata.get("key")) or _string_or_none(metadata.get("initialkey")),
                        _optional_float(metadata.get("energy")),
                        _optional_float(metadata.get("duration")),
                        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                        row["id"],
                    ),
                )
                updated += 1
        return {"adapter": "sonara", "tracks_updated": updated, "embeddings_deleted": 0}

    def load_embedding_matrix(self, embedding_key: str = DEFAULT_EMBEDDING_KEY) -> tuple[list[Track], np.ndarray]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT t.*, e.model_name AS embedding_model, e.dim AS embedding_dim, e.vector,
                    (
                        SELECT json_group_array(embedding_key)
                        FROM embeddings
                        WHERE track_id = t.id
                    ) AS embedding_keys_json
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
                SELECT t.*, e.model_name AS embedding_model, e.dim AS embedding_dim,
                    (
                        SELECT json_group_array(embedding_key)
                        FROM embeddings
                        WHERE track_id = t.id
                    ) AS embedding_keys_json
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
        metadata = _metadata_from_json(row["metadata_json"] if "metadata_json" in row.keys() else "{}")
        genres, genre_scores = _genres_from_metadata(metadata)
        analyses = _analyses_from_row(row, metadata)
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
            metadata=metadata,
            genres=genres,
            genre_scores=genre_scores,
            analyses=analyses,
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


def _metadata_from_json(metadata_json: object) -> dict[str, object]:
    try:
        metadata = json.loads(str(metadata_json or "{}"))
    except json.JSONDecodeError:
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _genres_from_metadata(metadata: dict[str, object]) -> tuple[list[str] | None, dict[str, float] | None]:
    raw_genres = metadata.get("maest_genres")
    if not isinstance(raw_genres, list):
        return None, None
    labels: list[str] = []
    scores: dict[str, float] = {}
    for item in raw_genres:
        if not isinstance(item, dict):
            continue
        label = _string_or_none(item.get("label"))
        score = _optional_float(item.get("score"))
        if label is None:
            continue
        labels.append(label)
        scores[label] = float(score or 0.0)
    return (labels or None), (scores or None)


def _analyses_from_row(row: sqlite3.Row, metadata: dict[str, object]) -> list[str] | None:
    analyses_set: set[str] = set()
    if metadata.get("maest_genres"):
        analyses_set.add("maest")
    if metadata.get("sonara_features"):
        analyses_set.add("sonara")
    keys_json = row["embedding_keys_json"] if "embedding_keys_json" in row.keys() else None
    try:
        keys = json.loads(str(keys_json or "[]"))
    except json.JSONDecodeError:
        keys = []
    if isinstance(keys, list):
        for key in keys:
            text = _string_or_none(key)
            if text:
                analyses_set.add(text)
    ordered = [name for name in ("sonara", "maest", "mert", "clap") if name in analyses_set]
    extras = sorted(name for name in analyses_set if name not in {"maest", "sonara", "mert", "clap"})
    analyses = ordered + extras
    return analyses or None
