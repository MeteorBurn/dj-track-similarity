"""Deterministic collection views over saved MERT-v2 unit vectors."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EmbeddingExploration:
    coordinates: np.ndarray
    cluster_ids: np.ndarray
    representative_track_ids: tuple[int, ...]
    explained_variance_ratio: tuple[float, float]


def explore_embeddings(
    track_ids: Sequence[int],
    matrix: np.ndarray,
    *,
    n_clusters: int,
) -> EmbeddingExploration:
    """Project all rows and group their original directions without inference.

    Groups are spherical k-means partitions, not musical labels. PCA coordinates
    are approximate and must not replace cosine similarity in retrieval.
    """
    ids = tuple(track_ids)
    if any(
        isinstance(track_id, (bool, np.bool_))
        or not isinstance(track_id, (int, np.integer))
        or track_id <= 0
        for track_id in ids
    ) or len(set(ids)) != len(ids):
        raise ValueError("track_ids must contain unique positive integers")
    if (
        isinstance(n_clusters, (bool, np.bool_))
        or not isinstance(n_clusters, (int, np.integer))
        or n_clusters <= 0
    ):
        raise ValueError("n_clusters must be a positive integer")
    vectors = np.asarray(matrix, dtype=np.float64)
    if vectors.shape != (len(ids), 1024):
        raise ValueError("MERT-v2 matrix must have one 1024-dimensional row per track")
    if not np.isfinite(vectors).all():
        raise ValueError("MERT-v2 matrix contains non-finite values")
    norms = np.linalg.norm(vectors, axis=1)
    if not np.all(np.isclose(norms, 1.0, rtol=1e-4, atol=1e-5)):
        raise ValueError("MERT-v2 matrix must contain L2 unit vectors")
    if not ids:
        return EmbeddingExploration(
            np.empty((0, 2)), np.empty(0, dtype=np.int64), (), (0.0, 0.0)
        )
    vectors = vectors / norms[:, None]
    coordinates, variance = _project(vectors)
    labels, centers = _spherical_groups(vectors, min(n_clusters, len(ids)))
    representatives = []
    for group, center in enumerate(centers):
        members = np.flatnonzero(labels == group)
        scores = vectors[members] @ center
        nearest = members[np.isclose(scores, scores.max(), rtol=1e-12, atol=1e-12)]
        representatives.append(min(int(ids[index]) for index in nearest))
    # Stable representative ordering avoids exposing arbitrary cluster numbers.
    order = np.argsort(representatives)
    remap = np.empty(len(order), dtype=np.int64)
    remap[order] = np.arange(len(order))
    return EmbeddingExploration(
        coordinates,
        remap[labels],
        tuple(representatives[index] for index in order),
        variance,
    )


def _project(vectors: np.ndarray) -> tuple[np.ndarray, tuple[float, float]]:
    coordinates = np.zeros((len(vectors), 2))
    if len(vectors) < 2 or np.all(vectors == vectors[0]):
        return coordinates, (0.0, 0.0)
    centered = vectors - vectors.mean(axis=0)
    total = float(np.einsum("ij,ij->", centered, centered))
    if total <= np.finfo(np.float64).eps**2 * len(vectors):
        return coordinates, (0.0, 0.0)
    # A small randomized range keeps work linear in collection size; no N x N
    # distance matrix or full covariance decomposition is constructed.
    width = min(8, len(vectors) - 1, vectors.shape[1])
    random = np.random.default_rng(42).standard_normal((vectors.shape[1], width))
    basis, _ = np.linalg.qr(centered @ random, mode="reduced")
    for _ in range(2):
        right, _ = np.linalg.qr(centered.T @ basis, mode="reduced")
        basis, _ = np.linalg.qr(centered @ right, mode="reduced")
    _, singular, components = np.linalg.svd(basis.T @ centered, full_matrices=False)
    for index in range(min(2, len(singular))):
        if singular[index] <= singular[0] * max(centered.shape) * np.finfo(float).eps:
            continue
        component = components[index]
        if component[np.argmax(np.abs(component))] < 0:
            component = -component
        coordinates[:, index] = centered @ component
    explained = np.sum(coordinates**2, axis=0) / total
    return coordinates, (float(explained[0]), float(explained[1]))


def _spherical_groups(vectors: np.ndarray, count: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(42)
    chosen = [int(rng.integers(len(vectors)))]
    distances = np.clip(1.0 - vectors @ vectors[chosen[0]], 0.0, 2.0)
    for _ in range(1, count):
        distances[chosen] = 0.0
        if distances.max() <= 1e-10:
            break
        chosen.append(int(np.argmax(distances)))
        distances = np.minimum(
            distances, np.clip(1.0 - vectors @ vectors[chosen[-1]], 0.0, 2.0)
        )
    centers = vectors[chosen].copy()
    previous = None
    for _ in range(100):
        labels = np.argmax(vectors @ centers.T, axis=1)
        active, labels = np.unique(labels, return_inverse=True)
        centers = centers[active]
        if previous is not None and np.array_equal(labels, previous):
            break
        updated = np.zeros_like(centers)
        np.add.at(updated, labels, vectors)
        norms = np.linalg.norm(updated, axis=1)
        directional = norms > 1e-12
        updated[directional] /= norms[directional, None]
        # Opposing directions can have a zero mean; keeping the prior unit
        # direction is valid for their flat spherical objective.
        updated[~directional] = centers[~directional]
        centers = updated
        previous = labels
    return labels, centers
