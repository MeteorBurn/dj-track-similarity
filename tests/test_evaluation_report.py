from __future__ import annotations

from pathlib import Path

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.judged import judged_label_status
from dj_track_similarity.evaluation.reports import build_search_evaluation_report


def test_build_search_evaluation_report_matches_result_events_to_feedback(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1, metadata={"title": "Seed"})
    candidate_a = db.upsert_track(path=tmp_path / "a.wav", size=10, mtime=1, metadata={"title": "A"})
    candidate_b = db.upsert_track(path=tmp_path / "b.wav", size=10, mtime=1, metadata={"title": "B"})
    candidate_c = db.upsert_track(path=tmp_path / "c.wav", size=10, mtime=1, metadata={"title": "C"})
    candidate_d = db.upsert_track(path=tmp_path / "d.wav", size=10, mtime=1, metadata={"title": "D"})
    session_id = db.create_search_session("mert", [seed_id], {"feedback_source": "manual", "limit": 3})
    db.record_search_result_event(session_id, candidate_a, rank=1, total_score=0.9, score_breakdown={"mert": 0.9})
    db.record_search_result_event(session_id, candidate_b, rank=2, total_score=0.8, score_breakdown={"mert": 0.8})
    db.record_search_result_event(session_id, candidate_c, rank=3, total_score=0.7, score_breakdown={"mert": 0.7})
    db.upsert_track_pair_feedback(seed_id, candidate_a, 3, source="manual")
    db.upsert_track_pair_feedback(seed_id, candidate_b, 0, source="manual")
    db.upsert_track_pair_feedback(seed_id, candidate_d, 2, source="manual")

    report = build_search_evaluation_report(db, k_values=[2])

    assert report["status"] == "ok"
    assert report["counts"]["sessions_total"] == 1
    assert report["counts"]["sessions_with_labels"] == 1
    assert report["counts"]["judged_results"] == 2
    assert report["counts"]["unjudged_results"] == 1
    assert report["counts"]["labels_by_rating"] == {"0": 1, "1": 0, "2": 1, "3": 1}
    session = report["sessions"][0]
    assert session["total_relevant_labels"] == 2
    assert session["metrics"]["precision_at_2"] == 0.5
    assert session["metrics"]["recall_at_2"] == 0.5
    assert session["metrics"]["bad_suggestion_rate_at_2"] == 0.5
    assert report["by_mode"]["mert"]["sessions_total"] == 1


def test_build_search_evaluation_report_returns_insufficient_data_without_labels(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")

    report = build_search_evaluation_report(db, k_values=[5])

    assert report["status"] == "insufficient_data"
    assert report["counts"]["sessions_total"] == 0
    assert report["counts"]["judged_results"] == 0


def test_judged_only_report_gate_counts_only_feedback_matched_to_events(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1, metadata={"title": "Seed"})
    matched_candidate_id = db.upsert_track(path=tmp_path / "matched.wav", size=10, mtime=1, metadata={"title": "Matched"})
    unjudged_candidate_id = db.upsert_track(path=tmp_path / "unjudged.wav", size=10, mtime=1, metadata={"title": "Unjudged"})
    unmatched_feedback_candidate_id = db.upsert_track(path=tmp_path / "unmatched.wav", size=10, mtime=1, metadata={"title": "Unmatched"})
    session_id = db.create_search_session("hybrid_search_preview", [seed_id], {"feedback_source": "hybrid_ui", "limit": 2})
    db.record_search_result_event(session_id, matched_candidate_id, rank=1, total_score=0.9, score_breakdown={"hybrid": 0.9})
    db.record_search_result_event(session_id, unjudged_candidate_id, rank=2, total_score=0.8, score_breakdown={"hybrid": 0.8})
    db.upsert_track_pair_feedback(seed_id, matched_candidate_id, 3, source="hybrid_ui")
    db.upsert_track_pair_feedback(seed_id, unmatched_feedback_candidate_id, 0, source="hybrid_ui")
    db.upsert_track_pair_feedback(seed_id, unjudged_candidate_id, 3, source="manual")

    report = build_search_evaluation_report(db, k_values=[10], judged_only=True)

    assert report["status"] == "insufficient_data"
    assert report["evaluation_mode"] == "judged_validation"
    assert report["label_status"] == "insufficient_data"
    assert report["judged_pairs"] == 1
    assert report["judged_seeds"] == 1
    assert report["counts"]["judged_results"] == 1
    assert report["counts"]["labels_by_rating"] == {"0": 1, "1": 0, "2": 0, "3": 2}
    assert report["judged_label_gate"]["labels_by_rating"] == {"0": 0, "1": 0, "2": 0, "3": 1}
    assert report["can_create_candidate_profile"] is False
    assert report["can_update_defaults"] is False
    assert report["metric_availability"]["explanation_tag_agreement_at_3"]["status"] == "not_available"


def test_report_computes_explanation_tag_agreement_when_reason_tags_match_axes(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1, metadata={"title": "Seed"})
    candidate_id = db.upsert_track(path=tmp_path / "candidate.wav", size=10, mtime=1, metadata={"title": "Candidate"})
    session_id = db.create_search_session("hybrid_search_preview", [seed_id], {"feedback_source": "hybrid_ui", "limit": 1})
    db.record_search_result_event(
        session_id,
        candidate_id,
        rank=1,
        total_score=0.9,
        score_breakdown={"match_character": {"groove": 0.82, "density": 0.76}},
    )
    db.upsert_track_pair_feedback(seed_id, candidate_id, 3, reason_tags=("good_groove", "good_density"), source="hybrid_ui")

    report = build_search_evaluation_report(db, k_values=[3])

    agreement = report["metric_availability"]["explanation_tag_agreement_at_3"]
    assert agreement["status"] == "ok"
    assert agreement["value"] == 1.0
    assert agreement["coverage"] == 1.0


def test_judged_label_status_thresholds() -> None:
    assert judged_label_status(49) == "insufficient_data"
    assert judged_label_status(50) == "sufficient_for_diagnostics"
    assert judged_label_status(199) == "sufficient_for_diagnostics"
    assert judged_label_status(200) == "sufficient_for_candidate_profile"
    assert judged_label_status(499) == "sufficient_for_candidate_profile"
    assert judged_label_status(500) == "sufficient_for_default_review"
