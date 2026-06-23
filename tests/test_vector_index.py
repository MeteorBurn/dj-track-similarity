from __future__ import annotations

from pathlib import Path

import numpy as np

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.search import SimilaritySearch
from dj_track_similarity.vector_index import ExactVectorSearchBackend


def test_exact_backend_matches_manual_matrix_dot_ranking() -> None:
    matrix = np.asarray(
        [
            [0.0, 1.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.8, 0.2, 0.0],
            [-1.0, 0.0, 0.0],
        ],
        dtype=np.float32,
    )
    track_ids = [10, 11, 12, 13]
    query = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
    scores = matrix @ query
    manual_indices = np.argsort(-scores)[:3]

    hits = ExactVectorSearchBackend().search(matrix, track_ids, query, limit=3)

    assert [hit.index for hit in hits] == [int(index) for index in manual_indices]
    assert [hit.track_id for hit in hits] == [track_ids[int(index)] for index in manual_indices]
    assert [hit.score for hit in hits] == [float(scores[int(index)]) for index in manual_indices]


def test_exact_backend_preserves_numpy_argsort_tie_order() -> None:
    matrix = np.asarray(
        [
            [1.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [1.0, 0.0],
        ],
        dtype=np.float32,
    )
    track_ids = [101, 102, 103, 104]
    query = np.asarray([1.0, 0.0], dtype=np.float32)
    scores = matrix @ query
    manual_indices = [int(index) for index in np.argsort(-scores)]
    backend = ExactVectorSearchBackend()

    first_hits = backend.search(matrix, track_ids, query, limit=len(track_ids))
    second_hits = backend.search(matrix, track_ids, query, limit=len(track_ids))

    assert [hit.index for hit in first_hits] == manual_indices
    assert [hit.index for hit in second_hits] == manual_indices


def test_similarity_search_excludes_seed_tracks_outside_backend(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_track_id = _add_track(db, tmp_path, "seed", [1.0, 0.0, 0.0])
    near_track_id = _add_track(db, tmp_path, "near", [0.99, 0.01, 0.0])
    far_track_id = _add_track(db, tmp_path, "far", [0.0, 1.0, 0.0])
    backend = ExactVectorSearchBackend()

    tracks, matrix = db.load_embedding_matrix("mert")
    direct_hits = backend.search(matrix, [track.id for track in tracks], matrix[0], limit=len(tracks))
    results = SimilaritySearch(db, vector_backend=backend).search([seed_track_id], limit=5)

    assert direct_hits[0].track_id == seed_track_id
    assert [result.track.id for result in results] == [near_track_id, far_track_id]


def _add_track(db: LibraryDatabase, tmp_path: Path, stem: str, embedding: list[float]) -> int:
    track_id = db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=100,
        mtime=1,
        metadata={"artist": "Vector Test", "title": stem},
    )
    db.save_embedding(track_id, np.asarray(embedding, dtype=np.float32), "test-mert", embedding_key="mert")
    return track_id
