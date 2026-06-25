from __future__ import annotations

from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.score_profiles import (
    LABEL_POLICY,
    ScoreProfile,
    build_score_profile_application_report,
    build_score_profile_from_source_report,
    load_score_profile,
    rank_candidates_with_profile,
    save_score_profile,
    validate_score_profile,
)


def test_score_profile_builds_from_ok_source_profile_report() -> None:
    profile = build_score_profile_from_source_report(_source_profile_report({"mert": 0.65, "maest": 0.35}), name="auto")

    assert profile.name == "auto"
    assert profile.profile_kind == "unsupervised_source_profile"
    assert profile.weight_kind == "unsupervised_internal_profile"
    assert profile.sources == ["mert", "maest"]
    assert profile.weights == {"mert": pytest.approx(0.65), "maest": pytest.approx(0.35)}
    assert any("unsupervised" in limitation for limitation in profile.limitations)
    assert any("not probability" in limitation for limitation in profile.limitations)
    assert any("not human ground truth" in limitation for limitation in profile.limitations)


def test_score_profile_accepts_clap_source_weight() -> None:
    profile = build_score_profile_from_source_report(_source_profile_report({"mert": 0.6, "clap": 0.4}), name="clap_auto")

    assert profile.sources == ["mert", "clap"]
    assert profile.weights == {"mert": pytest.approx(0.6), "clap": pytest.approx(0.4)}


def test_score_profile_rejects_non_ok_source_profile_report() -> None:
    report = _source_profile_report({"mert": 1.0})
    report["status"] = "insufficient_data"

    with pytest.raises(ValueError, match="status must be ok"):
        build_score_profile_from_source_report(report, name="auto")


def test_score_profile_validation_rejects_bad_weights() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        validate_score_profile(_profile_payload(weights={"mert": -0.1, "maest": 1.1}))

    with pytest.raises(ValueError, match="sum approximately"):
        validate_score_profile(_profile_payload(weights={"mert": 0.7, "maest": 0.7}))

    with pytest.raises(ValueError, match="missing weights"):
        validate_score_profile(_profile_payload(sources=["mert", "maest"], weights={"mert": 1.0}))


def test_weighted_rrf_prefers_candidate_from_high_weight_source() -> None:
    profile = _score_profile(weights={"mert": 0.1, "maest": 0.9})
    ranked_candidates = rank_candidates_with_profile(
        {
            101: {"mert": {"rank": 1}},
            102: {"maest": {"rank": 1}},
        },
        profile,
        rrf_k=60,
    )

    assert [candidate.candidate_track_id for candidate in ranked_candidates] == [102, 101]


def test_score_profile_save_load_round_trip(tmp_path: Path) -> None:
    output_path = tmp_path / "score_profile.json"
    profile = _score_profile(weights={"mert": 0.25, "maest": 0.75})

    save_score_profile(profile, output_path)
    loaded = load_score_profile(output_path)

    assert loaded == profile
    assert output_path.read_text(encoding="utf-8").startswith('{"')


def test_score_profile_metrics_preserve_unjudged_rank_positions(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _track(db, tmp_path, "seed")
    unjudged_candidate_id = _track(db, tmp_path, "unjudged")
    relevant_candidate_id = _track(db, tmp_path, "relevant")
    session_id = db.create_search_session("evaluation_candidate_pool", [seed_id], {"feedback_source": "manual"})
    db.record_search_result_event(
        session_id,
        unjudged_candidate_id,
        rank=1,
        total_score=0.0,
        score_breakdown={"sources": {"mert": {"rank": 1}}},
    )
    db.record_search_result_event(
        session_id,
        relevant_candidate_id,
        rank=2,
        total_score=0.0,
        score_breakdown={"sources": {"mert": {"rank": 2}}},
    )
    db.upsert_track_pair_feedback(seed_id, relevant_candidate_id, 3, source="manual")
    profile = _score_profile(weights={"mert": 1.0})

    report = build_score_profile_application_report(db, profile, k_values=[1, 2], rrf_k=60)

    assert report["label_policy"] == LABEL_POLICY
    assert report["judged_results"] == 1
    assert report["unjudged_results"] == 1
    assert report["counts"]["judged_results"] == 1
    assert report["counts"]["unjudged_results"] == 1
    assert report["counts"]["label_policy"] == LABEL_POLICY
    assert report["ranked_sessions"][0]["relevances_for_metrics"] == [0, 3]
    assert report["metrics"]["hit_rate_at_1"] == 0.0
    assert report["metrics"]["mean_precision_at_1"] == 0.0
    assert report["metrics"]["hit_rate_at_2"] == 1.0
    assert report["label_status"] == "insufficient_data"
    assert report["metrics"]["mean_strong_match_rate_at_2"] == 0.5


def _track(db: LibraryDatabase, tmp_path: Path, stem: str) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.title()},
    )


def _score_profile(weights: dict[str, float]) -> ScoreProfile:
    return build_score_profile_from_source_report(_source_profile_report(weights), name="auto")


def _profile_payload(
    *,
    sources: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, object]:
    clean_weights = weights or {"mert": 0.5, "maest": 0.5}
    return {
        "name": "auto",
        "profile_kind": "unsupervised_source_profile",
        "weight_kind": "unsupervised_internal_profile",
        "sources": sources or list(clean_weights),
        "weights": clean_weights,
        "created_at": "2026-06-23T00:00:00Z",
        "source_report_summary": {"status": "ok"},
        "limitations": [
            "This is an unsupervised automatic internal score profile.",
            "These weights are not probability or calibrated confidence.",
            "This profile is not human ground truth.",
        ],
        "version": 1,
    }


def _source_profile_report(weights: dict[str, float]) -> dict[str, object]:
    return {
        "status": "ok",
        "profile_kind": "unsupervised_source_profile",
        "weight_kind": "unsupervised_internal_profile",
        "sources": list(weights),
        "seed_count": 3,
        "per_source": {
            source: {
                "seeds_with_results": 3,
                "seed_coverage_rate": 1.0,
                "consensus_support": 0.5,
                "conflict_rate": 0.0,
            }
            for source in weights
        },
        "consensus": {"method": "reciprocal_rank_fusion", "rrf_k": 60, "top_k": 10, "seeds_with_consensus": 3},
        "recommended_weights": {
            "weight_kind": "unsupervised_internal_profile",
            "weights": weights,
            "note": "test weights",
        },
        "warnings": [],
        "limitations": [],
    }
