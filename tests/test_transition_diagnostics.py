from __future__ import annotations

import pytest

from dj_track_similarity.models import Track
from dj_track_similarity.transition_diagnostics import compute_transition_diagnostics


def test_bpm_exact_match_has_low_risk() -> None:
    diagnostics = compute_transition_diagnostics(
        {"bpm": 124.0, "musical_key": "8A", "energy": 0.5},
        {"bpm": 124.0, "musical_key": "8A", "energy": 0.5},
    )

    assert diagnostics.components["bpm_risk"] == 0.0
    assert diagnostics.transition_risk == 0.0


def test_bpm_half_double_compatible_has_low_risk() -> None:
    diagnostics = compute_transition_diagnostics(
        {"bpm": 64.0},
        {"bpm": 128.8},
    )

    assert diagnostics.components["bpm_risk"] == pytest.approx(0.0520833333)
    assert diagnostics.transition_risk == diagnostics.components["bpm_risk"]


def test_bpm_quarter_quadruple_not_treated_as_low_risk() -> None:
    diagnostics = compute_transition_diagnostics(
        {"bpm": 60.0},
        {"bpm": 240.0},
    )

    assert diagnostics.components["bpm_risk"] == 1.0
    assert diagnostics.transition_risk == diagnostics.components["bpm_risk"]


def test_resolves_sonara_bpm_before_tag_bpm_and_keeps_tag_key_priority() -> None:
    diagnostics = compute_transition_diagnostics(
        {
            "bpm": 130.0,
            "musical_key": "2A",
            "metadata": {
                "bpm": 100.0,
                "key": "8A",
                "sonara_features": {
                    "bpm": {"type": "float", "value": 130.0},
                    "bpm_confidence": {"type": "float", "value": 1.0},
                    "key": {"type": "str", "value": "2A"},
                },
            },
        },
        {
            "bpm": 132.0,
            "musical_key": "2B",
            "metadata": {
                "bpm": 116.0,
                "key": "9A",
                "sonara_features": {
                    "bpm": {"type": "float", "value": 132.0},
                    "bpm_confidence": {"type": "float", "value": 1.0},
                    "key": {"type": "str", "value": "2B"},
                },
            },
        },
    )

    assert diagnostics.components["bpm_risk"] == pytest.approx((2.0 / 130.0) / 0.12)
    assert diagnostics.components["key_risk"] < 0.1


def test_resolves_tag_bpm_when_sonara_bpm_is_missing() -> None:
    diagnostics = compute_transition_diagnostics(
        {"metadata": {"bpm": 100.0}},
        {"metadata": {"bpm": 104.0}},
    )

    assert diagnostics.components["bpm_risk"] == pytest.approx((4.0 / 100.0) / 0.12)


def test_resolves_sonara_bpm_and_key_when_tags_are_missing() -> None:
    diagnostics = compute_transition_diagnostics(
        {
            "metadata": {
                "sonara_features": {
                    "bpm": {"type": "float", "value": 120.0},
                    "bpm_confidence": {"type": "float", "value": 1.0},
                    "key": {"type": "str", "value": "8A"},
                }
            }
        },
        {
            "metadata": {
                "sonara_features": {
                    "bpm": {"type": "float", "value": 123.0},
                    "bpm_confidence": {"type": "float", "value": 1.0},
                    "key": {"type": "str", "value": "9A"},
                }
            }
        },
    )

    assert diagnostics.components["bpm_risk"] == pytest.approx((3.0 / 120.0) / 0.12)
    assert diagnostics.components["key_risk"] < 0.1


def test_adjacent_camelot_key_has_lower_risk_than_clash() -> None:
    adjacent = compute_transition_diagnostics({"musical_key": "8A"}, {"musical_key": "9A"})
    clash = compute_transition_diagnostics({"musical_key": "8A"}, {"musical_key": "2B"})

    assert adjacent.components["key_risk"] < clash.components["key_risk"]
    assert adjacent.components["key_risk"] < 0.1
    assert clash.components["key_risk"] > 0.7


def test_sonara_camelot_precedes_conversion_of_an_ordinary_key_tag() -> None:
    adjacent = compute_transition_diagnostics(
        {"metadata": {"key": "F major", "sonara_features": {"key_camelot": {"value": "8A"}}}},
        {"metadata": {"key": "C minor", "sonara_features": {"key_camelot": {"value": "9A"}}}},
    )

    assert adjacent.components["key_risk"] == pytest.approx(0.05)


def test_low_sonara_key_confidence_attenuates_harmonic_evidence() -> None:
    high_confidence = compute_transition_diagnostics(
        {"metadata": {"sonara_features": {"key_camelot": "8A", "key_confidence": 1.0}}},
        {"metadata": {"sonara_features": {"key_camelot": "8A", "key_confidence": 1.0}}},
    )
    low_confidence = compute_transition_diagnostics(
        {"metadata": {"sonara_features": {"key_camelot": "8A", "key_confidence": 0.2}}},
        {"metadata": {"sonara_features": {"key_camelot": "8A", "key_confidence": 0.2}}},
    )

    assert high_confidence.components["key_risk"] == 0.0
    assert low_confidence.components["key_risk"] == pytest.approx(0.25)
    assert "low_key_confidence" in low_confidence.warnings


def test_transition_risk_v1_keeps_legacy_key_resolution() -> None:
    seed = {"metadata": {"key": "A minor", "sonara_features": {"key_camelot": "8A", "key_confidence": 1.0}}}
    candidate = {"metadata": {"key": "F# major", "sonara_features": {"key_camelot": "9A", "key_confidence": 1.0}}}

    legacy = compute_transition_diagnostics(seed, candidate, risk_version="v1")
    current = compute_transition_diagnostics(seed, candidate, risk_version="v2")

    assert legacy.components["key_risk"] == pytest.approx(0.45)
    assert current.components["key_risk"] == pytest.approx(0.05)
    assert current.components_v1 is not None
    assert current.components_v1["key_risk"] == pytest.approx(0.45)


def test_transition_risk_v2_is_tempo_confidence_aware_without_changing_v1() -> None:
    seed = {
        "metadata": {
            "sonara_features": {
                "bpm": {"value": 120.0},
                "bpm_confidence": {"value": 0.04},
            }
        }
    }
    candidate = {
        "metadata": {
            "sonara_features": {
                "bpm": {"value": 180.0},
                "bpm_confidence": {"value": 1.0},
            }
        }
    }

    legacy = compute_transition_diagnostics(seed, candidate, risk_version="v1")
    current = compute_transition_diagnostics(seed, candidate, risk_version="v2")

    assert legacy.components["bpm_risk"] == 1.0
    assert current.components["bpm_risk"] == pytest.approx(0.6)
    assert current.components_v1 is not None
    assert current.components_v1["bpm_risk"] == 1.0
    assert "low_bpm_confidence" in current.warnings


def test_transition_risk_v1_does_not_fall_back_to_stale_sonara_bpm_column() -> None:
    stale = Track(
        id=1,
        path="stale.wav",
        size=1,
        mtime=1.0,
        bpm=90.0,
        metadata={"sonara_features": {"bpm": {"value": 90.0}}},
    )

    diagnostics = compute_transition_diagnostics(stale, {"bpm": 128.0}, risk_version="v1")

    assert diagnostics.components["bpm_risk"] is None
    assert "missing_bpm" in diagnostics.warnings


def test_missing_data_returns_none_component() -> None:
    diagnostics = compute_transition_diagnostics(
        {"musical_key": "8A"},
        {"musical_key": "9A"},
    )

    assert diagnostics.components["bpm_risk"] is None
    assert diagnostics.components["energy_jump_risk"] is None
    assert "missing_bpm" in diagnostics.warnings
    assert "missing_energy" in diagnostics.warnings


def test_aggregate_ignores_missing_components() -> None:
    diagnostics = compute_transition_diagnostics(
        {"bpm": 120.0},
        {"bpm": 126.0},
    )

    assert diagnostics.components["bpm_risk"] == pytest.approx(0.4166666667)
    assert diagnostics.transition_risk == diagnostics.components["bpm_risk"]
    assert diagnostics.available_components == ["bpm_risk"]


def test_source_disagreement_risk_uses_source_counts() -> None:
    diagnostics = compute_transition_diagnostics(
        {},
        {},
        source_count=1,
        max_source_count=4,
    )

    assert diagnostics.components["source_disagreement_risk"] == 0.75
    assert diagnostics.transition_risk == 0.75


def test_transition_risk_v2_adds_stored_feature_components() -> None:
    diagnostics = compute_transition_diagnostics(
        {"metadata": {"sonara_features": {"onset_density": 0.25, "spectral_centroid_mean": 1000.0, "valence": 0.8}}},
        {"metadata": {"sonara_features": {"onset_density": 0.75, "spectral_centroid_mean": 2000.0, "valence": 0.2}}},
    )

    assert diagnostics.risk_version == "v2"
    assert diagnostics.components["density_jump_risk"] == pytest.approx(0.5)
    assert diagnostics.components["texture_clash_risk"] == pytest.approx(0.5)
    assert diagnostics.components["mood_clash_risk"] == pytest.approx(0.6)
    assert diagnostics.components["confidence_missingness_risk"] == 0.0
    assert diagnostics.transition_risk_v1 is None


def test_transition_risk_v2_uses_grid_stability_and_structure_boundaries() -> None:
    diagnostics = compute_transition_diagnostics(
        {
            "metadata": {
                "sonara_features": {
                    "duration_sec": 200.0,
                    "outro_start_sec": 180.0,
                    "grid_stability": 1.0,
                    "energy_level": 6.0,
                    "segments": [{"energy": 0.8}, {"energy": 0.4}],
                    "energy_curve_summary": {"value": None, "summary": {"mean": 0.5, "std": 0.1, "min": 0.2, "max": 0.8}},
                }
            }
        },
        {
            "metadata": {
                "sonara_features": {
                    "intro_end_sec": 20.0,
                    "grid_stability": 0.64,
                    "energy_level": 7.0,
                    "segments": [{"energy": 0.5}, {"energy": 0.9}],
                    "energy_curve_summary": {"value": None, "summary": {"mean": 0.6, "std": 0.1, "min": 0.2, "max": 0.9}},
                }
            }
        },
    )

    assert diagnostics.components["grid_instability_risk"] == pytest.approx(0.2)
    assert diagnostics.components["structure_transition_risk"] == pytest.approx(0.0625)
    assert "grid_instability_risk" in diagnostics.available_components
    assert "structure_transition_risk" in diagnostics.available_components


def test_missing_vocal_classifier_scores_do_not_add_missingness_risk() -> None:
    diagnostics = compute_transition_diagnostics(
        {"metadata": {"sonara_features": {"onset_density": 0.25, "spectral_centroid_mean": 1000.0, "valence": 0.8}}},
        {"metadata": {"sonara_features": {"onset_density": 0.75, "spectral_centroid_mean": 2000.0, "valence": 0.2}}},
        classifier_risk_weights={"voice_presence": 1.0},
    )

    assert diagnostics.components["vocal_conflict_risk"] is None
    assert diagnostics.components["confidence_missingness_risk"] == 0.0


def test_transition_risk_v1_remains_available() -> None:
    diagnostics = compute_transition_diagnostics(
        {"bpm": 120.0, "energy": 0.1, "metadata": {"sonara_features": {"onset_density": 0.2}}},
        {"bpm": 126.0, "energy": 0.9, "metadata": {"sonara_features": {"onset_density": 0.9}}},
        risk_version="v1",
    )

    assert diagnostics.risk_version == "v1"
    assert set(diagnostics.components) == {"bpm_risk", "key_risk", "energy_jump_risk", "source_disagreement_risk"}
    assert "density_jump_risk" not in diagnostics.components
    assert diagnostics.transition_risk == pytest.approx((0.4166666667 + 0.8) / 2)


def test_vocal_conflict_risk_uses_requested_classifier_score() -> None:
    diagnostics = compute_transition_diagnostics(
        {"classifier_scores": {"voice_presence": {"score": 0.1}}},
        {"classifier_scores": {"voice_presence": {"score": 0.8}}},
        classifier_risk_weights={"voice_presence": 1.0},
    )

    assert diagnostics.components["vocal_conflict_risk"] == 0.8
