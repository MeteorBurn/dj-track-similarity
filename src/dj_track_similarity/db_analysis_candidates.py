"""Analysis candidate readiness in one library connection."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from .analysis_models import AnalysisCandidate, AnalysisOutput, AnalysisTarget
from .db_embeddings import EmbeddingTrackIdentity
from .maest_analysis_validation import MAEST_ANALYSIS_COLUMNS, validate_maest_analysis_row
from .maest_windows import MaestWindowContext
from .sonara_core_validation import SONARA_CORE_COLUMNS, validate_sonara_core_row


_TABLE_BY_OUTPUT = {
    ("sonara", "core"): "sonara_features",
    ("maest", "analysis"): "maest_genres",
    ("maest", "embedding"): "maest_embeddings",
    ("mert", "embedding"): "mert_embeddings",
    ("muq", "embedding"): "muq_embeddings",
    ("mulan", "embedding"): "mulan_embeddings",
    ("clap", "embedding"): "clap_embeddings",
    ("sonara", "embedding"): "sonara_embeddings",
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
        raise ValueError("outputs must contain at most one value per family/output")
    return normalized


def table_for_output(output: AnalysisOutput) -> str | None:
    return _TABLE_BY_OUTPUT.get(output.key)


def require_active_analysis_outputs(
    connection: sqlite3.Connection,
    outputs: Sequence[AnalysisOutput],
) -> tuple[AnalysisOutput, ...]:
    del connection
    return normalize_analysis_outputs(outputs)


def read_current_track_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            tracks.track_id, tracks.track_uuid, tracks.file_path,
            tracks.file_size_bytes, tracks.file_modified_ns,
            sonara.leading_silence_seconds,
            sonara.trailing_silence_seconds,
            sonara.intro_end_seconds,
            sonara.outro_start_seconds
        FROM tracks
        LEFT JOIN sonara_features AS sonara
          ON sonara.track_id = tracks.track_id
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
        leading_silence_seconds=(None if values[0] is None else float(values[0])),
        trailing_silence_seconds=(None if values[1] is None else float(values[1])),
        intro_end_seconds=None if values[2] is None else float(values[2]),
        outro_start_seconds=None if values[3] is None else float(values[3]),
    )


def _current_tracks(
    connection: sqlite3.Connection,
    *,
    catalog_uuid: str,
) -> dict[int, EmbeddingTrackIdentity]:
    return {
        int(row["track_id"]): EmbeddingTrackIdentity(
            catalog_uuid=catalog_uuid,
            track_id=int(row["track_id"]),
            track_uuid=str(row["track_uuid"]),
        )
        for row in read_current_track_rows(connection)
    }


def current_sonara_target_keys(
    connection: sqlite3.Connection,
    *,
    catalog_uuid: str,
) -> set[tuple[int, str]]:
    return set(
        _valid_sonara_rows(
            connection,
            current_tracks=_current_tracks(connection, catalog_uuid=catalog_uuid),
        )
    )


def ready_target_keys_by_output(
    *,
    connection: sqlite3.Connection,
    catalog_uuid: str,
    outputs: Sequence[AnalysisOutput],
) -> dict[tuple[str, str], set[tuple[int, str]]]:
    normalized = require_active_analysis_outputs(connection, outputs)
    current_tracks = _current_tracks(connection, catalog_uuid=catalog_uuid)
    ready: dict[tuple[str, str], set[tuple[int, str]]] = {}
    for output in normalized:
        if output.key == ("sonara", "core"):
            rows = _valid_sonara_rows(connection, current_tracks=current_tracks)
        elif output.key == ("maest", "analysis"):
            rows = _valid_maest_rows(connection, current_tracks=current_tracks)
        elif output.output_kind == "embedding":
            table = table_for_output(output)
            if table is None:
                raise ValueError(
                    "unsupported analysis output "
                    f"{output.analysis_family}/{output.output_kind}"
                )
            rows = _valid_embedding_rows(
                connection,
                table=table,
                current_tracks=current_tracks,
            )
        else:
            raise ValueError(
                "unsupported analysis output "
                f"{output.analysis_family}/{output.output_kind}"
            )
        ready[output.key] = set(rows)
    return ready


def _valid_sonara_rows(
    connection: sqlite3.Connection,
    *,
    current_tracks: dict[int, EmbeddingTrackIdentity],
) -> tuple[tuple[int, str], ...]:
    rows = connection.execute(
        f"SELECT {', '.join(SONARA_CORE_COLUMNS)} FROM sonara_features"
    ).fetchall()
    valid: list[tuple[int, str]] = []
    for row in rows:
        expected = current_tracks.get(int(row["track_id"]))
        if expected is None:
            continue
        is_valid, _reason = validate_sonara_core_row(
            row,
            expected_track_id=expected.track_id,
        )
        if is_valid:
            valid.append((expected.track_id, expected.track_uuid))
    return tuple(valid)


def _valid_maest_rows(
    connection: sqlite3.Connection,
    *,
    current_tracks: dict[int, EmbeddingTrackIdentity],
) -> tuple[tuple[int, str], ...]:
    rows = connection.execute(
        f"SELECT {', '.join(MAEST_ANALYSIS_COLUMNS)} FROM maest_genres"
    ).fetchall()
    valid: list[tuple[int, str]] = []
    for row in rows:
        expected = current_tracks.get(int(row["track_id"]))
        if expected is None:
            continue
        is_valid, _reason = validate_maest_analysis_row(
            row,
            expected_track_id=expected.track_id,
        )
        if is_valid:
            valid.append((expected.track_id, expected.track_uuid))
    return tuple(valid)


def _valid_embedding_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    current_tracks: dict[int, EmbeddingTrackIdentity],
) -> tuple[tuple[int, str], ...]:
    rows = connection.execute(
        f"""
        SELECT track_id, track_uuid
        FROM {table}
        """
    ).fetchall()
    valid: list[tuple[int, str]] = []
    for row in rows:
        expected = current_tracks.get(int(row["track_id"]))
        if expected is None:
            continue
        if str(row["track_uuid"]) != expected.track_uuid:
            continue
        valid.append((expected.track_id, expected.track_uuid))
    return tuple(valid)


def missing_outputs_for_target(
    target: AnalysisTarget,
    outputs: Sequence[AnalysisOutput],
    ready: dict[tuple[str, str], set[tuple[int, str]]],
) -> tuple[AnalysisOutput, ...]:
    target_key = (target.track_id, target.track_uuid)
    return tuple(output for output in outputs if target_key not in ready.get(output.key, set()))


def collect_analysis_candidates(
    *,
    connection: sqlite3.Connection,
    catalog_uuid: str,
    outputs: Sequence[AnalysisOutput],
    limit: int | None,
    require_current_sonara: bool = False,
) -> list[AnalysisCandidate]:
    normalized = normalize_analysis_outputs(outputs)
    if not isinstance(require_current_sonara, bool):
        raise TypeError("require_current_sonara must be a boolean")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("limit must be a non-negative integer or None")
        if limit == 0:
            return []
    sonara_output = AnalysisOutput("sonara", "core")
    needs_sonara = require_current_sonara or any(
        output.analysis_family == "maest" for output in normalized
    )
    readiness_outputs = (
        normalized
        if not needs_sonara or sonara_output in normalized
        else (*normalized, sonara_output)
    )
    ready = ready_target_keys_by_output(
        connection=connection,
        catalog_uuid=catalog_uuid,
        outputs=readiness_outputs,
    )
    sonara_ready = ready.get(sonara_output.key, set()) if needs_sonara else set()
    candidates: list[AnalysisCandidate] = []
    for row in read_current_track_rows(connection):
        target = target_from_track_row(row, catalog_uuid=catalog_uuid)
        target_key = (target.track_id, target.track_uuid)
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
                    _maest_window_context(row) if target_key in sonara_ready else None
                ),
            )
        )
        if limit is not None and len(candidates) >= limit:
            break
    return candidates
