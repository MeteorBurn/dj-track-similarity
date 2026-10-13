from __future__ import annotations


import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisTarget,
)
from dj_track_similarity.search.vector_index import (
    ExactVectorSearchBackend,
    ExactVectorQuery,
)


_NOW = "2026-07-24T10:00:00.000000Z"
_CATALOG_UUID = "00000000-0000-4000-8000-000000000001"


def test_exact_backend_preserves_stable_input_order_for_ties() -> None:
    query = _small_unit_vector(1.0, 0.0)
    backend = ExactVectorSearchBackend()
    nearby = np.nextafter(np.float32(0.5), np.float32(1.0))
    for cosines in (
        [],
        [1.0],
        [0.5] * 24,
        [0.5, -0.5, 1.0, 0.5, 0.0, 0.5, nearby, -1.0] * 3,
        [0.0, -0.0, -0.5, 0.5, -1.0, 1.0] * 4,
    ):
        matrix = np.asarray(
            [(value, (1.0 - value * value) ** 0.5) for value in cosines],
            dtype=np.float32,
        ).reshape(-1, 2)
        targets = _targets(*range(101, 101 + len(matrix)))
        scores = matrix @ query
        prepared = ExactVectorQuery(targets, scores.copy())
        for limit in (0, 1, 2, 3, len(targets) // 2, len(targets), len(targets) + 3):
            indices = np.argsort(-scores, kind="stable")[:limit].tolist()
            expected = [(index, targets[index], float(scores[index])) for index in indices]
            for hits in (
                backend.search(matrix, targets, query, limit=limit),
                prepared.search(limit),
                prepared.search(limit),
            ):
                assert [(hit.index, hit.target, hit.score) for hit in hits] == expected
        np.testing.assert_array_equal(prepared.scores, scores)

    # Empty output still validates matrix and identities, but never the query.
    matrix = np.asarray([[1.0, 0.0]], dtype=np.float32)
    assert backend.search(matrix, _targets(101), np.asarray([np.nan]), limit=0) == []
    with pytest.raises(ValueError, match="targets length mismatch"):
        backend.search(matrix, (), query, limit=0)
    with pytest.raises(ValueError, match="unit-normalized matrix"):
        backend.search(matrix * 2, _targets(101), query, limit=0)

    # Contrast scores retain the old full-sort ordering for non-finite values.
    scores = np.asarray([np.nan, 0.5, np.inf, -np.inf, 0.5, np.nan], dtype=np.float32)
    targets = _targets(*range(101, 107))
    prepared = ExactVectorQuery(targets, scores)
    for limit in (0, 1, 2, len(scores), len(scores) + 1):
        indices = np.argsort(-scores, kind="stable")[:limit].tolist()
        hits = prepared.search(limit)
        assert [hit.index for hit in hits] == indices
        assert [hit.target for hit in hits] == [targets[index] for index in indices]
        np.testing.assert_array_equal([hit.score for hit in hits], scores[indices])


def _targets(*track_ids: int) -> tuple[AnalysisTarget, ...]:
    return tuple(
        AnalysisTarget(
            catalog_uuid=_CATALOG_UUID,
            track_id=track_id,
            track_uuid=(
                "00000000-0000-4000-8000-"
                f"{track_id:012d}"
            ),
        )
        for track_id in track_ids
    )


def _small_unit_vector(*values: float) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float32)
    norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
    assert norm > 0.0
    vector /= norm
    return vector
