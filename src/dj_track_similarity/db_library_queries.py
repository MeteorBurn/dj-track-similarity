"""Library queries over one validated SQLite library."""

from __future__ import annotations

import json
import math
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from .analysis_models import (
    AnalysisOutput,
    ClassifierSpecification,
    OUTPUT_KINDS_BY_FAMILY,
    current_embedding_spec,
)
from .db_embeddings import EmbeddingTrackIdentity, validate_embedding_row_metadata
from .db_tracks import utc_now_text
from .library_models import (
    AnalysisCoverage,
    ClassifierScoreDetail,
    ClassifierScoreSummary,
    EmbeddingSummary,
    ExportTrackRow,
    FileTags,
    FileTechnical,
    GenreTagCandidate,
    LibrarySummary,
    MaestAnalysis,
    MaestGenre,
    SonaraCore,
    TrackDetail,
    TrackPage,
    TrackSummary,
    VectorSummary,
)
from .maest_analysis_validation import (
    MAEST_ANALYSIS_COLUMNS,
    parse_maest_genres_json,
    validate_maest_analysis_row,
)
from .track_models import TrackIdentity
from .sonara_core_validation import (
    SONARA_CORE_COLUMNS,
    validate_sonara_core_row,
)


_EMBEDDING_TABLES: tuple[tuple[str, str, str], ...] = (
    ("maest", "embedding", "maest_embeddings"),
    ("mert", "embedding", "mert_embeddings"),
    ("muq", "embedding", "muq_embeddings"),
    ("mulan", "embedding", "mulan_embeddings"),
    ("clap", "embedding", "clap_embeddings"),
)
_SONARA_VECTOR_SUMMARIES = (
    VectorSummary("mfcc_mean", 13),
    VectorSummary("chroma_mean", 12),
    VectorSummary("spectral_contrast_mean", 7),
)
_HUMAN_FTS_COLUMNS = (
    "file_path",
    "title",
    "artist",
    "album",
    "comment",
    "label",
    "country",
    "year",
    "track_number",
    "file_genres",
)


@dataclass(frozen=True)
class _ReadContext:
    catalog_uuid: str
    outputs: Mapping[tuple[str, str], AnalysisOutput]


def _json_ids(track_ids: Iterable[int]) -> str:
    return json.dumps(
        sorted({int(track_id) for track_id in track_ids}),
        separators=(",", ":"),
    )


def _json_identity_rows(identities: Mapping[int, str]) -> str:
    return json.dumps(
        [
            [track_id, track_uuid]
            for track_id, track_uuid in sorted(identities.items())
        ],
        separators=(",", ":"),
    )


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def _json_array(raw: object, field_name: str) -> list[object]:
    try:
        value = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{field_name} is not valid JSON") from error
    if not isinstance(value, list):
        raise RuntimeError(f"{field_name} must be a JSON array")
    return value


def _json_object(raw: object, field_name: str) -> dict[str, object]:
    try:
        value = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"{field_name} is not valid JSON") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"{field_name} must be a JSON object")
    return {str(key): child for key, child in value.items()}


def _json_object_sequence(
    raw: object, field_name: str
) -> tuple[dict[str, object], ...]:
    values = _json_array(raw, field_name)
    if any(not isinstance(value, dict) for value in values):
        raise RuntimeError(f"{field_name} entries must be JSON objects")
    return tuple(
        {str(key): child for key, child in value.items()}
        for value in values
        if isinstance(value, dict)
    )


def _parse_genres(raw: object) -> tuple[str, ...]:
    values = _json_array(raw, "tags.genres_json")
    if any(not isinstance(value, str) for value in values):
        raise RuntimeError("tags.genres_json entries must be strings")
    return tuple(str(value) for value in values)


def _parse_maest_genres(raw: object) -> tuple[MaestGenre, ...]:
    return tuple(
        MaestGenre(
            rank=rank,
            genre_name=label,
            score=score,
        )
        for rank, (label, score) in enumerate(
            parse_maest_genres_json(raw),
            start=1,
        )
    )


def _parse_probabilities(raw: object) -> Mapping[str, float] | None:
    values = _json_object(raw, "classifier_scores.probabilities_json")
    probabilities: dict[str, float] = {}
    for label, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        score = float(value)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            return None
        probabilities[label] = score
    return probabilities


def _parse_feature_names(raw: object) -> tuple[str, ...] | None:
    values = _json_array(raw, "classifier_scores.feature_names_json")
    if (
        not values
        or any(not isinstance(value, str) or not value.strip() for value in values)
        or len(set(values)) != len(values)
    ):
        return None
    return tuple(str(value) for value in values)


def _classifier_specifications_by_key(
    values: Sequence[ClassifierSpecification] | None,
) -> Mapping[str, ClassifierSpecification]:
    if values is None:
        return {}
    result: dict[str, ClassifierSpecification] = {}
    for value in values:
        if not isinstance(value, ClassifierSpecification):
            raise TypeError(
                "classifier_specifications must contain "
                "ClassifierSpecification values"
            )
        if value.classifier_key in result:
            raise ValueError(
                "classifier_specifications must contain unique classifier keys"
            )
        result[value.classifier_key] = value
    return result


def _fts_query(raw: str) -> str:
    terms = [term for term in raw.split() if term]
    if not terms:
        return ""
    quoted = " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
    columns = " ".join(_HUMAN_FTS_COLUMNS)
    return f"{{{columns}}} : ({quoted})"


def _like_pattern(raw: str) -> str:
    escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _read_context(
    connection: sqlite3.Connection,
    *,
    expected_catalog_uuid: str,
) -> _ReadContext:
    library = connection.execute(
        """
        SELECT catalog_uuid
        FROM library
        WHERE singleton_id = 1
        """
    ).fetchone()
    actual_catalog_uuid = None if library is None else str(library[0])
    if actual_catalog_uuid != expected_catalog_uuid:
        raise RuntimeError("library does not belong to the selected catalog")

    outputs = {
        (family, kind): AnalysisOutput(family, kind)
        for family, kinds in OUTPUT_KINDS_BY_FAMILY.items()
        for kind in kinds
    }
    return _ReadContext(
        catalog_uuid=expected_catalog_uuid,
        outputs=outputs,
    )


def _base_select_fields() -> str:
    return """
        t.track_id,
        t.track_uuid,
        t.file_path,
        t.file_size_bytes,
        t.file_modified_ns,
        t.audio_format,
        t.sample_rate_hz,
        t.channel_count,
        t.bit_rate_bps,
        t.bit_depth,
        t.audio_duration_seconds,
        t.last_scanned_at,
        t.missing_since,
        ft.title,
        ft.artist,
        ft.album,
        ft.tag_bpm,
        ft.tag_key,
        ft.comment,
        ft.year,
        ft.label,
        ft.country,
        ft.track_number,
        ft.genres_json,
        ft.tags_read_at,
        EXISTS(
            SELECT 1 FROM likes liked
            WHERE liked.track_id = t.track_id
        ) AS liked
    """


def _filter_sql(
    *,
    context: _ReadContext,
    query: str,
    search_mode: str,
    liked_only: bool,
    syncopated_only: bool,
    classifier_filters: Sequence[tuple[str, float]],
    primary_classifier: tuple[str, float] | None,
    classifier_specifications: Mapping[str, ClassifierSpecification],
    include_missing: bool,
) -> tuple[str, list[object]]:
    del classifier_specifications
    conditions: list[str] = []
    params: list[object] = []
    if not include_missing:
        conditions.append("t.missing_since IS NULL")

    cleaned_query = query.strip()
    if cleaned_query:
        if search_mode == "fts":
            conditions.append(
                """
                t.track_id IN (
                    SELECT CAST(track_id AS INTEGER)
                    FROM track_search_fts
                    WHERE track_search_fts MATCH ?
                )
                """
            )
            params.append(_fts_query(cleaned_query))
        elif search_mode == "like":
            pattern = _like_pattern(cleaned_query)
            conditions.append(
                """
                (
                    t.file_path LIKE ? ESCAPE '\\'
                    OR ft.title LIKE ? ESCAPE '\\'
                    OR ft.artist LIKE ? ESCAPE '\\'
                    OR ft.album LIKE ? ESCAPE '\\'
                    OR ft.comment LIKE ? ESCAPE '\\'
                    OR ft.label LIKE ? ESCAPE '\\'
                    OR ft.country LIKE ? ESCAPE '\\'
                    OR CAST(ft.year AS TEXT) LIKE ? ESCAPE '\\'
                    OR ft.track_number LIKE ? ESCAPE '\\'
                    OR ft.genres_json LIKE ? ESCAPE '\\'
                )
                """
            )
            params.extend([pattern] * 10)
        else:
            raise ValueError("search_mode must be 'like' or 'fts'")

    if liked_only:
        conditions.append("EXISTS(SELECT 1 FROM likes l WHERE l.track_id = t.track_id)")

    if syncopated_only:
        output = context.outputs.get(("maest", "analysis"))
        if output is None:
            conditions.append("0")
        else:
            conditions.append(
                """
                EXISTS(
                    SELECT 1
                    FROM maest_genres ms
                    WHERE ms.track_id = t.track_id
                      AND ms.syncopated_rhythm = 1
                )
                """
            )

    if primary_classifier is not None:
        classifier_key, score = primary_classifier
        conditions.append(
            """
            primary_cs.classifier_key = ?
            AND primary_cs.score >= ?
            """
        )
        params.extend([classifier_key, score])

    for classifier_key, score in classifier_filters:
        if primary_classifier is not None and classifier_key == primary_classifier[0]:
            continue
        conditions.append(
            """
            EXISTS(
                SELECT 1
                FROM classifier_scores cs
                WHERE cs.track_id = t.track_id
                  AND cs.classifier_key = ?
                  AND cs.score >= ?
            )
            """
        )
        params.extend([classifier_key, score])

    return (
        "" if not conditions else "WHERE " + " AND ".join(conditions),
        params,
    )


def _validated_classifier_filters(
    classifier_min_scores: Mapping[str, float],
) -> tuple[tuple[str, float], ...]:
    filters: list[tuple[str, float]] = []
    for classifier_key, threshold in sorted(classifier_min_scores.items()):
        if not classifier_key.strip():
            raise ValueError("classifier keys must be non-empty")
        score = float(threshold)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("classifier score thresholds must be between 0 and 1")
        filters.append((classifier_key, score))
    return tuple(filters)


def _base_from_sql(*, has_primary_classifier: bool) -> str:
    if has_primary_classifier:
        return """
            FROM classifier_scores primary_cs
                 INDEXED BY idx_classifier_scores_lookup
            JOIN tracks t ON t.track_id = primary_cs.track_id
            LEFT JOIN tags ft ON ft.track_id = t.track_id
        """
    return """
        FROM tracks t
        LEFT JOIN tags ft ON ft.track_id = t.track_id
    """


def _order_sql(
    *,
    has_primary_classifier: bool,
) -> str:
    order = [
        "liked DESC",
    ]
    if has_primary_classifier:
        order.append("primary_cs.score DESC")
    order.extend(
        [
            "COALESCE(ft.artist, '') COLLATE NOCASE",
            "COALESCE(ft.title, '') COLLATE NOCASE",
            "t.file_path COLLATE NOCASE",
            "t.track_id",
        ]
    )
    return "ORDER BY " + ", ".join(order)


def _query_base_rows(
    connection: sqlite3.Connection,
    *,
    context: _ReadContext,
    query: str,
    search_mode: str,
    liked_only: bool,
    syncopated_only: bool,
    classifier_min_scores: Mapping[str, float],
    include_missing: bool,
    limit: int | None,
    offset: int,
    classifier_specifications: Mapping[str, ClassifierSpecification] | None = None,
) -> tuple[list[sqlite3.Row], int]:
    classifier_filters = _validated_classifier_filters(classifier_min_scores)
    primary_classifier = (
        None if not classifier_filters else classifier_filters[0]
    )
    where_sql, where_params = _filter_sql(
        context=context,
        query=query,
        search_mode=search_mode,
        liked_only=liked_only,
        syncopated_only=syncopated_only,
        classifier_filters=classifier_filters,
        primary_classifier=primary_classifier,
        classifier_specifications=classifier_specifications or {},
        include_missing=include_missing,
    )
    from_sql = _base_from_sql(
        has_primary_classifier=primary_classifier is not None,
    )
    total = int(
        connection.execute(
            f"""
            SELECT COUNT(*)
            {from_sql}
            {where_sql}
            """,
            where_params,
        ).fetchone()[0]
    )
    order_sql = _order_sql(
        has_primary_classifier=primary_classifier is not None,
    )
    pagination_sql = ""
    pagination_params: list[object] = []
    if limit is not None:
        pagination_sql = "LIMIT ? OFFSET ?"
        pagination_params.extend([int(limit), int(offset)])
    rows = connection.execute(
        f"""
        SELECT {_base_select_fields()}
        {from_sql}
        {where_sql}
        {order_sql}
        {pagination_sql}
        """,
        [*where_params, *pagination_params],
    ).fetchall()
    return rows, total


def _identity_map(
    rows: Sequence[sqlite3.Row],
) -> dict[int, str]:
    return {
        int(row["track_id"]): str(row["track_uuid"])
        for row in rows
    }


def _valid_sonara_core_ids(
    connection: sqlite3.Connection,
    *,
    output: AnalysisOutput | None,
    identities: Mapping[int, str],
    drive_from_requested: bool,
) -> set[int]:
    if output is None or not identities:
        return set()
    if drive_from_requested:
        rows = connection.execute(
            f"""
            SELECT {", ".join(f"stored.{column}" for column in SONARA_CORE_COLUMNS)}
            FROM json_each(?) requested
            CROSS JOIN sonara_features stored
            WHERE stored.track_id = CAST(requested.value AS INTEGER)
            """,
            (_json_ids(identities),),
        ).fetchall()
    else:
        rows = connection.execute(
            f"""
            SELECT {", ".join(SONARA_CORE_COLUMNS)}
            FROM sonara_features
            WHERE track_id IN (
                  SELECT CAST(value AS INTEGER)
                  FROM json_each(?)
              )
            """,
            (_json_ids(identities),),
        ).fetchall()
    valid_ids: set[int] = set()
    for row in rows:
        track_id = int(row["track_id"])
        if track_id not in identities:
            continue
        valid, _reason = validate_sonara_core_row(
            row,
            expected_track_id=track_id,
        )
        if valid:
            valid_ids.add(track_id)
    return valid_ids


def _valid_maest_analysis_ids(
    connection: sqlite3.Connection,
    *,
    output: AnalysisOutput | None,
    identities: Mapping[int, str],
    drive_from_requested: bool,
) -> set[int]:
    if output is None or not identities:
        return set()
    if drive_from_requested:
        rows = connection.execute(
            f"""
            SELECT {", ".join(f"stored.{column}" for column in MAEST_ANALYSIS_COLUMNS)}
            FROM json_each(?) requested
            CROSS JOIN maest_genres stored
            WHERE stored.track_id = CAST(requested.value AS INTEGER)
            """,
            (_json_ids(identities),),
        ).fetchall()
    else:
        rows = connection.execute(
            f"""
            SELECT {", ".join(MAEST_ANALYSIS_COLUMNS)}
            FROM maest_genres
            WHERE track_id IN (
                  SELECT CAST(value AS INTEGER)
                  FROM json_each(?)
              )
            """,
            (_json_ids(identities),),
        ).fetchall()
    valid_ids: set[int] = set()
    for row in rows:
        track_id = int(row["track_id"])
        if track_id not in identities:
            continue
        valid, _reason = validate_maest_analysis_row(
            row,
            expected_track_id=track_id,
        )
        if valid:
            valid_ids.add(track_id)
    return valid_ids


def _current_analysis_row_count(
    connection: sqlite3.Connection,
    *,
    table: str,
    output: AnalysisOutput | None,
    identities: Mapping[int, str],
) -> int:
    if output is None or not identities:
        return 0
    return int(
        connection.execute(
            f"""
            WITH requested AS (
                SELECT
                    CAST(json_extract(value, '$[0]') AS INTEGER) AS track_id
                FROM json_each(?)
            )
            SELECT COUNT(*)
            FROM {table} stored
            JOIN requested
              ON requested.track_id = stored.track_id
            """,
            (_json_identity_rows(identities),),
        ).fetchone()[0]
    )


def _valid_embedding_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    output: AnalysisOutput | None,
    identities: Mapping[int, str],
    catalog_uuid: str,
    embedding: bool,
    drive_from_requested: bool,
) -> dict[int, Mapping[str, object]]:
    if output is None or not identities:
        return {}
    if embedding:
        try:
            current_embedding_spec(output.analysis_family)
        except ValueError:
            return {}
    embedding_fields = (
        ", dim, normalization, length(embedding_blob) AS embedding_bytes"
        if embedding
        else ""
    )
    if drive_from_requested:
        rows = connection.execute(
            f"""
            SELECT stored.track_id, stored.track_uuid,
                   stored.analyzed_at
                   {embedding_fields}
            FROM json_each(?) requested
            CROSS JOIN {table} stored
            WHERE stored.track_id = CAST(requested.value AS INTEGER)
            """,
            (_json_ids(identities),),
        )
    else:
        rows = connection.execute(
            f"""
            SELECT track_id, track_uuid,
                   analyzed_at
                   {embedding_fields}
            FROM {table}
            WHERE track_id IN (
                  SELECT CAST(value AS INTEGER)
                  FROM json_each(?)
              )
            """,
            (_json_ids(identities),),
        )
    valid: dict[int, Mapping[str, object]] = {}
    for row in rows:
        track_id = int(row["track_id"])
        expected = identities.get(track_id)
        if expected is None:
            continue
        if (
            row["track_id"] != track_id
            or str(row["track_uuid"]) != expected
        ):
            continue
        if embedding:
            valid_embedding, _reason = validate_embedding_row_metadata(
                family=output.analysis_family,
                row=row,
                expected_track=EmbeddingTrackIdentity(
                    catalog_uuid=catalog_uuid,
                    track_id=track_id,
                    track_uuid=expected,
                ),
            )
            if not valid_embedding:
                continue
        valid[track_id] = {
            "track_id": row["track_id"],
            "track_uuid": row["track_uuid"],
            "analyzed_at": row["analyzed_at"],
        }
        if embedding:
            valid[track_id]["dim"] = row["dim"]
            valid[track_id]["normalization"] = row["normalization"]
    return valid


def _current_artifact_row_count(
    connection: sqlite3.Connection,
    *,
    table: str,
    output: AnalysisOutput | None,
    identities: Mapping[int, str],
) -> int:
    if output is None or not identities:
        return 0
    try:
        expected_spec = current_embedding_spec(output.analysis_family)
    except ValueError:
        return 0
    return int(
        connection.execute(
            f"""
            WITH requested AS (
                SELECT
                    CAST(json_extract(value, '$[0]') AS INTEGER) AS track_id,
                    CAST(json_extract(value, '$[1]') AS TEXT) AS track_uuid
                FROM json_each(?)
            )
            SELECT COUNT(*)
            FROM {table} stored
            JOIN requested
              ON requested.track_id = stored.track_id
             AND requested.track_uuid = stored.track_uuid
            WHERE stored.dim = ?
              AND stored.normalization = ?
            """,
            (
                _json_identity_rows(identities),
                expected_spec.dimension,
                expected_spec.normalization,
            ),
        ).fetchone()[0]
    )


def _current_classifier_details(
    connection: sqlite3.Connection,
    *,
    identities: Mapping[int, str],
    drive_from_requested: bool,
    classifier_specifications: Mapping[str, ClassifierSpecification],
) -> dict[int, tuple[ClassifierScoreDetail, ...]]:
    del classifier_specifications
    if not identities:
        return {}
    select_fields = """
        SELECT
            cs.track_id,
            cs.track_uuid,
            cs.classifier_key,
            cs.score,
            cs.predicted_class,
            cs.score_bucket,
            cs.confidence,
            cs.probabilities_json,
            cs.feature_set,
            cs.feature_names_json,
            cs.positive_label,
            cs.analyzed_at
    """
    current_sql = " ORDER BY cs.track_id, cs.classifier_key"
    params = (_json_ids(identities),)
    if drive_from_requested:
        rows = connection.execute(
            select_fields
            + """
            FROM json_each(?) requested
            CROSS JOIN classifier_scores cs
            WHERE cs.track_id = CAST(requested.value AS INTEGER)
            """
            + current_sql,
            params,
        )
    else:
        rows = connection.execute(
            select_fields
            + """
            FROM classifier_scores cs
            WHERE cs.track_id IN (
                  SELECT CAST(value AS INTEGER)
                  FROM json_each(?)
              )
            """
            + current_sql,
            params,
        )
    grouped: defaultdict[int, list[ClassifierScoreDetail]] = defaultdict(list)
    for row in rows:
        feature_names = _parse_feature_names(row["feature_names_json"])
        if feature_names is None:
            continue
        classifier_key = str(row["classifier_key"])
        probabilities = _parse_probabilities(row["probabilities_json"])
        if probabilities is None:
            continue
        bucket = str(row["score_bucket"])
        if bucket not in {"low", "medium", "high"}:
            continue
        grouped[int(row["track_id"])].append(
            ClassifierScoreDetail(
                classifier_key=classifier_key,
                score=float(row["score"]),
                predicted_class=str(row["predicted_class"]),
                score_bucket=bucket,  # type: ignore[arg-type]
                confidence=float(row["confidence"]),
                probabilities=probabilities,
                feature_set=str(row["feature_set"]),
                feature_names=feature_names,
                positive_label=str(row["positive_label"]),
                analyzed_at=str(row["analyzed_at"]),
            )
        )
    return {track_id: tuple(values) for track_id, values in grouped.items()}


def _coverage_and_classifiers(
    connection: sqlite3.Connection,
    *,
    context: _ReadContext,
    rows: Sequence[sqlite3.Row],
    classifier_specifications: Mapping[str, ClassifierSpecification] | None = None,
) -> tuple[
    dict[int, AnalysisCoverage],
    dict[int, tuple[ClassifierScoreDetail, ...]],
    dict[tuple[str, str], dict[int, Mapping[str, object]]],
]:
    identities = _identity_map(rows)
    drive_from_requested = len(identities) <= 500
    sonara_core = _valid_sonara_core_ids(
        connection,
        output=context.outputs.get(("sonara", "core")),
        identities=identities,
        drive_from_requested=drive_from_requested,
    )
    maest_analysis = _valid_maest_analysis_ids(
        connection,
        output=context.outputs.get(("maest", "analysis")),
        identities=identities,
        drive_from_requested=drive_from_requested,
    )
    embedding_rows: dict[
        tuple[str, str],
        dict[int, Mapping[str, object]],
    ] = {}
    for family, output_kind, table in _EMBEDDING_TABLES:
        embedding_rows[(family, output_kind)] = _valid_embedding_rows(
            connection,
            table=table,
            output=context.outputs.get((family, output_kind)),
            identities=identities,
            catalog_uuid=context.catalog_uuid,
            embedding=True,
            drive_from_requested=drive_from_requested,
        )
    coverage = {
        track_id: AnalysisCoverage(
            sonara_core=track_id in sonara_core,
            maest_analysis=track_id in maest_analysis,
            maest_embedding=track_id in embedding_rows[("maest", "embedding")],
            mert=track_id in embedding_rows[("mert", "embedding")],
            muq=track_id in embedding_rows[("muq", "embedding")],
            mulan=track_id in embedding_rows[("mulan", "embedding")],
            clap=track_id in embedding_rows[("clap", "embedding")],
        )
        for track_id in identities
    }
    classifiers = _current_classifier_details(
        connection,
        identities=identities,
        drive_from_requested=drive_from_requested,
        classifier_specifications=classifier_specifications or {},
    )
    return coverage, classifiers, embedding_rows


def _classifier_summaries(
    details: Sequence[ClassifierScoreDetail],
) -> tuple[ClassifierScoreSummary, ...]:
    return tuple(
        ClassifierScoreSummary(
            classifier_key=detail.classifier_key,
            score=detail.score,
            predicted_class=detail.predicted_class,
            score_bucket=detail.score_bucket,
            confidence=detail.confidence,
        )
        for detail in details
    )


def _track_summary(
    row: sqlite3.Row,
    *,
    catalog_uuid: str,
    coverage: AnalysisCoverage,
    classifiers: Sequence[ClassifierScoreDetail],
) -> TrackSummary:
    return TrackSummary(
        track_id=int(row["track_id"]),
        catalog_uuid=catalog_uuid,
        track_uuid=str(row["track_uuid"]),
        file_path=str(row["file_path"]),
        title=_optional_text(row["title"]),
        artist=_optional_text(row["artist"]),
        album=_optional_text(row["album"]),
        tag_bpm=_optional_float(row["tag_bpm"]),
        tag_key=_optional_text(row["tag_key"]),
        audio_duration_seconds=_optional_float(row["audio_duration_seconds"]),
        liked=bool(row["liked"]),
        analysis_coverage=coverage,
        classifier_scores=_classifier_summaries(classifiers),
    )


def _assemble_summaries(
    connection: sqlite3.Connection,
    *,
    context: _ReadContext,
    rows: Sequence[sqlite3.Row],
    classifier_specifications: Mapping[str, ClassifierSpecification] | None = None,
) -> tuple[TrackSummary, ...]:
    coverage, classifiers, _embedding_rows = _coverage_and_classifiers(
        connection,
        context=context,
        rows=rows,
        classifier_specifications=classifier_specifications,
    )
    return tuple(
        _track_summary(
            row,
            catalog_uuid=context.catalog_uuid,
            coverage=coverage[int(row["track_id"])],
            classifiers=classifiers.get(int(row["track_id"]), ()),
        )
        for row in rows
    )


def _file_tags(row: sqlite3.Row) -> FileTags | None:
    if row["tags_read_at"] is None:
        return None
    return FileTags(
        title=_optional_text(row["title"]),
        artist=_optional_text(row["artist"]),
        album=_optional_text(row["album"]),
        track_number=_optional_text(row["track_number"]),
        label=_optional_text(row["label"]),
        country=_optional_text(row["country"]),
        year=_optional_int(row["year"]),
        tag_key=_optional_text(row["tag_key"]),
        tag_bpm=_optional_float(row["tag_bpm"]),
        comment=_optional_text(row["comment"]),
        genres=_parse_genres(row["genres_json"]),
        tags_read_at=str(row["tags_read_at"]),
    )


def _sonara_core(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    output: AnalysisOutput | None,
) -> SonaraCore | None:
    if output is None:
        return None
    row = connection.execute(
        f"""
        SELECT {", ".join(SONARA_CORE_COLUMNS)}
        FROM sonara_features
        WHERE track_id = ?
        """,
        (track_id,),
    ).fetchone()
    if row is None:
        return None
    valid, _reason = validate_sonara_core_row(
        row,
        expected_track_id=track_id,
    )
    if not valid:
        return None
    return SonaraCore(
        analysis_schema_version=int(row["analysis_schema_version"]),
        detected_bpm=_optional_float(row["detected_bpm"]),
        raw_bpm=_optional_float(row["raw_bpm"]),
        bpm_confidence=_optional_float(row["bpm_confidence"]),
        onset_density_per_second=_optional_float(row["onset_density_per_second"]),
        beat_count=_optional_int(row["beat_count"]),
        tempo_variability=_optional_float(row["tempo_variability"]),
        beat_grid_offset_seconds=_optional_float(row["beat_grid_offset_seconds"]),
        beat_grid_stability=_optional_float(row["beat_grid_stability"]),
        bpm_candidates=()
        if row["bpm_candidates_json"] is None
        else _json_object_sequence(
            row["bpm_candidates_json"],
            "sonara.bpm_candidates_json",
        ),
        detected_key_name=_optional_text(row["detected_key_name"]),
        detected_key_camelot=_optional_text(row["detected_key_camelot"]),
        key_confidence=_optional_float(row["key_confidence"]),
        predominant_chord=_optional_text(row["predominant_chord"]),
        chord_changes_per_second=_optional_float(row["chord_changes_per_second"]),
        key_candidates=()
        if row["key_candidates_json"] is None
        else _json_object_sequence(
            row["key_candidates_json"],
            "sonara.key_candidates_json",
        ),
        energy_score=_optional_float(row["energy_score"]),
        energy_level=_optional_int(row["energy_level"]),
        danceability_score=_optional_float(row["danceability_score"]),
        valence_score=_optional_float(row["valence_score"]),
        acousticness_score=_optional_float(row["acousticness_score"]),
        dissonance_score=_optional_float(row["dissonance_score"]),
        spectral_centroid_hz=_optional_float(row["spectral_centroid_hz"]),
        spectral_bandwidth_hz=_optional_float(row["spectral_bandwidth_hz"]),
        spectral_rolloff_hz=_optional_float(row["spectral_rolloff_hz"]),
        spectral_flatness=_optional_float(row["spectral_flatness"]),
        zero_crossing_rate=_optional_float(row["zero_crossing_rate"]),
        rms_mean=_optional_float(row["rms_mean"]),
        rms_max=_optional_float(row["rms_max"]),
        integrated_loudness_lufs=_optional_float(row["integrated_loudness_lufs"]),
        dynamic_range_db=_optional_float(row["dynamic_range_db"]),
        true_peak_dbtp=_optional_float(row["true_peak_dbtp"]),
        replay_gain_db=_optional_float(row["replay_gain_db"]),
        max_momentary_loudness_lufs=_optional_float(row["max_momentary_loudness_lufs"]),
        loudness_range_lu=_optional_float(row["loudness_range_lu"]),
        analyzed_duration_seconds=_optional_float(row["analyzed_duration_seconds"]),
        intro_end_seconds=_optional_float(row["intro_end_seconds"]),
        outro_start_seconds=_optional_float(row["outro_start_seconds"]),
        leading_silence_seconds=_optional_float(row["leading_silence_seconds"]),
        trailing_silence_seconds=_optional_float(row["trailing_silence_seconds"]),
        energy_curve_hop_seconds=_optional_float(row["energy_curve_hop_seconds"]),
        energy_curve_sample_count=_optional_int(row["energy_curve_sample_count"]),
        energy_curve_min=_optional_float(row["energy_curve_min"]),
        energy_curve_max=_optional_float(row["energy_curve_max"]),
        energy_curve_mean=_optional_float(row["energy_curve_mean"]),
        energy_curve_stddev=_optional_float(row["energy_curve_stddev"]),
        vocal_probability=_optional_float(row["vocal_probability"]),
        mood_happy_score=_optional_float(row["mood_happy_score"]),
        mood_aggressive_score=_optional_float(row["mood_aggressive_score"]),
        mood_relaxed_score=_optional_float(row["mood_relaxed_score"]),
        mood_sad_score=_optional_float(row["mood_sad_score"]),
        aggression_score=_optional_float(row["aggression_score"]),
        aggression_confidence=_optional_float(row["aggression_confidence"]),
        aggression_forcefulness=_optional_float(row["aggression_forcefulness"]),
        aggression_harshness=_optional_float(row["aggression_harshness"]),
        aggression_tension=_optional_float(row["aggression_tension"]),
        aggression_rhythm=_optional_float(row["aggression_rhythm"]),
        vector_summaries=_SONARA_VECTOR_SUMMARIES,
        analyzed_at=str(row["analyzed_at"]),
    )


def _maest_analysis(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    output: AnalysisOutput | None,
) -> MaestAnalysis | None:
    if output is None:
        return None
    row = connection.execute(
        f"""
        SELECT {", ".join(MAEST_ANALYSIS_COLUMNS)}
        FROM maest_genres
        WHERE track_id = ?
        """,
        (track_id,),
    ).fetchone()
    if row is None:
        return None
    valid, _reason = validate_maest_analysis_row(
        row,
        expected_track_id=track_id,
    )
    if not valid:
        return None
    syncopated = row["syncopated_rhythm"]
    return MaestAnalysis(
        syncopated_rhythm=(None if syncopated is None else bool(syncopated)),
        genres=_parse_maest_genres(row["genres_json"]),
        analyzed_at=str(row["analyzed_at"]),
    )


class LibraryQueryRepository:
    """Read-model mixin for the single library database."""

    catalog_uuid: str
    _write_lock: threading.RLock

    def connect(self) -> sqlite3.Connection:
        raise NotImplementedError

    def classifier_score_counts(
        self,
        classifier_keys: Sequence[str],
    ) -> dict[str, int]:
        counts = dict.fromkeys(classifier_keys, 0)
        if not counts:
            return counts
        placeholders = ", ".join("?" for _ in counts)
        with closing(self.connect()) as core_connection:
            rows = core_connection.execute(
                f"""
                SELECT classifier_key, COUNT(*) AS score_count
                FROM classifier_scores AS cs
                WHERE classifier_key IN ({placeholders})
                GROUP BY classifier_key
                """,
                tuple(counts),
            ).fetchall()
        for row in rows:
            classifier_key = str(row["classifier_key"])
            if classifier_key in counts:
                counts[classifier_key] = int(row["score_count"])
        return counts

    @contextmanager
    def _open_library(
        self,
    ) -> Iterator[tuple[sqlite3.Connection, _ReadContext]]:
        with closing(self.connect()) as connection:
            context = _read_context(
                connection,
                expected_catalog_uuid=self.catalog_uuid,
            )
            yield connection, context

    def list_track_summaries(
        self,
        *,
        include_missing: bool = False,
        classifier_specifications: Sequence[ClassifierSpecification] | None = None,
    ) -> tuple[TrackSummary, ...]:
        specifications_by_key = _classifier_specifications_by_key(
            classifier_specifications
        )
        with self._open_library() as (connection, context):
            rows, _total = _query_base_rows(
                connection,
                context=context,
                query="",
                search_mode="like",
                liked_only=False,
                syncopated_only=False,
                classifier_min_scores={},
                include_missing=include_missing,
                limit=None,
                offset=0,
            )
            return _assemble_summaries(
                connection,
                context=context,
                rows=rows,
                classifier_specifications=specifications_by_key,
            )

    def get_track_summaries(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
        classifier_specifications: Sequence[ClassifierSpecification] | None = None,
    ) -> tuple[TrackSummary, ...]:
        """Hydrate a strict selection in caller order.

        Unknown or unavailable IDs fail closed. Repeated IDs are preserved so
        callers can align the returned summaries with an existing ranked list.
        """

        requested: list[int] = []
        for value in track_ids:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("track_ids must contain only positive integers")
            requested.append(value)
        if not requested:
            return ()
        specifications_by_key = _classifier_specifications_by_key(
            classifier_specifications
        )

        with self._open_library() as (connection, context):
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            rows = connection.execute(
                f"""
                SELECT {_base_select_fields()}
                FROM tracks t
                LEFT JOIN tags ft ON ft.track_id = t.track_id
                WHERE t.track_id IN (
                    SELECT CAST(value AS INTEGER)
                    FROM json_each(?)
                )
                {missing_sql}
                """,
                (_json_ids(requested),),
            ).fetchall()
            summaries = _assemble_summaries(
                connection,
                context=context,
                rows=rows,
                classifier_specifications=specifications_by_key,
            )
        by_id = {summary.track_id: summary for summary in summaries}
        unavailable = sorted(set(requested).difference(by_id))
        if unavailable:
            raise KeyError(
                "Unknown current track ids: "
                + ", ".join(str(track_id) for track_id in unavailable)
            )
        return tuple(by_id[track_id] for track_id in requested)

    def paginate_track_summaries(
        self,
        *,
        query: str = "",
        search_mode: str = "like",
        liked_only: bool = False,
        syncopated_only: bool = False,
        classifier_min_scores: Mapping[str, float] | None = None,
        include_missing: bool = False,
        limit: int = 100,
        offset: int = 0,
        classifier_specifications: Sequence[ClassifierSpecification] | None = None,
    ) -> TrackPage:
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        scores = dict(classifier_min_scores or {})
        specifications_by_key = _classifier_specifications_by_key(
            classifier_specifications
        )
        with self._open_library() as (connection, context):
            rows, total = _query_base_rows(
                connection,
                context=context,
                query=query,
                search_mode=search_mode,
                liked_only=liked_only,
                syncopated_only=syncopated_only,
                classifier_min_scores=scores,
                include_missing=include_missing,
                limit=bounded_limit,
                offset=bounded_offset,
                classifier_specifications=specifications_by_key,
            )
            items = _assemble_summaries(
                connection,
                context=context,
                rows=rows,
                classifier_specifications=specifications_by_key,
            )
        return TrackPage(
            items=items,
            total=total,
            limit=bounded_limit,
            offset=bounded_offset,
        )

    def filter_track_summaries(
        self,
        *,
        query: str = "",
        search_mode: str = "like",
        liked_only: bool = False,
        syncopated_only: bool = False,
        classifier_min_scores: Mapping[str, float] | None = None,
        include_missing: bool = False,
        classifier_specifications: Sequence[ClassifierSpecification] | None = None,
    ) -> tuple[TrackSummary, ...]:
        scores = dict(classifier_min_scores or {})
        specifications_by_key = _classifier_specifications_by_key(
            classifier_specifications
        )
        with self._open_library() as (connection, context):
            rows, _total = _query_base_rows(
                connection,
                context=context,
                query=query,
                search_mode=search_mode,
                liked_only=liked_only,
                syncopated_only=syncopated_only,
                classifier_min_scores=scores,
                include_missing=include_missing,
                limit=None,
                offset=0,
                classifier_specifications=specifications_by_key,
            )
            return _assemble_summaries(
                connection,
                context=context,
                rows=rows,
                classifier_specifications=specifications_by_key,
            )

    def get_track_detail(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
        classifier_specifications: Sequence[ClassifierSpecification] | None = None,
    ) -> TrackDetail:
        specifications_by_key = _classifier_specifications_by_key(
            classifier_specifications
        )
        with self._open_library() as (connection, context):
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            row = connection.execute(
                f"""
                SELECT {_base_select_fields()}
                FROM tracks t
                LEFT JOIN tags ft ON ft.track_id = t.track_id
                WHERE t.track_id = ?
                {missing_sql}
                """,
                (int(track_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown current track id: {track_id}")
            coverage, classifiers, embedding_rows = _coverage_and_classifiers(
                connection,
                context=context,
                rows=[row],
                classifier_specifications=specifications_by_key,
            )
            numeric_id = int(row["track_id"])
            classifier_details = classifiers.get(numeric_id, ())
            summary = _track_summary(
                row,
                catalog_uuid=context.catalog_uuid,
                coverage=coverage[numeric_id],
                classifiers=classifier_details,
            )
            sonara = _sonara_core(
                connection,
                track_id=numeric_id,
                output=context.outputs.get(("sonara", "core")),
            )
            maest = _maest_analysis(
                connection,
                track_id=numeric_id,
                output=context.outputs.get(("maest", "analysis")),
            )
            embeddings = tuple(
                EmbeddingSummary(
                    analysis_family=family,
                    dim=int(embedding_row["dim"]),
                    normalization=str(embedding_row["normalization"]),
                    analyzed_at=str(embedding_row["analyzed_at"]),
                )
                for family, output_kind, _table in _EMBEDDING_TABLES
                if context.outputs.get((family, output_kind))
                is not None
                and (
                    embedding_row := embedding_rows[(family, output_kind)].get(numeric_id)
                )
                is not None
            )
            return TrackDetail(
                **summary.__dict__,
                file=FileTechnical(
                    file_size_bytes=int(row["file_size_bytes"]),
                    file_modified_ns=int(row["file_modified_ns"]),
                    audio_format=_optional_text(row["audio_format"]),
                    sample_rate_hz=_optional_int(row["sample_rate_hz"]),
                    channel_count=_optional_int(row["channel_count"]),
                    bit_rate_bps=_optional_int(row["bit_rate_bps"]),
                    bit_depth=_optional_int(row["bit_depth"]),
                    audio_duration_seconds=_optional_float(
                        row["audio_duration_seconds"]
                    ),
                    last_scanned_at=str(row["last_scanned_at"]),
                    missing_since=_optional_text(row["missing_since"]),
                ),
                file_tags=_file_tags(row),
                sonara_core=sonara,
                maest=maest,
                embeddings=embeddings,
                classifier_scores_detail=classifier_details,
            )

    def get_media_path(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> Path:
        with self._open_library() as (connection, _context):
            missing_sql = "" if include_missing else "AND missing_since IS NULL"
            row = connection.execute(
                f"""
                SELECT file_path
                FROM tracks
                WHERE track_id = ?
                {missing_sql}
                """,
                (int(track_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown current track id: {track_id}")
            return Path(str(row["file_path"]))

    def set_track_liked(
        self,
        *,
        expected: TrackIdentity,
        liked: bool,
        classifier_specifications: Sequence[ClassifierSpecification] | None = None,
    ) -> TrackSummary:
        if not isinstance(liked, bool):
            raise TypeError("liked must be a bool")
        if expected.catalog_uuid != self.catalog_uuid:
            raise RuntimeError("Track like candidate belongs to a different catalog")
        specifications_by_key = _classifier_specifications_by_key(
            classifier_specifications
        )
        with (
            self._write_lock,
            self._open_library() as (connection, context),
        ):
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT track_id, track_uuid
                    FROM tracks
                    WHERE track_id = ?
                      AND track_uuid = ?
                      AND missing_since IS NULL
                    """,
                    (
                        expected.track_id,
                        expected.track_uuid,
                    ),
                ).fetchone()
                if row is None:
                    raise RuntimeError(
                        "Track identity changed before the liked-state mutation"
                    )
                if liked:
                    connection.execute(
                        """
                        INSERT INTO likes(track_id, liked_at)
                        VALUES (?, ?)
                        ON CONFLICT(track_id) DO UPDATE SET
                            liked_at = excluded.liked_at
                        """,
                        (expected.track_id, utc_now_text()),
                    )
                else:
                    connection.execute(
                        "DELETE FROM likes WHERE track_id = ?",
                        (expected.track_id,),
                    )
                base_row = connection.execute(
                    f"""
                    SELECT {_base_select_fields()}
                    FROM tracks t
                    LEFT JOIN tags ft ON ft.track_id = t.track_id
                    WHERE t.track_id = ?
                    """,
                    (expected.track_id,),
                ).fetchone()
                assert base_row is not None
                summary = _assemble_summaries(
                    connection,
                    context=context,
                    rows=[base_row],
                    classifier_specifications=specifications_by_key,
                )[0]
                connection.commit()
                return summary
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise

    def list_liked_track_ids(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[int, ...]:
        with self._open_library() as (connection, _context):
            missing_sql = "" if include_missing else "WHERE t.missing_since IS NULL"
            rows = connection.execute(
                f"""
                SELECT l.track_id
                FROM likes l
                JOIN tracks t ON t.track_id = l.track_id
                {missing_sql}
                ORDER BY l.liked_at DESC, l.track_id
                """
            )
            return tuple(int(row[0]) for row in rows)

    def list_genre_tag_candidates(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[GenreTagCandidate, ...]:
        """Return present tracks with current, non-empty MAEST genre scores."""

        with self._open_library() as (connection, context):
            output = context.outputs.get(("maest", "analysis"))
            if output is None:
                return ()
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            rows = connection.execute(
                f"""
                SELECT
                    t.track_id,
                    t.track_uuid,
                    t.file_path,
                    t.file_size_bytes,
                    t.file_modified_ns,
                    ms.syncopated_rhythm,
                    ms.genres_json,
                    ms.analyzed_at
                FROM tracks t
                JOIN maest_genres ms
                 ON ms.track_id = t.track_id
                WHERE 1 = 1
                {missing_sql}
                ORDER BY t.file_path COLLATE NOCASE, t.track_id
                """
            ).fetchall()
            candidates: list[GenreTagCandidate] = []
            for row in rows:
                valid, _reason = validate_maest_analysis_row(
                    row,
                    expected_track_id=int(row["track_id"]),
                )
                if not valid:
                    continue
                genres = tuple(
                    genre.genre_name
                    for genre in _parse_maest_genres(row["genres_json"])
                )
                if not genres:
                    continue
                candidates.append(
                    GenreTagCandidate(
                        catalog_uuid=context.catalog_uuid,
                        track_id=int(row["track_id"]),
                        track_uuid=str(row["track_uuid"]),
                        file_path=str(row["file_path"]),
                        expected_file_size_bytes=int(row["file_size_bytes"]),
                        expected_file_modified_ns=int(row["file_modified_ns"]),
                        genres=genres,
                        maest_analyzed_at=str(row["analyzed_at"]),
                    )
                )
            return tuple(candidates)

    def export_track_rows(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> tuple[ExportTrackRow, ...]:
        requested = tuple(int(track_id) for track_id in track_ids)
        if not requested:
            return ()
        with self._open_library() as (connection, context):
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            rows = connection.execute(
                f"""
                SELECT
                    t.track_id,
                    t.track_uuid,
                    t.file_path,
                    ft.artist,
                    ft.title,
                    ft.album,
                    ft.tag_bpm,
                    ft.tag_key
                FROM tracks t
                LEFT JOIN tags ft ON ft.track_id = t.track_id
                WHERE t.track_id IN (
                    SELECT CAST(value AS INTEGER)
                    FROM json_each(?)
                )
                {missing_sql}
                """,
                (_json_ids(requested),),
            ).fetchall()
            by_id = {int(row["track_id"]): row for row in rows}
            unavailable_ids = sorted(set(requested).difference(by_id))
            if unavailable_ids:
                raise KeyError(
                    "Unknown current track ids: "
                    + ", ".join(str(track_id) for track_id in unavailable_ids)
                )
            sonara_by_id: dict[int, SonaraCore | None] = {
                track_id: _sonara_core(
                    connection,
                    track_id=track_id,
                    output=context.outputs.get(("sonara", "core")),
                )
                for track_id, row in by_id.items()
            }
            result: list[ExportTrackRow] = []
            for track_id in requested:
                row = by_id.get(track_id)
                if row is None:
                    continue
                sonara = sonara_by_id[track_id]
                result.append(
                    ExportTrackRow(
                        track_id=track_id,
                        file_path=str(row["file_path"]),
                        artist=_optional_text(row["artist"]),
                        title=_optional_text(row["title"]),
                        album=_optional_text(row["album"]),
                        tag_bpm=_optional_float(row["tag_bpm"]),
                        tag_key=_optional_text(row["tag_key"]),
                        sonara_bpm=(None if sonara is None else sonara.detected_bpm),
                        sonara_key=(
                            None
                            if sonara is None
                            else sonara.detected_key_camelot or sonara.detected_key_name
                        ),
                        sonara_energy=(None if sonara is None else sonara.energy_score),
                    )
                )
            return tuple(result)

    def claim_sonara_analysis_range(
        self,
        bpm_min: float,
        bpm_max: float,
    ) -> tuple[float, float]:
        """Return the library BPM range, claiming this pair when none is set.

        The range belongs to the library, not to any single analysed row: the
        first analysis job claims it, every later run reuses it, and only a
        SONARA reset or a full library clear releases it. Reading and claiming
        share one transaction so two jobs started against a fresh library
        cannot settle on different ranges.
        """

        with self._write_lock:
            with closing(self.connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    claimed = _stored_sonara_range(connection)
                    if claimed is not None:
                        connection.rollback()
                        return claimed
                    connection.execute(
                        """
                        UPDATE library
                        SET sonara_bpm_min = ?,
                            sonara_bpm_max = ?,
                            updated_at = ?
                        WHERE singleton_id = 1
                        """,
                        (float(bpm_min), float(bpm_max), utc_now_text()),
                    )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        return (float(bpm_min), float(bpm_max))

    def library_summary(self) -> LibrarySummary:
        def count_rows(connection: sqlite3.Connection, table: str) -> int:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

        with closing(self.connect()) as connection:
            return LibrarySummary(
                tracks=count_rows(connection, "tracks"),
                sonara=count_rows(connection, "sonara_features"),
                maest_analysis=count_rows(connection, "maest_genres"),
                maest_embedding=count_rows(connection, "maest_embeddings"),
                mert=count_rows(connection, "mert_embeddings"),
                muq=count_rows(connection, "muq_embeddings"),
                mulan=count_rows(connection, "mulan_embeddings"),
                clap=count_rows(connection, "clap_embeddings"),
                liked=count_rows(connection, "likes"),
                classifiers=count_rows(connection, "classifier_scores"),
                **_sonara_range_fields(connection),
            )


def _stored_sonara_range(
    connection: sqlite3.Connection,
) -> tuple[float, float] | None:
    """Read the claimed library BPM range, or None while none is claimed."""
    row = connection.execute(
        """
        SELECT sonara_bpm_min, sonara_bpm_max
        FROM library
        WHERE singleton_id = 1
        """
    ).fetchone()
    if row is None or row[0] is None or row[1] is None:
        return None
    return (float(row[0]), float(row[1]))


def _sonara_range_fields(
    connection: sqlite3.Connection,
) -> dict[str, float | None]:
    """Expose the claimed library range, or nulls while none is claimed."""
    claimed = _stored_sonara_range(connection)
    if claimed is None:
        return {"sonara_bpm_min": None, "sonara_bpm_max": None}
    return {"sonara_bpm_min": claimed[0], "sonara_bpm_max": claimed[1]}
