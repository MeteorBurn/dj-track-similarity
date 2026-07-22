from __future__ import annotations

import sqlite3
from typing import Iterable, Mapping

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
from .sonara_storage import (
    SonaraAnalysisStorage,
    SonaraCoreStorage,
    SonaraRepresentationsStorage,
    SonaraTimelineStorage,
)


EMBEDDING_PRESENCE_FLAG_COLUMNS = {
    "maest": "has_maest_embedding",
    "mert": "has_mert_embedding",
    "muq": "has_muq_embedding",
    "clap": "has_clap_embedding",
}


def _classifier_ready_sql(
    required_inputs: Iterable[str],
    sonara_signature: dict[str, object] | None,
) -> tuple[str, tuple[object, ...]]:
    required = {str(value).strip().lower() for value in required_inputs}
    unknown = required - {"sonara", "mert", "maest", "clap"}
    if unknown:
        raise ValueError(f"Unsupported classifier inputs: {', '.join(sorted(unknown))}")
    conditions: list[str] = []
    params: list[object] = []
    if "sonara" in required:
        signature_id = str((sonara_signature or {}).get("signature_id") or "")
        if not signature_id:
            raise ValueError("SONARA classifier readiness requires an analysis signature")
        conditions.append(
            "t.has_sonara_analysis = 1 AND "
            "COALESCE(json_extract(t.metadata_json, '$.sonara_analysis_signature.signature_id'), '') = ?"
        )
        params.append(signature_id)
    for source in ("mert", "maest", "clap"):
        if source in required:
            conditions.append(f"t.has_{source}_embedding = 1")
    return (" AND ".join(f"({condition})" for condition in conditions) or "1 = 1", tuple(params))


def _classifier_sonara_feature_ready_sql(
    feature_names: Iterable[str],
) -> tuple[str, tuple[object, ...]]:
    conditions: list[str] = []
    params: list[object] = []
    for name in feature_names:
        text = str(name)
        if not text.startswith("sonara:"):
            continue
        key = text.partition(":")[2]
        field, separator, index_text = key.rpartition(":")
        indexed = bool(separator and index_text.isdigit())
        field_name = field if indexed else key
        escaped_field = field_name.replace("\\", "\\\\").replace('"', '\\"')
        base_path = f'$.sonara_features."{escaped_field}"'
        if indexed:
            index = int(index_text)
            payload_path = f"{base_path}.value[{index}]"
            legacy_path = f"{base_path}[{index}]"
        else:
            payload_path = f"{base_path}.value"
            legacy_path = base_path
        conditions.append(
            "COALESCE(json_type(t.metadata_json, ?), json_type(t.metadata_json, ?)) "
            "IN ('integer', 'real', 'true', 'false')"
        )
        params.extend((payload_path, legacy_path))
    return (" AND ".join(f"({condition})" for condition in conditions) or "1 = 1", tuple(params))


def _classifier_sonara_features_are_present(track: Track, feature_names: Iterable[str]) -> bool:
    metadata = track.metadata if isinstance(track.metadata, Mapping) else {}
    features = metadata.get("sonara_features")
    sonara_names = tuple(name for name in feature_names if str(name).startswith("sonara:"))
    if not sonara_names:
        return True
    if not isinstance(features, Mapping):
        return False
    for name in sonara_names:
        key = str(name).partition(":")[2]
        field, separator, index_text = key.rpartition(":")
        raw = features.get(field if separator and index_text.isdigit() else key)
        if isinstance(raw, Mapping):
            raw = raw.get("value")
        if separator and index_text.isdigit():
            if not isinstance(raw, (list, tuple)):
                return False
            index = int(index_text)
            if index >= len(raw) or optional_float(raw[index]) is None:
                return False
        elif optional_float(raw) is None:
            return False
    return True


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
        if selected == ["sonara"]:
            candidates.sort(key=lambda candidate: candidate.path)
        else:
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

    def classifier_candidate_readiness(
        self,
        classifier: str,
        *,
        model_id: str,
        required_inputs: Iterable[str],
        sonara_signature: dict[str, object] | None = None,
        feature_names: Iterable[str] = (),
    ) -> dict[str, int]:
        required = tuple(required_inputs)
        names = tuple(str(name) for name in feature_names)
        ready_sql, ready_params = _classifier_ready_sql(required, sonara_signature)
        feature_sql, feature_params = _classifier_sonara_feature_ready_sql(names)
        with self.connect() as connection:
            row = connection.execute(
                f"""
                WITH candidate_tracks AS (
                    SELECT t.*
                    FROM tracks t
                    LEFT JOIN track_classifier_scores s
                      ON s.track_id = t.id AND s.classifier = ?
                    WHERE s.track_id IS NULL OR s.model_id != ?
                )
                SELECT
                    COUNT(*) AS candidates,
                    COALESCE(
                        SUM(CASE WHEN ({ready_sql}) AND ({feature_sql}) THEN 1 ELSE 0 END),
                        0
                    ) AS ready
                FROM candidate_tracks t
                """,
                (
                    classifier.strip(),
                    str(model_id),
                    *ready_params,
                    *feature_params,
                ),
            ).fetchone()
        candidates = int(row["candidates"] or 0)
        ready = int(row["ready"] or 0)
        return {"candidates": candidates, "ready": ready, "not_ready": candidates - ready}

    def list_classifier_candidates(
        self,
        classifier: str,
        *,
        model_id: str,
        required_inputs: Iterable[str],
        sonara_signature: dict[str, object] | None = None,
        feature_names: Iterable[str] = (),
        limit: int | None = None,
    ) -> list[Track]:
        ready_sql, ready_params = _classifier_ready_sql(required_inputs, sonara_signature)
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN track_classifier_scores s
                  ON s.track_id = t.id AND s.classifier = ?
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE (s.track_id IS NULL OR s.model_id != ?)
                  AND {ready_sql}
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                """,
                (classifier.strip(), DEFAULT_EMBEDDING_KEY, str(model_id), *ready_params),
            ).fetchall()
        tracks = [
            track
            for row in rows
            if _classifier_sonara_features_are_present(
                track := self._row_to_track(row, include_metadata=True),
                feature_names,
            )
        ]
        return tracks if limit is None else tracks[: max(0, int(limit))]

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
        error = self.save_sonara_analysis_batch(
            [
                SonaraAnalysisStorage(
                    track_id=track_id,
                    core=SonaraCoreStorage(
                        features=features,
                        bpm=bpm,
                        musical_key=musical_key,
                        energy=energy,
                        duration=duration,
                        model_name=model_name,
                        provenance=provenance,
                        analysis_signature=analysis_signature,
                    ),
                )
            ]
        )[0]
        if error is not None:
            raise error

    def save_sonara_timeline(
        self,
        track_id: int,
        timeline: dict[str, object],
        *,
        provenance: dict[str, object] | None,
        analysis_signature: dict[str, object],
    ) -> None:
        error = self.save_sonara_analysis_batch(
            [
                SonaraAnalysisStorage(
                    track_id=track_id,
                    timeline=SonaraTimelineStorage(
                        timeline=timeline,
                        provenance=provenance,
                        analysis_signature=analysis_signature,
                    ),
                )
            ]
        )[0]
        if error is not None:
            raise error

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
        error = self.save_sonara_analysis_batch(
            [
                SonaraAnalysisStorage(
                    track_id=track_id,
                    representations=SonaraRepresentationsStorage(
                        embedding=embedding,
                        fingerprint=fingerprint,
                        embedding_version=embedding_version,
                        fingerprint_version=fingerprint_version,
                        model_name=model_name,
                        provenance=provenance,
                        analysis_signature=analysis_signature,
                    ),
                )
            ]
        )[0]
        if error is not None:
            raise error

    def save_sonara_analysis_batch(
        self,
        analyses: Iterable[SonaraAnalysisStorage],
    ) -> list[Exception | None]:
        """Persist a native SONARA batch in one transaction with per-track rollback."""

        pending = list(analyses)
        if not pending:
            return []
        errors: list[Exception | None] = []
        embedding_keys_to_invalidate: set[str] = set()
        invalidate_all_embeddings = False
        invalidate_sonara_features = False
        with self._write_lock, self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for index, analysis in enumerate(pending):
                savepoint = f"sonara_batch_item_{index}"
                connection.execute(f"SAVEPOINT {savepoint}")
                item_embedding_keys: tuple[str, ...] = ()
                try:
                    if analysis.core is not None:
                        item_embedding_keys = self._save_sonara_core(
                            connection,
                            analysis.track_id,
                            analysis.core,
                        )
                    if analysis.timeline is not None:
                        self._save_sonara_timeline(connection, analysis.track_id, analysis.timeline)
                    if analysis.representations is not None:
                        self._save_sonara_representations(
                            connection,
                            analysis.track_id,
                            analysis.representations,
                        )
                except Exception as error:
                    connection.execute(f"ROLLBACK TO {savepoint}")
                    connection.execute(f"RELEASE {savepoint}")
                    errors.append(error)
                    continue
                connection.execute(f"RELEASE {savepoint}")
                errors.append(None)
                embedding_keys_to_invalidate.update(item_embedding_keys)
                invalidate_sonara_features = invalidate_sonara_features or analysis.core is not None
                invalidate_all_embeddings = invalidate_all_embeddings or (
                    analysis.timeline is not None or analysis.representations is not None
                )

        if invalidate_all_embeddings:
            self._invalidate_embedding_cache()
        else:
            self._invalidate_embedding_cache_keys(embedding_keys_to_invalidate)
        if invalidate_sonara_features:
            self._invalidate_sonara_feature_cache()
        return errors

    def _save_sonara_core(
        self,
        connection: sqlite3.Connection,
        track_id: int,
        core: SonaraCoreStorage,
    ) -> tuple[str, ...]:
        metadata = self._metadata_for_track_update(connection, track_id)
        metadata["sonara_features"] = core.features
        metadata["sonara_model"] = core.model_name
        if core.provenance is not None:
            metadata["sonara_provenance"] = core.provenance
        else:
            metadata.pop("sonara_provenance", None)
        if core.analysis_signature is not None:
            metadata[SONARA_ANALYSIS_SIGNATURE_KEY] = core.analysis_signature
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
                optional_float(core.bpm),
                core.musical_key,
                optional_float(core.energy),
                optional_float(core.duration),
                metadata_to_json(metadata, sort_keys=False),
                track_id,
            ),
        )
        upsert_track_search_fts(connection, track_id)
        embedding_keys = tuple(_embedding_keys_for_track(connection, track_id))
        _delete_sonara_dependent_classifier_scores(connection, track_id=track_id)
        return embedding_keys

    @staticmethod
    def _save_sonara_timeline(
        connection: sqlite3.Connection,
        track_id: int,
        timeline: SonaraTimelineStorage,
    ) -> None:
        fields = sorted(timeline.timeline)
        if not fields:
            raise ValueError("SONARA Timeline output did not contain any timeline fields")
        signature_id = str(timeline.analysis_signature.get("signature_id") or "").strip()
        if not signature_id:
            raise ValueError("SONARA Timeline analysis signature is missing signature_id")
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
                metadata_to_json(timeline.timeline, sort_keys=False),
                signature_id,
                metadata_to_json(timeline.analysis_signature, sort_keys=False),
                metadata_to_json(timeline.provenance or {}, sort_keys=False),
            ),
        )

    @staticmethod
    def _save_sonara_representations(
        connection: sqlite3.Connection,
        track_id: int,
        representations: SonaraRepresentationsStorage,
    ) -> None:
        vector = np.asarray(representations.embedding, dtype=np.float32).reshape(-1)
        if not vector.size or not np.isfinite(vector).all():
            raise ValueError("SONARA embedding must be a non-empty finite vector")
        signature_id = str(representations.analysis_signature.get("signature_id") or "").strip()
        if not signature_id:
            raise ValueError("SONARA Representations analysis signature is missing signature_id")
        embedding_metadata = {
            "version": representations.embedding_version,
            "dtype": "float32",
            "provenance": representations.provenance or {},
            "analysis_signature": representations.analysis_signature,
        }
        fingerprint_metadata = {
            "provenance": representations.provenance or {},
            "analysis_signature": representations.analysis_signature,
        }
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
                representations.model_name,
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
                representations.model_name,
                representations.fingerprint_version,
                metadata_to_json(representations.fingerprint, sort_keys=False),
                signature_id,
                metadata_to_json(fingerprint_metadata, sort_keys=False),
            ),
        )

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

    def sonara_migration_blockers(
        self,
        expected_signatures: dict[str, dict[str, object]],
    ) -> dict[str, int]:
        """Count persisted SONARA rows that belong to a different analysis contract."""

        signature_ids = {
            output: str(signature.get("signature_id") or "")
            for output, signature in expected_signatures.items()
        }
        with self.connect() as connection:
            core_id = signature_ids.get("core", "")
            timeline_id = signature_ids.get("timeline", "")
            representations_id = signature_ids.get("representations", "")
            core = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM tracks
                    WHERE json_type(metadata_json, '$.sonara_features') IS NOT NULL
                      AND COALESCE(json_extract(metadata_json, '$.sonara_analysis_signature.signature_id'), '') != ?
                    """,
                    (core_id,),
                ).fetchone()[0]
            )
            timeline = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM timeline.sonara_timeline
                    WHERE COALESCE(analysis_signature_id, '') != ?
                    """,
                    (timeline_id,),
                ).fetchone()[0]
            )
            representations = int(
                connection.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM representations.embeddings
                         WHERE embedding_key = 'sonara' AND COALESCE(analysis_signature_id, '') != ?)
                      + (SELECT COUNT(*) FROM representations.fingerprints
                         WHERE fingerprint_key = 'fingerprint' AND COALESCE(analysis_signature_id, '') != ?)
                    """,
                    (representations_id, representations_id),
                ).fetchone()[0]
            )
        return {
            "core": core,
            "timeline": timeline,
            "representations": representations,
            "total": core + timeline + representations,
        }

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

    def delete_stale_classifier_scores(
        self,
        classifier: str,
        *,
        current_model_id: str,
        current_feature_set: str,
    ) -> int:
        """Delete score rows for *classifier* whose model_id or feature_set no longer matches.

        Only rows for the given classifier key are touched; other classifiers are
        never affected.  Returns the number of rows deleted.
        """
        key = classifier.strip()
        with self._write_lock, self.connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM track_classifier_scores
                WHERE classifier = ?
                  AND (model_id != ? OR feature_set != ?)
                """,
                (key, str(current_model_id), str(current_feature_set)),
            )
            return cursor.rowcount

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


# ---------------------------------------------------------------------------
# v7 schema helpers — standalone functions, no dependency on LibraryDatabase
# ---------------------------------------------------------------------------

import hashlib
import json
import struct


def upsert_sonara_contract_v7(
    connection: sqlite3.Connection,
    model_name: str,
    model_version: str,
    release_hash: str,
) -> str:
    """Compute the SONARA Core contract hash, insert into ``contracts`` if new.

    Returns the ``contract_hash`` string (``"sha256:<hex>"``).
    """
    from datetime import datetime, timezone

    payload: dict[str, object] = {
        "analysis_family": "sonara",
        "output_kind": "core",
        "model_name": model_name,
        "model_version": model_version,
        "sonara_package_version": "0.2.9",
        "upstream_schema_version": 4,
        "analysis_mode": "playlist",
        "sample_rate_hz": 22050,
        "bpm_min": 70,
        "bpm_max": 180,
        "project_feature_revision": 5,
        "decoder_backend": "sonara-symphonia",
        "execution_path": "analyze_batch",
        "release_hash": release_hash,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    contract_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    existing = connection.execute(
        "SELECT contract_hash FROM contracts WHERE contract_hash = ?",
        (contract_hash,),
    ).fetchone()
    if existing is None:
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """
            INSERT INTO contracts (
                contract_hash, analysis_family, output_kind,
                model_name, model_version, release_hash,
                canonical_payload_json, created_at
            ) VALUES (?, 'sonara', 'core', ?, ?, ?, ?, ?)
            """,
            (contract_hash, model_name, model_version, release_hash, canonical, now),
        )

    return contract_hash


def upsert_maest_contract_v7(
    connection: sqlite3.Connection,
    model_name: str,
    model_version: str,
    dim: int | None,
    output_kind: str,
) -> str:
    """Compute a MAEST contract hash and INSERT OR IGNORE into ``contracts``.

    ``output_kind`` must be ``'analysis'`` (for scores) or ``'embedding'``.
    ``dim`` is required for ``output_kind='embedding'`` and should be ``None``
    for ``output_kind='analysis'``.

    Returns the ``contract_hash`` string (``"sha256:<hex>"``).
    """
    from datetime import datetime, timezone

    payload: dict[str, object] = {
        "analysis_family": "maest",
        "output_kind": output_kind,
        "model_name": model_name,
        "model_version": model_version,
        "dim": dim,
        "encoding": "float32-le" if output_kind == "embedding" else None,
        "normalization": "none" if output_kind == "embedding" else None,
        "release_hash": None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    contract_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    existing = connection.execute(
        "SELECT contract_hash FROM contracts WHERE contract_hash = ?",
        (contract_hash,),
    ).fetchone()
    if existing is None:
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """
            INSERT INTO contracts (
                contract_hash, analysis_family, output_kind,
                model_name, model_version, release_hash,
                canonical_payload_json, created_at
            ) VALUES (?, 'maest', ?, ?, ?, NULL, ?, ?)
            """,
            (contract_hash, output_kind, model_name, model_version, canonical, now),
        )

    return contract_hash


def save_maest_scores_v7(
    connection: sqlite3.Connection,
    track_id: int,
    content_generation: int,
    contract_hash: str,
    syncopated_rhythm: int | None,
    genres_json: str,
    analyzed_at: str,
) -> None:
    """Write one MAEST scores row to the v7 Core ``maest_scores`` table.

    ``genres_json`` must be a valid JSON array string, e.g.::

        '[{"rank": 1, "genre_name": "techno", "score": 0.85}]'

    ``syncopated_rhythm`` must be 0, 1, or None.

    This function does NOT accept an embedding parameter — MAEST embeddings
    are stored in the artifacts sidecar via ``save_maest_embedding_v7()``.
    """
    import json as _json

    # Validate genres_json is a JSON array
    try:
        parsed = _json.loads(genres_json)
    except _json.JSONDecodeError as exc:
        raise ValueError(f"save_maest_scores_v7: genres_json is not valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise ValueError(
            f"save_maest_scores_v7: genres_json must be a JSON array, got {type(parsed).__name__}"
        )

    with connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO maest_scores (
                track_id, content_generation, contract_hash,
                syncopated_rhythm, genres_json, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(track_id),
                int(content_generation),
                contract_hash,
                syncopated_rhythm,
                genres_json,
                analyzed_at,
            ),
        )


def save_maest_embedding_v7(
    artifacts_connection: sqlite3.Connection,
    track_id: int,
    track_uuid: str,
    content_generation: int,
    contract_hash: str,
    embedding: "object",
    normalization: str,
    analyzed_at: str,
) -> None:
    """Write one MAEST embedding row to the artifacts sidecar ``maest_embeddings`` table.

    ``embedding`` may be a numpy array or any sequence of floats; it is packed
    to little-endian float32 bytes (``<f4``).

    ``normalization`` must be ``'none'`` or ``'l2'``; raises ``ValueError``
    otherwise.

    This function writes to the **artifacts sidecar**, NOT to the Core DB.
    """
    import numpy as np

    if normalization not in ("none", "l2"):
        raise ValueError(
            f"save_maest_embedding_v7: normalization must be 'none' or 'l2', got {normalization!r}"
        )

    arr = np.asarray(embedding, dtype="<f4")
    if arr.ndim != 1:
        raise ValueError(
            f"save_maest_embedding_v7: embedding must be 1-D, got shape {arr.shape}"
        )
    dim = int(arr.shape[0])
    if dim <= 0:
        raise ValueError(
            f"save_maest_embedding_v7: embedding must have at least 1 element, got {dim}"
        )
    embedding_blob = arr.tobytes()

    with artifacts_connection:
        artifacts_connection.execute(
            """
            INSERT OR REPLACE INTO maest_embeddings (
                track_id, track_uuid, content_generation, contract_hash,
                dim, normalization, embedding_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(track_id),
                track_uuid,
                int(content_generation),
                contract_hash,
                dim,
                normalization,
                embedding_blob,
                analyzed_at,
            ),
        )


def save_sonara_row_v7(
    connection: sqlite3.Connection,
    track_id: int,
    content_generation: int,
    contract_hash: str,
    sonara_output: dict[str, object],
    analyzed_at: str,
) -> None:
    """Write one SONARA Core row to the v7 ``sonara`` table.

    ``sonara_output`` is a flat dict whose keys match the column names defined
    in ``db_schema_v7.py``.  The three timbre BLOBs are required:

    - ``mfcc_mean_blob``: 13 float32 values → 52 bytes
    - ``chroma_mean_blob``: 12 float32 values → 48 bytes
    - ``spectral_contrast_mean_blob``: 7 float32 values → 28 bytes

    Each BLOB may be supplied as ``bytes`` (already packed) or as a sequence of
    floats (packed here with ``struct.pack('<Nf', ...)``.

    Raises ``ValueError`` if any BLOB is missing or has the wrong byte length.
    """

    def _require_blob(key: str, expected_floats: int) -> bytes:
        raw = sonara_output.get(key)
        expected_bytes = expected_floats * 4
        if raw is None:
            raise ValueError(
                f"save_sonara_row_v7: '{key}' is required but was None"
            )
        if isinstance(raw, (bytes, bytearray, memoryview)):
            blob = bytes(raw)
        else:
            # Treat as a sequence of floats and pack
            try:
                values = list(raw)  # type: ignore[arg-type]
            except TypeError:
                raise ValueError(
                    f"save_sonara_row_v7: '{key}' must be bytes or a sequence of floats"
                )
            if len(values) != expected_floats:
                raise ValueError(
                    f"save_sonara_row_v7: '{key}' must have {expected_floats} values, "
                    f"got {len(values)}"
                )
            blob = struct.pack(f"<{expected_floats}f", *values)
        if len(blob) != expected_bytes:
            raise ValueError(
                f"save_sonara_row_v7: '{key}' must be {expected_bytes} bytes, "
                f"got {len(blob)}"
            )
        return blob

    mfcc_blob = _require_blob("mfcc_mean_blob", 13)
    chroma_blob = _require_blob("chroma_mean_blob", 12)
    contrast_blob = _require_blob("spectral_contrast_mean_blob", 7)

    def _g(key: str) -> object:
        return sonara_output.get(key)

    connection.execute(
        """
        INSERT OR REPLACE INTO sonara (
            track_id, content_generation, contract_hash,
            -- Rhythm
            detected_bpm, raw_bpm, bpm_confidence,
            onset_density_per_second, beat_count, tempo_variability,
            beat_grid_offset_seconds, beat_grid_stability, bpm_candidates_json,
            -- Tonal
            detected_key_name, detected_key_camelot, key_confidence,
            predominant_chord, chord_changes_per_second, key_candidates_json,
            -- Perceptual
            energy_score, energy_level, danceability_score,
            valence_score, acousticness_score, dissonance_score,
            -- Spectral
            spectral_centroid_hz, spectral_bandwidth_hz, spectral_rolloff_hz,
            spectral_flatness, zero_crossing_rate,
            -- Loudness
            rms_mean, rms_max, integrated_loudness_lufs,
            dynamic_range_db, true_peak_dbtp, replay_gain_db,
            max_momentary_loudness_lufs, loudness_range_lu,
            -- Structure
            analyzed_duration_seconds, intro_end_seconds, outro_start_seconds,
            leading_silence_seconds, trailing_silence_seconds,
            -- Energy curve
            energy_curve_hop_seconds, energy_curve_sample_count,
            energy_curve_min, energy_curve_max, energy_curve_mean, energy_curve_stddev,
            -- Voice / Mood
            vocal_probability, mood_happy_score, mood_aggressive_score,
            mood_relaxed_score, mood_sad_score,
            -- BLOBs
            mfcc_mean_blob, chroma_mean_blob, spectral_contrast_mean_blob,
            -- Provenance
            analyzed_at
        ) VALUES (
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?,
            ?
        )
        """,
        (
            int(track_id), int(content_generation), contract_hash,
            # Rhythm
            _g("detected_bpm"), _g("raw_bpm"), _g("bpm_confidence"),
            _g("onset_density_per_second"), _g("beat_count"), _g("tempo_variability"),
            _g("beat_grid_offset_seconds"), _g("beat_grid_stability"),
            _g("bpm_candidates_json"),
            # Tonal
            _g("detected_key_name"), _g("detected_key_camelot"), _g("key_confidence"),
            _g("predominant_chord"), _g("chord_changes_per_second"),
            _g("key_candidates_json"),
            # Perceptual
            _g("energy_score"), _g("energy_level"), _g("danceability_score"),
            _g("valence_score"), _g("acousticness_score"), _g("dissonance_score"),
            # Spectral
            _g("spectral_centroid_hz"), _g("spectral_bandwidth_hz"), _g("spectral_rolloff_hz"),
            _g("spectral_flatness"), _g("zero_crossing_rate"),
            # Loudness
            _g("rms_mean"), _g("rms_max"), _g("integrated_loudness_lufs"),
            _g("dynamic_range_db"), _g("true_peak_dbtp"), _g("replay_gain_db"),
            _g("max_momentary_loudness_lufs"), _g("loudness_range_lu"),
            # Structure
            _g("analyzed_duration_seconds"), _g("intro_end_seconds"), _g("outro_start_seconds"),
            _g("leading_silence_seconds"), _g("trailing_silence_seconds"),
            # Energy curve
            _g("energy_curve_hop_seconds"), _g("energy_curve_sample_count"),
            _g("energy_curve_min"), _g("energy_curve_max"),
            _g("energy_curve_mean"), _g("energy_curve_stddev"),
            # Voice / Mood
            _g("vocal_probability"), _g("mood_happy_score"), _g("mood_aggressive_score"),
            _g("mood_relaxed_score"), _g("mood_sad_score"),
            # BLOBs
            mfcc_blob, chroma_blob, contrast_blob,
            # Provenance
            analyzed_at,
        ),
    )


# ---------------------------------------------------------------------------
# v7 ML embedding contract + sidecar writers — MERT / MuQ / CLAP (Todo 18)
# ---------------------------------------------------------------------------

_ML_EMBEDDING_FAMILIES = frozenset({"mert", "muq", "clap"})


def upsert_ml_embedding_contract_v7(
    connection: sqlite3.Connection,
    family: str,
    model_name: str,
    model_version: str,
    dim: int,
    normalization: str,
) -> str:
    """Compute an ML embedding contract hash and INSERT OR IGNORE into ``contracts``.

    ``family`` must be one of ``'mert'``, ``'muq'``, or ``'clap'``; raises
    ``ValueError`` otherwise.

    ``normalization`` must be ``'none'`` or ``'l2'``; raises ``ValueError``
    otherwise.

    Returns the ``contract_hash`` string (``"sha256:<hex>"``).
    """
    from datetime import datetime, timezone

    if family not in _ML_EMBEDDING_FAMILIES:
        raise ValueError(
            f"upsert_ml_embedding_contract_v7: family must be one of "
            f"{sorted(_ML_EMBEDDING_FAMILIES)}, got {family!r}"
        )
    if normalization not in ("none", "l2"):
        raise ValueError(
            f"upsert_ml_embedding_contract_v7: normalization must be 'none' or 'l2', "
            f"got {normalization!r}"
        )

    payload: dict[str, object] = {
        "analysis_family": family,
        "output_kind": "embedding",
        "model_name": model_name,
        "model_version": model_version,
        "dim": dim,
        "encoding": "float32-le",
        "normalization": normalization,
        "release_hash": None,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    contract_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    existing = connection.execute(
        "SELECT contract_hash FROM contracts WHERE contract_hash = ?",
        (contract_hash,),
    ).fetchone()
    if existing is None:
        now = datetime.now(timezone.utc).isoformat()
        connection.execute(
            """
            INSERT INTO contracts (
                contract_hash, analysis_family, output_kind,
                model_name, model_version, release_hash,
                canonical_payload_json, created_at
            ) VALUES (?, ?, 'embedding', ?, ?, NULL, ?, ?)
            """,
            (contract_hash, family, model_name, model_version, canonical, now),
        )

    return contract_hash


def _save_ml_embedding_v7(
    artifacts_connection: sqlite3.Connection,
    table_name: str,
    track_id: int,
    track_uuid: str,
    content_generation: int,
    contract_hash: str,
    embedding: "object",
    normalization: str,
    analyzed_at: str,
) -> None:
    """Internal helper: write one ML embedding row to *table_name* in the artifacts sidecar.

    ``table_name`` must be one of ``mert_embeddings``, ``muq_embeddings``, or
    ``clap_embeddings``.

    ``embedding`` may be a numpy array or any sequence of floats; it is packed
    to little-endian float32 bytes (``<f4``).

    ``normalization`` must be ``'none'`` or ``'l2'``; raises ``ValueError``
    otherwise.
    """
    import numpy as np

    if normalization not in ("none", "l2"):
        raise ValueError(
            f"_save_ml_embedding_v7: normalization must be 'none' or 'l2', got {normalization!r}"
        )

    arr = np.asarray(embedding, dtype="<f4")
    if arr.ndim != 1:
        raise ValueError(
            f"_save_ml_embedding_v7: embedding must be 1-D, got shape {arr.shape}"
        )
    dim = int(arr.shape[0])
    if dim <= 0:
        raise ValueError(
            f"_save_ml_embedding_v7: embedding must have at least 1 element, got {dim}"
        )
    embedding_blob = arr.tobytes()

    with artifacts_connection:
        artifacts_connection.execute(
            f"""
            INSERT OR REPLACE INTO {table_name} (
                track_id, track_uuid, content_generation, contract_hash,
                dim, normalization, embedding_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,  # noqa: S608
            (
                int(track_id),
                track_uuid,
                int(content_generation),
                contract_hash,
                dim,
                normalization,
                embedding_blob,
                analyzed_at,
            ),
        )


def save_mert_embedding_v7(
    artifacts_connection: sqlite3.Connection,
    track_id: int,
    track_uuid: str,
    content_generation: int,
    contract_hash: str,
    embedding: "object",
    normalization: str,
    analyzed_at: str,
) -> None:
    """Write one MERT embedding row to the artifacts sidecar ``mert_embeddings`` table.

    ``embedding`` may be a numpy array or any sequence of floats; it is packed
    to little-endian float32 bytes (``<f4``).

    ``normalization`` must be ``'none'`` or ``'l2'``; raises ``ValueError``
    otherwise.

    This function writes to the **artifacts sidecar**, NOT to the Core DB.
    """
    _save_ml_embedding_v7(
        artifacts_connection,
        "mert_embeddings",
        track_id,
        track_uuid,
        content_generation,
        contract_hash,
        embedding,
        normalization,
        analyzed_at,
    )


def save_muq_embedding_v7(
    artifacts_connection: sqlite3.Connection,
    track_id: int,
    track_uuid: str,
    content_generation: int,
    contract_hash: str,
    embedding: "object",
    normalization: str,
    analyzed_at: str,
) -> None:
    """Write one MuQ embedding row to the artifacts sidecar ``muq_embeddings`` table.

    ``embedding`` may be a numpy array or any sequence of floats; it is packed
    to little-endian float32 bytes (``<f4``).

    ``normalization`` must be ``'none'`` or ``'l2'``; raises ``ValueError``
    otherwise.

    This function writes to the **artifacts sidecar**, NOT to the Core DB.
    """
    _save_ml_embedding_v7(
        artifacts_connection,
        "muq_embeddings",
        track_id,
        track_uuid,
        content_generation,
        contract_hash,
        embedding,
        normalization,
        analyzed_at,
    )


def save_clap_embedding_v7(
    artifacts_connection: sqlite3.Connection,
    track_id: int,
    track_uuid: str,
    content_generation: int,
    contract_hash: str,
    embedding: "object",
    normalization: str,
    analyzed_at: str,
) -> None:
    """Write one CLAP embedding row to the artifacts sidecar ``clap_embeddings`` table.

    ``embedding`` may be a numpy array or any sequence of floats; it is packed
    to little-endian float32 bytes (``<f4``).

    ``normalization`` must be ``'none'`` or ``'l2'``; raises ``ValueError``
    otherwise.

    This function writes to the **artifacts sidecar**, NOT to the Core DB.
    """
    _save_ml_embedding_v7(
        artifacts_connection,
        "clap_embeddings",
        track_id,
        track_uuid,
        content_generation,
        contract_hash,
        embedding,
        normalization,
        analyzed_at,
    )
