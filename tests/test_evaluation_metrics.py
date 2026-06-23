from __future__ import annotations

import math

import pytest

from dj_track_similarity.evaluation.metrics import (
    average_precision_at_k,
    bad_suggestion_rate_at_k,
    dcg_at_k,
    hit_rate_at_k,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    pairwise_accuracy,
    precision_at_k,
    r_precision,
    recall_at_k,
    recommended_songs_clicks,
)


def test_ranking_metrics_on_toy_relevances() -> None:
    relevances = [3, 0, 2]

    assert precision_at_k(relevances, 2) == pytest.approx(0.5)
    assert recall_at_k(relevances, total_relevant=2, k=3) == pytest.approx(1.0)
    assert dcg_at_k([3, 2], 2) == pytest.approx(7 + (3 / math.log2(3)))
    assert ndcg_at_k([3, 2], 2) == pytest.approx(1.0)
    assert average_precision_at_k([0, 3, 2], 3) == pytest.approx(((1 / 2) + (2 / 3)) / 2)
    assert bad_suggestion_rate_at_k(relevances, 2) == pytest.approx(0.5)
    assert r_precision(relevances, total_relevant=2) == pytest.approx(0.5)


def test_list_metrics_on_toy_sessions() -> None:
    relevance_lists = [[0, 2], [0, 0, 3], [1, 1]]

    assert mean_reciprocal_rank(relevance_lists, 3) == pytest.approx(((1 / 2) + (1 / 3) + 0) / 3)
    assert mean_average_precision(relevance_lists, 3) == pytest.approx(((1 / 2) + (1 / 3) + 0) / 3)
    assert hit_rate_at_k(relevance_lists, 2) == pytest.approx(1 / 3)


def test_recommended_songs_clicks_and_pairwise_accuracy() -> None:
    assert recommended_songs_clicks([0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2]) == 1
    assert recommended_songs_clicks([0] * 25) == 3
    assert recommended_songs_clicks([]) == 0
    assert pairwise_accuracy([(0.9, 0.1), (0.2, 0.2), (0.1, 0.4)]) == pytest.approx(0.5)


def test_empty_inputs_return_zero() -> None:
    assert precision_at_k([], 5) == 0.0
    assert recall_at_k([], total_relevant=0, k=5) == 0.0
    assert dcg_at_k([], 5) == 0.0
    assert ndcg_at_k([], 5) == 0.0
    assert average_precision_at_k([], 5) == 0.0
    assert mean_reciprocal_rank([], 5) == 0.0
    assert mean_average_precision([], 5) == 0.0
    assert hit_rate_at_k([], 5) == 0.0
    assert bad_suggestion_rate_at_k([], 5) == 0.0
    assert r_precision([], total_relevant=0) == 0.0
    assert pairwise_accuracy([]) == 0.0
