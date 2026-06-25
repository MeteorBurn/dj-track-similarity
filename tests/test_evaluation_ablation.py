from __future__ import annotations

from pathlib import Path

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.ablation import build_source_ablation_report
from dj_track_similarity.evaluation.score_profiles import LABEL_POLICY, ScoreProfile, build_score_profile_from_source_profile_report


def test_build_source_ablation_report_returns_insufficient_data_without_events_or_labels(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")

    report = build_source_ablation_report(db, k_values=[5], rrf_k=60)

    assert report["status"] == "insufficient_data"
    assert report["confidence_intervals"] is None
    assert report["counts"]["sessions_total"] == 0
    assert report["counts"]["judged_results"] == 0


def test_source_ablation_single_source_metrics_reflect_labels(tmp_path: Path) -> None:
    db, track_ids = _ablation_library(tmp_path, ["candidate_a", "candidate_b"])
    session_id = _candidate_pool_session(db, track_ids["seed"])
    _candidate_event(db, session_id, track_ids["candidate_a"], {"mert": {"rank": 1, "score": 0.7}})
    _candidate_event(db, session_id, track_ids["candidate_b"], {"mert": {"rank": 2, "score": 0.6}})
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["candidate_a"], 3, source="manual")
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["candidate_b"], 0, source="manual")

    report = build_source_ablation_report(db, k_values=[1, 2], rrf_k=60)

    metrics = report["variants"]["source:mert"]["metrics"]
    assert report["status"] == "ok"
    assert metrics["mean_precision_at_1"] == 1.0
    assert metrics["hit_rate_at_1"] == 1.0
    assert metrics["mean_bad_suggestion_rate_at_2"] == 0.5


def test_source_ablation_rrf_all_promotes_multi_source_candidate(tmp_path: Path) -> None:
    db, track_ids = _ablation_library(tmp_path, ["shared", "mert_only"])
    session_id = _candidate_pool_session(db, track_ids["seed"])
    _candidate_event(
        db,
        session_id,
        track_ids["shared"],
        {"mert": {"rank": 2, "score": 0.5}, "maest": {"rank": 2, "score": 0.5}},
    )
    _candidate_event(db, session_id, track_ids["mert_only"], {"mert": {"rank": 1, "score": 0.9}})
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["shared"], 3, source="manual")
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["mert_only"], 1, source="manual")

    report = build_source_ablation_report(db, k_values=[1], rrf_k=60)

    rrf_session = report["sessions"][0]["variants"]["fusion:rrf_all"]
    assert rrf_session["ranked_candidate_track_ids"] == [track_ids["shared"], track_ids["mert_only"]]
    assert report["variants"]["fusion:rrf_all"]["metrics"]["mean_precision_at_1"] == 1.0


def test_source_ablation_leave_one_out_variants_include_deltas(tmp_path: Path) -> None:
    db, track_ids = _ablation_library(tmp_path, ["shared", "mert_only", "sonara_only", "clap_only"])
    session_id = _candidate_pool_session(db, track_ids["seed"])
    _candidate_event(
        db,
        session_id,
        track_ids["shared"],
        {
            "mert": {"rank": 2, "score": 0.6},
            "maest": {"rank": 1, "score": 0.8},
            "sonara": {"rank": 2, "score": 0.5},
            "clap": {"rank": 2, "score": 0.4},
        },
    )
    _candidate_event(db, session_id, track_ids["mert_only"], {"mert": {"rank": 1, "score": 0.9}})
    _candidate_event(db, session_id, track_ids["sonara_only"], {"sonara": {"rank": 1, "score": 0.9}})
    _candidate_event(db, session_id, track_ids["clap_only"], {"clap": {"rank": 1, "score": 0.9}})
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["shared"], 3, source="manual")
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["mert_only"], 0, source="manual")
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["sonara_only"], 2, source="manual")
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["clap_only"], 1, source="manual")

    report = build_source_ablation_report(db, k_values=[1], rrf_k=60)

    assert "fusion:rrf_without_mert" in report["variants"]
    assert "fusion:rrf_without_maest" in report["variants"]
    assert "fusion:rrf_without_sonara" in report["variants"]
    assert "fusion:rrf_without_clap" in report["variants"]
    deltas = report["variants"]["fusion:rrf_without_mert"]["delta_vs_fusion_rrf_all"]
    assert "mean_precision_at_1" in deltas
    assert report["variants"]["fusion:rrf_all"]["delta_vs_fusion_rrf_all"]["mean_precision_at_1"] == 0.0


def test_source_ablation_uses_rank_without_raw_source_score(tmp_path: Path) -> None:
    db, track_ids = _ablation_library(tmp_path, ["candidate_a", "candidate_b"])
    session_id = _candidate_pool_session(db, track_ids["seed"])
    _candidate_event(db, session_id, track_ids["candidate_a"], {"mert": {"rank": 2}, "maest": {"rank": 1}})
    _candidate_event(db, session_id, track_ids["candidate_b"], {"mert": {"rank": 1}})
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["candidate_a"], 3, source="manual")
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["candidate_b"], 0, source="manual")

    report = build_source_ablation_report(db, k_values=[1], rrf_k=60)

    ranked_track_ids = report["sessions"][0]["variants"]["fusion:rrf_all"]["ranked_candidate_track_ids"]
    assert ranked_track_ids == [track_ids["candidate_a"], track_ids["candidate_b"]]
    assert report["counts"]["sources_seen"] == ["mert", "maest"]


def test_source_ablation_with_score_profile_includes_weighted_rrf_variant(tmp_path: Path) -> None:
    db, track_ids = _ablation_library(tmp_path, ["candidate_a", "candidate_b"])
    session_id = _candidate_pool_session(db, track_ids["seed"])
    _candidate_event(db, session_id, track_ids["candidate_a"], {"mert": {"rank": 1}, "maest": {"rank": 10}})
    _candidate_event(db, session_id, track_ids["candidate_b"], {"mert": {"rank": 10}, "maest": {"rank": 1}})
    score_profile = _score_profile("maest_auto", {"mert": 0.1, "maest": 0.9})

    report = build_source_ablation_report(db, k_values=[1], rrf_k=60, score_profile=score_profile)

    assert report["status"] == "insufficient_data"
    assert report["score_profile"]["name"] == "maest_auto"
    assert "fusion:weighted_rrf:maest_auto" in report["variants"]
    assert report["variants"]["fusion:weighted_rrf:maest_auto"]["score_profile"]["weight_kind"] == "unsupervised_internal_profile"


def test_source_ablation_metrics_preserve_unjudged_rank_positions(tmp_path: Path) -> None:
    db, track_ids = _ablation_library(tmp_path, ["unjudged", "relevant"])
    session_id = _candidate_pool_session(db, track_ids["seed"])
    _candidate_event(db, session_id, track_ids["unjudged"], {"mert": {"rank": 1, "score": 0.9}})
    _candidate_event(db, session_id, track_ids["relevant"], {"mert": {"rank": 2, "score": 0.8}})
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["relevant"], 3, source="manual")

    report = build_source_ablation_report(db, k_values=[1, 2], rrf_k=60)

    source_variant = report["sessions"][0]["variants"]["source:mert"]
    metrics = report["variants"]["source:mert"]["metrics"]
    assert report["label_policy"] == LABEL_POLICY
    assert report["counts"]["judged_results"] == 1
    assert report["counts"]["unjudged_results"] == 1
    assert report["counts"]["label_policy"] == LABEL_POLICY
    assert source_variant["relevances_for_metrics"] == [0, 3]
    assert source_variant["label_policy"] == LABEL_POLICY
    assert metrics["hit_rate_at_1"] == 0.0
    assert metrics["mean_precision_at_1"] == 0.0
    assert metrics["hit_rate_at_2"] == 1.0


def test_source_ablation_judged_only_metrics_drop_unjudged_rank_positions(tmp_path: Path) -> None:
    db, track_ids = _ablation_library(tmp_path, ["unjudged", "relevant"])
    session_id = _candidate_pool_session(db, track_ids["seed"])
    _candidate_event(db, session_id, track_ids["unjudged"], {"mert": {"rank": 1, "score": 0.9}})
    _candidate_event(db, session_id, track_ids["relevant"], {"mert": {"rank": 2, "score": 0.8}})
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["relevant"], 3, source="manual")

    report = build_source_ablation_report(db, k_values=[1], rrf_k=60, judged_only=True)

    source_variant = report["sessions"][0]["variants"]["source:mert"]
    metrics = report["variants"]["source:mert"]["metrics"]
    assert report["status"] == "insufficient_data"
    assert report["evaluation_mode"] == "judged_validation"
    assert report["judged_pairs"] == 1
    assert source_variant["relevances_for_metrics"] == [3]
    assert metrics["mean_precision_at_1"] == 1.0
    assert metrics["mean_strong_match_rate_at_1"] == 1.0


def test_weighted_rrf_order_changes_when_profile_emphasizes_source(tmp_path: Path) -> None:
    db, track_ids = _ablation_library(tmp_path, ["candidate_a", "candidate_b"])
    session_id = _candidate_pool_session(db, track_ids["seed"])
    _candidate_event(db, session_id, track_ids["candidate_a"], {"mert": {"rank": 1}, "maest": {"rank": 10}})
    _candidate_event(db, session_id, track_ids["candidate_b"], {"mert": {"rank": 10}, "maest": {"rank": 1}})
    score_profile = _score_profile("maest_auto", {"mert": 0.1, "maest": 0.9})

    report = build_source_ablation_report(db, k_values=[1], rrf_k=60, score_profile=score_profile)

    rrf_ids = report["sessions"][0]["variants"]["fusion:rrf_all"]["ranked_candidate_track_ids"]
    weighted_ids = report["sessions"][0]["variants"]["fusion:weighted_rrf:maest_auto"]["ranked_candidate_track_ids"]
    assert rrf_ids == [track_ids["candidate_a"], track_ids["candidate_b"]]
    assert weighted_ids == [track_ids["candidate_b"], track_ids["candidate_a"]]


def _ablation_library(tmp_path: Path, candidate_names: list[str]) -> tuple[LibraryDatabase, dict[str, int]]:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {"seed": _track(db, tmp_path, "seed")}
    for candidate_name in candidate_names:
        track_ids[candidate_name] = _track(db, tmp_path, candidate_name)
    return db, track_ids


def _track(db: LibraryDatabase, tmp_path: Path, stem: str) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.replace("_", " ").title()},
    )


def _candidate_pool_session(db: LibraryDatabase, seed_track_id: int) -> int:
    return db.create_search_session(
        "evaluation_candidate_pool",
        [seed_track_id],
        {"feedback_source": "manual", "sources": ["mert", "maest", "sonara"]},
    )


def _candidate_event(
    db: LibraryDatabase,
    session_id: int,
    candidate_track_id: int,
    source_contributions: dict[str, dict[str, float | int]],
) -> None:
    db.record_search_result_event(
        session_id,
        candidate_track_id,
        rank=1,
        total_score=0.0,
        score_breakdown={"sources": source_contributions},
    )


def _score_profile(name: str, weights: dict[str, float]) -> ScoreProfile:
    return build_score_profile_from_source_profile_report(
        {
            "status": "ok",
            "profile_kind": "unsupervised_source_profile",
            "weight_kind": "unsupervised_internal_profile",
            "sources": list(weights),
            "seed_count": 1,
            "per_source": {},
            "consensus": {},
            "recommended_weights": {"weight_kind": "unsupervised_internal_profile", "weights": weights, "note": "test"},
            "warnings": [],
            "limitations": [],
        },
        name=name,
    )
