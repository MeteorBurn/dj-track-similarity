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
    fingerprint_candidate_pairs,
    fingerprint_match_scores,
    fingerprint_sketch,
    load_fingerprint_sketches,
    sonara_duplicate_clusters,
)
from audio_dedup import config as config_module  # noqa: E402
from audio_dedup import models as models_module  # noqa: E402
from audio_dedup import report_payload as report_payload_module  # noqa: E402
from audio_dedup import scoring as scoring_module  # noqa: E402


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


def test_fingerprint_scan_matches_representatives_only_above_the_upstream_threshold() -> (
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
    versions = {1: 1, 2: 1, 3: 1, 4: 1, 5: 2, 6: 1, 7: 1, 8: 1}
    values = {
        track_id: _fingerprint_base64(np.arange(128, dtype=np.uint32) + track_id)
        for track_id in versions
    }
    connection.executemany(
        """
        INSERT INTO sonara_fingerprints (
            track_id, track_uuid, fingerprint_version, fingerprint_base64, analyzed_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        [
            (track_id, f"current-{track_id}", versions[track_id], values[track_id], "2026-09-20T00:00:00+00:00")
            for track_id in versions
        ],
    )
    identities = {track_id: f"current-{track_id}" for track_id in versions}
    # 7 rounds to 301, one bucket up from 1: the spread a whole-second boundary
    # makes of copies that differ by hundredths. 4 rounds to 302 and 8 to 305,
    # both beyond the slack and out of reach.
    durations = {
        1: 300.2, 2: 300.4, 3: 300.1, 4: 302.0, 5: 300.3,
        6: 299.9, 7: 300.6, 8: 305.0,
    }
    ids_by_value = {value: track_id for track_id, value in values.items()}
    scores = {
        frozenset((1, 2)): 0.9,
        frozenset((1, 3)): 0.3,
        frozenset((2, 3)): 0.8,
        frozenset((1, 4)): 0.99,
        frozenset((1, 5)): 0.99,
        frozenset((1, 6)): 0.95,
        frozenset((2, 6)): 0.7,
        frozenset((1, 7)): 0.97,
        frozenset((2, 7)): 0.6,
        frozenset((6, 7)): 0.5,
        frozenset((2, 4)): 0.8,
        frozenset((4, 6)): 0.75,
        frozenset((4, 7)): 0.85,
        frozenset((1, 8)): 0.99,
    }
    compared: list[frozenset[int]] = []

    def matcher(left: str, right: str) -> float:
        pair = frozenset((ids_by_value[left], ids_by_value[right]))
        compared.append(pair)
        return scores.get(pair, 0.0)

    result = sonara_duplicate_clusters(
        connection,
        identities,
        durations,
        matcher=matcher,
    )

    assert [cluster.representative_id for cluster in result.clusters] == [1]
    cluster = result.clusters[0]
    # 7 sits one bucket up and still joins: rounding must not hide a copy that
    # differs by hundredths of a second across a whole-second boundary.
    assert cluster.member_ids == (1, 2, 6, 7)
    assert cluster.pair_scores == {
        (1, 2): 0.9,
        (1, 6): 0.95,
        (2, 6): 0.7,
        (1, 7): 0.97,
        (2, 7): 0.6,
        (6, 7): 0.5,
    }
    # 3 is only ever offered to representative 1, and 0.30 is not above 0.30.
    assert frozenset((2, 3)) not in compared
    assert frozenset((1, 3)) in compared
    # Beyond the slack and a different fingerprint version are never compared at
    # all, however high their score would have been.
    assert frozenset((1, 8)) not in compared
    assert frozenset((1, 4)) not in compared
    assert frozenset((1, 5)) not in compared
    assert result.valid_fingerprint_count == 8
    assert result.duration_bucket_count == 4


def test_missing_fingerprint_table_yields_no_duplicate_evidence() -> None:
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


def test_lsh_pairs_group_only_at_the_review_threshold() -> None:
    """The LSH mode groups a verified pair and drops one below the threshold.

    Retrieval only shortlists; the exact native score decides, so a shortlisted
    pair scoring under the review threshold forms no group at all.
    """

    def _track(track_id: int) -> models_module.TrackRecord:
        return models_module.TrackRecord(
            track_id=track_id,
            path=f"C:/music/{track_id}.flac",
            size=100 - track_id,
            mtime=1.0,
            artist=None,
            title=None,
            album=None,
            bpm=None,
            musical_key=None,
            duration=None,
            metadata={},
        )

    tracks = [_track(track_id) for track_id in (1, 2, 3, 4)]
    below_threshold = config_module.FINGERPRINT_REVIEW_MIN_SIMILARITY - 0.01

    groups = scoring_module.groups_from_fingerprint_pairs(
        tracks,
        {(1, 2): 0.88, (3, 4): below_threshold},
    )

    assert len(groups) == 1
    assert groups[0].track_ids == (1, 2)
    evidence = groups[0].pair_evidence[0]
    assert evidence.fingerprint_similarity == pytest.approx(0.88)
    assert evidence.candidate_sources == ("fingerprint_lsh",)

    payload = report_payload_module.build_report(
        groups,
        tracks,
        mode=config_module.MODE_FINGERPRINT_LSH,
        path_contains=[],
    )
    group_payload = payload["groups"][0]
    assert group_payload["fingerprint_similarity"] == pytest.approx(0.88)
    assert group_payload["candidate_deletes"][0]["fingerprint_vs_keeper"] == pytest.approx(0.88)
    assert group_payload["pairwise_evidence"][0]["candidate_sources"] == ["fingerprint_lsh"]
