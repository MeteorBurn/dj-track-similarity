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


def _track(db: LibraryDatabase, tmp_path: Path, stem: str) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.replace("_", " ").title()},
        bpm=124.0,
        musical_key="8A",
        energy=0.5,
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
