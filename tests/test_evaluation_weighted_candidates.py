from __future__ import annotations

import json
from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.candidates import CandidatePoolRow, CandidateSourceContribution
import dj_track_similarity.evaluation.weighted_candidates as weighted_candidates
from dj_track_similarity.evaluation.weighted_candidates import build_weighted_candidate_pool


def test_weighted_profile_ranks_high_weight_source_candidate_first(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db, tracks = _weighted_library(tmp_path)
    rows = (
        _candidate_row(db, tracks["seed"], tracks["mert_top"], {"mert": (1, 100.0)}),
        _candidate_row(db, tracks["seed"], tracks["maest_top"], {"maest": (1, 0.01)}),
    )
    monkeypatch.setattr(weighted_candidates, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_weighted_candidate_pool(
        db,
        [tracks["seed"]],
        _score_profile({"mert": 0.1, "maest": 0.9}),
        ["mert", "maest"],
        per_source=2,
        random_seed=123,
    )

    assert [row.candidate_track_id for row in result.rows] == [tracks["maest_top"], tracks["mert_top"]]
    assert result.rows[0].profile_score > result.rows[1].profile_score


def test_weighted_candidates_use_source_ranks_not_raw_scores(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db, tracks = _weighted_library(tmp_path)
    rows = (
        _candidate_row(db, tracks["seed"], tracks["mert_top"], {"maest": (2, 1000.0)}),
        _candidate_row(db, tracks["seed"], tracks["maest_top"], {"maest": (1, 0.01)}),
    )
    monkeypatch.setattr(weighted_candidates, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_weighted_candidate_pool(
        db,
        [tracks["seed"]],
        _score_profile({"maest": 1.0}),
        ["maest"],
        per_source=2,
        random_seed=123,
    )

    assert [row.candidate_track_id for row in result.rows] == [tracks["maest_top"], tracks["mert_top"]]


def test_weighted_candidates_transition_risk_weight_demotes_high_risk_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    tracks = {
        "seed": _track(db, tmp_path, "seed"),
        "risky": _track(db, tmp_path, "risky", bpm=200.0, musical_key="8B", energy=1.0),
        "safe": _track(db, tmp_path, "safe"),
    }
    rows = (
        _candidate_row(db, tracks["seed"], tracks["risky"], {"mert": (1, 0.9)}),
        _candidate_row(db, tracks["seed"], tracks["safe"], {"mert": (2, 0.8)}),
    )
    monkeypatch.setattr(weighted_candidates, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_weighted_candidate_pool(
        db,
        [tracks["seed"]],
        _score_profile({"mert": 1.0}),
        ["mert"],
        per_source=2,
        random_seed=123,
        rrf_k=1,
        transition_risk_weight=1.0,
    )

    assert [row.candidate_track_id for row in result.rows] == [tracks["safe"], tracks["risky"]]
    assert result.rows[1].transition_risk_penalty > 0.0
    assert result.rows[0].adjusted_score > result.rows[1].adjusted_score


def test_weighted_candidates_exclude_seed_and_tie_order_is_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db, tracks = _weighted_library(tmp_path)
    rows = (
        _candidate_row(db, tracks["seed"], tracks["seed"], {"mert": (1, 1.0)}),
        _candidate_row(db, tracks["seed"], tracks["mert_top"], {"mert": (1, 1.0)}),
        _candidate_row(db, tracks["seed"], tracks["maest_top"], {"mert": (1, 1.0)}),
    )
    monkeypatch.setattr(weighted_candidates, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    first = build_weighted_candidate_pool(db, [tracks["seed"]], _score_profile({"mert": 1.0}), ["mert"], 2, 19)
    second = build_weighted_candidate_pool(db, [tracks["seed"]], _score_profile({"mert": 1.0}), ["mert"], 2, 19)

    assert [row.candidate_track_id for row in first.rows] == [row.candidate_track_id for row in second.rows]
    assert tracks["seed"] not in {row.candidate_track_id for row in first.rows}
    assert [row.profile_rank for row in first.rows] == [1, 2]


def test_weighted_candidates_record_session_in_profile_rank_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db, tracks = _weighted_library(tmp_path)
    rows = (
        _candidate_row(db, tracks["seed"], tracks["mert_top"], {"mert": (1, 1.0)}),
        _candidate_row(db, tracks["seed"], tracks["maest_top"], {"maest": (1, 1.0)}),
    )
    monkeypatch.setattr(weighted_candidates, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_weighted_candidate_pool(
        db,
        [tracks["seed"]],
        _score_profile({"mert": 0.1, "maest": 0.9}),
        ["mert", "maest"],
        per_source=2,
        random_seed=123,
        record_session=True,
    )

    sessions = db.list_search_sessions_with_events()
    assert result.session_ids == (sessions[0]["id"],)
    assert sessions[0]["mode"] == "evaluation_weighted_candidate_pool"
    assert sessions[0]["request"]["transition_risk_version"] == "v2"
    assert [event["track_id"] for event in sessions[0]["events"]] == [row.candidate_track_id for row in result.rows]
    assert [event["rank"] for event in sessions[0]["events"]] == [1, 2]
    assert sessions[0]["events"][0]["score_breakdown"]["score_kind"] == "weighted_rrf"
    assert sessions[0]["events"][0]["score_breakdown"]["transition_risk_version"] == "v2"
    assert sessions[0]["events"][0]["score_breakdown"]["profile_weights"] == {"maest": 0.9, "mert": 0.1}
    assert "components" in sessions[0]["events"][0]["score_breakdown"]["weighted_rrf"]


def test_weighted_candidates_require_requested_sources_to_match_profile(tmp_path: Path) -> None:
    db, tracks = _weighted_library(tmp_path)
    profile = _score_profile({"mert": 0.5, "maest": 0.5})

    with pytest.raises(ValueError, match="not requested"):
        build_weighted_candidate_pool(db, [tracks["seed"]], profile, ["mert"], per_source=2, random_seed=123)

    with pytest.raises(ValueError, match="no score profile weight"):
        build_weighted_candidate_pool(db, [tracks["seed"]], _score_profile({"mert": 1.0}), ["mert", "maest"], per_source=2, random_seed=123)


def test_weighted_candidate_csv_row_contains_expected_manual_columns(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db, tracks = _weighted_library(tmp_path)
    rows = (_candidate_row(db, tracks["seed"], tracks["mert_top"], {"mert": (1, 0.9)}),)
    monkeypatch.setattr(weighted_candidates, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_weighted_candidate_pool(db, [tracks["seed"]], _score_profile({"mert": 1.0}), ["mert"], 1, 123)
    csv_row = result.rows[0].csv_row()

    assert csv_row["rating"] == ""
    assert csv_row["reason_tags"] == ""
    assert csv_row["notes"] == ""
    assert csv_row["source"] == "manual"
    assert csv_row["candidate_album"] == "Album mert_top"
    assert csv_row["transition_risk_weight"] == 0.0
    assert csv_row["transition_risk_penalty"] == 0.0
    assert json.loads(str(csv_row["sources_json"])) == {"mert": {"rank": 1, "score": 0.9}}
    assert json.loads(str(csv_row["score_profile_weights_json"])) == {"mert": 1.0}


def _weighted_library(tmp_path: Path) -> tuple[LibraryDatabase, dict[str, int]]:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    return db, {
        "seed": _track(db, tmp_path, "seed"),
        "mert_top": _track(db, tmp_path, "mert_top"),
        "maest_top": _track(db, tmp_path, "maest_top"),
    }


def _track(
    db: LibraryDatabase,
    tmp_path: Path,
    stem: str,
    *,
    bpm: float | None = 120.0,
    musical_key: str | None = "1A",
    energy: float | None = 0.5,
) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.replace("_", " ").title(), "album": f"Album {stem}"},
        bpm=bpm,
        musical_key=musical_key,
        energy=energy,
    )


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


def _score_profile(weights: dict[str, float]):
    from dj_track_similarity.evaluation.score_profiles import score_profile_from_dict

    return score_profile_from_dict(
        {
            "name": "auto",
            "profile_kind": "unsupervised_source_profile",
            "weight_kind": "unsupervised_internal_profile",
            "sources": list(weights),
            "weights": weights,
            "created_at": "2026-06-23T00:00:00Z",
            "source_report_summary": {"status": "ok"},
            "limitations": [
                "This is an unsupervised automatic internal score profile.",
                "These weights are not probability or calibrated confidence.",
                "This profile is not human ground truth.",
            ],
            "version": 1,
        },
    )
