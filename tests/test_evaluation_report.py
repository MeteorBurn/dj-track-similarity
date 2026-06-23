from __future__ import annotations

from pathlib import Path

from dj_track_similarity.database import LibraryDatabase
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
