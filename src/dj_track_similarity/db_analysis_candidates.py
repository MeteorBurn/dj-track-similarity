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
)
from .maest_analysis_validation import (
    MAEST_ANALYSIS_COLUMNS,
    validate_maest_analysis_row,
)
from .maest_windows import MaestWindowContext
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
        SELECT
            tracks.track_id, tracks.track_uuid, tracks.file_path,
            tracks.file_size_bytes, tracks.file_modified_ns,
            tracks.content_generation,
            sonara.leading_silence_seconds,
            sonara.trailing_silence_seconds,
            sonara.intro_end_seconds,
            sonara.outro_start_seconds
        FROM tracks
        LEFT JOIN sonara
          ON sonara.track_id = tracks.track_id
         AND sonara.content_generation = tracks.content_generation
        WHERE tracks.missing_since IS NULL
        ORDER BY tracks.file_path COLLATE NOCASE, tracks.track_id
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


def _maest_window_context(row: sqlite3.Row) -> MaestWindowContext | None:
    values = (
        row["leading_silence_seconds"],
        row["trailing_silence_seconds"],
        row["intro_end_seconds"],
        row["outro_start_seconds"],
    )
    if all(value is None for value in values):
        return None
    return MaestWindowContext(
        leading_silence_seconds=(
            None if values[0] is None else float(values[0])
        ),
        trailing_silence_seconds=(
            None if values[1] is None else float(values[1])
        ),
        intro_end_seconds=None if values[2] is None else float(values[2]),
        outro_start_seconds=None if values[3] is None else float(values[3]),
    )


def current_sonara_target_keys(
    core_connection: sqlite3.Connection,
    *,
    catalog_uuid: str,
) -> set[tuple[int, str, int]]:
    current_tracks = {
        int(row["track_id"]): ArtifactTrackIdentity(
            catalog_uuid=catalog_uuid,
            track_id=int(row["track_id"]),
            track_uuid=str(row["track_uuid"]),
            content_generation=int(row["content_generation"]),
        )
        for row in read_current_track_rows(core_connection)
    }
    rows = _valid_sonara_core_rows(
        core_connection,
        output=AnalysisOutput("sonara", "core"),
        current_tracks=current_tracks,
    )
    return {
        (track_id, track_uuid, generation)
        for track_id, track_uuid, generation in rows
    }


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
        else:
            raise ValueError(
                "unsupported artifact output "
                f"{output.analysis_family}/{output.output_kind}"
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
    require_current_sonara: bool = False,
) -> list[AnalysisCandidate]:
    normalized = require_active_analysis_outputs(core_connection, outputs)
    if not isinstance(require_current_sonara, bool):
        raise TypeError("require_current_sonara must be a boolean")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer or None")
        if limit == 0:
            return []
    needs_sonara_readiness = require_current_sonara or any(
        output.analysis_family == "maest" for output in normalized
    )
    sonara_output = AnalysisOutput("sonara", "core")
    readiness_outputs = (
        normalized
        if not needs_sonara_readiness
        or any(output.key == sonara_output.key for output in normalized)
        else (*normalized, sonara_output)
    )
    ready = ready_target_keys_by_output(
        core_connection=core_connection,
        artifacts_connection=artifacts_connection,
        catalog_uuid=catalog_uuid,
        outputs=readiness_outputs,
    )
    sonara_ready = (
        ready.get(sonara_output.key, set())
        if needs_sonara_readiness
        else set()
    )
    candidates: list[AnalysisCandidate] = []
    for row in read_current_track_rows(core_connection):
        target = target_from_track_row(row, catalog_uuid=catalog_uuid)
        target_key = (
            target.track_id,
            target.track_uuid,
            target.content_generation,
        )
        if require_current_sonara and target_key not in sonara_ready:
            continue
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
                maest_window_context=(
                    _maest_window_context(row)
                    if target_key in sonara_ready
                    else None
                ),
            )
        )
        if limit is not None and len(candidates) >= limit:
            break
    return candidates
