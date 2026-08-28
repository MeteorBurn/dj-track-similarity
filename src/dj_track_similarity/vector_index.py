from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .analysis_models import AnalysisTarget


EXACT_VECTOR_BACKEND_NAME = "exact_numpy"
_L2_RTOL = 1e-4
_L2_ATOL = 1e-5


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    """One cosine-search result bound to an exact current track identity."""

    target: AnalysisTarget
    score: float
    index: int | None = None


class VectorSearchBackend(Protocol):
    """Cosine backend for production ``normalization='l2'`` embeddings."""

    backend_name: str

    def search(
        self,
        matrix: np.ndarray,
        targets: Sequence[AnalysisTarget],
        query: np.ndarray,
        limit: int,
    ) -> list[VectorSearchHit]:
        """Return nearest vector hits ordered by descending cosine score."""
        ...


class VectorIndexUnavailable(RuntimeError):
    """Raised when a requested vector index cannot be used safely."""


class ExactVectorSearchBackend:
    """Deterministic exact cosine search over validated unit vectors."""

    backend_name = EXACT_VECTOR_BACKEND_NAME

    def search(
        self,
        matrix: np.ndarray,
        targets: Sequence[AnalysisTarget],
        query: np.ndarray,
        limit: int,
    ) -> list[VectorSearchHit]:
        search_matrix = _l2_search_matrix(matrix)
        search_targets = _targets_for_matrix(targets, search_matrix)
        search_limit = min(_search_limit(limit), search_matrix.shape[0])
        if search_limit == 0:
            return []

        query_vector = _l2_query_vector(query, search_matrix)
        scores = search_matrix @ query_vector
        ranked_indices = np.argsort(-scores, kind="stable")[:search_limit]
        return [
            VectorSearchHit(
                target=search_targets[int(index)],
                score=float(scores[int(index)]),
                index=int(index),
            )
            for index in ranked_indices
        ]


def _search_matrix(matrix: np.ndarray) -> np.ndarray:
    search_matrix = np.asarray(matrix, dtype=np.float32)
    if search_matrix.ndim != 2:
        raise ValueError("Vector search matrix must be two-dimensional")
    if search_matrix.shape[1] <= 0:
        raise ValueError(
            "Vector search requires a positive embedding dimension"
        )
    if not bool(np.all(np.isfinite(search_matrix))):
        raise ValueError("Vector search matrix contains non-finite values")
    return np.ascontiguousarray(search_matrix, dtype=np.float32)


def _l2_search_matrix(matrix: np.ndarray) -> np.ndarray:
    search_matrix = _search_matrix(matrix)
    if search_matrix.shape[0] == 0:
        return search_matrix
    norms = np.sqrt(np.einsum("ij,ij->i", search_matrix, search_matrix))
    if not bool(
        np.all(
            np.isclose(
                norms,
                1.0,
                rtol=_L2_RTOL,
                atol=_L2_ATOL,
            )
        )
    ):
        raise ValueError(
            "Cosine vector search requires unit-normalized matrix rows"
        )
    return search_matrix


def _targets_for_matrix(
    targets: Sequence[AnalysisTarget],
    matrix: np.ndarray,
) -> tuple[AnalysisTarget, ...]:
    search_targets = tuple(targets)
    if len(search_targets) != matrix.shape[0]:
        raise ValueError(
            "Vector search targets length mismatch: "
            f"{len(search_targets)} != {matrix.shape[0]}"
        )
    if any(
        not isinstance(target, AnalysisTarget)
        for target in search_targets
    ):
        raise TypeError(
            "Vector search targets must contain only AnalysisTarget values"
        )
    if not search_targets:
        return ()
    catalogs = {target.catalog_uuid for target in search_targets}
    if len(catalogs) != 1:
        raise ValueError(
            "Vector search targets must belong to one catalog UUID"
        )
    if len(set(search_targets)) != len(search_targets):
        raise ValueError(
            "Vector search targets must not contain duplicate identities"
        )
    track_ids = [target.track_id for target in search_targets]
    if len(set(track_ids)) != len(track_ids):
        raise ValueError(
            "Vector search targets contain conflicting identities "
            "for one track ID"
        )
    return search_targets


def _query_vector(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    query_vector = np.asarray(query, dtype=np.float32).reshape(-1)
    if query_vector.shape[0] != matrix.shape[1]:
        raise ValueError(
            "Vector search query dim mismatch: "
            f"{query_vector.shape[0]} != {matrix.shape[1]}"
        )
    if not bool(np.all(np.isfinite(query_vector))):
        raise ValueError("Vector search query contains non-finite values")
    return np.ascontiguousarray(query_vector, dtype=np.float32)


def _l2_query_vector(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    query_vector = _query_vector(query, matrix)
    norm = float(
        np.linalg.norm(query_vector.astype(np.float64, copy=False))
    )
    if not np.isclose(norm, 1.0, rtol=_L2_RTOL, atol=_L2_ATOL):
        raise ValueError(
            "Cosine vector search requires a unit-normalized query"
        )
    return query_vector


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

