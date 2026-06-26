from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import dj_track_similarity.hybrid_search as hybrid_search
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.candidates import CandidatePoolRow, CandidateSourceContribution
from dj_track_similarity.evaluation.score_profile_optimizer import (
    build_promoted_score_profile_payload,
    build_score_profile_optimizer_report,
)
from dj_track_similarity.hybrid_search import build_hybrid_search_preview


def test_hybrid_feedback_optimizer_promotion_e2e_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    rejected_db, _rejected_ids = _build_hybrid_feedback_fixture(monkeypatch, tmp_path, seed_count=50, name="rejected.sqlite")
    rejected = build_score_profile_optimizer_report(rejected_db, grid_step=0.5, bootstrap_samples=0)

    assert rejected["status"] == "rejected"
    assert rejected["decision"] == "insufficient_matched_judged_pairs"
    assert rejected["judged_pairs"] == 100
    assert rejected["matched_judged_examples"] == 100

    candidate_db, candidate_ids = _build_hybrid_feedback_fixture(monkeypatch, tmp_path, seed_count=100, name="candidate.sqlite")
    candidate = build_score_profile_optimizer_report(candidate_db, grid_step=0.5, bootstrap_samples=0)

    assert candidate["status"] == "ok"
    assert candidate["judged_pairs"] == 200
    assert candidate["matched_judged_examples"] == 200
    assert candidate["candidate_profile_allowed"] is True
    assert candidate["can_update_defaults"] is False
    assert candidate["weights"]["mert"] > candidate["weights"]["maest"]
    assert _classifier_adjusted_event_count(candidate_db, "classifier_deep_groove") == 100
    with pytest.raises(ValueError, match="500 matched judged-pair"):
        build_promoted_score_profile_payload(candidate)

    promotable_db, promotable_ids = _build_hybrid_feedback_fixture(monkeypatch, tmp_path, seed_count=250, name="promotable.sqlite")
    promotable = build_score_profile_optimizer_report(promotable_db, grid_step=0.5, bootstrap_samples=0)
    promoted_payload = build_promoted_score_profile_payload(promotable)

    assert promotable["status"] == "ok"
    assert promotable["judged_pairs"] == 500
    assert promotable["can_update_defaults"] is True
    assert promoted_payload["weights"] == promotable["weights"]
    assert promoted_payload["sources"] == promotable["sources"]
    assert promoted_payload["can_apply_as_default"] is True

    score_profile = _score_profile_from_optimizer_report(promotable)
    profiled_preview = build_hybrid_search_preview(
        promotable_db,
        seed_track_ids=[promotable_ids["seed_ids"][0]],
        sources=score_profile["sources"],
        score_profile=score_profile,
        per_source=2,
        limit=2,
    )
    assert profiled_preview.results
    with pytest.raises(ValueError, match="score_profile sources must match requested sources exactly"):
        build_hybrid_search_preview(
            promotable_db,
            seed_track_ids=[promotable_ids["seed_ids"][0]],
            sources=["mert"],
            score_profile=score_profile,
            per_source=2,
            limit=2,
        )


def _build_hybrid_feedback_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    seed_count: int,
    name: str,
) -> tuple[LibraryDatabase, dict[str, list[int]]]:
    db = LibraryDatabase(tmp_path / name)
    pairs: dict[int, tuple[int, int]] = {}
    seed_ids: list[int] = []
    for index in range(seed_count):
        seed_id = _track(db, tmp_path, f"{name}_seed_{index}")
        bad_id = _track(db, tmp_path, f"{name}_bad_{index}")
        good_id = _track(db, tmp_path, f"{name}_good_{index}")
        db.save_classifier_score(
            good_id,
            classifier="deep_groove",
            score=0.9,
            label="positive",
            confidence=0.9,
            probabilities={"positive": 0.9},
            feature_set="combined",
            model_id="old-model",
        )
        pairs[seed_id] = (good_id, bad_id)
        seed_ids.append(seed_id)

    monkeypatch.setattr(
        hybrid_search,
        "promoted_classifiers",
        lambda: [
            {
                "classifier_key": "deep_groove",
                "manifest_status": "valid",
                "production_status": "valid_calibrated",
                "model_id": "new-model",
                "hybrid_signal": {
                    "role": "preference_boost",
                    "axis": "groove",
                    "label": "Boost deep groove",
                    "default_preference": 0.5,
                    "allowed_modes": ["hybrid"],
                    "missing_score_policy": "neutral",
                },
                "hybrid_signal_source": "manifest",
            }
        ],
    )

    def candidate_rows(_db: LibraryDatabase, request: Any):
        seed_id = int(request.seed_track_ids[0])
        good_id, bad_id = pairs[seed_id]
        return (
            _candidate_row(db, seed_id, good_id, {"mert": (1, 0.95), "maest": (10, 0.25)}),
            _candidate_row(db, seed_id, bad_id, {"mert": (10, 0.25), "maest": (1, 0.95)}),
        ), ()

    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", candidate_rows)

    first_preview_warnings: tuple[str, ...] | None = None
    for seed_id in seed_ids:
        good_id, bad_id = pairs[seed_id]
        preview = build_hybrid_search_preview(
            db,
            seed_track_ids=[seed_id],
            sources=["mert", "maest"],
            per_source=2,
            limit=2,
            classifier_preferences={"deep_groove": 0.5},
            record_session=True,
        )
        first_preview_warnings = first_preview_warnings or preview.warnings
        row_by_track = {row.track.id: row for row in preview.results}
        assert row_by_track[good_id].classifier_support["deep_groove"]["available"] is True
        assert row_by_track[good_id].classifier_support["deep_groove"]["stale"] is True
        assert "classifier_deep_groove" in row_by_track[good_id].score_breakdown
        assert row_by_track[bad_id].classifier_support["deep_groove"]["available"] is False
        assert "classifier_deep_groove" not in row_by_track[bad_id].score_breakdown
        db.upsert_track_pair_feedback(seed_id, good_id, 3, source="hybrid_ui")
        db.upsert_track_pair_feedback(seed_id, bad_id, 0, source="hybrid_ui")

    assert first_preview_warnings is not None
    assert any("deep_groove" in warning and "stale" in warning.lower() for warning in first_preview_warnings)
    return db, {"seed_ids": seed_ids}


def _candidate_row(db: LibraryDatabase, seed_id: int, candidate_id: int, contributions: dict[str, tuple[int, float]]) -> CandidatePoolRow:
    return CandidatePoolRow(
        seed_track=db.get_track(seed_id),
        candidate_track=db.get_track(candidate_id),
        blind_rank=1,
        source_contributions={
            source: CandidateSourceContribution(rank=rank, score=score)
            for source, (rank, score) in contributions.items()
        },
    )


def _classifier_adjusted_event_count(db: LibraryDatabase, breakdown_key: str) -> int:
    count = 0
    for session in db.list_search_sessions_with_events():
        for event in session["events"]:
            score_breakdown = event.get("score_breakdown") or {}
            if breakdown_key in score_breakdown.get("score_breakdown", {}):
                count += 1
    return count


def _score_profile_from_optimizer_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": report["profile_name"],
        "profile_kind": "unsupervised_source_profile",
        "weight_kind": "unsupervised_internal_profile",
        "sources": list(report["sources"]),
        "weights": dict(report["weights"]),
        "created_at": report["created_at"],
        "source_report_summary": {
            "source": "optimizer_e2e_fixture",
            "judged_pairs": report["judged_pairs"],
        },
        "limitations": [
            "This score profile is unsupervised ranking evidence.",
            "It is not probability or calibrated confidence.",
            "It is not human ground truth; feedback only validates recorded candidate pools.",
        ],
        "version": 1,
    }


def _track(db: LibraryDatabase, tmp_path: Path, stem: str) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.replace("_", " ").title()},
    )
