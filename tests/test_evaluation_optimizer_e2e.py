from __future__ import annotations

import pytest

from dj_track_similarity.evaluation.score_profile_optimizer import (
    build_saved_score_profile_payload,
    build_score_profile_optimizer_report,
)
from evaluation_fixtures import EvaluationRepository


def test_weighted_feedback_optimizer_profile_save_e2e_fixture() -> None:
    rejected_db = _build_weighted_feedback_fixture(seed_count=50)
    rejected = build_score_profile_optimizer_report(
        rejected_db,
        grid_step=0.5,
        bootstrap_samples=0,
    )

    assert rejected["status"] == "rejected"
    assert rejected["decision"] == "insufficient_matched_judged_pairs"
    assert rejected["judged_pairs"] == 100
    assert rejected["matched_judged_examples"] == 100

    candidate_db = _build_weighted_feedback_fixture(seed_count=100)
    candidate = build_score_profile_optimizer_report(
        candidate_db,
        grid_step=0.5,
        bootstrap_samples=0,
    )

    assert candidate["status"] == "ok"
    assert candidate["judged_pairs"] == 200
    assert candidate["matched_judged_examples"] == 200
    assert candidate["candidate_profile_allowed"] is True
    assert candidate["can_update_defaults"] is False
    assert candidate["weights"]["mert"] > candidate["weights"]["maest"]
    assert (
        _classifier_adjusted_event_count(
            candidate_db,
            "classifier_deep_groove",
        )
        == 100
    )
    with pytest.raises(ValueError, match="500 matched judged-pair"):
        build_saved_score_profile_payload(candidate)

    promotable_db = _build_weighted_feedback_fixture(seed_count=250)
    saveable = build_score_profile_optimizer_report(
        promotable_db,
        grid_step=0.5,
        bootstrap_samples=0,
    )
    saved_payload = build_saved_score_profile_payload(saveable)

    assert saveable["status"] == "ok"
    assert saveable["judged_pairs"] == 500
    assert saveable["can_update_defaults"] is True
    assert saved_payload["weights"] == saveable["weights"]
    assert saved_payload["sources"] == saveable["sources"]
    assert saved_payload["can_apply_as_default"] is True


def _build_weighted_feedback_fixture(
    *,
    seed_count: int,
) -> EvaluationRepository:
    repository = EvaluationRepository(track_count=seed_count + 2)
    bad_id = seed_count + 1
    good_id = seed_count + 2
    for seed_id in range(1, seed_count + 1):
        repository.add_session(
            seed_track_id=seed_id,
            mode="evaluation_candidate_pool",
            feedback_source="manual",
            events=(
                {
                    "candidate_track_id": good_id,
                    "rank": 1,
                    "sources": {
                        "mert": {"rank": 1, "score": 0.95},
                        "maest": {"rank": 10, "score": 0.25},
                    },
                    "score_breakdown": {
                        "score_breakdown": {
                            "classifier_deep_groove": 0.45,
                        },
                    },
                },
                {
                    "candidate_track_id": bad_id,
                    "rank": 2,
                    "sources": {
                        "mert": {"rank": 10, "score": 0.25},
                        "maest": {"rank": 1, "score": 0.95},
                    },
                },
            ),
        )
        repository.add_feedback(
            good_id,
            3,
            seed_track_id=seed_id,
            source="manual",
        )
        repository.add_feedback(
            bad_id,
            0,
            seed_track_id=seed_id,
            source="manual",
        )
    return repository


def _classifier_adjusted_event_count(
    repository: EvaluationRepository,
    breakdown_key: str,
) -> int:
    return sum(
        1
        for session in repository.list_search_sessions_with_events()
        for event in session["events"]
        if breakdown_key
        in (event.get("score_breakdown") or {}).get(
            "score_breakdown",
            {},
        )
    )
