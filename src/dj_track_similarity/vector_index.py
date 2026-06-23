from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np


EXACT_VECTOR_BACKEND_NAME = "exact_numpy"


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    track_id: int
    score: float
    index: int | None = None


class VectorSearchBackend(Protocol):
    backend_name: str

    def search(
        self,
        matrix: np.ndarray,
        track_ids: Sequence[int],
        query: np.ndarray,
        limit: int,
    ) -> list[VectorSearchHit]:
        """Return nearest vector hits ordered by backend score."""
        ...


class VectorIndexUnavailable(RuntimeError):
    """Raised when a requested non-exact vector index is unavailable."""


class ExactVectorSearchBackend:
    backend_name = EXACT_VECTOR_BACKEND_NAME

    def search(
        self,
        matrix: np.ndarray,
        track_ids: Sequence[int],
        query: np.ndarray,
        limit: int,
    ) -> list[VectorSearchHit]:
        search_matrix = _search_matrix(matrix)
        search_track_ids = _track_ids_for_matrix(track_ids, search_matrix)
        search_limit = _search_limit(limit)
        if search_limit == 0 or search_matrix.shape[0] == 0:
            return []

        query_vector = _query_vector(query, search_matrix)
        scores = search_matrix @ query_vector
        ranked_indices = np.argsort(-scores)[:search_limit]
        return [
            VectorSearchHit(
                track_id=search_track_ids[int(index)],
                score=float(scores[int(index)]),
                index=int(index),
            )
            for index in ranked_indices
        ]


def _search_matrix(matrix: np.ndarray) -> np.ndarray:
    search_matrix = np.asarray(matrix, dtype=np.float32)
    if search_matrix.ndim != 2:
        raise ValueError("Vector search matrix must be two-dimensional")
    return search_matrix


def _track_ids_for_matrix(track_ids: Sequence[int], matrix: np.ndarray) -> tuple[int, ...]:
    search_track_ids = tuple(int(track_id) for track_id in track_ids)
    if len(search_track_ids) != matrix.shape[0]:
        raise ValueError(
            f"Vector search track IDs length mismatch: {len(search_track_ids)} != {matrix.shape[0]}",
        )
    return search_track_ids


def _query_vector(query: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    query_vector = np.asarray(query, dtype=np.float32).reshape(-1)
    if query_vector.shape[0] != matrix.shape[1]:
        raise ValueError(
            f"Vector search query dim mismatch: {query_vector.shape[0]} != {matrix.shape[1]}",
        )
    return query_vector


def _search_limit(limit: int) -> int:
    if isinstance(limit, bool):
        raise ValueError("Vector search limit must be a non-negative integer")
    search_limit = int(limit)
    if search_limit < 0:
        raise ValueError("Vector search limit must be a non-negative integer")
    return search_limit
