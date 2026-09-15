from __future__ import annotations


import numpy as np

from dj_track_similarity.analysis_models import (
    AnalysisTarget,
)
from dj_track_similarity.search.vector_index import (
    ExactVectorSearchBackend,
)


_NOW = "2026-07-24T10:00:00.000000Z"
_CATALOG_UUID = "00000000-0000-4000-8000-000000000001"


def test_exact_backend_preserves_stable_input_order_for_ties() -> None:
    matrix = np.stack(
        (
            _small_unit_vector(1.0, 0.0),
            _small_unit_vector(1.0, 0.0),
            _small_unit_vector(0.0, 1.0),
            _small_unit_vector(1.0, 0.0),
        )
    )
    targets = _targets(101, 102, 103, 104)
    query = _small_unit_vector(1.0, 0.0)
    scores = matrix @ query
    manual_indices = [
        int(index)
        for index in np.argsort(-scores, kind="stable")
    ]
    backend = ExactVectorSearchBackend()

    first_hits = backend.search(
        matrix,
        targets,
        query,
        limit=len(targets),
    )
    second_hits = backend.search(
        matrix,
        targets,
        query,
        limit=len(targets),
    )

    assert [hit.index for hit in first_hits] == manual_indices
    assert [hit.index for hit in second_hits] == manual_indices
    assert [hit.target for hit in first_hits] == [
        targets[index] for index in manual_indices
    ]


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
