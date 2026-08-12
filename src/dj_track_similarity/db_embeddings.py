"""Identity-aware embedding storage inside the single library database."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from .analysis_models import current_embedding_spec
from .db_schema import validate_library_schema


_EMBEDDING_TABLES: Mapping[str, str] = {
    "maest": "maest_embeddings",
    "mert": "mert_embeddings",
    "muq": "muq_embeddings",
    "clap": "clap_embeddings",
}


@dataclass(frozen=True)
class EmbeddingTrackIdentity:
    """Current library identity required for one embedding write."""

    catalog_uuid: str
    track_id: int
    track_uuid: str
    content_generation: int

    def __post_init__(self) -> None:
        if not isinstance(self.catalog_uuid, str) or not self.catalog_uuid.strip():
            raise ValueError("catalog_uuid must be a non-empty string")
        if (
            isinstance(self.track_id, bool)
            or not isinstance(self.track_id, int)
            or self.track_id <= 0
        ):
            raise ValueError("track_id must be a positive integer")
        if not isinstance(self.track_uuid, str) or not self.track_uuid.strip():
            raise ValueError("track_uuid must be a non-empty string")
        if (
            isinstance(self.content_generation, bool)
            or not isinstance(self.content_generation, int)
            or self.content_generation <= 0
        ):
            raise ValueError("content_generation must be a positive integer")


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _is_l2_unit_vector(vector: np.ndarray) -> bool:
    norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
    return bool(np.isfinite(norm) and np.isclose(norm, 1.0, rtol=1e-4, atol=1e-5))


def _validate_embedding_row_identity(
    row: Mapping[str, object] | sqlite3.Row,
    *,
    expected_track: EmbeddingTrackIdentity,
) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(row, (Mapping, sqlite3.Row)):
        return None, "embedding row is not a mapping"
    values = dict(row)
    required_fields = {
        "track_id",
        "track_uuid",
        "content_generation",
        "dim",
        "normalization",
        "embedding_blob",
    }
    if not required_fields.issubset(values):
        return None, "embedding row is missing required fields"
    row_track_id = _positive_int(values["track_id"])
    if row_track_id is None:
        return None, "invalid track_id"
    if row_track_id != expected_track.track_id:
        return None, "track_id mismatch"
    if not isinstance(values["track_uuid"], str):
        return None, "invalid track_uuid"
    if values["track_uuid"] != expected_track.track_uuid:
        return None, "track_uuid mismatch"
    row_generation = _positive_int(values["content_generation"])
    if row_generation is None:
        return None, "invalid content_generation"
    if row_generation != expected_track.content_generation:
        return None, "content_generation mismatch"
    return values, None


def validate_embedding_row_payload(
    *,
    family: str,
    row: Mapping[str, object] | sqlite3.Row,
    expected_track: EmbeddingTrackIdentity,
) -> tuple[bool, str | None]:
    """Validate one persisted embedding without opening another connection."""

    try:
        expected_spec = current_embedding_spec(family)
    except ValueError:
        return False, "unsupported embedding family"
    values, reason = _validate_embedding_row_identity(
        row,
        expected_track=expected_track,
    )
    if values is None:
        return False, reason
    dim = _positive_int(values["dim"])
    if dim is None:
        return False, "invalid dim"
    if dim != expected_spec.dimension:
        return False, "dim mismatch"
    if not isinstance(values["normalization"], str):
        return False, "invalid normalization"
    normalization = values["normalization"]
    if normalization != expected_spec.normalization:
        return False, "normalization mismatch"
    blob = values["embedding_blob"]
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        return False, "embedding_blob is not bytes"
    if len(blob) != dim * 4:
        return False, "blob length mismatch"
    vector = np.frombuffer(blob, dtype="<f4")
    if vector.shape != (dim,):
        return False, "embedding shape mismatch"
    if not bool(np.all(np.isfinite(vector))):
        return False, "non-finite values"
    if normalization == "l2" and not _is_l2_unit_vector(vector):
        return False, "l2 vector is not unit-normalized"
    return True, None


def current_track_identity(
    connection: sqlite3.Connection,
    track_id: int,
) -> EmbeddingTrackIdentity | None:
    """Load the current track identity from the same library connection."""

    catalog_uuid = validate_library_schema(connection)
    row = connection.execute(
        """
        SELECT track_id, track_uuid, content_generation
        FROM tracks
        WHERE track_id = ?
        """,
        (int(track_id),),
    ).fetchone()
    if row is None:
        return None
    return EmbeddingTrackIdentity(
        catalog_uuid=catalog_uuid,
        track_id=int(row[0]),
        track_uuid=str(row[1]),
        content_generation=int(row[2]),
    )


def _validate_current_track_identity(
    connection: sqlite3.Connection,
    expected: EmbeddingTrackIdentity,
) -> tuple[bool, str | None]:
    current = current_track_identity(connection, expected.track_id)
    if current is None:
        return False, "unknown track_id"
    if current.catalog_uuid != expected.catalog_uuid:
        return False, "catalog_uuid mismatch"
    if current.track_uuid != expected.track_uuid:
        return False, "track_uuid mismatch"
    if current.content_generation != expected.content_generation:
        return False, "content_generation mismatch"
    return True, None


def read_valid_embedding(
    *,
    family: str,
    track_id: int,
    connection: sqlite3.Connection,
) -> np.ndarray | None:
    table = _EMBEDDING_TABLES.get(family)
    if table is None:
        raise ValueError(f"unsupported embedding family: {family!r}")
    expected_track = current_track_identity(connection, int(track_id))
    if expected_track is None:
        return None
    row = connection.execute(
        f"""
        SELECT track_id, track_uuid, content_generation,
               dim, normalization, embedding_blob
        FROM {table}
        WHERE track_id = ?
        """,
        (int(track_id),),
    ).fetchone()
    if row is None:
        return None
    valid, _reason = validate_embedding_row_payload(
        family=family,
        row=row,
        expected_track=expected_track,
    )
    if not valid:
        return None
    return np.frombuffer(row["embedding_blob"], dtype="<f4").copy()


def write_valid_embedding_in_transaction(
    *,
    connection: sqlite3.Connection,
    track: EmbeddingTrackIdentity,
    family: str,
    embedding: Sequence[float] | np.ndarray,
    analyzed_at: str,
) -> None:
    """Validate and UPSERT one embedding in a caller-owned transaction."""

    if not connection.in_transaction:
        raise RuntimeError("embedding writes require an active library transaction")
    table = _EMBEDDING_TABLES.get(family)
    try:
        spec = current_embedding_spec(family)
    except ValueError:
        spec = None
    if table is None or spec is None:
        raise ValueError(f"unsupported embedding family: {family!r}")
    identity_valid, identity_reason = _validate_current_track_identity(
        connection,
        track,
    )
    if not identity_valid:
        raise RuntimeError(f"stale embedding write rejected: {identity_reason}")
    vector = np.asarray(embedding, dtype="<f4")
    if vector.ndim != 1 or vector.shape != (spec.dimension,):
        raise ValueError(
            f"embedding shape {vector.shape} does not match "
            f"{family} dimension {spec.dimension}"
        )
    if not bool(np.all(np.isfinite(vector))):
        raise ValueError("embedding contains non-finite values")
    if spec.normalization == "l2" and not _is_l2_unit_vector(vector):
        raise ValueError("l2 embedding must be unit-normalized")
    if not isinstance(analyzed_at, str) or not analyzed_at.strip():
        raise ValueError("analyzed_at must be a non-empty string")
    connection.execute(
        f"""
        INSERT INTO {table}(
            track_id, track_uuid, content_generation,
            dim, normalization, embedding_blob, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            track_uuid = excluded.track_uuid,
            content_generation = excluded.content_generation,
            dim = excluded.dim,
            normalization = excluded.normalization,
            embedding_blob = excluded.embedding_blob,
            analyzed_at = excluded.analyzed_at
        """,
        (
            track.track_id,
            track.track_uuid,
            track.content_generation,
            spec.dimension,
            spec.normalization,
            vector.tobytes(order="C"),
            analyzed_at,
        ),
    )


def write_valid_embedding(
    *,
    connection: sqlite3.Connection,
    track: EmbeddingTrackIdentity,
    family: str,
    embedding: Sequence[float] | np.ndarray,
    analyzed_at: str,
) -> None:
    """Validate and atomically publish one embedding in the library."""

    if connection.in_transaction:
        raise RuntimeError("canonical embedding writes require an idle connection")
    connection.execute("BEGIN IMMEDIATE")
    try:
        write_valid_embedding_in_transaction(
            connection=connection,
            track=track,
            family=family,
            embedding=embedding,
            analyzed_at=analyzed_at,
        )
        connection.commit()
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
