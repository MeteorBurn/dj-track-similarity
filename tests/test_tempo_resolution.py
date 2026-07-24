from __future__ import annotations

import json

import pytest

from dj_track_similarity.analysis_contracts import ContractIdentity
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    SonaraFeatureRow,
)
from dj_track_similarity.library_models import AnalysisCoverage, TrackSummary
from dj_track_similarity.tempo_resolution import (
    TempoEvidence,
    confidence_aware_target_score,
    confidence_aware_tempo_score,
    resolve_tempo_evidence,
    tempo_filter_compatible,
    tempo_pair_reliability,
)
from dj_track_similarity.track_models import TrackIdentity


_CORE_OUTPUT = AnalysisOutput(
    ContractIdentity(
        analysis_family="sonara",
        output_kind="core",
        model_name="test-sonara",
        model_version="1",
        release_hash="sha256:" + "1" * 64,
        checkpoint_id="test-checkpoint",
        preprocessing="test-preprocessing",
        parameters={"fixture": "tempo-resolution"},
    )
)


def _evidence(bpm: float, confidence: float, *, grid: float | None = None) -> TempoEvidence:
    reliability = confidence if grid is None else (confidence * grid) ** 0.5
    return TempoEvidence(bpm, (bpm,), confidence, grid, reliability, "sonara")


def _resolved(
    track_id: int,
    *,
    tag_bpm: float | None = None,
    sonara_values: dict[str, object] | None = None,
) -> TempoEvidence:
    identity = TrackIdentity(
        catalog_uuid="fixture-catalog",
        track_id=track_id,
        track_uuid=f"fixture-track-{track_id}",
        content_generation=1,
    )
    summary = TrackSummary(
        track_id=identity.track_id,
        catalog_uuid=identity.catalog_uuid,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
        file_path=f"C:/fixture/{track_id}.wav",
        title=f"Track {track_id}",
        artist="Fixture Artist",
        album=None,
        tag_bpm=tag_bpm,
        tag_key=None,
        audio_duration_seconds=None,
        liked=False,
        analysis_coverage=AnalysisCoverage(sonara_core=sonara_values is not None),
        classifier_scores=(),
    )
    sonara = None
    if sonara_values is not None:
        sonara = SonaraFeatureRow(
            target=AnalysisTarget(
                catalog_uuid=identity.catalog_uuid,
                track_id=identity.track_id,
                track_uuid=identity.track_uuid,
                content_generation=identity.content_generation,
            ),
            output=_CORE_OUTPUT,
            values=sonara_values,
        )
    return resolve_tempo_evidence(identity, summary, sonara)


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
    evidence = _resolved(
        1,
        tag_bpm=95.0,
        sonara_values={
            "detected_bpm": 126.0,
            "bpm_confidence": 0.3,
            "bpm_candidates_json": json.dumps([[190.0, 3.2], [126.0, 3.0]]),
        },
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


def test_sonara_analysis_without_confidence_is_neutral_not_trusted() -> None:
    stale = _resolved(1, sonara_values={"detected_bpm": 90.0})
    current = _evidence(128.0, 1.0)

    assert stale.reliability == 0.0
    assert confidence_aware_tempo_score(stale, current) == pytest.approx(0.5)


def test_sonara_bpm_with_null_confidence_stays_neutral_not_tag_fallback() -> None:
    evidence = _resolved(
        1,
        tag_bpm=128.0,
        sonara_values={"detected_bpm": 155.0},
    )

    assert evidence.bpm == 155.0
    assert evidence.source == "sonara_low_confidence"
    assert evidence.reliability == 0.0


def test_null_confidence_yields_neutral() -> None:
    evidence = _resolved(
        1,
        tag_bpm=128.0,
        sonara_values={"detected_bpm": 126.0},
    )
    reference = _evidence(128.0, 1.0)

    assert evidence.reliability == 0.0
    assert confidence_aware_tempo_score(evidence, reference) == pytest.approx(0.5)


def test_tag_only_tempo_preserves_measured_matching_behavior() -> None:
    candidate = _resolved(1, tag_bpm=128.0)
    reference = _resolved(2, tag_bpm=130.0)

    assert candidate.source == "tag"
    assert tempo_pair_reliability(candidate, reference) == 1.0
    assert confidence_aware_tempo_score(candidate, reference) == pytest.approx(0.875)


def test_persisted_tempo_uses_current_identity_bound_sonara_core() -> None:
    evidence = _resolved(
        1,
        tag_bpm=128.0,
        sonara_values={"detected_bpm": 90.0, "bpm_confidence": 1.0},
    )

    assert evidence.bpm == 90.0
    assert evidence.source == "sonara"

    no_tag = _resolved(2, sonara_values={"detected_bpm": 90.0})
    assert no_tag.bpm == 90.0
    assert no_tag.reliability == 0.0
