"""Stored classifier inputs and validated score writes."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import fields

import numpy as np

from ..analysis_models import (
    AnalysisTarget,
    ClassifierCandidate,
    ClassifierFeatureRow,
    ClassifierSpecification,
)
from .analysis_candidates import (
    table_for_output,
)
from .ddl import FLOAT32_LE, ClassifierScoreRecord
from .sonara_core_validation import (
    SONARA_CORE_COLUMNS,
)
from ..classifier.manifest import classifier_source_layer
from ..classifier.sonara_features import resolve_sonara_classifier_feature


_CLASSIFIER_SCORE_COLUMNS = tuple(
    field.name for field in fields(ClassifierScoreRecord)
    if field.name not in {"feature_set", "feature_names_json"}
) + ("feature_spec_id",)


_SONARA_IDENTITY_COLUMNS = {
    "track_id",
}


_CLASSIFIER_PROBABILITY_TOLERANCE = 1e-9


def _classifier_input_query_parts(
    specification: ClassifierSpecification,
) -> tuple[list[str], list[str], dict[str, str]]:
    """Build the fixed-table joins needed by one classifier recipe.

    Each feature source joins its own row: ``family@N`` at layer N and a bare
    token at the family's default layer, so artifacts promoted before layer
    tokens keep reading the vector they were trained on. Returns the selected
    columns, the joins and the blob column of each embedding source.
    """

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
    joined_aliases: set[str] = set()
    embedding_columns: dict[str, str] = {}
    sources = dict.fromkeys(
        feature_name.partition(":")[0] for feature_name in specification.feature_names
    )
    for source in sources:
        family, layer = classifier_source_layer(source)
        output = outputs_by_family.get(family)
        if output is None:
            raise ValueError(f"classifier feature source has no required input: {source}")
        table = table_for_output(output)
        if table is None:
            raise ValueError(
                "unsupported classifier input "
                f"{output.analysis_family}/{output.output_kind}"
            )
        alias = f"classifier_{family}" if layer is None else f"classifier_{family}_{layer}"
        if output.output_kind == "embedding":
            embedding_columns[source] = f"{alias}_embedding_blob"
        elif output.key != ("sonara", "core"):
            raise ValueError(
                "unsupported classifier input "
                f"{output.analysis_family}/{output.output_kind}"
            )
        if alias in joined_aliases:
            # "family" and "family@<default>" name one stored row.
            continue
        joined_aliases.add(alias)
        # A literal layer keeps the default-layer partial index usable.
        layer_filter = "" if layer is None else f" AND {alias}.layer = {int(layer)}"
        joins.append(
            f"JOIN {table} AS {alias} ON {alias}.track_id = tracks.track_id{layer_filter}"
        )
        if output.key == ("sonara", "core"):
            select_columns.extend(
                f"{alias}.{column} AS sonara_{column}"
                for column in SONARA_CORE_COLUMNS
                if column not in _SONARA_IDENTITY_COLUMNS
            )
        else:
            select_columns.append(f"{alias}.embedding_blob AS {alias}_embedding_blob")
    return select_columns, joins, embedding_columns


def _classifier_feature_vector_from_row(
    row: sqlite3.Row,
    specification: ClassifierSpecification,
    *,
    embedding_columns: Mapping[str, str],
) -> np.ndarray:
    embedding_vectors = {
        source: np.frombuffer(row[column], dtype=FLOAT32_LE)
        for source, column in embedding_columns.items()
    }
    values: list[float] = []
    for feature_name in specification.feature_names:
        source, separator, key = feature_name.partition(":")
        if not separator:
            raise ValueError(
                f"classifier feature has no required input: {feature_name}"
            )
        if source == "sonara":
            resolved = resolve_sonara_classifier_feature(key)
            if resolved is None:
                raise ValueError(f"unsupported SONARA classifier feature: {key}")
            column, index = resolved
            raw = row[f"sonara_{column}"]
            if index is None:
                values.append(float(raw))
            else:
                values.append(float(np.frombuffer(raw, dtype=FLOAT32_LE)[index]))
        else:
            vector = embedding_vectors.get(source)
            if vector is None:
                raise ValueError(
                    f"classifier feature has no required input: {feature_name}"
                )
            values.append(float(vector[int(key)]))
    return _readonly_copy(np.asarray(values, dtype=FLOAT32_LE))


def _classifier_work_item_from_row(
    row: sqlite3.Row,
    specification: ClassifierSpecification,
    *,
    catalog_uuid: str,
    embedding_columns: Mapping[str, str],
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
            embedding_columns=embedding_columns,
        ),
    )
    return candidate, feature_row


def _upsert_classifier_score(
    core_connection: sqlite3.Connection,
    score: ClassifierScoreRecord,
) -> None:
    core_connection.execute(
        """
        INSERT INTO classifier_feature_specs (feature_set, feature_names_json)
        VALUES (?, ?)
        ON CONFLICT(feature_set, feature_names_json) DO NOTHING
        """,
        (score.feature_set, score.feature_names_json),
    )
    feature_spec_id = core_connection.execute(
        """
        SELECT feature_spec_id FROM classifier_feature_specs
        WHERE feature_set = ? AND feature_names_json = ?
        """,
        (score.feature_set, score.feature_names_json),
    ).fetchone()[0]
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
        tuple(
            feature_spec_id if column == "feature_spec_id" else getattr(score, column)
            for column in _CLASSIFIER_SCORE_COLUMNS
        ),
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


def _readonly_copy(vector: np.ndarray) -> np.ndarray:
    copied = np.ascontiguousarray(vector, dtype=FLOAT32_LE).copy()
    copied.setflags(write=False)
    return copied


def _count_classifier_work(
    connection: sqlite3.Connection,
    specification: ClassifierSpecification,
    joins: Sequence[str],
) -> int:
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
    return int(
        connection.execute(
            query,
            (specification.classifier_key,),
        ).fetchone()[0]
    )


def _read_classifier_work_rows(
    connection: sqlite3.Connection,
    specification: ClassifierSpecification,
    columns: Sequence[str],
    joins: Sequence[str],
    *,
    after_track_id: int,
    limit: int,
) -> list[sqlite3.Row]:
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
    return connection.execute(
        query,
        (
            specification.classifier_key,
            after_track_id,
            limit,
        ),
    ).fetchall()
