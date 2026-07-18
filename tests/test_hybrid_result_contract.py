from __future__ import annotations

from pathlib import Path

import numpy as np

from dj_track_similarity.database import LibraryDatabase
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
    "grid_instability",
    "structure_transition",
    "source_disagreement",
    "confidence_missingness",
}


def test_hybrid_result_rows_expose_pr22_explanation_contract(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _track(db, tmp_path, "seed")
    candidate_id = _track(db, tmp_path, "candidate")
    _save_embeddings(db, seed_id, [1.0, 0.0])
    _save_embeddings(db, candidate_id, [0.95, 0.05])

    result = build_hybrid_search_preview(db, seed_track_ids=[seed_id], sources=["mert"], limit=1)
    row = result.results[0]

    assert row.total_score == row.score
    assert row.calibrated_score is None
    assert tuple(row.match_character) == MATCH_CHARACTER_AXES
    assert set(row.risk_breakdown) == RISK_BREAKDOWN_KEYS
    assert row.source_support["mert"]["available"] is True
    assert row.classifier_support == {}
    assert row.explanation


def _track(db: LibraryDatabase, tmp_path: Path, stem: str) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem},
        bpm=124.0,
        musical_key="8A",
        energy=0.5,
    )


def _save_embeddings(db: LibraryDatabase, track_id: int, values: list[float]) -> None:
    db.save_embedding(track_id, np.asarray(values, dtype=np.float32), "test-mert", embedding_key="mert")
