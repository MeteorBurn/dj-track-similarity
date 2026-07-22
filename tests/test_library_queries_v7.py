"""Tests for v7 track assembly: assemble_track_summary_v7 / assemble_track_detail_v7.

Conventions:
- No conftest.py; each test builds its own in-memory SQLite DBs (Core + artifacts sidecar).
- No real ML models — all embeddings are synthetic.
- Run with: python -m pytest tests/test_library_queries_v7.py --override-ini addopts= -q
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

from dj_track_similarity.db_analysis import (
    save_clap_embedding_v7,
    save_maest_embedding_v7,
    save_maest_scores_v7,
    save_mert_embedding_v7,
    save_muq_embedding_v7,
    upsert_maest_contract_v7,
    upsert_ml_embedding_contract_v7,
)
from dj_track_similarity.db_artifacts import create_artifacts_sidecar_schema
from dj_track_similarity.db_schema_v7 import create_v7_schema
from dj_track_similarity.db_library_queries import (
    assemble_track_summary_v7,
    assemble_track_detail_v7,
)
from dj_track_similarity.sonara_storage import (
    save_sonara_core_v7,
    save_sonara_fingerprint_v7,
    save_sonara_similarity_embedding_v7,
    save_sonara_timeline_v7,
)


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
    file_path: str | None = None,
) -> str:
    """Insert a minimal track row; returns the track_uuid."""
    track_uuid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    path = file_path or f"/music/track_{track_id}.flac"
    conn.execute(
        """
        INSERT INTO tracks (
            track_id, track_uuid, file_path, file_size_bytes, file_modified_ns,
            audio_format, audio_codec, sample_rate_hz, channel_count, bit_rate_bps,
            audio_duration_seconds, content_generation, last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            track_uuid,
            path,
            12_345_678,
            1_700_000_000_000_000_000,
            "flac",
            "flac",
            44100,
            2,
            1411000,
            360.0,
            content_generation,
            now,
            now,
            now,
        ),
    )
    conn.commit()
    return track_uuid


def _insert_file_tags(conn: sqlite3.Connection, track_id: int = 1) -> None:
    """Insert a file_tags row for the given track."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO file_tags (
            track_id, title, artist, album, tag_bpm, tag_key,
            comment, year, label, catalog_number, country, isrc,
            track_number, disc_number, genres_json, tags_read_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            "Test Track",
            "Test Artist",
            "Test Album",
            128.0,
            "Am",
            "A test comment",
            2020,
            "Test Label",
            "CAT001",
            "DE",
            "DEABC1234567",
            "1",
            "1",
            '["Techno", "House"]',
            now,
        ),
    )
    conn.commit()


def _pack_f32(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _make_sonara_output() -> dict:
    """Build a complete synthetic SONARA Core output dict."""
    return {
        "detected_bpm": 128.0,
        "raw_bpm": 127.8,
        "bpm_confidence": 0.95,
        "onset_density_per_second": 4.2,
        "beat_count": 512,
        "tempo_variability": 0.02,
        "beat_grid_offset_seconds": 0.01,
        "beat_grid_stability": 0.98,
        "bpm_candidates_json": '[{"rank":1,"bpm":128.0,"score":0.95}]',
        "detected_key_name": "A minor",
        "detected_key_camelot": "8A",
        "key_confidence": 0.87,
        "predominant_chord": "Am",
        "chord_changes_per_second": 0.5,
        "key_candidates_json": '[{"rank":1,"key_name":"A minor","camelot":"8A","score":0.87}]',
        "energy_score": 0.75,
        "energy_level": 8,
        "danceability_score": 0.82,
        "valence_score": 0.45,
        "acousticness_score": 0.1,
        "dissonance_score": 0.2,
        "spectral_centroid_hz": 3200.0,
        "spectral_bandwidth_hz": 1800.0,
        "spectral_rolloff_hz": 8000.0,
        "spectral_flatness": 0.15,
        "zero_crossing_rate": 0.08,
        "rms_mean": 0.12,
        "rms_max": 0.45,
        "integrated_loudness_lufs": -9.5,
        "dynamic_range_db": 6.0,
        "true_peak_dbtp": -0.3,
        "replay_gain_db": -1.2,
        "max_momentary_loudness_lufs": -6.0,
        "loudness_range_lu": 4.5,
        "analyzed_duration_seconds": 360.0,
        "intro_end_seconds": 16.0,
        "outro_start_seconds": 340.0,
        "leading_silence_seconds": 0.05,
        "trailing_silence_seconds": 0.1,
        "energy_curve_hop_seconds": 0.5,
        "energy_curve_sample_count": 720,
        "energy_curve_min": 0.1,
        "energy_curve_max": 0.9,
        "energy_curve_mean": 0.5,
        "energy_curve_stddev": 0.15,
        "vocal_probability": 0.3,
        "mood_happy_score": 0.6,
        "mood_aggressive_score": 0.4,
        "mood_relaxed_score": 0.35,
        "mood_sad_score": 0.2,
        "mfcc_mean_blob": _pack_f32([float(i) * 0.1 for i in range(13)]),
        "chroma_mean_blob": _pack_f32([float(i) * 0.05 for i in range(12)]),
        "spectral_contrast_mean_blob": _pack_f32([float(i) * 0.2 for i in range(7)]),
    }


def _insert_classifier_score(
    conn: sqlite3.Connection,
    track_id: int = 1,
    classifier_key: str = "live_instrumentation",
) -> None:
    """Insert a classifier_scores row for the given track."""
    now = datetime.now(timezone.utc).isoformat()
    probabilities = {"live": 0.87, "studio": 0.13}
    conn.execute(
        """
        INSERT INTO classifier_scores (
            track_id, classifier_key, content_generation, model_id, feature_set,
            feature_manifest_hash, uses_sonara, sonara_release_hash,
            positive_label, predicted_class, score_bucket, score, confidence,
            probabilities_json, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            classifier_key,
            1,
            "model-abc123",
            "sonara_mert",
            "manifest-hash-xyz",
            1,
            "release-hash-abc",
            "live",
            "live",
            "high",
            0.87,
            0.87,
            json.dumps(probabilities),
            now,
        ),
    )
    conn.commit()


def _insert_sonara_contract(
    core_conn: sqlite3.Connection,
    output_kind: str,
    model_name: str = "sonara-core",
    model_version: str = "0.2.9",
    release_hash: str = "test-release-hash-abc123",
) -> str:
    """Insert a SONARA contracts row for the given output_kind; return contract_hash."""
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


def _build_full_v7_fixture() -> tuple[sqlite3.Connection, sqlite3.Connection, int, str]:
    """Build a complete v7 Core + artifacts fixture with 1 track and all analysis types.

    Returns (core_conn, artifacts_conn, track_id, release_hash).
    """
    core = _make_core_db()
    artifacts = _make_artifacts_db()
    track_id = 1
    release_hash = "test-release-hash-abc123"
    analyzed_at = datetime.now(timezone.utc).isoformat()

    track_uuid = _insert_track(core, track_id=track_id)
    _insert_file_tags(core, track_id=track_id)

    # SONARA Core
    save_sonara_core_v7(
        core,
        track_id=track_id,
        content_generation=1,
        sonara_output=_make_sonara_output(),
        analyzed_at=analyzed_at,
        model_name="sonara-core",
        model_version="0.2.9",
        release_hash=release_hash,
    )

    # MAEST scores
    scores_contract = upsert_maest_contract_v7(
        core,
        model_name="maest-discogs-400d",
        model_version="1.0",
        dim=None,
        output_kind="analysis",
    )
    save_maest_scores_v7(
        core,
        track_id=track_id,
        content_generation=1,
        contract_hash=scores_contract,
        syncopated_rhythm=1,
        genres_json='[{"rank":1,"genre_name":"techno","score":0.85}]',
        analyzed_at=analyzed_at,
    )

    # MAEST embedding in sidecar
    maest_emb_contract = upsert_maest_contract_v7(
        core,
        model_name="maest-discogs-400d",
        model_version="1.0",
        dim=768,
        output_kind="embedding",
    )
    rng = np.random.default_rng(0)
    save_maest_embedding_v7(
        artifacts,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=1,
        contract_hash=maest_emb_contract,
        embedding=rng.random(768, dtype=np.float32),
        normalization="l2",
        analyzed_at=analyzed_at,
    )

    # MERT embedding
    mert_contract = upsert_ml_embedding_contract_v7(
        core, family="mert", model_name="m-a-p/MERT-v1-95M",
        model_version="1.0", dim=768, normalization="l2",
    )
    save_mert_embedding_v7(
        artifacts,
        track_id=track_id, track_uuid=track_uuid, content_generation=1,
        contract_hash=mert_contract,
        embedding=rng.random(768, dtype=np.float32),
        normalization="l2", analyzed_at=analyzed_at,
    )

    # MuQ embedding
    muq_contract = upsert_ml_embedding_contract_v7(
        core, family="muq", model_name="OpenMuQ/MuQ-large-msd-iter",
        model_version="1.0", dim=1024, normalization="l2",
    )
    save_muq_embedding_v7(
        artifacts,
        track_id=track_id, track_uuid=track_uuid, content_generation=1,
        contract_hash=muq_contract,
        embedding=rng.random(1024, dtype=np.float32),
        normalization="l2", analyzed_at=analyzed_at,
    )

    # CLAP embedding
    clap_contract = upsert_ml_embedding_contract_v7(
        core, family="clap",
        model_name="lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt",
        model_version="1.0", dim=512, normalization="none",
    )
    save_clap_embedding_v7(
        artifacts,
        track_id=track_id, track_uuid=track_uuid, content_generation=1,
        contract_hash=clap_contract,
        embedding=rng.random(512, dtype=np.float32),
        normalization="none", analyzed_at=analyzed_at,
    )

    # SONARA similarity embedding in sidecar
    sonara_emb_contract = _insert_sonara_contract(core, output_kind="embedding", release_hash=release_hash)
    save_sonara_similarity_embedding_v7(
        artifacts,
        track_id=track_id, track_uuid=track_uuid, content_generation=1,
        contract_hash=sonara_emb_contract,
        embedding=rng.random(256, dtype=np.float32),
        normalization="l2", analyzed_at=analyzed_at,
    )

    # SONARA timeline in sidecar
    timeline_contract = _insert_sonara_contract(core, output_kind="timeline", release_hash=release_hash)
    save_sonara_timeline_v7(
        artifacts,
        track_id=track_id, track_uuid=track_uuid, content_generation=1,
        contract_hash=timeline_contract,
        payload_json='{"beats": [0.5, 1.0, 1.5], "downbeats": [0.5]}',
        analyzed_at=analyzed_at,
    )

    # SONARA fingerprint in sidecar
    fp_contract = _insert_sonara_contract(core, output_kind="fingerprint", release_hash=release_hash)
    save_sonara_fingerprint_v7(
        artifacts,
        track_id=track_id, track_uuid=track_uuid, content_generation=1,
        contract_hash=fp_contract,
        fingerprint_version="v1",
        word_list=[0xDEADBEEF, 0xCAFEBABE, 0x12345678, 0xABCDEF01],
        analyzed_at=analyzed_at,
    )

    # Classifier score
    _insert_classifier_score(core, track_id=track_id)

    return core, artifacts, track_id, release_hash


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_track_summary_no_metadata_json() -> None:
    """assemble_track_summary_v7 returns a clean v7 dict with no legacy v6 fields.

    Verifies:
    - No 'metadata_json' key in result
    - No 'has_sonara_analysis' key in result
    - No top-level 'bpm' key (only tag_bpm from file_tags)
    - analysis_coverage present with expected booleans
    - classifier_scores list contains entries with predicted_class and score_bucket
    - The v7 tracks table has no 'metadata_json' column (schema verification)
    """
    core, artifacts, track_id, release_hash = _build_full_v7_fixture()

    result = assemble_track_summary_v7(
        core_conn=core,
        artifacts_conn=artifacts,
        track_id=track_id,
        sonara_active_release_hash=release_hash,
    )

    assert result is not None, "assemble_track_summary_v7 must return a dict for a valid track_id"

    # --- No legacy v6 fields ---
    assert "metadata_json" not in result, (
        "Result must NOT contain 'metadata_json' — that is a v6 legacy field"
    )
    assert "has_sonara_analysis" not in result, (
        "Result must NOT contain 'has_sonara_analysis' — that is a v6 has_* flag"
    )
    assert "has_maest_analysis" not in result, (
        "Result must NOT contain 'has_maest_analysis' — that is a v6 has_* flag"
    )
    assert "bpm" not in result, (
        "Result must NOT have a top-level 'bpm' key — use tag_bpm from file_tags"
    )
    assert "energy" not in result, (
        "Result must NOT have a top-level 'energy' key — that is a v6 legacy field"
    )
    assert "musical_key" not in result, (
        "Result must NOT have a top-level 'musical_key' key — that is a v6 legacy field"
    )
    assert "duration" not in result, (
        "Result must NOT have a top-level 'duration' key — use audio_duration_seconds"
    )
    assert "embedding_model" not in result, (
        "Result must NOT contain 'embedding_model' — that is a v6 legacy field"
    )
    assert "embedding_dim" not in result, (
        "Result must NOT contain 'embedding_dim' — that is a v6 legacy field"
    )

    # --- Required v7 top-level fields ---
    assert "track_id" in result
    assert "file_path" in result
    assert "audio_duration_seconds" in result
    assert "liked" in result
    assert result["track_id"] == track_id
    assert result["file_path"] == f"/music/track_{track_id}.flac"
    assert result["audio_duration_seconds"] == 360.0
    assert result["liked"] is False

    # --- tag_bpm from file_tags ---
    assert "tag_bpm" in result
    assert result["tag_bpm"] == 128.0

    # --- analysis_coverage ---
    assert "analysis_coverage" in result
    coverage = result["analysis_coverage"]
    assert isinstance(coverage, dict)
    expected_keys = {"sonara_core", "timeline", "sonara_embedding", "fingerprint", "maest", "mert", "muq", "clap"}
    assert set(coverage.keys()) == expected_keys, (
        f"analysis_coverage keys mismatch: {set(coverage.keys())} != {expected_keys}"
    )
    assert coverage["sonara_core"] is True, "sonara_core coverage must be True"
    assert coverage["maest"] is True, "maest coverage must be True"
    assert coverage["mert"] is True, "mert coverage must be True"
    assert coverage["muq"] is True, "muq coverage must be True"
    assert coverage["clap"] is True, "clap coverage must be True"
    assert coverage["sonara_embedding"] is True, "sonara_embedding coverage must be True"
    assert coverage["timeline"] is True, "timeline coverage must be True"
    assert coverage["fingerprint"] is True, "fingerprint coverage must be True"

    # --- classifier_scores ---
    assert "classifier_scores" in result
    cs = result["classifier_scores"]
    assert isinstance(cs, list)
    assert len(cs) == 1, f"Expected 1 classifier score, got {len(cs)}"
    score_entry = cs[0]
    assert "predicted_class" in score_entry, "classifier_scores entry must have 'predicted_class'"
    assert "score_bucket" in score_entry, "classifier_scores entry must have 'score_bucket'"
    assert "classifier_key" in score_entry
    assert "score" in score_entry
    assert "confidence" in score_entry
    assert score_entry["classifier_key"] == "live_instrumentation"
    assert score_entry["predicted_class"] == "live"
    assert score_entry["score_bucket"] == "high"
    assert abs(score_entry["score"] - 0.87) < 1e-6

    # --- Schema verification: metadata_json column must NOT exist in v7 tracks ---
    count = core.execute(
        "SELECT COUNT(*) FROM pragma_table_info('tracks') WHERE name='metadata_json'"
    ).fetchone()[0]
    assert count == 0, (
        f"v7 tracks table must NOT have a 'metadata_json' column, but pragma_table_info returned count={count}"
    )

    core.close()
    artifacts.close()


def test_track_detail_v7_no_raw_bytes() -> None:
    """assemble_track_detail_v7 returns full detail with no BLOB fields.

    Verifies:
    - No raw bytes values anywhere in the returned dict
    - optional_outputs.timeline_fields is a list of strings when timeline row exists
    - embeddings list contains summaries with dim/normalization/model_name (no blob)
    - sonara_core.vector_summaries contains dim info (no raw bytes)
    - classifier_scores_detail contains probabilities as dict[str, float]
    - file_tags.genres is a decoded list of strings
    """
    core, artifacts, track_id, release_hash = _build_full_v7_fixture()

    result = assemble_track_detail_v7(
        core_conn=core,
        artifacts_conn=artifacts,
        track_id=track_id,
        sonara_active_release_hash=release_hash,
    )

    assert result is not None, "assemble_track_detail_v7 must return a dict for a valid track_id"

    # --- No legacy v6 fields ---
    assert "metadata_json" not in result
    assert "has_sonara_analysis" not in result
    assert "bpm" not in result

    # --- No raw BLOB bytes anywhere in the result ---
    def _find_bytes_values(obj: object, path: str = "") -> list[str]:
        """Recursively find any bytes values in a nested dict/list structure."""
        found = []
        if isinstance(obj, bytes):
            found.append(path)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                found.extend(_find_bytes_values(v, f"{path}.{k}" if path else str(k)))
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                found.extend(_find_bytes_values(v, f"{path}[{i}]"))
        return found

    bytes_paths = _find_bytes_values(result)
    assert not bytes_paths, (
        f"assemble_track_detail_v7 must NOT expose raw bytes. Found bytes at: {bytes_paths}"
    )

    # --- file sub-model ---
    assert "file" in result
    file_info = result["file"]
    assert isinstance(file_info, dict)
    assert file_info["file_size_bytes"] == 12_345_678
    assert file_info["audio_format"] == "flac"
    assert file_info["sample_rate_hz"] == 44100
    assert file_info["channel_count"] == 2
    assert file_info["audio_duration_seconds"] == 360.0

    # --- file_tags sub-model ---
    assert "file_tags" in result
    ft = result["file_tags"]
    assert ft is not None
    assert ft["title"] == "Test Track"
    assert ft["artist"] == "Test Artist"
    assert ft["tag_bpm"] == 128.0
    assert isinstance(ft["genres"], list), "file_tags.genres must be a decoded list"
    assert "Techno" in ft["genres"], f"Expected 'Techno' in genres, got {ft['genres']}"
    assert "House" in ft["genres"], f"Expected 'House' in genres, got {ft['genres']}"

    # --- sonara_core sub-model ---
    assert "sonara_core" in result
    sc = result["sonara_core"]
    assert sc is not None
    assert sc["detected_bpm"] == 128.0
    assert sc["energy_score"] == 0.75
    # vector_summaries: dim info only, no raw bytes
    assert "vector_summaries" in sc
    vs = sc["vector_summaries"]
    assert isinstance(vs, list)
    assert len(vs) == 3, f"Expected 3 vector summaries (mfcc, chroma, contrast), got {len(vs)}"
    for entry in vs:
        assert "vector_type" in entry
        assert "dim" in entry
        assert isinstance(entry["dim"], int)
        assert "embedding_blob" not in entry, "vector_summaries must NOT contain raw blob bytes"
    # bpm_candidates decoded from JSON
    assert isinstance(sc["bpm_candidates"], list)
    assert len(sc["bpm_candidates"]) == 1
    assert sc["bpm_candidates"][0]["bpm"] == 128.0

    # --- maest sub-model ---
    assert "maest" in result
    maest = result["maest"]
    assert maest is not None
    assert maest["syncopated_rhythm"] is True
    assert isinstance(maest["genres"], list)
    assert len(maest["genres"]) == 1
    assert maest["genres"][0]["genre_name"] == "techno"

    # --- embeddings list (summaries, no raw bytes) ---
    assert "embeddings" in result
    embeddings = result["embeddings"]
    assert isinstance(embeddings, list)
    assert len(embeddings) >= 1, "Expected at least one embedding summary"
    for emb in embeddings:
        assert "analysis_family" in emb
        assert "model_name" in emb
        assert "dim" in emb
        assert "normalization" in emb
        assert "analyzed_at" in emb
        assert "embedding_blob" not in emb, "embeddings must NOT contain raw blob bytes"
        assert isinstance(emb["dim"], int)
        assert emb["dim"] > 0

    # --- classifier_scores_detail ---
    assert "classifier_scores_detail" in result
    csd = result["classifier_scores_detail"]
    assert isinstance(csd, list)
    assert len(csd) == 1
    detail = csd[0]
    assert "probabilities" in detail
    assert isinstance(detail["probabilities"], dict), "probabilities must be a decoded dict"
    assert "live" in detail["probabilities"]
    assert abs(detail["probabilities"]["live"] - 0.87) < 1e-6
    assert detail["predicted_class"] == "live"
    assert detail["score_bucket"] == "high"
    assert "feature_set" in detail
    assert "model_id" in detail

    # --- optional_outputs ---
    assert "optional_outputs" in result
    opt = result["optional_outputs"]
    assert isinstance(opt, dict)
    assert "timeline_fields" in opt
    assert isinstance(opt["timeline_fields"], list), "timeline_fields must be a list"
    # Timeline payload was '{"beats": [...], "downbeats": [...]}' — expect those keys
    assert len(opt["timeline_fields"]) > 0, "timeline_fields must be non-empty when timeline row exists"
    for field in opt["timeline_fields"]:
        assert isinstance(field, str), f"timeline_fields entries must be strings, got {type(field)}"
    assert "beats" in opt["timeline_fields"]
    assert "downbeats" in opt["timeline_fields"]
    assert opt["sonara_embedding_available"] is True
    assert opt["audio_fingerprint_available"] is True

    # --- analysis_coverage ---
    coverage = result["analysis_coverage"]
    assert coverage["sonara_core"] is True
    assert coverage["timeline"] is True
    assert coverage["sonara_embedding"] is True
    assert coverage["fingerprint"] is True
    assert coverage["maest"] is True
    assert coverage["mert"] is True
    assert coverage["muq"] is True
    assert coverage["clap"] is True

    core.close()
    artifacts.close()


def test_track_summary_returns_none_for_missing_track() -> None:
    """assemble_track_summary_v7 returns None when track_id does not exist."""
    core = _make_core_db()
    artifacts = _make_artifacts_db()

    result = assemble_track_summary_v7(
        core_conn=core,
        artifacts_conn=artifacts,
        track_id=9999,
    )
    assert result is None, "Must return None for a non-existent track_id"

    core.close()
    artifacts.close()


def test_track_detail_returns_none_for_missing_track() -> None:
    """assemble_track_detail_v7 returns None when track_id does not exist."""
    core = _make_core_db()
    artifacts = _make_artifacts_db()

    result = assemble_track_detail_v7(
        core_conn=core,
        artifacts_conn=artifacts,
        track_id=9999,
    )
    assert result is None, "Must return None for a non-existent track_id"

    core.close()
    artifacts.close()


def test_track_summary_no_analysis_coverage_false() -> None:
    """analysis_coverage is all False when no analysis data exists for the track."""
    core = _make_core_db()
    artifacts = _make_artifacts_db()

    _insert_track(core, track_id=1)

    result = assemble_track_summary_v7(
        core_conn=core,
        artifacts_conn=artifacts,
        track_id=1,
    )
    assert result is not None
    coverage = result["analysis_coverage"]
    for key, val in coverage.items():
        assert val is False, f"Expected coverage['{key}'] = False for unanalyzed track, got {val}"

    core.close()
    artifacts.close()


def test_track_summary_liked_flag() -> None:
    """liked field reflects the likes table correctly."""
    core = _make_core_db()
    artifacts = _make_artifacts_db()

    _insert_track(core, track_id=1)

    # Not liked initially
    result = assemble_track_summary_v7(core_conn=core, artifacts_conn=artifacts, track_id=1)
    assert result is not None
    assert result["liked"] is False

    # Insert a like
    now = datetime.now(timezone.utc).isoformat()
    core.execute("INSERT INTO likes (track_id, liked_at) VALUES (?, ?)", (1, now))
    core.commit()

    result2 = assemble_track_summary_v7(core_conn=core, artifacts_conn=artifacts, track_id=1)
    assert result2 is not None
    assert result2["liked"] is True

    core.close()
    artifacts.close()
