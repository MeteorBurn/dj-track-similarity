"""Tests for the prepare-sonara-release command and protocol.

Run with:
    python -m pytest tests/test_prepare_sonara_release.py --override-ini addopts= -q

No conftest.py; each test constructs its own temp SQLite database.
"""

from __future__ import annotations

import json
import sqlite3
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dj_track_similarity.db_schema_v7 import create_v7_schema
from dj_track_similarity.prepare_sonara_release import (
    ACTIVE_RELEASE_HASH_KEY,
    CONFIRM_STRING,
    RECEIPT_KEY,
    LockHeldError,
    PrepareSonaraReleaseError,
    prepare_sonara_release,
    validate_backup_dir,
    validate_confirm,
    validate_sonara_outputs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_blobs() -> tuple[bytes, bytes, bytes]:
    """Return minimal valid BLOB values for the sonara table."""
    mfcc = struct.pack("<13f", *([0.0] * 13))       # 52 bytes
    chroma = struct.pack("<12f", *([0.0] * 12))     # 48 bytes
    contrast = struct.pack("<7f", *([0.0] * 7))     # 28 bytes
    return mfcc, chroma, contrast


def _open_v7(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    create_v7_schema(conn)
    return conn


def _insert_track(conn: sqlite3.Connection, track_id: int, uuid: str, path: str) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO tracks(
            track_id, track_uuid, file_path, file_size_bytes, file_modified_ns,
            content_generation, last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, 1000, 1000000, 1, ?, ?, ?)
        """,
        (track_id, uuid, path, now, now, now),
    )


def _insert_contract(conn: sqlite3.Connection, contract_hash: str) -> None:
    now = _now()
    conn.execute(
        """
        INSERT OR IGNORE INTO contracts(
            contract_hash, analysis_family, output_kind, model_name,
            release_hash, canonical_payload_json, created_at
        ) VALUES (?, 'sonara', 'core', 'sonara', ?, '{}', ?)
        """,
        (contract_hash, "sha256:releasehash", now),
    )


def _insert_sonara_row(conn: sqlite3.Connection, track_id: int, contract_hash: str) -> None:
    mfcc, chroma, contrast = _make_blobs()
    now = _now()
    conn.execute(
        """
        INSERT INTO sonara(
            track_id, content_generation, contract_hash,
            mfcc_mean_blob, chroma_mean_blob, spectral_contrast_mean_blob,
            analyzed_at
        ) VALUES (?, 1, ?, ?, ?, ?, ?)
        """,
        (track_id, contract_hash, mfcc, chroma, contrast, now),
    )


def _insert_maest_row(conn: sqlite3.Connection, track_id: int, contract_hash: str) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO maest_scores(
            track_id, content_generation, contract_hash,
            genres_json, analyzed_at
        ) VALUES (?, 1, ?, '[]', ?)
        """,
        (track_id, contract_hash, now),
    )


def _insert_classifier_score(
    conn: sqlite3.Connection,
    track_id: int,
    classifier_key: str,
    uses_sonara: int,
    sonara_release_hash: str | None,
) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO classifier_scores(
            track_id, classifier_key, content_generation, model_id,
            feature_set, feature_manifest_hash,
            uses_sonara, sonara_release_hash,
            positive_label, predicted_class, score_bucket,
            score, confidence, probabilities_json, analyzed_at
        ) VALUES (?, ?, 1, 'model_v1', 'features', 'hash123',
                  ?, ?,
                  'positive', 'positive', 'high',
                  0.9, 0.8, '{}', ?)
        """,
        (track_id, classifier_key, uses_sonara, sonara_release_hash, now),
    )


def _set_library_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO library_settings(setting_key, setting_value, updated_at)
        VALUES(?, ?, ?)
        ON CONFLICT(setting_key) DO UPDATE SET
            setting_value = excluded.setting_value,
            updated_at    = excluded.updated_at
        """,
        (key, value, now),
    )


def _get_library_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT setting_value FROM library_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    return row[0] if row else None


def _insert_maest_contract(conn: sqlite3.Connection, contract_hash: str) -> None:
    now = _now()
    conn.execute(
        """
        INSERT OR IGNORE INTO contracts(
            contract_hash, analysis_family, output_kind, model_name,
            release_hash, canonical_payload_json, created_at
        ) VALUES (?, 'maest', 'analysis', 'maest', NULL, '{}', ?)
        """,
        (contract_hash, now),
    )


# ---------------------------------------------------------------------------
# test_prepare_clears_only_sonara_rows
# ---------------------------------------------------------------------------

def test_prepare_clears_only_sonara_rows(tmp_path: Path) -> None:
    """Happy-path: sonara rows cleared, maest_scores and uses_sonara=0 classifier retained."""
    db_file = tmp_path / "library.sqlite"
    backup_dir = tmp_path / "bak"
    backup_dir.mkdir()

    OLD_HASH = "sha256:oldhash"
    NEW_HASH = "sha256:newhash"
    SONARA_CONTRACT = "sha256:sonara_contract_abc"
    MAEST_CONTRACT = "sha256:maest_contract_abc"

    conn = _open_v7(str(db_file))

    # Insert contracts
    _insert_contract(conn, SONARA_CONTRACT)
    _insert_maest_contract(conn, MAEST_CONTRACT)

    # Insert 2 tracks
    _insert_track(conn, 1, "uuid-1", "/music/track1.mp3")
    _insert_track(conn, 2, "uuid-2", "/music/track2.mp3")

    # Insert 2 sonara rows
    _insert_sonara_row(conn, 1, SONARA_CONTRACT)
    _insert_sonara_row(conn, 2, SONARA_CONTRACT)

    # Insert 2 maest_scores rows
    _insert_maest_row(conn, 1, MAEST_CONTRACT)
    _insert_maest_row(conn, 2, MAEST_CONTRACT)

    # Insert 2 classifier_scores: one uses_sonara=1, one uses_sonara=0
    _insert_classifier_score(conn, 1, "sonara_classifier", 1, OLD_HASH)
    _insert_classifier_score(conn, 2, "ml_only_classifier", 0, None)

    # Set active release hash
    _set_library_setting(conn, ACTIVE_RELEASE_HASH_KEY, OLD_HASH)

    conn.commit()
    conn.close()

    # Run prepare
    receipt = prepare_sonara_release(
        db_path=db_file,
        backup_dir=backup_dir,
        sonara_outputs=["core", "timeline", "embedding", "fingerprint"],
        new_release_hash=NEW_HASH,
    )

    # Verify receipt
    assert receipt["step"] == 7
    assert receipt["new_release_hash"] == NEW_HASH
    assert "finalized_at" in receipt

    # Verify DB state
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row

    # sonara table must be empty
    sonara_count = conn.execute("SELECT COUNT(*) FROM sonara").fetchone()[0]
    assert sonara_count == 0, f"Expected sonara empty, got {sonara_count} rows"

    # maest_scores must be untouched (2 rows)
    maest_count = conn.execute("SELECT COUNT(*) FROM maest_scores").fetchone()[0]
    assert maest_count == 2, f"Expected 2 maest_scores rows, got {maest_count}"

    # classifier_scores: uses_sonara=1 row deleted, uses_sonara=0 row retained
    cs_rows = conn.execute(
        "SELECT classifier_key, uses_sonara FROM classifier_scores ORDER BY classifier_key"
    ).fetchall()
    assert len(cs_rows) == 1, f"Expected 1 classifier_scores row, got {len(cs_rows)}"
    assert cs_rows[0]["classifier_key"] == "ml_only_classifier"
    assert cs_rows[0]["uses_sonara"] == 0

    # active release hash updated
    active_hash = _get_library_setting(conn, ACTIVE_RELEASE_HASH_KEY)
    assert active_hash == NEW_HASH, f"Expected {NEW_HASH}, got {active_hash}"

    # receipt deleted
    receipt_val = _get_library_setting(conn, RECEIPT_KEY)
    assert receipt_val is None, f"Expected receipt deleted, got {receipt_val!r}"

    conn.close()

    # Backup must exist
    assert (backup_dir / "library.sqlite.bak").exists(), "Core backup not found"


# ---------------------------------------------------------------------------
# test_crash_resume
# ---------------------------------------------------------------------------

def test_crash_resume(tmp_path: Path) -> None:
    """Crash-resume: if receipt exists at step 4, resume from step 5 and complete."""
    db_file = tmp_path / "library.sqlite"
    backup_dir = tmp_path / "bak"
    backup_dir.mkdir()

    OLD_HASH = "sha256:oldhash"
    NEW_HASH = "sha256:newhash"
    SONARA_CONTRACT = "sha256:sonara_contract_xyz"
    MAEST_CONTRACT = "sha256:maest_contract_xyz"

    conn = _open_v7(str(db_file))

    _insert_contract(conn, SONARA_CONTRACT)
    _insert_maest_contract(conn, MAEST_CONTRACT)

    _insert_track(conn, 1, "uuid-1", "/music/track1.mp3")
    _insert_track(conn, 2, "uuid-2", "/music/track2.mp3")

    _insert_sonara_row(conn, 1, SONARA_CONTRACT)
    _insert_sonara_row(conn, 2, SONARA_CONTRACT)

    _insert_maest_row(conn, 1, MAEST_CONTRACT)
    _insert_maest_row(conn, 2, MAEST_CONTRACT)

    _insert_classifier_score(conn, 1, "sonara_classifier", 1, OLD_HASH)
    _insert_classifier_score(conn, 2, "ml_only_classifier", 0, None)

    _set_library_setting(conn, ACTIVE_RELEASE_HASH_KEY, OLD_HASH)

    # Simulate crash after step 4: write a receipt with step=4
    # (sidecars were cleared, but Core transaction not yet done)
    crash_receipt = {
        "step": 4,
        "started_at": _now(),
        "previous_release_hash": OLD_HASH,
        "new_release_hash": NEW_HASH,
    }
    _set_library_setting(conn, RECEIPT_KEY, json.dumps(crash_receipt))

    conn.commit()
    conn.close()

    # Also write a fake backup so step 2 is considered done (step=4 > 2)
    (backup_dir / "library.sqlite.bak").write_bytes(b"fake_backup")

    # Run prepare — should detect receipt and resume from step 5
    receipt = prepare_sonara_release(
        db_path=db_file,
        backup_dir=backup_dir,
        sonara_outputs=["core", "timeline", "embedding", "fingerprint"],
        new_release_hash=NEW_HASH,
    )

    # Verify receipt
    assert receipt["step"] == 7
    assert receipt["new_release_hash"] == NEW_HASH
    assert "finalized_at" in receipt

    # Verify DB state — same final state as happy path
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row

    sonara_count = conn.execute("SELECT COUNT(*) FROM sonara").fetchone()[0]
    assert sonara_count == 0, f"Expected sonara empty after resume, got {sonara_count}"

    maest_count = conn.execute("SELECT COUNT(*) FROM maest_scores").fetchone()[0]
    assert maest_count == 2, f"Expected 2 maest_scores rows after resume, got {maest_count}"

    cs_rows = conn.execute(
        "SELECT classifier_key, uses_sonara FROM classifier_scores ORDER BY classifier_key"
    ).fetchall()
    assert len(cs_rows) == 1, f"Expected 1 classifier_scores row after resume, got {len(cs_rows)}"
    assert cs_rows[0]["classifier_key"] == "ml_only_classifier"

    active_hash = _get_library_setting(conn, ACTIVE_RELEASE_HASH_KEY)
    assert active_hash == NEW_HASH

    receipt_val = _get_library_setting(conn, RECEIPT_KEY)
    assert receipt_val is None, "Receipt should be deleted after successful resume"

    conn.close()


# ---------------------------------------------------------------------------
# Validation unit tests
# ---------------------------------------------------------------------------

def test_validate_confirm_ok() -> None:
    validate_confirm(CONFIRM_STRING)  # must not raise


def test_validate_confirm_wrong() -> None:
    with pytest.raises(ValueError, match="PREPARE SONARA RELEASE"):
        validate_confirm("wrong string")


def test_validate_sonara_outputs_ok() -> None:
    validate_sonara_outputs(["core", "timeline", "embedding", "fingerprint"])


def test_validate_sonara_outputs_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        validate_sonara_outputs(["core", "bogus"])


def test_validate_backup_dir_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent"
    with pytest.raises(ValueError, match="does not exist"):
        validate_backup_dir(missing)
