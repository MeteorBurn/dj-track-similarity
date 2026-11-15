from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..analysis_models import AnalysisTarget


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    """One cosine-search result bound to an exact current track identity."""

    target: AnalysisTarget
    score: float
    index: int | None = None


class VectorIndexUnavailable(RuntimeError):
    """Raised when a requested vector index cannot be used safely."""


def stable_top_k_indices(scores: np.ndarray, limit: int) -> np.ndarray:
    """Return the exact prefix of a descending stable sort without sorting N."""
    size = scores.size
    count = min(_search_limit(limit), size)
    if count == 0:
        return np.empty(0, dtype=np.intp)
    if count * 2 >= size or not bool(np.all(np.isfinite(scores))):
        return np.argsort(-scores, kind="stable")[:count]

    cutoff = np.partition(scores, size - count)[size - count]
    above = np.flatnonzero(scores > cutoff)
    # Partition is unstable. Take only the earliest equal rows needed at the
    # boundary, retaining the same ties as a full stable sort (also for ±0).
    equal = np.flatnonzero(scores == cutoff)[:count - above.size]
    selected = np.concatenate((above, equal))
    return selected[np.argsort(-scores[selected], kind="stable")]


@dataclass(frozen=True, slots=True)
class ExactVectorQuery:
    """Request-local scores and checked identities, reusable at any depth."""

    targets: tuple[AnalysisTarget, ...]
    scores: np.ndarray

    def search(self, limit: int) -> list[VectorSearchHit]:
        return [
            VectorSearchHit(
                target=self.targets[int(index)],
                score=float(self.scores[int(index)]),
                index=int(index),
            )
            for index in stable_top_k_indices(self.scores, limit)
        ]


def _search_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError(
            "Vector search limit must be a non-negative integer"
        )
    if limit < 0:
        raise ValueError(
            "Vector search limit must be a non-negative integer"
        )
    return limit

