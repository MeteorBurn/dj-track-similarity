from __future__ import annotations

import base64
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pytest


TOOL_ROOT = Path(__file__).resolve().parents[1]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from audio_dedup.fingerprints import (  # noqa: E402
    FingerprintSketch,
    _fingerprint_lsh_bucket_keys,
    fingerprint_candidate_pairs,
    fingerprint_match_scores,
    fingerprint_sketch,
    load_fingerprint_sketches,
)
from audio_dedup import core  # noqa: E402


def _fingerprint_base64(words: np.ndarray) -> str:
    return base64.b64encode(words.astype("<u4", copy=False).tobytes()).decode("ascii")


def test_fingerprint_lsh_keeps_nearby_same_version_pair_without_duration_data() -> None:
    source_words = np.tile(np.array([0x11111111, 0xABCD1234], dtype=np.uint32), 240)
    nearby_words = source_words.copy()
    nearby_words[40:50] ^= np.uint32(0x00000001)
    unrelated_words = np.bitwise_not(source_words)

    sketches = [
        fingerprint_sketch(1, 1, _fingerprint_base64(source_words)),
        fingerprint_sketch(2, 1, _fingerprint_base64(nearby_words)),
        fingerprint_sketch(3, 1, _fingerprint_base64(unrelated_words)),
    ]

    pairs = fingerprint_candidate_pairs(sketches)

    assert (1, 2) in pairs
    assert (1, 3) not in pairs
    assert (2, 3) not in pairs


def test_fingerprint_lsh_never_matches_across_fingerprint_versions() -> None:
    descriptor = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    sketches = [
        FingerprintSketch(track_id=1, version=1, descriptor=descriptor),
        FingerprintSketch(track_id=2, version=2, descriptor=descriptor.copy()),
    ]

    assert fingerprint_candidate_pairs(sketches) == set()


def test_fingerprint_lsh_bucket_key_requires_two_adjacent_bands() -> None:
    left_signature = np.zeros(96, dtype=bool)
    right_signature = left_signature.copy()
    right_signature[12] = True

    left_keys = _fingerprint_lsh_bucket_keys(left_signature)
    right_keys = _fingerprint_lsh_bucket_keys(right_signature)

    assert len(left_keys) == 4
    assert left_keys[0] != right_keys[0]
    assert left_keys[1:] == right_keys[1:]


def test_fingerprint_sketch_rejects_malformed_or_empty_storage_value() -> None:
    with pytest.raises(ValueError, match="base64"):
        fingerprint_sketch(1, 1, "not valid base64")

    with pytest.raises(ValueError, match="no complete 32-bit frames"):
        fingerprint_sketch(1, 1, "")


def test_stored_fingerprint_loader_rejects_stale_identity_and_matches_only_same_version() -> (
    None
):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE sonara_fingerprints (
            track_id INTEGER PRIMARY KEY,
            track_uuid TEXT NOT NULL,
            fingerprint_version INTEGER NOT NULL,
            fingerprint_base64 TEXT NOT NULL,
            analyzed_at TEXT NOT NULL
        );
        """
    )
    words = np.arange(128, dtype=np.uint32)
    value = _fingerprint_base64(words)
    connection.executemany(
        """
        INSERT INTO sonara_fingerprints (
            track_id, track_uuid, fingerprint_version, fingerprint_base64, analyzed_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (1, "current-1", 1, value, "2026-08-26T00:00:00+00:00"),
            (2, "current-2", 1, value, "2026-08-26T00:00:00+00:00"),
            (3, "stale-3", 1, value, "2026-08-26T00:00:00+00:00"),
            (4, "current-4", 2, value, "2026-08-26T00:00:00+00:00"),
        ],
    )
    identities = {1: "current-1", 2: "current-2", 3: "current-3", 4: "current-4"}

    loaded = load_fingerprint_sketches(connection, identities)
    scores = fingerprint_match_scores(
        connection,
        {(1, 2), (1, 3), (1, 4)},
        identities,
        matcher=lambda left, right: 0.88 if left == right else 0.0,
    )

    assert {sketch.track_id for sketch in loaded.sketches} == {1, 2, 4}
    assert loaded.rejected_rows == 1
    assert scores == {(1, 2): 0.88}


def test_missing_fingerprint_table_disables_only_the_fingerprint_signal() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row

    loaded = load_fingerprint_sketches(connection, {1: "current-1"})
    scores = fingerprint_match_scores(
        connection,
        {(1, 2)},
        {1: "current-1", 2: "current-2"},
        matcher=lambda _left, _right: 1.0,
    )

    assert loaded.sketches == ()
    assert loaded.rejected_rows == 0
    assert scores == {}


def test_fingerprint_matching_reports_progress_after_each_chunk() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE sonara_fingerprints (
            track_id INTEGER PRIMARY KEY,
            track_uuid TEXT NOT NULL,
            fingerprint_version INTEGER NOT NULL,
            fingerprint_base64 TEXT NOT NULL,
            analyzed_at TEXT NOT NULL
        );
        """
    )
    pairs = {(index * 2 + 1, index * 2 + 2) for index in range(251)}
    identities = {
        track_id: f"track-{track_id}"
        for pair in pairs
        for track_id in pair
    }
    value = _fingerprint_base64(np.arange(128, dtype=np.uint32))
    connection.executemany(
        """
        INSERT INTO sonara_fingerprints (
            track_id, track_uuid, fingerprint_version, fingerprint_base64, analyzed_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (track_id, track_uuid, 1, value, "2026-08-26T00:00:00+00:00")
            for track_id, track_uuid in identities.items()
        ],
    )
    progress: list[tuple[int, int]] = []

    scores = fingerprint_match_scores(
        connection,
        pairs,
        identities,
        matcher=lambda _left, _right: 0.88,
        progress_callback=lambda completed, total: progress.append((completed, total)),
    )

    assert len(scores) == 251
    assert progress == [(250, 251), (251, 251)]


def test_fingerprint_sketch_loading_reports_progress_after_each_chunk() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE sonara_fingerprints (
            track_id INTEGER PRIMARY KEY,
            track_uuid TEXT NOT NULL,
            fingerprint_version INTEGER NOT NULL,
            fingerprint_base64 TEXT NOT NULL,
            analyzed_at TEXT NOT NULL
        );
        """
    )
    identities = {track_id: f"track-{track_id}" for track_id in range(1, 451)}
    value = _fingerprint_base64(np.arange(128, dtype=np.uint32))
    connection.executemany(
        """
        INSERT INTO sonara_fingerprints (
            track_id, track_uuid, fingerprint_version, fingerprint_base64, analyzed_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (track_id, track_uuid, 1, value, "2026-08-26T00:00:00+00:00")
            for track_id, track_uuid in identities.items()
        ],
    )
    progress: list[tuple[int, int]] = []

    loaded = load_fingerprint_sketches(
        connection,
        identities,
        progress_callback=lambda completed, total: progress.append((completed, total)),
    )

    assert len(loaded.sketches) == 450
    assert progress == [(200, 450), (400, 450), (450, 450)]


def test_fingerprint_only_match_forms_review_group_without_duration_or_embedding_gate() -> (
    None
):
    tracks = [
        core.TrackRecord(
            track_id=1,
            path="C:/music/one.flac",
            size=100,
            mtime=1.0,
            artist=None,
            title=None,
            album=None,
            bpm=None,
            musical_key=None,
            duration=None,
            metadata={},
            embeddings={},
        ),
        core.TrackRecord(
            track_id=2,
            path="C:/music/two.flac",
            size=90,
            mtime=1.0,
            artist=None,
            title=None,
            album=None,
            bpm=None,
            musical_key=None,
            duration=None,
            metadata={},
            embeddings={},
        ),
    ]
    config = core.resolve_preset("safe", min_score=None)
    groups = core.find_duplicate_groups(
        tracks,
        config,
        limit_groups=None,
        candidate_sources={(1, 2): ("fingerprint_lsh",)},
        fingerprint_scores={(1, 2): 0.88},
    )

    assert len(groups) == 1
    evidence = groups[0].pair_evidence[0]
    assert evidence.fingerprint_similarity == pytest.approx(0.88)
    assert evidence.candidate_sources == ("fingerprint_lsh",)
    payload = core.build_report(
        groups,
        tracks,
        config,
        root=Path("C:/music"),
        path_contains=[],
    )
    group_payload = payload["groups"][0]
    assert group_payload["candidate_deletes"][0]["decision"] == "review"
    blocked_reasons = group_payload["candidate_deletes"][0]["blocked_reasons"]
    assert any(
        "SONARA fingerprint-only candidate" in reason and "0.880000" in reason
        for reason in blocked_reasons
    )
    assert group_payload["pairwise_evidence"][0]["candidate_sources"] == [
        "fingerprint_lsh"
    ]


def test_fingerprint_mode_candidates_come_only_from_fingerprint_lsh() -> None:
    shared = np.linspace(-1.0, 1.0, 96, dtype=np.float32)

    def _track(track_id: int, embedding: np.ndarray | None = None) -> core.TrackRecord:
        return core.TrackRecord(
            track_id=track_id,
            path=f"C:/music/{track_id}.flac",
            size=100,
            mtime=1.0,
            artist=None,
            title=None,
            album=None,
            bpm=None,
            musical_key=None,
            duration=180.0,
            metadata={},
            embeddings={} if embedding is None else {"mert": embedding},
        )

    source_words = np.tile(np.array([0x11111111, 0xABCD1234], dtype=np.uint32), 240)
    nearby_words = source_words.copy()
    nearby_words[40:50] ^= np.uint32(0x00000001)
    tracks = [
        _track(1, shared),
        _track(2, shared.copy()),
        _track(3),
        _track(4),
        _track(5),
    ]
    sketches = [
        fingerprint_sketch(3, 1, _fingerprint_base64(np.bitwise_not(source_words))),
        fingerprint_sketch(4, 1, _fingerprint_base64(source_words)),
        fingerprint_sketch(5, 1, _fingerprint_base64(nearby_words)),
    ]
    config = core.resolve_preset("safe", min_score=None)
    empty_sources = core.SourceConfig(sources=(), weights={})

    result = core._candidate_pair_sources(
        tracks,
        config,
        empty_sources,
        fingerprint_sketches=sketches,
        fingerprint_only=True,
    )

    assert result == {(4, 5): ("fingerprint_lsh",)}


def test_default_fingerprint_mode_rejects_embedding_source_selection(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="--embedding"):
        core.run_report(
            db_path=tmp_path / "missing.sqlite",
            root=Path("C:/music"),
            path_contains=[],
            preset_name="safe",
            min_score=None,
            limit_groups=None,
            out_dir=tmp_path,
            sources=("mert",),
        )


def test_exact_fingerprint_checks_skip_duration_only_candidates() -> None:
    pairs = core._fingerprint_exact_candidate_pairs(
        {
            (1, 2): ("duration_window",),
            (3, 4): ("mert_lsh",),
            (5, 6): ("fingerprint_lsh",),
        }
    )

    assert pairs == {(3, 4), (5, 6)}
