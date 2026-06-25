from __future__ import annotations

import pytest

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
