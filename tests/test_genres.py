import pytest

from dj_track_similarity.genres import rank_genres, rank_maest_genres


def test_rank_genres_orders_scores_and_limits_results() -> None:
    ranked = rank_genres(["A", "B", "C"], [0.1, 0.9, 0.5], top_k=2)

    assert ranked == [
        {"label": "B", "score": 0.9},
        {"label": "C", "score": 0.5},
    ]


def test_rank_maest_genres_averages_each_tracks_windows_before_top_k() -> None:
    ranked = rank_maest_genres(
        ["A", "B", "C"],
        [
            [0.1, 0.9, 0.2],
            [0.3, 0.7, 0.6],
            [0.5, 0.8, 0.1],
            [0.9, 0.2, 0.3],
        ],
        [0, 0, 0, 1],
        expected_tracks=2,
        top_k=2,
    )

    assert [[item["label"] for item in values] for values in ranked] == [
        ["B", "A"],
        ["A", "C"],
    ]
    assert [[item["score"] for item in values] for values in ranked] == [
        pytest.approx([0.8, 0.3]),
        pytest.approx([0.9, 0.3]),
    ]
