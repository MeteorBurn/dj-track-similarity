"""Analysis candidate readiness in one library connection."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from ..analysis_models import (
    EMBEDDING_LAYERS,
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
)
from .embeddings import EmbeddingTrackIdentity
from .embedding_layers import require_embedding_layers


_TABLE_BY_OUTPUT = {
    ("sonara", "core"): "sonara_features",
    ("maest", "analysis"): "maest_genres",
    ("maest", "embedding"): "maest_embeddings",
    ("mert_v2", "embedding"): "mert_v2_embeddings",
    ("muq", "embedding"): "muq_embeddings",
    ("mulan", "embedding"): "mulan_embeddings",
    ("clap", "embedding"): "clap_embeddings",
    ("sonara", "embedding"): "sonara_embeddings",
    ("sonara", "fingerprint"): "sonara_fingerprints",
    ("sonara", "timeline"): "sonara_timeline",
}


def require_sonara_timeline(connection: sqlite3.Connection) -> None:
    """Fail clearly on a library that never received the sonara_timeline table."""

    exists = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'sonara_timeline'"
    ).fetchone()
    if exists is None:
        raise RuntimeError(
            "This library database has no sonara_timeline table; "
            "SONARA Timeline cannot be stored or read until the table is added"
        )


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


def read_current_track_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT
            tracks.track_id, tracks.track_uuid, tracks.file_path,
            tracks.file_size_bytes, tracks.file_modified_ns
        FROM tracks
        WHERE tracks.missing_since IS NULL
        ORDER BY tracks.file_path COLLATE NOCASE, tracks.track_id
        """
    ).fetchall()


def read_current_track_identities(
    connection: sqlite3.Connection,
) -> list[sqlite3.Row]:
    """Read only what a search needs: the identity of every current track.

    Analysis candidates also need file facts. Search only needs identities;
    keep the same ordering for deterministic tie-breaking among equal scores.
    """

    return connection.execute(
        """
        SELECT track_id, track_uuid
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
        _current_track_rows(
            connection,
            table="sonara_features",
            current_tracks=_current_tracks(connection, catalog_uuid=catalog_uuid),
        )
    )


def ready_target_keys_by_output(
    *,
    connection: sqlite3.Connection,
    catalog_uuid: str,
    outputs: Sequence[AnalysisOutput],
) -> dict[tuple[str, str], set[tuple[int, str]]]:
    normalized = normalize_analysis_outputs(outputs)
    current_tracks = _current_tracks(connection, catalog_uuid=catalog_uuid)
    ready: dict[tuple[str, str], set[tuple[int, str]]] = {}
    for output in normalized:
        # Like embeddings, SONARA and MAEST readiness is the stored row of the
        # current track: the writer validated the payload, and checking every
        # stored row per status request or job start would dominate large libraries.
        if output.key in {("sonara", "core"), ("maest", "analysis")}:
            rows = _current_track_rows(
                connection,
                table=_TABLE_BY_OUTPUT[output.key],
                current_tracks=current_tracks,
            )
        elif output.key in {("sonara", "fingerprint"), ("sonara", "timeline")}:
            if output.key == ("sonara", "timeline"):
                require_sonara_timeline(connection)
            rows = _valid_embedding_rows(
                connection,
                table=_TABLE_BY_OUTPUT[output.key],
                current_tracks=current_tracks,
            )
        elif output.output_kind == "embedding":
            table = table_for_output(output)
            if table is None:
                raise ValueError(
                    "unsupported analysis output "
                    f"{output.analysis_family}/{output.output_kind}"
                )
            # A layered family is ready on its default-layer row: the writer
            # replaces all layers of a track in one validated transaction, so
            # that row stands for the set. A track migrated with only the
            # default layer is ready too; resetting the family refills it.
            layers = EMBEDDING_LAYERS.get(output.analysis_family)
            if layers is not None:
                require_embedding_layers(connection, output.analysis_family)
            rows = _valid_embedding_rows(
                connection,
                table=table,
                current_tracks=current_tracks,
                layer=None if layers is None else layers.default,
            )

        else:
            raise ValueError(
                "unsupported analysis output "
                f"{output.analysis_family}/{output.output_kind}"
            )
        ready[output.key] = set(rows)
    return ready


def _current_track_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    current_tracks: dict[int, EmbeddingTrackIdentity],
) -> tuple[tuple[int, str], ...]:
    # sonara_features and maest_genres have no track UUID: a row belongs to the
    # track by track_id and is deleted together with it.
    return tuple(
        (expected.track_id, expected.track_uuid)
        for (track_id,) in connection.execute(f"SELECT track_id FROM {table}")
        if (expected := current_tracks.get(int(track_id))) is not None
    )


def _valid_embedding_rows(
    connection: sqlite3.Connection,
    *,
    table: str,
    current_tracks: dict[int, EmbeddingTrackIdentity],
    layer: int | None = None,
) -> tuple[tuple[int, str], ...]:
    # The literal layer spells the WHERE of the partial default-layer index, so
    # the planner reads that covering index alone instead of every layer row.
    layer_filter = "" if layer is None else f"WHERE layer = {int(layer)}"
    rows = connection.execute(
        f"""
        SELECT track_id, track_uuid
        FROM {table}
        {layer_filter}
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
    readiness_outputs = (
        normalized
        if not require_current_sonara or sonara_output in normalized
        else (*normalized, sonara_output)
    )
    ready = ready_target_keys_by_output(
        connection=connection,
        catalog_uuid=catalog_uuid,
        outputs=readiness_outputs,
    )
    sonara_ready = ready.get(sonara_output.key, set()) if require_current_sonara else set()
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
            )
        )
        if limit is not None and len(candidates) >= limit:
            break
    return candidates
