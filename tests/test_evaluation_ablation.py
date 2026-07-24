from __future__ import annotations

from dj_track_similarity.evaluation.ablation import build_source_ablation_report

from evaluation_v7_fixtures import EvaluationRepository, profile


def test_ablation_uses_current_typed_records_and_manual_labels() -> None:
    repository = EvaluationRepository()
    repository.add_session(
        events=(
            {"candidate_track_id": 2, "rank": 1, "sources": {"mert": {"rank": 1}}},
            {"candidate_track_id": 3, "rank": 2, "sources": {"mert": {"rank": 2}}},
        )
    )
    repository.add_feedback(2, 3)
    repository.add_feedback(3, 0)

    report = build_source_ablation_report(repository, k_values=(1, 2), rrf_k=60)

    metrics = report["variants"]["source:mert"]["metrics"]
    assert report["status"] == "ok"
    assert metrics["mean_precision_at_1"] == 1.0
    assert metrics["hit_rate_at_1"] == 1.0
    assert metrics["mean_bad_suggestion_rate_at_2"] == 0.5


def test_ablation_rrf_and_classifier_removal_preserve_ranking_invariants() -> None:
    repository = EvaluationRepository()
    repository.add_session(
        events=(
            {
                "candidate_track_id": 2,
                "sources": {"mert": {"rank": 2}, "maest": {"rank": 2}},
            },
            {"candidate_track_id": 3, "sources": {"mert": {"rank": 1}}},
            {
                "candidate_track_id": 4,
                "sources": {"mert": {"rank": 3}},
                "score_breakdown": {
                    "classifier_support": {
                        "voice": {"available": True, "score_contribution": 0.2}
                    }
                },
            },
        )
    )
    repository.add_feedback(2, 3)
    repository.add_feedback(3, 0)
    repository.add_feedback(4, 2)

    report = build_source_ablation_report(repository, k_values=(1,), rrf_k=60)

    session = report["sessions"][0]["variants"]
    assert session["fusion:rrf_all"]["ranked_candidate_track_ids"][:2] == [2, 4]
    assert "fusion:rrf_without_classifiers" in report["variants"]
    assert report["variants"]["fusion:rrf_all"]["classifier_adjusted"] is True
    assert report["counts"]["signals_seen"] == ["mert", "maest", "classifiers"]


def test_ablation_weighted_rrf_and_judged_gate_do_not_rewrite_rank_positions() -> None:
    repository = EvaluationRepository()
    repository.add_session(
        events=(
            {
                "candidate_track_id": 2,
                "sources": {"mert": {"rank": 1}, "maest": {"rank": 10}},
            },
            {
                "candidate_track_id": 3,
                "sources": {"mert": {"rank": 10}, "maest": {"rank": 1}},
            },
        )
    )
    repository.add_feedback(3, 3)

    report = build_source_ablation_report(
        repository,
        k_values=(1,),
        rrf_k=60,
        score_profile=profile({"mert": 0.1, "maest": 0.9}),
        judged_only=True,
    )

    variants = report["sessions"][0]["variants"]
    assert report["status"] == "insufficient_data"
    assert report["evaluation_mode"] == "judged_validation"
    assert variants["fusion:rrf_all"]["relevances_for_metrics"] == [3]
    assert variants["fusion:weighted_rrf:fixture"]["ranked_candidate_track_ids"] == [
        3,
        2,
    ]
