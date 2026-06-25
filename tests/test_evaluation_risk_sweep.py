from __future__ import annotations

from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.risk_sweep import build_risk_penalty_sweep_report
from dj_track_similarity.evaluation.score_profiles import ScoreProfile, build_score_profile_from_source_report


def test_risk_sweep_without_labels_returns_diagnostics_only(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _track(db, tmp_path, "seed")
    candidate_id = _track(db, tmp_path, "candidate")
    _record_pool(db, seed_id, [(candidate_id, 1, 0.2)])

    report = build_risk_penalty_sweep_report(db, _score_profile(), weights=[0.0, 0.5], k_values=[1], rrf_k=1)

    assert report["status"] == "ok"
    assert report["label_status"] == "insufficient_data"
    assert "best_by_metric" not in report
    variant = report["variants"]["transition_risk_weight:0.5"]
    assert variant["label_status"] == "insufficient_data"
    assert "metrics" not in variant
    assert variant["diagnostics"]["average_transition_risk_at_k"]["1"] == pytest.approx(0.2)
    assert variant["diagnostics"]["source_count_at_k"]["1"]["average"] == 1.0
    assert variant["ranked_sessions"][0]["ranked_candidate_track_ids"] == [candidate_id]


def test_risk_sweep_with_labels_includes_metrics_and_best_by_metric(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _track(db, tmp_path, "seed")
    risky_id = _track(db, tmp_path, "risky")
    safe_id = _track(db, tmp_path, "safe")
    _record_pool(db, seed_id, [(risky_id, 1, 1.0), (safe_id, 2, 0.0)])
    db.upsert_track_pair_feedback(seed_id, risky_id, 0, source="manual")
    db.upsert_track_pair_feedback(seed_id, safe_id, 3, source="manual")

    report = build_risk_penalty_sweep_report(db, _score_profile(), weights=[0.0, 1.0], k_values=[1], rrf_k=1)

    assert report["label_status"] == "insufficient_data"
    assert report["judged_pairs"] == 2
    assert report["variants"]["transition_risk_weight:0"]["metrics"]["mean_precision_at_1"] == 0.0
    assert report["variants"]["transition_risk_weight:1"]["metrics"]["mean_precision_at_1"] == 1.0
    assert report["variants"]["transition_risk_weight:1"]["metrics"]["mean_strong_match_rate_at_1"] == 1.0
    assert report["best_by_metric"]["mean_precision_at_1"]["transition_risk_weight"] == 1.0
    assert report["best_by_metric"]["mean_bad_suggestion_rate_at_1"]["transition_risk_weight"] == 1.0


def test_risk_sweep_high_weight_lowers_average_transition_risk_at_k(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _track(db, tmp_path, "seed")
    risky_id = _track(db, tmp_path, "risky")
    safe_id = _track(db, tmp_path, "safe")
    _record_pool(db, seed_id, [(risky_id, 1, 1.0), (safe_id, 2, 0.0)])

    report = build_risk_penalty_sweep_report(db, _score_profile(), weights=[0.0, 1.0], k_values=[1], rrf_k=1)

    risk_without_penalty = report["variants"]["transition_risk_weight:0"]["diagnostics"]["average_transition_risk_at_k"]["1"]
    risk_with_penalty = report["variants"]["transition_risk_weight:1"]["diagnostics"]["average_transition_risk_at_k"]["1"]
    assert risk_with_penalty < risk_without_penalty
    assert report["variants"]["transition_risk_weight:1"]["ranked_sessions"][0]["ranked_candidate_track_ids"] == [safe_id, risky_id]


def test_risk_sweep_recomputes_source_risk_from_effective_recorded_sources(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _track(db, tmp_path, "seed")
    candidate_id = _track(db, tmp_path, "candidate")
    session_id = db.create_search_session(
        "evaluation_weighted_candidate_pool",
        [seed_id],
        {"feedback_source": "manual", "sources": ["mert", "clap"]},
    )
    db.record_search_result_event(
        session_id,
        candidate_id,
        rank=1,
        total_score=0.0,
        score_breakdown={"sources": {"mert": {"rank": 1, "score": 1.0}}},
    )

    report = build_risk_penalty_sweep_report(db, _score_profile({"mert": 1.0, "clap": 0.0}), weights=[0.0], k_values=[1], rrf_k=1)

    candidate = report["variants"]["transition_risk_weight:0"]["ranked_sessions"][0]["ranked_candidates"][0]
    assert candidate["source_count"] == 1
    assert candidate["transition_risk"] == 0.0


def test_risk_sweep_rejects_invalid_weight(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")

    with pytest.raises(ValueError, match="weight must be between 0 and 1"):
        build_risk_penalty_sweep_report(db, _score_profile(), weights=[-0.1], k_values=[1])

    with pytest.raises(ValueError, match="weight must be between 0 and 1"):
        build_risk_penalty_sweep_report(db, _score_profile(), weights=[1.1], k_values=[1])


def _record_pool(db: LibraryDatabase, seed_id: int, candidates: list[tuple[int, int, float]]) -> None:
    session_id = db.create_search_session("evaluation_weighted_candidate_pool", [seed_id], {"feedback_source": "manual", "sources": ["mert"]})
    for candidate_id, rank, risk in candidates:
        db.record_search_result_event(
            session_id,
            candidate_id,
            rank=rank,
            total_score=0.0,
            score_breakdown={
                "sources": {"mert": {"rank": rank, "score": 1.0 / rank}},
                "transition_risk": risk,
            },
        )


def _track(db: LibraryDatabase, tmp_path: Path, stem: str) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.title()},
        bpm=120.0,
        musical_key="1A",
        energy=0.5,
    )


def _score_profile(weights: dict[str, float] | None = None) -> ScoreProfile:
    clean_weights = weights or {"mert": 1.0}
    return build_score_profile_from_source_report(
        {
            "status": "ok",
            "profile_kind": "unsupervised_source_profile",
            "weight_kind": "unsupervised_internal_profile",
            "sources": list(clean_weights),
            "seed_count": 1,
            "per_source": {},
            "consensus": {},
            "recommended_weights": {"weight_kind": "unsupervised_internal_profile", "weights": clean_weights, "note": "test"},
            "warnings": [],
            "limitations": [],
        },
        name="auto",
    )
