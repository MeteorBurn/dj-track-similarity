from dj_track_similarity.genres import rank_genres


def test_rank_genres_orders_scores_and_limits_results() -> None:
    ranked = rank_genres(["A", "B", "C"], [0.1, 0.9, 0.5], top_k=2)

    assert ranked == [
        {"label": "B", "score": 0.9},
        {"label": "C", "score": 0.5},
    ]
