"""Analysis persistence in the single library database."""

from __future__ import annotations

import json
import math
import secrets
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import fields
from types import MappingProxyType

import numpy as np

from .analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisResetResult,
    AnalysisTarget,
    AnalysisVectorRow,
    AnalysisWriteResult,
    ClassifierCandidate,
    ClassifierFeatureRow,
    ClassifierScoreWrite,
    ClassifierSpecification,
    EmbeddingWrite,
    MaestWrite,
    OUTPUT_KINDS_BY_FAMILY,
    SonaraFeatureRow,
    SonaraWrite,
    StaleAnalysisTargetError,
    current_embedding_spec,
)
from .db_analysis_candidates import (
    collect_analysis_candidates,
    current_sonara_target_keys,
    normalize_analysis_outputs,
    read_current_track_identities,
    require_active_analysis_outputs,
    table_for_output,
    target_from_track_row,
)
from .db_embeddings import (
    EmbeddingTrackIdentity,
    read_valid_embeddings,
    write_valid_embedding_in_transaction,
)
from .db_ddl import ClassifierScoreRecord
from .maest_analysis_validation import (
    has_maest_syncopated_rhythm,
    parse_maest_genres_json,
    validate_maest_analysis_row,
)
from .sonara_core_validation import (
    SONARA_CORE_COLUMNS,
    SONARA_CORE_VECTOR_DIMS,
    validate_sonara_core_row,
)
from .sonara_classifier_features import resolve_sonara_classifier_feature


_CLASSIFIER_SCORE_COLUMNS = tuple(field.name for field in fields(ClassifierScoreRecord))
_SONARA_IDENTITY_COLUMNS = {
    "track_id",
}
_CLASSIFIER_PROBABILITY_TOLERANCE = 1e-9
_SQLITE_IN_CHUNK_SIZE = 800


_CURRENT_SONARA_TARGETS_SQL = """
    FROM sonara_features AS sonara
    JOIN tracks
      ON tracks.track_id = sonara.track_id
    WHERE tracks.missing_since IS NULL
"""


def _classifier_input_query_parts(
    specification: ClassifierSpecification,
) -> tuple[list[str], list[str], dict[str, AnalysisOutput]]:
    """Build the fixed-table joins needed by one classifier recipe."""

    outputs_by_family = {
        output.analysis_family: output
        for output in specification.required_outputs
    }
    select_columns = [
        "tracks.track_id",
        "tracks.track_uuid",
        "tracks.file_path",
        "tracks.file_size_bytes",
        "tracks.file_modified_ns",
    ]
    joins: list[str] = []
    for family, output in outputs_by_family.items():
        table = table_for_output(output)
        if table is None:
            raise ValueError(
                "unsupported classifier input "
                f"{output.analysis_family}/{output.output_kind}"
            )
        alias = f"classifier_{family}"
        joins.append(f"JOIN {table} AS {alias} ON {alias}.track_id = tracks.track_id")
        if output.key == ("sonara", "core"):
            select_columns.extend(
                f"{alias}.{column} AS sonara_{column}"
                for column in SONARA_CORE_COLUMNS
                if column not in _SONARA_IDENTITY_COLUMNS
            )
        elif output.output_kind == "embedding":
            select_columns.append(
                f"{alias}.embedding_blob AS {family}_embedding_blob"
            )
        else:
            raise ValueError(
                "unsupported classifier input "
                f"{output.analysis_family}/{output.output_kind}"
            )
    return select_columns, joins, outputs_by_family


def _classifier_feature_vector_from_row(
    row: sqlite3.Row,
    specification: ClassifierSpecification,
    *,
    outputs_by_family: Mapping[str, AnalysisOutput],
) -> np.ndarray:
    embedding_vectors = {
        family: np.frombuffer(row[f"{family}_embedding_blob"], dtype="<f4")
        for family, output in outputs_by_family.items()
        if output.output_kind == "embedding"
    }
    values: list[float] = []
    for feature_name in specification.feature_names:
        family, separator, key = feature_name.partition(":")
        if not separator or family not in outputs_by_family:
            raise ValueError(
                f"classifier feature has no required input: {feature_name}"
            )
        if family == "sonara":
            resolved = resolve_sonara_classifier_feature(key)
            if resolved is None:
                raise ValueError(f"unsupported SONARA classifier feature: {key}")
            column, index = resolved
            raw = row[f"sonara_{column}"]
            if index is None:
                values.append(float(raw))
            else:
                values.append(float(np.frombuffer(raw, dtype="<f4")[index]))
        else:
            values.append(float(embedding_vectors[family][int(key)]))
    return _readonly_copy(np.asarray(values, dtype="<f4"))


def _classifier_work_item_from_row(
    row: sqlite3.Row,
    specification: ClassifierSpecification,
    *,
    catalog_uuid: str,
    outputs_by_family: Mapping[str, AnalysisOutput],
) -> tuple[ClassifierCandidate, ClassifierFeatureRow]:
    target = AnalysisTarget(
        catalog_uuid=catalog_uuid,
        track_id=int(row["track_id"]),
        track_uuid=str(row["track_uuid"]),
    )
    candidate = ClassifierCandidate(
        target=target,
        file_path=str(row["file_path"]),
        file_size_bytes=int(row["file_size_bytes"]),
        file_modified_ns=int(row["file_modified_ns"]),
    )
    feature_row = ClassifierFeatureRow(
        target=target,
        specification=specification,
        vector=_classifier_feature_vector_from_row(
            row,
            specification,
            outputs_by_family=outputs_by_family,
        ),
    )
    return candidate, feature_row


def _catalog_uuid(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        "SELECT singleton_id, catalog_uuid FROM library"
    ).fetchall()
    if len(rows) != 1 or int(rows[0][0]) != 1:
        raise RuntimeError("library must contain exactly singleton_id=1")
    catalog_uuid = str(rows[0][1]).strip()
    if not catalog_uuid:
        raise RuntimeError("library catalog UUID is empty")
    return catalog_uuid


def _embedding_track(target: AnalysisTarget) -> EmbeddingTrackIdentity:
    return EmbeddingTrackIdentity(
        catalog_uuid=target.catalog_uuid,
        track_id=target.track_id,
        track_uuid=target.track_uuid,
    )


def _require_current_target(
    core_connection: sqlite3.Connection,
    target: AnalysisTarget,
    *,
    catalog_uuid: str,
) -> None:
    if target.catalog_uuid != catalog_uuid:
        raise StaleAnalysisTargetError(
            "stale analysis target rejected: catalog_uuid mismatch"
        )
    row = core_connection.execute(
        """
        SELECT track_uuid, missing_since
        FROM tracks
        WHERE track_id = ?
        """,
        (target.track_id,),
    ).fetchone()
    if row is None:
        raise StaleAnalysisTargetError(
            "stale analysis target rejected: unknown track_id"
        )
    if str(row[0]) != target.track_uuid:
        raise StaleAnalysisTargetError(
            "stale analysis target rejected: track_uuid mismatch"
        )
    if row[1] is not None:
        raise StaleAnalysisTargetError(
            "stale analysis target rejected: track is missing"
        )


def _savepoint(connection: sqlite3.Connection, index: int) -> str:
    name = f"analysis_item_{index}"
    connection.execute(f"SAVEPOINT {name}")
    return name


def _rollback_savepoint(connection: sqlite3.Connection, name: str) -> None:
    connection.execute(f"ROLLBACK TO {name}")
    connection.execute(f"RELEASE {name}")


def _release_savepoint(connection: sqlite3.Connection, name: str) -> None:
    connection.execute(f"RELEASE {name}")


def _error_result(
    target: AnalysisTarget,
    error: Exception,
) -> AnalysisWriteResult:
    return AnalysisWriteResult(
        target=target,
        error=f"{type(error).__name__}: {error}",
    )


def _upsert_sonara_core(
    core_connection: sqlite3.Connection,
    *,
    write: SonaraWrite,
) -> None:
    row = write.core
    valid, reason = validate_sonara_core_row(
        row,
        expected_track_id=write.target.track_id,
    )
    if not valid:
        raise ValueError(f"invalid SONARA Core row: {reason}")
    placeholders = ", ".join("?" for _ in SONARA_CORE_COLUMNS)
    updates = ", ".join(
        f"{column} = excluded.{column}"
        for column in SONARA_CORE_COLUMNS
        if column != "track_id"
    )
    core_connection.execute(
        f"""
        INSERT INTO sonara_features ({", ".join(SONARA_CORE_COLUMNS)})
        VALUES ({placeholders})
        ON CONFLICT(track_id) DO UPDATE SET {updates}
        """,
        tuple(getattr(row, column) for column in SONARA_CORE_COLUMNS),
    )


def _upsert_sonara_fingerprint(
    connection: sqlite3.Connection,
    *,
    write: SonaraWrite,
) -> None:
    fingerprint = write.fingerprint
    if fingerprint is None:
        return
    connection.execute(
        """
        INSERT INTO sonara_fingerprints(
            track_id, track_uuid, fingerprint_version, fingerprint_base64, analyzed_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            track_uuid = excluded.track_uuid,
            fingerprint_version = excluded.fingerprint_version,
            fingerprint_base64 = excluded.fingerprint_base64,
            analyzed_at = excluded.analyzed_at
        """,
        (
            write.target.track_id,
            write.target.track_uuid,
            fingerprint.version,
            fingerprint.value,
            fingerprint.analyzed_at,
        ),
    )


def _upsert_maest_analysis(
    core_connection: sqlite3.Connection,
    *,
    write: MaestWrite,
) -> None:
    row = {
        "track_id": write.target.track_id,
        "syncopated_rhythm": (
            None if write.syncopated_rhythm is None else int(write.syncopated_rhythm)
        ),
        "genres_json": write.genres_json,
        "analyzed_at": write.analyzed_at,
    }
    valid, reason = validate_maest_analysis_row(
        row,
        expected_track_id=write.target.track_id,
    )
    if not valid:
        raise ValueError(f"invalid MAEST analysis row: {reason}")
    core_connection.execute(
        """
        INSERT INTO maest_genres (
            track_id, syncopated_rhythm, genres_json, analyzed_at
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            syncopated_rhythm = excluded.syncopated_rhythm,
            genres_json = excluded.genres_json,
            analyzed_at = excluded.analyzed_at
        """,
        tuple(
            row[column]
            for column in (
                "track_id",
                "syncopated_rhythm",
                "genres_json",
                "analyzed_at",
            )
        ),
    )


def _upsert_classifier_score(
    core_connection: sqlite3.Connection,
    score: ClassifierScoreRecord,
) -> None:
    placeholders = ", ".join("?" for _ in _CLASSIFIER_SCORE_COLUMNS)
    updates = ", ".join(
        f"{column} = excluded.{column}"
        for column in _CLASSIFIER_SCORE_COLUMNS
        if column not in {"track_id", "classifier_key"}
    )
    core_connection.execute(
        f"""
        INSERT INTO classifier_scores (
            {", ".join(_CLASSIFIER_SCORE_COLUMNS)}
        ) VALUES ({placeholders})
        ON CONFLICT(track_id, classifier_key) DO UPDATE SET {updates}
        """,
        tuple(getattr(score, column) for column in _CLASSIFIER_SCORE_COLUMNS),
    )


def _validate_classifier_score(
    score: ClassifierScoreRecord,
    specification: ClassifierSpecification,
) -> None:
    for field_name in (
        "track_uuid",
        "classifier_key",
        "feature_set",
        "feature_names_json",
        "positive_label",
        "predicted_class",
        "analyzed_at",
    ):
        value = getattr(score, field_name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"classifier score {field_name} is required")
    try:
        feature_names = json.loads(score.feature_names_json)
    except json.JSONDecodeError as error:
        raise ValueError(
            "classifier feature_names_json must be valid JSON"
        ) from error
    if feature_names != list(specification.feature_names):
        raise ValueError(
            "classifier feature_names_json does not match ordered feature_names"
        )
    if score.score_bucket not in {"low", "medium", "high"}:
        raise ValueError("classifier score_bucket is invalid")
    for field_name in ("score", "confidence"):
        value = getattr(score, field_name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"classifier {field_name} must be a finite number between 0 and 1"
            )
        number = float(value)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise ValueError(
                f"classifier {field_name} must be finite and between 0 and 1"
            )
    try:
        probabilities = json.loads(score.probabilities_json)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("classifier probabilities_json must be valid JSON") from error
    if not isinstance(probabilities, dict):
        raise ValueError("classifier probabilities_json must contain an object")
    if not probabilities:
        raise ValueError("classifier probabilities_json must not be empty")
    normalized_probabilities: dict[str, float] = {}
    for label, value in probabilities.items():
        if not isinstance(label, str) or not label:
            raise ValueError("classifier probability labels must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("classifier probabilities must be finite numbers")
        probability = float(value)
        if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
            raise ValueError("classifier probabilities must be between 0 and 1")
        normalized_probabilities[label] = probability
    if set(normalized_probabilities) != set(specification.label_order):
        raise ValueError(
            "classifier probability labels do not match canonical label_order"
        )
    if not math.isclose(
        math.fsum(normalized_probabilities.values()),
        1.0,
        rel_tol=0.0,
        abs_tol=_CLASSIFIER_PROBABILITY_TOLERANCE,
    ):
        raise ValueError("classifier probabilities must sum to 1")
    expected_class = max(
        specification.label_order,
        key=normalized_probabilities.__getitem__,
    )
    if score.predicted_class != expected_class:
        raise ValueError(
            "classifier predicted_class does not match canonical label-order argmax"
        )
    expected_score = normalized_probabilities[specification.positive_label]
    if not math.isclose(
        float(score.score),
        expected_score,
        rel_tol=0.0,
        abs_tol=_CLASSIFIER_PROBABILITY_TOLERANCE,
    ):
        raise ValueError(
            "classifier score does not equal the positive-label probability"
        )
    expected_confidence = max(normalized_probabilities.values())
    if not math.isclose(
        float(score.confidence),
        expected_confidence,
        rel_tol=0.0,
        abs_tol=_CLASSIFIER_PROBABILITY_TOLERANCE,
    ):
        raise ValueError("classifier confidence does not equal max(probabilities)")
    expected_bucket = (
        "high"
        if expected_score >= 0.7
        else "medium"
        if expected_score >= 0.3
        else "low"
    )
    if score.score_bucket != expected_bucket:
        raise ValueError("classifier score_bucket does not match the selected score")
def _selected_targets(
    core_connection: sqlite3.Connection,
    *,
    catalog_uuid: str,
    targets: Sequence[AnalysisTarget] | None,
) -> tuple[AnalysisTarget, ...]:
    if targets is None:
        return tuple(
            target_from_track_row(row, catalog_uuid=catalog_uuid)
            for row in read_current_track_identities(core_connection)
        )
    selected = tuple(targets)
    for target in selected:
        if not isinstance(target, AnalysisTarget):
            raise TypeError("targets must contain only AnalysisTarget values")
        _require_current_target(
            core_connection,
            target,
            catalog_uuid=catalog_uuid,
        )
    return selected


def _readonly_copy(vector: np.ndarray) -> np.ndarray:
    copied = np.ascontiguousarray(vector, dtype="<f4").copy()
    copied.setflags(write=False)
    return copied


def _readonly(vector: np.ndarray) -> np.ndarray:
    """Return *vector* unchanged when it is already a read-only ``<f4`` row.

    Bulk reads hand back read-only rows of one stacked array, so copying them
    again allocated a second full library for no gain. Anything else — a
    writable array, another dtype, a non-contiguous slice — still goes through
    the copy.
    """

    if (
        isinstance(vector, np.ndarray)
        and not vector.flags.writeable
        and vector.dtype == np.dtype("<f4")
        and vector.flags.c_contiguous
    ):
        return vector
    return _readonly_copy(vector)


class AnalysisRepository:
    """Mixin implemented by :class:`LibraryDatabase`."""

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        family = str(analysis_family).strip().lower()
        kind = str(output_kind).strip().lower()
        if family not in OUTPUT_KINDS_BY_FAMILY:
            raise ValueError(f"unsupported analysis_family: {analysis_family!r}")
        if kind not in OUTPUT_KINDS_BY_FAMILY[family]:
            raise ValueError(
                f"unsupported output_kind {output_kind!r} "
                f"for analysis_family {family!r}"
            )
        return AnalysisOutput(family, kind)

    def recompute_maest_syncopated_rhythm(self) -> int:
        """Explicitly repair MAEST syncopated-rhythm flags from stored genres."""

        with self._write_lock:
            with closing(self.connect()) as core_connection:
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    rows = core_connection.execute(
                        "SELECT track_id, syncopated_rhythm, genres_json FROM maest_genres"
                    ).fetchall()
                    updates = [
                        (expected, int(row["track_id"]))
                        for row in rows
                        if (
                            expected := int(
                                has_maest_syncopated_rhythm(
                                    label
                                    for label, _score in parse_maest_genres_json(
                                        row["genres_json"]
                                    )
                                )
                            )
                        )
                        != row["syncopated_rhythm"]
                    ]
                    core_connection.executemany(
                        "UPDATE maest_genres SET syncopated_rhythm = ? WHERE track_id = ?",
                        updates,
                    )
                    core_connection.commit()
                except BaseException:
                    core_connection.rollback()
                    raise
        return len(updates)

    def register_analysis_outputs(
        self,
        outputs: Sequence[AnalysisOutput],
    ) -> tuple[str, ...]:
        normalized = normalize_analysis_outputs(outputs)
        return tuple(
            f"{output.analysis_family}/{output.output_kind}"
            for output in normalized
        )

    def list_analysis_candidates(
        self,
        outputs: Sequence[AnalysisOutput],
        *,
        limit: int | None = None,
        require_current_sonara: bool = False,
    ) -> list[AnalysisCandidate]:
        normalized = normalize_analysis_outputs(outputs)
        with self._write_lock:
            with closing(self.connect()) as connection:
                catalog_uuid = _catalog_uuid(connection)
                return collect_analysis_candidates(
                    connection=connection,
                    catalog_uuid=catalog_uuid,
                    outputs=normalized,
                    limit=limit,
                    require_current_sonara=require_current_sonara,
                )

    def current_sonara_track_count(self) -> int:
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                catalog_uuid = _catalog_uuid(core_connection)
                return len(
                    current_sonara_target_keys(
                        core_connection,
                        catalog_uuid=catalog_uuid,
                    )
                )

    def save_sonara_results(
        self,
        writes: Sequence[SonaraWrite],
    ) -> tuple[AnalysisWriteResult, ...]:
        selected = tuple(writes)
        if any(not isinstance(write, SonaraWrite) for write in selected):
            raise TypeError("writes must contain only SonaraWrite values")
        if not selected:
            return ()
        results: list[AnalysisWriteResult] = []
        with self._write_lock:
            with closing(self.connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    catalog_uuid = _catalog_uuid(connection)
                    for index, write in enumerate(selected):
                        name = _savepoint(connection, index)
                        try:
                            require_active_analysis_outputs(
                                connection,
                                write.outputs,
                            )
                            _require_current_target(
                                connection,
                                write.target,
                                catalog_uuid=catalog_uuid,
                            )
                            _upsert_sonara_core(
                                connection,
                                write=write,
                            )
                            if write.embedding is not None:
                                write_valid_embedding_in_transaction(
                                    connection=connection,
                                    track=_embedding_track(write.target),
                                    family=write.embedding.family,
                                    embedding=write.embedding.vector,
                                    analyzed_at=write.embedding.analyzed_at,
                                )
                            _upsert_sonara_fingerprint(
                                connection,
                                write=write,
                            )
                        except Exception as error:
                            _rollback_savepoint(connection, name)
                            results.append(_error_result(write.target, error))
                        else:
                            _release_savepoint(connection, name)
                            results.append(
                                AnalysisWriteResult(
                                    target=write.target,
                                    written_outputs=write.outputs,
                                )
                            )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        return tuple(results)

    def save_maest_results(
        self,
        writes: Sequence[MaestWrite],
    ) -> tuple[AnalysisWriteResult, ...]:
        selected = tuple(writes)
        if any(not isinstance(write, MaestWrite) for write in selected):
            raise TypeError("writes must contain only MaestWrite values")
        if not selected:
            return ()
        results: list[AnalysisWriteResult] = []
        with self._write_lock:
            with closing(self.connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    catalog_uuid = _catalog_uuid(connection)
                    for index, write in enumerate(selected):
                        name = _savepoint(connection, index)
                        try:
                            require_active_analysis_outputs(
                                connection,
                                write.outputs,
                            )
                            _require_current_target(
                                connection,
                                write.target,
                                catalog_uuid=catalog_uuid,
                            )
                            _upsert_maest_analysis(
                                connection,
                                write=write,
                            )
                            if write.embedding is not None:
                                write_valid_embedding_in_transaction(
                                    connection=connection,
                                    track=_embedding_track(write.target),
                                    family=write.embedding.family,
                                    embedding=write.embedding.vector,
                                    analyzed_at=write.embedding.analyzed_at,
                                )
                        except Exception as error:
                            _rollback_savepoint(connection, name)
                            results.append(_error_result(write.target, error))
                        else:
                            _release_savepoint(connection, name)
                            results.append(
                                AnalysisWriteResult(
                                    target=write.target,
                                    written_outputs=write.outputs,
                                )
                            )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        return tuple(results)

    def save_embedding_results(
        self,
        writes: Sequence[EmbeddingWrite],
    ) -> tuple[AnalysisWriteResult, ...]:
        selected = tuple(writes)
        if any(not isinstance(write, EmbeddingWrite) for write in selected):
            raise TypeError("writes must contain only EmbeddingWrite values")
        if not selected:
            return ()
        results: list[AnalysisWriteResult] = []
        with self._write_lock:
            with closing(self.connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    catalog_uuid = _catalog_uuid(connection)
                    for index, write in enumerate(selected):
                        name = _savepoint(connection, index)
                        output = AnalysisOutput(
                            write.output.family,
                            "embedding",
                        )
                        try:
                            require_active_analysis_outputs(
                                connection,
                                (output,),
                            )
                            _require_current_target(
                                connection,
                                write.target,
                                catalog_uuid=catalog_uuid,
                            )
                            if table_for_output(output) is None:
                                raise ValueError(
                                    "embedding output has no library table"
                                )
                            write_valid_embedding_in_transaction(
                                connection=connection,
                                track=_embedding_track(write.target),
                                family=write.output.family,
                                embedding=write.output.vector,
                                analyzed_at=write.output.analyzed_at,
                            )
                        except Exception as error:
                            _rollback_savepoint(connection, name)
                            results.append(_error_result(write.target, error))
                        else:
                            _release_savepoint(connection, name)
                            results.append(
                                AnalysisWriteResult(
                                    target=write.target,
                                    written_outputs=(output,),
                                )
                            )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        return tuple(results)

    def load_analysis_vectors(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[AnalysisVectorRow, ...]:
        if output.output_kind != "embedding":
            raise ValueError("vector loading requires an embedding output")
        with self._write_lock:
            with closing(self.connect()) as connection:
                catalog_uuid = _catalog_uuid(connection)
                require_active_analysis_outputs(
                    connection,
                    (output,),
                )
                selected = _selected_targets(
                    connection,
                    catalog_uuid=catalog_uuid,
                    targets=targets,
                )
                vectors = read_valid_embeddings(
                    family=output.analysis_family,
                    identities={
                        target.track_id: target.track_uuid
                        for target in selected
                    },
                    catalog_uuid=catalog_uuid,
                    connection=connection,
                )
                return tuple(
                    AnalysisVectorRow(
                        target=target,
                        output=output,
                        vector=_readonly(vectors[target.track_id]),
                    )
                    for target in selected
                    if target.track_id in vectors
                )

    def random_embedding_target(
        self,
        output: AnalysisOutput,
        *,
        exclude_track_ids: Sequence[int] = (),
    ) -> AnalysisTarget | None:
        """Pick one current embedded target without reading any vector.

        Row presence under the current identity, dimension, and normalization
        is what makes a track selectable, and all three are stored columns.
        The blob itself adds nothing to that decision: its byte length is a
        table constraint, and its values were validated on write.
        """

        if output.output_kind != "embedding":
            raise ValueError("embedding target selection requires an embedding output")
        table = table_for_output(output)
        if table is None:
            raise ValueError("embedding output has no library table")
        spec = current_embedding_spec(output.analysis_family)
        excluded_ids = tuple(sorted({int(track_id) for track_id in exclude_track_ids}))
        excluded_json = json.dumps(excluded_ids, separators=(",", ":"))
        selectable_sql = f"""
            FROM {table} AS embeddings
            JOIN tracks
              ON tracks.track_id = embeddings.track_id
             AND tracks.track_uuid = embeddings.track_uuid
            WHERE tracks.missing_since IS NULL
              AND embeddings.dim = ?
              AND embeddings.normalization = ?
        """
        spec_parameters = (spec.dimension, spec.normalization)
        with self._write_lock:
            with closing(self.connect()) as connection:
                catalog_uuid = _catalog_uuid(connection)
                require_active_analysis_outputs(
                    connection,
                    (output,),
                )
                available_track_count = int(
                    connection.execute(
                        f"""
                        SELECT COUNT(*)
                        {selectable_sql}
                          AND embeddings.track_id NOT IN (
                              SELECT CAST(value AS INTEGER)
                              FROM json_each(?)
                          )
                        """,
                        (*spec_parameters, excluded_json),
                    ).fetchone()[0]
                )
                if available_track_count == 0:
                    return None
                offset = secrets.randbelow(available_track_count)
                row = connection.execute(
                    f"""
                    SELECT
                        tracks.track_id,
                        tracks.track_uuid
                    {selectable_sql}
                      AND embeddings.track_id NOT IN (
                          SELECT CAST(value AS INTEGER)
                          FROM json_each(?)
                      )
                    ORDER BY embeddings.track_id
                    LIMIT 1 OFFSET ?
                    """,
                    (*spec_parameters, excluded_json, offset),
                ).fetchone()
                if row is None:
                    raise RuntimeError(
                        "current embedding target selection changed during read"
                    )
                return AnalysisTarget(
                    catalog_uuid=catalog_uuid,
                    track_id=int(row["track_id"]),
                    track_uuid=str(row["track_uuid"]),
                )

    def load_sonara_feature_rows(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[SonaraFeatureRow, ...]:
        if output.key != ("sonara", "core"):
            raise ValueError("SONARA feature loading requires a SONARA core output")
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                catalog_uuid = _catalog_uuid(core_connection)
                require_active_analysis_outputs(
                    core_connection,
                    (output,),
                )
                selected = _selected_targets(
                    core_connection,
                    catalog_uuid=catalog_uuid,
                    targets=targets,
                )
                selected_by_id = {target.track_id: target for target in selected}
                if not selected_by_id:
                    return ()
                if targets is None:
                    rows = core_connection.execute(
                        f"""
                        SELECT {", ".join(SONARA_CORE_COLUMNS)}
                        FROM sonara_features
                        ORDER BY track_id
                        """
                    ).fetchall()
                else:
                    rows = []
                    selected_ids = tuple(selected_by_id)
                    for start in range(0, len(selected_ids), _SQLITE_IN_CHUNK_SIZE):
                        chunk = selected_ids[start : start + _SQLITE_IN_CHUNK_SIZE]
                        placeholders = ", ".join("?" for _ in chunk)
                        rows.extend(
                            core_connection.execute(
                                f"""
                                SELECT {", ".join(SONARA_CORE_COLUMNS)}
                                FROM sonara_features
                                WHERE track_id IN ({placeholders})
                                ORDER BY track_id
                                """,
                                chunk,
                            ).fetchall()
                        )
                    rows.sort(key=lambda row: int(row["track_id"]))
                result: list[SonaraFeatureRow] = []
                for row in rows:
                    target = selected_by_id.get(int(row["track_id"]))
                    if target is None:
                        continue
                    valid, _reason = validate_sonara_core_row(
                        row,
                        expected_track_id=target.track_id,
                    )
                    if not valid:
                        continue
                    values: dict[str, object] = {}
                    for column in SONARA_CORE_COLUMNS:
                        if column in _SONARA_IDENTITY_COLUMNS:
                            continue
                        value = row[column]
                        dim = SONARA_CORE_VECTOR_DIMS.get(column)
                        if dim is not None:
                            vector = np.frombuffer(
                                value,
                                dtype="<f4",
                            )
                            values[column] = tuple(float(item) for item in vector)
                        else:
                            values[column] = value
                    result.append(
                        SonaraFeatureRow(
                            target=target,
                            output=output,
                            values=MappingProxyType(values),
                        )
                    )
                return tuple(result)

    def random_sonara_target(
        self,
        output: AnalysisOutput,
        *,
        exclude_track_ids: Sequence[int] = (),
    ) -> AnalysisTarget | None:
        """Pick one current SONARA target without reading its feature vectors."""

        if output.key != ("sonara", "core"):
            raise ValueError("SONARA target selection requires a SONARA core output")
        excluded_ids = tuple(sorted({int(track_id) for track_id in exclude_track_ids}))
        excluded_json = json.dumps(excluded_ids, separators=(",", ":"))
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                catalog_uuid = _catalog_uuid(core_connection)
                require_active_analysis_outputs(
                    core_connection,
                    (output,),
                )
                total_track_count = int(
                    core_connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM tracks
                        WHERE missing_since IS NULL
                        """
                    ).fetchone()[0]
                )
                if total_track_count == 0:
                    return None
                sonara_track_count = int(
                    core_connection.execute(
                        f"SELECT COUNT(*) {_CURRENT_SONARA_TARGETS_SQL}"
                    ).fetchone()[0]
                )
                if sonara_track_count == 0:
                    return None
                available_track_count = int(
                    core_connection.execute(
                        f"""
                        SELECT COUNT(*)
                        {_CURRENT_SONARA_TARGETS_SQL}
                          AND sonara.track_id NOT IN (
                              SELECT CAST(value AS INTEGER)
                              FROM json_each(?)
                          )
                        """,
                        (excluded_json,),
                    ).fetchone()[0]
                )
                if available_track_count == 0:
                    return None
                offset = secrets.randbelow(available_track_count)
                row = core_connection.execute(
                    f"""
                    SELECT
                        tracks.track_id,
                        tracks.track_uuid
                    {_CURRENT_SONARA_TARGETS_SQL}
                      AND sonara.track_id NOT IN (
                          SELECT CAST(value AS INTEGER)
                          FROM json_each(?)
                      )
                    ORDER BY sonara.track_id
                    LIMIT 1 OFFSET ?
                    """,
                    (excluded_json, offset),
                ).fetchone()
                if row is None:
                    raise RuntimeError(
                        "current SONARA target selection changed during read"
                    )
                return AnalysisTarget(
                    catalog_uuid=catalog_uuid,
                    track_id=int(row["track_id"]),
                    track_uuid=str(row["track_uuid"]),
                )

    def classifier_work_count(
        self,
        specification: ClassifierSpecification,
        *,
        limit: int | None = None,
    ) -> int:
        """Count rows that already contain every input required by a classifier."""

        if not isinstance(specification, ClassifierSpecification):
            raise TypeError("specification must be a ClassifierSpecification")
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
                raise ValueError("limit must be a non-negative integer or None")
            if limit == 0:
                return 0
        _columns, joins, _outputs_by_family = _classifier_input_query_parts(
            specification
        )
        query = "\n".join(
            (
                "SELECT COUNT(*)",
                "FROM tracks",
                *joins,
                "LEFT JOIN classifier_scores AS scored",
                "  ON scored.track_id = tracks.track_id",
                " AND scored.classifier_key = ?",
                "WHERE tracks.missing_since IS NULL",
                "  AND scored.track_id IS NULL",
            )
        )
        with self._write_lock:
            with closing(self.connect()) as connection:
                count = int(
                    connection.execute(
                        query,
                        (specification.classifier_key,),
                    ).fetchone()[0]
                )
        return count if limit is None else min(count, limit)

    def load_classifier_work_batch(
        self,
        specification: ClassifierSpecification,
        *,
        after_track_id: int,
        limit: int,
    ) -> tuple[tuple[ClassifierCandidate, ClassifierFeatureRow], ...]:
        """Load one classifier batch from stored analysis rows.

        Classifier input data is trusted once written.  This path therefore
        selects current tracks by the presence of their required rows and does
        not perform a library-wide payload or generation validation pass.
        """

        if not isinstance(specification, ClassifierSpecification):
            raise TypeError("specification must be a ClassifierSpecification")
        if (
            isinstance(after_track_id, bool)
            or not isinstance(after_track_id, int)
            or after_track_id < 0
        ):
            raise ValueError("after_track_id must be a non-negative integer")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer")
        if limit == 0:
            return ()
        columns, joins, outputs_by_family = _classifier_input_query_parts(
            specification
        )
        query = "\n".join(
            (
                f"SELECT {', '.join(columns)}",
                "FROM tracks",
                *joins,
                "LEFT JOIN classifier_scores AS scored",
                "  ON scored.track_id = tracks.track_id",
                " AND scored.classifier_key = ?",
                "WHERE tracks.missing_since IS NULL",
                "  AND tracks.track_id > ?",
                "  AND scored.track_id IS NULL",
                "ORDER BY tracks.track_id",
                "LIMIT ?",
            )
        )
        with self._write_lock:
            with closing(self.connect()) as connection:
                catalog_uuid = _catalog_uuid(connection)
                rows = connection.execute(
                    query,
                    (
                        specification.classifier_key,
                        after_track_id,
                        limit,
                    ),
                ).fetchall()
        return tuple(
            _classifier_work_item_from_row(
                row,
                specification,
                catalog_uuid=catalog_uuid,
                outputs_by_family=outputs_by_family,
            )
            for row in rows
        )

    def save_classifier_scores(
        self,
        writes: Sequence[ClassifierScoreWrite],
    ) -> tuple[AnalysisWriteResult, ...]:
        selected = tuple(writes)
        if any(not isinstance(write, ClassifierScoreWrite) for write in selected):
            raise TypeError("writes must contain only ClassifierScoreWrite values")
        if not selected:
            return ()
        results: list[AnalysisWriteResult] = []
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    for index, write in enumerate(selected):
                        name = _savepoint(core_connection, index)
                        try:
                            _validate_classifier_score(
                                write.score,
                                write.specification,
                            )
                            _upsert_classifier_score(
                                core_connection,
                                write.score,
                            )
                        except Exception as error:
                            _rollback_savepoint(core_connection, name)
                            results.append(_error_result(write.target, error))
                        else:
                            _release_savepoint(core_connection, name)
                            results.append(AnalysisWriteResult(target=write.target))
                    core_connection.commit()
                except BaseException:
                    if core_connection.in_transaction:
                        core_connection.rollback()
                    raise
        return tuple(results)

    def reset_analysis_outputs(
        self,
        outputs: Sequence[AnalysisOutput],
    ) -> AnalysisResetResult:
        normalized = normalize_analysis_outputs(outputs)
        with self._write_lock:
            with closing(self.connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    require_active_analysis_outputs(
                        connection,
                        normalized,
                    )
                    core_deleted = 0
                    embedding_deleted = 0
                    for output in normalized:
                        if output.key == ("sonara", "core"):
                            cursor = connection.execute(
                                "DELETE FROM sonara_features"
                            )
                            core_deleted += max(
                                0,
                                int(cursor.rowcount),
                            )
                        elif output.key == ("maest", "analysis"):
                            cursor = connection.execute(
                                "DELETE FROM maest_genres"
                            )
                            core_deleted += max(
                                0,
                                int(cursor.rowcount),
                            )
                        else:
                            table = table_for_output(output)
                            if table is None:
                                raise ValueError("unsupported analysis output reset")
                            cursor = connection.execute(f"DELETE FROM {table}")
                            embedding_deleted += max(
                                0,
                                int(cursor.rowcount),
                            )
                    classifier_deleted = 0
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        return AnalysisResetResult(
            feature_rows_deleted=core_deleted,
            embedding_rows_deleted=embedding_deleted,
            classifier_rows_deleted=classifier_deleted,
        )

    def reset_classifier_scores(
        self,
        classifier_keys: Sequence[str],
    ) -> AnalysisResetResult:
        keys = tuple(
            dict.fromkeys(
                str(value).strip() for value in classifier_keys if str(value).strip()
            )
        )
        if not keys:
            raise ValueError("at least one classifier key is required")
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                try:
                    core_connection.execute("BEGIN IMMEDIATE")
                    placeholders = ", ".join("?" for _ in keys)
                    cursor = core_connection.execute(
                        f"""
                        DELETE FROM classifier_scores
                        WHERE classifier_key IN ({placeholders})
                        """,
                        keys,
                    )
                    deleted = max(0, int(cursor.rowcount))
                    core_connection.commit()
                except BaseException:
                    if core_connection.in_transaction:
                        core_connection.rollback()
                    raise
        return AnalysisResetResult(classifier_rows_deleted=deleted)
