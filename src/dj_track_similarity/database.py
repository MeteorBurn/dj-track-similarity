from __future__ import annotations

from contextlib import nullcontext as _nullcontext
import json
import sqlite3
import threading
from pathlib import Path
from typing import Iterable

import numpy as np

from .db_schema import (
    MAEST_HAS_GENRES_SQL,
    TRACK_SELECT_FIELDS,
    TRACK_SLIM_SELECT_FIELDS,
    TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR,
)
from .db_connection import connect_database, ensure_database_schema, resolve_database_path, write_lock_for_path
from .db_library_queries import build_track_filter_sql, track_order_sql
from .db_analysis_candidates import (
    analysis_candidate_select_sql,
    chunk_ids,
    clean_analysis_models,
    missing_analysis_ids_params,
    missing_analysis_ids_sql,
    row_to_analysis_candidate,
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
from .models import AnalysisCandidate, Track


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
    def __init__(self, path: str | Path) -> None:
        self.path = resolve_database_path(path)
        self._write_lock = write_lock_for_path(self.path)
        self._cache_lock = threading.Lock()
        self._embedding_matrix_cache: dict[str, tuple[list[Track], np.ndarray]] = {}
        self._ensure_schema()

    def connect(self) -> sqlite3.Connection:
        return connect_database(self.path)

    def _ensure_schema(self) -> None:
        ensure_database_schema(self.path, self._write_lock)

    def _invalidate_embedding_cache(self, embedding_key: str | None = None) -> None:
        with self._cache_lock:
            if embedding_key is None:
                self._embedding_matrix_cache.clear()
            else:
                self._embedding_matrix_cache.pop(embedding_key, None)

    def _invalidate_embedding_cache_keys(self, embedding_keys: Iterable[str]) -> None:
        keys = tuple(dict.fromkeys(key for key in embedding_keys if key))
        if not keys:
            return
        with self._cache_lock:
            for key in keys:
                self._embedding_matrix_cache.pop(key, None)

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
            embedding_keys = _embedding_keys_for_track(connection, int(row["id"])) if row is not None else ()
        self._invalidate_embedding_cache_keys(embedding_keys)
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
        liked_only: bool = False,
        classifier_min_scores: dict[str, float] | None = None,
        limit: int = 100,
        offset: int = 0,
        include_metadata: bool = False,
        embedding_key: str = DEFAULT_EMBEDDING_KEY,
    ) -> dict[str, object]:
        fields = TRACK_SELECT_FIELDS if include_metadata else TRACK_SLIM_SELECT_FIELDS
        thresholds = dict(classifier_min_scores or {})
        where_sql, params = build_track_filter_sql(
            query=query,
            preset=preset,
            liked_only=liked_only,
            classifier_min_scores=thresholds,
        )
        order_sql = track_order_sql(classifier_min_scores=thresholds)
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
        liked_only: bool = False,
        classifier_min_scores: dict[str, float] | None = None,
        include_metadata: bool = False,
        embedding_key: str = DEFAULT_EMBEDDING_KEY,
    ) -> dict[str, object]:
        fields = TRACK_SELECT_FIELDS if include_metadata else TRACK_SLIM_SELECT_FIELDS
        thresholds = dict(classifier_min_scores or {})
        where_sql, params = build_track_filter_sql(
            query=query,
            preset=preset,
            liked_only=liked_only,
            classifier_min_scores=thresholds,
        )
        order_sql = track_order_sql(classifier_min_scores=thresholds)
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

    def set_track_liked(self, track_id: int, liked: bool) -> Track:
        with self._write_lock, self.connect() as connection:
            row = connection.execute("SELECT id FROM tracks WHERE id = ?", (int(track_id),)).fetchone()
            if row is None:
                raise KeyError(f"Unknown track id: {track_id}")
            if liked:
                connection.execute(
                    """
                    INSERT INTO track_likes (track_id)
                    VALUES (?)
                    ON CONFLICT(track_id) DO UPDATE SET liked_at = CURRENT_TIMESTAMP
                    """,
                    (int(track_id),),
                )
            else:
                connection.execute("DELETE FROM track_likes WHERE track_id = ?", (int(track_id),))
            embedding_keys = _embedding_keys_for_track(connection, int(track_id))
        self._invalidate_embedding_cache_keys(embedding_keys)
        return self.get_track(track_id)

    def list_analysis_candidates(self, models: Iterable[str], *, limit: int | None = None) -> list[AnalysisCandidate]:
        selected = clean_analysis_models(models)
        if not selected:
            return []
        candidate_ids: dict[int, None] = {}
        per_model_limit = limit if limit is not None else None
        limit_sql, limit_params = _limit_sql(per_model_limit)
        with self.connect() as connection:
            for model in selected:
                rows = connection.execute(
                    missing_analysis_ids_sql(model, limit_sql),
                    missing_analysis_ids_params(model, limit_params),
                ).fetchall()
                for row in rows:
                    candidate_ids[int(row["id"])] = None
        if not candidate_ids:
            return []
        candidates: list[AnalysisCandidate] = []
        with self.connect() as connection:
            for ids in chunk_ids(tuple(candidate_ids), 500):
                placeholders = ", ".join("?" for _ in ids)
                rows = connection.execute(
                    analysis_candidate_select_sql(placeholders),
                    ids,
                ).fetchall()
                candidates.extend(row_to_analysis_candidate(row, selected) for row in rows)
        candidates.sort(key=lambda candidate: (candidate.artist or "", candidate.title or "", candidate.path))
        if limit is not None:
            return candidates[: max(0, int(limit))]
        return candidates

    def list_tracks_missing_classifier(self, classifier: str, *, limit: int | None = None) -> list[Track]:
        limit_sql, params = _limit_sql(limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN track_classifier_scores s
                  ON s.track_id = t.id AND s.classifier = ?
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE s.track_id IS NULL
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                {limit_sql}
                """,
                (classifier.strip(), DEFAULT_EMBEDDING_KEY, *params),
            ).fetchall()
        return [self._row_to_track(row, include_metadata=True) for row in rows]

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

    def library_summary(self, classifier_keys: Iterable[str] | None = None) -> dict[str, int]:
        cleaned_classifier_keys = sorted({key.strip() for key in (classifier_keys or []) if key.strip()})
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
            liked = int(connection.execute("SELECT COUNT(*) FROM track_likes").fetchone()[0])
            classifiers = 0
            if cleaned_classifier_keys:
                placeholders = ", ".join("?" for _ in cleaned_classifier_keys)
                classifiers = int(
                    connection.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM (
                            SELECT t.id
                            FROM tracks t
                            JOIN track_classifier_scores s ON s.track_id = t.id
                            WHERE s.classifier IN ({placeholders})
                            GROUP BY t.id
                            HAVING COUNT(DISTINCT s.classifier) = ?
                        )
                        """,
                        (*cleaned_classifier_keys, len(cleaned_classifier_keys)),
                    ).fetchone()[0]
                )
        return {
            "tracks": tracks,
            "sonara": sonara,
            "maest": maest,
            "mert": mert,
            "clap": clap,
            "liked": liked,
            "classifiers": classifiers,
        }

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
        if not np.isfinite(normalized).all():
            raise ValueError("Embedding vector must contain only finite values")
        norm = float(np.linalg.norm(normalized))
        if not np.isfinite(norm) or norm == 0:
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
            embedding_keys = _embedding_keys_for_track(connection, track_id)
        self._invalidate_embedding_cache_keys(embedding_keys)

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
            embedding_keys = _embedding_keys_for_track(connection, track_id)
        self._invalidate_embedding_cache_keys(embedding_keys)

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
            embedding_keys = _embedding_keys_for_track(connection, track_id)
        self._invalidate_embedding_cache_keys(embedding_keys)

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

    def reset_classifier_scores(self, classifiers: list[str]) -> dict[str, object]:
        cleaned = [classifier.strip() for classifier in classifiers if classifier.strip()]
        if not cleaned:
            return {"classifiers": [], "scores_deleted": 0}
        placeholders = ", ".join("?" for _ in cleaned)
        with self._write_lock, self.connect() as connection:
            cursor = connection.execute(
                f"DELETE FROM track_classifier_scores WHERE classifier IN ({placeholders})",
                tuple(cleaned),
            )
            deleted = cursor.rowcount
        return {"classifiers": cleaned, "scores_deleted": deleted}

    def relocate_library(self, old_root: str | Path, new_root: str | Path, *, apply: bool = False) -> dict[str, object]:
        old_root_text = _normalize_root(old_root)
        new_root_text = _normalize_root(new_root)
        if old_root_text == new_root_text:
            raise ValueError("Old and new library roots must be different")

        embedding_keys_to_invalidate: set[str] = set()
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
                    embedding_keys_to_invalidate.update(_embedding_keys_for_track(connection, int(change["track_id"])))
                    connection.execute(
                        "UPDATE tracks SET path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (change["new_path"], change["track_id"]),
                    )
        if apply and changes:
            self._invalidate_embedding_cache_keys(embedding_keys_to_invalidate)

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
        embedding_keys_to_invalidate: set[str] = set()
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
                embedding_keys_to_invalidate.update(_embedding_keys_for_track(connection, int(row["id"])))
                updated += 1
        if updated:
            self._invalidate_embedding_cache_keys(embedding_keys_to_invalidate)
        return {"adapter": adapter, "tracks_updated": updated, "embeddings_deleted": 0}

    def _reset_metadata_and_embedding_analysis(
        self,
        adapter: str,
        keys: tuple[str, ...],
        *,
        embedding_key: str,
    ) -> dict[str, object]:
        updated = 0
        embedding_keys_to_invalidate: set[str] = set()
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
                embedding_keys_to_invalidate.update(_embedding_keys_for_track(connection, int(row["id"])))
                updated += 1
            cursor = connection.execute("DELETE FROM embeddings WHERE embedding_key = ?", (embedding_key,))
            deleted = cursor.rowcount
        if updated or deleted:
            self._invalidate_embedding_cache_keys((*embedding_keys_to_invalidate, embedding_key))
        return {"adapter": adapter, "tracks_updated": updated, "embeddings_deleted": deleted}

    def _reset_sonara_analysis(self) -> dict[str, object]:
        updated = 0
        embedding_keys_to_invalidate: set[str] = set()
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
                embedding_keys_to_invalidate.update(_embedding_keys_for_track(connection, int(row["id"])))
                updated += 1
        if updated:
            self._invalidate_embedding_cache_keys(embedding_keys_to_invalidate)
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
            liked=bool(row["liked"]) if "liked" in row_keys else False,
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


def _embedding_keys_for_track(connection: sqlite3.Connection, track_id: int) -> tuple[str, ...]:
    rows = connection.execute(
        "SELECT embedding_key FROM embeddings WHERE track_id = ?",
        (int(track_id),),
    ).fetchall()
    return tuple(str(row["embedding_key"]) for row in rows)


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
