from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class SonaraCoreStorage:
    features: dict[str, object]
    bpm: float | None
    musical_key: str | None
    energy: float | None
    duration: float | None
    model_name: str
    provenance: dict[str, object] | None
    analysis_signature: dict[str, object] | None


@dataclass(frozen=True)
class SonaraTimelineStorage:
    timeline: dict[str, object]
    provenance: dict[str, object] | None
    analysis_signature: dict[str, object]


@dataclass(frozen=True)
class SonaraRepresentationsStorage:
    embedding: np.ndarray
    fingerprint: dict[str, object]
    embedding_version: str | None
    fingerprint_version: str | None
    model_name: str
    provenance: dict[str, object] | None
    analysis_signature: dict[str, object]


@dataclass(frozen=True)
class SonaraAnalysisStorage:
    track_id: int
    core: SonaraCoreStorage | None = None
    timeline: SonaraTimelineStorage | None = None
    representations: SonaraRepresentationsStorage | None = None


# ---------------------------------------------------------------------------
# v7 high-level writer — does NOT modify the v6 dataclasses above
# ---------------------------------------------------------------------------

def save_sonara_core_v7(
    connection: "sqlite3.Connection",
    track_id: int,
    content_generation: int,
    sonara_output: "dict[str, object]",
    analyzed_at: str,
    *,
    model_name: str,
    model_version: str,
    release_hash: str,
) -> str:
    """Upsert the SONARA Core contract and write one row to the v7 ``sonara`` table.

    This is the single entry point callers should use.  It combines
    :func:`~dj_track_similarity.db_analysis.upsert_sonara_contract_v7` and
    :func:`~dj_track_similarity.db_analysis.save_sonara_row_v7` inside one
    transaction so the contract row always exists before the ``sonara`` FK is
    written.

    Args:
        connection: An open :class:`sqlite3.Connection` to a v7 schema database.
        track_id: The ``tracks.track_id`` for this result.
        content_generation: The ``tracks.content_generation`` value at analysis time.
        sonara_output: Flat dict of SONARA Core outputs.  Keys match the column
            names in the ``sonara`` table.  The three timbre BLOBs
            (``mfcc_mean_blob``, ``chroma_mean_blob``,
            ``spectral_contrast_mean_blob``) are required and must be either
            ``bytes`` of the correct length or a sequence of floats that will be
            packed as float32-le.
        analyzed_at: ISO-8601 timestamp string recorded in ``sonara.analyzed_at``.
        model_name: Passed to :func:`upsert_sonara_contract_v7`.
        model_version: Passed to :func:`upsert_sonara_contract_v7`.
        release_hash: Passed to :func:`upsert_sonara_contract_v7`.

    Returns:
        The ``contract_hash`` string (``"sha256:<hex>"``).

    Raises:
        ValueError: If any required BLOB is missing or has the wrong length.
    """
    import sqlite3  # local import to avoid circular at module level

    from .db_analysis import save_sonara_row_v7, upsert_sonara_contract_v7

    with connection:
        contract_hash = upsert_sonara_contract_v7(
            connection,
            model_name=model_name,
            model_version=model_version,
            release_hash=release_hash,
        )
        save_sonara_row_v7(
            connection,
            track_id=track_id,
            content_generation=content_generation,
            contract_hash=contract_hash,
            sonara_output=sonara_output,
            analyzed_at=analyzed_at,
        )

    return contract_hash


# ---------------------------------------------------------------------------
# v7 sidecar writers — timeline, fingerprint, similarity embedding
# ---------------------------------------------------------------------------

def save_sonara_timeline_v7(
    artifacts_connection: "sqlite3.Connection",
    track_id: int,
    track_uuid: str,
    content_generation: int,
    contract_hash: str,
    payload_json: str,
    analyzed_at: str,
) -> None:
    """Write one row to ``sonara_timeline`` in the artifacts sidecar.

    Args:
        artifacts_connection: Open connection to the artifacts sidecar DB.
        track_id: The ``tracks.track_id`` for this result.
        track_uuid: The ``tracks.track_uuid`` string.
        content_generation: The ``tracks.content_generation`` value at analysis time.
        contract_hash: Pre-computed contract hash (``"sha256:<hex>"``).
        payload_json: Valid JSON object string (validated by SQLite CHECK).
        analyzed_at: ISO-8601 timestamp string.
    """
    import sqlite3  # local import to avoid circular at module level

    with artifacts_connection:
        artifacts_connection.execute(
            """
            INSERT OR REPLACE INTO sonara_timeline (
                track_id, track_uuid, content_generation, contract_hash,
                payload_json, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (track_id, track_uuid, content_generation, contract_hash, payload_json, analyzed_at),
        )


def save_sonara_fingerprint_v7(
    artifacts_connection: "sqlite3.Connection",
    track_id: int,
    track_uuid: str,
    content_generation: int,
    contract_hash: str,
    fingerprint_version: str,
    word_list: "Sequence[int]",
    analyzed_at: str,
) -> None:
    """Write one row to ``sonara_fingerprints`` in the artifacts sidecar.

    Args:
        artifacts_connection: Open connection to the artifacts sidecar DB.
        track_id: The ``tracks.track_id`` for this result.
        track_uuid: The ``tracks.track_uuid`` string.
        content_generation: The ``tracks.content_generation`` value at analysis time.
        contract_hash: Pre-computed contract hash (``"sha256:<hex>"``).
        fingerprint_version: Version string for the fingerprint algorithm.
        word_list: Sequence of uint32 integers (NOT a JSON string — v7 format).
            All values must be in ``0 ≤ v ≤ 4_294_967_295``.
        analyzed_at: ISO-8601 timestamp string.

    Raises:
        ValueError: If ``word_list`` is a dict (v6 format rejected), or if any
            value is out of the uint32 range.
    """
    import struct
    import sqlite3  # local import to avoid circular at module level

    # Reject v6 JSON-array-under-payload_json format
    if isinstance(word_list, dict):
        raise ValueError(
            "v6 fingerprint format rejected — pass a list of uint32 integers directly"
        )

    # Validate all values are in uint32 range
    uint32_max = 4_294_967_295
    for i, v in enumerate(word_list):
        if not (0 <= v <= uint32_max):
            raise ValueError(
                f"word_list[{i}] = {v} is out of uint32 range [0, {uint32_max}]"
            )

    word_count = len(word_list)
    fingerprint_blob = struct.pack(f"<{word_count}I", *word_list)

    with artifacts_connection:
        artifacts_connection.execute(
            """
            INSERT OR REPLACE INTO sonara_fingerprints (
                track_id, track_uuid, content_generation, contract_hash,
                fingerprint_version, word_count, byte_order, fingerprint_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'little', ?, ?)
            """,
            (
                track_id, track_uuid, content_generation, contract_hash,
                fingerprint_version, word_count, fingerprint_blob, analyzed_at,
            ),
        )


def save_sonara_similarity_embedding_v7(
    artifacts_connection: "sqlite3.Connection",
    track_id: int,
    track_uuid: str,
    content_generation: int,
    contract_hash: str,
    embedding: "np.ndarray | Sequence[float]",
    normalization: str,
    analyzed_at: str,
) -> None:
    """Write one row to ``sonara_similarity_embeddings`` in the artifacts sidecar.

    Args:
        artifacts_connection: Open connection to the artifacts sidecar DB.
        track_id: The ``tracks.track_id`` for this result.
        track_uuid: The ``tracks.track_uuid`` string.
        content_generation: The ``tracks.content_generation`` value at analysis time.
        contract_hash: Pre-computed contract hash (``"sha256:<hex>"``).
        embedding: Numpy array or sequence of floats; packed as little-endian float32.
        normalization: One of ``'none'`` or ``'l2'``.
        analyzed_at: ISO-8601 timestamp string.

    Raises:
        ValueError: If ``normalization`` is not ``'none'`` or ``'l2'``.
    """
    import sqlite3  # local import to avoid circular at module level

    if normalization not in ("none", "l2"):
        raise ValueError(
            f"normalization must be 'none' or 'l2', got {normalization!r}"
        )

    arr = np.asarray(embedding, dtype="<f4")
    dim = len(arr)
    embedding_blob = arr.tobytes()

    with artifacts_connection:
        artifacts_connection.execute(
            """
            INSERT OR REPLACE INTO sonara_similarity_embeddings (
                track_id, track_uuid, content_generation, contract_hash,
                dim, normalization, embedding_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id, track_uuid, content_generation, contract_hash,
                dim, normalization, embedding_blob, analyzed_at,
            ),
        )
