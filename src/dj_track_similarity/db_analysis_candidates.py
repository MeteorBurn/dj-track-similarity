"""Current-generation candidate readiness for the analysis repository."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from .analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
)
from .db_artifacts import (
    ArtifactTrackIdentity,
    validate_embedding_row_payload,
    validate_fingerprint_row_payload,
    validate_timeline_row_payload,
)
from .maest_analysis_validation import (
    MAEST_ANALYSIS_COLUMNS,
    validate_maest_analysis_row,
)
from .sonara_core_validation import (
    SONARA_CORE_COLUMNS,
    validate_sonara_core_row,
)


_CORE_TABLE_BY_OUTPUT = {
    ("sonara", "core"): "sonara",
    ("maest", "analysis"): "maest_scores",
}
_ARTIFACT_TABLE_BY_OUTPUT = {
    ("maest", "embedding"): "maest_embeddings",
    ("mert", "embedding"): "mert_embeddings",
    ("muq", "embedding"): "muq_embeddings",
    ("clap", "embedding"): "clap_embeddings",
    ("sonara", "embedding"): "sonara_similarity_embeddings",
    ("sonara", "timeline"): "sonara_timeline",
    ("sonara", "fingerprint"): "sonara_fingerprints",
}


def normalize_analysis_outputs(
    outputs: Sequence[AnalysisOutput],
) -> tuple[AnalysisOutput, ...]:
    normalized = tuple(outputs)
    if not normalized:
        raise ValueError("at least one analysis output is required")
    if any(not isinstance(output, AnalysisOutput) for output in normalized):
        raise TypeError("outputs must contain only AnalysisOutput values")
    keys = [output.key for output in normalized]
    if len(set(keys)) != len(keys):
        raise ValueError(
            "outputs must contain at most one value per family/output"
        )
    return normalized


def artifact_table_for_output(output: AnalysisOutput) -> str | None:
    return _ARTIFACT_TABLE_BY_OUTPUT.get(output.key)


def core_table_for_output(output: AnalysisOutput) -> str | None:
    return _CORE_TABLE_BY_OUTPUT.get(output.key)


def require_active_analysis_outputs(
    core_connection: sqlite3.Connection,
    outputs: Sequence[AnalysisOutput],
) -> tuple[AnalysisOutput, ...]:
    del core_connection
    return normalize_analysis_outputs(outputs)


def read_current_track_rows(
    core_connection: sqlite3.Connection,
) -> list[sqlite3.Row]:
    return core_connection.execute(
        """
        SELECT track_id, track_uuid, file_path, file_size_bytes,
               file_modified_ns, content_generation
        FROM tracks
        WHERE missing_since IS NULL
        ORDER BY file_path COLLATE NOCASE, track_id
        """
    ).fetchall()


def target_from_track_row(
    row: sqlite3.Row,
    *,
    catalog_uuid: str,
) -> AnalysisTarget:
    return AnalysisTarget(
        catalog_uuid=catalog_uuid,
        track_id=int(row["track_id"]),
        track_uuid=str(row["track_uuid"]),
        content_generation=int(row["content_generation"]),
    )


def ready_target_keys_by_output(
    *,
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    catalog_uuid: str,
    outputs: Sequence[AnalysisOutput],
) -> dict[tuple[str, str], set[tuple[int, str, int]]]:
    normalized = require_active_analysis_outputs(core_connection, outputs)
    current_tracks = {
        int(row["track_id"]): ArtifactTrackIdentity(
            catalog_uuid=catalog_uuid,
            track_id=int(row["track_id"]),
            track_uuid=str(row["track_uuid"]),
            content_generation=int(row["content_generation"]),
        )
        for row in read_current_track_rows(core_connection)
    }
    ready: dict[tuple[str, str], set[tuple[int, str, int]]] = {}
    for output in normalized:
        core_table = core_table_for_output(output)
        if output.key == ("sonara", "core"):
            rows = _valid_sonara_core_rows(
                core_connection,
                output=output,
                current_tracks=current_tracks,
            )
        elif output.key == ("maest", "analysis"):
            rows = _valid_maest_analysis_rows(
                core_connection,
                output=output,
                current_tracks=current_tracks,
            )
        elif core_table is not None:
            rows = core_connection.execute(
                f"""
                SELECT stored.track_id, tracks.track_uuid,
                       stored.content_generation
                FROM {core_table} AS stored
                JOIN tracks ON tracks.track_id = stored.track_id
                WHERE stored.content_generation = tracks.content_generation
                  AND tracks.missing_since IS NULL
                """
            )
        else:
            artifact_table = artifact_table_for_output(output)
            if artifact_table is None:
                raise ValueError(
                    "unsupported analysis output "
                    f"{output.analysis_family}/{output.output_kind}"
                )
            rows = _valid_artifact_rows(
                artifacts_connection,
                table=artifact_table,
                output=output,
                current_tracks=current_tracks,
            )
        ready[output.key] = {(int(row[0]), str(row[1]), int(row[2])) for row in rows}
    return ready


def _valid_sonara_core_rows(
    connection: sqlite3.Connection,
    *,
    output: AnalysisOutput,
    current_tracks: dict[int, ArtifactTrackIdentity],
) -> tuple[tuple[int, str, int], ...]:
    rows = connection.execute(
        f"""
        SELECT {", ".join(SONARA_CORE_COLUMNS)}
        FROM sonara
        """
    ).fetchall()
    valid_rows: list[tuple[int, str, int]] = []
    for row in rows:
        expected_track = current_tracks.get(int(row["track_id"]))
        if expected_track is None:
            continue
        valid, _reason = validate_sonara_core_row(
            row,
            expected_track_id=expected_track.track_id,
            expected_content_generation=expected_track.content_generation,
        )
        if valid:
            valid_rows.append(
                (
                    expected_track.track_id,
                    expected_track.track_uuid,
                    expected_track.content_generation,
                )
            )
    return tuple(valid_rows)


def _valid_maest_analysis_rows(
    connection: sqlite3.Connection,
    *,
    output: AnalysisOutput,
    current_tracks: dict[int, ArtifactTrackIdentity],
) -> tuple[tuple[int, str, int], ...]:
    rows = connection.execute(
        f"""
        SELECT {", ".join(MAEST_ANALYSIS_COLUMNS)}
        FROM maest_scores
        """
    ).fetchall()
    valid_rows: list[tuple[int, str, int]] = []
    for row in rows:
        expected_track = current_tracks.get(int(row["track_id"]))
        if expected_track is None:
            continue
        valid, _reason = validate_maest_analysis_row(
            row,
            expected_track_id=expected_track.track_id,
            expected_content_generation=expected_track.content_generation,
        )
        if valid:
            valid_rows.append(
                (
                    expected_track.track_id,
                    expected_track.track_uuid,
                    expected_track.content_generation,
                )
            )
    return tuple(valid_rows)


def _valid_artifact_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    output: AnalysisOutput,
    current_tracks: dict[int, ArtifactTrackIdentity],
) -> tuple[sqlite3.Row, ...]:
    if output.output_kind == "embedding":
        payload_fields = "dim, normalization, embedding_blob"
    elif output.key == ("sonara", "timeline"):
        payload_fields = "payload_json"
    elif output.key == ("sonara", "fingerprint"):
        payload_fields = "fingerprint_version, word_count, byte_order, fingerprint_blob"
    else:
        raise ValueError(
            "unsupported artifact output "
            f"{output.analysis_family}/{output.output_kind}"
        )
    rows = connection.execute(
        f"""
        SELECT track_id, track_uuid, content_generation,
               {payload_fields}
        FROM {table}
        """
    ).fetchall()
    valid: list[sqlite3.Row] = []
    for row in rows:
        expected_track = current_tracks.get(int(row["track_id"]))
        if expected_track is None:
            continue
        if output.output_kind == "embedding":
            is_valid, _reason = validate_embedding_row_payload(
                family=output.analysis_family,
                row=row,
                expected_track=expected_track,
            )
        elif output.key == ("sonara", "timeline"):
            is_valid, _reason = validate_timeline_row_payload(
                row=row,
                expected_track=expected_track,
            )
        else:
            is_valid, _reason = validate_fingerprint_row_payload(
                row=row,
                expected_track=expected_track,
            )
        if is_valid:
            valid.append(row)
    return tuple(valid)


def missing_outputs_for_target(
    target: AnalysisTarget,
    outputs: Sequence[AnalysisOutput],
    ready: dict[tuple[str, str], set[tuple[int, str, int]]],
) -> tuple[AnalysisOutput, ...]:
    target_key = (
        target.track_id,
        target.track_uuid,
        target.content_generation,
    )
    return tuple(
        output for output in outputs if target_key not in ready.get(output.key, set())
    )


def collect_analysis_candidates(
    *,
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    catalog_uuid: str,
    outputs: Sequence[AnalysisOutput],
    limit: int | None,
) -> list[AnalysisCandidate]:
    normalized = require_active_analysis_outputs(core_connection, outputs)
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer or None")
        if limit == 0:
            return []
    ready = ready_target_keys_by_output(
        core_connection=core_connection,
        artifacts_connection=artifacts_connection,
        catalog_uuid=catalog_uuid,
        outputs=normalized,
    )
    candidates: list[AnalysisCandidate] = []
    for row in read_current_track_rows(core_connection):
        target = target_from_track_row(row, catalog_uuid=catalog_uuid)
        missing = missing_outputs_for_target(target, normalized, ready)
        if not missing:
            continue
        candidates.append(
            AnalysisCandidate(
                target=target,
                file_path=str(row["file_path"]),
                file_size_bytes=int(row["file_size_bytes"]),
                file_modified_ns=int(row["file_modified_ns"]),
                missing_outputs=missing,
            )
        )
        if limit is not None and len(candidates) >= limit:
            break
    return candidates
