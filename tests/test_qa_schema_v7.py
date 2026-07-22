"""Tests for scripts/qa_schema_v7.py — end-to-end QA harness.

Test conventions:
- No conftest.py; each test constructs its own temp SQLite fixtures.
- Run with: python -m pytest tests/test_qa_schema_v7.py --override-ini addopts= -q
"""

from __future__ import annotations

import json
import sqlite3
import struct
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the QA harness module
# ---------------------------------------------------------------------------

# Add scripts/ to sys.path so we can import qa_schema_v7 directly
_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import qa_schema_v7  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _make_blob(n_floats: int, value: float = 0.5) -> bytes:
    """Create a float32-le blob of n_floats all set to value."""
    return struct.pack(f"<{n_floats}f", *([value] * n_floats))


def _build_healthy_core(path: Path, catalog_uuid: str) -> None:
    """Create a healthy v7 Core database with one track, one contract, one sonara row,
    one classifier_scores row, and a populated FTS index."""
    from dj_track_similarity.db_schema_v7 import create_v7_schema

    create_v7_schema(str(path))

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys = ON")
    now = _now()

    # library_catalog singleton
    conn.execute(
        "INSERT INTO library_catalog (singleton_id, catalog_uuid, created_at, updated_at) VALUES (1, ?, ?, ?)",
        (catalog_uuid, now, now),
    )

    # A contract for SONARA core
    contract_hash = "sha256:" + "a" * 64
    conn.execute(
        """
        INSERT INTO contracts (
            contract_hash, analysis_family, output_kind, model_name, model_version,
            release_hash, canonical_payload_json, created_at
        ) VALUES (?, 'sonara', 'core', 'sonara-model', '0.2.9', 'rel-abc', '{}', ?)
        """,
        (contract_hash, now),
    )

    # A track
    track_uuid = str(uuid.uuid4())
    cur = conn.execute(
        """
        INSERT INTO tracks (
            track_uuid, file_path, file_size_bytes, file_modified_ns,
            content_generation, last_scanned_at, created_at, updated_at
        ) VALUES (?, '/music/track1.mp3', 1024, 1700000000000000000, 1, ?, ?, ?)
        """,
        (track_uuid, now, now, now),
    )
    track_id = cur.lastrowid

    # file_tags
    conn.execute(
        """
        INSERT INTO file_tags (track_id, title, artist, genres_json, tags_read_at)
        VALUES (?, 'Test Track', 'Test Artist', '[]', ?)
        """,
        (track_id, now),
    )

    # sonara row (requires 3 BLOBs: 13*4, 12*4, 7*4 bytes)
    conn.execute(
        """
        INSERT INTO sonara (
            track_id, content_generation, contract_hash,
            mfcc_mean_blob, chroma_mean_blob, spectral_contrast_mean_blob,
            analyzed_at
        ) VALUES (?, 1, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            contract_hash,
            _make_blob(13),
            _make_blob(12),
            _make_blob(7),
            now,
        ),
    )

    # classifier_scores row — all invariants satisfied:
    #   positive_label = 'energetic', predicted_class = 'energetic' (argmax)
    #   score = probs['energetic'] = 0.8
    #   confidence = max(probs.values()) = 0.8
    #   score_bucket = 'high' (0.8 >= 0.7)
    import hashlib as _hashlib
    probs = {"energetic": 0.8, "calm": 0.2}
    probs_json = json.dumps(probs)
    feature_manifest_hash = "sha256:" + _hashlib.sha256(b"sonara-feature-set").hexdigest()
    conn.execute(
        """
        INSERT INTO classifier_scores (
            track_id, classifier_key, content_generation,
            model_id, feature_set, feature_manifest_hash,
            uses_sonara, sonara_release_hash,
            positive_label, predicted_class, score_bucket,
            score, confidence, probabilities_json, analyzed_at
        ) VALUES (?, 'energy', 1, 'model-v1', 'sonara', ?,
                  1, 'rel-abc', 'energetic', 'energetic', 'high',
                  0.8, 0.8, ?, ?)
        """,
        (track_id, feature_manifest_hash, probs_json, now),
    )

    # FTS row
    conn.execute(
        """
        INSERT INTO track_search_fts (
            track_id, file_path, title, artist, album, comment, label,
            catalog_number, country, isrc, year, track_number, disc_number,
            file_genres, maest_genres
        ) VALUES (?, '/music/track1.mp3', 'Test Track', 'Test Artist',
                  NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
        """,
        (track_id,),
    )

    conn.commit()
    conn.close()


def _build_healthy_artifacts(path: Path, catalog_uuid: str, core_path: Path) -> None:
    """Create a healthy artifacts sidecar bound to catalog_uuid, with one mert_embeddings row
    that references a valid track_id and contract_hash from Core."""
    from dj_track_similarity.db_artifacts import create_artifacts_sidecar_schema

    create_artifacts_sidecar_schema(str(path), catalog_uuid=catalog_uuid)

    # Read the track_id and contract_hash from Core
    core_conn = sqlite3.connect(str(core_path))
    core_conn.row_factory = sqlite3.Row
    track_row = core_conn.execute("SELECT track_id, track_uuid FROM tracks LIMIT 1").fetchone()
    contract_row = core_conn.execute("SELECT contract_hash FROM contracts LIMIT 1").fetchone()
    core_conn.close()

    track_id = track_row["track_id"]
    track_uuid = track_row["track_uuid"]
    contract_hash = contract_row["contract_hash"]
    now = _now()

    dim = 128
    conn = sqlite3.connect(str(path))
    conn.execute(
        """
        INSERT INTO mert_embeddings (
            track_id, track_uuid, content_generation, contract_hash,
            dim, normalization, embedding_blob, analyzed_at
        ) VALUES (?, ?, 1, ?, ?, 'none', ?, ?)
        """,
        (track_id, track_uuid, contract_hash, dim, _make_blob(dim), now),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# test_qa_passes_on_healthy_migrated_db
# ---------------------------------------------------------------------------


def test_qa_passes_on_healthy_migrated_db(tmp_path: Path) -> None:
    """Build a healthy v7 Core + artifacts sidecar; harness must return exit 0 with QA PASSED."""
    catalog_uuid = str(uuid.uuid4())
    core_path = tmp_path / "library.sqlite"
    artifacts_path = tmp_path / "library.sqlite.artifacts.sqlite"

    _build_healthy_core(core_path, catalog_uuid)
    _build_healthy_artifacts(artifacts_path, catalog_uuid, core_path)

    exit_code = qa_schema_v7.run_qa(
        db_path=core_path,
        artifacts_db_path=artifacts_path,
        evaluation_db_path=None,
    )

    assert exit_code == 0, "Expected exit code 0 (QA PASSED)"


def test_qa_passes_stdout_contains_qa_passed(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Verify stdout contains 'QA PASSED' on a healthy DB."""
    catalog_uuid = str(uuid.uuid4())
    core_path = tmp_path / "library.sqlite"
    artifacts_path = tmp_path / "library.sqlite.artifacts.sqlite"

    _build_healthy_core(core_path, catalog_uuid)
    _build_healthy_artifacts(artifacts_path, catalog_uuid, core_path)

    exit_code = qa_schema_v7.run_qa(
        db_path=core_path,
        artifacts_db_path=artifacts_path,
        evaluation_db_path=None,
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "QA PASSED" in captured.out


# ---------------------------------------------------------------------------
# test_qa_fails_on_orphaned_sidecar_rows
# ---------------------------------------------------------------------------


def test_qa_fails_on_orphaned_sidecar_rows(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """Insert a mert_embeddings row with a contract_hash not in Core contracts.
    Harness must return exit 1 with FAIL: orphaned mert_embeddings rows."""
    catalog_uuid = str(uuid.uuid4())
    core_path = tmp_path / "library.sqlite"
    artifacts_path = tmp_path / "library.sqlite.artifacts.sqlite"

    _build_healthy_core(core_path, catalog_uuid)

    # Build artifacts sidecar with a valid structure first
    from dj_track_similarity.db_artifacts import create_artifacts_sidecar_schema
    create_artifacts_sidecar_schema(str(artifacts_path), catalog_uuid=catalog_uuid)

    # Read a valid track_id from Core
    core_conn = sqlite3.connect(str(core_path))
    core_conn.row_factory = sqlite3.Row
    track_row = core_conn.execute("SELECT track_id, track_uuid FROM tracks LIMIT 1").fetchone()
    core_conn.close()

    track_id = track_row["track_id"]
    track_uuid = track_row["track_uuid"]

    # Insert a mert_embeddings row with a BOGUS contract_hash (not in Core contracts)
    bogus_contract_hash = "sha256:" + "f" * 64
    dim = 128
    now = _now()

    art_conn = sqlite3.connect(str(artifacts_path))
    art_conn.execute(
        """
        INSERT INTO mert_embeddings (
            track_id, track_uuid, content_generation, contract_hash,
            dim, normalization, embedding_blob, analyzed_at
        ) VALUES (?, ?, 1, ?, ?, 'none', ?, ?)
        """,
        (track_id, track_uuid, bogus_contract_hash, dim, _make_blob(dim), now),
    )
    art_conn.commit()
    art_conn.close()

    exit_code = qa_schema_v7.run_qa(
        db_path=core_path,
        artifacts_db_path=artifacts_path,
        evaluation_db_path=None,
    )

    captured = capsys.readouterr()
    assert exit_code == 1, "Expected exit code 1 (FAIL)"
    combined = captured.out + captured.err
    assert "FAIL" in combined, f"Expected FAIL in output, got: {combined!r}"
    assert "mert_embeddings" in combined, f"Expected mert_embeddings in output, got: {combined!r}"
