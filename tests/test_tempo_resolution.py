from __future__ import annotations

import pytest

from dj_track_similarity.models import Track
from dj_track_similarity.sonara_contract import expected_sonara_analysis_signature
from dj_track_similarity.tempo_resolution import (
    TempoEvidence,
    confidence_aware_target_score,
    confidence_aware_tempo_score,
    resolve_tempo_evidence,
    tempo_filter_compatible,
    tempo_pair_reliability,
)


def _evidence(bpm: float, confidence: float, *, grid: float | None = None) -> TempoEvidence:
    reliability = confidence if grid is None else (confidence * grid) ** 0.5
    return TempoEvidence(bpm, (bpm,), confidence, grid, reliability, "sonara")


def test_pair_reliability_uses_geometric_mean_and_neutral_blend() -> None:
    candidate = _evidence(128.0, 0.25)
    reference = _evidence(128.0, 0.81)

    assert tempo_pair_reliability(candidate, reference) == pytest.approx(0.45)
    assert confidence_aware_tempo_score(candidate, reference) == pytest.approx(0.725)


def test_grid_stability_is_a_secondary_reliability_signal() -> None:
    stable = _evidence(128.0, 0.8, grid=1.0)
    drifting = _evidence(128.0, 0.8, grid=0.0)

    assert stable.reliability == pytest.approx((0.8 * 1.0) ** 0.5)
    assert drifting.reliability == 0.0
    assert confidence_aware_target_score(drifting, 128.0, 12.0) == pytest.approx(0.5)


def test_low_confidence_uses_tag_confirmed_by_sonara_candidate() -> None:
    evidence = resolve_tempo_evidence(
        {
            "bpm": 126.0,
            "metadata": {
                "bpm": [95.0],
                "sonara_features": {
                    "bpm": {"value": 126.0},
                    "bpm_confidence": {"value": 0.3},
                    "bpm_candidates": {"value": [[190.0, 3.2], [126.0, 3.0]]},
                },
            },
        }
    )

    assert evidence.bpm == 95.0
    assert evidence.source == "tag_confirmed_by_sonara_candidate"
    assert evidence.alternatives == (126.0, 190.0, 95.0)
    assert evidence.reliability == pytest.approx(0.3)


def test_low_confidence_mismatch_does_not_become_a_hard_filter_rejection() -> None:
    candidate = _evidence(90.0, 0.2)
    reference = _evidence(128.0, 0.9)
    high_confidence_candidate = _evidence(90.0, 0.9)

    assert tempo_filter_compatible(candidate, reference, 4.0) is True
    assert tempo_filter_compatible(high_confidence_candidate, reference, 4.0) is False


def test_quarter_or_quadruple_tempo_is_not_treated_as_half_double_match() -> None:
    candidate = _evidence(60.0, 1.0)
    reference = _evidence(240.0, 1.0)

    assert confidence_aware_tempo_score(candidate, reference) == 0.0


def test_set_trajectory_target_uses_direct_bpm_not_half_double_match() -> None:
    candidate = _evidence(60.0, 1.0)

    assert confidence_aware_target_score(candidate, 120.0, 12.0) == 0.0


def test_old_sonara_analysis_without_confidence_is_neutral_not_trusted() -> None:
    stale = resolve_tempo_evidence(
        {"metadata": {"sonara_features": {"bpm": {"value": 90.0}}}}
    )
    current = _evidence(128.0, 1.0)

    assert stale.reliability == 0.0
    assert confidence_aware_tempo_score(stale, current) == pytest.approx(0.5)


def test_old_sonara_analysis_uses_independent_tag_fallback() -> None:
    stale = resolve_tempo_evidence(
        {
            "bpm": 155.0,
            "metadata": {
                "bpm": [128.0],
                "sonara_features": {"bpm": {"value": 155.0}},
            },
        }
    )

    assert stale.bpm == 128.0
    assert stale.alternatives == (128.0,)
    assert stale.source == "legacy_tag_fallback"
    assert stale.reliability == 1.0


def test_tag_only_tempo_preserves_measured_matching_behavior() -> None:
    candidate = resolve_tempo_evidence({"metadata": {"bpm": [128.0]}})
    reference = resolve_tempo_evidence({"metadata": {"bpm": [130.0]}})

    assert candidate.source == "tag"
    assert tempo_pair_reliability(candidate, reference) == 1.0
    assert confidence_aware_tempo_score(candidate, reference) == pytest.approx(0.875)


def test_persisted_tempo_ignores_unsigned_sonara_but_accepts_current_signature() -> None:
    metadata = {
        "bpm": [128.0],
        "sonara_features": {"bpm": {"value": 90.0}, "bpm_confidence": {"value": 1.0}},
    }
    stale = Track(id=1, path="stale.wav", size=1, mtime=1.0, bpm=90.0, metadata=dict(metadata))
    current = Track(
        id=2,
        path="current.wav",
        size=1,
        mtime=1.0,
        bpm=90.0,
        metadata={**metadata, "sonara_analysis_signature": expected_sonara_analysis_signature([])},
    )

    assert resolve_tempo_evidence(stale).bpm == 128.0
    assert resolve_tempo_evidence(stale).source == "tag"
    assert resolve_tempo_evidence(current).bpm == 90.0
    assert resolve_tempo_evidence(current).source == "sonara"

    no_tag = Track(
        id=3,
        path="stale-no-tag.wav",
        size=1,
        mtime=1.0,
        bpm=90.0,
        metadata={"sonara_features": metadata["sonara_features"]},
    )
    assert resolve_tempo_evidence(no_tag).bpm is None
    assert resolve_tempo_evidence(no_tag).reliability == 0.0
