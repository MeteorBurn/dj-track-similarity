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
from .sonara_contract import (
    SONARA_ANALYSIS_SIGNATURE_KEY,
    feature_set_uses_sonara,
    sonara_analysis_signature_errors,
    sonara_analysis_is_current,
)


EMBEDDING_PRESENCE_FLAG_COLUMNS = {
    "maest": "has_maest_embedding",
    "mert": "has_mert_embedding",
    "muq": "has_muq_embedding",
    "clap": "has_clap_embedding",
}


def _delete_sonara_dependent_classifier_scores(connection, *, track_id: int | None = None) -> int:
    where_sql = " WHERE track_id = ?" if track_id is not None else ""
    params: tuple[object, ...] = (int(track_id),) if track_id is not None else ()
    rows = connection.execute(
        f"SELECT track_id, classifier, feature_set FROM track_classifier_scores{where_sql}",
        params,
    ).fetchall()
    targets = [
        (int(row["track_id"]), str(row["classifier"]))
        for row in rows
        if feature_set_uses_sonara(row["feature_set"])
    ]
    if targets:
        connection.executemany(
            "DELETE FROM track_classifier_scores WHERE track_id = ? AND classifier = ?",
            targets,
        )
    return len(targets)


class AnalysisRepository:
    def list_analysis_candidates(
        self,
        models: Iterable[str],
        *,
        limit: int | None = None,
        expected_sonara_signatures: dict[str, dict[str, object]] | None = None,
    ) -> list[AnalysisCandidate]:
        selected = clean_analysis_models(models)
        if not selected:
            return []
        if "sonara" in selected and not expected_sonara_signatures:
            from .sonara_features import sonara_analysis_signatures_for_outputs

            expected_sonara_signatures = sonara_analysis_signatures_for_outputs(("core",))
        candidate_ids: dict[int, set[str]] = {}
        per_model_limit = limit if limit is not None else None
        limit_sql, limit_params = _limit_sql(per_model_limit)
        sonara_signature_ids = {
            output: str(signature["signature_id"])
            for output, signature in (expected_sonara_signatures or {}).items()
            if signature.get("signature_id")
        }
        expected_core_signature = (expected_sonara_signatures or {}).get("core")
        with self.connect() as connection:
            for model in selected:
                rows = connection.execute(
                    missing_analysis_ids_sql(model, limit_sql, sonara_signature_ids=sonara_signature_ids),
                    missing_analysis_ids_params(
                        model,
                        limit_params,
                        sonara_signature_ids=sonara_signature_ids,
                    ),
                ).fetchall()
                for row in rows:
                    candidate_ids.setdefault(int(row["id"]), set()).add(model)
            if not candidate_ids:
                return []
            candidates: list[AnalysisCandidate] = []
            for ids in chunk_ids(tuple(candidate_ids), 500):
                placeholders = ", ".join("?" for _ in ids)
                rows = connection.execute(
                    analysis_candidate_select_sql(placeholders),
                    ids,
                ).fetchall()
                candidates.extend(
                    row_to_analysis_candidate(
                        row,
                        selected,
                        expected_sonara_signature=expected_core_signature,
                        force_missing_sonara="sonara" in candidate_ids[int(row["id"])],
                    )
                    for row in rows
                )
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
        provenance: dict[str, object] | None = None,
        analysis_signature: dict[str, object] | None = None,
    ) -> None:
        with self._write_lock, self.connect() as connection:
            metadata = self._metadata_for_track_update(connection, track_id)
            metadata["sonara_features"] = features
            metadata["sonara_model"] = model_name
            if provenance is not None:
                metadata["sonara_provenance"] = provenance
            else:
                metadata.pop("sonara_provenance", None)
            if analysis_signature is not None:
                metadata[SONARA_ANALYSIS_SIGNATURE_KEY] = analysis_signature
            else:
                metadata.pop(SONARA_ANALYSIS_SIGNATURE_KEY, None)
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
            _delete_sonara_dependent_classifier_scores(connection, track_id=track_id)
        self._invalidate_embedding_cache_keys(embedding_keys)
        self._invalidate_sonara_feature_cache()

    def save_sonara_timeline(
        self,
        track_id: int,
        timeline: dict[str, object],
        *,
        provenance: dict[str, object] | None,
        analysis_signature: dict[str, object],
    ) -> None:
        fields = sorted(timeline)
        if not fields:
            raise ValueError("SONARA Timeline output did not contain any timeline fields")
        signature_id = str(analysis_signature.get("signature_id") or "").strip()
        if not signature_id:
            raise ValueError("SONARA Timeline analysis signature is missing signature_id")
        with self._write_lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO timeline.sonara_timeline (
                    track_id, fields_json, payload_json, analysis_signature_id,
                    analysis_signature_json, provenance_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(track_id) DO UPDATE SET
                    fields_json = excluded.fields_json,
                    payload_json = excluded.payload_json,
                    analysis_signature_id = excluded.analysis_signature_id,
                    analysis_signature_json = excluded.analysis_signature_json,
                    provenance_json = excluded.provenance_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    int(track_id),
                    metadata_to_json(fields, sort_keys=False),
                    metadata_to_json(timeline, sort_keys=False),
                    signature_id,
                    metadata_to_json(analysis_signature, sort_keys=False),
                    metadata_to_json(provenance or {}, sort_keys=False),
                ),
            )
        self._invalidate_embedding_cache()

    def load_sonara_timeline(self, track_id: int) -> dict[str, object] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json, analysis_signature_json
                FROM timeline.sonara_timeline
                WHERE track_id = ?
                """,
                (int(track_id),),
            ).fetchone()
        if row is None:
            return None
        signature = metadata_from_json(row["analysis_signature_json"])
        if sonara_analysis_signature_errors(signature):
            return None
        timeline = metadata_from_json(row["payload_json"])
        return timeline if isinstance(timeline, dict) else None

    def save_sonara_representations(
        self,
        track_id: int,
        *,
        embedding: np.ndarray,
        fingerprint: dict[str, object],
        embedding_version: str | None,
        fingerprint_version: str | None,
        model_name: str,
        provenance: dict[str, object] | None,
        analysis_signature: dict[str, object],
    ) -> None:
        vector = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if not vector.size or not np.isfinite(vector).all():
            raise ValueError("SONARA embedding must be a non-empty finite vector")
        signature_id = str(analysis_signature.get("signature_id") or "").strip()
        if not signature_id:
            raise ValueError("SONARA Representations analysis signature is missing signature_id")
        embedding_metadata = {
            "version": embedding_version,
            "dtype": "float32",
            "provenance": provenance or {},
            "analysis_signature": analysis_signature,
        }
        fingerprint_metadata = {
            "provenance": provenance or {},
            "analysis_signature": analysis_signature,
        }
        with self._write_lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO representations.embeddings (
                    track_id, embedding_key, model_name, dim, vector, normalization,
                    analysis_signature_id, metadata_json, updated_at
                )
                VALUES (?, 'sonara', ?, ?, ?, 'none', ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(track_id, embedding_key) DO UPDATE SET
                    model_name = excluded.model_name,
                    dim = excluded.dim,
                    vector = excluded.vector,
                    normalization = excluded.normalization,
                    analysis_signature_id = excluded.analysis_signature_id,
                    metadata_json = excluded.metadata_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    int(track_id),
                    model_name,
                    int(vector.size),
                    vector.tobytes(),
                    signature_id,
                    metadata_to_json(embedding_metadata, sort_keys=False),
                ),
            )
            connection.execute(
                """
                INSERT INTO representations.fingerprints (
                    track_id, fingerprint_key, model_name, version, payload_json,
                    analysis_signature_id, metadata_json, updated_at
                )
                VALUES (?, 'fingerprint', ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(track_id, fingerprint_key) DO UPDATE SET
                    model_name = excluded.model_name,
                    version = excluded.version,
                    payload_json = excluded.payload_json,
                    analysis_signature_id = excluded.analysis_signature_id,
                    metadata_json = excluded.metadata_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    int(track_id),
                    model_name,
                    fingerprint_version,
                    metadata_to_json(fingerprint, sort_keys=False),
                    signature_id,
                    metadata_to_json(fingerprint_metadata, sort_keys=False),
                ),
            )
        self._invalidate_embedding_cache()

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
            connection.execute("DELETE FROM representations.embeddings")
            connection.execute("DELETE FROM representations.fingerprints")
            connection.execute("DELETE FROM timeline.sonara_timeline")
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
        keys = (
            "sonara_features",
            "sonara_features_file",
            "sonara_model",
            "sonara_provenance",
            SONARA_ANALYSIS_SIGNATURE_KEY,
        )
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
            timeline_deleted = connection.execute("DELETE FROM timeline.sonara_timeline").rowcount
            sonara_embeddings_deleted = connection.execute(
                "DELETE FROM representations.embeddings WHERE embedding_key = 'sonara'"
            ).rowcount
            fingerprints_deleted = connection.execute(
                "DELETE FROM representations.fingerprints WHERE fingerprint_key = 'fingerprint'"
            ).rowcount
            classifier_scores_deleted = _delete_sonara_dependent_classifier_scores(connection)
        if updated or timeline_deleted or sonara_embeddings_deleted or fingerprints_deleted or classifier_scores_deleted:
            embedding_keys_to_invalidate.add("sonara")
            self._invalidate_embedding_cache_keys(embedding_keys_to_invalidate)
            self._invalidate_sonara_feature_cache()
        return {
            "adapter": "sonara",
            "tracks_updated": updated,
            "embeddings_deleted": sonara_embeddings_deleted,
            "timeline_deleted": timeline_deleted,
            "fingerprints_deleted": fingerprints_deleted,
            "classifier_scores_deleted": classifier_scores_deleted,
        }

    def load_embedding_matrix(
        self,
        embedding_key: str = DEFAULT_EMBEDDING_KEY,
        *,
        include_metadata: bool = False,
    ) -> tuple[list[Track], np.ndarray]:
        cache_key = (embedding_key, bool(include_metadata))
        with self._cache_lock:
            cached = self._embedding_matrix_cache.get(cache_key)
            if cached is not None:
                return cached
        fields = (
            f"{TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR}, t.metadata_json"
            if include_metadata
            else TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR
        )
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {fields}
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
                self._embedding_matrix_cache[cache_key] = result
            return result
        tracks = [self._row_to_track(row, include_metadata=include_metadata) for row in rows]
        vectors = [np.frombuffer(row["vector"], dtype=np.float32).copy() for row in rows]
        result = (tracks, np.vstack(vectors).astype(np.float32))
        with self._cache_lock:
            self._embedding_matrix_cache[cache_key] = result
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
            if not sonara_analysis_is_current(metadata):
                continue
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
        source_table = "representations.embeddings" if embedding_key == "sonara" else "embeddings"
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT vector
                FROM {source_table}
                WHERE track_id = ? AND embedding_key = ?
                """,
                (int(track_id), embedding_key),
            ).fetchone()
        if row is None:
            return None
        return np.frombuffer(row["vector"], dtype=np.float32).copy()
