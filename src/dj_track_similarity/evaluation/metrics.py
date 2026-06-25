from __future__ import annotations

from collections.abc import Mapping, Sequence
import math


EXPLANATION_REASON_TAG_AXES = {
    "good_groove": ("groove", "high"),
    "good_density": ("density", "high"),
    "bad_density": ("density", "low"),
    "good_texture": ("texture", "high"),
    "wrong_texture": ("texture", "low"),
    "good_mood": ("mood", "high"),
    "good_tonal": ("tonal", "high"),
    "bad_tonal": ("tonal", "low"),
    "too_vocal": ("vocalness", "low"),
    "wrong_energy": ("energy_flow", "low"),
    "interesting_adjacent": ("novelty", "high"),
    "too_obvious": ("novelty", "low"),
}
EXPLANATION_HIGH_THRESHOLD = 0.55
EXPLANATION_LOW_THRESHOLD = 0.45
EXPLANATION_NEUTRAL_VALUE = 0.5


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


def rating_rate_at_k(relevances: Sequence[int | float], k: int, rating: int | float) -> float:
    judged_relevances = _top_k(relevances, k)
    if not judged_relevances:
        return 0.0
    clean_rating = _finite_relevance(rating)
    return sum(1 for relevance in judged_relevances if relevance == clean_rating) / len(judged_relevances)


def strong_match_rate_at_k(relevances: Sequence[int | float], k: int) -> float:
    return rating_rate_at_k(relevances, k, 3)


def maybe_rate_at_k(relevances: Sequence[int | float], k: int) -> float:
    return rating_rate_at_k(relevances, k, 1)


def reject_rate_at_k(relevances: Sequence[int | float], k: int) -> float:
    return rating_rate_at_k(relevances, k, 0)


def explanation_tag_agreement_at_k(
    k: int = 3,
    comparisons: Sequence[Mapping[str, object]] | None = None,
) -> dict[str, float | int | str | None]:
    clean_k = max(1, int(k))
    if not comparisons:
        return _explanation_tag_agreement_unavailable(clean_k, "No comparable PR-22 explanation rows were provided.")

    considered = [comparison for comparison in comparisons if _comparison_rank(comparison) <= clean_k]
    if not considered:
        return _explanation_tag_agreement_unavailable(clean_k, f"No judged rows were available within rank {clean_k}.")

    compared_events = 0
    compared_tags = 0
    agreement_sum = 0.0
    for comparison in considered:
        event_agreements = _event_explanation_tag_agreements(comparison)
        if not event_agreements:
            continue
        compared_events += 1
        compared_tags += len(event_agreements)
        agreement_sum += sum(event_agreements)

    if compared_tags <= 0:
        return _explanation_tag_agreement_unavailable(clean_k, "Reason tags could not be compared to explanation axes.")

    return {
        "status": "ok",
        "value": agreement_sum / compared_tags,
        "coverage": compared_events / len(considered),
        "k": clean_k,
        "reason": "Computed only for judged rows with comparable reason tags and non-neutral explanation axes.",
        "compared_events": compared_events,
        "compared_tags": compared_tags,
    }


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


def _explanation_tag_agreement_unavailable(clean_k: int, reason: str) -> dict[str, float | int | str | None]:
    return {
        "status": "not_available",
        "value": None,
        "coverage": 0.0,
        "k": clean_k,
        "reason": reason,
        "compared_events": 0,
        "compared_tags": 0,
    }


def _comparison_rank(comparison: Mapping[str, object]) -> int:
    rank = comparison.get("rank")
    if isinstance(rank, bool):
        return 1
    try:
        clean_rank = int(rank) if rank is not None else 1
    except (TypeError, ValueError):
        return 1
    return max(1, clean_rank)


def _event_explanation_tag_agreements(comparison: Mapping[str, object]) -> list[float]:
    match_character = _comparison_match_character(comparison)
    if not match_character:
        return []
    agreements: list[float] = []
    for tag in _comparison_reason_tags(comparison):
        axis_expectation = EXPLANATION_REASON_TAG_AXES.get(tag)
        if axis_expectation is None:
            continue
        axis, expectation = axis_expectation
        axis_value = _axis_value(match_character, axis)
        if axis_value is None:
            continue
        if expectation == "high":
            agreements.append(1.0 if axis_value >= EXPLANATION_HIGH_THRESHOLD else 0.0)
        else:
            agreements.append(1.0 if axis_value <= EXPLANATION_LOW_THRESHOLD else 0.0)
    return agreements


def _comparison_match_character(comparison: Mapping[str, object]) -> Mapping[str, object] | None:
    direct_match_character = comparison.get("match_character")
    if isinstance(direct_match_character, Mapping):
        return direct_match_character
    score_breakdown = comparison.get("score_breakdown")
    if not isinstance(score_breakdown, Mapping):
        return None
    nested_match_character = score_breakdown.get("match_character")
    return nested_match_character if isinstance(nested_match_character, Mapping) else None


def _comparison_reason_tags(comparison: Mapping[str, object]) -> list[str]:
    reason_tags = comparison.get("reason_tags")
    if isinstance(reason_tags, str):
        return [reason_tags]
    if not isinstance(reason_tags, Sequence):
        return []
    return [str(tag) for tag in reason_tags]


def _axis_value(match_character: Mapping[str, object], axis: str) -> float | None:
    raw_value = match_character.get(axis)
    if raw_value is None or isinstance(raw_value, bool):
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    if value == EXPLANATION_NEUTRAL_VALUE:
        return None
    return max(0.0, min(1.0, value))


def _pair_credit(preferred_score: int | float, other_score: int | float) -> float:
    preferred = _finite_relevance(preferred_score)
    other = _finite_relevance(other_score)
    if preferred > other:
        return 1.0
    if preferred == other:
        return 0.5
    return 0.0
