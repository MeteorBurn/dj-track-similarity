from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.candidates import CandidatePoolRow, CandidateSourceContribution
import dj_track_similarity.hybrid_search as hybrid_search
from dj_track_similarity.hybrid_search import build_hybrid_search_preview


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
    assert components["source_disagreement_risk"] == 0.5
    assert transition_diagnostics["transition_risk"] == pytest.approx(sum(component_values) / len(component_values))


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
