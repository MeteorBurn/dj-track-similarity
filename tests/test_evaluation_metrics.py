from __future__ import annotations

import math

import pytest

from dj_track_similarity.evaluation.metrics import (
    average_precision_at_k,
    bad_suggestion_rate_at_k,
    dcg_at_k,
    explanation_tag_agreement_at_k,
    hit_rate_at_k,
    maybe_rate_at_k,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    pairwise_accuracy,
    precision_at_k,
    r_precision,
    rating_rate_at_k,
    recall_at_k,
    recommended_songs_clicks,
    reject_rate_at_k,
    strong_match_rate_at_k,
)


def test_ranking_metrics_on_toy_relevances() -> None:
    relevances = [3, 0, 2]

    assert precision_at_k(relevances, 2) == pytest.approx(0.5)
    assert recall_at_k(relevances, total_relevant=2, k=3) == pytest.approx(1.0)
    assert dcg_at_k([3, 2], 2) == pytest.approx(7 + (3 / math.log2(3)))
    assert ndcg_at_k([3, 2], 2) == pytest.approx(1.0)
    assert average_precision_at_k([0, 3, 2], 3) == pytest.approx(((1 / 2) + (2 / 3)) / 2)
    assert bad_suggestion_rate_at_k(relevances, 2) == pytest.approx(0.5)
    assert rating_rate_at_k([3, 1, 0, 3], 4, 3) == pytest.approx(0.5)
    assert strong_match_rate_at_k([3, 1, 0, 3], 4) == pytest.approx(0.5)
    assert maybe_rate_at_k([3, 1, 0, 3], 4) == pytest.approx(0.25)
    assert reject_rate_at_k([3, 1, 0, 3], 4) == pytest.approx(0.25)
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
    assert rating_rate_at_k([], 5, 3) == 0.0
    assert strong_match_rate_at_k([], 5) == 0.0
    assert maybe_rate_at_k([], 5) == 0.0
    assert reject_rate_at_k([], 5) == 0.0
    assert r_precision([], total_relevant=0) == 0.0
    assert pairwise_accuracy([]) == 0.0


def test_explanation_tag_agreement_is_not_available_until_explanations_exist() -> None:
    availability = explanation_tag_agreement_at_k(3)

    assert availability["status"] == "not_available"
    assert availability["value"] is None
    assert availability["coverage"] == 0.0


def test_explanation_tag_agreement_computes_for_matching_axes() -> None:
    availability = explanation_tag_agreement_at_k(
        3,
        [
            {
                "rank": 1,
                "reason_tags": ["good_groove", "bad_tonal"],
                "score_breakdown": {"match_character": {"groove": 0.8, "tonal": 0.2}},
            },
            {
                "rank": 2,
                "reason_tags": ["good_density"],
                "score_breakdown": {"match_character": {"density": 0.4}},
            },
            {
                "rank": 4,
                "reason_tags": ["good_texture"],
                "score_breakdown": {"match_character": {"texture": 0.9}},
            },
        ],
    )

    assert availability["status"] == "ok"
    assert availability["value"] == pytest.approx(2 / 3)
    assert availability["coverage"] == pytest.approx(1.0)
    assert availability["compared_tags"] == 3


def test_explanation_tag_agreement_stays_unavailable_for_neutral_axes() -> None:
    availability = explanation_tag_agreement_at_k(
        3,
        [
            {
                "rank": 1,
                "reason_tags": ["good_groove"],
                "score_breakdown": {"match_character": {"groove": 0.5}},
            },
        ],
    )

    assert availability["status"] == "not_available"
    assert availability["coverage"] == 0.0
