from __future__ import annotations

import math

import pytest

from dj_track_similarity.analysis_contracts import ContractIdentity
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    SonaraFeatureRow,
)
from dj_track_similarity.library_models import (
    AnalysisCoverage,
    ClassifierScoreSummary,
    TrackSummary,
)
from dj_track_similarity.track_models import TrackIdentity
from dj_track_similarity.transition_diagnostics import (
    TransitionTrack,
    compute_transition_diagnostics,
)


CATALOG_UUID = "transition-diagnostics-catalog"
SONARA_OUTPUT = AnalysisOutput(
    ContractIdentity(
        analysis_family="sonara",
        output_kind="core",
        model_name="sonara",
        model_version="test",
        release_hash="sha256:" + "1" * 64,
    )
)


def _track(
    track_id: int,
    *,
    tag_bpm: float | None = None,
    tag_key: str | None = None,
    audio_duration_seconds: float | None = None,
    sonara_values: dict[str, object] | None = None,
    classifier_scores: tuple[ClassifierScoreSummary, ...] = (),
) -> TransitionTrack:
    track_uuid = f"track-{track_id}"
    identity = TrackIdentity(
        catalog_uuid=CATALOG_UUID,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=1,
    )
    summary = TrackSummary(
        track_id=track_id,
        catalog_uuid=CATALOG_UUID,
        track_uuid=track_uuid,
        content_generation=1,
        file_path=f"C:/music/{track_uuid}.wav",
        title=None,
        artist=None,
        album=None,
        tag_bpm=tag_bpm,
        tag_key=tag_key,
        audio_duration_seconds=audio_duration_seconds,
        liked=False,
        analysis_coverage=AnalysisCoverage(
            sonara_core=sonara_values is not None
        ),
        classifier_scores=classifier_scores,
    )
    sonara = (
        None
        if sonara_values is None
        else SonaraFeatureRow(
            target=AnalysisTarget(
                catalog_uuid=identity.catalog_uuid,
                track_id=identity.track_id,
                track_uuid=identity.track_uuid,
                content_generation=identity.content_generation,
            ),
            output=SONARA_OUTPUT,
            values=sonara_values,
        )
    )
    return TransitionTrack(identity=identity, summary=summary, sonara=sonara)


def _classifier_score(
    classifier_key: str,
    score: float,
) -> ClassifierScoreSummary:
    return ClassifierScoreSummary(
        classifier_key=classifier_key,
        score=score,
        predicted_class="positive" if score >= 0.5 else "negative",
        score_bucket="high" if score >= 0.5 else "low",
        confidence=max(score, 1.0 - score),
    )


def test_bpm_exact_match_has_low_risk() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(1, tag_bpm=124.0, tag_key="8A"),
        _track(2, tag_bpm=124.0, tag_key="8A"),
    )

    assert diagnostics.components["bpm_risk"] == 0.0
    assert diagnostics.transition_risk == 0.0


def test_bpm_half_double_compatible_has_low_risk() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(1, tag_bpm=64.0),
        _track(2, tag_bpm=128.8),
    )

    assert diagnostics.components["bpm_risk"] == pytest.approx(0.0520833333)
    assert diagnostics.transition_risk == diagnostics.components["bpm_risk"]


def test_bpm_quarter_quadruple_not_treated_as_low_risk() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(1, tag_bpm=60.0),
        _track(2, tag_bpm=240.0),
    )

    assert diagnostics.components["bpm_risk"] == 1.0


def test_sonara_bpm_precedes_tag_bpm_and_camelot_tag_precedes_sonara_key() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(
            1,
            tag_bpm=100.0,
            tag_key="2A",
            sonara_values={
                "detected_bpm": 130.0,
                "bpm_confidence": 1.0,
                "detected_key_camelot": "8A",
                "key_confidence": 1.0,
            },
        ),
        _track(
            2,
            tag_bpm=116.0,
            tag_key="2B",
            sonara_values={
                "detected_bpm": 132.0,
                "bpm_confidence": 1.0,
                "detected_key_camelot": "9A",
                "key_confidence": 1.0,
            },
        ),
    )

    assert diagnostics.components["bpm_risk"] == pytest.approx(
        (2.0 / 130.0) / 0.12
    )
    assert diagnostics.components["key_risk"] < 0.1


def test_tag_bpm_is_used_when_current_sonara_bpm_is_missing() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(1, tag_bpm=100.0),
        _track(2, tag_bpm=104.0),
    )

    assert diagnostics.components["bpm_risk"] == pytest.approx(
        (4.0 / 100.0) / 0.12
    )


def test_sonara_bpm_and_key_are_used_when_tags_are_missing() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(
            1,
            sonara_values={
                "detected_bpm": 120.0,
                "bpm_confidence": 1.0,
                "detected_key_camelot": "8A",
            },
        ),
        _track(
            2,
            sonara_values={
                "detected_bpm": 123.0,
                "bpm_confidence": 1.0,
                "detected_key_camelot": "9A",
            },
        ),
    )

    assert diagnostics.components["bpm_risk"] == pytest.approx(
        (3.0 / 120.0) / 0.12
    )
    assert diagnostics.components["key_risk"] < 0.1


def test_adjacent_camelot_key_has_lower_risk_than_clash() -> None:
    adjacent = compute_transition_diagnostics(
        _track(1, tag_key="8A"),
        _track(2, tag_key="9A"),
    )
    clash = compute_transition_diagnostics(
        _track(1, tag_key="8A"),
        _track(2, tag_key="2B"),
    )

    assert adjacent.components["key_risk"] < clash.components["key_risk"]
    assert adjacent.components["key_risk"] < 0.1
    assert clash.components["key_risk"] > 0.7


def test_sonara_camelot_precedes_conversion_of_an_ordinary_key_tag_in_v2() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(
            1,
            tag_key="F major",
            sonara_values={"detected_key_camelot": "8A"},
        ),
        _track(
            2,
            tag_key="C minor",
            sonara_values={"detected_key_camelot": "9A"},
        ),
    )

    assert diagnostics.components["key_risk"] == pytest.approx(0.05)


def test_low_sonara_key_confidence_attenuates_harmonic_evidence() -> None:
    high_confidence = compute_transition_diagnostics(
        _track(
            1,
            sonara_values={
                "detected_key_camelot": "8A",
                "key_confidence": 1.0,
            },
        ),
        _track(
            2,
            sonara_values={
                "detected_key_camelot": "8A",
                "key_confidence": 1.0,
            },
        ),
    )
    low_confidence = compute_transition_diagnostics(
        _track(
            1,
            sonara_values={
                "detected_key_camelot": "8A",
                "key_confidence": 0.2,
            },
        ),
        _track(
            2,
            sonara_values={
                "detected_key_camelot": "8A",
                "key_confidence": 0.2,
            },
        ),
    )

    assert high_confidence.components["key_risk"] == 0.0
    assert low_confidence.components["key_risk"] == pytest.approx(0.25)
    assert "low_key_confidence" in low_confidence.warnings


def test_transition_risk_v1_keeps_plain_tag_key_resolution() -> None:
    seed = _track(
        1,
        tag_key="A minor",
        sonara_values={
            "detected_key_camelot": "8A",
            "key_confidence": 1.0,
        },
    )
    candidate = _track(
        2,
        tag_key="F# major",
        sonara_values={
            "detected_key_camelot": "9A",
            "key_confidence": 1.0,
        },
    )

    legacy = compute_transition_diagnostics(seed, candidate, risk_version="v1")
    current = compute_transition_diagnostics(seed, candidate, risk_version="v2")

    assert legacy.components["key_risk"] == pytest.approx(0.8)
    assert current.components["key_risk"] == pytest.approx(0.05)
    assert current.components_v1 is not None
    assert current.components_v1["key_risk"] == pytest.approx(0.8)


def test_transition_risk_v2_is_tempo_confidence_aware_without_changing_v1() -> None:
    seed = _track(
        1,
        sonara_values={"detected_bpm": 120.0, "bpm_confidence": 0.04},
    )
    candidate = _track(
        2,
        sonara_values={"detected_bpm": 180.0, "bpm_confidence": 1.0},
    )

    legacy = compute_transition_diagnostics(seed, candidate, risk_version="v1")
    current = compute_transition_diagnostics(seed, candidate, risk_version="v2")

    assert legacy.components["bpm_risk"] == 1.0
    assert current.components["bpm_risk"] == pytest.approx(0.6)
    assert current.components_v1 is not None
    assert current.components_v1["bpm_risk"] == 1.0
    assert "low_bpm_confidence" in current.warnings


def test_missing_data_returns_none_components_and_warnings() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(1, tag_key="8A"),
        _track(2, tag_key="9A"),
    )

    assert diagnostics.components["bpm_risk"] is None
    assert diagnostics.components["energy_jump_risk"] is None
    assert "missing_bpm" in diagnostics.warnings
    assert "missing_energy" in diagnostics.warnings


def test_aggregate_ignores_missing_components() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(1, tag_bpm=120.0),
        _track(2, tag_bpm=126.0),
    )

    assert diagnostics.components["bpm_risk"] == pytest.approx(0.4166666667)
    assert diagnostics.transition_risk == diagnostics.components["bpm_risk"]
    assert diagnostics.available_components == ["bpm_risk"]


def test_source_disagreement_risk_uses_source_counts() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(1),
        _track(2),
        source_count=1,
        max_source_count=4,
    )

    assert diagnostics.components["source_disagreement_risk"] == 0.75
    assert diagnostics.transition_risk == 0.75


def test_transition_risk_v2_adds_typed_sonara_feature_components() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(
            1,
            sonara_values={
                "onset_density_per_second": 0.25,
                "spectral_centroid_hz": 1000.0,
                "valence_score": 0.8,
            },
        ),
        _track(
            2,
            sonara_values={
                "onset_density_per_second": 0.75,
                "spectral_centroid_hz": 2000.0,
                "valence_score": 0.2,
            },
        ),
    )

    assert diagnostics.risk_version == "v2"
    assert diagnostics.components["density_jump_risk"] == pytest.approx(0.5)
    assert diagnostics.components["texture_clash_risk"] == pytest.approx(0.5)
    assert diagnostics.components["mood_clash_risk"] == pytest.approx(0.55)
    assert diagnostics.components["confidence_missingness_risk"] == 0.0
    assert diagnostics.transition_risk_v1 is None


def test_transition_risk_v2_uses_grid_stability_and_structure_fields() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(
            1,
            sonara_values={
                "analyzed_duration_seconds": 200.0,
                "outro_start_seconds": 180.0,
                "beat_grid_stability": 1.0,
                "energy_level": 6.0,
                "energy_curve_mean": 0.5,
                "energy_curve_stddev": 0.1,
                "energy_curve_min": 0.2,
                "energy_curve_max": 0.8,
            },
        ),
        _track(
            2,
            sonara_values={
                "intro_end_seconds": 20.0,
                "beat_grid_stability": 0.64,
                "energy_level": 7.0,
                "energy_curve_mean": 0.6,
                "energy_curve_stddev": 0.1,
                "energy_curve_min": 0.2,
                "energy_curve_max": 0.9,
            },
        ),
    )

    assert diagnostics.components["grid_instability_risk"] == pytest.approx(0.2)
    assert diagnostics.components["structure_transition_risk"] == pytest.approx(
        0.05
    )
    assert "grid_instability_risk" in diagnostics.available_components
    assert "structure_transition_risk" in diagnostics.available_components


def test_missing_vocal_classifier_scores_do_not_add_missingness_risk() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(
            1,
            sonara_values={
                "onset_density_per_second": 0.25,
                "spectral_centroid_hz": 1000.0,
                "valence_score": 0.8,
            },
        ),
        _track(
            2,
            sonara_values={
                "onset_density_per_second": 0.75,
                "spectral_centroid_hz": 2000.0,
                "valence_score": 0.2,
            },
        ),
        classifier_risk_weights={"voice_presence": 1.0},
    )

    assert diagnostics.components["vocal_conflict_risk"] is None
    assert diagnostics.components["confidence_missingness_risk"] == 0.0


def test_transition_risk_v1_remains_available() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(
            1,
            tag_bpm=120.0,
            sonara_values={"energy_score": 0.1},
        ),
        _track(
            2,
            tag_bpm=126.0,
            sonara_values={"energy_score": 0.9},
        ),
        risk_version="v1",
    )

    assert diagnostics.risk_version == "v1"
    assert set(diagnostics.components) == {
        "bpm_risk",
        "key_risk",
        "energy_jump_risk",
        "source_disagreement_risk",
    }
    assert "density_jump_risk" not in diagnostics.components
    assert diagnostics.transition_risk == pytest.approx(
        (0.4166666667 + 0.8) / 2
    )


def test_vocal_conflict_risk_uses_requested_classifier_score() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(
            1,
            classifier_scores=(_classifier_score("voice_presence", 0.1),),
        ),
        _track(
            2,
            classifier_scores=(_classifier_score("voice_presence", 0.8),),
        ),
        classifier_risk_weights={"voice_presence": 1.0},
    )

    assert diagnostics.components["vocal_conflict_risk"] == 0.8


def test_non_finite_typed_values_never_escape_diagnostics() -> None:
    diagnostics = compute_transition_diagnostics(
        _track(
            1,
            sonara_values={
                "detected_bpm": float("nan"),
                "onset_density_per_second": float("inf"),
            },
        ),
        _track(
            2,
            sonara_values={
                "detected_bpm": 128.0,
                "onset_density_per_second": 0.5,
            },
        ),
        source_count=1,
        max_source_count=2,
    )

    assert diagnostics.components["bpm_risk"] is None
    assert diagnostics.components["density_jump_risk"] is None
    assert diagnostics.transition_risk is not None
    assert math.isfinite(diagnostics.transition_risk)
    assert all(
        value is None or math.isfinite(value)
        for value in diagnostics.components.values()
    )


def test_transition_track_rejects_mismatched_sonara_identity() -> None:
    current = _track(1)
    mismatched = SonaraFeatureRow(
        target=AnalysisTarget(
            catalog_uuid=CATALOG_UUID,
            track_id=2,
            track_uuid="track-2",
            content_generation=1,
        ),
        output=SONARA_OUTPUT,
        values={"detected_bpm": 128.0},
    )

    with pytest.raises(ValueError, match="SONARA row identity"):
        TransitionTrack(
            identity=current.identity,
            summary=current.summary,
            sonara=mismatched,
        )
