from __future__ import annotations

from contextlib import nullcontext as _nullcontext
import json
import sqlite3
import threading
from pathlib import Path
from typing import ClassVar, Iterable

import numpy as np

from .db_schema import (
    MAEST_HAS_GENRES_SQL,
    SQLITE_BUSY_TIMEOUT_SECONDS,
    TRACK_SELECT_FIELDS,
    TRACK_SLIM_SELECT_FIELDS,
    TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR,
    ensure_schema,
)
from .metadata_payload import (
    analyses_from_row,
    clean_maest_genre_label,
    genres_from_metadata,
    metadata_from_json,
    metadata_to_json,
    optional_float,
    string_or_none,
)
from .models import Track


DEFAULT_EMBEDDING_KEY = "mert"
MAEST_EMBEDDING_KEY = "maest"
LIBRARY_ROOT_SETTING_KEY = "library_root"
SYNCOPATED_RHYTHM_GENRES = (
    "Breakbeat",
    "Breakcore",
    "Breaks",
    "Progressive Breaks",
    "Broken Beat",
    "Drum n Bass",
    "Jungle",
    "Halftime",
    "Juke",
    "UK Garage",
    "Speed Garage",
    "Bassline",
    "Electro",
)


def normalize_path(path: str | Path) -> str:
    return Path(path).as_posix()


class LibraryDatabase:
    _write_locks: ClassVar[dict[Path, threading.RLock]] = {}
    _write_locks_guard: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve(strict=False)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = self._write_lock_for_path(self.path)
        self._cache_lock = threading.Lock()
        self._embedding_matrix_cache: dict[str, tuple[list[Track], np.ndarray]] = {}
        self._ensure_schema()

    @classmethod
    def _write_lock_for_path(cls, path: Path) -> threading.RLock:
        with cls._write_locks_guard:
            lock = cls._write_locks.get(path)
            if lock is None:
                lock = threading.RLock()
                cls._write_locks[path] = lock
            return lock

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=SQLITE_BUSY_TIMEOUT_SECONDS)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_SECONDS * 1000}")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute("PRAGMA cache_size = -32768")
        return connection

    def _ensure_schema(self) -> None:
        with self._write_lock, self.connect() as connection:
            ensure_schema(connection)

    def _invalidate_embedding_cache(self, embedding_key: str | None = None) -> None:
        with self._cache_lock:
            if embedding_key is None:
                self._embedding_matrix_cache.clear()
            else:
                self._embedding_matrix_cache.pop(embedding_key, None)

    def get_track_by_path(self, path: str | Path) -> Track | None:
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE t.path = ?
                """,
                (DEFAULT_EMBEDDING_KEY, normalize_path(path)),
            ).fetchone()
        return self._row_to_track(row) if row else None

    def get_library_root(self) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM library_settings WHERE key = ?",
                (LIBRARY_ROOT_SETTING_KEY,),
            ).fetchone()
        return str(row["value"]) if row is not None else None

    def set_library_root(self, root: str | Path) -> str:
        normalized = normalize_path(root)
        with self._write_lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO library_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (LIBRARY_ROOT_SETTING_KEY, normalized),
            )
        return normalized

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
        artist = string_or_none(metadata.get("artist"))
        title = string_or_none(metadata.get("title")) or Path(path).stem
        album = string_or_none(metadata.get("album"))
        bpm = optional_float(bpm) if bpm is not None else optional_float(metadata.get("bpm"))
        musical_key = musical_key or string_or_none(metadata.get("key")) or string_or_none(metadata.get("initialkey"))
        energy = optional_float(energy)
        duration = optional_float(duration) if duration is not None else optional_float(metadata.get("duration"))
        metadata_json = metadata_to_json(metadata)

        with self._write_lock, self.connect() as connection:
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
        self._invalidate_embedding_cache()
        if row is None:
            raise RuntimeError(f"Failed to upsert track: {normalized}")
        return int(row["id"])

    def list_tracks(
        self,
        *,
        with_embeddings: bool | None = None,
        embedding_key: str = DEFAULT_EMBEDDING_KEY,
        include_metadata: bool = True,
    ) -> list[Track]:
        fields = TRACK_SELECT_FIELDS if include_metadata else TRACK_SLIM_SELECT_FIELDS
        where = ""
        if with_embeddings is True:
            where = "WHERE e.track_id IS NOT NULL"
        elif with_embeddings is False:
            where = "WHERE e.track_id IS NULL"
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {fields}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                {where}
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                """,
                (embedding_key,),
            ).fetchall()
        return [self._row_to_track(row, include_metadata=include_metadata) for row in rows]

    def list_tracks_page(
        self,
        *,
        query: str = "",
        preset: str = "all",
        min_break_energy: float | None = None,
        limit: int = 100,
        offset: int = 0,
        include_metadata: bool = False,
        embedding_key: str = DEFAULT_EMBEDDING_KEY,
    ) -> dict[str, object]:
        fields = TRACK_SELECT_FIELDS if include_metadata else TRACK_SLIM_SELECT_FIELDS
        where_parts, params = _track_filter_sql(query=query, preset=preset, min_break_energy=min_break_energy)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        order_sql = _track_order_sql(min_break_energy=min_break_energy)
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        with self.connect() as connection:
            total = int(connection.execute(f"SELECT COUNT(*) FROM tracks t {where_sql}", params).fetchone()[0])
            rows = connection.execute(
                f"""
                SELECT {fields}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                {where_sql}
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?
                """,
                (embedding_key, *params, bounded_limit, bounded_offset),
            ).fetchall()
        return {
            "items": [self._row_to_track(row, include_metadata=include_metadata) for row in rows],
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    def list_filtered_tracks(
        self,
        *,
        query: str = "",
        preset: str = "all",
        min_break_energy: float | None = None,
        include_metadata: bool = False,
        embedding_key: str = DEFAULT_EMBEDDING_KEY,
    ) -> dict[str, object]:
        fields = TRACK_SELECT_FIELDS if include_metadata else TRACK_SLIM_SELECT_FIELDS
        where_parts, params = _track_filter_sql(query=query, preset=preset, min_break_energy=min_break_energy)
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        order_sql = _track_order_sql(min_break_energy=min_break_energy)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {fields}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                {where_sql}
                ORDER BY {order_sql}
                """,
                (embedding_key, *params),
            ).fetchall()
        tracks = [self._row_to_track(row, include_metadata=include_metadata) for row in rows]
        return {"items": tracks, "total": len(tracks)}

    def list_tracks_missing_sonara(self, *, limit: int | None = None) -> list[Track]:
        limit_sql, params = _limit_sql(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SLIM_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE json_type(t.metadata_json, '$.sonara_features') IS NULL
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                {limit_sql}
                """,
                (DEFAULT_EMBEDDING_KEY, *params),
            ).fetchall()
        return [self._row_to_track(row, include_metadata=False) for row in rows]

    def list_tracks_missing_maest(self, *, limit: int | None = None) -> list[Track]:
        limit_sql, params = _limit_sql(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SLIM_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE e.track_id IS NULL
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                {limit_sql}
                """,
                (MAEST_EMBEDDING_KEY, *params),
            ).fetchall()
        return [self._row_to_track(row, include_metadata=False) for row in rows]

    def list_tracks_missing_embedding(self, embedding_key: str, *, limit: int | None = None) -> list[Track]:
        limit_sql, params = _limit_sql(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SLIM_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE e.track_id IS NULL
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                {limit_sql}
                """,
                (embedding_key, *params),
            ).fetchall()
        return [self._row_to_track(row, include_metadata=False) for row in rows]

    def list_track_paths(self) -> list[tuple[int, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, path
                FROM tracks
                ORDER BY COALESCE(artist, ''), COALESCE(title, ''), path
                """
            ).fetchall()
        return [(int(row["id"]), str(row["path"])) for row in rows]

    def get_track_file_stat_by_path(self, path: str | Path) -> tuple[int, int, float] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, size, mtime FROM tracks WHERE path = ?",
                (normalize_path(path),),
            ).fetchone()
        if row is None:
            return None
        return int(row["id"]), int(row["size"]), float(row["mtime"])

    def list_tracks_with_maest_genres(self) -> list[Track]:
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE {MAEST_HAS_GENRES_SQL.replace('metadata_json', 't.metadata_json')}
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                """,
                (DEFAULT_EMBEDDING_KEY,),
            ).fetchall()
        return [self._row_to_track(row) for row in rows]

    def library_summary(self) -> dict[str, int]:
        with self.connect() as connection:
            tracks = int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
            sonara = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tracks INDEXED BY idx_tracks_sonara_present
                    WHERE json_type(metadata_json, '$.sonara_features') IS NOT NULL
                    """
                ).fetchone()[0]
            )
            maest = int(
                connection.execute(
                    "SELECT COUNT(DISTINCT track_id) FROM embeddings WHERE embedding_key = ?",
                    (MAEST_EMBEDDING_KEY,),
                ).fetchone()[0]
            )
            mert = int(
                connection.execute("SELECT COUNT(DISTINCT track_id) FROM embeddings WHERE embedding_key = ?", ("mert",)).fetchone()[0]
            )
            clap = int(
                connection.execute("SELECT COUNT(DISTINCT track_id) FROM embeddings WHERE embedding_key = ?", ("clap",)).fetchone()[0]
            )
        return {"tracks": tracks, "sonara": sonara, "maest": maest, "mert": mert, "clap": clap}

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
        with self._write_lock, self.connect() as connection:
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
        self._invalidate_embedding_cache(embedding_key)

    def save_genres(self, track_id: int, genres: list[dict[str, object]], *, model_name: str) -> None:
        cleaned = []
        for genre in genres:
            label = clean_maest_genre_label(string_or_none(genre.get("label")))
            if not label:
                continue
            score = optional_float(genre.get("score"))
            cleaned.append({"label": label, "score": float(score or 0.0)})
        with self._write_lock, self.connect() as connection:
            metadata = self._metadata_for_track_update(connection, track_id)
            _set_maest_metadata(metadata, model_name=model_name, genres=cleaned)
            connection.execute(
                "UPDATE tracks SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (metadata_to_json(metadata, sort_keys=False), track_id),
            )
        self._invalidate_embedding_cache()

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
        with self._write_lock, self.connect() as connection:
            metadata = self._metadata_for_track_update(connection, track_id)
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
                    optional_float(bpm),
                    musical_key,
                    optional_float(energy),
                    optional_float(duration),
                    metadata_to_json(metadata, sort_keys=False),
                    track_id,
                ),
            )
        self._invalidate_embedding_cache()

    def refresh_track_file_metadata(
        self,
        track_id: int,
        *,
        size: int,
        mtime: float,
        metadata: dict[str, object],
        replace_metadata_keys: Iterable[str],
    ) -> None:
        with self._write_lock, self.connect() as connection:
            existing_metadata = self._metadata_for_track_update(connection, track_id)
            for key in replace_metadata_keys:
                existing_metadata.pop(key, None)
            existing_metadata.update(metadata)
            has_sonara = bool(existing_metadata.get("sonara_features"))
            bpm = optional_float(metadata.get("bpm"))
            musical_key = string_or_none(metadata.get("key")) or string_or_none(metadata.get("initialkey"))
            duration = optional_float(metadata.get("duration"))
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
                    string_or_none(metadata.get("artist")),
                    string_or_none(metadata.get("title")) or Path(string_or_none(existing_metadata.get("path")) or "").stem,
                    string_or_none(metadata.get("album")),
                    1 if has_sonara else 0,
                    bpm,
                    1 if has_sonara else 0,
                    musical_key,
                    1 if has_sonara else 0,
                    duration,
                    metadata_to_json(existing_metadata),
                    track_id,
                ),
            )
        self._invalidate_embedding_cache()

    def _metadata_for_track_update(self, connection: sqlite3.Connection, track_id: int) -> dict[str, object]:
        row = connection.execute("SELECT metadata_json FROM tracks WHERE id = ?", (track_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown track id: {track_id}")
        return metadata_from_json(row["metadata_json"])

    def reset_analysis(self, adapter: str) -> dict[str, object]:
        adapter = adapter.strip().lower()
        if adapter in {"mert", "clap"}:
            with self._write_lock, self.connect() as connection:
                cursor = connection.execute("DELETE FROM embeddings WHERE embedding_key = ?", (adapter,))
                deleted = cursor.rowcount
            self._invalidate_embedding_cache(adapter)
            return {"adapter": adapter, "tracks_updated": 0, "embeddings_deleted": deleted}
        if adapter == "maest":
            return self._reset_metadata_and_embedding_analysis(
                adapter,
                ("maest_genres", "maest_model", "maest_syncopated_rhythm"),
                embedding_key=MAEST_EMBEDDING_KEY,
            )
        if adapter == "sonara":
            return self._reset_sonara_analysis()
        raise ValueError(f"Unsupported analysis adapter reset: {adapter}")

    def clear_library(self) -> dict[str, int]:
        with self._write_lock, self.connect() as connection:
            counts = {
                "tracks_deleted": int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]),
                "embeddings_deleted": int(connection.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]),
            }
            connection.execute("DELETE FROM embeddings")
            connection.execute("DELETE FROM tracks")
        self._invalidate_embedding_cache()
        return counts

    def save_classifier_score(
        self,
        track_id: int,
        *,
        classifier: str,
        score: float,
        label: str,
        confidence: float,
        probabilities: dict[str, float],
        feature_set: str,
        model_id: str,
    ) -> None:
        probabilities_json = metadata_to_json(probabilities)
        with self._write_lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO track_classifier_scores (
                    track_id, classifier, score, label, confidence,
                    probabilities_json, feature_set, model_id, analyzed_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(track_id, classifier) DO UPDATE SET
                    score = excluded.score,
                    label = excluded.label,
                    confidence = excluded.confidence,
                    probabilities_json = excluded.probabilities_json,
                    feature_set = excluded.feature_set,
                    model_id = excluded.model_id,
                    analyzed_at = CURRENT_TIMESTAMP
                """,
                (
                    int(track_id),
                    classifier.strip(),
                    float(score),
                    label.strip(),
                    float(confidence),
                    probabilities_json,
                    feature_set.strip(),
                    str(model_id),
                ),
            )

    def classifier_score(self, track_id: int, classifier: str) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT score, label, confidence, probabilities_json, feature_set, model_id, analyzed_at
                FROM track_classifier_scores
                WHERE track_id = ? AND classifier = ?
                """,
                (int(track_id), classifier),
            ).fetchone()
        if row is None:
            return None
        return {
            "score": float(row["score"]),
            "label": str(row["label"]),
            "confidence": float(row["confidence"]),
            "probabilities": metadata_from_json(row["probabilities_json"]),
            "feature_set": str(row["feature_set"]),
            "model_id": str(row["model_id"]),
            "analyzed_at": str(row["analyzed_at"]),
        }

    def relocate_library(self, old_root: str | Path, new_root: str | Path, *, apply: bool = False) -> dict[str, object]:
        old_root_text = _normalize_root(old_root)
        new_root_text = _normalize_root(new_root)
        if old_root_text == new_root_text:
            raise ValueError("Old and new library roots must be different")

        with self._write_lock if apply else _nullcontext(), self.connect() as connection:
            rows = connection.execute("SELECT id, path FROM tracks ORDER BY id").fetchall()
            existing_by_path = {str(row["path"]).casefold(): int(row["id"]) for row in rows}
            changes: list[dict[str, object]] = []
            conflicts: list[dict[str, object]] = []
            missing_files: list[dict[str, object]] = []
            planned_paths: set[str] = set()

            for row in rows:
                track_id = int(row["id"])
                old_path = str(row["path"])
                new_path = _relocate_path(old_path, old_root_text, new_root_text)
                if new_path is None:
                    continue

                new_path_key = new_path.casefold()
                existing_track_id = existing_by_path.get(new_path_key)
                if existing_track_id is not None and existing_track_id != track_id:
                    conflicts.append(
                        {
                            "track_id": track_id,
                            "old_path": old_path,
                            "new_path": new_path,
                            "existing_track_id": existing_track_id,
                        }
                    )
                if new_path_key in planned_paths:
                    conflicts.append(
                        {
                            "track_id": track_id,
                            "old_path": old_path,
                            "new_path": new_path,
                            "existing_track_id": None,
                        }
                    )
                planned_paths.add(new_path_key)

                if not Path(new_path).is_file():
                    missing_files.append({"track_id": track_id, "path": new_path})
                changes.append({"track_id": track_id, "old_path": old_path, "new_path": new_path})

            if apply:
                if conflicts:
                    raise ValueError("Cannot relocate library because one or more target paths conflict")
                if missing_files:
                    raise ValueError("Cannot relocate library because one or more target files are missing")
                for change in changes:
                    connection.execute(
                        "UPDATE tracks SET path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (change["new_path"], change["track_id"]),
                    )
        if apply and changes:
            self._invalidate_embedding_cache()

        return {
            "old_root": old_root_text,
            "new_root": new_root_text,
            "dry_run": not apply,
            "tracks_matched": len(changes),
            "tracks_updated": len(changes) if apply else 0,
            "missing_files": missing_files,
            "conflicts": conflicts,
            "changes": changes,
        }

    def _reset_metadata_analysis(self, adapter: str, keys: tuple[str, ...]) -> dict[str, object]:
        updated = 0
        with self._write_lock, self.connect() as connection:
            rows = connection.execute("SELECT id, metadata_json FROM tracks").fetchall()
            for row in rows:
                metadata = metadata_from_json(row["metadata_json"])
                if not any(key in metadata for key in keys):
                    continue
                for key in keys:
                    metadata.pop(key, None)
                connection.execute(
                    "UPDATE tracks SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (metadata_to_json(metadata), row["id"]),
                )
                updated += 1
        if updated:
            self._invalidate_embedding_cache()
        return {"adapter": adapter, "tracks_updated": updated, "embeddings_deleted": 0}

    def _reset_metadata_and_embedding_analysis(
        self,
        adapter: str,
        keys: tuple[str, ...],
        *,
        embedding_key: str,
    ) -> dict[str, object]:
        updated = 0
        with self._write_lock, self.connect() as connection:
            rows = connection.execute("SELECT id, metadata_json FROM tracks").fetchall()
            for row in rows:
                metadata = metadata_from_json(row["metadata_json"])
                if not any(key in metadata for key in keys):
                    continue
                for key in keys:
                    metadata.pop(key, None)
                connection.execute(
                    "UPDATE tracks SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (metadata_to_json(metadata), row["id"]),
                )
                updated += 1
            cursor = connection.execute("DELETE FROM embeddings WHERE embedding_key = ?", (embedding_key,))
            deleted = cursor.rowcount
        if updated or deleted:
            self._invalidate_embedding_cache()
        return {"adapter": adapter, "tracks_updated": updated, "embeddings_deleted": deleted}

    def _reset_sonara_analysis(self) -> dict[str, object]:
        updated = 0
        keys = ("sonara_features", "sonara_features_file", "sonara_model")
        with self._write_lock, self.connect() as connection:
            rows = connection.execute("SELECT id, metadata_json FROM tracks").fetchall()
            for row in rows:
                metadata = metadata_from_json(row["metadata_json"])
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
                        optional_float(metadata.get("bpm")),
                        string_or_none(metadata.get("key")) or string_or_none(metadata.get("initialkey")),
                        optional_float(metadata.get("energy")),
                        optional_float(metadata.get("duration")),
                        metadata_to_json(metadata),
                        row["id"],
                    ),
                )
                updated += 1
        if updated:
            self._invalidate_embedding_cache()
        return {"adapter": "sonara", "tracks_updated": updated, "embeddings_deleted": 0}

    def load_embedding_matrix(self, embedding_key: str = DEFAULT_EMBEDDING_KEY) -> tuple[list[Track], np.ndarray]:
        with self._cache_lock:
            cached = self._embedding_matrix_cache.get(embedding_key)
            if cached is not None:
                return cached
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
            result = ([], np.zeros((0, 0), dtype=np.float32))
            with self._cache_lock:
                self._embedding_matrix_cache[embedding_key] = result
            return result
        tracks = [self._row_to_track(row, include_metadata=False) for row in rows]
        vectors = [np.frombuffer(row["vector"], dtype=np.float32).copy() for row in rows]
        result = (tracks, np.vstack(vectors).astype(np.float32))
        with self._cache_lock:
            self._embedding_matrix_cache[embedding_key] = result
        return result

    @staticmethod
    def _row_to_track(row: sqlite3.Row, *, include_metadata: bool = True) -> Track:
        row_keys = set(row.keys())
        metadata = metadata_from_json(row["metadata_json"]) if include_metadata and "metadata_json" in row_keys else {}
        genres, genre_scores = genres_from_metadata(metadata) if include_metadata else (None, None)
        analyses = analyses_from_row(row, metadata)
        classifier_scores = _classifier_scores_from_row(row) if "classifier_scores_json" in row_keys else None
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
            metadata=metadata if include_metadata else None,
            genres=genres,
            genre_scores=genre_scores,
            classifier_scores=classifier_scores,
            analyses=analyses,
            embedding_model=row["embedding_model"] if "embedding_model" in row.keys() else None,
            embedding_dim=row["embedding_dim"] if "embedding_dim" in row.keys() else None,
        )


def _limit_sql(limit: int | None) -> tuple[str, tuple[int, ...]]:
    if limit is None:
        return "", ()
    return "LIMIT ?", (max(0, int(limit)),)


def _track_filter_sql(*, query: str, preset: str, min_break_energy: float | None = None) -> tuple[list[str], list[object]]:
    where_parts: list[str] = []
    params: list[object] = []
    needle = query.strip().lower()
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
    if preset == "syncopated":
        where_parts.append("json_extract(t.metadata_json, '$.maest_syncopated_rhythm') = 1")
    elif preset != "all":
        raise ValueError(f"Unknown library preset: {preset}")
    if min_break_energy is not None:
        where_parts.append(
            """
            EXISTS (
                SELECT 1
                FROM track_classifier_scores cs
                WHERE cs.track_id = t.id
                  AND cs.classifier = 'break_energy'
                  AND cs.score >= ?
            )
            """
        )
        params.append(float(min_break_energy))
    return where_parts, params


def _track_order_sql(*, min_break_energy: float | None = None) -> str:
    if min_break_energy is None:
        return "COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path"
    return (
        "(SELECT cs.score FROM track_classifier_scores cs "
        "WHERE cs.track_id = t.id AND cs.classifier = 'break_energy') DESC, "
        "COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path"
    )


def _classifier_scores_from_row(row: sqlite3.Row) -> dict[str, dict[str, object]] | None:
    raw = row["classifier_scores_json"]
    if raw is None:
        return None
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) and parsed else None


def _set_maest_metadata(metadata: dict[str, object], *, model_name: str, genres: list[dict[str, object]]) -> None:
    for key in ("maest_model", "maest_genres", "maest_syncopated_rhythm"):
        metadata.pop(key, None)
    metadata["maest_model"] = model_name
    metadata["maest_genres"] = genres
    metadata["maest_syncopated_rhythm"] = _has_syncopated_rhythm_genre(genres)


def _has_syncopated_rhythm_genre(genres: list[dict[str, object]]) -> bool:
    syncopated = {genre.lower() for genre in SYNCOPATED_RHYTHM_GENRES}
    for genre in genres:
        label = string_or_none(genre.get("label"))
        if label and label.lower() in syncopated:
            return True
    return False


def _normalize_root(path: str | Path) -> str:
    normalized = normalize_path(path).rstrip("/")
    if not normalized:
        raise ValueError("Library root must not be empty")
    return normalized


def _relocate_path(path: str, old_root: str, new_root: str) -> str | None:
    path_key = path.casefold()
    old_key = old_root.casefold()
    if path_key == old_key:
        return new_root
    prefix = f"{old_key}/"
    if not path_key.startswith(prefix):
        return None
    relative = path[len(old_root) :].lstrip("/")
    return f"{new_root}/{relative}" if relative else new_root
