from __future__ import annotations

from dj_track_similarity.evaluation.judged import judged_label_status
from dj_track_similarity.evaluation.reports import build_search_evaluation_report

from evaluation_v7_fixtures import EvaluationRepository


def test_search_report_matches_typed_current_events_to_manual_feedback() -> None:
    repository = EvaluationRepository()
    repository.add_session(
        mode="hybrid_search_preview",
        events=(
            {"candidate_track_id": 2, "rank": 1, "sources": {"mert": {"rank": 1}}},
            {"candidate_track_id": 3, "rank": 2, "sources": {"mert": {"rank": 2}}},
        ),
    )
    repository.add_feedback(2, 3, reason_tags=("energy",))
    repository.add_feedback(3, 0)

    report = build_search_evaluation_report(repository, k_values=(1, 2))

    assert report["status"] == "ok"
    assert report["counts"]["judged_results"] == 2
    assert report["overall"]["mean_precision_at_1"] == 1.0
    assert report["overall"]["mean_bad_suggestion_rate_at_2"] == 0.5


def test_search_report_discards_stale_event_provenance_before_metrics() -> None:
    repository = EvaluationRepository()
    repository.add_session(
        events=({"candidate_track_id": 2, "sources": {"mert": {"rank": 1}}},)
    )
    repository.add_feedback(2, 3)
    repository.sessions[0]["events"][0]["score_breakdown"]["sources"]["mert"][
        "contract_hash"
    ] = "sha256:" + "0" * 64

    report = build_search_evaluation_report(repository, judged_only=True)

    assert report["status"] == "insufficient_data"
    assert report["counts"]["sessions_total"] == 1
    assert report["counts"]["judged_results"] == 0


def test_judged_label_status_has_explicit_profile_and_default_gates() -> None:
    assert judged_label_status(49) == "insufficient_data"
    assert judged_label_status(50) == "sufficient_for_diagnostics"
    assert judged_label_status(200) == "sufficient_for_candidate_profile"
    assert judged_label_status(500) == "sufficient_for_default_review"
