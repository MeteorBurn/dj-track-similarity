from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.candidates import CandidatePoolRow, export_candidate_pools


def test_export_candidate_pools_deduplicates_and_blinds_deterministically(tmp_path: Path) -> None:
    db, track_ids = _library_with_mert_and_maest_embeddings(tmp_path)

    first = export_candidate_pools(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        per_source=2,
        random_seed=19,
        record_session=False,
    )
    second = export_candidate_pools(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        per_source=2,
        random_seed=19,
        record_session=False,
    )

    assert first.warnings == ()
    assert first.session_ids == ()
    assert _pool_snapshot(first.rows) == _pool_snapshot(second.rows)
    assert {row.candidate_track_id for row in first.rows} == {
        track_ids["shared"],
        track_ids["mert_only"],
        track_ids["maest_only"],
    }
    assert [row.blind_rank for row in first.rows] == [1, 2, 3]
    assert all(row.candidate_track_id != row.seed_track_id for row in first.rows)

    shared_row = next(row for row in first.rows if row.candidate_track_id == track_ids["shared"])
    assert json.loads(shared_row.sources_json) == {
        "maest": {"rank": 1, "score": shared_row.source_contributions["maest"].score},
        "mert": {"rank": 1, "score": shared_row.source_contributions["mert"].score},
    }


def test_export_candidate_pools_skips_missing_source_and_keeps_working_source(tmp_path: Path) -> None:
    db, track_ids = _library_with_mert_and_maest_embeddings(tmp_path)

    result = export_candidate_pools(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "sonara"],
        per_source=1,
        random_seed=3,
        record_session=False,
    )

    assert len(result.rows) == 1
    assert result.rows[0].candidate_track_id == track_ids["shared"]
    assert any("source=sonara" in warning for warning in result.warnings)


def _pool_snapshot(rows: tuple[CandidatePoolRow, ...]) -> list[tuple[int, int, int, str]]:
    return [(row.seed_track_id, row.candidate_track_id, row.blind_rank, row.sources_json) for row in rows]


def _library_with_mert_and_maest_embeddings(tmp_path: Path) -> tuple[LibraryDatabase, dict[str, int]]:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed", artist="Seed Artist", title="Seed", bpm=120.0, energy=0.5),
        "shared": _track(db, tmp_path, "shared", artist="Shared Artist", title="Shared", bpm=121.0, energy=0.52),
        "mert_only": _track(db, tmp_path, "mert_only", artist="MERT Artist", title="MERT", bpm=122.0, energy=0.55),
        "maest_only": _track(db, tmp_path, "maest_only", artist="MAEST Artist", title="MAEST", bpm=123.0, energy=0.6),
    }

    _save_embedding_pair(db, track_ids["seed"], mert=[1.0, 0.0], maest=[0.0, 1.0])
    _save_embedding_pair(db, track_ids["shared"], mert=[0.99, 0.1], maest=[0.1, 0.99])
    _save_embedding_pair(db, track_ids["mert_only"], mert=[0.8, 0.2], maest=[1.0, 0.0])
    _save_embedding_pair(db, track_ids["maest_only"], mert=[0.0, 1.0], maest=[0.2, 0.8])
    return db, track_ids


def _track(
    db: LibraryDatabase,
    tmp_path: Path,
    stem: str,
    *,
    artist: str,
    title: str,
    bpm: float,
    energy: float,
) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": artist, "title": title},
        bpm=bpm,
        musical_key="1A",
        energy=energy,
    )


def _save_embedding_pair(db: LibraryDatabase, track_id: int, *, mert: list[float], maest: list[float]) -> None:
    db.save_embedding(track_id, np.asarray(mert, dtype=np.float32), "test-mert", embedding_key="mert")
    db.save_embedding(track_id, np.asarray(maest, dtype=np.float32), "test-maest", embedding_key="maest")
