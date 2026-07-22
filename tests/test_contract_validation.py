"""Tests for runtime contract validation (Todo 10).

Each test constructs its own in-memory SQLite databases — no shared fixtures,
no conftest.py, no real library DB.

Run:
    python -m pytest tests/test_contract_validation.py --override-ini addopts= -q
"""

from __future__ import annotations

import sqlite3
import struct

import numpy as np
import pytest

from dj_track_similarity.db_artifacts import (
    create_artifacts_sidecar_schema,
    read_valid_embedding,
    validate_sidecar_row,
)
from dj_track_similarity.db_schema_v7 import create_v7_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAMILY = "mert"
_DIM = 768
_HASH_GOOD = "sha256:abc123"
_HASH_WRONG = "sha256:wronghash"
_TRACK_ID = 1
_TRACK_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_ANALYZED_AT = "2026-07-22T00:00:00.000000Z"


def _make_core_db(contract_hash: str = _HASH_GOOD) -> sqlite3.Connection:
    """Return an in-memory Core v7 DB with one contracts row."""
    conn = sqlite3.connect(":memory:")
    create_v7_schema(conn)
    conn.execute(
        """
        INSERT INTO contracts(
            contract_hash, analysis_family, output_kind,
            model_name, model_version, release_hash,
            canonical_payload_json, created_at
        ) VALUES (?, 'mert', 'embedding', 'MERT-v1-public-checkpoint', '1.0',
                  NULL, '{"analysis_family":"mert"}', '2026-07-22T00:00:00Z')
        """,
        (contract_hash,),
    )
    conn.commit()
    return conn


def _make_artifacts_db() -> sqlite3.Connection:
    """Return an in-memory artifacts sidecar DB."""
    conn = sqlite3.connect(":memory:")
    create_artifacts_sidecar_schema(conn, catalog_uuid="test-catalog")
    return conn


def _finite_blob(dim: int = _DIM) -> bytes:
    """Return a valid all-finite float32-le blob of *dim* floats."""
    values = [float(i % 100) / 100.0 for i in range(dim)]
    return struct.pack(f"<{dim}f", *values)


def _insert_mert_row(
    conn: sqlite3.Connection,
    contract_hash: str = _HASH_GOOD,
    dim: int = _DIM,
    normalization: str = "none",
    blob: bytes | None = None,
    track_id: int = _TRACK_ID,
) -> None:
    if blob is None:
        blob = _finite_blob(dim)
    conn.execute(
        """
        INSERT INTO mert_embeddings(
            track_id, track_uuid, content_generation,
            contract_hash, dim, normalization, embedding_blob, analyzed_at
        ) VALUES (?, ?, 1, ?, ?, ?, ?, ?)
        """,
        (track_id, _TRACK_UUID, contract_hash, dim, normalization, blob, _ANALYZED_AT),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Required tests
# ---------------------------------------------------------------------------


def test_correct_contract_accepted() -> None:
    """Happy path: valid row with matching contract hash returns a numpy array."""
    core_conn = _make_core_db(contract_hash=_HASH_GOOD)
    artifacts_conn = _make_artifacts_db()
    _insert_mert_row(artifacts_conn, contract_hash=_HASH_GOOD)

    result = read_valid_embedding(
        _FAMILY,
        _TRACK_ID,
        artifacts_conn,
        expected_contract_hash=_HASH_GOOD,
        core_contracts_conn=core_conn,
    )

    assert result is not None, "Expected a numpy array, got None"
    assert isinstance(result, np.ndarray)
    assert result.shape == (_DIM,)
    assert result.dtype == np.float32


def test_wrong_contract_hash_rejected() -> None:
    """Row with wrong contract_hash is silently ignored (returns None)."""
    core_conn = _make_core_db(contract_hash=_HASH_GOOD)
    artifacts_conn = _make_artifacts_db()
    # Insert row with the WRONG hash
    _insert_mert_row(artifacts_conn, contract_hash=_HASH_WRONG)

    # read_valid_embedding must return None
    result = read_valid_embedding(
        _FAMILY,
        _TRACK_ID,
        artifacts_conn,
        expected_contract_hash=_HASH_GOOD,
        core_contracts_conn=core_conn,
    )
    assert result is None, "Expected None for wrong contract hash"

    # validate_sidecar_row must report the exact reason
    row = {
        "contract_hash": _HASH_WRONG,
        "dim": _DIM,
        "normalization": "none",
        "embedding_blob": _finite_blob(),
    }
    is_valid, reason = validate_sidecar_row(
        _FAMILY, row, _HASH_GOOD, core_conn
    )
    assert is_valid is False
    assert reason == "contract_hash mismatch"


def test_unknown_contract_rejected() -> None:
    """Hash matches expected but is NOT registered in Core contracts → rejected."""
    # Core DB has NO contracts row at all
    core_conn = sqlite3.connect(":memory:")
    create_v7_schema(core_conn)

    artifacts_conn = _make_artifacts_db()
    _insert_mert_row(artifacts_conn, contract_hash=_HASH_GOOD)

    result = read_valid_embedding(
        _FAMILY,
        _TRACK_ID,
        artifacts_conn,
        expected_contract_hash=_HASH_GOOD,
        core_contracts_conn=core_conn,
    )
    assert result is None, "Expected None for unregistered contract"

    row = {
        "contract_hash": _HASH_GOOD,
        "dim": _DIM,
        "normalization": "none",
        "embedding_blob": _finite_blob(),
    }
    is_valid, reason = validate_sidecar_row(
        _FAMILY, row, _HASH_GOOD, core_conn
    )
    assert is_valid is False
    assert reason == "unknown contract in registry"


def test_non_finite_blob_rejected() -> None:
    """Blob containing NaN is rejected with 'non-finite values'."""
    core_conn = _make_core_db(contract_hash=_HASH_GOOD)
    artifacts_conn = _make_artifacts_db()

    # Build a blob with a NaN as the first value, bypassing SQLite CHECK
    # (we write raw bytes directly so the CHECK constraint is not triggered
    # by the Python-level insert — SQLite CHECK on BLOB length still passes
    # because len == dim*4).
    nan_blob = struct.pack(f"<{_DIM}f", float("nan"), *([0.0] * (_DIM - 1)))
    _insert_mert_row(artifacts_conn, contract_hash=_HASH_GOOD, blob=nan_blob)

    result = read_valid_embedding(
        _FAMILY,
        _TRACK_ID,
        artifacts_conn,
        expected_contract_hash=_HASH_GOOD,
        core_contracts_conn=core_conn,
    )
    assert result is None, "Expected None for blob with NaN"

    row = {
        "contract_hash": _HASH_GOOD,
        "dim": _DIM,
        "normalization": "none",
        "embedding_blob": nan_blob,
    }
    is_valid, reason = validate_sidecar_row(
        _FAMILY, row, _HASH_GOOD, core_conn
    )
    assert is_valid is False
    assert reason == "non-finite values"
