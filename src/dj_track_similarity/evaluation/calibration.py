from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import TYPE_CHECKING, Any

from .ablation import DEFAULT_RRF_K, _build_session_variants, _candidate_pool_sessions
from .candidates import DEFAULT_FEEDBACK_SOURCE

if TYPE_CHECKING:
    from dj_track_similarity.database import LibraryDatabase


DEFAULT_ACCEPTED_THRESHOLD = 2
DEFAULT_BINS = 10
DEFAULT_MIN_SAMPLES = 30
DEFAULT_SCORE_MODE = "rrf"
DEFAULT_THRESHOLDS = (0.9, 0.8, 0.7, 0.6, 0.5)

SCORE_KINDS = {
    "event-total-score": "event_total_score_raw",
    "rank-percentile": "rank_percentile_diagnostic",
    "rrf": "rrf_minmax_diagnostic",
}

DIAGNOSTIC_NOTES = (
    "Scores in this report are diagnostic ordering scores, not calibrated production confidence or probability.",
    "Brier score, log loss, ECE, bins, and thresholds compare those diagnostic scores with manual accepted labels only.",
    "Do not use this report as a production threshold change without a separate calibration decision and enough labels.",
    "This command does not change production search endpoints, scoring weights, or default thresholds.",
)


@dataclass(frozen=True)
class CalibrationSample:
    session_id: int
    candidate_track_id: int
    score: float
    rating: int
    label: int


def brier_score(predicted_probabilities: Sequence[float], labels: Sequence[int]) -> float:
    samples = _probability_samples(predicted_probabilities, labels)
    return sum((probability - label) ** 2 for probability, label in samples) / len(samples)


def log_loss(predicted_probabilities: Sequence[float], labels: Sequence[int], eps: float = 1e-15) -> float:
    clean_eps = _clean_eps(eps)
    samples = _probability_samples(predicted_probabilities, labels)
    losses = []
    for probability, label in samples:
        clipped_probability = min(1.0 - clean_eps, max(clean_eps, probability))
        losses.append(-(label * math.log(clipped_probability) + (1 - label) * math.log(1.0 - clipped_probability)))
    return sum(losses) / len(losses)


def reliability_bins(predicted_probabilities: Sequence[float], labels: Sequence[int], bins: int = DEFAULT_BINS) -> list[dict[str, float | int | None]]:
    clean_bins = _positive_int(bins, "bins")
    samples = _probability_samples(predicted_probabilities, labels)
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(clean_bins)]
    for probability, label in samples:
        bucket_index = min(clean_bins - 1, int(probability * clean_bins))
        buckets[bucket_index].append((probability, label))
    return [_reliability_bin(index, bucket, clean_bins) for index, bucket in enumerate(buckets)]


def expected_calibration_error(predicted_probabilities: Sequence[float], labels: Sequence[int], bins: int = DEFAULT_BINS) -> float:
    clean_bins = _positive_int(bins, "bins")
    samples = _probability_samples(predicted_probabilities, labels)
    total = len(samples)
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(clean_bins)]
    for probability, label in samples:
        bucket_index = min(clean_bins - 1, int(probability * clean_bins))
        buckets[bucket_index].append((probability, label))
    return sum((len(bucket) / total) * abs(_average_score(bucket) - _positive_rate(bucket)) for bucket in buckets if bucket)


def threshold_table(
    predicted_probabilities: Sequence[float],
    labels: Sequence[int],
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
) -> list[dict[str, float | int]]:
    samples = _probability_samples(predicted_probabilities, labels)
    clean_thresholds = tuple(_probability(threshold, "threshold") for threshold in thresholds)
    total_positive_count = sum(label for _probability_value, label in samples)
    return [_threshold_row(samples, threshold, total_positive_count) for threshold in clean_thresholds]


def score_quantiles(
    scores: Sequence[float],
    quantiles: Sequence[float] = (0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0),
) -> list[dict[str, float]]:
    clean_scores = sorted(_finite_float(score, "score") for score in scores)
    if not clean_scores:
        return []
    clean_quantiles = tuple(_probability(quantile, "quantile") for quantile in quantiles)
    return [{"quantile": quantile, "value": _quantile_value(clean_scores, quantile)} for quantile in clean_quantiles]


def build_calibration_report(
    db: LibraryDatabase,
    *,
    score_mode: str = DEFAULT_SCORE_MODE,
    bins: int = DEFAULT_BINS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
    accepted_threshold: int = DEFAULT_ACCEPTED_THRESHOLD,
    rrf_k: int = DEFAULT_RRF_K,
) -> dict[str, Any]:
    clean_score_mode = _score_mode(score_mode)
    clean_bins = _positive_int(bins, "bins")
    clean_min_samples = _positive_int(min_samples, "min_samples")
    clean_accepted_threshold = _rating_threshold(accepted_threshold)
    clean_rrf_k = _positive_int(rrf_k, "rrf_k")
    sessions = db.list_search_sessions_with_events()
    feedback_map = db.get_pair_feedback_map()
    samples, score_status = _calibration_samples(
        clean_score_mode,
        sessions,
        feedback_map,
        accepted_threshold=clean_accepted_threshold,
        rrf_k=clean_rrf_k,
    )
    return _calibration_report(
        clean_score_mode,
        samples,
        score_status,
        session_count=len(sessions),
        event_count=sum(len(session["events"]) for session in sessions),
        bins=clean_bins,
        min_samples=clean_min_samples,
        accepted_threshold=clean_accepted_threshold,
        rrf_k=clean_rrf_k,
    )


def calibration_record_config(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "score_mode": report["score_mode"],
        "score_kind": report["score_kind"],
        "accepted_threshold": report["accepted_threshold"],
        "bins": report["bins"],
        "min_samples": report["min_samples"],
        "rrf_k": report["rrf_k"],
    }


def calibration_record_metrics(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": report["status"],
        "calibration_status": report["calibration_status"],
        "sample_count": report["sample_count"],
        "positive_count": report["positive_count"],
        "negative_count": report["negative_count"],
        "brier_score": report["brier_score"],
        "log_loss": report["log_loss"],
        "ece": report["ece"],
    }


def _calibration_report(
    score_mode: str,
    samples: Sequence[CalibrationSample],
    score_status: str | None,
    *,
    session_count: int,
    event_count: int,
    bins: int,
    min_samples: int,
    accepted_threshold: int,
    rrf_k: int,
) -> dict[str, Any]:
    probabilities = [sample.score for sample in samples]
    labels = [sample.label for sample in samples]
    sample_count = len(samples)
    positive_count = sum(labels)
    status = _report_status(sample_count, min_samples, score_status)
    metrics_ready = status == "ok"
    probability_tables_ready = sample_count > 0 and score_status is None
    return {
        "status": status,
        "calibration_status": _calibration_status(status),
        "score_mode": score_mode,
        "score_kind": SCORE_KINDS[score_mode],
        "accepted_threshold": accepted_threshold,
        "bins": bins,
        "min_samples": min_samples,
        "rrf_k": rrf_k,
        "sample_count": sample_count,
        "positive_count": positive_count,
        "negative_count": sample_count - positive_count,
        "session_count": session_count,
        "sessions_with_samples": len({sample.session_id for sample in samples}),
        "event_count": event_count,
        "unjudged_count": max(0, event_count - sample_count),
        "brier_score": brier_score(probabilities, labels) if metrics_ready else None,
        "log_loss": log_loss(probabilities, labels) if metrics_ready else None,
        "ece": expected_calibration_error(probabilities, labels, bins=bins) if metrics_ready else None,
        "reliability_bins": reliability_bins(probabilities, labels, bins=bins) if probability_tables_ready else [],
        "threshold_table": threshold_table(probabilities, labels) if probability_tables_ready else [],
        "score_quantiles": score_quantiles(probabilities),
        "notes": _report_notes(status),
    }


def _calibration_samples(
    score_mode: str,
    sessions: Sequence[Mapping[str, Any]],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    *,
    accepted_threshold: int,
    rrf_k: int,
) -> tuple[tuple[CalibrationSample, ...], str | None]:
    if score_mode == "rank-percentile":
        return _rank_percentile_samples(sessions, feedback_map, accepted_threshold), None
    if score_mode == "rrf":
        return _rrf_samples(sessions, feedback_map, accepted_threshold, rrf_k), None
    return _event_total_score_samples(sessions, feedback_map, accepted_threshold)


def _rank_percentile_samples(
    sessions: Sequence[Mapping[str, Any]],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    accepted_threshold: int,
) -> tuple[CalibrationSample, ...]:
    samples: list[CalibrationSample] = []
    for session in sessions:
        events = sorted(session["events"], key=_event_sort_key)
        if not events:
            continue
        divisor = max(1, len(events) - 1)
        for index, event in enumerate(events):
            score = 1.0 if len(events) == 1 else 1.0 - (index / divisor)
            sample = _event_sample(session, event, score, feedback_map, accepted_threshold)
            if sample is not None:
                samples.append(sample)
    return tuple(samples)


def _rrf_samples(
    sessions: Sequence[Mapping[str, Any]],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    accepted_threshold: int,
    rrf_k: int,
) -> tuple[CalibrationSample, ...]:
    samples: list[CalibrationSample] = []
    for session in _candidate_pool_sessions(sessions):
        variant = _build_session_variants(session, feedback_map, rrf_k, None).get("fusion:rrf_all")
        if variant is None or variant.judged_results <= 0:
            continue
        scores_by_track_id = _minmax_rank_scores(variant.ranked_candidates)
        for candidate_track_id, rating in zip(variant.judged_candidate_track_ids, variant.judged_relevances):
            samples.append(
                CalibrationSample(
                    session_id=session.session_id,
                    candidate_track_id=candidate_track_id,
                    score=scores_by_track_id[candidate_track_id],
                    rating=rating,
                    label=int(rating >= accepted_threshold),
                ),
            )
    return tuple(samples)


def _event_total_score_samples(
    sessions: Sequence[Mapping[str, Any]],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    accepted_threshold: int,
) -> tuple[tuple[CalibrationSample, ...], str | None]:
    samples: list[CalibrationSample] = []
    has_out_of_range_score = False
    for session in sessions:
        for event in session["events"]:
            total_score = _finite_float(event["total_score"], "total_score")
            sample = _event_sample(session, event, total_score, feedback_map, accepted_threshold)
            if sample is not None:
                if total_score < 0.0 or total_score > 1.0:
                    has_out_of_range_score = True
                samples.append(sample)
    status = "uncalibrated_score_out_of_range" if has_out_of_range_score else None
    return tuple(samples), status


def _event_sample(
    session: Mapping[str, Any],
    event: Mapping[str, Any],
    score: float,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    accepted_threshold: int,
) -> CalibrationSample | None:
    seed_track_ids = tuple(int(track_id) for track_id in session["seed_track_ids"])
    candidate_track_id = int(event["track_id"])
    label = _matching_label(seed_track_ids, candidate_track_id, _session_feedback_source(session), feedback_map)
    if label is None:
        return None
    rating = int(label["rating"])
    return CalibrationSample(
        session_id=int(session["id"]),
        candidate_track_id=candidate_track_id,
        score=_finite_float(score, "score"),
        rating=rating,
        label=int(rating >= accepted_threshold),
    )


def _matching_label(
    seed_track_ids: Sequence[int],
    candidate_track_id: int,
    preferred_source: str,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    preferred_label = _first_label_for_source(seed_track_ids, candidate_track_id, preferred_source, feedback_map)
    if preferred_label is not None:
        return preferred_label
    manual_label = _first_label_for_source(seed_track_ids, candidate_track_id, DEFAULT_FEEDBACK_SOURCE, feedback_map)
    if manual_label is not None:
        return manual_label
    return _first_label_for_any_source(seed_track_ids, candidate_track_id, feedback_map)


def _first_label_for_source(
    seed_track_ids: Sequence[int],
    candidate_track_id: int,
    source: str,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    for seed_track_id in seed_track_ids:
        label = feedback_map.get((seed_track_id, candidate_track_id, source))
        if label is not None:
            return label
    return None


def _first_label_for_any_source(
    seed_track_ids: Sequence[int],
    candidate_track_id: int,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    seed_id_set = set(seed_track_ids)
    matches = [
        label
        for (seed_track_id, label_candidate_id, _source), label in feedback_map.items()
        if seed_track_id in seed_id_set and label_candidate_id == candidate_track_id
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda label: (int(label["seed_track_id"]), str(label["source"])))[0]


def _minmax_rank_scores(ranked_candidates: Sequence[Any]) -> dict[int, float]:
    raw_scores = [float(candidate.rank_score) for candidate in ranked_candidates]
    min_score = min(raw_scores)
    max_score = max(raw_scores)
    if max_score == min_score:
        return {int(candidate.candidate_track_id): 1.0 for candidate in ranked_candidates}
    return {int(candidate.candidate_track_id): (float(candidate.rank_score) - min_score) / (max_score - min_score) for candidate in ranked_candidates}


def _reliability_bin(index: int, bucket: Sequence[tuple[float, int]], bins: int) -> dict[str, float | int | None]:
    lower = index / bins
    upper = (index + 1) / bins
    if not bucket:
        return {"lower": lower, "upper": upper, "count": 0, "avg_score": None, "positive_rate": None, "gap": None}
    avg_score = _average_score(bucket)
    positive_rate = _positive_rate(bucket)
    return {
        "lower": lower,
        "upper": upper,
        "count": len(bucket),
        "avg_score": avg_score,
        "positive_rate": positive_rate,
        "gap": abs(avg_score - positive_rate),
    }


def _threshold_row(samples: Sequence[tuple[float, int]], threshold: float, total_positive_count: int) -> dict[str, float | int]:
    selected_labels = [label for probability, label in samples if probability >= threshold]
    positive_count = sum(selected_labels)
    count = len(selected_labels)
    return {
        "threshold": threshold,
        "count": count,
        "positive_count": positive_count,
        "precision": positive_count / count if count else 0.0,
        "recall": positive_count / total_positive_count if total_positive_count else 0.0,
    }


def _probability_samples(predicted_probabilities: Sequence[float], labels: Sequence[int]) -> tuple[tuple[float, int], ...]:
    if len(predicted_probabilities) != len(labels):
        raise ValueError("Predicted probabilities and labels must have the same length")
    if len(predicted_probabilities) == 0:
        raise ValueError("At least one probability sample is required")
    return tuple((_probability(probability, "predicted probability"), _binary_label(label)) for probability, label in zip(predicted_probabilities, labels))


def _average_score(bucket: Sequence[tuple[float, int]]) -> float:
    return sum(probability for probability, _label in bucket) / len(bucket)


def _positive_rate(bucket: Sequence[tuple[float, int]]) -> float:
    return sum(label for _probability_value, label in bucket) / len(bucket)


def _quantile_value(sorted_scores: Sequence[float], quantile: float) -> float:
    if len(sorted_scores) == 1:
        return sorted_scores[0]
    position = quantile * (len(sorted_scores) - 1)
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return sorted_scores[lower_index]
    fraction = position - lower_index
    return sorted_scores[lower_index] + (sorted_scores[upper_index] - sorted_scores[lower_index]) * fraction


def _report_status(sample_count: int, min_samples: int, score_status: str | None) -> str:
    if score_status is not None:
        return score_status
    if sample_count < min_samples:
        return "insufficient_data"
    return "ok"


def _calibration_status(status: str) -> str:
    if status == "ok":
        return "diagnostic_only"
    return status


def _report_notes(status: str) -> list[str]:
    notes = list(DIAGNOSTIC_NOTES)
    if status == "insufficient_data":
        notes.append("The labeled sample count is below min_samples, so probability metrics are withheld.")
    if status == "uncalibrated_score_out_of_range":
        notes.append("At least one selected event total_score falls outside [0, 1]; choose a diagnostic transform before probability metrics.")
    return notes


def _event_sort_key(event: Mapping[str, Any]) -> tuple[int, int]:
    score_breakdown = event.get("score_breakdown")
    if isinstance(score_breakdown, Mapping):
        blind_rank = _optional_positive_int(score_breakdown.get("blind_rank"))
        if blind_rank is not None:
            return blind_rank, int(event["id"])
    return int(event["rank"]), int(event["id"])


def _session_feedback_source(session: Mapping[str, Any]) -> str:
    request = session.get("request")
    if not isinstance(request, Mapping):
        return DEFAULT_FEEDBACK_SOURCE
    source = request.get("feedback_source") or request.get("label_source") or request.get("source")
    if source is None:
        return DEFAULT_FEEDBACK_SOURCE
    text = str(source).strip()
    return text or DEFAULT_FEEDBACK_SOURCE


def _score_mode(value: str) -> str:
    text = str(value).strip().lower()
    if text in SCORE_KINDS:
        return text
    allowed = ", ".join(sorted(SCORE_KINDS))
    raise ValueError(f"Unsupported score_mode: {value}. Allowed: {allowed}")


def _rating_threshold(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError("accepted_threshold must be an integer between 0 and 3")
    try:
        threshold = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("accepted_threshold must be an integer between 0 and 3") from error
    if threshold < 0 or threshold > 3:
        raise ValueError("accepted_threshold must be an integer between 0 and 3")
    return threshold


def _binary_label(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError("Labels must be 0 or 1")
    try:
        label = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("Labels must be 0 or 1") from error
    if label not in {0, 1}:
        raise ValueError("Labels must be 0 or 1")
    return label


def _probability(value: float, field_name: str) -> float:
    probability = _finite_float(value, field_name)
    if probability < 0.0 or probability > 1.0:
        raise ValueError(f"{field_name} must be in [0, 1]")
    return probability


def _finite_float(value: float, field_name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be finite") from error
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if clean_value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return clean_value


def _optional_positive_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        clean_value = int(value)
    except (TypeError, ValueError):
        return None
    if clean_value <= 0:
        return None
    return clean_value


def _clean_eps(value: float) -> float:
    eps = _finite_float(value, "eps")
    if eps <= 0.0 or eps >= 0.5:
        raise ValueError("eps must be greater than 0 and less than 0.5")
    return eps
