from __future__ import annotations

import pytest

from dj_track_similarity.evaluation.calibration import (
    brier_score,
    build_calibration_report,
    expected_calibration_error,
    reliability_bins,
    threshold_table,
)

from evaluation_v7_fixtures import EvaluationRepository


def test_calibration_probability_metrics_match_known_values() -> None:
    probabilities = (0.1, 0.4, 0.8)
    labels = (0, 1, 1)

    assert brier_score(probabilities, labels) == pytest.approx((0.01 + 0.36 + 0.04) / 3)
    assert reliability_bins(probabilities, labels, bins=2)[0] == {
        "lower": 0.0,
        "upper": 0.5,
        "count": 2,
        "avg_score": 0.25,
        "positive_rate": 0.5,
        "gap": 0.25,
    }
    assert expected_calibration_error(probabilities, labels, bins=2) == pytest.approx(
        7 / 30
    )
    assert (
        threshold_table(probabilities, labels, thresholds=(0.5,))[0]["precision"] == 1.0
    )


def test_calibration_rrf_uses_current_provenance_and_manual_label_gate() -> None:
    repository = EvaluationRepository()
    repository.add_session(
        events=(
            {"candidate_track_id": 2, "sources": {"mert": {"rank": 1}}},
            {"candidate_track_id": 3, "sources": {"mert": {"rank": 2}}},
        )
    )
    repository.add_feedback(2, 3)
    repository.add_feedback(3, 0)

    report = build_calibration_report(
        repository,
        score_mode="rrf",
        bins=2,
        min_samples=1,
        judged_only=True,
    )

    assert report["status"] == "insufficient_data"
    assert report["evaluation_mode"] == "judged_validation"
    assert report["sample_count"] == 2
    assert report["positive_count"] == 1
    assert report["score_kind"] == "rrf_minmax_diagnostic"


def test_event_total_score_outside_probability_range_remains_diagnostic() -> None:
    repository = EvaluationRepository()
    repository.add_session(
        events=(
            {
                "candidate_track_id": 2,
                "total_score": 2.0,
                "sources": {"mert": {"rank": 1}},
            },
        )
    )
    repository.add_feedback(2, 3)

    report = build_calibration_report(
        repository, score_mode="event-total-score", min_samples=1
    )

    assert report["calibration_status"] == "uncalibrated_score_out_of_range"
    assert report["brier_score"] is None
    assert report["score_quantiles"] == [
        {"quantile": 0.0, "value": 2.0},
        {"quantile": 0.1, "value": 2.0},
        {"quantile": 0.25, "value": 2.0},
        {"quantile": 0.5, "value": 2.0},
        {"quantile": 0.75, "value": 2.0},
        {"quantile": 0.9, "value": 2.0},
        {"quantile": 1.0, "value": 2.0},
    ]
