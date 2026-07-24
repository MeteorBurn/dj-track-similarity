from __future__ import annotations

from dataclasses import replace
import json

import pytest

from dj_track_similarity.analysis_models import SonaraFeatureRow
from dj_track_similarity.evaluation.candidates import CandidatePoolRow, CandidateSourceContribution
from dj_track_similarity.evaluation.recorded_sessions import (
    load_current_evaluation_sessions,
)
import dj_track_similarity.evaluation.weighted_candidates as weighted_candidates
from dj_track_similarity.evaluation.weighted_candidates import build_weighted_candidate_pool
from dj_track_similarity.transition_diagnostics import TransitionTrack
from evaluation_v7_fixtures import EvaluationRepository


def test_weighted_profile_ranks_high_weight_source_candidate_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, tracks = _weighted_library()
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


def test_weighted_candidates_use_source_ranks_not_raw_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, tracks = _weighted_library()
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


def test_weighted_candidates_exclude_zero_weight_only_support_without_renormalizing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, tracks = _weighted_library()
    rows = (
        _candidate_row(
            db,
            tracks["seed"],
            tracks["mert_top"],
            {"mert": (1, 0.9)},
        ),
        _candidate_row(
            db,
            tracks["seed"],
            tracks["maest_top"],
            {"clap": (1, 0.9)},
        ),
    )
    monkeypatch.setattr(
        weighted_candidates,
        "generate_candidate_pool_rows",
        lambda _db, _request: (rows, ()),
    )

    result = build_weighted_candidate_pool(
        db,
        [tracks["seed"]],
        _score_profile({"mert": 0.25, "maest": 0.75, "clap": 0.0}),
        ["mert", "maest", "clap"],
        per_source=2,
        random_seed=123,
        rrf_k=60,
    )

    assert [row.candidate_track_id for row in result.rows] == [tracks["mert_top"]]
    assert result.rows[0].raw_rrf_score == pytest.approx(0.25 / 61.0)


def test_weighted_candidates_zero_weight_source_does_not_change_transition_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, tracks = _weighted_library()
    mert_only_rows = (
        _candidate_row(
            db,
            tracks["seed"],
            tracks["mert_top"],
            {"mert": (2, 0.8)},
        ),
        _candidate_row(
            db,
            tracks["seed"],
            tracks["maest_top"],
            {"mert": (1, 0.9)},
        ),
    )
    rows_with_zero_weight_source = (
        _candidate_row(
            db,
            tracks["seed"],
            tracks["mert_top"],
            {"mert": (2, 0.8), "maest": (1, 0.9)},
        ),
        mert_only_rows[1],
    )

    def candidate_rows(_db, request):
        rows = (
            rows_with_zero_weight_source
            if "maest" in request.sources
            else mert_only_rows
        )
        return rows, ()

    monkeypatch.setattr(
        weighted_candidates,
        "generate_candidate_pool_rows",
        candidate_rows,
    )
    common = {
        "db": db,
        "seed_track_ids": [tracks["seed"]],
        "per_source": 2,
        "random_seed": 123,
        "rrf_k": 60,
        "transition_risk_weight": 1.0,
    }

    mert_only = build_weighted_candidate_pool(
        profile=_score_profile({"mert": 1.0}),
        sources=["mert"],
        **common,
    )
    zero_weight_maest = build_weighted_candidate_pool(
        profile=_score_profile({"mert": 1.0, "maest": 0.0}),
        sources=["mert", "maest"],
        **common,
    )

    assert [row.candidate_track_id for row in mert_only.rows] == [
        tracks["maest_top"],
        tracks["mert_top"],
    ]
    assert [row.candidate_track_id for row in zero_weight_maest.rows] == [
        tracks["maest_top"],
        tracks["mert_top"],
    ]
    for baseline, with_zero_weight_source in zip(
        mert_only.rows,
        zero_weight_maest.rows,
        strict=True,
    ):
        assert with_zero_weight_source.raw_rrf_score == pytest.approx(
            baseline.raw_rrf_score
        )
        assert with_zero_weight_source.transition_risk == pytest.approx(
            baseline.transition_risk
        )
        assert with_zero_weight_source.adjusted_score == pytest.approx(
            baseline.adjusted_score
        )


def test_weighted_candidates_transition_risk_weight_demotes_high_risk_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = EvaluationRepository()
    tracks = {
        "seed": 1,
        "risky": 2,
        "safe": 3,
    }
    db.summaries[tracks["risky"]] = _summary_with_tags(
        db,
        tracks["risky"],
        bpm=200.0,
        musical_key="8B",
    )
    db.sonara_rows[tracks["risky"]] = _sonara_with_energy(
        db,
        tracks["risky"],
        energy=1.0,
        bpm=200.0,
        musical_key="8B",
    )
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
        rrf_k=60,
        transition_risk_weight=1.0,
    )

    assert [row.candidate_track_id for row in result.rows] == [tracks["safe"], tracks["risky"]]
    assert result.rows[1].transition_risk_penalty > 0.0
    assert result.rows[0].adjusted_score > result.rows[1].adjusted_score


def test_weighted_candidates_exclude_seed_and_tie_order_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, tracks = _weighted_library()
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


def test_weighted_candidates_record_session_in_profile_rank_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, tracks = _weighted_library()
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

    sessions = load_current_evaluation_sessions(db)
    assert result.session_ids == (sessions[0]["id"],)
    assert sessions[0]["mode"] == "evaluation_weighted_candidate_pool"
    assert sessions[0]["request"]["transition_risk_version"] == "v2"
    assert [event["track_id"] for event in sessions[0]["events"]] == [row.candidate_track_id for row in result.rows]
    assert [event["rank"] for event in sessions[0]["events"]] == [1, 2]
    assert sessions[0]["events"][0]["score_breakdown"]["score_kind"] == "weighted_rrf"
    assert sessions[0]["events"][0]["score_breakdown"]["transition_risk_version"] == "v2"
    assert sessions[0]["events"][0]["score_breakdown"]["profile_weights"] == {"maest": 0.9, "mert": 0.1}
    assert "components" in sessions[0]["events"][0]["score_breakdown"]["weighted_rrf"]


def test_weighted_candidates_require_requested_sources_to_match_profile() -> None:
    db, tracks = _weighted_library()
    profile = _score_profile({"mert": 0.5, "maest": 0.5})

    with pytest.raises(ValueError, match="not requested"):
        build_weighted_candidate_pool(db, [tracks["seed"]], profile, ["mert"], per_source=2, random_seed=123)

    with pytest.raises(ValueError, match="no score profile weight"):
        build_weighted_candidate_pool(db, [tracks["seed"]], _score_profile({"mert": 1.0}), ["mert", "maest"], per_source=2, random_seed=123)


def test_weighted_candidate_csv_row_contains_expected_manual_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db, tracks = _weighted_library()
    db.summaries[tracks["mert_top"]] = replace(
        db.summaries[tracks["mert_top"]],
        album="Album mert_top",
        tag_key="2B",
    )
    db.sonara_rows[tracks["mert_top"]] = _sonara_with_energy(
        db,
        tracks["mert_top"],
        energy=0.9,
        bpm=90.0,
        musical_key="2B",
    )
    rows = (_candidate_row(db, tracks["seed"], tracks["mert_top"], {"mert": (1, 0.9)}),)
    monkeypatch.setattr(weighted_candidates, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_weighted_candidate_pool(db, [tracks["seed"]], _score_profile({"mert": 1.0}), ["mert"], 1, 123)
    csv_row = result.rows[0].csv_row()

    assert csv_row["rating"] == ""
    assert csv_row["reason_tags"] == ""
    assert csv_row["notes"] == ""
    assert csv_row["source"] == "manual"
    assert csv_row["candidate_album"] == "Album mert_top"
    assert csv_row["candidate_bpm"] == "90.0"
    assert csv_row["candidate_musical_key"] == "2B"
    assert csv_row["candidate_energy"] == "0.9"
    assert csv_row["transition_risk_weight"] == 0.0
    assert csv_row["transition_risk_penalty"] == 0.0
    assert json.loads(str(csv_row["sources_json"])) == {
        "mert": {
            "contract_hash": db.outputs[("mert", "embedding")].contract_hash,
            "rank": 1,
            "score": 0.9,
        }
    }
    assert json.loads(str(csv_row["score_profile_weights_json"])) == {"mert": 1.0}


def _weighted_library() -> tuple[EvaluationRepository, dict[str, int]]:
    db = EvaluationRepository()
    return db, {
        "seed": 1,
        "mert_top": 2,
        "maest_top": 3,
    }


def _candidate_row(
    db: EvaluationRepository,
    seed_id: int,
    candidate_id: int,
    contributions: dict[str, tuple[int, float]],
) -> CandidatePoolRow:
    return CandidatePoolRow(
        seed_track=_transition_track(db, seed_id),
        candidate_track=_transition_track(db, candidate_id),
        blind_rank=1,
        source_contributions={
            source: CandidateSourceContribution(
                rank=rank,
                score=score,
                contract_hash=db.outputs[
                    (source, "core" if source == "sonara" else "embedding")
                ].contract_hash,
            )
            for source, (rank, score) in contributions.items()
        },
    )


def _transition_track(
    db: EvaluationRepository,
    track_id: int,
) -> TransitionTrack:
    return TransitionTrack(
        identity=db.identities[track_id],
        summary=db.summaries[track_id],
        sonara=db.sonara_rows.get(track_id),
    )


def _summary_with_tags(
    db: EvaluationRepository,
    track_id: int,
    *,
    bpm: float,
    musical_key: str,
):
    return replace(
        db.summaries[track_id],
        tag_bpm=bpm,
        tag_key=musical_key,
    )


def _sonara_with_energy(
    db: EvaluationRepository,
    track_id: int,
    *,
    energy: float,
    bpm: float | None = None,
    musical_key: str | None = None,
) -> SonaraFeatureRow:
    current = db.sonara_rows[track_id]
    values = dict(current.values)
    values["energy_score"] = energy
    if bpm is not None:
        values["detected_bpm"] = bpm
    if musical_key is not None:
        values["detected_key_camelot"] = musical_key
    return SonaraFeatureRow(
        target=current.target,
        output=current.output,
        values=values,
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
