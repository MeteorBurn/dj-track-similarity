from __future__ import annotations

from collections.abc import Sequence
import math


def precision_at_k(relevances: Sequence[int | float], k: int, threshold: int | float = 2) -> float:
    judged_relevances = _top_k(relevances, k)
    if not judged_relevances:
        return 0.0
    return _relevant_count(judged_relevances, threshold) / len(judged_relevances)


def recall_at_k(relevances: Sequence[int | float], total_relevant: int, k: int, threshold: int | float = 2) -> float:
    if total_relevant <= 0:
        return 0.0
    found_relevant = _relevant_count(_top_k(relevances, k), threshold)
    return min(1.0, found_relevant / total_relevant)


def dcg_at_k(relevances: Sequence[int | float], k: int) -> float:
    return sum(_dcg_gain(relevance, rank) for rank, relevance in enumerate(_top_k(relevances, k), start=1))


def ndcg_at_k(relevances: Sequence[int | float], k: int) -> float:
    ideal_dcg = dcg_at_k(sorted(relevances, reverse=True), k)
    if ideal_dcg <= 0.0:
        return 0.0
    return dcg_at_k(relevances, k) / ideal_dcg


def average_precision_at_k(relevances: Sequence[int | float], k: int, threshold: int | float = 2) -> float:
    judged_relevances = _top_k(relevances, k)
    relevant_total = min(_relevant_count(relevances, threshold), max(0, int(k)))
    if relevant_total <= 0:
        return 0.0
    precision_sum = 0.0
    relevant_seen = 0
    for rank, relevance in enumerate(judged_relevances, start=1):
        if relevance < threshold:
            continue
        relevant_seen += 1
        precision_sum += relevant_seen / rank
    return precision_sum / relevant_total


def mean_reciprocal_rank(
    relevance_lists: Sequence[Sequence[int | float]],
    k: int,
    threshold: int | float = 2,
) -> float:
    if not relevance_lists:
        return 0.0
    return sum(_reciprocal_rank(relevances, k, threshold) for relevances in relevance_lists) / len(relevance_lists)


def mean_average_precision(
    relevance_lists: Sequence[Sequence[int | float]],
    k: int,
    threshold: int | float = 2,
) -> float:
    if not relevance_lists:
        return 0.0
    return sum(average_precision_at_k(relevances, k, threshold) for relevances in relevance_lists) / len(relevance_lists)


def hit_rate_at_k(
    relevance_lists: Sequence[Sequence[int | float]],
    k: int,
    threshold: int | float = 2,
) -> float:
    if not relevance_lists:
        return 0.0
    hits = sum(1 for relevances in relevance_lists if _relevant_count(_top_k(relevances, k), threshold) > 0)
    return hits / len(relevance_lists)


def bad_suggestion_rate_at_k(relevances: Sequence[int | float], k: int, bad_threshold: int | float = 0) -> float:
    judged_relevances = _top_k(relevances, k)
    if not judged_relevances:
        return 0.0
    bad_count = sum(1 for relevance in judged_relevances if relevance <= bad_threshold)
    return bad_count / len(judged_relevances)


def r_precision(relevances: Sequence[int | float], total_relevant: int, threshold: int | float = 2) -> float:
    if total_relevant <= 0:
        return 0.0
    found_relevant = _relevant_count(_top_k(relevances, total_relevant), threshold)
    return found_relevant / total_relevant


def recommended_songs_clicks(
    relevances: Sequence[int | float],
    batch_size: int = 10,
    threshold: int | float = 2,
) -> int:
    clean_batch_size = max(1, int(batch_size))
    for index, relevance in enumerate(relevances):
        if relevance >= threshold:
            return index // clean_batch_size
    if not relevances:
        return 0
    return math.ceil(len(relevances) / clean_batch_size)


def pairwise_accuracy(preferred_pairs: Sequence[tuple[int | float, int | float]]) -> float:
    if not preferred_pairs:
        return 0.0
    correct = sum(_pair_credit(preferred_score, other_score) for preferred_score, other_score in preferred_pairs)
    return correct / len(preferred_pairs)


def _top_k(relevances: Sequence[int | float], k: int) -> list[float]:
    clean_k = max(0, int(k))
    if clean_k <= 0:
        return []
    return [_finite_relevance(relevance) for relevance in relevances[:clean_k]]


def _finite_relevance(value: int | float) -> float:
    relevance = float(value)
    if not math.isfinite(relevance):
        raise ValueError("Relevance values must be finite")
    return relevance


def _relevant_count(relevances: Sequence[int | float], threshold: int | float) -> int:
    return sum(1 for relevance in relevances if _finite_relevance(relevance) >= threshold)


def _dcg_gain(relevance: int | float, rank: int) -> float:
    clean_relevance = _finite_relevance(relevance)
    return (2**clean_relevance - 1) / math.log2(rank + 1)


def _reciprocal_rank(relevances: Sequence[int | float], k: int, threshold: int | float) -> float:
    for rank, relevance in enumerate(_top_k(relevances, k), start=1):
        if relevance >= threshold:
            return 1 / rank
    return 0.0


def _pair_credit(preferred_score: int | float, other_score: int | float) -> float:
    preferred = _finite_relevance(preferred_score)
    other = _finite_relevance(other_score)
    if preferred > other:
        return 1.0
    if preferred == other:
        return 0.5
    return 0.0
