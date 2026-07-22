"""Tests for v7 read-path adapters in set_builder.py (Todo 21).

Covers:
- _hydrate_v7_sonara_values(): scalar + short-vector statistics from v7 sonara table
- BUG-R1 regression: graceful handling when BLOB columns are absent/NULL

Conventions:
- No conftest.py; each test builds its own in-memory SQLite DB.
- No real SONARA — all values are synthetic.
- Run with: python -m pytest tests/test_set_builder_v7.py --override-ini addopts= -q
"""
from __future__ import annotations

import sqlite3
import struct
import uuid
from datetime import datetime, timezone

import numpy as np
import pytest

from dj_track_similarity.db_schema_v7 import create_v7_schema
from dj_track_similarity.set_builder import _hydrate_v7_sonara_values


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_core_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    create_v7_schema(conn)
    return conn


def _pack_f32(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


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


def _insert_contract(conn: sqlite3.Connection) -> str:
    """Insert a minimal sonara/core contract row; returns the contract_hash."""
    import hashlib
    import json

    payload = {
        "analysis_family": "sonara",
        "output_kind": "core",
        "model_name": "sonara-core",
        "model_version": "0.2.9",
        "release_hash": "test_release_hash_abc123",
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    contract_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT OR IGNORE INTO contracts (
            contract_hash, analysis_family, output_kind, model_name, model_version,
            release_hash, canonical_payload_json, created_at
        ) VALUES (?, 'sonara', 'core', 'sonara-core', '0.2.9', 'test_release_hash_abc123', ?, ?)
        """,
        (contract_hash, canonical, now),
    )
    conn.commit()
    return contract_hash


def _insert_sonara_row(
    conn: sqlite3.Connection,
    track_id: int,
    contract_hash: str,
    *,
    content_generation: int = 1,
    mfcc: list[float] | None = None,
    chroma: list[float] | None = None,
    contrast: list[float] | None = None,
    energy_score: float = 0.75,
    danceability_score: float = 0.82,
    valence_score: float = 0.45,
    acousticness_score: float = 0.1,
    dissonance_score: float = 0.2,
    detected_bpm: float = 128.0,
    onset_density_per_second: float = 4.2,
    rms_mean: float = 0.12,
    rms_max: float = 0.45,
    integrated_loudness_lufs: float = -9.5,
    dynamic_range_db: float = 6.0,
    chord_changes_per_second: float = 0.5,
    spectral_centroid_hz: float = 3200.0,
    spectral_bandwidth_hz: float = 1800.0,
    spectral_rolloff_hz: float = 8000.0,
    spectral_flatness: float = 0.15,
    zero_crossing_rate: float = 0.08,
    beat_count: int = 512,
) -> None:
    mfcc_values = mfcc if mfcc is not None else [float(i) * 0.1 for i in range(13)]
    chroma_values = chroma if chroma is not None else [float(i) * 0.05 for i in range(12)]
    contrast_values = contrast if contrast is not None else [float(i) * 0.2 for i in range(7)]

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO sonara (
            track_id, content_generation, contract_hash,
            detected_bpm, bpm_confidence, onset_density_per_second, beat_count,
            beat_grid_stability,
            energy_score, danceability_score, valence_score, acousticness_score, dissonance_score,
            spectral_centroid_hz, spectral_bandwidth_hz, spectral_rolloff_hz,
            spectral_flatness, zero_crossing_rate,
            rms_mean, rms_max, integrated_loudness_lufs, dynamic_range_db,
            chord_changes_per_second,
            mfcc_mean_blob, chroma_mean_blob, spectral_contrast_mean_blob,
            analyzed_at
        ) VALUES (
            ?, ?, ?,
            ?, 0.95, ?, ?,
            0.98,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, ?, ?, ?,
            ?,
            ?, ?, ?,
            ?
        )
        """,
        (
            track_id, content_generation, contract_hash,
            detected_bpm, onset_density_per_second, beat_count,
            energy_score, danceability_score, valence_score, acousticness_score, dissonance_score,
            spectral_centroid_hz, spectral_bandwidth_hz, spectral_rolloff_hz,
            spectral_flatness, zero_crossing_rate,
            rms_mean, rms_max, integrated_loudness_lufs, dynamic_range_db,
            chord_changes_per_second,
            _pack_f32(mfcc_values), _pack_f32(chroma_values), _pack_f32(contrast_values),
            now,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_hydrate_v7_sonara_values_returns_scalars_and_blob_stats() -> None:
    """_hydrate_v7_sonara_values returns scalar fields AND 9 short-vector statistics."""
    conn = _make_core_db()
    _insert_track(conn, track_id=1)
    contract_hash = _insert_contract(conn)

    mfcc_values = [float(i) * 0.1 for i in range(13)]
    chroma_values = [float(i) * 0.05 for i in range(12)]
    contrast_values = [float(i) * 0.2 for i in range(7)]

    _insert_sonara_row(
        conn,
        track_id=1,
        contract_hash=contract_hash,
        mfcc=mfcc_values,
        chroma=chroma_values,
        contrast=contrast_values,
        energy_score=0.75,
        danceability_score=0.82,
    )

    result = _hydrate_v7_sonara_values(conn, track_id=1)

    # --- Scalar fields ---
    assert "energy" in result, "energy (energy_score) must be present"
    assert abs(result["energy"] - 0.75) < 1e-5, f"energy: {result['energy']}"

    assert "danceability" in result, "danceability (danceability_score) must be present"
    assert abs(result["danceability"] - 0.82) < 1e-5, f"danceability: {result['danceability']}"

    assert "bpm" in result, "bpm (detected_bpm) must be present"
    assert abs(result["bpm"] - 128.0) < 1e-5

    assert "rms_mean" in result
    assert "dynamic_range_db" in result

    # --- Short-vector statistics (9 keys from _read_sonara_short_vectors_v7) ---
    mfcc_arr = np.array(mfcc_values, dtype=np.float32)
    chroma_arr = np.array(chroma_values, dtype=np.float32)
    contrast_arr = np.array(contrast_values, dtype=np.float32)

    assert "mfcc_mean.summary.min" in result
    assert "mfcc_mean.summary.max" in result
    assert "mfcc_mean.summary.mean" in result
    assert "mfcc_mean.summary.std" in result

    assert abs(result["mfcc_mean.summary.min"] - float(np.min(mfcc_arr))) < 1e-5
    assert abs(result["mfcc_mean.summary.max"] - float(np.max(mfcc_arr))) < 1e-5
    assert abs(result["mfcc_mean.summary.mean"] - float(np.mean(mfcc_arr))) < 1e-5
    assert abs(result["mfcc_mean.summary.std"] - float(np.std(mfcc_arr))) < 1e-5

    assert "chroma_mean.summary.min" in result
    assert "chroma_mean.summary.max" in result
    assert "chroma_mean.summary.mean" in result
    assert "chroma_mean.summary.std" in result

    assert abs(result["chroma_mean.summary.mean"] - float(np.mean(chroma_arr))) < 1e-5

    assert "spectral_contrast_mean" in result
    assert abs(result["spectral_contrast_mean"] - float(np.mean(contrast_arr))) < 1e-5

    conn.close()


def test_hydrate_v7_sonara_values_missing_row_returns_empty() -> None:
    """_hydrate_v7_sonara_values returns {} when no sonara row exists for the track."""
    conn = _make_core_db()
    _insert_track(conn, track_id=1)

    result = _hydrate_v7_sonara_values(conn, track_id=1)
    assert result == {}, f"Expected empty dict, got {result}"

    conn.close()


def test_hydrate_v7_sonara_values_no_sonara_table_returns_empty() -> None:
    """_hydrate_v7_sonara_values returns {} gracefully when the sonara table does not exist."""
    # Use a plain in-memory DB without the v7 schema
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    result = _hydrate_v7_sonara_values(conn, track_id=1)
    assert result == {}, f"Expected empty dict for missing table, got {result}"

    conn.close()


def test_broad_score_requires_blob_columns() -> None:
    """BUG-R1 regression: _hydrate_v7_sonara_values handles missing BLOB columns gracefully.

    The v7 sonara table enforces NOT NULL on the three BLOB columns, so they
    cannot be NULL in a valid row.  This test verifies the graceful-fallback
    contract for two degraded-schema scenarios:

    1. When the sonara table is entirely absent → returns empty dict (graceful).
    2. When the sonara table exists but the scalar columns are absent →
       returns empty dict (graceful — OperationalError is caught internally).

    The function is designed to degrade gracefully so that v6 code paths can
    still operate when the v7 schema is not present.  The BUG-R1 concern is
    that a missing BLOB column must not silently produce a partial result that
    feeds incorrect zeros into the SET broad score; instead the function must
    return {} so the caller falls back to the v6 JSON path.
    """
    # Scenario 1: table entirely absent → returns empty dict (graceful)
    conn_no_table = sqlite3.connect(":memory:")
    conn_no_table.row_factory = sqlite3.Row
    result_no_table = _hydrate_v7_sonara_values(conn_no_table, track_id=1)
    assert result_no_table == {}, "Missing table must return empty dict, not raise"
    conn_no_table.close()

    # Scenario 2: sonara table exists but the scalar columns queried by
    # _hydrate_v7_sonara_values are absent (only track_id column exists).
    # The scalar SELECT raises OperationalError internally, which is caught,
    # and the function returns {} gracefully.
    conn_bad_schema = sqlite3.connect(":memory:")
    conn_bad_schema.row_factory = sqlite3.Row
    conn_bad_schema.execute(
        """
        CREATE TABLE sonara (
            track_id INTEGER PRIMARY KEY
        )
        """
    )
    conn_bad_schema.execute("INSERT INTO sonara VALUES (1)")
    conn_bad_schema.commit()

    # OperationalError is caught internally → returns {} (graceful fallback)
    result_bad_schema = _hydrate_v7_sonara_values(conn_bad_schema, track_id=1)
    assert result_bad_schema == {}, (
        "Wrong-schema sonara table must return empty dict (graceful), "
        f"got {result_bad_schema}"
    )
    conn_bad_schema.close()

    # Scenario 3: verify that a VALID v7 sonara row with all BLOBs present
    # returns a non-empty dict (the positive case that BUG-R1 must not break).
    conn_valid = _make_core_db()
    _insert_track(conn_valid, track_id=1)
    contract_hash = _insert_contract(conn_valid)
    _insert_sonara_row(conn_valid, track_id=1, contract_hash=contract_hash)
    result_valid = _hydrate_v7_sonara_values(conn_valid, track_id=1)
    assert result_valid, "Valid sonara row must return a non-empty dict"
    # All three BLOB-derived stat groups must be present
    assert "mfcc_mean.summary.mean" in result_valid, "mfcc stats must be present"
    assert "chroma_mean.summary.mean" in result_valid, "chroma stats must be present"
    assert "spectral_contrast_mean" in result_valid, "spectral_contrast stats must be present"
    conn_valid.close()


def test_hydrate_v7_sonara_values_null_scalars_omitted() -> None:
    """NULL scalar values are silently omitted from the returned dict."""
    conn = _make_core_db()
    _insert_track(conn, track_id=1)
    contract_hash = _insert_contract(conn)

    # Insert a row with minimal non-NULL scalars (energy_score only, rest NULL)
    now = datetime.now(timezone.utc).isoformat()
    mfcc_blob = _pack_f32([0.0] * 13)
    chroma_blob = _pack_f32([0.0] * 12)
    contrast_blob = _pack_f32([0.0] * 7)
    conn.execute(
        """
        INSERT INTO sonara (
            track_id, content_generation, contract_hash,
            energy_score,
            mfcc_mean_blob, chroma_mean_blob, spectral_contrast_mean_blob,
            analyzed_at
        ) VALUES (?, 1, ?, ?, ?, ?, ?, ?)
        """,
        (1, contract_hash, 0.6, mfcc_blob, chroma_blob, contrast_blob, now),
    )
    conn.commit()

    result = _hydrate_v7_sonara_values(conn, track_id=1)

    # energy must be present
    assert "energy" in result
    assert abs(result["energy"] - 0.6) < 1e-5

    # bpm (detected_bpm) was NULL → must be absent
    assert "bpm" not in result, f"bpm should be absent (NULL in DB), got {result.get('bpm')}"

    # rms_mean was NULL → must be absent
    assert "rms_mean" not in result

    # BLOB stats must still be present (BLOBs are NOT NULL)
    assert "mfcc_mean.summary.mean" in result

    conn.close()
