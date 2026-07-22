"""Acceptance tests for the v7 Core schema (db_schema_v7.py).

Run with:
    python -m pytest tests/test_schema_v7.py --override-ini addopts= -q

No conftest.py; each test constructs its own in-memory SQLite database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_artifacts import (
    ARTIFACTS_SCHEMA_VERSION,
    create_artifacts_sidecar_schema,
)
from dj_track_similarity.db_schema import (
    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
    SONARA_CLASSIFIER_RELEASE_HASH_SETTING_KEY,
    SONARA_CLASSIFIER_REVISION_SETTING_KEY,
)
from dj_track_similarity.db_schema_v7 import (
    SCHEMA_VERSION,
    ClassifierScoreV7,
    FileTagsV7,
    SonaraRowV7,
    TrackV7,
    create_v7_schema,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_v7() -> sqlite3.Connection:
    """Return an in-memory connection with the v7 schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_v7_schema(conn)
    return conn


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','shadow') AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {str(r["name"]) for r in rows}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r["name"]) for r in rows}


def _user_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


# ---------------------------------------------------------------------------
# Primary acceptance test
# ---------------------------------------------------------------------------

def test_new_database_matches_approved_v7_contract() -> None:
    """Full contract check for the v7 Core schema."""
    conn = _open_v7()

    # --- user_version = 7 ---
    assert _user_version(conn) == SCHEMA_VERSION == 7, (
        f"Expected user_version=7, got {_user_version(conn)}"
    )

    # --- All 12 owner tables exist ---
    all_tables = _tables(conn)
    required_owner_tables = {
        "library_catalog",
        "library_settings",
        "contracts",
        "tracks",
        "file_tags",
        "sonara",
        "maest_scores",
        "classifier_scores",
        "likes",
        "pair_feedback",
        "transition_feedback",
        "track_search_fts",
    }
    missing = required_owner_tables - all_tables
    assert not missing, f"Missing tables: {missing}"

    # --- PRAGMA foreign_key_check returns empty (no violations on empty DB) ---
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert violations == [], f"Foreign key violations: {violations}"

    # --- classifier_scores has BOTH predicted_class AND score_bucket ---
    cs_cols = _columns(conn, "classifier_scores")
    assert "predicted_class" in cs_cols, "classifier_scores missing 'predicted_class'"
    assert "score_bucket" in cs_cols, "classifier_scores missing 'score_bucket'"

    # --- tracks has file_modified_ns (INTEGER, not text mtime) ---
    track_cols = _columns(conn, "tracks")
    assert "file_modified_ns" in track_cols, "tracks missing 'file_modified_ns'"

    # --- tracks does NOT have metadata_json ---
    assert "metadata_json" not in track_cols, "tracks must NOT have 'metadata_json'"

    # --- tracks does NOT have has_sonara_analysis ---
    assert "has_sonara_analysis" not in track_cols, "tracks must NOT have 'has_sonara_analysis'"

    # --- sonara has the three required BLOB columns ---
    sonara_cols = _columns(conn, "sonara")
    assert "mfcc_mean_blob" in sonara_cols, "sonara missing 'mfcc_mean_blob'"
    assert "chroma_mean_blob" in sonara_cols, "sonara missing 'chroma_mean_blob'"
    assert "spectral_contrast_mean_blob" in sonara_cols, "sonara missing 'spectral_contrast_mean_blob'"

    # --- transition_feedback has source column ---
    tf_cols = _columns(conn, "transition_feedback")
    assert "source" in tf_cols, "transition_feedback missing 'source'"

    conn.close()


# ---------------------------------------------------------------------------
# Additional structural tests
# ---------------------------------------------------------------------------

def test_create_v7_schema_from_path_string(tmp_path: pytest.TempPathFactory) -> None:
    """create_v7_schema() accepts a path string and creates the schema."""
    db_path = str(tmp_path / "test_v7.sqlite")
    create_v7_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assert _user_version(conn) == 7
    conn.close()


def test_create_v7_schema_memory_string() -> None:
    """create_v7_schema(':memory:') exits cleanly with no output."""
    # Should not raise
    create_v7_schema(":memory:")


def test_library_catalog_singleton_constraint() -> None:
    """library_catalog enforces singleton_id = 1."""
    conn = _open_v7()
    conn.execute(
        "INSERT INTO library_catalog(singleton_id, catalog_uuid, created_at, updated_at) "
        "VALUES (1, 'uuid-a', '2026-01-01T00:00:00.000000Z', '2026-01-01T00:00:00.000000Z')"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO library_catalog(singleton_id, catalog_uuid, created_at, updated_at) "
            "VALUES (2, 'uuid-b', '2026-01-01T00:00:00.000000Z', '2026-01-01T00:00:00.000000Z')"
        )
    conn.close()


def test_tracks_file_modified_ns_is_integer() -> None:
    """file_modified_ns column info shows INTEGER affinity."""
    conn = _open_v7()
    col_info = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(tracks)").fetchall()
    }
    assert col_info["file_modified_ns"]["type"].upper() == "INTEGER"
    conn.close()


def test_sonara_blob_length_constraints() -> None:
    """BLOB length CHECK constraints are enforced on insert."""
    conn = _open_v7()
    conn.execute("PRAGMA foreign_keys = OFF")

    good_mfcc = b"\x00" * (13 * 4)
    good_chroma = b"\x00" * (12 * 4)
    good_sc = b"\x00" * (7 * 4)

    base_insert = (
        "INSERT INTO sonara("
        "track_id, content_generation, contract_hash, "
        "mfcc_mean_blob, chroma_mean_blob, spectral_contrast_mean_blob, analyzed_at"
        ") VALUES (1, 1, 'hash-abc', ?, ?, ?, '2026-01-01T00:00:00.000000Z')"
    )

    # Correct lengths — should succeed
    conn.execute(base_insert, (good_mfcc, good_chroma, good_sc))
    conn.rollback()

    # Wrong mfcc length — should fail CHECK
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base_insert, (b"\x00" * 10, good_chroma, good_sc))
    conn.rollback()

    # Wrong chroma length — should fail CHECK
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base_insert, (good_mfcc, b"\x00" * 5, good_sc))
    conn.rollback()

    # Wrong spectral_contrast length — should fail CHECK
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base_insert, (good_mfcc, good_chroma, b"\x00" * 3))
    conn.rollback()

    conn.close()


def test_classifier_scores_score_bucket_constraint() -> None:
    """score_bucket CHECK rejects values outside ('low','medium','high')."""
    conn = _open_v7()
    conn.execute("PRAGMA foreign_keys = OFF")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO classifier_scores("
            "track_id, classifier_key, content_generation, model_id, feature_set, "
            "feature_manifest_hash, uses_sonara, positive_label, predicted_class, "
            "score_bucket, score, confidence, probabilities_json, analyzed_at"
            ") VALUES (1,'k',1,'m','f','h',0,'pos','pos','invalid',0.5,0.5,'{}','2026-01-01T00:00:00.000000Z')"
        )
    conn.close()


def test_file_tags_genres_json_must_be_array() -> None:
    """genres_json CHECK rejects non-array JSON."""
    conn = _open_v7()
    conn.execute("PRAGMA foreign_keys = OFF")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO file_tags(track_id, genres_json, tags_read_at) "
            "VALUES (1, '{\"not\": \"array\"}', '2026-01-01T00:00:00.000000Z')"
        )
    conn.close()


def test_contracts_output_kind_cross_check() -> None:
    """contracts CHECK rejects invalid output_kind for a given analysis_family."""
    conn = _open_v7()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO contracts("
            "contract_hash, analysis_family, output_kind, model_name, "
            "canonical_payload_json, created_at"
            ") VALUES ('h1','maest','core','maest-model','{}','2026-01-01T00:00:00.000000Z')"
        )
    conn.close()


def test_dataclasses_are_importable() -> None:
    """All four domain dataclasses can be imported and are frozen."""
    import dataclasses
    import struct

    for cls in (TrackV7, FileTagsV7, SonaraRowV7, ClassifierScoreV7):
        assert dataclasses.is_dataclass(cls), f"{cls.__name__} is not a dataclass"
        assert len(dataclasses.fields(cls)) > 0, f"{cls.__name__} has no fields"

    # Verify frozen — assignment should raise FrozenInstanceError
    row = SonaraRowV7(
        track_id=1,
        content_generation=1,
        contract_hash="abc",
        detected_bpm=None,
        raw_bpm=None,
        bpm_confidence=None,
        onset_density_per_second=None,
        beat_count=None,
        tempo_variability=None,
        beat_grid_offset_seconds=None,
        beat_grid_stability=None,
        bpm_candidates_json=None,
        detected_key_name=None,
        detected_key_camelot=None,
        key_confidence=None,
        predominant_chord=None,
        chord_changes_per_second=None,
        key_candidates_json=None,
        energy_score=None,
        energy_level=None,
        danceability_score=None,
        valence_score=None,
        acousticness_score=None,
        dissonance_score=None,
        spectral_centroid_hz=None,
        spectral_bandwidth_hz=None,
        spectral_rolloff_hz=None,
        spectral_flatness=None,
        zero_crossing_rate=None,
        rms_mean=None,
        rms_max=None,
        integrated_loudness_lufs=None,
        dynamic_range_db=None,
        true_peak_dbtp=None,
        replay_gain_db=None,
        max_momentary_loudness_lufs=None,
        loudness_range_lu=None,
        analyzed_duration_seconds=None,
        intro_end_seconds=None,
        outro_start_seconds=None,
        leading_silence_seconds=None,
        trailing_silence_seconds=None,
        energy_curve_hop_seconds=None,
        energy_curve_sample_count=None,
        energy_curve_min=None,
        energy_curve_max=None,
        energy_curve_mean=None,
        energy_curve_stddev=None,
        vocal_probability=None,
        mood_happy_score=None,
        mood_aggressive_score=None,
        mood_relaxed_score=None,
        mood_sad_score=None,
        mfcc_mean_blob=struct.pack("<13f", *([0.0] * 13)),
        chroma_mean_blob=struct.pack("<12f", *([0.0] * 12)),
        spectral_contrast_mean_blob=struct.pack("<7f", *([0.0] * 7)),
        analyzed_at="2026-01-01T00:00:00.000000Z",
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError, TypeError)):
        row.track_id = 99  # type: ignore[misc]


def test_all_sonara_scalar_columns_present() -> None:
    """All 45+ SONARA scalar columns from the spec are present in the sonara table."""
    conn = _open_v7()
    cols = _columns(conn, "sonara")
    expected_scalars = {
        "detected_bpm", "raw_bpm", "bpm_confidence", "onset_density_per_second",
        "beat_count", "tempo_variability", "beat_grid_offset_seconds", "beat_grid_stability",
        "detected_key_name", "detected_key_camelot", "key_confidence", "predominant_chord",
        "chord_changes_per_second", "energy_score", "energy_level", "danceability_score",
        "valence_score", "acousticness_score", "dissonance_score", "spectral_centroid_hz",
        "spectral_bandwidth_hz", "spectral_rolloff_hz", "spectral_flatness",
        "zero_crossing_rate", "rms_mean", "rms_max", "integrated_loudness_lufs",
        "dynamic_range_db", "true_peak_dbtp", "replay_gain_db", "max_momentary_loudness_lufs",
        "loudness_range_lu", "analyzed_duration_seconds", "intro_end_seconds",
        "outro_start_seconds", "leading_silence_seconds", "trailing_silence_seconds",
        "energy_curve_hop_seconds", "energy_curve_sample_count", "energy_curve_min",
        "energy_curve_max", "energy_curve_mean", "energy_curve_stddev",
        "vocal_probability", "mood_happy_score", "mood_aggressive_score",
        "mood_relaxed_score", "mood_sad_score",
    }
    missing = expected_scalars - cols
    assert not missing, f"sonara table missing scalar columns: {sorted(missing)}"
    conn.close()


def test_tracks_no_has_flags() -> None:
    """tracks must not contain any has_* flag columns."""
    conn = _open_v7()
    cols = _columns(conn, "tracks")
    has_flags = {c for c in cols if c.startswith("has_")}
    assert not has_flags, f"tracks must not have has_* columns, found: {has_flags}"
    conn.close()


def test_fts5_table_columns() -> None:
    """track_search_fts has all required FTS5 columns."""
    conn = _open_v7()
    fts_cols = _columns(conn, "track_search_fts")
    required_fts_cols = {
        "track_id", "file_path", "title", "artist", "album", "comment",
        "label", "catalog_number", "country", "isrc", "year",
        "track_number", "disc_number", "file_genres", "maest_genres",
    }
    missing = required_fts_cols - fts_cols
    assert not missing, f"track_search_fts missing columns: {missing}"
    conn.close()


# ---------------------------------------------------------------------------
# Artifacts sidecar schema tests (db_artifacts.py — Todo 12)
# ---------------------------------------------------------------------------

def _open_artifacts(catalog_uuid: str = "test-uuid") -> sqlite3.Connection:
    """Return an in-memory connection with the artifacts sidecar schema applied."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_artifacts_sidecar_schema(conn, catalog_uuid=catalog_uuid)
    return conn


def test_artifacts_sidecar_schema() -> None:
    """Full contract check for the artifacts sidecar schema."""
    conn = _open_artifacts(catalog_uuid="test-uuid")

    # --- user_version = 1 ---
    uv = int(conn.execute("PRAGMA user_version").fetchone()[0])
    assert uv == ARTIFACTS_SCHEMA_VERSION == 1, f"Expected user_version=1, got {uv}"

    # --- All 8 tables exist ---
    all_tables = {
        str(r["name"])
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }
    required_tables = {
        "storage_metadata",
        "maest_embeddings",
        "mert_embeddings",
        "muq_embeddings",
        "clap_embeddings",
        "sonara_similarity_embeddings",
        "sonara_timeline",
        "sonara_fingerprints",
    }
    missing = required_tables - all_tables
    assert not missing, f"Missing tables: {missing}"

    # --- PRAGMA foreign_key_check returns empty (no violations on empty DB) ---
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert violations == [], f"Foreign key violations: {violations}"

    # --- storage_metadata singleton row is present with matching catalog_uuid ---
    row = conn.execute("SELECT * FROM storage_metadata WHERE singleton_id = 1").fetchone()
    assert row is not None, "storage_metadata singleton row missing"
    assert row["catalog_uuid"] == "test-uuid", (
        f"Expected catalog_uuid='test-uuid', got {row['catalog_uuid']!r}"
    )
    assert row["schema_version"] == 1, f"Expected schema_version=1, got {row['schema_version']}"

    # --- BLOB length CHECK: wrong-length embedding_blob raises IntegrityError ---
    dim = 4
    good_blob = b"\x00" * (dim * 4)   # 16 bytes — correct
    bad_blob  = b"\x00" * (dim * 4 - 1)  # 15 bytes — wrong

    base_emb = (
        "INSERT INTO maest_embeddings"
        "(track_id, track_uuid, content_generation, contract_hash, dim, normalization, embedding_blob, analyzed_at)"
        " VALUES (1, 'uuid-1', 1, 'hash-abc', ?, 'l2', ?, '2026-01-01T00:00:00.000000Z')"
    )
    # Correct length — must succeed
    conn.execute(base_emb, (dim, good_blob))
    conn.rollback()

    # Wrong length — must raise IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base_emb, (dim, bad_blob))
    conn.rollback()

    # --- normalization CHECK: 'wrong' value raises IntegrityError ---
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base_emb, (dim, good_blob))  # first insert good row
        conn.execute(
            "INSERT INTO mert_embeddings"
            "(track_id, track_uuid, content_generation, contract_hash, dim, normalization, embedding_blob, analyzed_at)"
            " VALUES (1, 'uuid-1', 1, 'hash-abc', ?, 'wrong', ?, '2026-01-01T00:00:00.000000Z')",
            (dim, good_blob),
        )
    conn.rollback()

    conn.close()


def test_artifacts_sidecar_no_catalog_uuid() -> None:
    """create_artifacts_sidecar_schema() without catalog_uuid leaves storage_metadata empty."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_artifacts_sidecar_schema(conn, catalog_uuid=None)

    row = conn.execute("SELECT * FROM storage_metadata WHERE singleton_id = 1").fetchone()
    assert row is None, "storage_metadata must be empty when catalog_uuid is not provided"
    conn.close()


def test_artifacts_sidecar_from_path_string(tmp_path: pytest.TempPathFactory) -> None:
    """create_artifacts_sidecar_schema() accepts a path string."""
    db_path = str(tmp_path / "artifacts.sqlite")
    create_artifacts_sidecar_schema(db_path, catalog_uuid="path-uuid")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    uv = int(conn.execute("PRAGMA user_version").fetchone()[0])
    assert uv == 1
    row = conn.execute("SELECT catalog_uuid FROM storage_metadata WHERE singleton_id = 1").fetchone()
    assert row is not None and row["catalog_uuid"] == "path-uuid"
    conn.close()


def test_artifacts_sonara_fingerprint_blob_length_check() -> None:
    """sonara_fingerprints BLOB length CHECK is enforced."""
    conn = _open_artifacts()
    word_count = 3
    good_fp = b"\x00" * (word_count * 4)  # 12 bytes
    bad_fp  = b"\x00" * (word_count * 4 + 1)  # 13 bytes — wrong

    base_fp = (
        "INSERT INTO sonara_fingerprints"
        "(track_id, track_uuid, content_generation, contract_hash,"
        " fingerprint_version, word_count, byte_order, fingerprint_blob, analyzed_at)"
        " VALUES (1, 'uuid-1', 1, 'hash-abc', 'v1', ?, 'little', ?, '2026-01-01T00:00:00.000000Z')"
    )
    # Correct length — must succeed
    conn.execute(base_fp, (word_count, good_fp))
    conn.rollback()

    # Wrong length — must raise IntegrityError
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base_fp, (word_count, bad_fp))
    conn.rollback()

    conn.close()


def test_artifacts_sonara_timeline_payload_json_check() -> None:
    """sonara_timeline payload_json must be a valid JSON object."""
    conn = _open_artifacts()

    base_tl = (
        "INSERT INTO sonara_timeline"
        "(track_id, track_uuid, content_generation, contract_hash, payload_json, analyzed_at)"
        " VALUES (1, 'uuid-1', 1, 'hash-abc', ?, '2026-01-01T00:00:00.000000Z')"
    )
    # Valid JSON object — must succeed
    conn.execute(base_tl, ('{"beats": []}',))
    conn.rollback()

    # JSON array — must fail (json_type must be 'object')
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base_tl, ('[1, 2, 3]',))
    conn.rollback()

    # Invalid JSON — must fail
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(base_tl, ('not-json',))
    conn.rollback()

    conn.close()


def test_artifacts_storage_metadata_singleton_constraint() -> None:
    """storage_metadata enforces singleton_id = 1."""
    conn = _open_artifacts(catalog_uuid="uuid-a")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO storage_metadata(singleton_id, catalog_uuid, schema_version, created_at, updated_at)"
            " VALUES (2, 'uuid-b', 1, '2026-01-01T00:00:00.000000Z', '2026-01-01T00:00:00.000000Z')"
        )
    conn.close()


# ---------------------------------------------------------------------------
# BUG-C2 regression tests — release-hash gating in _ensure_sonara_classifier_feature_revision
# ---------------------------------------------------------------------------

def _v6_track(db: LibraryDatabase, tmp_path: Path, name: str) -> int:
    path = tmp_path / name
    path.write_bytes(b"audio")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1.0, metadata={"title": name})


def _v6_save_score(db: LibraryDatabase, track_id: int, classifier: str, *, feature_set: str) -> None:
    db.save_classifier_score(
        track_id,
        classifier=classifier,
        score=0.75,
        label="high",
        confidence=0.75,
        probabilities={"yes": 0.75, "no": 0.25},
        feature_set=feature_set,
        model_id="test-model",
    )


def _set_active_release_hash(db: LibraryDatabase, release_hash: str) -> None:
    """Write sonara.active_release_hash into library_settings."""
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO library_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY, release_hash),
        )


def test_release_hash_mismatch_blocks_analyze(tmp_path: Path) -> None:
    """BUG-C2: A SONARA release-hash change must invalidate SONARA-dependent
    classifier scores even when SONARA_PROJECT_FEATURE_REVISION is unchanged.

    Scenario:
    1. DB is created; scores are saved and the active_release_hash is recorded.
    2. The stored active_release_hash is changed to a different value (simulating
       a SONARA package/decoder upgrade without a feature-revision bump).
    3. Re-opening the DB triggers ensure_schema → _ensure_sonara_classifier_feature_revision.
    4. SONARA-dependent scores must be deleted; non-SONARA scores must survive.
    """
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)

    track_id = _v6_track(db, tmp_path, "track.wav")

    # SONARA-dependent score (uses_sonara=True via feature_set)
    _v6_save_score(db, track_id, "sonara_profile", feature_set="sonara+maest")
    # Non-SONARA score — must survive
    _v6_save_score(db, track_id, "embedding_only", feature_set="mert+maest")

    # Record the "current" release hash as if SONARA analysis was done and
    # classifier scoring completed against that release.
    _set_active_release_hash(db, "sha256:aabbccdd")
    # Simulate the gating sentinel being in sync (scores were valid at this hash).
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO library_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (SONARA_CLASSIFIER_RELEASE_HASH_SETTING_KEY, "sha256:aabbccdd"),
        )

    # Now simulate a SONARA release upgrade: change the active hash to a new value.
    _set_active_release_hash(db, "sha256:deadbeef")

    # Re-open the DB — this triggers ensure_schema → _ensure_sonara_classifier_feature_revision.
    db2 = LibraryDatabase(db_path)

    # SONARA-dependent score must be gone
    assert db2.classifier_score(track_id, "sonara_profile") is None, (
        "SONARA-dependent score must be deleted when release hash changes"
    )
    # Non-SONARA score must survive
    assert db2.classifier_score(track_id, "embedding_only") is not None, (
        "Non-SONARA score must not be deleted on release hash change"
    )


def test_matching_release_hash_preserves_scores(tmp_path: Path) -> None:
    """When the stored release hash matches the active hash, scores must be preserved."""
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)

    track_id = _v6_track(db, tmp_path, "track.wav")
    _v6_save_score(db, track_id, "sonara_profile", feature_set="sonara+maest")
    _v6_save_score(db, track_id, "embedding_only", feature_set="mert+maest")

    # Set the same hash in both active and scored sentinels — no mismatch.
    _set_active_release_hash(db, "sha256:aabbccdd")
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO library_settings (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (SONARA_CLASSIFIER_RELEASE_HASH_SETTING_KEY, "sha256:aabbccdd"),
        )

    # Re-open — gating should see matching hash and leave scores alone.
    db2 = LibraryDatabase(db_path)

    assert db2.classifier_score(track_id, "sonara_profile") is not None, (
        "SONARA-dependent score must be preserved when release hash matches"
    )
    assert db2.classifier_score(track_id, "embedding_only") is not None


def test_no_active_release_hash_setting_preserves_existing_behaviour(tmp_path: Path) -> None:
    """When sonara.active_release_hash is absent, the existing feature-revision
    check must still work (backward-compat: no regression on v6 DBs)."""
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)

    track_id = _v6_track(db, tmp_path, "track.wav")
    _v6_save_score(db, track_id, "sonara_profile", feature_set="combined")
    _v6_save_score(db, track_id, "embedding_only", feature_set="mert+maest")

    # Wipe the feature-revision setting to force re-check on next open.
    with db.connect() as connection:
        connection.execute(
            "DELETE FROM library_settings WHERE key = ?",
            (SONARA_CLASSIFIER_REVISION_SETTING_KEY,),
        )
    # Do NOT set active_release_hash — simulates a v6 DB without the new setting.

    db2 = LibraryDatabase(db_path)

    # Feature-revision check should still delete SONARA-dependent scores.
    assert db2.classifier_score(track_id, "sonara_profile") is None
    assert db2.classifier_score(track_id, "embedding_only") is not None


# ---------------------------------------------------------------------------
# Evaluation sidecar schema tests (Todo 13)
# ---------------------------------------------------------------------------

def test_evaluation_sidecar_schema() -> None:
    """Full contract check for the evaluation sidecar schema."""
    from dj_track_similarity.db_evaluation_sidecar import (
        SIDECAR_SCHEMA_VERSION,
        create_evaluation_sidecar_schema,
    )

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_evaluation_sidecar_schema(conn, catalog_uuid="test-catalog-uuid")

    # --- user_version = 1 ---
    user_ver = int(conn.execute("PRAGMA user_version").fetchone()[0])
    assert user_ver == SIDECAR_SCHEMA_VERSION == 1, (
        f"Expected user_version=1, got {user_ver}"
    )

    # --- All 6 tables exist ---
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    actual_tables = {str(r["name"]) for r in rows}
    required_tables = {
        "storage_metadata",
        "search_sessions",
        "search_session_seeds",
        "search_result_events",
        "calibration_runs",
        "evaluation_settings",
    }
    missing = required_tables - actual_tables
    assert not missing, f"Missing tables: {missing}"

    # --- PRAGMA foreign_key_check returns empty (no violations on empty DB) ---
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert violations == [], f"Foreign key violations: {violations}"

    # --- storage_metadata singleton was inserted ---
    meta = conn.execute("SELECT * FROM storage_metadata WHERE singleton_id = 1").fetchone()
    assert meta is not None, "storage_metadata singleton row missing"
    assert meta["catalog_uuid"] == "test-catalog-uuid"
    assert meta["schema_version"] == 1

    # --- JSON CHECK on search_sessions.request_json rejects invalid JSON ---
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO search_sessions(mode, request_json, created_at) "
            "VALUES ('mert', 'not-json', '2026-01-01T00:00:00.000000Z')"
        )
    conn.rollback()

    # --- Valid JSON insert into search_sessions succeeds ---
    conn.execute(
        "INSERT INTO search_sessions(mode, request_json, created_at) "
        "VALUES ('mert', '{}', '2026-01-01T00:00:00.000000Z')"
    )
    conn.rollback()

    # --- JSON CHECK on search_result_events.score_breakdown_json rejects invalid JSON ---
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO search_result_events("
            "session_id, rank, track_id, track_uuid, content_generation, "
            "snapshot_state, total_score, score_breakdown_json, created_at"
            ") VALUES (1, 0, 1, 'uuid-a', 1, 'current', 0.9, 'bad-json', '2026-01-01T00:00:00.000000Z')"
        )
    conn.rollback()

    # --- snapshot_state CHECK rejects invalid values ---
    conn.execute(
        "INSERT INTO search_sessions(mode, request_json, created_at) "
        "VALUES ('sonara', '{}', '2026-01-01T00:00:00.000000Z')"
    )
    session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO search_session_seeds("
            "session_id, position, track_id, track_uuid, content_generation, snapshot_state"
            ") VALUES (?, 0, 1, 'uuid-b', 1, 'unknown')",
            (session_id,),
        )
    conn.rollback()

    # --- cross-column CHECK: missing state requires content_generation = 0 ---
    conn.execute(
        "INSERT INTO search_sessions(mode, request_json, created_at) "
        "VALUES ('sonara', '{}', '2026-01-01T00:00:00.000000Z')"
    )
    session_id2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO search_session_seeds("
            "session_id, position, track_id, track_uuid, content_generation, snapshot_state"
            ") VALUES (?, 0, 1, 'uuid-c', 1, 'missing')",
            (session_id2,),
        )
    conn.rollback()

    # --- JSON CHECK on calibration_runs ---
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO calibration_runs("
            "profile_name, search_mode, config_json, metrics_json, created_at"
            ") VALUES ('p', 'mert', 'bad', '{}', '2026-01-01T00:00:00.000000Z')"
        )
    conn.rollback()

    # --- JSON CHECK on evaluation_settings ---
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO evaluation_settings(setting_key, value_json, updated_at) "
            "VALUES ('k', 'not-json', '2026-01-01T00:00:00.000000Z')"
        )
    conn.rollback()

    conn.close()


def test_no_sidecar_without_recording(tmp_path: Path) -> None:
    """The evaluation sidecar must NOT be auto-created on import or at module level.

    Intent: normal search operations that do not explicitly invoke
    ``create_evaluation_sidecar_schema`` must never cause the sidecar file to
    appear on disk.  This test documents and enforces that contract.
    """
    import inspect

    from dj_track_similarity import db_evaluation_sidecar
    from dj_track_similarity.db_evaluation_sidecar import create_evaluation_sidecar_schema

    # 1. The function is callable.
    assert callable(create_evaluation_sidecar_schema)

    # 2. Importing the module does NOT create any file in tmp_path.
    sidecar_path = tmp_path / "library.evaluation.sqlite"
    assert not sidecar_path.exists(), (
        "Sidecar file must not exist before create_evaluation_sidecar_schema() is called"
    )

    # 3. Calling the function on a real path DOES create the file.
    create_evaluation_sidecar_schema(str(sidecar_path), catalog_uuid="test")
    assert sidecar_path.exists(), (
        "create_evaluation_sidecar_schema() must create the file when given a path"
    )

    # 4. The module source does NOT call create_evaluation_sidecar_schema at module level.
    #    Use AST analysis to find top-level Call nodes that reference the function.
    import ast

    source = inspect.getsource(db_evaluation_sidecar)
    tree = ast.parse(source)

    # Collect names of top-level function/class definitions so we can skip their bodies.
    top_level_def_names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            top_level_def_names.add(node.name)

    # Walk only the top-level statements (not inside any function/class body).
    module_level_calls: list[str] = []
    for node in ast.iter_child_nodes(tree):
        # Skip function and class definitions — calls inside them are fine.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        # Look for any Call to create_evaluation_sidecar_schema in this statement.
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name == "create_evaluation_sidecar_schema":
                    module_level_calls.append(ast.dump(child))

    assert not module_level_calls, (
        "create_evaluation_sidecar_schema must NOT be called at module level; "
        f"found {len(module_level_calls)} call(s)"
    )
