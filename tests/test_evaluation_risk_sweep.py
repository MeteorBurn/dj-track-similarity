from __future__ import annotations

import pytest

from dj_track_similarity.evaluation.risk_sweep import build_risk_penalty_sweep_report

from evaluation_v7_fixtures import EvaluationRepository, profile


def test_risk_sweep_reorders_candidates_by_stored_current_risk() -> None:
    repository = EvaluationRepository()
    repository.add_session(
        events=(
            {
                "candidate_track_id": 2,
                "sources": {"mert": {"rank": 1}},
                "score_breakdown": {
                    "transition_risk": 0.9,
                    "transition_risk_version": "v2",
                },
            },
            {
                "candidate_track_id": 3,
                "sources": {"mert": {"rank": 2}},
                "score_breakdown": {
                    "transition_risk": 0.0,
                    "transition_risk_version": "v2",
                },
            },
        )
    )
    repository.add_feedback(2, 0)
    repository.add_feedback(3, 3)

    report = build_risk_penalty_sweep_report(
        repository, profile({"mert": 1.0}), weights=(0.0, 1.0), k_values=(1,), rrf_k=1
    )

    assert report["variants"]["transition_risk_weight:0"]["ranked_sessions"][0][
        "ranked_candidate_track_ids"
    ] == [2, 3]
    assert report["variants"]["transition_risk_weight:1"]["ranked_sessions"][0][
        "ranked_candidate_track_ids"
    ] == [3, 2]
    assert (
        report["best_by_metric"]["mean_bad_suggestion_rate_at_1"]["direction"] == "min"
    )


def test_risk_sweep_selects_versioned_v1_and_v2_risk_values() -> None:
    repository = EvaluationRepository()
    repository.add_session(
        events=(
            {
                "candidate_track_id": 2,
                "sources": {"mert": {"rank": 1}},
                "score_breakdown": {
                    "transition_diagnostics": {
                        "transition_risk": 0.7,
                        "transition_risk_v1": 0.2,
                        "risk_version": "v2",
                    }
                },
            },
        )
    )

    v1 = build_risk_penalty_sweep_report(
        repository,
        profile({"mert": 1.0}),
        weights=(0.0,),
        k_values=(1,),
        risk_version="v1",
    )
    v2 = build_risk_penalty_sweep_report(
        repository,
        profile({"mert": 1.0}),
        weights=(0.0,),
        k_values=(1,),
        risk_version="v2",
    )

    assert (
        v1["variants"]["transition_risk_weight:0"]["ranked_sessions"][0][
            "ranked_candidates"
        ][0]["transition_risk"]
        == 0.2
    )
    assert (
        v2["variants"]["transition_risk_weight:0"]["ranked_sessions"][0][
            "ranked_candidates"
        ][0]["transition_risk"]
        == 0.7
    )


def test_risk_sweep_without_labels_keeps_diagnostics_and_rejects_invalid_weights() -> (
    None
):
    repository = EvaluationRepository()
    repository.add_session(
        events=(
            {
                "candidate_track_id": 2,
                "sources": {"mert": {"rank": 1}},
                "score_breakdown": {
                    "transition_risk": 0.4,
                    "transition_risk_version": "v2",
                },
            },
        )
    )

    report = build_risk_penalty_sweep_report(
        repository, profile({"mert": 1.0}), weights=(0.0,), k_values=(1,)
    )

    assert report["judged_results"] == 0
    assert "best_by_metric" not in report
    with pytest.raises(ValueError, match="weight must be between 0 and 1"):
        build_risk_penalty_sweep_report(
            repository, profile({"mert": 1.0}), weights=(-0.1,), k_values=(1,)
        )
