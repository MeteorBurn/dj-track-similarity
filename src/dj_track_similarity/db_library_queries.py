"""V7-only library queries over one validated Core/Artifacts bundle."""

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

from .analysis_contracts import ContractIdentity, ContractIdentityError
from .analysis_model_runners import current_embedding_analysis_output
from .analysis_models import (
    ACTIVE_CONTRACT_SETTING_PREFIX,
    AnalysisOutput,
    active_classifier_required_outputs_hashes,
    validate_production_contract,
)
from .db_artifacts import (
    ArtifactTrackIdentity,
    validate_embedding_row_payload,
    validate_fingerprint_row_payload,
    validate_timeline_row_payload,
)
from .db_schema import SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY
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
    OptionalOutputs,
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
    ("clap", "embedding", "clap_embeddings"),
    ("sonara", "embedding", "sonara_similarity_embeddings"),
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
    "catalog_number",
    "country",
    "isrc",
    "year",
    "track_number",
    "disc_number",
    "file_genres",
)


@dataclass(frozen=True)
class _ReadContext:
    catalog_uuid: str
    active_release_hash: str | None
    active_contracts: Mapping[tuple[str, str], ContractIdentity]
    active_classifier_required_outputs_hashes: frozenset[str]


def _json_ids(track_ids: Iterable[int]) -> str:
    return json.dumps(
        sorted({int(track_id) for track_id in track_ids}),
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
    values = _json_array(raw, "file_tags.genres_json")
    if any(not isinstance(value, str) for value in values):
        raise RuntimeError("file_tags.genres_json entries must be strings")
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


def _contract_from_row(row: sqlite3.Row) -> ContractIdentity:
    stored_hash = str(row["contract_hash"])
    try:
        identity = ContractIdentity.from_canonical_payload_json(
            str(row["canonical_payload_json"])
        )
    except ContractIdentityError as error:
        raise RuntimeError(
            f"contract registry contains invalid payload for {stored_hash}"
        ) from error
    if identity.contract_hash != stored_hash:
        raise RuntimeError(f"contract registry hash mismatch for {stored_hash}")
    stored_identity = (
        str(row["analysis_family"]),
        str(row["output_kind"]),
        str(row["model_name"]),
        _optional_text(row["model_version"]),
        _optional_text(row["release_hash"]),
    )
    expected_identity = (
        identity.analysis_family,
        identity.output_kind,
        identity.model_name,
        identity.model_version,
        identity.release_hash,
    )
    if stored_identity != expected_identity:
        raise RuntimeError(f"contract registry columns mismatch for {stored_hash}")
    return identity


def _read_context(
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    *,
    expected_catalog_uuid: str,
) -> _ReadContext:
    core_catalog = core_connection.execute(
        """
        SELECT catalog_uuid
        FROM library_catalog
        WHERE singleton_id = 1
        """
    ).fetchone()
    artifacts_catalog = artifacts_connection.execute(
        """
        SELECT catalog_uuid
        FROM storage_metadata
        WHERE singleton_id = 1
        """
    ).fetchone()
    actual_core = None if core_catalog is None else str(core_catalog[0])
    actual_artifacts = None if artifacts_catalog is None else str(artifacts_catalog[0])
    if (
        actual_core != expected_catalog_uuid
        or actual_artifacts != expected_catalog_uuid
    ):
        raise RuntimeError("Core and Artifacts do not belong to the selected catalog")

    settings = {
        str(row["setting_key"]): str(row["setting_value"])
        for row in core_connection.execute(
            "SELECT setting_key, setting_value FROM library_settings"
        )
    }
    contracts_by_hash = {
        identity.contract_hash: identity
        for identity in (
            _contract_from_row(row)
            for row in core_connection.execute(
                """
                SELECT contract_hash, analysis_family, output_kind,
                       model_name, model_version, release_hash,
                       canonical_payload_json
                FROM contracts
                """
            )
        )
    }
    active_release = settings.get(SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY)
    active: dict[tuple[str, str], ContractIdentity] = {}
    for key, contract_hash in settings.items():
        prefix = f"{ACTIVE_CONTRACT_SETTING_PREFIX}."
        if not key.startswith(prefix):
            continue
        suffix = key[len(prefix) :]
        try:
            family, output_kind = suffix.split(".", maxsplit=1)
        except ValueError:
            continue
        identity = contracts_by_hash.get(contract_hash)
        if identity is None or (
            identity.analysis_family,
            identity.output_kind,
        ) != (family, output_kind):
            continue
        try:
            validate_production_contract(identity)
        except ValueError:
            continue
        if output_kind == "embedding" and family in {
            "maest",
            "mert",
            "muq",
            "clap",
        }:
            current = current_embedding_analysis_output(family)
            if (
                identity.contract_hash != current.contract_hash
                or identity.canonical_payload_json
                != current.contract.canonical_payload_json
            ):
                continue
        if family == "sonara" and (
            active_release is None or identity.release_hash != active_release
        ):
            continue
        active[(family, output_kind)] = identity
    return _ReadContext(
        catalog_uuid=expected_catalog_uuid,
        active_release_hash=active_release,
        active_contracts=active,
        active_classifier_required_outputs_hashes=(
            active_classifier_required_outputs_hashes(
                tuple(AnalysisOutput(identity) for identity in active.values())
            )
        ),
    )


def _base_select_fields() -> str:
    return """
        t.track_id,
        t.track_uuid,
        t.content_generation,
        t.file_path,
        t.file_size_bytes,
        t.file_modified_ns,
        t.audio_format,
        t.audio_codec,
        t.sample_rate_hz,
        t.channel_count,
        t.bit_rate_bps,
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
        ft.catalog_number,
        ft.country,
        ft.isrc,
        ft.track_number,
        ft.disc_number,
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
    classifier_min_scores: Mapping[str, float],
    include_missing: bool,
) -> tuple[str, list[object]]:
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
                    OR ft.catalog_number LIKE ? ESCAPE '\\'
                    OR ft.country LIKE ? ESCAPE '\\'
                    OR ft.isrc LIKE ? ESCAPE '\\'
                    OR CAST(ft.year AS TEXT) LIKE ? ESCAPE '\\'
                    OR ft.track_number LIKE ? ESCAPE '\\'
                    OR ft.disc_number LIKE ? ESCAPE '\\'
                    OR ft.genres_json LIKE ? ESCAPE '\\'
                )
                """
            )
            params.extend([pattern] * 13)
        else:
            raise ValueError("search_mode must be 'like' or 'fts'")

    if liked_only:
        conditions.append("EXISTS(SELECT 1 FROM likes l WHERE l.track_id = t.track_id)")

    if syncopated_only:
        contract = context.active_contracts.get(("maest", "analysis"))
        if contract is None:
            conditions.append("0")
        else:
            conditions.append(
                """
                EXISTS(
                    SELECT 1
                    FROM maest_scores ms
                    WHERE ms.track_id = t.track_id
                      AND ms.content_generation = t.content_generation
                      AND ms.contract_hash = ?
                      AND ms.syncopated_rhythm = 1
                )
                """
            )
            params.append(contract.contract_hash)

    for classifier_key, threshold in sorted(classifier_min_scores.items()):
        if not classifier_key.strip():
            raise ValueError("classifier keys must be non-empty")
        score = float(threshold)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("classifier score thresholds must be between 0 and 1")
        conditions.append(
            """
            EXISTS(
                SELECT 1
                FROM classifier_scores cs
                WHERE cs.track_id = t.track_id
                  AND cs.classifier_key = ?
                  AND cs.score >= ?
                  AND cs.content_generation = t.content_generation
                  AND cs.required_outputs_hash IN (
                      SELECT CAST(value AS TEXT)
                      FROM json_each(?)
                  )
                  AND (
                      cs.uses_sonara = 0
                      OR (
                          ? IS NOT NULL
                          AND cs.sonara_release_hash = ?
                      )
                  )
            )
            """
        )
        params.extend(
            [
                classifier_key,
                score,
                json.dumps(
                    sorted(context.active_classifier_required_outputs_hashes),
                    separators=(",", ":"),
                ),
                context.active_release_hash,
                context.active_release_hash,
            ]
        )

    return (
        "" if not conditions else "WHERE " + " AND ".join(conditions),
        params,
    )


def _order_sql(
    *,
    classifier_min_scores: Mapping[str, float],
) -> tuple[str, list[object]]:
    order = [
        "liked DESC",
    ]
    params: list[object] = []
    primary_classifier = next(iter(sorted(classifier_min_scores)), None)
    if primary_classifier is not None:
        order.append(
            """
            (
                SELECT cs.score
                FROM classifier_scores cs
                WHERE cs.track_id = t.track_id
                  AND cs.classifier_key = ?
                  AND cs.content_generation = t.content_generation
                LIMIT 1
            ) DESC
            """
        )
        params.append(primary_classifier)
    order.extend(
        [
            "COALESCE(ft.artist, '') COLLATE NOCASE",
            "COALESCE(ft.title, '') COLLATE NOCASE",
            "t.file_path COLLATE NOCASE",
            "t.track_id",
        ]
    )
    return "ORDER BY " + ", ".join(order), params


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
) -> tuple[list[sqlite3.Row], int]:
    where_sql, where_params = _filter_sql(
        context=context,
        query=query,
        search_mode=search_mode,
        liked_only=liked_only,
        syncopated_only=syncopated_only,
        classifier_min_scores=classifier_min_scores,
        include_missing=include_missing,
    )
    total = int(
        connection.execute(
            f"""
            SELECT COUNT(*)
            FROM tracks t
            LEFT JOIN file_tags ft ON ft.track_id = t.track_id
            {where_sql}
            """,
            where_params,
        ).fetchone()[0]
    )
    order_sql, order_params = _order_sql(classifier_min_scores=classifier_min_scores)
    pagination_sql = ""
    pagination_params: list[object] = []
    if limit is not None:
        pagination_sql = "LIMIT ? OFFSET ?"
        pagination_params.extend([int(limit), int(offset)])
    rows = connection.execute(
        f"""
        SELECT {_base_select_fields()}
        FROM tracks t
        LEFT JOIN file_tags ft ON ft.track_id = t.track_id
        {where_sql}
        {order_sql}
        {pagination_sql}
        """,
        [*where_params, *order_params, *pagination_params],
    ).fetchall()
    return rows, total


def _identity_map(
    rows: Sequence[sqlite3.Row],
) -> dict[int, tuple[str, int]]:
    return {
        int(row["track_id"]): (
            str(row["track_uuid"]),
            int(row["content_generation"]),
        )
        for row in rows
    }


def _valid_sonara_core_ids(
    connection: sqlite3.Connection,
    *,
    contract: ContractIdentity | None,
    identities: Mapping[int, tuple[str, int]],
) -> set[int]:
    if contract is None or not identities:
        return set()
    rows = connection.execute(
        f"""
        SELECT {", ".join(SONARA_CORE_COLUMNS)}
        FROM sonara
        WHERE contract_hash = ?
          AND track_id IN (
              SELECT CAST(value AS INTEGER)
              FROM json_each(?)
          )
        """,
        (contract.contract_hash, _json_ids(identities)),
    ).fetchall()
    valid_ids: set[int] = set()
    for row in rows:
        track_id = int(row["track_id"])
        expected_identity = identities.get(track_id)
        if expected_identity is None:
            continue
        _track_uuid, content_generation = expected_identity
        valid, _reason = validate_sonara_core_row(
            row,
            expected_contract=contract,
            expected_track_id=track_id,
            expected_content_generation=content_generation,
        )
        if valid:
            valid_ids.add(track_id)
    return valid_ids


def _valid_maest_analysis_ids(
    connection: sqlite3.Connection,
    *,
    contract: ContractIdentity | None,
    identities: Mapping[int, tuple[str, int]],
) -> set[int]:
    if contract is None or not identities:
        return set()
    rows = connection.execute(
        f"""
        SELECT {", ".join(MAEST_ANALYSIS_COLUMNS)}
        FROM maest_scores
        WHERE contract_hash = ?
          AND track_id IN (
              SELECT CAST(value AS INTEGER)
              FROM json_each(?)
          )
        """,
        (contract.contract_hash, _json_ids(identities)),
    ).fetchall()
    valid_ids: set[int] = set()
    for row in rows:
        track_id = int(row["track_id"])
        expected_identity = identities.get(track_id)
        if expected_identity is None:
            continue
        _track_uuid, content_generation = expected_identity
        valid, _reason = validate_maest_analysis_row(
            row,
            expected_contract=contract,
            expected_track_id=track_id,
            expected_content_generation=content_generation,
        )
        if valid:
            valid_ids.add(track_id)
    return valid_ids


def _valid_artifact_rows(
    connection: sqlite3.Connection,
    *,
    catalog_uuid: str,
    table: str,
    contract: ContractIdentity | None,
    identities: Mapping[int, tuple[str, int]],
    embedding: bool,
) -> dict[int, Mapping[str, object]]:
    if contract is None or not identities:
        return {}
    embedding_fields = ", dim, normalization, embedding_blob" if embedding else ""
    rows = connection.execute(
        f"""
        SELECT track_id, track_uuid, content_generation, contract_hash,
               analyzed_at
               {embedding_fields}
        FROM {table}
        WHERE contract_hash = ?
          AND track_id IN (
              SELECT CAST(value AS INTEGER)
              FROM json_each(?)
          )
        """,
        (contract.contract_hash, _json_ids(identities)),
    )
    valid: dict[int, Mapping[str, object]] = {}
    for row in rows:
        track_id = int(row["track_id"])
        expected = identities.get(track_id)
        if expected is None:
            continue
        expected_track = ArtifactTrackIdentity(
            catalog_uuid=catalog_uuid,
            track_id=track_id,
            track_uuid=expected[0],
            content_generation=expected[1],
        )
        is_valid, _reason = validate_embedding_row_payload(
            family=contract.analysis_family,
            row=row,
            expected_contract=contract,
            expected_track=expected_track,
        )
        if not is_valid:
            continue
        valid[track_id] = {
            "track_id": row["track_id"],
            "track_uuid": row["track_uuid"],
            "content_generation": row["content_generation"],
            "analyzed_at": row["analyzed_at"],
            "dim": row["dim"],
            "normalization": row["normalization"],
        }
    return valid


def _valid_timeline_rows(
    connection: sqlite3.Connection,
    *,
    catalog_uuid: str,
    contract: ContractIdentity | None,
    identities: Mapping[int, tuple[str, int]],
) -> dict[int, Mapping[str, object]]:
    if contract is None or not identities:
        return {}
    rows = connection.execute(
        """
        SELECT track_id, track_uuid, content_generation, contract_hash,
               payload_json, analyzed_at
        FROM sonara_timeline
        WHERE contract_hash = ?
          AND track_id IN (
              SELECT CAST(value AS INTEGER)
              FROM json_each(?)
          )
        """,
        (contract.contract_hash, _json_ids(identities)),
    )
    valid: dict[int, Mapping[str, object]] = {}
    for row in rows:
        track_id = int(row["track_id"])
        expected = identities.get(track_id)
        if expected is None:
            continue
        is_valid, _reason = validate_timeline_row_payload(
            row=row,
            expected_contract=contract,
            expected_track=ArtifactTrackIdentity(
                catalog_uuid=catalog_uuid,
                track_id=track_id,
                track_uuid=expected[0],
                content_generation=expected[1],
            ),
        )
        if is_valid:
            valid[track_id] = row
    return valid


def _valid_fingerprint_ids(
    connection: sqlite3.Connection,
    *,
    catalog_uuid: str,
    contract: ContractIdentity | None,
    identities: Mapping[int, tuple[str, int]],
) -> set[int]:
    if contract is None or not identities:
        return set()
    rows = connection.execute(
        """
        SELECT track_id, track_uuid, content_generation, contract_hash,
               fingerprint_version, word_count, byte_order,
               fingerprint_blob
        FROM sonara_fingerprints
        WHERE contract_hash = ?
          AND track_id IN (
              SELECT CAST(value AS INTEGER)
              FROM json_each(?)
          )
        """,
        (contract.contract_hash, _json_ids(identities)),
    )
    valid: set[int] = set()
    for row in rows:
        track_id = int(row["track_id"])
        expected = identities.get(track_id)
        if expected is None:
            continue
        is_valid, _reason = validate_fingerprint_row_payload(
            row=row,
            expected_contract=contract,
            expected_track=ArtifactTrackIdentity(
                catalog_uuid=catalog_uuid,
                track_id=track_id,
                track_uuid=expected[0],
                content_generation=expected[1],
            ),
        )
        if is_valid:
            valid.add(track_id)
    return valid


def _current_classifier_details(
    connection: sqlite3.Connection,
    *,
    identities: Mapping[int, tuple[str, int]],
    active_release_hash: str | None,
    active_required_outputs_hashes: frozenset[str],
) -> dict[int, tuple[ClassifierScoreDetail, ...]]:
    if not identities or not active_required_outputs_hashes:
        return {}
    rows = connection.execute(
        """
        SELECT
            cs.track_id,
            cs.classifier_key,
            cs.score,
            cs.predicted_class,
            cs.score_bucket,
            cs.confidence,
            cs.probabilities_json,
            cs.feature_set,
            cs.feature_manifest_hash,
            cs.required_outputs_hash,
            cs.model_id,
            cs.uses_sonara,
            cs.sonara_release_hash,
            cs.positive_label,
            cs.analyzed_at
        FROM classifier_scores cs
        JOIN tracks t ON t.track_id = cs.track_id
        WHERE cs.content_generation = t.content_generation
          AND cs.track_id IN (
              SELECT CAST(value AS INTEGER)
              FROM json_each(?)
          )
          AND cs.required_outputs_hash IN (
              SELECT CAST(value AS TEXT)
              FROM json_each(?)
          )
          AND (
              cs.uses_sonara = 0
              OR (
                  ? IS NOT NULL
                  AND cs.sonara_release_hash = ?
              )
          )
        ORDER BY cs.track_id, cs.classifier_key
        """,
        (
            _json_ids(identities),
            json.dumps(
                sorted(active_required_outputs_hashes),
                separators=(",", ":"),
            ),
            active_release_hash,
            active_release_hash,
        ),
    )
    grouped: defaultdict[int, list[ClassifierScoreDetail]] = defaultdict(list)
    for row in rows:
        probabilities = _parse_probabilities(row["probabilities_json"])
        if probabilities is None:
            continue
        bucket = str(row["score_bucket"])
        if bucket not in {"low", "medium", "high"}:
            continue
        grouped[int(row["track_id"])].append(
            ClassifierScoreDetail(
                classifier_key=str(row["classifier_key"]),
                score=float(row["score"]),
                predicted_class=str(row["predicted_class"]),
                score_bucket=bucket,  # type: ignore[arg-type]
                confidence=float(row["confidence"]),
                probabilities=probabilities,
                feature_set=str(row["feature_set"]),
                feature_manifest_hash=str(row["feature_manifest_hash"]),
                required_outputs_hash=str(row["required_outputs_hash"]),
                model_id=str(row["model_id"]),
                uses_sonara=bool(row["uses_sonara"]),
                sonara_release_hash=_optional_text(row["sonara_release_hash"]),
                positive_label=str(row["positive_label"]),
                analyzed_at=str(row["analyzed_at"]),
            )
        )
    return {track_id: tuple(values) for track_id, values in grouped.items()}


def _coverage_and_classifiers(
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    *,
    context: _ReadContext,
    rows: Sequence[sqlite3.Row],
) -> tuple[
    dict[int, AnalysisCoverage],
    dict[int, tuple[ClassifierScoreDetail, ...]],
    dict[tuple[str, str], dict[int, Mapping[str, object]]],
]:
    identities = _identity_map(rows)
    sonara_core = _valid_sonara_core_ids(
        core_connection,
        contract=context.active_contracts.get(("sonara", "core")),
        identities=identities,
    )
    maest_analysis = _valid_maest_analysis_ids(
        core_connection,
        contract=context.active_contracts.get(("maest", "analysis")),
        identities=identities,
    )
    artifact_rows: dict[
        tuple[str, str],
        dict[int, Mapping[str, object]],
    ] = {}
    for family, output_kind, table in _EMBEDDING_TABLES:
        artifact_rows[(family, output_kind)] = _valid_artifact_rows(
            artifacts_connection,
            catalog_uuid=context.catalog_uuid,
            table=table,
            contract=context.active_contracts.get((family, output_kind)),
            identities=identities,
            embedding=True,
        )
    timeline = _valid_timeline_rows(
        artifacts_connection,
        catalog_uuid=context.catalog_uuid,
        contract=context.active_contracts.get(("sonara", "timeline")),
        identities=identities,
    )
    artifact_rows[("sonara", "timeline")] = timeline
    fingerprint = _valid_fingerprint_ids(
        artifacts_connection,
        catalog_uuid=context.catalog_uuid,
        contract=context.active_contracts.get(("sonara", "fingerprint")),
        identities=identities,
    )
    coverage = {
        track_id: AnalysisCoverage(
            sonara_core=track_id in sonara_core,
            timeline=track_id in timeline,
            sonara_embedding=track_id in artifact_rows[("sonara", "embedding")],
            fingerprint=track_id in fingerprint,
            maest_analysis=track_id in maest_analysis,
            maest_embedding=track_id in artifact_rows[("maest", "embedding")],
            mert=track_id in artifact_rows[("mert", "embedding")],
            muq=track_id in artifact_rows[("muq", "embedding")],
            clap=track_id in artifact_rows[("clap", "embedding")],
        )
        for track_id in identities
    }
    classifiers = _current_classifier_details(
        core_connection,
        identities=identities,
        active_release_hash=context.active_release_hash,
        active_required_outputs_hashes=(
            context.active_classifier_required_outputs_hashes
        ),
    )
    return coverage, classifiers, artifact_rows


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
        content_generation=int(row["content_generation"]),
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
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    *,
    context: _ReadContext,
    rows: Sequence[sqlite3.Row],
) -> tuple[TrackSummary, ...]:
    coverage, classifiers, _artifact_rows = _coverage_and_classifiers(
        core_connection,
        artifacts_connection,
        context=context,
        rows=rows,
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
        tag_bpm=_optional_float(row["tag_bpm"]),
        tag_key=_optional_text(row["tag_key"]),
        comment=_optional_text(row["comment"]),
        year=_optional_int(row["year"]),
        label=_optional_text(row["label"]),
        catalog_number=_optional_text(row["catalog_number"]),
        country=_optional_text(row["country"]),
        isrc=_optional_text(row["isrc"]),
        track_number=_optional_text(row["track_number"]),
        disc_number=_optional_text(row["disc_number"]),
        genres=_parse_genres(row["genres_json"]),
        tags_read_at=str(row["tags_read_at"]),
    )


def _sonara_core(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    generation: int,
    contract: ContractIdentity | None,
) -> SonaraCore | None:
    if contract is None:
        return None
    row = connection.execute(
        f"""
        SELECT {", ".join(SONARA_CORE_COLUMNS)}
        FROM sonara
        WHERE track_id = ?
          AND content_generation = ?
          AND contract_hash = ?
        """,
        (track_id, generation, contract.contract_hash),
    ).fetchone()
    if row is None:
        return None
    valid, _reason = validate_sonara_core_row(
        row,
        expected_contract=contract,
        expected_track_id=track_id,
        expected_content_generation=generation,
    )
    if not valid:
        return None
    return SonaraCore(
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
        vector_summaries=_SONARA_VECTOR_SUMMARIES,
        analyzed_at=str(row["analyzed_at"]),
    )


def _maest_analysis(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    generation: int,
    contract: ContractIdentity | None,
) -> MaestAnalysis | None:
    if contract is None:
        return None
    row = connection.execute(
        f"""
        SELECT {", ".join(MAEST_ANALYSIS_COLUMNS)}
        FROM maest_scores
        WHERE track_id = ?
          AND content_generation = ?
          AND contract_hash = ?
        """,
        (track_id, generation, contract.contract_hash),
    ).fetchone()
    if row is None:
        return None
    valid, _reason = validate_maest_analysis_row(
        row,
        expected_contract=contract,
        expected_track_id=track_id,
        expected_content_generation=generation,
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
    """Read-model mixin for the v7 Core and mandatory Artifacts databases."""

    catalog_uuid: str
    _write_lock: threading.RLock

    def connect(self) -> sqlite3.Connection:
        raise NotImplementedError

    def connect_artifacts(self) -> sqlite3.Connection:
        raise NotImplementedError

    @contextmanager
    def _open_library_bundle(
        self,
    ) -> Iterator[tuple[sqlite3.Connection, sqlite3.Connection, _ReadContext]]:
        with (
            closing(self.connect()) as core_connection,
            closing(self.connect_artifacts()) as artifacts_connection,
        ):
            context = _read_context(
                core_connection,
                artifacts_connection,
                expected_catalog_uuid=self.catalog_uuid,
            )
            yield core_connection, artifacts_connection, context

    def list_track_summaries(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]:
        with self._open_library_bundle() as (
            core_connection,
            artifacts_connection,
            context,
        ):
            rows, _total = _query_base_rows(
                core_connection,
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
                core_connection,
                artifacts_connection,
                context=context,
                rows=rows,
            )

    def get_track_summaries(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
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

        with self._open_library_bundle() as (
            core_connection,
            artifacts_connection,
            context,
        ):
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            rows = core_connection.execute(
                f"""
                SELECT {_base_select_fields()}
                FROM tracks t
                LEFT JOIN file_tags ft ON ft.track_id = t.track_id
                WHERE t.track_id IN (
                    SELECT CAST(value AS INTEGER)
                    FROM json_each(?)
                )
                {missing_sql}
                """,
                (_json_ids(requested),),
            ).fetchall()
            summaries = _assemble_summaries(
                core_connection,
                artifacts_connection,
                context=context,
                rows=rows,
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
    ) -> TrackPage:
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        scores = dict(classifier_min_scores or {})
        with self._open_library_bundle() as (
            core_connection,
            artifacts_connection,
            context,
        ):
            rows, total = _query_base_rows(
                core_connection,
                context=context,
                query=query,
                search_mode=search_mode,
                liked_only=liked_only,
                syncopated_only=syncopated_only,
                classifier_min_scores=scores,
                include_missing=include_missing,
                limit=bounded_limit,
                offset=bounded_offset,
            )
            items = _assemble_summaries(
                core_connection,
                artifacts_connection,
                context=context,
                rows=rows,
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
    ) -> tuple[TrackSummary, ...]:
        scores = dict(classifier_min_scores or {})
        with self._open_library_bundle() as (
            core_connection,
            artifacts_connection,
            context,
        ):
            rows, _total = _query_base_rows(
                core_connection,
                context=context,
                query=query,
                search_mode=search_mode,
                liked_only=liked_only,
                syncopated_only=syncopated_only,
                classifier_min_scores=scores,
                include_missing=include_missing,
                limit=None,
                offset=0,
            )
            return _assemble_summaries(
                core_connection,
                artifacts_connection,
                context=context,
                rows=rows,
            )

    def get_track_detail(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> TrackDetail:
        with self._open_library_bundle() as (
            core_connection,
            artifacts_connection,
            context,
        ):
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            row = core_connection.execute(
                f"""
                SELECT {_base_select_fields()}
                FROM tracks t
                LEFT JOIN file_tags ft ON ft.track_id = t.track_id
                WHERE t.track_id = ?
                {missing_sql}
                """,
                (int(track_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown current track id: {track_id}")
            coverage, classifiers, artifact_rows = _coverage_and_classifiers(
                core_connection,
                artifacts_connection,
                context=context,
                rows=[row],
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
                core_connection,
                track_id=numeric_id,
                generation=int(row["content_generation"]),
                contract=context.active_contracts.get(("sonara", "core")),
            )
            maest = _maest_analysis(
                core_connection,
                track_id=numeric_id,
                generation=int(row["content_generation"]),
                contract=context.active_contracts.get(("maest", "analysis")),
            )
            embeddings = tuple(
                EmbeddingSummary(
                    analysis_family=family,
                    model_name=contract.model_name,
                    model_version=contract.model_version,
                    dim=int(artifact_row["dim"]),
                    normalization=str(artifact_row["normalization"]),
                    analyzed_at=str(artifact_row["analyzed_at"]),
                )
                for family, output_kind, _table in _EMBEDDING_TABLES
                if (contract := context.active_contracts.get((family, output_kind)))
                is not None
                and (
                    artifact_row := artifact_rows[(family, output_kind)].get(numeric_id)
                )
                is not None
            )
            timeline_row = artifact_rows[("sonara", "timeline")].get(numeric_id)
            timeline_fields = (
                ()
                if timeline_row is None
                else tuple(
                    _json_object(
                        timeline_row["payload_json"],
                        "sonara_timeline.payload_json",
                    )
                )
            )
            return TrackDetail(
                **summary.__dict__,
                file=FileTechnical(
                    file_size_bytes=int(row["file_size_bytes"]),
                    file_modified_ns=int(row["file_modified_ns"]),
                    audio_format=_optional_text(row["audio_format"]),
                    audio_codec=_optional_text(row["audio_codec"]),
                    sample_rate_hz=_optional_int(row["sample_rate_hz"]),
                    channel_count=_optional_int(row["channel_count"]),
                    bit_rate_bps=_optional_int(row["bit_rate_bps"]),
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
                optional_outputs=OptionalOutputs(
                    timeline_fields=timeline_fields,
                    sonara_embedding_available=coverage[numeric_id].sonara_embedding,
                    audio_fingerprint_available=coverage[numeric_id].fingerprint,
                ),
            )

    def get_media_path(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> Path:
        with self._open_library_bundle() as (
            core_connection,
            _artifacts_connection,
            _context,
        ):
            missing_sql = "" if include_missing else "AND missing_since IS NULL"
            row = core_connection.execute(
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
    ) -> TrackSummary:
        if not isinstance(liked, bool):
            raise TypeError("liked must be a bool")
        if expected.catalog_uuid != self.catalog_uuid:
            raise RuntimeError("Track like candidate belongs to a different catalog")
        with (
            self._write_lock,
            self._open_library_bundle() as (
                core_connection,
                artifacts_connection,
                context,
            ),
        ):
            core_connection.execute("BEGIN IMMEDIATE")
            try:
                row = core_connection.execute(
                    """
                    SELECT track_id, track_uuid, content_generation
                    FROM tracks
                    WHERE track_id = ?
                      AND track_uuid = ?
                      AND content_generation = ?
                      AND missing_since IS NULL
                    """,
                    (
                        expected.track_id,
                        expected.track_uuid,
                        expected.content_generation,
                    ),
                ).fetchone()
                if row is None:
                    raise RuntimeError(
                        "Track identity or content generation changed before "
                        "the liked-state mutation"
                    )
                if liked:
                    core_connection.execute(
                        """
                        INSERT INTO likes(track_id, liked_at)
                        VALUES (?, ?)
                        ON CONFLICT(track_id) DO UPDATE SET
                            liked_at = excluded.liked_at
                        """,
                        (expected.track_id, utc_now_text()),
                    )
                else:
                    core_connection.execute(
                        "DELETE FROM likes WHERE track_id = ?",
                        (expected.track_id,),
                    )
                base_row = core_connection.execute(
                    f"""
                    SELECT {_base_select_fields()}
                    FROM tracks t
                    LEFT JOIN file_tags ft ON ft.track_id = t.track_id
                    WHERE t.track_id = ?
                    """,
                    (expected.track_id,),
                ).fetchone()
                assert base_row is not None
                summary = _assemble_summaries(
                    core_connection,
                    artifacts_connection,
                    context=context,
                    rows=[base_row],
                )[0]
                core_connection.commit()
                return summary
            except BaseException:
                if core_connection.in_transaction:
                    core_connection.rollback()
                raise

    def list_liked_track_ids(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[int, ...]:
        with self._open_library_bundle() as (
            core_connection,
            _artifacts_connection,
            _context,
        ):
            missing_sql = "" if include_missing else "WHERE t.missing_since IS NULL"
            rows = core_connection.execute(
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

        with self._open_library_bundle() as (
            core_connection,
            _artifacts_connection,
            context,
        ):
            contract = context.active_contracts.get(("maest", "analysis"))
            if contract is None:
                return ()
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            rows = core_connection.execute(
                f"""
                SELECT
                    t.track_id,
                    t.track_uuid,
                    t.file_path,
                    t.content_generation,
                    t.file_size_bytes,
                    t.file_modified_ns,
                    ms.contract_hash,
                    ms.syncopated_rhythm,
                    ms.genres_json,
                    ms.analyzed_at
                FROM tracks t
                JOIN maest_scores ms
                  ON ms.track_id = t.track_id
                 AND ms.content_generation = t.content_generation
                 AND ms.contract_hash = ?
                WHERE 1 = 1
                {missing_sql}
                ORDER BY t.file_path COLLATE NOCASE, t.track_id
                """,
                (contract.contract_hash,),
            ).fetchall()
            candidates: list[GenreTagCandidate] = []
            for row in rows:
                valid, _reason = validate_maest_analysis_row(
                    row,
                    expected_contract=contract,
                    expected_track_id=int(row["track_id"]),
                    expected_content_generation=int(row["content_generation"]),
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
                        content_generation=int(row["content_generation"]),
                        expected_file_size_bytes=int(row["file_size_bytes"]),
                        expected_file_modified_ns=int(row["file_modified_ns"]),
                        genres=genres,
                        maest_analyzed_at=str(row["analyzed_at"]),
                    )
                )
            return tuple(candidates)

    def load_sonara_timeline(
        self,
        track_id: int,
    ) -> Mapping[str, object] | None:
        with self._open_library_bundle() as (
            core_connection,
            artifacts_connection,
            context,
        ):
            track = core_connection.execute(
                """
                SELECT track_id, track_uuid, content_generation
                FROM tracks
                WHERE track_id = ?
                  AND missing_since IS NULL
                """,
                (int(track_id),),
            ).fetchone()
            if track is None:
                raise KeyError(f"Unknown current track id: {track_id}")
            rows = _valid_timeline_rows(
                artifacts_connection,
                catalog_uuid=context.catalog_uuid,
                contract=context.active_contracts.get(("sonara", "timeline")),
                identities={
                    int(track["track_id"]): (
                        str(track["track_uuid"]),
                        int(track["content_generation"]),
                    )
                },
            )
            timeline = rows.get(int(track_id))
            if timeline is None:
                return None
            return _json_object(
                timeline["payload_json"],
                "sonara_timeline.payload_json",
            )

    def get_optional_outputs(self, track_id: int) -> OptionalOutputs:
        detail = self.get_track_detail(track_id)
        return detail.optional_outputs

    def export_track_rows(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> tuple[ExportTrackRow, ...]:
        requested = tuple(int(track_id) for track_id in track_ids)
        if not requested:
            return ()
        with self._open_library_bundle() as (
            core_connection,
            _artifacts_connection,
            context,
        ):
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            rows = core_connection.execute(
                f"""
                SELECT
                    t.track_id,
                    t.track_uuid,
                    t.content_generation,
                    t.file_path,
                    ft.artist,
                    ft.title,
                    ft.album,
                    ft.tag_bpm,
                    ft.tag_key
                FROM tracks t
                LEFT JOIN file_tags ft ON ft.track_id = t.track_id
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
                    core_connection,
                    track_id=track_id,
                    generation=int(row["content_generation"]),
                    contract=context.active_contracts.get(("sonara", "core")),
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

    def library_summary(
        self,
        classifier_keys: Iterable[str] | None = None,
        *,
        include_missing: bool = False,
    ) -> LibrarySummary:
        requested_classifiers = tuple(
            sorted({key.strip() for key in (classifier_keys or ()) if key.strip()})
        )
        with self._open_library_bundle() as (
            core_connection,
            artifacts_connection,
            context,
        ):
            missing_sql = "" if include_missing else "WHERE t.missing_since IS NULL"
            rows = core_connection.execute(
                f"""
                SELECT
                    t.track_id,
                    t.track_uuid,
                    t.content_generation,
                    EXISTS(
                        SELECT 1 FROM likes l
                        WHERE l.track_id = t.track_id
                    ) AS liked
                FROM tracks t
                {missing_sql}
                """
            ).fetchall()
            identities = _identity_map(rows)
            sonara = _valid_sonara_core_ids(
                core_connection,
                contract=context.active_contracts.get(("sonara", "core")),
                identities=identities,
            )
            maest_analysis = _valid_maest_analysis_ids(
                core_connection,
                contract=context.active_contracts.get(("maest", "analysis")),
                identities=identities,
            )
            artifact_counts: dict[str, int] = {}
            for family in ("maest", "mert", "muq", "clap"):
                valid = _valid_artifact_rows(
                    artifacts_connection,
                    catalog_uuid=context.catalog_uuid,
                    table=f"{family}_embeddings",
                    contract=context.active_contracts.get((family, "embedding")),
                    identities=identities,
                    embedding=True,
                )
                artifact_counts[family] = len(valid)
            classifier_rows = _current_classifier_details(
                core_connection,
                identities=identities,
                active_release_hash=context.active_release_hash,
                active_required_outputs_hashes=(
                    context.active_classifier_required_outputs_hashes
                ),
            )
            if requested_classifiers:
                expected = set(requested_classifiers)
                classifier_count = sum(
                    expected.issubset({score.classifier_key for score in scores})
                    for scores in classifier_rows.values()
                )
            else:
                classifier_count = len(classifier_rows)
            return LibrarySummary(
                tracks=len(rows),
                sonara=len(sonara),
                maest_analysis=len(maest_analysis),
                maest_embedding=artifact_counts["maest"],
                mert=artifact_counts["mert"],
                muq=artifact_counts["muq"],
                clap=artifact_counts["clap"],
                liked=sum(bool(row["liked"]) for row in rows),
                classifiers=classifier_count,
            )
