"""Tests for v7 ML embedding storage: MERT / MuQ / CLAP per-family sidecar tables.

Conventions:
- No conftest.py; each test builds its own in-memory SQLite DBs.
- No real ML models — all embeddings are synthetic.
- Run with: python -m pytest tests/test_ml_storage_v7.py --override-ini addopts= -q
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

import numpy as np
import pytest

from dj_track_similarity.db_analysis import (
    save_clap_embedding_v7,
    save_mert_embedding_v7,
    save_muq_embedding_v7,
    upsert_ml_embedding_contract_v7,
)
from dj_track_similarity.db_artifacts import (
    create_artifacts_sidecar_schema,
    read_valid_embedding,
)
from dj_track_similarity.db_schema_v7 import create_v7_schema


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_core_db() -> sqlite3.Connection:
    """Return an in-memory v7 Core schema connection with FK enforcement."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_v7_schema(conn)
    return conn


def _make_artifacts_db() -> sqlite3.Connection:
    """Return an in-memory artifacts sidecar schema connection."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_artifacts_sidecar_schema(conn, catalog_uuid=str(uuid.uuid4()))
    return conn


def _insert_track(
    conn: sqlite3.Connection,
    track_id: int = 1,
    content_generation: int = 1,
) -> str:
    """Insert a minimal track row; returns the track_uuid."""
    track_uuid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO tracks (
            track_id, track_uuid, file_path, file_size_bytes, file_modified_ns,
            content_generation, last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            track_uuid,
            f"/music/track_{track_id}.flac",
            1_234_567,
            1_700_000_000_000_000_000,
            content_generation,
            now,
            now,
            now,
        ),
    )
    conn.commit()
    return track_uuid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_per_family_sidecar_tables() -> None:
    """Each ML family writes to its own sidecar table; contracts registered in Core."""
    core = _make_core_db()
    artifacts = _make_artifacts_db()

    track_uuid = _insert_track(core, track_id=1, content_generation=1)
    analyzed_at = datetime.now(timezone.utc).isoformat()

    # Upsert 3 contracts — one per family
    mert_contract = upsert_ml_embedding_contract_v7(
        core,
        family="mert",
        model_name="m-a-p/MERT-v1-95M",
        model_version="1.0",
        dim=768,
        normalization="l2",
    )
    muq_contract = upsert_ml_embedding_contract_v7(
        core,
        family="muq",
        model_name="OpenMuQ/MuQ-large-msd-iter",
        model_version="1.0",
        dim=1024,
        normalization="l2",
    )
    clap_contract = upsert_ml_embedding_contract_v7(
        core,
        family="clap",
        model_name="lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt",
        model_version="1.0",
        dim=512,
        normalization="none",
    )

    # All hashes must be distinct sha256 strings
    assert mert_contract.startswith("sha256:")
    assert muq_contract.startswith("sha256:")
    assert clap_contract.startswith("sha256:")
    assert len({mert_contract, muq_contract, clap_contract}) == 3

    # Build synthetic embeddings matching each contract's dim
    rng = np.random.default_rng(0)
    mert_emb = rng.random(768, dtype=np.float32)
    muq_emb = rng.random(1024, dtype=np.float32)
    clap_emb = rng.random(512, dtype=np.float32)

    # Write each embedding to the sidecar
    save_mert_embedding_v7(
        artifacts,
        track_id=1,
        track_uuid=track_uuid,
        content_generation=1,
        contract_hash=mert_contract,
        embedding=mert_emb,
        normalization="l2",
        analyzed_at=analyzed_at,
    )
    save_muq_embedding_v7(
        artifacts,
        track_id=1,
        track_uuid=track_uuid,
        content_generation=1,
        contract_hash=muq_contract,
        embedding=muq_emb,
        normalization="l2",
        analyzed_at=analyzed_at,
    )
    save_clap_embedding_v7(
        artifacts,
        track_id=1,
        track_uuid=track_uuid,
        content_generation=1,
        contract_hash=clap_contract,
        embedding=clap_emb,
        normalization="none",
        analyzed_at=analyzed_at,
    )

    # --- Row count assertions ---
    assert artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 1
    assert artifacts.execute("SELECT COUNT(*) FROM muq_embeddings").fetchone()[0] == 1
    assert artifacts.execute("SELECT COUNT(*) FROM clap_embeddings").fetchone()[0] == 1

    # --- Dim assertions ---
    assert artifacts.execute("SELECT dim FROM mert_embeddings WHERE track_id = 1").fetchone()[0] == 768
    assert artifacts.execute("SELECT dim FROM muq_embeddings WHERE track_id = 1").fetchone()[0] == 1024
    assert artifacts.execute("SELECT dim FROM clap_embeddings WHERE track_id = 1").fetchone()[0] == 512

    # --- Decoded embedding round-trip ---
    def _decode(table: str) -> np.ndarray:
        row = artifacts.execute(
            f"SELECT embedding_blob, dim FROM {table} WHERE track_id = 1"  # noqa: S608
        ).fetchone()
        assert row is not None
        return np.frombuffer(row["embedding_blob"], dtype="<f4")

    np.testing.assert_array_equal(_decode("mert_embeddings"), mert_emb.astype("<f4"))
    np.testing.assert_array_equal(_decode("muq_embeddings"), muq_emb.astype("<f4"))
    np.testing.assert_array_equal(_decode("clap_embeddings"), clap_emb.astype("<f4"))

    # --- Core contracts: 3 rows for mert/muq/clap ---
    ml_contract_count = core.execute(
        "SELECT COUNT(*) FROM contracts WHERE analysis_family IN ('mert', 'muq', 'clap')"
    ).fetchone()[0]
    assert ml_contract_count == 3, (
        f"Expected 3 ML contracts (mert + muq + clap), got {ml_contract_count}"
    )

    core.close()
    artifacts.close()


def test_wrong_contract_ignored() -> None:
    """A sidecar row whose contract_hash is not in Core contracts is silently ignored by read_valid_embedding."""
    core = _make_core_db()
    artifacts = _make_artifacts_db()

    track_uuid = _insert_track(core, track_id=1, content_generation=1)
    analyzed_at = datetime.now(timezone.utc).isoformat()

    # Register a real contract in Core
    real_contract = upsert_ml_embedding_contract_v7(
        core,
        family="mert",
        model_name="m-a-p/MERT-v1-95M",
        model_version="1.0",
        dim=768,
        normalization="l2",
    )

    # Write a row with an ORPHAN contract_hash (not in Core contracts)
    orphan_hash = "sha256:" + "a" * 64
    rng = np.random.default_rng(1)
    emb = rng.random(768, dtype=np.float32)
    save_mert_embedding_v7(
        artifacts,
        track_id=1,
        track_uuid=track_uuid,
        content_generation=1,
        contract_hash=orphan_hash,
        embedding=emb,
        normalization="l2",
        analyzed_at=analyzed_at,
    )

    # read_valid_embedding must return None (orphan row silently ignored)
    result = read_valid_embedding(
        family="mert",
        track_id=1,
        artifacts_conn=artifacts,
        expected_contract_hash=real_contract,
        core_contracts_conn=core,
    )
    assert result is None, f"Expected None for orphan contract, got {result}"

    # The orphan row must still be present in the sidecar (not deleted)
    row_count = artifacts.execute(
        "SELECT COUNT(*) FROM mert_embeddings WHERE track_id = 1"
    ).fetchone()[0]
    assert row_count == 1, (
        f"Orphan row must remain in sidecar (not deleted), got count={row_count}"
    )

    core.close()
    artifacts.close()


def test_invalid_normalization_rejected() -> None:
    """save_*_embedding_v7 raises ValueError for an invalid normalization value."""
    artifacts = _make_artifacts_db()
    rng = np.random.default_rng(2)
    emb = rng.random(768, dtype=np.float32)

    with pytest.raises(ValueError, match="normalization"):
        save_mert_embedding_v7(
            artifacts,
            track_id=1,
            track_uuid=str(uuid.uuid4()),
            content_generation=1,
            contract_hash="sha256:" + "b" * 64,
            embedding=emb,
            normalization="wrong",
            analyzed_at=datetime.now(timezone.utc).isoformat(),
        )

    artifacts.close()


def test_invalid_family_rejected() -> None:
    """upsert_ml_embedding_contract_v7 raises ValueError for an invalid family."""
    core = _make_core_db()

    with pytest.raises(ValueError, match="family"):
        upsert_ml_embedding_contract_v7(
            core,
            family="sonara",
            model_name="some-model",
            model_version="1.0",
            dim=256,
            normalization="none",
        )

    core.close()
