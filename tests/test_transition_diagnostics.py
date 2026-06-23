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
