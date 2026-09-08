from __future__ import annotations

from collections.abc import Sequence


def rank_genres(
    labels: Sequence[str],
    scores: Sequence[float],
    top_k: int,
) -> list[dict[str, float | str]]:
    """Rank MAEST genre probabilities already activated and pooled by the adapter."""

    ranked = sorted(zip(labels, scores), key=lambda item: item[1], reverse=True)
    return [
        {"label": label, "score": float(score)}
        for label, score in ranked[: max(1, int(top_k))]
    ]
