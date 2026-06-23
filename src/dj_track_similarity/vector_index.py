from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import importlib
from typing import Any, Protocol

import numpy as np


EXACT_VECTOR_BACKEND_NAME = "exact_numpy"
HNSW_VECTOR_BACKEND_NAME = "hnswlib"
_VECTOR_BACKEND_ALIASES = {
    "exact": EXACT_VECTOR_BACKEND_NAME,
    EXACT_VECTOR_BACKEND_NAME: EXACT_VECTOR_BACKEND_NAME,
    "hnsw": HNSW_VECTOR_BACKEND_NAME,
    HNSW_VECTOR_BACKEND_NAME: HNSW_VECTOR_BACKEND_NAME,
}


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


class HnswVectorSearchBackend:
    """Optional benchmark-only HNSW backend that builds a transient index per search."""

    backend_name = HNSW_VECTOR_BACKEND_NAME

    def __init__(self, *, ef_construction: int = 200, m: int = 16, ef_search: int = 50) -> None:
        self._hnswlib = _load_hnswlib()
        self.ef_construction = _positive_hnsw_parameter("ef_construction", ef_construction)
        self.m = _positive_hnsw_parameter("m", m)
        self.ef_search = _positive_hnsw_parameter("ef_search", ef_search)

    def search(
        self,
        matrix: np.ndarray,
        track_ids: Sequence[int],
        query: np.ndarray,
        limit: int,
    ) -> list[VectorSearchHit]:
        search_matrix = _search_matrix(matrix)
        search_track_ids = _track_ids_for_matrix(track_ids, search_matrix)
        search_limit = min(_search_limit(limit), search_matrix.shape[0])
        if search_limit == 0 or search_matrix.shape[0] == 0:
            return []
        if search_matrix.shape[1] <= 0:
            raise ValueError("HNSW vector search requires a positive embedding dimension")

        query_vector = _query_vector(query, search_matrix)
        index = self._build_index(search_matrix)
        index.set_ef(max(self.ef_search, search_limit))
        labels, distances = index.knn_query(query_vector.reshape(1, -1), k=search_limit)
        return _hnsw_hits(labels, distances, search_track_ids, search_matrix.shape[0])

    def _build_index(self, matrix: np.ndarray) -> Any:
        indexed_matrix = np.ascontiguousarray(matrix, dtype=np.float32)
        index = self._hnswlib.Index(space="ip", dim=int(indexed_matrix.shape[1]))
        index.init_index(
            max_elements=int(indexed_matrix.shape[0]),
            ef_construction=self.ef_construction,
            M=self.m,
        )
        index.add_items(indexed_matrix, np.arange(indexed_matrix.shape[0], dtype=np.int64))
        return index


def create_vector_backend(name: str) -> VectorSearchBackend:
    backend_name = _canonical_vector_backend_name(name)
    if backend_name == EXACT_VECTOR_BACKEND_NAME:
        return ExactVectorSearchBackend()
    if backend_name == HNSW_VECTOR_BACKEND_NAME:
        return HnswVectorSearchBackend()
    raise ValueError(f"Unsupported vector backend: {name!r}")


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


def _canonical_vector_backend_name(name: str) -> str:
    clean_name = str(name).strip().lower()
    try:
        return _VECTOR_BACKEND_ALIASES[clean_name]
    except KeyError as error:
        valid_names = ", ".join(sorted(_VECTOR_BACKEND_ALIASES))
        raise ValueError(f"Unknown vector backend {name!r}. Valid backends: {valid_names}") from error


def _load_hnswlib() -> Any:
    try:
        return importlib.import_module("hnswlib")
    except ImportError as error:
        raise VectorIndexUnavailable(
            "HNSW vector search requires optional dependency 'hnswlib'. "
            "Install it with `python -m pip install -e .[ann]` or choose --vector-backend exact.",
        ) from error


def _positive_hnsw_parameter(name: str, value: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"HNSW parameter {name} must be a positive integer")
    clean_value = int(value)
    if clean_value <= 0:
        raise ValueError(f"HNSW parameter {name} must be a positive integer")
    return clean_value


def _hnsw_hits(
    labels: np.ndarray,
    distances: np.ndarray,
    track_ids: Sequence[int],
    matrix_rows: int,
) -> list[VectorSearchHit]:
    flat_labels = np.asarray(labels).reshape(-1)
    flat_distances = np.asarray(distances, dtype=np.float32).reshape(-1)
    hits: list[VectorSearchHit] = []
    for label, distance in zip(flat_labels, flat_distances, strict=True):
        matrix_index = int(label)
        if matrix_index < 0 or matrix_index >= matrix_rows:
            raise ValueError(f"HNSW vector search returned out-of-range index: {matrix_index}")
        hits.append(
            VectorSearchHit(
                track_id=track_ids[matrix_index],
                score=float(1.0 - float(distance)),
                index=matrix_index,
            ),
        )
    return hits
