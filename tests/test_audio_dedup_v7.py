"""Tests for v7 artifacts sidecar fingerprint read helpers in audio_dedup_jobs.

Covers:
  - read_v7_fingerprint()  — single-row lookup, missing-row None return
  - list_v7_fingerprint_pairs()  — full-table iteration filtered by contract_hash
  - apply-mode confirmation guard (APPLY DELETE) still enforced by AudioDedupJobManager

No conftest.py; each test constructs its own temp SQLite.
Run with:
    python -m pytest tests/test_audio_dedup_v7.py --override-ini addopts= -q
"""
from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

import pytest

from dj_track_similarity.audio_dedup_jobs import (
    APPLY_CONFIRMATION,
    AudioDedupJobManager,
    list_v7_fingerprint_pairs,
    read_v7_fingerprint,
)
from dj_track_similarity.database import LibraryDatabase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CONTRACT_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_CONTRACT_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def _make_blob(words: list[int]) -> bytes:
    """Pack a list of uint32 values as little-endian bytes."""
    return struct.pack(f"<{len(words)}I", *words)


def _create_artifacts_sidecar(path: Path) -> sqlite3.Connection:
    """Create a minimal v7 artifacts sidecar with the sonara_fingerprints table."""
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        PRAGMA journal_mode = WAL;
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
        CREATE INDEX idx_sonara_fingerprints_contract_generation
            ON sonara_fingerprints(contract_hash, content_generation, track_id);
        """
    )
    return conn


def _insert_fingerprint(
    conn: sqlite3.Connection,
    *,
    track_id: int,
    words: list[int],
    contract_hash: str = _CONTRACT_A,
    track_uuid: str | None = None,
    content_generation: int = 1,
    fingerprint_version: str = "v1",
) -> bytes:
    blob = _make_blob(words)
    conn.execute(
        """
        INSERT INTO sonara_fingerprints(
            track_id, track_uuid, content_generation, contract_hash,
            fingerprint_version, word_count, byte_order, fingerprint_blob, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'little', ?, '2026-07-22T00:00:00Z')
        """,
        (
            track_id,
            track_uuid or f"uuid-{track_id}",
            content_generation,
            contract_hash,
            fingerprint_version,
            len(words),
            blob,
        ),
    )
    conn.commit()
    return blob


def _create_library_db(path: Path) -> LibraryDatabase:
    """Create a full library DB via LibraryDatabase (creates proper schema)."""
    return LibraryDatabase(path)


# ---------------------------------------------------------------------------
# test_v7_fingerprint_read
# ---------------------------------------------------------------------------


def test_v7_fingerprint_read(tmp_path: Path) -> None:
    """read_v7_fingerprint returns bytes for existing rows, None for missing."""
    artifacts_path = tmp_path / "library.artifacts.sqlite"
    conn = _create_artifacts_sidecar(artifacts_path)

    # Insert 3 tracks with distinct fingerprint blobs
    blob1 = _insert_fingerprint(conn, track_id=1, words=[0xDEAD, 0xBEEF, 0xCAFE])
    blob2 = _insert_fingerprint(conn, track_id=2, words=[0x0001, 0x0002])
    blob3 = _insert_fingerprint(conn, track_id=3, words=[0xFFFF, 0x1234, 0x5678, 0xABCD])

    # --- read_v7_fingerprint: existing rows ---
    result1 = read_v7_fingerprint(conn, track_id=1)
    assert result1 is not None
    assert isinstance(result1, bytes)
    assert result1 == blob1

    result2 = read_v7_fingerprint(conn, track_id=2)
    assert result2 == blob2

    result3 = read_v7_fingerprint(conn, track_id=3)
    assert result3 == blob3

    # --- read_v7_fingerprint: missing row returns None ---
    assert read_v7_fingerprint(conn, track_id=99) is None
    assert read_v7_fingerprint(conn, track_id=0) is None

    # --- list_v7_fingerprint_pairs: all 3 rows under CONTRACT_A ---
    pairs = list(list_v7_fingerprint_pairs(conn, _CONTRACT_A))
    assert len(pairs) == 3
    assert pairs[0] == (1, blob1)
    assert pairs[1] == (2, blob2)
    assert pairs[2] == (3, blob3)

    conn.close()


def test_list_v7_fingerprint_pairs_filters_by_contract_hash(tmp_path: Path) -> None:
    """list_v7_fingerprint_pairs only yields rows matching the given contract_hash."""
    artifacts_path = tmp_path / "library.artifacts.sqlite"
    conn = _create_artifacts_sidecar(artifacts_path)

    blob_a1 = _insert_fingerprint(conn, track_id=1, words=[0x0001], contract_hash=_CONTRACT_A)
    blob_a2 = _insert_fingerprint(conn, track_id=2, words=[0x0002], contract_hash=_CONTRACT_A)
    _insert_fingerprint(conn, track_id=3, words=[0x0003], contract_hash=_CONTRACT_B)

    pairs_a = list(list_v7_fingerprint_pairs(conn, _CONTRACT_A))
    pairs_b = list(list_v7_fingerprint_pairs(conn, _CONTRACT_B))
    pairs_none = list(list_v7_fingerprint_pairs(conn, "sha256:nonexistent"))

    assert len(pairs_a) == 2
    assert pairs_a[0] == (1, blob_a1)
    assert pairs_a[1] == (2, blob_a2)

    assert len(pairs_b) == 1
    assert pairs_b[0][0] == 3

    assert pairs_none == []

    conn.close()


def test_list_v7_fingerprint_pairs_empty_table(tmp_path: Path) -> None:
    """list_v7_fingerprint_pairs on an empty table yields nothing."""
    artifacts_path = tmp_path / "library.artifacts.sqlite"
    conn = _create_artifacts_sidecar(artifacts_path)

    pairs = list(list_v7_fingerprint_pairs(conn, _CONTRACT_A))
    assert pairs == []

    conn.close()


def test_v7_fingerprint_blob_round_trips_as_uint32_le(tmp_path: Path) -> None:
    """Blob stored as little-endian uint32 words round-trips correctly."""
    import struct

    artifacts_path = tmp_path / "library.artifacts.sqlite"
    conn = _create_artifacts_sidecar(artifacts_path)

    words = [0x00000001, 0xDEADBEEF, 0xCAFEBABE, 0xFFFFFFFF]
    blob = _insert_fingerprint(conn, track_id=10, words=words)

    result = read_v7_fingerprint(conn, track_id=10)
    assert result is not None
    unpacked = list(struct.unpack(f"<{len(words)}I", result))
    assert unpacked == words

    conn.close()


# ---------------------------------------------------------------------------
# test_v7_dedup_apply_requires_exact_confirmation
# ---------------------------------------------------------------------------


def test_v7_dedup_apply_requires_exact_confirmation(tmp_path: Path) -> None:
    """AudioDedupJobManager.create_job() rejects apply=True without exact APPLY DELETE."""
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    db = LibraryDatabase(db_path)
    manager = AudioDedupJobManager(db)
    root = tmp_path / "music"
    root.mkdir()

    # Wrong confirmation strings must raise ValueError
    wrong_strings = [
        None,
        "",
        "apply delete",          # lowercase
        "APPLY DELETE ",         # trailing space
        " APPLY DELETE",         # leading space
        "APPLY  DELETE",         # double space
        "DELETE",
        "APPLY",
        "apply",
    ]
    for bad_confirmation in wrong_strings:
        with pytest.raises(ValueError, match="APPLY DELETE"):
            manager.create_job(
                root=root,
                apply=True,
                confirmation=bad_confirmation,
            )

    # Correct confirmation must NOT raise
    job_id = manager.create_job(
        root=root,
        apply=True,
        confirmation=APPLY_CONFIRMATION,
    )
    assert job_id  # a UUID string was returned


def test_v7_dedup_apply_confirmation_not_required_for_dry_run(tmp_path: Path) -> None:
    """create_job() with apply=False does not require any confirmation string."""
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    db = LibraryDatabase(db_path)
    manager = AudioDedupJobManager(db)
    root = tmp_path / "music"
    root.mkdir()

    # No confirmation needed for dry-run (apply=False is the default)
    job_id = manager.create_job(root=root, apply=False)
    assert job_id

    job_id2 = manager.create_job(root=root)  # apply defaults to False
    assert job_id2


def test_apply_confirmation_constant_is_exact_string() -> None:
    """APPLY_CONFIRMATION sentinel must be exactly 'APPLY DELETE' — never change it."""
    assert APPLY_CONFIRMATION == "APPLY DELETE"
