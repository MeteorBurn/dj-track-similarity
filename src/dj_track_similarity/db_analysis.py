from __future__ import annotations

from typing import Iterable

import numpy as np

from .db_analysis_candidates import (
    analysis_candidate_select_sql,
    chunk_ids,
    clean_analysis_models,
    missing_analysis_ids_params,
    missing_analysis_ids_sql,
    row_to_analysis_candidate,
)
from .db_repository_utils import (
    DEFAULT_EMBEDDING_KEY,
    MAEST_EMBEDDING_KEY,
    _embedding_keys_for_track,
    _limit_sql,
    _set_maest_metadata,
)
from .db_schema import MAEST_HAS_GENRES_SQL, TRACK_SELECT_FIELDS, TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR
from .db_search_fts import rebuild_track_search_fts, upsert_track_search_fts
from .metadata_payload import clean_maest_genre_label, metadata_from_json, metadata_to_json, optional_float, string_or_none
from .models import AnalysisCandidate, Track


EMBEDDING_PRESENCE_FLAG_COLUMNS = {
    "maest": "has_maest_embedding",
    "mert": "has_mert_embedding",
    "muq": "has_muq_embedding",
    "clap": "has_clap_embedding",
}


class AnalysisRepository:
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
            flag_column = EMBEDDING_PRESENCE_FLAG_COLUMNS.get(embedding_key)
            if flag_column is not None:
                connection.execute(f"UPDATE tracks SET {flag_column} = 1 WHERE id = ?", (track_id,))
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
            upsert_track_search_fts(connection, track_id)
            embedding_keys = _embedding_keys_for_track(connection, track_id)
        self._invalidate_embedding_cache_keys(embedding_keys)
        self._invalidate_sonara_feature_cache()

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
                    has_sonara_analysis = 1,
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
            upsert_track_search_fts(connection, track_id)
            embedding_keys = _embedding_keys_for_track(connection, track_id)
        self._invalidate_embedding_cache_keys(embedding_keys)
        self._invalidate_sonara_feature_cache()

    def reset_analysis(self, adapter: str) -> dict[str, object]:
        adapter = adapter.strip().lower()
        if adapter in {"mert", "muq", "clap"}:
            with self._write_lock, self.connect() as connection:
                cursor = connection.execute("DELETE FROM embeddings WHERE embedding_key = ?", (adapter,))
                deleted = cursor.rowcount
                flag_column = EMBEDDING_PRESENCE_FLAG_COLUMNS[adapter]
                connection.execute(f"UPDATE tracks SET {flag_column} = 0 WHERE {flag_column} != 0")
            self._invalidate_embedding_cache(adapter)
            return {"adapter": adapter, "tracks_updated": 0, "embeddings_deleted": deleted}
        if adapter == "maest":
            return self._reset_metadata_and_embedding_analysis(
                adapter,
                ("maest_genres", "maest_model", "maest_syncopated_rhythm"),
                embedding_key=MAEST_EMBEDDING_KEY,
                flag_column=EMBEDDING_PRESENCE_FLAG_COLUMNS[MAEST_EMBEDDING_KEY],
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
            rebuild_track_search_fts(connection)
        self._invalidate_embedding_cache()
        self._invalidate_sonara_feature_cache()
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
                upsert_track_search_fts(connection, int(row["id"]))
                embedding_keys_to_invalidate.update(_embedding_keys_for_track(connection, int(row["id"])))
                updated += 1
        if updated:
            self._invalidate_embedding_cache_keys(embedding_keys_to_invalidate)
            self._invalidate_sonara_feature_cache()
        return {"adapter": adapter, "tracks_updated": updated, "embeddings_deleted": 0}

    def _reset_metadata_and_embedding_analysis(
        self,
        adapter: str,
        keys: tuple[str, ...],
        *,
        embedding_key: str,
        flag_column: str,
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
                upsert_track_search_fts(connection, int(row["id"]))
                embedding_keys_to_invalidate.update(_embedding_keys_for_track(connection, int(row["id"])))
                updated += 1
            cursor = connection.execute("DELETE FROM embeddings WHERE embedding_key = ?", (embedding_key,))
            deleted = cursor.rowcount
            connection.execute(f"UPDATE tracks SET {flag_column} = 0 WHERE {flag_column} != 0")
        if updated or deleted:
            self._invalidate_embedding_cache_keys((*embedding_keys_to_invalidate, embedding_key))
            self._invalidate_sonara_feature_cache()
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
                upsert_track_search_fts(connection, int(row["id"]))
                embedding_keys_to_invalidate.update(_embedding_keys_for_track(connection, int(row["id"])))
                updated += 1
            connection.execute("UPDATE tracks SET has_sonara_analysis = 0 WHERE has_sonara_analysis != 0")
        if updated:
            self._invalidate_embedding_cache_keys(embedding_keys_to_invalidate)
            self._invalidate_sonara_feature_cache()
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

    def load_sonara_feature_rows(self) -> tuple[list[Track], list[dict[str, object]]]:
        with self._cache_lock:
            cached = self._sonara_feature_row_cache
            if cached is not None:
                return cached
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE t.has_sonara_analysis = 1
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                """,
                (DEFAULT_EMBEDDING_KEY,),
            ).fetchall()
        tracks: list[Track] = []
        features_by_track: list[dict[str, object]] = []
        for row in rows:
            track = self._row_to_track(row, include_metadata=True)
            metadata = track.metadata or {}
            features = metadata.get("sonara_features")
            if not isinstance(features, dict):
                continue
            tracks.append(track)
            features_by_track.append(features)
        result = (tracks, features_by_track)
        with self._cache_lock:
            self._sonara_feature_row_cache = result
        return result

    def embedding_vector(self, track_id: int, embedding_key: str = DEFAULT_EMBEDDING_KEY) -> np.ndarray | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT vector
                FROM embeddings
                WHERE track_id = ? AND embedding_key = ?
                """,
                (int(track_id), embedding_key),
            ).fetchone()
        if row is None:
            return None
        return np.frombuffer(row["vector"], dtype=np.float32).copy()
