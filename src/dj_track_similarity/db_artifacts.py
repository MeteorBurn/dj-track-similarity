"""Artifacts sidecar schema DDL — ``library.artifacts.sqlite``.

This module is standalone — it does NOT import from any other dj_track_similarity
module so it can be used as a migration target without circular dependencies.

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

Contract validation (contract_hash lookup, cross-DB FK checks) is NOT done here —
that is the responsibility of the application layer (Todo 10).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

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
    catalog_uuid: Optional[str] = None,
) -> None:
    """Create the artifacts sidecar schema in *db*.

    Args:
        db: An open :class:`sqlite3.Connection` or a path string (including
            ``':memory:'``).  When a path string is given a new connection is
            opened, the schema is created, and the connection is closed.
        catalog_uuid: When provided, inserts the ``storage_metadata`` singleton
            row binding this sidecar to the named catalog.  When ``None`` the
            row is left empty; the writer that first attaches the sidecar is
            responsible for inserting it.
    """
    if isinstance(db, str):
        conn = sqlite3.connect(db)
        try:
            _apply_artifacts_schema(conn, catalog_uuid=catalog_uuid)
        finally:
            conn.close()
    else:
        _apply_artifacts_schema(db, catalog_uuid=catalog_uuid)


def _apply_artifacts_schema(
    conn: sqlite3.Connection,
    catalog_uuid: Optional[str],
) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")

    for ddl_block in _ALL_DDL:
        for statement in _split_statements(ddl_block):
            conn.execute(statement)

    conn.execute(f"PRAGMA user_version = {ARTIFACTS_SCHEMA_VERSION}")

    if catalog_uuid is not None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        conn.execute(
            """
            INSERT INTO storage_metadata(singleton_id, catalog_uuid, schema_version, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?)
            """,
            (catalog_uuid, ARTIFACTS_SCHEMA_VERSION, now, now),
        )

    conn.commit()


def _split_statements(ddl: str) -> list[str]:
    """Split a DDL block into individual statements, stripping SQL comments."""
    lines = []
    for line in ddl.splitlines():
        stripped = line.split("--")[0]
        lines.append(stripped)
    cleaned = "\n".join(lines)
    statements = [s.strip() for s in cleaned.split(";")]
    return [s for s in statements if s]


# ---------------------------------------------------------------------------
# Runtime contract validation (Todo 10)
# ---------------------------------------------------------------------------

import hashlib
import json

import numpy as np


def compute_expected_contract_hash(
    family: str,
    model_name: str,
    model_version: Optional[str],
    dim: int,
    encoding: str,
    normalization: str,
    checkpoint_id: Optional[str] = None,
    preprocessing: Optional[str] = None,
    release_hash: Optional[str] = None,
) -> str:
    """Compute the expected contract hash from the currently running adapter's identity.

    For non-SONARA families (MAEST/MERT/MuQ/CLAP) ``release_hash`` must be
    ``None``.  For SONARA ``release_hash`` is required.

    The canonical payload is serialised with ``json.dumps(sort_keys=True,
    separators=(',', ':'), ensure_ascii=False, allow_nan=False)`` and hashed
    with SHA-256.

    Returns:
        A string of the form ``"sha256:<hexdigest>"``.
    """
    # All embedding-type families use output_kind='embedding'
    output_kind = "embedding"

    payload = {
        "analysis_family": family,
        "output_kind": output_kind,
        "model_name": model_name,
        "model_version": model_version,
        "dim": dim,
        "encoding": encoding,
        "normalization": normalization,
        "checkpoint_id": checkpoint_id,
        "preprocessing": preprocessing,
        "release_hash": release_hash,
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def validate_sidecar_row(
    family: str,
    row: "dict | sqlite3.Row",
    expected_contract_hash: str,
    core_contracts_conn: sqlite3.Connection,
) -> "tuple[bool, str | None]":
    """Validate a row read from a sidecar embedding table.

    Args:
        family: Analysis family string (e.g. ``'mert'``).  Not used for
            field lookup but kept for future extensibility.
        row: A dict or :class:`sqlite3.Row` with keys ``contract_hash``,
            ``dim``, ``normalization``, and ``embedding_blob``.
        expected_contract_hash: The hash computed from the currently running
            adapter (see :func:`compute_expected_contract_hash`).
        core_contracts_conn: An open connection to the Core database whose
            ``contracts`` table is used to verify the hash is registered.

    Returns:
        ``(True, None)`` when the row is valid, or ``(False, reason)`` where
        *reason* is a short human-readable string describing the first
        validation failure.
    """
    # Accept both dict and sqlite3.Row
    if isinstance(row, sqlite3.Row):
        row = dict(row)

    row_hash: str = row["contract_hash"]
    dim: int = row["dim"]
    normalization: str = row["normalization"]
    blob: bytes = row["embedding_blob"]

    # 1. Contract hash must match expected
    if row_hash != expected_contract_hash:
        return False, "contract_hash mismatch"

    # 2. Contract hash must exist in Core contracts registry
    cur = core_contracts_conn.execute(
        "SELECT 1 FROM contracts WHERE contract_hash = ? LIMIT 1",
        (row_hash,),
    )
    if cur.fetchone() is None:
        return False, "unknown contract in registry"

    # 3. dim must be positive
    if dim <= 0:
        return False, "invalid dim"

    # 4. Blob length must equal dim * 4 (float32 = 4 bytes)
    if len(blob) != dim * 4:
        return False, "blob length mismatch"

    # 5. normalization must be one of the allowed values
    if normalization not in ("none", "l2"):
        return False, "invalid normalization"

    # 6. All values must be finite (no NaN or inf)
    vec = np.frombuffer(blob, dtype="<f4")
    if not np.all(np.isfinite(vec)):
        return False, "non-finite values"

    return True, None


def read_valid_embedding(
    family: str,
    track_id: int,
    artifacts_conn: sqlite3.Connection,
    expected_contract_hash: str,
    core_contracts_conn: sqlite3.Connection,
) -> "np.ndarray | None":
    """Read and validate an embedding for *track_id* from the sidecar.

    Reads the row for *track_id* from ``<family>_embeddings``, validates it
    with :func:`validate_sidecar_row`, and returns the decoded
    :class:`numpy.ndarray` of shape ``(dim,)`` on success.

    Returns ``None`` when the row is missing or invalid.  Invalid rows are
    silently ignored — they will be reconciled on the next successful write
    for that track.
    """
    table = f"{family}_embeddings"
    cur = artifacts_conn.execute(
        f"SELECT contract_hash, dim, normalization, embedding_blob FROM {table} WHERE track_id = ?",  # noqa: S608
        (track_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None

    row_dict = {
        "contract_hash": row[0],
        "dim": row[1],
        "normalization": row[2],
        "embedding_blob": row[3],
    }

    is_valid, _reason = validate_sidecar_row(
        family, row_dict, expected_contract_hash, core_contracts_conn
    )
    if not is_valid:
        return None

    return np.frombuffer(row_dict["embedding_blob"], dtype="<f4").copy()
