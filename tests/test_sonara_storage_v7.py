"""Tests for v7 SONARA Core storage: save_sonara_core_v7 and helpers.

Conventions:
- No conftest.py; each test builds its own in-memory SQLite DB.
- No real SONARA — all outputs are synthetic fixed-value dicts.
- Run with: python -m pytest tests/test_sonara_storage_v7.py --override-ini addopts= -q
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
import uuid
from datetime import datetime, timezone

import numpy as np
import pytest

from dj_track_similarity.db_artifacts import create_artifacts_sidecar_schema
from dj_track_similarity.db_schema_v7 import create_v7_schema
from dj_track_similarity.sonara_storage import (
    save_sonara_core_v7,
    save_sonara_fingerprint_v7,
    save_sonara_similarity_embedding_v7,
    save_sonara_timeline_v7,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> sqlite3.Connection:
    """Return an in-memory v7 schema connection with FK enforcement."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_v7_schema(conn)
    return conn


def _insert_track(conn: sqlite3.Connection, track_id: int = 1, content_generation: int = 1) -> None:
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
            str(uuid.uuid4()),
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


def _pack_f32(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _make_sonara_output(
    *,
    mfcc: list[float] | None = None,
    chroma: list[float] | None = None,
    contrast: list[float] | None = None,
) -> dict[str, object]:
    """Build a complete synthetic SONARA Core output dict."""
    mfcc_values = mfcc if mfcc is not None else [float(i) * 0.1 for i in range(13)]
    chroma_values = chroma if chroma is not None else [float(i) * 0.05 for i in range(12)]
    contrast_values = contrast if contrast is not None else [float(i) * 0.2 for i in range(7)]

    return {
        # Rhythm
        "detected_bpm": 128.0,
        "raw_bpm": 127.8,
        "bpm_confidence": 0.95,
        "onset_density_per_second": 4.2,
        "beat_count": 512,
        "tempo_variability": 0.02,
        "beat_grid_offset_seconds": 0.01,
        "beat_grid_stability": 0.98,
        "bpm_candidates_json": '[{"rank":1,"bpm":128.0,"score":0.95},{"rank":2,"bpm":64.0,"score":0.3}]',
        # Tonal
        "detected_key_name": "A minor",
        "detected_key_camelot": "8A",
        "key_confidence": 0.87,
        "predominant_chord": "Am",
        "chord_changes_per_second": 0.5,
        "key_candidates_json": '[{"rank":1,"key_name":"A minor","camelot":"8A","score":0.87}]',
        # Perceptual
        "energy_score": 0.75,
        "energy_level": 8,
        "danceability_score": 0.82,
        "valence_score": 0.45,
        "acousticness_score": 0.1,
        "dissonance_score": 0.2,
        # Spectral
        "spectral_centroid_hz": 3200.0,
        "spectral_bandwidth_hz": 1800.0,
        "spectral_rolloff_hz": 8000.0,
        "spectral_flatness": 0.15,
        "zero_crossing_rate": 0.08,
        # Loudness
        "rms_mean": 0.12,
        "rms_max": 0.45,
        "integrated_loudness_lufs": -9.5,
        "dynamic_range_db": 6.0,
        "true_peak_dbtp": -0.3,
        "replay_gain_db": -1.2,
        "max_momentary_loudness_lufs": -6.0,
        "loudness_range_lu": 4.5,
        # Structure
        "analyzed_duration_seconds": 360.0,
        "intro_end_seconds": 16.0,
        "outro_start_seconds": 340.0,
        "leading_silence_seconds": 0.05,
        "trailing_silence_seconds": 0.1,
        # Energy curve
        "energy_curve_hop_seconds": 0.5,
        "energy_curve_sample_count": 720,
        "energy_curve_min": 0.1,
        "energy_curve_max": 0.9,
        "energy_curve_mean": 0.5,
        "energy_curve_stddev": 0.15,
        # Voice / Mood
        "vocal_probability": 0.3,
        "mood_happy_score": 0.6,
        "mood_aggressive_score": 0.4,
        "mood_relaxed_score": 0.35,
        "mood_sad_score": 0.2,
        # BLOBs
        "mfcc_mean_blob": _pack_f32(mfcc_values),
        "chroma_mean_blob": _pack_f32(chroma_values),
        "spectral_contrast_mean_blob": _pack_f32(contrast_values),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sonara_core_row_written() -> None:
    """save_sonara_core_v7 writes exactly one sonara row and one contracts row."""
    conn = _make_db()
    _insert_track(conn, track_id=1, content_generation=1)

    mfcc_values = [float(i) * 0.1 for i in range(13)]
    output = _make_sonara_output(mfcc=mfcc_values)
    analyzed_at = datetime.now(timezone.utc).isoformat()

    contract_hash = save_sonara_core_v7(
        conn,
        track_id=1,
        content_generation=1,
        sonara_output=output,
        analyzed_at=analyzed_at,
        model_name="sonara-core",
        model_version="0.2.9",
        release_hash="abc123def456",
    )

    # One sonara row for track_id=1
    count = conn.execute(
        "SELECT COUNT(*) FROM sonara WHERE track_id = 1"
    ).fetchone()[0]
    assert count == 1, f"Expected 1 sonara row, got {count}"

    # No NULL mfcc blobs
    null_count = conn.execute(
        "SELECT COUNT(*) FROM sonara WHERE mfcc_mean_blob IS NULL"
    ).fetchone()[0]
    assert null_count == 0, "mfcc_mean_blob must not be NULL"

    # One contracts row for sonara/core
    contract_count = conn.execute(
        "SELECT COUNT(*) FROM contracts WHERE analysis_family = 'sonara' AND output_kind = 'core'"
    ).fetchone()[0]
    assert contract_count == 1, f"Expected 1 contracts row, got {contract_count}"

    # energy_score is a REAL value
    row = conn.execute("SELECT energy_score FROM sonara WHERE track_id = 1").fetchone()
    assert row is not None
    assert isinstance(row["energy_score"], float), f"energy_score should be float, got {type(row['energy_score'])}"
    assert abs(row["energy_score"] - 0.75) < 1e-6

    # Decoded MFCC blob matches input
    blob_row = conn.execute("SELECT mfcc_mean_blob FROM sonara WHERE track_id = 1").fetchone()
    assert blob_row is not None
    raw_blob = blob_row["mfcc_mean_blob"]
    decoded = list(struct.unpack("<13f", raw_blob))
    assert len(decoded) == 13
    for i, (got, expected) in enumerate(zip(decoded, mfcc_values)):
        assert abs(got - expected) < 1e-5, f"MFCC[{i}]: got {got}, expected {expected}"

    # contract_hash returned is a sha256 string
    assert contract_hash.startswith("sha256:"), f"Unexpected contract_hash: {contract_hash}"

    conn.close()


def test_missing_mfcc_rejected() -> None:
    """save_sonara_core_v7 raises ValueError when mfcc_mean_blob is None; nothing written."""
    conn = _make_db()
    _insert_track(conn, track_id=1, content_generation=1)

    output = _make_sonara_output()
    output["mfcc_mean_blob"] = None  # type: ignore[assignment]

    analyzed_at = datetime.now(timezone.utc).isoformat()

    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        save_sonara_core_v7(
            conn,
            track_id=1,
            content_generation=1,
            sonara_output=output,
            analyzed_at=analyzed_at,
            model_name="sonara-core",
            model_version="0.2.9",
            release_hash="abc123def456",
        )

    # Nothing written to sonara table
    count = conn.execute("SELECT COUNT(*) FROM sonara").fetchone()[0]
    assert count == 0, f"Expected 0 sonara rows after rejection, got {count}"

    conn.close()


def test_wrong_mfcc_length_rejected() -> None:
    """save_sonara_core_v7 raises ValueError when mfcc_mean_blob has wrong byte length."""
    conn = _make_db()
    _insert_track(conn, track_id=1, content_generation=1)

    output = _make_sonara_output()
    # 10 floats instead of 13 → wrong length
    output["mfcc_mean_blob"] = struct.pack("<10f", *[0.0] * 10)

    analyzed_at = datetime.now(timezone.utc).isoformat()

    with pytest.raises((ValueError, sqlite3.IntegrityError)):
        save_sonara_core_v7(
            conn,
            track_id=1,
            content_generation=1,
            sonara_output=output,
            analyzed_at=analyzed_at,
            model_name="sonara-core",
            model_version="0.2.9",
            release_hash="abc123def456",
        )

    count = conn.execute("SELECT COUNT(*) FROM sonara").fetchone()[0]
    assert count == 0, f"Expected 0 sonara rows after rejection, got {count}"

    conn.close()


def test_contract_upsert_idempotent() -> None:
    """Calling save_sonara_core_v7 twice with the same contract params inserts only one contracts row."""
    conn = _make_db()
    _insert_track(conn, track_id=1, content_generation=1)
    _insert_track(conn, track_id=2, content_generation=1)

    analyzed_at = datetime.now(timezone.utc).isoformat()
    kwargs = dict(
        model_name="sonara-core",
        model_version="0.2.9",
        release_hash="abc123def456",
    )

    save_sonara_core_v7(
        conn, track_id=1, content_generation=1,
        sonara_output=_make_sonara_output(), analyzed_at=analyzed_at, **kwargs,
    )
    save_sonara_core_v7(
        conn, track_id=2, content_generation=1,
        sonara_output=_make_sonara_output(), analyzed_at=analyzed_at, **kwargs,
    )

    contract_count = conn.execute(
        "SELECT COUNT(*) FROM contracts WHERE analysis_family = 'sonara' AND output_kind = 'core'"
    ).fetchone()[0]
    assert contract_count == 1, f"Expected 1 contracts row (idempotent upsert), got {contract_count}"

    sonara_count = conn.execute("SELECT COUNT(*) FROM sonara").fetchone()[0]
    assert sonara_count == 2

    conn.close()


# ---------------------------------------------------------------------------
# Helpers for sidecar tests (Todo 16)
# ---------------------------------------------------------------------------

def _make_artifacts_db() -> sqlite3.Connection:
    """Return an in-memory artifacts sidecar connection."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_artifacts_sidecar_schema(conn, catalog_uuid="test-catalog")
    return conn


def _insert_contract(
    core_conn: sqlite3.Connection,
    output_kind: str,
    model_name: str = "sonara-core",
    model_version: str = "0.2.9",
    release_hash: str = "abc123def456",
) -> str:
    """Insert a contracts row for the given output_kind and return the contract_hash."""
    payload: dict[str, object] = {
        "analysis_family": "sonara",
        "output_kind": output_kind,
        "model_name": model_name,
        "model_version": model_version,
        "release_hash": release_hash,
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    contract_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    core_conn.execute(
        """
        INSERT OR IGNORE INTO contracts (
            contract_hash, analysis_family, output_kind,
            model_name, model_version, release_hash,
            canonical_payload_json, created_at
        ) VALUES (?, 'sonara', ?, ?, ?, ?, ?, ?)
        """,
        (contract_hash, output_kind, model_name, model_version, release_hash, canonical, now),
    )
    core_conn.commit()
    return contract_hash


# ---------------------------------------------------------------------------
# Sidecar tests (Todo 16)
# ---------------------------------------------------------------------------

def test_sidecar_tables_populated() -> None:
    """save_sonara_{timeline,fingerprint,similarity_embedding}_v7 each write one row."""
    core_conn = _make_db()
    artifacts_conn = _make_artifacts_db()

    track_uuid = str(uuid.uuid4())
    track_id = 1
    content_generation = 1
    analyzed_at = datetime.now(timezone.utc).isoformat()

    # Insert track into core DB
    now = datetime.now(timezone.utc).isoformat()
    core_conn.execute(
        """
        INSERT INTO tracks (
            track_id, track_uuid, file_path, file_size_bytes, file_modified_ns,
            content_generation, last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            track_uuid,
            "/music/track_1.flac",
            1_234_567,
            1_700_000_000_000_000_000,
            content_generation,
            now,
            now,
            now,
        ),
    )
    core_conn.commit()

    # Upsert contracts for each output_kind
    timeline_hash = _insert_contract(core_conn, output_kind="timeline")
    fingerprint_hash = _insert_contract(core_conn, output_kind="fingerprint")
    embedding_hash = _insert_contract(core_conn, output_kind="embedding")

    # --- Timeline ---
    payload = {"beats": [0.5, 1.0, 1.5], "downbeats": [0.5, 1.5]}
    payload_json = json.dumps(payload)
    save_sonara_timeline_v7(
        artifacts_conn,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=content_generation,
        contract_hash=timeline_hash,
        payload_json=payload_json,
        analyzed_at=analyzed_at,
    )

    # --- Fingerprint ---
    word_list = [0, 1, 2, 4_294_967_295, 123456789]
    save_sonara_fingerprint_v7(
        artifacts_conn,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=content_generation,
        contract_hash=fingerprint_hash,
        fingerprint_version="v1",
        word_list=word_list,
        analyzed_at=analyzed_at,
    )

    # --- Similarity embedding ---
    embedding = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    save_sonara_similarity_embedding_v7(
        artifacts_conn,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=content_generation,
        contract_hash=embedding_hash,
        embedding=embedding,
        normalization="l2",
        analyzed_at=analyzed_at,
    )

    # Assert row counts
    tl_count = artifacts_conn.execute("SELECT COUNT(*) FROM sonara_timeline").fetchone()[0]
    assert tl_count == 1, f"Expected 1 sonara_timeline row, got {tl_count}"

    fp_count = artifacts_conn.execute("SELECT COUNT(*) FROM sonara_fingerprints").fetchone()[0]
    assert fp_count == 1, f"Expected 1 sonara_fingerprints row, got {fp_count}"

    emb_count = artifacts_conn.execute("SELECT COUNT(*) FROM sonara_similarity_embeddings").fetchone()[0]
    assert emb_count == 1, f"Expected 1 sonara_similarity_embeddings row, got {emb_count}"

    # Assert timeline payload_json round-trips
    tl_row = artifacts_conn.execute(
        "SELECT payload_json FROM sonara_timeline WHERE track_id = ?", (track_id,)
    ).fetchone()
    assert tl_row is not None
    assert json.loads(tl_row["payload_json"]) == payload

    # Assert fingerprint blob decodes back to original uint32 sequence
    fp_row = artifacts_conn.execute(
        "SELECT word_count, byte_order, fingerprint_blob FROM sonara_fingerprints WHERE track_id = ?",
        (track_id,),
    ).fetchone()
    assert fp_row is not None
    assert fp_row["byte_order"] == "little"
    assert fp_row["word_count"] == len(word_list)
    decoded_words = list(struct.unpack(f"<{fp_row['word_count']}I", fp_row["fingerprint_blob"]))
    assert decoded_words == word_list

    # Assert similarity embedding blob decodes to original float32 array
    emb_row = artifacts_conn.execute(
        "SELECT dim, normalization, embedding_blob FROM sonara_similarity_embeddings WHERE track_id = ?",
        (track_id,),
    ).fetchone()
    assert emb_row is not None
    assert emb_row["normalization"] == "l2"
    assert emb_row["dim"] == len(embedding)
    decoded_emb = np.frombuffer(emb_row["embedding_blob"], dtype="<f4")
    expected_emb = np.asarray(embedding, dtype="<f4")
    np.testing.assert_array_almost_equal(decoded_emb, expected_emb, decimal=6)

    core_conn.close()
    artifacts_conn.close()


def test_v6_fingerprint_rejected() -> None:
    """save_sonara_fingerprint_v7 raises ValueError when given a dict (v6 format)."""
    artifacts_conn = _make_artifacts_db()

    track_uuid = str(uuid.uuid4())
    analyzed_at = datetime.now(timezone.utc).isoformat()
    fake_hash = "sha256:" + "a" * 64

    # Attempt to call with a dict (v6 JSON-array-under-payload_json format)
    with pytest.raises(ValueError, match="v6 fingerprint format rejected"):
        save_sonara_fingerprint_v7(
            artifacts_conn,
            track_id=1,
            track_uuid=track_uuid,
            content_generation=1,
            contract_hash=fake_hash,
            fingerprint_version="v1",
            word_list={"value": [1, 2, 3]},  # type: ignore[arg-type]
            analyzed_at=analyzed_at,
        )

    # Assert no rows written
    count = artifacts_conn.execute("SELECT COUNT(*) FROM sonara_fingerprints").fetchone()[0]
    assert count == 0, f"Expected 0 sonara_fingerprints rows after rejection, got {count}"

    artifacts_conn.close()
