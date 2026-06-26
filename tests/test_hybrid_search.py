from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.candidates import CandidatePoolRow, CandidateSourceContribution
import dj_track_similarity.hybrid_search as hybrid_search
from dj_track_similarity.hybrid_explanation import MATCH_CHARACTER_AXES
from dj_track_similarity.hybrid_search import build_hybrid_search_preview

RISK_BREAKDOWN_KEYS = {
    "bpm",
    "tonal",
    "energy_jump",
    "density_jump",
    "texture_clash",
    "mood_clash",
    "vocal_conflict",
    "source_disagreement",
    "confidence_missingness",
}


def test_hybrid_search_uses_equal_weights_by_default(tmp_path: Path) -> None:
    db, track_ids = _hybrid_library(tmp_path)

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        per_source=3,
        limit=3,
    )

    assert result.weights_used == {"mert": 0.5, "maest": 0.5}
    assert result.sources == ("mert", "maest")
    assert len(result.results) == 3
    assert all(row.score <= 1.0 for row in result.results)
    assert result.results[0].transition_risk is not None
    assert result.results[0].transition_diagnostics["supporting_seed_count"] == 1
    assert "source_disagreement_risk" in result.results[0].transition_diagnostics["components"]
    assert result.results[0].total_score == result.results[0].adjusted_score
    assert result.results[0].calibrated_score is None
    assert tuple(result.results[0].match_character) == MATCH_CHARACTER_AXES
    assert set(result.results[0].risk_breakdown) == RISK_BREAKDOWN_KEYS


def test_hybrid_search_custom_weights_change_order(tmp_path: Path) -> None:
    db, track_ids = _hybrid_library(tmp_path)

    mert_weighted = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        weights={"mert": 1.0, "maest": 0.0},
        per_source=3,
        limit=3,
    )
    maest_weighted = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        weights={"mert": 0.0, "maest": 1.0},
        per_source=3,
        limit=3,
    )

    assert mert_weighted.results[0].track.id == track_ids["mert_top"]
    assert maest_weighted.results[0].track.id == track_ids["maest_top"]
    assert mert_weighted.weights_used == {"mert": 1.0, "maest": 0.0}


def test_hybrid_search_zero_transition_risk_weight_keeps_rrf_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed", bpm=120.0, musical_key="1A", energy=0.5),
        "risky": _track(db, tmp_path, "risky", bpm=200.0, musical_key="8B", energy=1.0),
        "safe": _track(db, tmp_path, "safe", bpm=120.0, musical_key="1A", energy=0.5),
    }
    rows = (
        _candidate_row(db, track_ids["seed"], track_ids["risky"], {"mert": (1, 0.9)}),
        _candidate_row(db, track_ids["seed"], track_ids["safe"], {"mert": (2, 0.8)}),
    )
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert"],
        per_source=2,
        limit=2,
        rrf_k=1,
        transition_risk_weight=0.0,
    )

    assert [row.track.id for row in result.results] == [track_ids["risky"], track_ids["safe"]]
    assert result.results[0].score == pytest.approx(1.0)
    assert result.results[0].adjusted_score == pytest.approx(result.results[0].score)
    assert result.results[0].transition_risk_penalty == 0.0


def test_hybrid_search_transition_risk_weight_demotes_high_risk_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed", bpm=120.0, musical_key="1A", energy=0.5),
        "risky": _track(db, tmp_path, "risky", bpm=200.0, musical_key="8B", energy=1.0),
        "safe": _track(db, tmp_path, "safe", bpm=120.0, musical_key="1A", energy=0.5),
    }
    rows = (
        _candidate_row(db, track_ids["seed"], track_ids["risky"], {"mert": (1, 0.9)}),
        _candidate_row(db, track_ids["seed"], track_ids["safe"], {"mert": (2, 0.8)}),
    )
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert"],
        per_source=2,
        limit=2,
        rrf_k=1,
        transition_risk_weight=1.0,
    )

    assert [row.track.id for row in result.results] == [track_ids["safe"], track_ids["risky"]]
    assert result.results[1].transition_risk_penalty > 0.0
    assert result.results[0].adjusted_score > result.results[1].adjusted_score


def test_hybrid_search_missing_transition_risk_has_no_penalty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "candidate": _track(db, tmp_path, "candidate"),
    }
    rows = (_candidate_row(db, track_ids["seed"], track_ids["candidate"], {"mert": (1, 0.9)}),)
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))
    monkeypatch.setattr(
        hybrid_search,
        "_candidate_transition_diagnostics",
        lambda _candidate, *, seed_tracks, sources, risk_version, classifier_risk_weights: {"transition_risk": None, "warnings": []},
    )

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert"],
        per_source=1,
        limit=1,
        transition_risk_weight=1.0,
    )

    assert result.results[0].transition_risk is None
    assert result.results[0].transition_risk_penalty == 0.0
    assert result.results[0].adjusted_score == pytest.approx(1.0)


def test_hybrid_classifier_preferences_are_neutral_when_scores_are_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "candidate": _track(db, tmp_path, "candidate"),
    }
    rows = (_candidate_row(db, track_ids["seed"], track_ids["candidate"], {"mert": (1, 0.9)}),)
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    baseline = build_hybrid_search_preview(db, seed_track_ids=[track_ids["seed"]], sources=["mert"], per_source=1, limit=1)
    controlled = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert"],
        per_source=1,
        limit=1,
        classifier_preferences={"break_energy": 1.0},
    )

    assert controlled.results[0].score == pytest.approx(baseline.results[0].score)
    assert "classifier_break_energy" not in controlled.results[0].score_breakdown
    assert controlled.results[0].classifier_support["break_energy"]["available"] is False
    assert not any("break_energy" in line for line in controlled.results[0].explanation)
    assert any("break_energy" in warning and "neutral" in warning for warning in controlled.warnings)


def test_hybrid_classifier_preferences_are_scoped_by_classifier_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "candidate": _track(db, tmp_path, "candidate"),
    }
    db.save_classifier_score(
        track_ids["candidate"],
        classifier="abstract_edge",
        score=1.0,
        label="positive",
        confidence=1.0,
        probabilities={"positive": 1.0},
        feature_set="combined",
        model_id="test",
    )
    rows = (_candidate_row(db, track_ids["seed"], track_ids["candidate"], {"mert": (1, 0.9)}),)
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    wrong_key = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert"],
        per_source=1,
        limit=1,
        classifier_preferences={"break_energy": 1.0},
    )
    matching_key = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert"],
        per_source=1,
        limit=1,
        classifier_preferences={"abstract_edge": 1.0},
    )

    assert wrong_key.results[0].adjusted_score == pytest.approx(1.0)
    assert matching_key.results[0].adjusted_score == pytest.approx(1.0 + hybrid_search.CLASSIFIER_SCORE_ADJUSTMENT_SCALE)
    assert matching_key.results[0].score_breakdown["classifier_abstract_edge"]["contribution"] > 0
    assert matching_key.results[0].classifier_support["abstract_edge"]["available"] is True


def test_hybrid_classifier_support_uses_manifest_signal_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "candidate": _track(db, tmp_path, "candidate"),
    }
    db.save_classifier_score(
        track_ids["candidate"],
        classifier="deep_groove",
        score=0.9,
        label="positive",
        confidence=0.9,
        probabilities={"positive": 0.9},
        feature_set="combined",
        model_id="groove-v2",
    )
    rows = (_candidate_row(db, track_ids["seed"], track_ids["candidate"], {"mert": (1, 0.9)}),)
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))
    monkeypatch.setattr(
        hybrid_search,
        "promoted_classifiers",
        lambda: [
            {
                "classifier_key": "deep_groove",
                "manifest_status": "valid",
                "production_status": "valid_calibrated",
                "model_id": "groove-v2",
                "hybrid_signal": {
                    "role": "preference_boost",
                    "axis": "groove",
                    "label": "Boost deep groove",
                    "description": "Uses stored deep_groove scores as a groove preference.",
                    "default_preference": 0.55,
                    "allowed_modes": ["hybrid"],
                    "missing_score_policy": "neutral",
                },
                "hybrid_signal_source": "manifest",
            }
        ],
    )

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert"],
        per_source=1,
        limit=1,
        classifier_preferences={"deep_groove": 0.55},
    )

    support = result.results[0].classifier_support["deep_groove"]
    assert support["available"] is True
    assert support["role"] == "preference_boost"
    assert support["axis"] == "groove"
    assert support["label"] == "Boost deep groove"
    assert support["fresh"] is True
    assert support["stale"] is False
    assert support["production_status"] == "valid_calibrated"
    assert result.results[0].score_breakdown["classifier_deep_groove"]["contribution"] > 0
    assert any("Boost deep groove" in line and "groove" in line for line in result.results[0].explanation)


def test_hybrid_classifier_support_marks_stale_scores_without_dropping_signal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "candidate": _track(db, tmp_path, "candidate"),
    }
    db.save_classifier_score(
        track_ids["candidate"],
        classifier="deep_groove",
        score=0.9,
        label="positive",
        confidence=0.9,
        probabilities={"positive": 0.9},
        feature_set="combined",
        model_id="old-model",
    )
    rows = (_candidate_row(db, track_ids["seed"], track_ids["candidate"], {"mert": (1, 0.9)}),)
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))
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
                    "default_preference": 0.55,
                    "allowed_modes": ["hybrid"],
                    "missing_score_policy": "neutral",
                },
                "hybrid_signal_source": "manifest",
            }
        ],
    )

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert"],
        per_source=1,
        limit=1,
        classifier_preferences={"deep_groove": 0.55},
    )

    support = result.results[0].classifier_support["deep_groove"]
    assert support["available"] is True
    assert support["fresh"] is False
    assert support["stale"] is True
    assert result.results[0].score_breakdown["classifier_deep_groove"]["contribution"] > 0
    assert any("deep_groove" in warning and "stale" in warning.lower() for warning in result.warnings)


def test_hybrid_risk_classifier_signal_feeds_risk_breakdown_and_warnings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "candidate": _track(db, tmp_path, "candidate"),
    }
    db.save_classifier_score(
        track_ids["candidate"],
        classifier="harsh_noise",
        score=0.8,
        label="positive",
        confidence=0.8,
        probabilities={"positive": 0.8},
        feature_set="combined",
        model_id="noise-v1",
    )
    rows = (_candidate_row(db, track_ids["seed"], track_ids["candidate"], {"mert": (1, 0.9)}),)
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))
    monkeypatch.setattr(
        hybrid_search,
        "promoted_classifiers",
        lambda: [
            {
                "classifier_key": "harsh_noise",
                "manifest_status": "valid",
                "production_status": "valid_calibrated",
                "model_id": "noise-v1",
                "hybrid_signal": {
                    "role": "risk_penalty",
                    "axis": "texture",
                    "label": "Penalize harsh noise",
                    "default_risk_weight": 0.75,
                    "allowed_modes": ["hybrid"],
                    "missing_score_policy": "neutral",
                },
                "hybrid_signal_source": "manifest",
            }
        ],
    )

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert"],
        per_source=1,
        limit=1,
        classifier_risk_weights={"harsh_noise": 0.75},
    )

    row = result.results[0]
    support = row.classifier_support["harsh_noise"]
    assert support["role"] == "risk_penalty"
    assert support["axis"] == "texture"
    assert support["risk_contribution"] == pytest.approx(0.6)
    assert row.risk_breakdown["texture_clash"] == pytest.approx(0.6)
    assert any("Penalize harsh noise" in warning and "texture" in warning for warning in row.warnings)


def test_hybrid_search_excludes_zero_weight_source_only_candidates(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "positive_source": _track(db, tmp_path, "positive_source"),
        "zero_source_only": _track(db, tmp_path, "zero_source_only"),
    }
    rows = (
        _candidate_row(db, track_ids["seed"], track_ids["positive_source"], {"mert": (1, 0.9)}),
        _candidate_row(db, track_ids["seed"], track_ids["zero_source_only"], {"maest": (1, 0.99)}),
    )
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        weights={"mert": 1.0, "maest": 0.0},
        per_source=2,
        limit=10,
    )

    assert [row.track.id for row in result.results] == [track_ids["positive_source"]]
    assert all(row.raw_rrf_score > 0 for row in result.results)


def test_hybrid_search_excludes_seed_track(tmp_path: Path) -> None:
    db, track_ids = _hybrid_library(tmp_path)

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert"],
        per_source=4,
        limit=10,
    )

    assert track_ids["seed"] not in {row.track.id for row in result.results}


@pytest.mark.parametrize(
    "weights",
    (
        {"mert": -1.0, "maest": 2.0},
        {"mert": 0.0, "maest": 0.0},
        {"mert": 1.0},
    ),
)
def test_hybrid_search_rejects_invalid_weights(tmp_path: Path, weights: dict[str, float]) -> None:
    db, track_ids = _hybrid_library(tmp_path)

    with pytest.raises(ValueError):
        build_hybrid_search_preview(
            db,
            seed_track_ids=[track_ids["seed"]],
            sources=["mert", "maest"],
            weights=weights,
        )


def test_hybrid_search_rejects_duplicate_normalized_weight_keys(tmp_path: Path) -> None:
    db, track_ids = _hybrid_library(tmp_path)

    with pytest.raises(ValueError, match="duplicate normalized source"):
        build_hybrid_search_preview(
            db,
            seed_track_ids=[track_ids["seed"]],
            sources=["mert", "maest"],
            weights={"mert": 0.2, " MERT ": 0.3, "maest": 0.5},
        )


def test_hybrid_search_preserves_source_supporting_seed_ids_after_best_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed_a": _track(db, tmp_path, "seed_a"),
        "seed_b": _track(db, tmp_path, "seed_b"),
        "candidate": _track(db, tmp_path, "candidate"),
    }
    rows = (
        _candidate_row(db, track_ids["seed_a"], track_ids["candidate"], {"mert": (2, 0.4)}),
        _candidate_row(db, track_ids["seed_b"], track_ids["candidate"], {"mert": (1, 0.9)}),
    )
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed_a"], track_ids["seed_b"]],
        sources=["mert"],
        weights={"mert": 1.0},
        per_source=2,
        limit=5,
    )

    diagnostics = result.results[0].diagnostics
    source_support = diagnostics["source_support"]["mert"]
    assert diagnostics["supporting_seed_track_ids"] == [track_ids["seed_a"], track_ids["seed_b"]]
    assert source_support["best_seed_track_id"] == track_ids["seed_b"]
    assert source_support["supporting_seed_track_ids"] == [track_ids["seed_a"], track_ids["seed_b"]]
    assert result.results[0].transition_diagnostics["supporting_seed_count"] == 2


def test_hybrid_search_transition_diagnostics_use_supporting_seed_scope(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed_a": _track(db, tmp_path, "seed_a", bpm=120.0, musical_key="8A", energy=0.5),
        "seed_b": _track(db, tmp_path, "seed_b", bpm=180.0, musical_key="9A", energy=1.0),
        "candidate": _track(db, tmp_path, "candidate", bpm=120.0, musical_key="8A", energy=0.5),
    }
    rows = (_candidate_row(db, track_ids["seed_a"], track_ids["candidate"], {"mert": (1, 0.9)}),)
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed_a"], track_ids["seed_b"]],
        sources=["mert", "maest"],
        per_source=2,
        limit=5,
    )

    transition_diagnostics = result.results[0].transition_diagnostics
    components = transition_diagnostics["components"]
    component_values = [value for value in components.values() if value is not None]
    assert transition_diagnostics["supporting_seed_track_ids"] == [track_ids["seed_a"]]
    assert transition_diagnostics["supporting_seed_count"] == 1
    assert transition_diagnostics["seed_scope"] == "candidate_supporting_seeds"
    assert components["bpm_risk"] == 0.0
    assert components["source_disagreement_risk"] == 0.0
    assert transition_diagnostics["transition_risk"] == pytest.approx(sum(component_values) / len(component_values))


def test_hybrid_search_configured_clap_without_rows_does_not_inflate_source_risk(tmp_path: Path) -> None:
    db, track_ids = _hybrid_library(tmp_path)

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest", "clap"],
        per_source=3,
        limit=3,
        transition_risk_weight=1.0,
    )

    shared_row = next(row for row in result.results if row.track.id == track_ids["shared"])
    assert result.weights_used == {"mert": pytest.approx(1 / 3), "maest": pytest.approx(1 / 3), "clap": pytest.approx(1 / 3)}
    assert any("source=clap returned no candidates" in warning for warning in result.warnings)
    assert set(shared_row.score_breakdown) == {"mert", "maest"}
    assert shared_row.source_support["clap"]["available"] is False
    assert shared_row.transition_diagnostics["components"]["source_disagreement_risk"] == 0.0


def test_hybrid_search_transition_risk_matches_aggregated_components(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed_a": _track(db, tmp_path, "seed_a", bpm=120.0, musical_key="8A", energy=0.0),
        "seed_b": _track(db, tmp_path, "seed_b", bpm=None, musical_key="9A", energy=0.4),
        "candidate": _track(db, tmp_path, "candidate", bpm=126.0, musical_key="8A", energy=1.0),
    }
    rows = (
        _candidate_row(db, track_ids["seed_a"], track_ids["candidate"], {"mert": (1, 0.9)}),
        _candidate_row(db, track_ids["seed_b"], track_ids["candidate"], {"mert": (2, 0.8)}),
    )
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_hybrid_search_preview(
        db,
        seed_track_ids=[track_ids["seed_a"], track_ids["seed_b"]],
        sources=["mert", "maest"],
        per_source=2,
        limit=5,
    )

    transition_diagnostics = result.results[0].transition_diagnostics
    components = transition_diagnostics["components"]
    component_values = [value for value in components.values() if value is not None]
    assert transition_diagnostics["supporting_seed_count"] == 2
    assert transition_diagnostics["transition_risk"] == pytest.approx(sum(component_values) / len(component_values))
    assert result.results[0].transition_risk == transition_diagnostics["transition_risk"]


def test_hybrid_search_returns_empty_results_with_warnings_when_sources_lack_coverage(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1, metadata={"title": "Seed"})

    result = build_hybrid_search_preview(db, seed_track_ids=[seed_id], sources=["mert"], per_source=5)

    assert result.results == ()
    assert any("source=mert returned no candidates" in warning for warning in result.warnings)
    assert any("produced no candidate rows" in warning for warning in result.warnings)


def _hybrid_library(tmp_path: Path) -> tuple[LibraryDatabase, dict[str, int]]:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "mert_top": _track(db, tmp_path, "mert_top"),
        "maest_top": _track(db, tmp_path, "maest_top"),
        "shared": _track(db, tmp_path, "shared"),
    }
    _save_embeddings(db, track_ids["seed"], mert=[1.0, 0.0], maest=[0.0, 1.0])
    _save_embeddings(db, track_ids["mert_top"], mert=[0.99, 0.01], maest=[1.0, 0.0])
    _save_embeddings(db, track_ids["maest_top"], mert=[0.0, 1.0], maest=[0.01, 0.99])
    _save_embeddings(db, track_ids["shared"], mert=[0.8, 0.2], maest=[0.2, 0.8])
    return db, track_ids


def _track(
    db: LibraryDatabase,
    tmp_path: Path,
    stem: str,
    *,
    bpm: float | None = 124.0,
    musical_key: str | None = "8A",
    energy: float | None = 0.5,
) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.replace("_", " ").title()},
        bpm=bpm,
        musical_key=musical_key,
        energy=energy,
    )


def _save_embeddings(db: LibraryDatabase, track_id: int, *, mert: list[float], maest: list[float]) -> None:
    db.save_embedding(track_id, np.asarray(mert, dtype=np.float32), "test-mert", embedding_key="mert")
    db.save_embedding(track_id, np.asarray(maest, dtype=np.float32), "test-maest", embedding_key="maest")


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
