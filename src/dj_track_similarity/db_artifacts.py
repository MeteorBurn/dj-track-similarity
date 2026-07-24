"""Required v7 Artifacts schema and identity-aware storage gateway.

Tables (emission order):
  1.  storage_metadata              — singleton binding (catalog_uuid + schema_version)
  2.  maest_embeddings              — MAEST float32-le embedding BLOBs
  3.  mert_embeddings               — MERT float32-le embedding BLOBs
  4.  muq_embeddings                — MuQ float32-le embedding BLOBs
  5.  clap_embeddings               — CLAP float32-le embedding BLOBs
  6.  sonara_similarity_embeddings  — SONARA similarity embedding BLOBs
  7.  sonara_timeline               — SONARA Timeline payload (JSON)
  8.  sonara_fingerprints           — SONARA fingerprint packed uint32-le BLOBs

PRAGMA user_version = 1 is set at the end of create_artifacts_sidecar_schema().

Every public embedding read/write validates the Core/Artifacts catalog binding,
track UUID, content generation, canonical contract identity, shape,
normalization, and finite float32 payload.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Mapping, Sequence

import numpy as np

from .analysis_contracts import (
    FLOAT32_LE_ENCODING,
    ContractIdentity,
    ContractRegistryError,
    require_registered_contract,
)

ARTIFACTS_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# DDL strings — one per table/index block, in emission order
# ---------------------------------------------------------------------------

_DDL_STORAGE_METADATA = """
CREATE TABLE storage_metadata (
    singleton_id   INTEGER PRIMARY KEY CHECK(singleton_id = 1),
    catalog_uuid   TEXT    NOT NULL,
    schema_version INTEGER NOT NULL,
    created_at     TEXT    NOT NULL,
    updated_at     TEXT    NOT NULL
);
CREATE TRIGGER storage_metadata_immutable_insert
BEFORE INSERT ON storage_metadata
WHEN EXISTS (SELECT 1 FROM storage_metadata)
BEGIN
    SELECT RAISE(ABORT, 'storage_metadata is immutable')
    WHERE NOT EXISTS (
        SELECT 1
        FROM storage_metadata
        WHERE singleton_id IS NEW.singleton_id
          AND catalog_uuid IS NEW.catalog_uuid
          AND schema_version IS NEW.schema_version
          AND created_at IS NEW.created_at
          AND updated_at IS NEW.updated_at
    );
    SELECT RAISE(IGNORE);
END;
CREATE TRIGGER storage_metadata_immutable_update
BEFORE UPDATE ON storage_metadata
BEGIN
    SELECT RAISE(ABORT, 'storage_metadata is immutable');
END;
CREATE TRIGGER storage_metadata_immutable_delete
BEFORE DELETE ON storage_metadata
BEGIN
    SELECT RAISE(ABORT, 'storage_metadata is immutable');
END;
"""

# ---------------------------------------------------------------------------
# ML embedding tables — uniform shape, one per family
# ---------------------------------------------------------------------------

_DDL_MAEST_EMBEDDINGS = """
CREATE TABLE maest_embeddings (
    track_id           INTEGER PRIMARY KEY,
    track_uuid         TEXT    NOT NULL,
    content_generation INTEGER NOT NULL,
    contract_hash      TEXT    NOT NULL,
    dim                INTEGER NOT NULL CHECK(dim > 0),
    normalization      TEXT    NOT NULL CHECK(normalization IN ('none','l2')),
    embedding_blob     BLOB    NOT NULL CHECK(length(embedding_blob) = dim * 4),
    analyzed_at        TEXT    NOT NULL
);
CREATE INDEX idx_maest_embeddings_contract_generation ON maest_embeddings(contract_hash, content_generation, track_id);
CREATE INDEX idx_maest_embeddings_track_uuid ON maest_embeddings(track_uuid);
"""

_DDL_MERT_EMBEDDINGS = """
CREATE TABLE mert_embeddings (
    track_id           INTEGER PRIMARY KEY,
    track_uuid         TEXT    NOT NULL,
    content_generation INTEGER NOT NULL,
    contract_hash      TEXT    NOT NULL,
    dim                INTEGER NOT NULL CHECK(dim > 0),
    normalization      TEXT    NOT NULL CHECK(normalization IN ('none','l2')),
    embedding_blob     BLOB    NOT NULL CHECK(length(embedding_blob) = dim * 4),
    analyzed_at        TEXT    NOT NULL
);
CREATE INDEX idx_mert_embeddings_contract_generation ON mert_embeddings(contract_hash, content_generation, track_id);
CREATE INDEX idx_mert_embeddings_track_uuid ON mert_embeddings(track_uuid);
"""

_DDL_MUQ_EMBEDDINGS = """
CREATE TABLE muq_embeddings (
    track_id           INTEGER PRIMARY KEY,
    track_uuid         TEXT    NOT NULL,
    content_generation INTEGER NOT NULL,
    contract_hash      TEXT    NOT NULL,
    dim                INTEGER NOT NULL CHECK(dim > 0),
    normalization      TEXT    NOT NULL CHECK(normalization IN ('none','l2')),
    embedding_blob     BLOB    NOT NULL CHECK(length(embedding_blob) = dim * 4),
    analyzed_at        TEXT    NOT NULL
);
CREATE INDEX idx_muq_embeddings_contract_generation ON muq_embeddings(contract_hash, content_generation, track_id);
CREATE INDEX idx_muq_embeddings_track_uuid ON muq_embeddings(track_uuid);
"""

_DDL_CLAP_EMBEDDINGS = """
CREATE TABLE clap_embeddings (
    track_id           INTEGER PRIMARY KEY,
    track_uuid         TEXT    NOT NULL,
    content_generation INTEGER NOT NULL,
    contract_hash      TEXT    NOT NULL,
    dim                INTEGER NOT NULL CHECK(dim > 0),
    normalization      TEXT    NOT NULL CHECK(normalization IN ('none','l2')),
    embedding_blob     BLOB    NOT NULL CHECK(length(embedding_blob) = dim * 4),
    analyzed_at        TEXT    NOT NULL
);
CREATE INDEX idx_clap_embeddings_contract_generation ON clap_embeddings(contract_hash, content_generation, track_id);
CREATE INDEX idx_clap_embeddings_track_uuid ON clap_embeddings(track_uuid);
"""

# ---------------------------------------------------------------------------
# SONARA sidecar tables
# ---------------------------------------------------------------------------

_DDL_SONARA_SIMILARITY_EMBEDDINGS = """
CREATE TABLE sonara_similarity_embeddings (
    track_id           INTEGER PRIMARY KEY,
    track_uuid         TEXT    NOT NULL,
    content_generation INTEGER NOT NULL,
    contract_hash      TEXT    NOT NULL,
    dim                INTEGER NOT NULL CHECK(dim > 0),
    normalization      TEXT    NOT NULL CHECK(normalization IN ('none','l2')),
    embedding_blob     BLOB    NOT NULL CHECK(length(embedding_blob) = dim * 4),
    analyzed_at        TEXT    NOT NULL
);
CREATE INDEX idx_sonara_similarity_embeddings_contract_generation ON sonara_similarity_embeddings(contract_hash, content_generation, track_id);
CREATE INDEX idx_sonara_similarity_embeddings_track_uuid ON sonara_similarity_embeddings(track_uuid);
"""

_DDL_SONARA_TIMELINE = """
CREATE TABLE sonara_timeline (
    track_id           INTEGER PRIMARY KEY,
    track_uuid         TEXT    NOT NULL,
    content_generation INTEGER NOT NULL,
    contract_hash      TEXT    NOT NULL,
    payload_json       TEXT    NOT NULL CHECK(json_valid(payload_json) AND json_type(payload_json)='object'),
    analyzed_at        TEXT    NOT NULL
);
CREATE INDEX idx_sonara_timeline_contract_generation ON sonara_timeline(contract_hash, content_generation, track_id);
CREATE INDEX idx_sonara_timeline_track_uuid ON sonara_timeline(track_uuid);
"""

_DDL_SONARA_FINGERPRINTS = """
CREATE TABLE sonara_fingerprints (
    track_id            INTEGER PRIMARY KEY,
    track_uuid          TEXT    NOT NULL,
    content_generation  INTEGER NOT NULL,
    contract_hash       TEXT    NOT NULL,
    fingerprint_version TEXT    NOT NULL,
    word_count          INTEGER NOT NULL CHECK(word_count >= 0),
    byte_order          TEXT    NOT NULL CHECK(byte_order = 'little'),
    fingerprint_blob    BLOB    NOT NULL CHECK(length(fingerprint_blob) = word_count * 4),
    analyzed_at         TEXT    NOT NULL
);
CREATE INDEX idx_sonara_fingerprints_contract_generation ON sonara_fingerprints(contract_hash, content_generation, track_id);
CREATE INDEX idx_sonara_fingerprints_track_uuid ON sonara_fingerprints(track_uuid);
"""

# Ordered list of all DDL blocks to execute
_ALL_DDL: list[str] = [
    _DDL_STORAGE_METADATA,
    _DDL_MAEST_EMBEDDINGS,
    _DDL_MERT_EMBEDDINGS,
    _DDL_MUQ_EMBEDDINGS,
    _DDL_CLAP_EMBEDDINGS,
    _DDL_SONARA_SIMILARITY_EMBEDDINGS,
    _DDL_SONARA_TIMELINE,
    _DDL_SONARA_FINGERPRINTS,
]

# ---------------------------------------------------------------------------
# Schema creation function
# ---------------------------------------------------------------------------


def create_artifacts_sidecar_schema(
    db: "sqlite3.Connection | str",
    catalog_uuid: str,
) -> None:
    """Create the artifacts sidecar schema in *db*.

    Args:
        db: An open :class:`sqlite3.Connection` or a path string (including
            ``':memory:'``).  When a path string is given a new connection is
            opened, the schema is created, and the connection is closed.
        catalog_uuid: Non-empty Core catalog UUID. Unbound artifacts databases
            are invalid and are never created.
    """
    clean_catalog_uuid = _normalize_catalog_uuid(catalog_uuid)
    if isinstance(db, str):
        conn = sqlite3.connect(db)
        try:
            _apply_artifacts_schema(conn, catalog_uuid=clean_catalog_uuid)
        finally:
            conn.close()
    else:
        _apply_artifacts_schema(db, catalog_uuid=clean_catalog_uuid)


def _normalize_catalog_uuid(catalog_uuid: str) -> str:
    if not isinstance(catalog_uuid, str):
        raise ValueError("catalog_uuid must be a string")
    clean_catalog_uuid = catalog_uuid.strip()
    if not clean_catalog_uuid:
        raise ValueError("catalog_uuid must be a non-empty string")
    return clean_catalog_uuid


def _apply_artifacts_schema(
    conn: sqlite3.Connection,
    catalog_uuid: str,
) -> None:
    clean_catalog_uuid = _normalize_catalog_uuid(catalog_uuid)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")

    script = "\n".join(
        (
            "BEGIN IMMEDIATE;",
            *_ALL_DDL,
            f"PRAGMA user_version = {ARTIFACTS_SCHEMA_VERSION};",
        )
    )
    try:
        conn.executescript(script)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn.execute(
            """
            INSERT INTO storage_metadata(singleton_id, catalog_uuid, schema_version, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?)
            """,
            (clean_catalog_uuid, ARTIFACTS_SCHEMA_VERSION, now, now),
        )
        conn.commit()
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise


# ---------------------------------------------------------------------------
# Exact schema, binding, and embedding identity validation
# ---------------------------------------------------------------------------


_ARTIFACT_COLUMNS: dict[str, tuple[str, ...]] = {
    "storage_metadata": (
        "singleton_id",
        "catalog_uuid",
        "schema_version",
        "created_at",
        "updated_at",
    ),
    "maest_embeddings": (
        "track_id",
        "track_uuid",
        "content_generation",
        "contract_hash",
        "dim",
        "normalization",
        "embedding_blob",
        "analyzed_at",
    ),
    "mert_embeddings": (
        "track_id",
        "track_uuid",
        "content_generation",
        "contract_hash",
        "dim",
        "normalization",
        "embedding_blob",
        "analyzed_at",
    ),
    "muq_embeddings": (
        "track_id",
        "track_uuid",
        "content_generation",
        "contract_hash",
        "dim",
        "normalization",
        "embedding_blob",
        "analyzed_at",
    ),
    "clap_embeddings": (
        "track_id",
        "track_uuid",
        "content_generation",
        "contract_hash",
        "dim",
        "normalization",
        "embedding_blob",
        "analyzed_at",
    ),
    "sonara_similarity_embeddings": (
        "track_id",
        "track_uuid",
        "content_generation",
        "contract_hash",
        "dim",
        "normalization",
        "embedding_blob",
        "analyzed_at",
    ),
    "sonara_timeline": (
        "track_id",
        "track_uuid",
        "content_generation",
        "contract_hash",
        "payload_json",
        "analyzed_at",
    ),
    "sonara_fingerprints": (
        "track_id",
        "track_uuid",
        "content_generation",
        "contract_hash",
        "fingerprint_version",
        "word_count",
        "byte_order",
        "fingerprint_blob",
        "analyzed_at",
    ),
}
_ARTIFACT_INDEXES = {
    f"idx_{table}_{suffix}"
    for table in _ARTIFACT_COLUMNS
    if table != "storage_metadata"
    for suffix in ("contract_generation", "track_uuid")
}
_ARTIFACT_TRIGGERS = {
    "storage_metadata_immutable_insert",
    "storage_metadata_immutable_update",
    "storage_metadata_immutable_delete",
}
_EMBEDDING_TABLES = {
    "maest": "maest_embeddings",
    "mert": "mert_embeddings",
    "muq": "muq_embeddings",
    "clap": "clap_embeddings",
    "sonara": "sonara_similarity_embeddings",
}


def _normalized_schema_definitions(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, str, str], ...]:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE type IN ('table', 'index', 'trigger', 'view')
          AND name NOT LIKE 'sqlite_%'
          AND sql IS NOT NULL
        ORDER BY type, name
        """
    ).fetchall()
    return tuple(
        (
            str(object_type),
            str(name),
            str(table_name),
            " ".join(str(sql).split()),
        )
        for object_type, name, table_name, sql in rows
    )


def _schema_definition_fingerprint(
    definitions: tuple[tuple[str, str, str, str], ...],
) -> str:
    payload = json.dumps(
        definitions,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@lru_cache(maxsize=1)
def _expected_artifacts_schema_definitions() -> tuple[tuple[str, str, str, str], ...]:
    connection = sqlite3.connect(":memory:")
    try:
        create_artifacts_sidecar_schema(
            connection,
            catalog_uuid="expected-artifacts-catalog",
        )
        return _normalized_schema_definitions(connection)
    finally:
        connection.close()


@dataclass(frozen=True)
class ArtifactTrackIdentity:
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


_STORAGE_BINDING_PROOF_NONCE = object()


class StorageBindingProof:
    """One validated Core/Artifacts connection pair.

    Proofs are minted only by :func:`validate_storage_binding` and retain the
    exact connection objects that were validated.  A proof for another pair,
    even one with the same catalog UUID, is rejected.
    """

    __slots__ = (
        "_artifacts_connection",
        "_artifacts_marker",
        "_catalog_uuid",
        "_core_connection",
        "_core_marker",
        "_nonce",
    )

    def __init__(self) -> None:
        raise TypeError(
            "StorageBindingProof values are created by validate_storage_binding()"
        )

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("StorageBindingProof values are immutable")

    @property
    def catalog_uuid(self) -> str:
        return self._catalog_uuid


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _is_l2_unit_vector(vector: np.ndarray) -> bool:
    norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
    return bool(np.isfinite(norm) and np.isclose(norm, 1.0, rtol=1e-4, atol=1e-5))


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"invalid JSON constant: {value}")


_SONARA_TIMELINE_PAYLOAD_KEYS = frozenset(
    {
        "beats",
        "onset_frames",
        "chord_sequence",
        "chord_events",
        "tempo_curve",
        "downbeats",
        "energy_curve",
        "segments",
        "loudness_curve",
    }
)


def _finite_json_number(
    value: object,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    strict_minimum: bool = False,
) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    number = float(value)
    if not math.isfinite(number):
        return False
    if minimum is not None and (
        number <= minimum if strict_minimum else number < minimum
    ):
        return False
    return maximum is None or number <= maximum


def _valid_frame_sequence(value: object) -> bool:
    if not isinstance(value, list):
        return False
    previous = -1
    for frame in value:
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            return False
        if frame <= previous:
            return False
        previous = frame
    return True


def _valid_number_sequence(
    value: object,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    strict_minimum: bool = False,
    non_empty: bool = False,
) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not non_empty)
        and all(
            _finite_json_number(
                item,
                minimum=minimum,
                maximum=maximum,
                strict_minimum=strict_minimum,
            )
            for item in value
        )
    )


def validate_sonara_timeline_payload(
    payload: object,
) -> tuple[bool, str | None]:
    """Validate the exact canonical SONARA Timeline JSON payload."""

    if not isinstance(payload, Mapping):
        return False, "timeline payload is not a JSON object"
    if set(payload) != _SONARA_TIMELINE_PAYLOAD_KEYS:
        return False, "timeline payload fields do not match the canonical schema"

    beats = payload["beats"]
    onset_frames = payload["onset_frames"]
    downbeats = payload["downbeats"]
    if not _valid_frame_sequence(beats):
        return False, "timeline beats are invalid"
    if not _valid_frame_sequence(onset_frames):
        return False, "timeline onset_frames are invalid"
    if not _valid_frame_sequence(downbeats):
        return False, "timeline downbeats are invalid"
    if not set(downbeats).issubset(beats):
        return False, "timeline downbeats are not a subset of beats"

    tempo_curve = payload["tempo_curve"]
    if not _valid_number_sequence(
        tempo_curve,
        minimum=0.0,
        strict_minimum=True,
    ):
        return False, "timeline tempo_curve is invalid"
    if len(tempo_curve) != max(len(beats) - 1, 0):
        return False, "timeline tempo_curve length does not match beats"

    chord_sequence = payload["chord_sequence"]
    if not isinstance(chord_sequence, list) or any(
        not isinstance(label, str) or not label.strip() for label in chord_sequence
    ):
        return False, "timeline chord_sequence is invalid"

    chord_events = payload["chord_events"]
    if not isinstance(chord_events, list):
        return False, "timeline chord_events are invalid"
    previous_end = 0.0
    for event in chord_events:
        if not isinstance(event, dict) or set(event) != {
            "label",
            "start_sec",
            "end_sec",
        }:
            return False, "timeline chord event fields are invalid"
        if not isinstance(event["label"], str) or not event["label"].strip():
            return False, "timeline chord event label is invalid"
        if not _finite_json_number(event["start_sec"], minimum=0.0):
            return False, "timeline chord event start is invalid"
        if not _finite_json_number(event["end_sec"], minimum=0.0):
            return False, "timeline chord event end is invalid"
        start = float(event["start_sec"])
        end = float(event["end_sec"])
        if end < start or start < previous_end:
            return False, "timeline chord events overlap or run backward"
        previous_end = end

    if not _valid_number_sequence(
        payload["energy_curve"],
        minimum=0.0,
        maximum=1.0,
        non_empty=True,
    ):
        return False, "timeline energy_curve is invalid"

    segments = payload["segments"]
    if not isinstance(segments, list):
        return False, "timeline segments are invalid"
    previous_end = 0.0
    for segment in segments:
        if not isinstance(segment, dict) or set(segment) != {
            "start_sec",
            "end_sec",
            "energy",
        }:
            return False, "timeline segment fields are invalid"
        if not _finite_json_number(segment["start_sec"], minimum=0.0):
            return False, "timeline segment start is invalid"
        if not _finite_json_number(segment["end_sec"], minimum=0.0):
            return False, "timeline segment end is invalid"
        if not _finite_json_number(
            segment["energy"],
            minimum=0.0,
            maximum=1.0,
        ):
            return False, "timeline segment energy is invalid"
        start = float(segment["start_sec"])
        end = float(segment["end_sec"])
        if end <= start or start < previous_end:
            return False, "timeline segments overlap or run backward"
        previous_end = end

    if not _valid_number_sequence(payload["loudness_curve"]):
        return False, "timeline loudness_curve is invalid"
    return True, None


def _validate_artifact_row_identity(
    row: Mapping[str, object] | sqlite3.Row,
    *,
    expected_contract: ContractIdentity,
    expected_track: ArtifactTrackIdentity,
    required_fields: set[str],
) -> tuple[dict[str, object] | None, str | None]:
    if not isinstance(row, (Mapping, sqlite3.Row)):
        return None, "artifact row is not a mapping"
    values = dict(row)
    if not required_fields.issubset(values):
        return None, "artifact row is missing required fields"
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
    if not isinstance(values["contract_hash"], str):
        return None, "invalid contract_hash"
    if values["contract_hash"] != expected_contract.contract_hash:
        return None, "contract_hash mismatch"
    return values, None


def validate_embedding_row_payload(
    *,
    family: str,
    row: Mapping[str, object] | sqlite3.Row,
    expected_contract: ContractIdentity,
    expected_track: ArtifactTrackIdentity,
) -> tuple[bool, str | None]:
    """Validate one embedding row without performing connection lookups."""

    if family not in _EMBEDDING_TABLES:
        return False, "unsupported embedding family"
    if expected_contract.analysis_family != family:
        return False, "analysis_family mismatch"
    if expected_contract.output_kind != "embedding":
        return False, "output_kind mismatch"
    if expected_contract.encoding != FLOAT32_LE_ENCODING:
        return False, "encoding mismatch"
    values, reason = _validate_artifact_row_identity(
        row,
        expected_contract=expected_contract,
        expected_track=expected_track,
        required_fields={
            "track_id",
            "track_uuid",
            "content_generation",
            "contract_hash",
            "dim",
            "normalization",
            "embedding_blob",
        },
    )
    if values is None:
        return False, reason

    dim = _positive_int(values["dim"])
    if dim is None:
        return False, "invalid dim"
    if dim != expected_contract.dim:
        return False, "dim mismatch"
    if not isinstance(values["normalization"], str):
        return False, "invalid normalization"
    normalization = values["normalization"]
    if normalization != expected_contract.normalization:
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


def validate_timeline_row_payload(
    *,
    row: Mapping[str, object] | sqlite3.Row,
    expected_contract: ContractIdentity,
    expected_track: ArtifactTrackIdentity,
) -> tuple[bool, str | None]:
    """Validate one SONARA Timeline row without performing connection lookups."""

    if (
        expected_contract.analysis_family,
        expected_contract.output_kind,
    ) != ("sonara", "timeline"):
        return False, "contract is not SONARA Timeline"
    values, reason = _validate_artifact_row_identity(
        row,
        expected_contract=expected_contract,
        expected_track=expected_track,
        required_fields={
            "track_id",
            "track_uuid",
            "content_generation",
            "contract_hash",
            "payload_json",
        },
    )
    if values is None:
        return False, reason
    payload_json = values["payload_json"]
    if not isinstance(payload_json, str):
        return False, "payload_json is not text"
    try:
        payload = json.loads(
            payload_json,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError):
        return False, "payload_json is not finite valid JSON"
    return validate_sonara_timeline_payload(payload)


def validate_fingerprint_row_payload(
    *,
    row: Mapping[str, object] | sqlite3.Row,
    expected_contract: ContractIdentity,
    expected_track: ArtifactTrackIdentity,
) -> tuple[bool, str | None]:
    """Validate one SONARA fingerprint row without connection lookups."""

    if (
        expected_contract.analysis_family,
        expected_contract.output_kind,
    ) != ("sonara", "fingerprint"):
        return False, "contract is not a SONARA fingerprint"
    values, reason = _validate_artifact_row_identity(
        row,
        expected_contract=expected_contract,
        expected_track=expected_track,
        required_fields={
            "track_id",
            "track_uuid",
            "content_generation",
            "contract_hash",
            "fingerprint_version",
            "word_count",
            "byte_order",
            "fingerprint_blob",
        },
    )
    if values is None:
        return False, reason
    expected_version = expected_contract.parameters.get("fingerprint_version")
    if str(values["fingerprint_version"]) != str(expected_version):
        return False, "fingerprint_version mismatch"
    expected_byte_order = expected_contract.parameters.get("fingerprint_byte_order")
    if values["byte_order"] != expected_byte_order:
        return False, "fingerprint byte_order mismatch"
    word_count = values["word_count"]
    if (
        isinstance(word_count, bool)
        or not isinstance(word_count, int)
        or word_count <= 0
    ):
        return False, "fingerprint must contain at least one word"
    blob = values["fingerprint_blob"]
    if not isinstance(blob, (bytes, bytearray, memoryview)):
        return False, "fingerprint_blob is not bytes"
    if len(blob) != word_count * 4:
        return False, "fingerprint blob length mismatch"
    words = np.frombuffer(blob, dtype="<u4")
    if words.shape != (word_count,):
        return False, "fingerprint word count mismatch"
    return True, None


def validate_artifacts_sidecar_schema(
    connection: sqlite3.Connection,
    *,
    expected_catalog_uuid: str | None = None,
) -> str:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != ARTIFACTS_SCHEMA_VERSION:
        raise RuntimeError(
            f"SQLite Artifacts schema version {version} is not supported; "
            f"expected {ARTIFACTS_SCHEMA_VERSION}"
        )

    actual_views = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        )
    }
    if actual_views:
        raise RuntimeError(
            f"SQLite Artifacts contains unexpected views: {sorted(actual_views)}"
        )

    actual_tables = {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }
    expected_tables = set(_ARTIFACT_COLUMNS)
    if actual_tables != expected_tables:
        raise RuntimeError(
            "SQLite Artifacts table set mismatch; "
            f"missing={sorted(expected_tables - actual_tables)}, "
            f"extra={sorted(actual_tables - expected_tables)}"
        )
    for table, expected_columns in _ARTIFACT_COLUMNS.items():
        actual_columns = tuple(
            str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
        )
        if actual_columns != expected_columns:
            raise RuntimeError(
                f"SQLite Artifacts columns mismatch for {table}; "
                f"expected={list(expected_columns)}, actual={list(actual_columns)}"
            )

    actual_indexes = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if actual_indexes != _ARTIFACT_INDEXES:
        raise RuntimeError(
            "SQLite Artifacts index set mismatch; "
            f"missing={sorted(_ARTIFACT_INDEXES - actual_indexes)}, "
            f"extra={sorted(actual_indexes - _ARTIFACT_INDEXES)}"
        )
    actual_triggers = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )
    }
    if actual_triggers != _ARTIFACT_TRIGGERS:
        raise RuntimeError(
            "SQLite Artifacts trigger set mismatch; "
            f"missing={sorted(_ARTIFACT_TRIGGERS - actual_triggers)}, "
            f"extra={sorted(actual_triggers - _ARTIFACT_TRIGGERS)}"
        )

    actual_definitions = _normalized_schema_definitions(connection)
    expected_definitions = _expected_artifacts_schema_definitions()
    if actual_definitions != expected_definitions:
        raise RuntimeError(
            "SQLite Artifacts schema definition fingerprint mismatch; "
            f"expected={_schema_definition_fingerprint(expected_definitions)}, "
            f"actual={_schema_definition_fingerprint(actual_definitions)}"
        )

    rows = connection.execute(
        "SELECT singleton_id, catalog_uuid, schema_version FROM storage_metadata"
    ).fetchall()
    if len(rows) != 1 or int(rows[0][0]) != 1:
        raise RuntimeError("storage_metadata must contain exactly singleton_id=1")
    catalog_uuid = str(rows[0][1]).strip()
    if not catalog_uuid:
        raise RuntimeError("storage_metadata.catalog_uuid must be non-empty")
    if int(rows[0][2]) != ARTIFACTS_SCHEMA_VERSION:
        raise RuntimeError(
            "storage_metadata.schema_version does not match PRAGMA user_version"
        )
    if expected_catalog_uuid is not None and catalog_uuid != expected_catalog_uuid:
        raise RuntimeError("Artifacts database belongs to another library catalog")
    return catalog_uuid


def _connection_validation_marker(
    connection: sqlite3.Connection,
) -> tuple[object, ...] | None:
    try:
        return (
            connection._dj_validation_role,
            connection._dj_validated_catalog_uuid,
            connection._dj_validated_schema_cookie,
            connection._dj_validated_user_version,
            connection._dj_validated_storage_schema_version,
        )
    except AttributeError:
        return None


def _mint_storage_binding_proof(
    *,
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    catalog_uuid: str,
) -> StorageBindingProof:
    proof = object.__new__(StorageBindingProof)
    object.__setattr__(proof, "_nonce", _STORAGE_BINDING_PROOF_NONCE)
    object.__setattr__(proof, "_catalog_uuid", catalog_uuid)
    object.__setattr__(proof, "_core_connection", core_connection)
    object.__setattr__(proof, "_artifacts_connection", artifacts_connection)
    object.__setattr__(
        proof,
        "_core_marker",
        _connection_validation_marker(core_connection),
    )
    object.__setattr__(
        proof,
        "_artifacts_marker",
        _connection_validation_marker(artifacts_connection),
    )
    return proof


def _require_storage_binding_proof(
    proof: StorageBindingProof,
    *,
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
) -> StorageBindingProof:
    if (
        not isinstance(proof, StorageBindingProof)
        or proof._nonce is not _STORAGE_BINDING_PROOF_NONCE
    ):
        raise RuntimeError("invalid storage binding proof")
    if (
        proof._core_connection is not core_connection
        or proof._artifacts_connection is not artifacts_connection
    ):
        raise RuntimeError("storage binding proof belongs to another connection pair")
    if proof._core_marker != _connection_validation_marker(
        core_connection
    ) or proof._artifacts_marker != _connection_validation_marker(artifacts_connection):
        raise RuntimeError("storage binding proof is no longer current")
    return proof


def validate_storage_binding(
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
) -> StorageBindingProof:
    core_catalog_uuid = _validated_connection_catalog(
        core_connection,
        expected_role="core",
    )
    artifacts_catalog_uuid = _validated_connection_catalog(
        artifacts_connection,
        expected_role="artifacts",
    )
    if (
        core_catalog_uuid is not None
        and artifacts_catalog_uuid is not None
        and core_catalog_uuid == artifacts_catalog_uuid
    ):
        return _mint_storage_binding_proof(
            core_connection=core_connection,
            artifacts_connection=artifacts_connection,
            catalog_uuid=core_catalog_uuid,
        )

    from .db_schema import validate_core_schema

    catalog_uuid = validate_core_schema(core_connection)
    validate_artifacts_sidecar_schema(
        artifacts_connection,
        expected_catalog_uuid=catalog_uuid,
    )
    _store_connection_validation_marker(
        core_connection,
        role="core",
        catalog_uuid=catalog_uuid,
    )
    _store_connection_validation_marker(
        artifacts_connection,
        role="artifacts",
        catalog_uuid=catalog_uuid,
    )
    return _mint_storage_binding_proof(
        core_connection=core_connection,
        artifacts_connection=artifacts_connection,
        catalog_uuid=catalog_uuid,
    )


def _pragma_int(connection: sqlite3.Connection, pragma: str) -> int:
    row = connection.execute(f"PRAGMA {pragma}").fetchone()
    if row is None:
        raise RuntimeError(f"SQLite PRAGMA {pragma} returned no value")
    return int(row[0])


def _validated_connection_catalog(
    connection: sqlite3.Connection,
    *,
    expected_role: str,
) -> str | None:
    try:
        role = connection._dj_validation_role
        catalog_uuid = connection._dj_validated_catalog_uuid
        schema_cookie = connection._dj_validated_schema_cookie
        user_version = connection._dj_validated_user_version
        storage_schema_version = connection._dj_validated_storage_schema_version
    except AttributeError:
        return None
    if role != expected_role or not isinstance(catalog_uuid, str):
        return None
    catalog_uuid = catalog_uuid.strip()
    if not catalog_uuid:
        return None
    expected_user_version = (
        ARTIFACTS_SCHEMA_VERSION
        if expected_role == "artifacts"
        else _core_schema_version()
    )
    if (
        user_version != expected_user_version
        or _pragma_int(connection, "user_version") != user_version
        or _pragma_int(connection, "schema_version") != schema_cookie
    ):
        return None
    if (
        expected_role == "artifacts"
        and storage_schema_version != ARTIFACTS_SCHEMA_VERSION
    ):
        return None
    return catalog_uuid


def _core_schema_version() -> int:
    from .db_schema import CURRENT_SCHEMA_VERSION

    return CURRENT_SCHEMA_VERSION


def _store_connection_validation_marker(
    connection: sqlite3.Connection,
    *,
    role: str,
    catalog_uuid: str,
) -> None:
    storage_schema_version: int | None = None
    if role == "artifacts":
        row = connection.execute(
            "SELECT schema_version FROM storage_metadata WHERE singleton_id = 1"
        ).fetchone()
        if row is None:
            raise RuntimeError("storage_metadata must contain singleton_id=1")
        storage_schema_version = int(row[0])
    try:
        connection._dj_validation_role = role
        connection._dj_validated_catalog_uuid = catalog_uuid
        connection._dj_validated_schema_cookie = _pragma_int(
            connection,
            "schema_version",
        )
        connection._dj_validated_user_version = _pragma_int(
            connection,
            "user_version",
        )
        connection._dj_validated_storage_schema_version = storage_schema_version
    except AttributeError:
        pass


def current_track_identity(
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    track_id: int,
    *,
    storage_binding: StorageBindingProof | None = None,
) -> ArtifactTrackIdentity | None:
    binding = (
        validate_storage_binding(core_connection, artifacts_connection)
        if storage_binding is None
        else _require_storage_binding_proof(
            storage_binding,
            core_connection=core_connection,
            artifacts_connection=artifacts_connection,
        )
    )
    row = core_connection.execute(
        """
        SELECT track_id, track_uuid, content_generation
        FROM tracks
        WHERE track_id = ?
        """,
        (int(track_id),),
    ).fetchone()
    if row is None:
        return None
    return ArtifactTrackIdentity(
        catalog_uuid=binding.catalog_uuid,
        track_id=int(row[0]),
        track_uuid=str(row[1]),
        content_generation=int(row[2]),
    )


def _validate_current_track_identity(
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    expected: ArtifactTrackIdentity,
    *,
    storage_binding: StorageBindingProof | None = None,
) -> tuple[bool, str | None]:
    try:
        current = current_track_identity(
            core_connection,
            artifacts_connection,
            expected.track_id,
            storage_binding=storage_binding,
        )
    except RuntimeError as error:
        return False, str(error)
    if current is None:
        return False, "unknown track_id"
    if current.catalog_uuid != expected.catalog_uuid:
        return False, "catalog_uuid mismatch"
    if current.track_uuid != expected.track_uuid:
        return False, "track_uuid mismatch"
    if current.content_generation != expected.content_generation:
        return False, "content_generation mismatch"
    return True, None


def validate_sidecar_row(
    *,
    family: str,
    row: Mapping[str, object] | sqlite3.Row,
    expected_contract: ContractIdentity,
    expected_track: ArtifactTrackIdentity,
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    storage_binding: StorageBindingProof | None = None,
) -> tuple[bool, str | None]:
    if family not in _EMBEDDING_TABLES:
        return False, "unsupported embedding family"
    if expected_contract.analysis_family != family:
        return False, "analysis_family mismatch"
    if expected_contract.output_kind != "embedding":
        return False, "output_kind mismatch"
    if expected_contract.encoding != FLOAT32_LE_ENCODING:
        return False, "encoding mismatch"

    identity_valid, identity_reason = _validate_current_track_identity(
        core_connection,
        artifacts_connection,
        expected_track,
        storage_binding=storage_binding,
    )
    if not identity_valid:
        return False, identity_reason

    try:
        require_registered_contract(core_connection, expected_contract)
    except ContractRegistryError as error:
        return False, str(error)
    return validate_embedding_row_payload(
        family=family,
        row=row,
        expected_contract=expected_contract,
        expected_track=expected_track,
    )


def read_valid_embedding(
    *,
    family: str,
    track_id: int,
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    expected_contract: ContractIdentity,
    storage_binding: StorageBindingProof | None = None,
) -> np.ndarray | None:
    table = _EMBEDDING_TABLES.get(family)
    if table is None:
        raise ValueError(f"unsupported embedding family: {family!r}")
    binding = (
        validate_storage_binding(core_connection, artifacts_connection)
        if storage_binding is None
        else _require_storage_binding_proof(
            storage_binding,
            core_connection=core_connection,
            artifacts_connection=artifacts_connection,
        )
    )
    expected_track = current_track_identity(
        core_connection,
        artifacts_connection,
        int(track_id),
        storage_binding=binding,
    )
    if expected_track is None:
        return None
    row = artifacts_connection.execute(
        f"""
        SELECT track_id, track_uuid, content_generation, contract_hash,
               dim, normalization, embedding_blob
        FROM {table}
        WHERE track_id = ?
        """,
        (int(track_id),),
    ).fetchone()
    if row is None:
        return None
    row_mapping = {
        "track_id": row[0],
        "track_uuid": row[1],
        "content_generation": row[2],
        "contract_hash": row[3],
        "dim": row[4],
        "normalization": row[5],
        "embedding_blob": row[6],
    }
    valid, _reason = validate_sidecar_row(
        family=family,
        row=row_mapping,
        expected_contract=expected_contract,
        expected_track=expected_track,
        core_connection=core_connection,
        artifacts_connection=artifacts_connection,
        storage_binding=binding,
    )
    if not valid:
        return None
    return np.frombuffer(row[6], dtype="<f4").copy()


def write_valid_embedding_in_transaction(
    *,
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    track: ArtifactTrackIdentity,
    contract: ContractIdentity,
    embedding: Sequence[float] | np.ndarray,
    analyzed_at: str,
    storage_binding: StorageBindingProof | None = None,
) -> None:
    """Validate and UPSERT one embedding inside caller-owned transactions.

    The caller must already hold both transactions in strict Core-to-Artifacts
    lock order.  This helper performs no begin, commit, or rollback operation.
    """

    if not core_connection.in_transaction:
        raise RuntimeError(
            "in-transaction artifact writes require an active Core transaction"
        )
    if not artifacts_connection.in_transaction:
        raise RuntimeError(
            "in-transaction artifact writes require an active Artifacts transaction"
        )

    table = _EMBEDDING_TABLES.get(contract.analysis_family)
    if table is None:
        raise ValueError(f"unsupported embedding family: {contract.analysis_family!r}")
    if contract.output_kind != "embedding":
        raise ValueError("artifact embedding writes require output_kind='embedding'")

    binding = (
        validate_storage_binding(core_connection, artifacts_connection)
        if storage_binding is None
        else _require_storage_binding_proof(
            storage_binding,
            core_connection=core_connection,
            artifacts_connection=artifacts_connection,
        )
    )
    identity_valid, identity_reason = _validate_current_track_identity(
        core_connection,
        artifacts_connection,
        track,
        storage_binding=binding,
    )
    if not identity_valid:
        raise RuntimeError(f"stale artifact write rejected: {identity_reason}")
    require_registered_contract(core_connection, contract)

    vector = np.asarray(embedding, dtype="<f4")
    if vector.ndim != 1 or vector.shape != (contract.dim,):
        raise ValueError(
            f"embedding shape {vector.shape} does not match contract dim {contract.dim}"
        )
    if not bool(np.all(np.isfinite(vector))):
        raise ValueError("embedding contains non-finite values")
    if contract.normalization == "l2" and not _is_l2_unit_vector(vector):
        raise ValueError("l2 embedding must be unit-normalized")
    if not isinstance(analyzed_at, str) or not analyzed_at.strip():
        raise ValueError("analyzed_at must be a non-empty string")
    blob = vector.tobytes(order="C")

    artifacts_connection.execute(
        f"""
        INSERT INTO {table} (
            track_id, track_uuid, content_generation, contract_hash,
            dim, normalization, embedding_blob, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            track_uuid = excluded.track_uuid,
            content_generation = excluded.content_generation,
            contract_hash = excluded.contract_hash,
            dim = excluded.dim,
            normalization = excluded.normalization,
            embedding_blob = excluded.embedding_blob,
            analyzed_at = excluded.analyzed_at
        """,
        (
            track.track_id,
            track.track_uuid,
            track.content_generation,
            contract.contract_hash,
            contract.dim,
            contract.normalization,
            blob,
            str(analyzed_at),
        ),
    )


def write_valid_embedding(
    *,
    core_connection: sqlite3.Connection,
    artifacts_connection: sqlite3.Connection,
    track: ArtifactTrackIdentity,
    contract: ContractIdentity,
    embedding: Sequence[float] | np.ndarray,
    analyzed_at: str,
) -> None:
    """Validate and atomically publish one embedding against current Core identity.

    Both connections must be idle.  The function acquires a Core
    ``BEGIN IMMEDIATE`` transaction before validating track generation or
    contract identity, then acquires the Artifacts write transaction.  The
    Core transaction remains held until the Artifacts commit finishes.  This
    Core-to-Artifacts lock order prevents a stale writer from validating an old
    generation, waiting behind a newer artifact write, and subsequently
    overwriting the current row.
    """

    if core_connection.in_transaction:
        raise RuntimeError("canonical artifact writes require an idle Core connection")
    if artifacts_connection.in_transaction:
        raise RuntimeError(
            "canonical artifact writes require an idle Artifacts connection"
        )

    table = _EMBEDDING_TABLES.get(contract.analysis_family)
    if table is None:
        raise ValueError(f"unsupported embedding family: {contract.analysis_family!r}")
    if contract.output_kind != "embedding":
        raise ValueError("artifact embedding writes require output_kind='embedding'")

    core_transaction_started = False
    artifacts_transaction_started = False
    try:
        core_connection.execute("BEGIN IMMEDIATE")
        core_transaction_started = True
        artifacts_connection.execute("BEGIN IMMEDIATE")
        artifacts_transaction_started = True
        storage_binding = validate_storage_binding(
            core_connection,
            artifacts_connection,
        )
        write_valid_embedding_in_transaction(
            core_connection=core_connection,
            artifacts_connection=artifacts_connection,
            track=track,
            contract=contract,
            embedding=embedding,
            analyzed_at=analyzed_at,
            storage_binding=storage_binding,
        )
        artifacts_connection.commit()
        artifacts_transaction_started = False
        core_connection.commit()
        core_transaction_started = False
    except BaseException:
        if artifacts_transaction_started and artifacts_connection.in_transaction:
            try:
                artifacts_connection.rollback()
            except sqlite3.Error:
                pass
        if core_transaction_started and core_connection.in_transaction:
            try:
                core_connection.rollback()
            except sqlite3.Error:
                pass
        raise
