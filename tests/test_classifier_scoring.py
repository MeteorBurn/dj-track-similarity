"""Tests for BUG-C6: analyze-classifier must use full 6-tuple identity and delete stale scores."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import joblib
import numpy as np
import pytest

from dj_track_similarity.classifier_scoring import (
    analyze_classifier,
    _vector_value,
    _score_bucket_from_score,
    _argmax_with_tiebreak,
    save_classifier_score_v7,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_schema_v7 import create_v7_schema
from dj_track_similarity.sonara_contract import expected_sonara_analysis_signature, feature_set_uses_sonara


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

class FixedProbabilityModel:
    """Minimal sklearn-compatible model that always returns fixed probabilities."""

    classes_ = np.asarray(["negative", "positive"])

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        return np.tile(np.asarray([[0.3, 0.7]], dtype=np.float64), (matrix.shape[0], 1))


def _track(db: LibraryDatabase, tmp_path: Path, filename: str) -> int:
    path = tmp_path / filename
    path.write_bytes(b"audio")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1.0, metadata={"title": filename})


def _save_score(
    db: LibraryDatabase,
    track_id: int,
    classifier: str,
    *,
    score: float = 0.5,
    model_id: str = "model_A",
    feature_set: str = "mert",
) -> None:
    db.save_classifier_score(
        track_id,
        classifier=classifier,
        score=score,
        label="medium",
        confidence=max(score, 1.0 - score),
        probabilities={"negative": 1.0 - score, "positive": score},
        feature_set=feature_set,
        model_id=model_id,
    )


def _write_mert_only_model(path: Path, *, classifier_key: str, model_id: str) -> Path:
    """Write a minimal mert-only joblib artifact + model.json manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": FixedProbabilityModel(),
            "feature_set": "mert",
            "feature_names": ["mert:0", "mert:1"],
            "label_order": ["negative", "positive"],
            "classifier_key": classifier_key,
            "positive_label": "positive",
        },
        path,
    )
    manifest_path = path.with_name("model.json")
    manifest_path.write_text(
        json.dumps(
            {
                "classifier_key": classifier_key,
                "manifest_version": 2,
                "profile_name": classifier_key.replace("_", " ").title(),
                "profile_type": "binary",
                "feature_set": "mert",
                "feature_count": 2,
                "label_order": ["negative", "positive"],
                "positive_label": "positive",
                "negative_label": "negative",
                "model_id": model_id,
                "trained_label_counts": {"negative": 10, "positive": 10},
                "production": {
                    "score_semantics": "positive_label_probability",
                    "required_inputs": ["mert"],
                    "calibration": {"status": "uncalibrated", "method": None, "report": None},
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _insert_mert_embedding(db: LibraryDatabase, track_id: int) -> None:
    """Insert a fake 2-dim MERT embedding so the track is ready for scoring."""
    vector = np.asarray([0.6, 0.8], dtype=np.float32)
    db.save_embedding(track_id, vector, model_name="mert", dim=2, embedding_key="mert")


# ---------------------------------------------------------------------------
# Test 1: stale scores (wrong model_id) are deleted before re-scoring
# ---------------------------------------------------------------------------

def test_stale_scores_deleted_before_rescore(tmp_path: Path) -> None:
    """
    BUG-C6 regression test.

    Scenario:
    - Track has a score row for classifier 'my_cls' with model_id='model_A'.
    - A new artifact is promoted with model_id='model_B'.
    - analyze_classifier() must:
        1. Delete the model_A row before scoring.
        2. Write a new model_B row.

    Before the fix, analyze_classifier() called list_tracks_missing_classifier()
    which only returned tracks with NO score row — so model_A scores were silently
    kept and model_B never ran.
    """
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)

    track_id = _track(db, tmp_path, "track.wav")
    _insert_mert_embedding(db, track_id)

    # Pre-existing stale score from model_A
    _save_score(db, track_id, "my_cls", model_id="model_A", feature_set="mert")

    # Promote model_B artifact
    model_path = tmp_path / "models" / "classifiers" / "my-cls" / "model.joblib"
    _write_mert_only_model(model_path, classifier_key="my_cls", model_id="model_B")

    # Run analyze_classifier with model_B
    result = analyze_classifier(db, classifier="my_cls", model_path=model_path)

    # model_A score must be gone
    score_row = db.classifier_score(track_id, "my_cls")
    assert score_row is not None, "Expected a score row after re-scoring"
    assert score_row["model_id"] == "model_B", (
        f"Expected model_id='model_B' but got {score_row['model_id']!r}. "
        "Stale model_A score was not replaced — BUG-C6 not fixed."
    )
    assert result["scored"] >= 1, "Expected at least one track to be scored"


# ---------------------------------------------------------------------------
# Test 2: artifact SHA-256 mismatch is rejected before any scoring
# ---------------------------------------------------------------------------

def test_artifact_sha256_mismatch_rejected(tmp_path: Path) -> None:
    """
    BUG-C6 artifact integrity check.

    Scenario:
    - A valid artifact is written and its SHA-256 is recorded in model.json.
    - One byte of the artifact is tampered with.
    - analyze_classifier() must raise an exception containing
      'artifact SHA-256 mismatch' before writing any score rows.
    """
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)

    track_id = _track(db, tmp_path, "track.wav")
    _insert_mert_embedding(db, track_id)

    model_path = tmp_path / "models" / "classifiers" / "my-cls" / "model.joblib"
    _write_mert_only_model(model_path, classifier_key="my_cls", model_id="model_B")

    # Compute the real SHA-256 of the artifact
    real_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()

    # Write the correct hash into the manifest
    manifest_path = model_path.with_name("model.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_hash"] = real_sha256
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    # Tamper with the artifact (flip one byte)
    raw = bytearray(model_path.read_bytes())
    raw[-1] ^= 0xFF
    model_path.write_bytes(bytes(raw))

    # analyze_classifier must raise before scoring
    with pytest.raises((ValueError, RuntimeError), match="(?i)artifact sha.256 mismatch|sha256 mismatch|artifact.*mismatch"):
        analyze_classifier(db, classifier="my_cls", model_path=model_path)

    # No score rows must have been written
    score_row = db.classifier_score(track_id, "my_cls")
    assert score_row is None, (
        "Expected no score rows after SHA-256 mismatch rejection, "
        f"but found: {score_row}"
    )


# ---------------------------------------------------------------------------
# Helpers for v7 schema tests
# ---------------------------------------------------------------------------

def _make_v7_db(tmp_path: Path) -> sqlite3.Connection:
    """Create an in-memory v7 schema DB with one track row and return the connection."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_v7_schema(conn)
    now = "2026-07-22T00:00:00.000000Z"
    conn.execute(
        """
        INSERT INTO tracks (
            track_uuid, file_path, file_size_bytes, file_modified_ns,
            content_generation, last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("uuid-1", str(tmp_path / "track.wav"), 1024, 1000000000, 1, now, now, now),
    )
    conn.commit()
    return conn


def _track_id_v7(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT track_id FROM tracks LIMIT 1").fetchone()
    assert row is not None
    return int(row[0])


# ---------------------------------------------------------------------------
# Test 3: predicted_class is argmax with deterministic tie-break
# ---------------------------------------------------------------------------

def test_predicted_class_is_argmax(tmp_path: Path) -> None:
    """
    BUG-C1: save_classifier_score_v7() must write predicted_class (argmax)
    and score_bucket atomically.

    Covers:
    - Normal case: argmax selects the highest-probability label.
    - score_bucket thresholds: score >= 0.7 → 'high'.
    - score and confidence columns.
    - Tie-break: when two labels share max probability, the one with the
      lower index in manifest_label_order wins.
    """
    conn = _make_v7_db(tmp_path)
    track_id = _track_id_v7(conn)
    now = "2026-07-22T00:00:00.000000Z"

    # --- Normal case: broken=0.87, straight=0.13 ---
    save_classifier_score_v7(
        conn,
        track_id=track_id,
        classifier_key="break_energy",
        content_generation=1,
        model_id="model-v1",
        feature_set="mert",
        feature_manifest_hash="sha256:aabbcc",
        uses_sonara=0,
        sonara_release_hash=None,
        positive_label="broken",
        probabilities={"broken": 0.87, "straight": 0.13},
        manifest_label_order=["broken", "straight"],
        analyzed_at=now,
    )
    conn.commit()

    row = conn.execute(
        "SELECT predicted_class, score_bucket, score, confidence FROM classifier_scores "
        "WHERE track_id = ? AND classifier_key = ?",
        (track_id, "break_energy"),
    ).fetchone()
    assert row is not None, "Expected a classifier_scores row"
    assert row["predicted_class"] == "broken", (
        f"Expected predicted_class='broken' (argmax), got {row['predicted_class']!r}"
    )
    assert row["score_bucket"] == "high", (
        f"Expected score_bucket='high' (score=0.87 >= 0.7), got {row['score_bucket']!r}"
    )
    assert abs(row["score"] - 0.87) < 1e-6, f"Expected score=0.87, got {row['score']}"
    assert abs(row["confidence"] - 0.87) < 1e-6, f"Expected confidence=0.87, got {row['confidence']}"

    # --- Tie-break: a=0.5, b=0.5, manifest order = ["b", "a"] → "b" wins ---
    save_classifier_score_v7(
        conn,
        track_id=track_id,
        classifier_key="break_energy",
        content_generation=1,
        model_id="model-v1",
        feature_set="mert",
        feature_manifest_hash="sha256:aabbcc",
        uses_sonara=0,
        sonara_release_hash=None,
        positive_label="b",
        probabilities={"a": 0.5, "b": 0.5},
        manifest_label_order=["b", "a"],
        analyzed_at=now,
    )
    conn.commit()

    row2 = conn.execute(
        "SELECT predicted_class, score_bucket FROM classifier_scores "
        "WHERE track_id = ? AND classifier_key = ?",
        (track_id, "break_energy"),
    ).fetchone()
    assert row2 is not None
    assert row2["predicted_class"] == "b", (
        f"Tie-break: expected predicted_class='b' (lower manifest index), got {row2['predicted_class']!r}"
    )
    # score=0.5 → 'medium' (0.3 <= 0.5 < 0.7)
    assert row2["score_bucket"] == "medium", (
        f"Expected score_bucket='medium' (score=0.5), got {row2['score_bucket']!r}"
    )

    conn.close()


# ---------------------------------------------------------------------------
# Test 4: BUG-C5 — zero-fill removed; out-of-range dim → not-ready
# ---------------------------------------------------------------------------

def test_zero_fill_removed() -> None:
    """
    BUG-C5: _vector_value() must return None for out-of-range indices,
    not 0.0.  _track_feature_row() must propagate None → return None
    (track not-ready), so no corrupted score row is written.
    """
    # --- Unit test: _vector_value returns None for out-of-range index ---
    vector = np.asarray([1.0, 2.0, 3.0], dtype=np.float32)

    # In-range: should return the value
    assert _vector_value(vector, "0") == pytest.approx(1.0)
    assert _vector_value(vector, "2") == pytest.approx(3.0)

    # Out-of-range: must return None (BUG-C5 fix), NOT 0.0
    result_high = _vector_value(vector, "3")
    assert result_high is None, (
        f"Expected None for index=3 on dim-3 vector (BUG-C5), got {result_high!r}"
    )
    result_neg = _vector_value(vector, "-1")
    assert result_neg is None, (
        f"Expected None for index=-1 (BUG-C5), got {result_neg!r}"
    )

    # --- score_bucket thresholds: low boundary ---
    assert _score_bucket_from_score(0.0) == "low"
    assert _score_bucket_from_score(0.29) == "low"
    assert _score_bucket_from_score(0.3) == "medium"
    assert _score_bucket_from_score(0.69) == "medium"
    assert _score_bucket_from_score(0.7) == "high"
    assert _score_bucket_from_score(1.0) == "high"


# ---------------------------------------------------------------------------
# Test 5: SHA-256 mismatch rejected for v7 write path (BUG-C6 complement)
# ---------------------------------------------------------------------------

def test_artifact_sha256_mismatch_rejected_v7(tmp_path: Path) -> None:
    """
    BUG-C6 complement: artifact SHA-256 verification must fire BEFORE any
    scoring or DB mutation, even when the v7 write path would be used.

    This is a smoke test that reuses the existing analyze_classifier()
    entry point (which calls _load_payload() with expected_artifact_hash
    before any DB write).  The v7 write path is not reached when the
    artifact is tampered — the check must reject first.
    """
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)

    track_id = _track(db, tmp_path, "track_v7.wav")
    _insert_mert_embedding(db, track_id)

    model_path = tmp_path / "models" / "classifiers" / "my-cls-v7" / "model.joblib"
    _write_mert_only_model(model_path, classifier_key="my_cls_v7", model_id="model-v7")

    # Record the real SHA-256 in the manifest
    real_sha256 = hashlib.sha256(model_path.read_bytes()).hexdigest()
    manifest_path = model_path.with_name("model.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifact_hash"] = real_sha256
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    # Tamper with the artifact
    raw = bytearray(model_path.read_bytes())
    raw[-1] ^= 0xFF
    model_path.write_bytes(bytes(raw))

    # Must raise before any scoring
    with pytest.raises(
        (ValueError, RuntimeError),
        match="(?i)artifact sha.256 mismatch|sha256 mismatch|artifact.*mismatch",
    ):
        analyze_classifier(db, classifier="my_cls_v7", model_path=model_path)

    # No score row must have been written
    score_row = db.classifier_score(track_id, "my_cls_v7")
    assert score_row is None, (
        "Expected no score rows after SHA-256 mismatch rejection (v7 path), "
        f"but found: {score_row}"
    )
