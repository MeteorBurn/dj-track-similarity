from __future__ import annotations

import random

import pytest

from dj_track_similarity.evaluation.score_profile_optimizer import (
    build_promoted_score_profile_payload,
    build_score_profile_optimizer_report,
)
from dj_track_similarity.evaluation.score_profile_optimizer import _ranked_relevances as ranked_relevances_for_optimizer_test
from evaluation_v7_fixtures import EvaluationRepository


def test_optimizer_rejects_insufficient_matched_judged_pairs() -> None:
    db = EvaluationRepository()
    seed_id = _track(db)
    bad_id = _track(db)
    good_id = _track(db)
    _add_two_candidate_session(db, seed_id, bad_id, good_id, positive_source="mert")

    report = build_score_profile_optimizer_report(db, bootstrap_samples=0)

    assert report["status"] == "rejected"
    assert report["decision"] == "insufficient_matched_judged_pairs"
    assert report["judged_pairs"] == 2
    assert report["weights"] == {}
    assert report["can_apply_as_default"] is False


def test_optimizer_ignores_unmatched_feedback_rows() -> None:
    db = EvaluationRepository()
    seed_id = _track(db)
    candidate_id = _track(db)
    db.add_feedback(candidate_id, 3, seed_track_id=seed_id)

    report = build_score_profile_optimizer_report(db, min_judged_pairs=1, bootstrap_samples=0)

    assert report["status"] == "rejected"
    assert report["judged_pairs"] == 0
    assert report["matched_judged_examples"] == 0
    assert db.count_evaluation_rows()["pair_feedback"] == 1


def test_optimizer_split_by_seed_is_deterministic_and_disjoint() -> None:
    db = _build_two_candidate_optimizer_library(
        seed_count=100,
        positive_source="mert",
    )

    first = build_score_profile_optimizer_report(
        db,
        random_seed=99,
        grid_step=0.5,
        bootstrap_samples=0,
    )
    second = build_score_profile_optimizer_report(
        db,
        random_seed=99,
        grid_step=0.5,
        bootstrap_samples=0,
    )

    assert first["status"] == "ok"
    assert first["split"]["train_seeds"] == second["split"]["train_seeds"]
    assert first["split"]["validation_seeds"] == second["split"]["validation_seeds"]
    assert set(first["split"]["train_seeds"]).isdisjoint(first["split"]["validation_seeds"])
    assert first["split"]["seed_leakage"] == []


def test_optimizer_outputs_normalized_non_negative_weights_and_schema_fields() -> None:
    db = _build_two_candidate_optimizer_library(
        seed_count=100,
        positive_source="mert",
    )

    report = build_score_profile_optimizer_report(
        db,
        profile_name="judged_test",
        grid_step=0.5,
        bootstrap_samples=10,
    )

    assert report["status"] == "ok"
    assert report["profile_name"] == "judged_test"
    assert report["source"] == "judged_feedback"
    assert report["label_status"] == "sufficient_for_candidate_profile"
    assert report["judged_pairs"] == 200
    assert report["judged_seeds"] == 100
    assert report["weights"]["mert"] > report["weights"]["maest"]
    assert all(weight >= 0.0 for weight in report["weights"].values())
    assert sum(report["weights"].values()) == pytest.approx(1.0)
    assert all(weight >= 0.0 for weight in report["risk_weights"].values())
    assert report["validation_metrics"]["ndcg_at_10"] > report["baseline_validation_metrics"]["ndcg_at_10"]
    assert report["guardrails"]["validation_ndcg_improved"] is True
    assert report["guardrails"]["bad_rate_did_not_increase"] is True
    assert report["can_apply_as_default"] is False
    assert report["default_update_policy"] == "manual_review_only_never_automatic"


def test_optimizer_missing_sources_are_neutral_for_ranked_examples() -> None:
    good = _optimizer_example_for_missing_source_test(
        candidate_track_id=2,
        rating=3,
        source_contributions={"mert": {"rank": 1}},
    )
    bad = _optimizer_example_for_missing_source_test(
        candidate_track_id=1,
        rating=0,
        source_contributions={"mert": {"rank": 100}, "maest": {"rank": 1}},
    )

    relevances = ranked_relevances_for_optimizer_test(
        [bad, good],
        {"mert": 0.5, "maest": 0.5},
        60,
        {"transition_risk": 0.0},
    )

    assert relevances == [3, 0]


def test_optimizer_rejects_when_validation_ndcg_does_not_improve() -> None:
    db, seed_ids = _build_empty_seed_shell(seed_count=100)
    validation_seed_ids = _validation_seed_ids(seed_ids, random_seed=123)
    for index, seed_id in enumerate(seed_ids):
        positive_source = "maest" if seed_id in validation_seed_ids else "mert"
        bad_id = _track(db)
        good_id = _track(db)
        _add_two_candidate_session(db, seed_id, bad_id, good_id, positive_source=positive_source)

    report = build_score_profile_optimizer_report(
        db,
        random_seed=123,
        grid_step=0.5,
        bootstrap_samples=5,
    )

    assert report["status"] == "rejected"
    assert report["decision"] == "guardrail_failure"
    assert report["train_metrics"]["ndcg_at_10"] > report["baseline_train_metrics"]["ndcg_at_10"]
    assert report["guardrails"]["validation_ndcg_improved"] is False
    assert "validation_ndcg_improved" in report["guardrails"]["rejected_checks"]
    assert "bootstrap_stability_passed" in report["guardrails"]["rejected_checks"]


def test_optimizer_rejects_when_bad_suggestion_rate_increases() -> None:
    db = _build_bad_rate_increase_library(seed_count=20)

    report = build_score_profile_optimizer_report(
        db,
        grid_step=0.5,
        bootstrap_samples=0,
    )

    assert report["status"] == "rejected"
    assert report["guardrails"]["validation_ndcg_improved"] is True
    assert report["guardrails"]["bad_rate_did_not_increase"] is False
    assert report["validation_metrics"]["bad_suggestion_rate_at_10"] > report["baseline_validation_metrics"]["bad_suggestion_rate_at_10"]


def test_optimizer_does_not_write_database_rows_by_default() -> None:
    db = _build_two_candidate_optimizer_library(
        seed_count=100,
        positive_source="mert",
    )
    before_counts = db.count_evaluation_rows()

    report = build_score_profile_optimizer_report(
        db,
        grid_step=0.5,
        bootstrap_samples=0,
    )
    after_counts = db.count_evaluation_rows()

    assert report["status"] == "ok"
    assert after_counts == before_counts


def test_optimizer_promotion_payload_requires_default_review_gate() -> None:
    db = _build_two_candidate_optimizer_library(
        seed_count=100,
        positive_source="mert",
    )
    report = build_score_profile_optimizer_report(
        db,
        grid_step=0.5,
        bootstrap_samples=0,
    )

    assert report["status"] == "ok"
    assert report["can_update_defaults"] is False
    with pytest.raises(ValueError, match="500 matched judged-pair"):
        build_promoted_score_profile_payload(report)


def _build_two_candidate_optimizer_library(
    *,
    seed_count: int,
    positive_source: str,
) -> EvaluationRepository:
    db = EvaluationRepository(track_count=seed_count * 3)
    for _index in range(seed_count):
        seed_id = _track(db)
        bad_id = _track(db)
        good_id = _track(db)
        _add_two_candidate_session(db, seed_id, bad_id, good_id, positive_source=positive_source)
    return db


def _build_empty_seed_shell(
    *,
    seed_count: int,
) -> tuple[EvaluationRepository, list[int]]:
    db = EvaluationRepository(track_count=seed_count * 3)
    seed_ids = [_track(db) for _index in range(seed_count)]
    return db, seed_ids


def _build_bad_rate_increase_library(
    *,
    seed_count: int,
) -> EvaluationRepository:
    db = EvaluationRepository(track_count=seed_count * 13)
    for _seed_index in range(seed_count):
        seed_id = _track(db)
        events: list[dict[str, object]] = []
        feedback: list[tuple[int, int]] = []
        strong_id = _track(db)
        events.append(
            _candidate_event(
                strong_id,
                {"mert": {"rank": 1}, "maest": {"rank": 12}},
                rank=1,
            )
        )
        feedback.append((strong_id, 3))
        for offset in range(8):
            work_id = _track(db)
            events.append(
                _candidate_event(
                    work_id,
                    {
                        "mert": {"rank": offset + 2},
                        "maest": {"rank": offset + 1},
                    },
                    rank=offset + 2,
                )
            )
            feedback.append((work_id, 2))
        bad_id = _track(db)
        events.append(
            _candidate_event(
                bad_id,
                {"mert": {"rank": 10}, "maest": {"rank": 13}},
                rank=10,
            )
        )
        feedback.append((bad_id, 0))
        for offset in range(2):
            maybe_id = _track(db)
            events.append(
                _candidate_event(
                    maybe_id,
                    {
                        "mert": {"rank": offset + 11},
                        "maest": {"rank": offset + 9},
                    },
                    rank=offset + 11,
                )
            )
            feedback.append((maybe_id, 1))
        db.add_session(seed_track_id=seed_id, events=events)
        for candidate_id, rating in feedback:
            db.add_feedback(
                candidate_id,
                rating,
                seed_track_id=seed_id,
            )
    return db


def _add_two_candidate_session(
    db: EvaluationRepository,
    seed_id: int,
    bad_id: int,
    good_id: int,
    *,
    positive_source: str,
) -> None:
    negative_source = "maest" if positive_source == "mert" else "mert"
    db.add_session(
        seed_track_id=seed_id,
        events=(
            _candidate_event(
                bad_id,
                {
                    positive_source: {"rank": 10},
                    negative_source: {"rank": 1},
                },
                rank=1,
            ),
            _candidate_event(
                good_id,
                {
                    positive_source: {"rank": 1},
                    negative_source: {"rank": 10},
                },
                rank=2,
            ),
        ),
    )
    db.add_feedback(bad_id, 0, seed_track_id=seed_id)
    db.add_feedback(good_id, 3, seed_track_id=seed_id)


def _candidate_event(
    candidate_track_id: int,
    source_contributions: dict[str, dict[str, int]],
    *,
    rank: int,
) -> dict[str, object]:
    return {
        "candidate_track_id": candidate_track_id,
        "rank": rank,
        "sources": source_contributions,
    }


def _validation_seed_ids(seed_ids: list[int], *, random_seed: int) -> set[int]:
    shuffled_seed_ids = list(sorted(seed_ids))
    random.Random(random_seed).shuffle(shuffled_seed_ids)
    validation_count = max(1, round(len(shuffled_seed_ids) * 0.2))
    validation_count = min(validation_count, len(shuffled_seed_ids) - 1)
    return set(shuffled_seed_ids[:validation_count])


def _track(db: EvaluationRepository) -> int:
    track_id = int(getattr(db, "_next_test_track_id", 1))
    assert track_id in db.identities
    setattr(db, "_next_test_track_id", track_id + 1)
    return track_id


def _optimizer_example_for_missing_source_test(
    *,
    candidate_track_id: int,
    rating: int,
    source_contributions: dict[str, dict[str, int]],
):
    from dj_track_similarity.evaluation.score_profile_optimizer import OptimizerExample, SourceContribution

    return OptimizerExample(
        session_id=1,
        event_id=candidate_track_id,
        seed_track_id=1,
        candidate_track_id=candidate_track_id,
        rating=rating,
        source="manual",
        source_contributions={
            source: SourceContribution(rank=payload["rank"], score=None)
            for source, payload in source_contributions.items()
        },
        transition_risk=0.0,
    )
