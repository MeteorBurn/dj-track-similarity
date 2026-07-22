"""Tests for v7 MAEST storage: scores in Core, embeddings in artifacts sidecar.

Conventions:
- No conftest.py; each test builds its own in-memory SQLite DBs.
- No real MAEST model — all outputs are synthetic.
- Run with: python -m pytest tests/test_maest_storage_v7.py --override-ini addopts= -q
"""
from __future__ import annotations

import inspect
import sqlite3
import uuid
from datetime import datetime, timezone

import numpy as np
import pytest

from dj_track_similarity.db_analysis import (
    save_maest_embedding_v7,
    save_maest_scores_v7,
    upsert_maest_contract_v7,
)
from dj_track_similarity.db_artifacts import create_artifacts_sidecar_schema
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

def test_scores_in_core_embeddings_in_sidecar() -> None:
    """MAEST scores land in Core maest_scores; embeddings land in artifacts maest_embeddings."""
    core = _make_core_db()
    artifacts = _make_artifacts_db()

    track_uuid = _insert_track(core, track_id=1, content_generation=1)
    analyzed_at = datetime.now(timezone.utc).isoformat()

    # Upsert two contracts: one for scores (analysis), one for embedding
    scores_contract = upsert_maest_contract_v7(
        core,
        model_name="maest-discogs-400d",
        model_version="1.0",
        dim=None,
        output_kind="analysis",
    )
    embedding_contract = upsert_maest_contract_v7(
        core,
        model_name="maest-discogs-400d",
        model_version="1.0",
        dim=768,
        output_kind="embedding",
    )

    # Both contracts must be distinct sha256 hashes
    assert scores_contract.startswith("sha256:")
    assert embedding_contract.startswith("sha256:")
    assert scores_contract != embedding_contract

    # Write scores to Core
    genres_json = '[{"rank":1,"genre_name":"techno","score":0.85}]'
    save_maest_scores_v7(
        core,
        track_id=1,
        content_generation=1,
        contract_hash=scores_contract,
        syncopated_rhythm=1,
        genres_json=genres_json,
        analyzed_at=analyzed_at,
    )

    # Write embedding to artifacts sidecar
    rng = np.random.default_rng(42)
    embedding = rng.random(768, dtype=np.float32)
    save_maest_embedding_v7(
        artifacts,
        track_id=1,
        track_uuid=track_uuid,
        content_generation=1,
        contract_hash=embedding_contract,
        embedding=embedding,
        normalization="none",
        analyzed_at=analyzed_at,
    )

    # --- Assertions ---

    # Core: exactly 1 maest_scores row
    scores_count = core.execute("SELECT COUNT(*) FROM maest_scores").fetchone()[0]
    assert scores_count == 1, f"Expected 1 maest_scores row, got {scores_count}"

    # Artifacts: exactly 1 maest_embeddings row
    emb_count = artifacts.execute("SELECT COUNT(*) FROM maest_embeddings").fetchone()[0]
    assert emb_count == 1, f"Expected 1 maest_embeddings row, got {emb_count}"

    # syncopated_rhythm stored correctly
    synco = core.execute(
        "SELECT syncopated_rhythm FROM maest_scores WHERE track_id = 1"
    ).fetchone()[0]
    assert synco == 1, f"Expected syncopated_rhythm=1, got {synco}"

    # dim stored correctly in artifacts
    dim_val = artifacts.execute(
        "SELECT dim FROM maest_embeddings WHERE track_id = 1"
    ).fetchone()[0]
    assert dim_val == 768, f"Expected dim=768, got {dim_val}"

    # Decoded embedding matches input (float32 round-trip)
    blob_row = artifacts.execute(
        "SELECT embedding_blob, dim FROM maest_embeddings WHERE track_id = 1"
    ).fetchone()
    assert blob_row is not None
    raw_blob = blob_row["embedding_blob"]
    dim_stored = blob_row["dim"]
    decoded = np.frombuffer(raw_blob, dtype="<f4")
    assert len(decoded) == dim_stored == 768
    np.testing.assert_array_equal(decoded, embedding.astype("<f4"))

    # Core contracts: 2 rows for maest (one per output_kind)
    maest_contract_count = core.execute(
        "SELECT COUNT(*) FROM contracts WHERE analysis_family = 'maest'"
    ).fetchone()[0]
    assert maest_contract_count == 2, (
        f"Expected 2 maest contracts (analysis + embedding), got {maest_contract_count}"
    )

    core.close()
    artifacts.close()


def test_embedding_not_in_core() -> None:
    """Verify at schema and API level that Core maest_scores has no embedding column."""
    core = _make_core_db()

    # Schema-level: no 'embedding_blob' column in maest_scores
    columns = core.execute(
        "SELECT name FROM pragma_table_info('maest_scores')"
    ).fetchall()
    column_names = [row[0] for row in columns]
    assert "embedding_blob" not in column_names, (
        f"Core maest_scores must NOT have an embedding_blob column; found columns: {column_names}"
    )

    # API-level: save_maest_scores_v7 signature does NOT accept an 'embedding' parameter
    sig = inspect.signature(save_maest_scores_v7)
    assert "embedding" not in sig.parameters, (
        f"save_maest_scores_v7 must not accept an 'embedding' parameter; "
        f"found params: {list(sig.parameters)}"
    )

    # Calling with embedding= kwarg raises TypeError
    with pytest.raises(TypeError):
        save_maest_scores_v7(  # type: ignore[call-arg]
            core,
            track_id=1,
            content_generation=1,
            contract_hash="sha256:abc",
            syncopated_rhythm=0,
            genres_json="[]",
            analyzed_at=datetime.now(timezone.utc).isoformat(),
            embedding=b"should not be accepted",
        )

    core.close()
