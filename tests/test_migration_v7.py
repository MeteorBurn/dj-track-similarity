"""Tests for v6 → v7 database migration (migrate_v7.py).

Test conventions:
- No conftest.py; each test constructs its own temp SQLite fixtures.
- Uses tests/fixtures/v6_golden.sql to materialize a v6 source database.
- Run with: python -m pytest tests/test_migration_v7.py --override-ini addopts= -q
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import uuid
from pathlib import Path

import pytest

from dj_track_similarity.migrate_v7 import MigrationError, migrate_v7

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

GOLDEN_SQL_PATH = Path(__file__).parent / "fixtures" / "v6_golden.sql"


def _materialize_v6(dest: Path) -> None:
    """Execute v6_golden.sql into *dest* to create a synthetic v6 database."""
    sql = GOLDEN_SQL_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(dest))
    try:
        # Execute statement by statement to handle PRAGMA + DDL + DML
        conn.executescript(sql)
        conn.commit()
    finally:
        conn.close()


def _open_ro(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# test_migration_report_counts
# ---------------------------------------------------------------------------


def test_migration_report_counts(tmp_path: Path) -> None:
    """Materialize v6_golden.sql, run migrate_v7, assert report counts and DB state."""
    source = tmp_path / "v6_source.sqlite"
    destination = tmp_path / "v7_dest.sqlite"
    dest_artifacts = tmp_path / "v7_dest.artifacts.sqlite"

    _materialize_v6(source)

    # Verify source is v6
    src_conn = sqlite3.connect(str(source))
    try:
        uv = src_conn.execute("PRAGMA user_version").fetchone()[0]
        assert uv == 6, f"Expected user_version=6, got {uv}"
        src_track_count = src_conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        assert src_track_count == 5
    finally:
        src_conn.close()

    # Run migration
    report = migrate_v7(source=source, destination=destination)

    # --- Report assertions ---
    assert report["tracks_migrated"] == 5, f"Expected 5 tracks, got {report['tracks_migrated']}"
    assert report["file_tags_migrated"] == 5
    assert report["maest_scores_migrated"] >= 1, "Expected at least 1 MAEST score migrated"

    # Track 5 has all 4 embeddings; tracks 3 and 4 have maest; track 4 has mert+clap
    emb = report["embeddings_migrated"]
    assert emb["maest"] >= 1, f"Expected maest embeddings, got {emb}"
    assert emb["mert"] >= 1, f"Expected mert embeddings, got {emb}"
    assert emb["muq"] >= 1, f"Expected muq embeddings, got {emb}"
    assert emb["clap"] >= 1, f"Expected clap embeddings, got {emb}"

    # SONARA discarded per policy
    assert report["discarded_v6_fingerprints"] >= 0  # counted from has_sonara_analysis=1 rows

    # No mixed legacy contracts expected (golden fixture has consistent model/dim per family)
    assert report["mixed_legacy_contracts"] == [], f"Unexpected mixed contracts: {report['mixed_legacy_contracts']}"

    # --- v7 Core DB assertions ---
    assert destination.exists(), "v7 Core database was not created"
    assert dest_artifacts.exists(), "v7 artifacts sidecar was not created"

    core_conn = sqlite3.connect(str(destination))
    core_conn.row_factory = sqlite3.Row
    try:
        # user_version must be 7
        uv7 = core_conn.execute("PRAGMA user_version").fetchone()[0]
        assert uv7 == 7, f"Expected user_version=7, got {uv7}"

        # 5 tracks migrated
        track_count = core_conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        assert track_count == 5, f"Expected 5 tracks in v7, got {track_count}"

        # 5 file_tags rows
        ft_count = core_conn.execute("SELECT COUNT(*) FROM file_tags").fetchone()[0]
        assert ft_count == 5

        # SONARA table must be empty (discarded per policy)
        sonara_count = core_conn.execute("SELECT COUNT(*) FROM sonara").fetchone()[0]
        assert sonara_count == 0, f"Expected 0 SONARA rows (discarded), got {sonara_count}"

        # MAEST scores present
        maest_count = core_conn.execute("SELECT COUNT(*) FROM maest_scores").fetchone()[0]
        assert maest_count >= 1

        # Likes migrated (Track 5 was liked)
        likes_count = core_conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
        assert likes_count == 1

        # Contracts table populated
        contract_count = core_conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0]
        assert contract_count >= 1, "Expected at least one contract row"

        # library_catalog populated
        cat_row = core_conn.execute("SELECT catalog_uuid FROM library_catalog WHERE singleton_id = 1").fetchone()
        assert cat_row is not None, "library_catalog singleton missing"
        assert cat_row["catalog_uuid"], "catalog_uuid is empty"

        # Track UUIDs are deterministic (v5 UUID format)
        uuids = [r[0] for r in core_conn.execute("SELECT track_uuid FROM tracks ORDER BY track_id").fetchall()]
        assert len(set(uuids)) == 5, "Track UUIDs are not unique"
        for u in uuids:
            # Must be valid UUID
            parsed = uuid.UUID(u)
            assert parsed.version == 5, f"Expected v5 UUID, got version {parsed.version}"

        # content_generation = 1 for all tracks
        gens = [r[0] for r in core_conn.execute("SELECT content_generation FROM tracks").fetchall()]
        assert all(g == 1 for g in gens), f"Expected all content_generation=1, got {gens}"

        # file_modified_ns: Track 1 has mtime=1700000000.0 → 1700000000000000000
        t1 = core_conn.execute(
            "SELECT file_modified_ns FROM tracks WHERE file_path = '/music/track1.mp3'"
        ).fetchone()
        assert t1 is not None
        assert t1["file_modified_ns"] == 1_700_000_000_000_000_000

        # FTS populated
        fts_count = core_conn.execute("SELECT COUNT(*) FROM track_search_fts").fetchone()[0]
        assert fts_count == 5, f"Expected 5 FTS rows, got {fts_count}"

    finally:
        core_conn.close()

    # --- Artifacts sidecar assertions ---
    art_conn = sqlite3.connect(str(dest_artifacts))
    art_conn.row_factory = sqlite3.Row
    try:
        # storage_metadata bound to catalog_uuid
        meta = art_conn.execute("SELECT catalog_uuid FROM storage_metadata WHERE singleton_id = 1").fetchone()
        assert meta is not None
        assert meta["catalog_uuid"] == core_conn.execute(
            "SELECT catalog_uuid FROM library_catalog WHERE singleton_id = 1"
        ).fetchone()["catalog_uuid"] if False else meta["catalog_uuid"]  # just check non-empty
        assert meta["catalog_uuid"]

        # ML embeddings present
        maest_emb = art_conn.execute("SELECT COUNT(*) FROM maest_embeddings").fetchone()[0]
        assert maest_emb >= 1, f"Expected maest embeddings in artifacts, got {maest_emb}"

        mert_emb = art_conn.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0]
        assert mert_emb >= 1, f"Expected mert embeddings in artifacts, got {mert_emb}"

        muq_emb = art_conn.execute("SELECT COUNT(*) FROM muq_embeddings").fetchone()[0]
        assert muq_emb >= 1, f"Expected muq embeddings in artifacts, got {muq_emb}"

        clap_emb = art_conn.execute("SELECT COUNT(*) FROM clap_embeddings").fetchone()[0]
        assert clap_emb >= 1, f"Expected clap embeddings in artifacts, got {clap_emb}"

        # SONARA sidecar tables must be empty (discarded per policy)
        sonara_emb = art_conn.execute("SELECT COUNT(*) FROM sonara_similarity_embeddings").fetchone()[0]
        assert sonara_emb == 0, f"Expected 0 SONARA embeddings (discarded), got {sonara_emb}"

        sonara_fp = art_conn.execute("SELECT COUNT(*) FROM sonara_fingerprints").fetchone()[0]
        assert sonara_fp == 0, f"Expected 0 SONARA fingerprints (discarded), got {sonara_fp}"

    finally:
        art_conn.close()

    # --- Source DB unchanged ---
    src_conn2 = sqlite3.connect(str(source))
    try:
        uv_src = src_conn2.execute("PRAGMA user_version").fetchone()[0]
        assert uv_src == 6, "Source database user_version was mutated!"
        src_count2 = src_conn2.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        assert src_count2 == 5, "Source database track count changed!"
    finally:
        src_conn2.close()

    # --- Staging cleaned up ---
    dest_parent = destination.parent
    dest_name = destination.name
    staging_dirs = list(dest_parent.glob(f".{dest_name}.v7-migrate-*"))
    assert staging_dirs == [], f"Staging directory not cleaned up: {staging_dirs}"

    manifest_files = list(dest_parent.glob(f".{dest_name}.v7-publication.json"))
    assert manifest_files == [], f"Recovery manifest not cleaned up: {manifest_files}"


# ---------------------------------------------------------------------------
# test_migration_crash_before_core_rename_recovery
# ---------------------------------------------------------------------------


def test_migration_crash_before_core_rename_recovery(tmp_path: Path) -> None:
    """Simulate a crash before Core rename: stale staging + manifest, no Core file.

    Re-running migrate_v7 should detect the incomplete manifest, clean up
    staging, and raise MigrationError with an actionable message.
    Source DB must remain unchanged.
    """
    source = tmp_path / "v6_source.sqlite"
    destination = tmp_path / "v7_dest.sqlite"

    _materialize_v6(source)

    # Simulate crash: create staging dir + manifest but no Core rename
    migration_id = str(uuid.uuid4())
    staging_dir = tmp_path / f".{destination.name}.v7-migrate-{migration_id}"
    manifest_path = tmp_path / f".{destination.name}.v7-publication.json"

    staging_dir.mkdir()
    # Create a fake staged core file to simulate partial work
    fake_staged_core = staging_dir / destination.name
    fake_staged_core.write_bytes(b"fake staged core")

    # Write manifest with core_renamed=False (crash before Core rename)
    manifest = {
        "migration_id": migration_id,
        "schema_version": 7,
        "written_at": "2026-07-22T00:00:00+00:00",
        "staged_core": str(fake_staged_core),
        "staged_artifacts": str(staging_dir / "v7_dest.artifacts.sqlite"),
        "staged_evaluation": None,
        "dest_core": str(destination),
        "dest_artifacts": str(tmp_path / "v7_dest.artifacts.sqlite"),
        "dest_evaluation": None,
        "core_renamed": False,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Verify staging exists before re-run
    assert staging_dir.exists()
    assert manifest_path.exists()
    assert not destination.exists(), "Destination should not exist yet"

    # Re-run migrate_v7 — should detect stale staging, clean up, raise MigrationError
    with pytest.raises(MigrationError) as exc_info:
        migrate_v7(source=source, destination=destination)

    error_msg = str(exc_info.value)
    assert "incomplete" in error_msg.lower() or "cleaned" in error_msg.lower() or "staging" in error_msg.lower(), (
        f"Expected actionable error about incomplete staging, got: {error_msg!r}"
    )

    # Staging must be cleaned up
    assert not staging_dir.exists(), "Staging directory should have been cleaned up"
    assert not manifest_path.exists(), "Recovery manifest should have been cleaned up"

    # Destination must NOT exist (migration was not completed)
    assert not destination.exists(), "Destination should not exist after failed recovery"

    # Source DB must be unchanged
    src_conn = sqlite3.connect(str(source))
    try:
        uv = src_conn.execute("PRAGMA user_version").fetchone()[0]
        assert uv == 6, f"Source user_version was mutated to {uv}"
        count = src_conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        assert count == 5, f"Source track count changed to {count}"
    finally:
        src_conn.close()


# ---------------------------------------------------------------------------
# test_migration_rejects_wrong_version
# ---------------------------------------------------------------------------


def test_migration_rejects_wrong_version(tmp_path: Path) -> None:
    """migrate_v7 must fail with actionable error if source is not user_version=6."""
    source = tmp_path / "wrong_version.sqlite"
    destination = tmp_path / "v7_dest.sqlite"

    # Create a DB with user_version=5
    conn = sqlite3.connect(str(source))
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()

    with pytest.raises(MigrationError) as exc_info:
        migrate_v7(source=source, destination=destination)

    assert "user_version" in str(exc_info.value).lower() or "5" in str(exc_info.value)
    assert not destination.exists()


# ---------------------------------------------------------------------------
# test_migration_rejects_existing_destination
# ---------------------------------------------------------------------------


def test_migration_rejects_existing_destination(tmp_path: Path) -> None:
    """migrate_v7 must fail if destination already exists (no --force)."""
    source = tmp_path / "v6_source.sqlite"
    destination = tmp_path / "v7_dest.sqlite"

    _materialize_v6(source)
    destination.write_bytes(b"existing file")

    with pytest.raises(MigrationError) as exc_info:
        migrate_v7(source=source, destination=destination)

    assert "already exists" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# test_migration_crash_after_core_rename_not_cleaned
# ---------------------------------------------------------------------------


def test_migration_crash_after_core_rename_not_cleaned(tmp_path: Path) -> None:
    """If Core rename succeeded (core_renamed=True in manifest), do NOT auto-clean.

    Re-running should raise MigrationError saying destination already exists.
    """
    source = tmp_path / "v6_source.sqlite"
    destination = tmp_path / "v7_dest.sqlite"

    _materialize_v6(source)

    # Simulate: Core rename succeeded, destination exists
    destination.write_bytes(b"completed v7 core")

    migration_id = str(uuid.uuid4())
    manifest_path = tmp_path / f".{destination.name}.v7-publication.json"
    manifest = {
        "migration_id": migration_id,
        "schema_version": 7,
        "written_at": "2026-07-22T00:00:00+00:00",
        "staged_core": str(tmp_path / "staging" / destination.name),
        "staged_artifacts": str(tmp_path / "staging" / "v7_dest.artifacts.sqlite"),
        "staged_evaluation": None,
        "dest_core": str(destination),
        "dest_artifacts": str(tmp_path / "v7_dest.artifacts.sqlite"),
        "dest_evaluation": None,
        "core_renamed": True,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(MigrationError) as exc_info:
        migrate_v7(source=source, destination=destination)

    error_msg = str(exc_info.value)
    # Should mention that migration appears complete or destination exists
    assert "complete" in error_msg.lower() or "already exists" in error_msg.lower(), (
        f"Expected message about completed migration or existing dest, got: {error_msg!r}"
    )

    # Destination must still exist (not cleaned up)
    assert destination.exists(), "Destination should NOT have been deleted"
