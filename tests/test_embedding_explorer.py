from __future__ import annotations

import numpy as np

from dj_track_similarity.search.embedding_explorer import explore_embeddings


def test_embedding_exploration_preserves_direction_groups_and_representatives() -> None:
    rng = np.random.default_rng(7)
    matrix = np.zeros((12, 1024))
    expected = np.repeat(np.arange(3), 4)
    matrix[np.arange(12), expected] = 1.0
    matrix[:, 3:10] = rng.normal(0, 0.01, (12, 7))
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    track_ids = tuple(range(101, 113))
    original = matrix.copy()

    result = explore_embeddings(track_ids, matrix, n_clusters=3)
    repeated = explore_embeddings(track_ids, matrix, n_clusters=3)

    assert result.coordinates.shape == (12, 2)
    assert np.isfinite(result.coordinates).all()
    np.testing.assert_array_equal(result.cluster_ids, repeated.cluster_ids)
    np.testing.assert_allclose(result.coordinates, repeated.coordinates)
    np.testing.assert_array_equal(matrix, original)
    np.testing.assert_array_equal(
        result.cluster_ids[:, None] == result.cluster_ids,
        expected[:, None] == expected,
    )
    assert len(result.representative_track_ids) == 3
    for group_id, representative in enumerate(result.representative_track_ids):
        members = np.flatnonzero(result.cluster_ids == group_id)
        representative_index = track_ids.index(representative)
        assert representative_index in members
        centroid = matrix[members].mean(axis=0)
        centroid /= np.linalg.norm(centroid)
        assert matrix[representative_index] @ centroid >= (
            (matrix[members] @ centroid).max() - 1e-10
        )
    centered = matrix - matrix.mean(axis=0)
    explained = np.sum(result.coordinates**2, axis=0) / np.sum(centered**2)
    np.testing.assert_allclose(result.explained_variance_ratio, explained)
    assert 0.99 < sum(result.explained_variance_ratio) <= 1.0


def test_embedding_exploration_handles_empty_and_degenerate_collections() -> None:
    unit = np.zeros((1, 1024))
    unit[0, 0] = 1.0
    opposite = np.concatenate((unit, -unit))
    for matrix, requested, expected_groups in (
        (np.empty((0, 1024)), 3, 0),
        (unit, 3, 1),
        (np.repeat(unit, 4, axis=0), 3, 1),
        (np.repeat(opposite, 3, axis=0), 8, 2),
        (opposite, 1, 1),
    ):
        track_ids = tuple(range(1, len(matrix) + 1))
        result = explore_embeddings(track_ids, matrix, n_clusters=requested)
        assert result.coordinates.shape == (len(matrix), 2)
        assert result.cluster_ids.shape == (len(matrix),)
        assert np.isfinite(result.coordinates).all()
        assert np.isfinite(result.explained_variance_ratio).all()
        assert len(result.representative_track_ids) == expected_groups
        assert set(result.cluster_ids) == set(range(expected_groups))
        for group_id, representative in enumerate(result.representative_track_ids):
            assert result.cluster_ids[track_ids.index(representative)] == group_id
        if len(matrix) < 2 or np.array_equal(matrix, np.repeat(unit, len(matrix), axis=0)):
            assert not np.any(result.coordinates)
            assert result.explained_variance_ratio == (0.0, 0.0)
