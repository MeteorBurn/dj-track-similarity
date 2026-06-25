from __future__ import annotations

from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.candidates import CandidatePoolRow, CandidateSourceContribution
import dj_track_similarity.hybrid_search as hybrid_search
from dj_track_similarity.hybrid_search import build_hybrid_search_preview


def test_hybrid_explanation_source_support_matches_score_breakdown(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _track(db, tmp_path, "seed")
    candidate_id = _track(db, tmp_path, "candidate")
    rows = (_candidate_row(db, seed_id, candidate_id, {"mert": (1, 0.9), "maest": (3, 0.7)}),)
    monkeypatch.setattr(hybrid_search, "generate_candidate_pool_rows", lambda _db, _request: (rows, ()))

    result = build_hybrid_search_preview(db, seed_track_ids=[seed_id], sources=["mert", "maest", "clap"], limit=1)
    row = result.results[0]

    assert set(row.score_breakdown) == {"mert", "maest"}
    assert row.source_support["mert"]["rank"] == row.score_breakdown["mert"]["rank"]
    assert row.source_support["maest"]["score"] == row.score_breakdown["maest"]["score"]
    assert row.source_support["clap"]["available"] is False
    assert "MERT" in " ".join(row.explanation)
    assert "MAEST" in " ".join(row.explanation)


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
