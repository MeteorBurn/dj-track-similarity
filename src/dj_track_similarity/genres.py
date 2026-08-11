from __future__ import annotations

from collections.abc import Sequence


def rank_genres(
    labels: Sequence[str],
    scores: Sequence[float],
    top_k: int,
) -> list[dict[str, float | str]]:
    """Turn MAEST genre logits, already activated by the model adapter, into labels."""

    ranked = sorted(zip(labels, scores), key=lambda item: item[1], reverse=True)
    return [
        {"label": label, "score": float(score)}
        for label, score in ranked[: max(1, int(top_k))]
    ]


def rank_maest_genres(
    labels: Sequence[str],
    window_scores: Sequence[Sequence[float]],
    window_track_indexes: Sequence[int],
    *,
    expected_tracks: int,
    top_k: int,
) -> list[list[dict[str, float | str]]]:
    """Average MAEST genre scores from each track's analysis windows, then rank."""

    scores_by_track: dict[int, list[Sequence[float]]] = {}
    for scores, track_index in zip(window_scores, window_track_indexes):
        scores_by_track.setdefault(track_index, []).append(scores)

    ranked_by_track: list[list[dict[str, float | str]]] = []
    for track_index in range(expected_tracks):
        scores = scores_by_track.get(track_index, [])
        if not scores:
            raise ValueError("MAEST did not produce genre logits for every track")
        averaged_scores = [
            sum(values) / len(scores) for values in zip(*scores)
        ]
        ranked_by_track.append(rank_genres(labels, averaged_scores, top_k))
    return ranked_by_track
