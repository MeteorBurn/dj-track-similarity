from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dj_track_similarity.database import LibraryDatabase

from .metrics import (
    average_precision_at_k,
    bad_suggestion_rate_at_k,
    hit_rate_at_k,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    r_precision,
    recall_at_k,
    recommended_songs_clicks,
)

DEFAULT_K_VALUES = (5, 10)
RELEVANCE_THRESHOLD = 2


def build_search_evaluation_report(db: LibraryDatabase, k_values: Sequence[int] = DEFAULT_K_VALUES) -> dict[str, Any]:
    clean_k_values = _clean_k_values(k_values)
    sessions = db.list_search_sessions_with_events()
    feedback_map = db.get_pair_feedback_map()
    row_counts = db.count_evaluation_rows()
    session_reports = [_session_report(session, feedback_map, clean_k_values) for session in sessions]
    judged_results = sum(int(session["judged_results"]) for session in session_reports)
    total_events = sum(len(session["events"]) for session in sessions)
    report = {
        "status": "ok" if judged_results > 0 else "insufficient_data",
        "k_values": list(clean_k_values),
        "counts": {
            "sessions_total": len(sessions),
            "sessions_with_labels": sum(1 for session in session_reports if int(session["judged_results"]) > 0),
            "judged_results": judged_results,
            "unjudged_results": total_events - judged_results,
            "labels_by_rating": _all_labels_by_rating(feedback_map),
            "rows": row_counts,
        },
        "overall": _aggregate_report(session_reports, clean_k_values),
        "by_mode": _mode_reports(session_reports, clean_k_values),
        "sessions": session_reports,
    }
    return report


def _session_report(
    session: Mapping[str, Any],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    k_values: Sequence[int],
) -> dict[str, Any]:
    seed_track_ids = [int(track_id) for track_id in session["seed_track_ids"]]
    source = _session_feedback_source(session)
    judged_events = [_judged_event(event, seed_track_ids, source, feedback_map) for event in session["events"]]
    judged_events = [event for event in judged_events if event is not None]
    relevances = [int(event["rating"]) for event in judged_events]
    total_relevant = _total_relevant_for_session(seed_track_ids, source, feedback_map)
    return {
        "session_id": int(session["id"]),
        "mode": str(session["mode"]),
        "created_at": session["created_at"],
        "seed_track_ids": seed_track_ids,
        "feedback_source": source,
        "results_total": len(session["events"]),
        "judged_results": len(judged_events),
        "unjudged_results": len(session["events"]) - len(judged_events),
        "total_relevant_labels": total_relevant,
        "labels_by_rating": _labels_by_rating(relevances),
        "metrics": _single_relevance_metrics(relevances, total_relevant, k_values),
        "judged_events": judged_events,
    }


def _judged_event(
    event: Mapping[str, Any],
    seed_track_ids: Sequence[int],
    source: str | None,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> dict[str, Any] | None:
    candidate_track_id = int(event["track_id"])
    label = _matching_label(seed_track_ids, candidate_track_id, source, feedback_map)
    if label is None:
        return None
    return {
        "event_id": int(event["id"]),
        "track_id": candidate_track_id,
        "rank": int(event["rank"]),
        "rating": int(label["rating"]),
        "source": str(label["source"]),
        "seed_track_id": int(label["seed_track_id"]),
    }


def _matching_label(
    seed_track_ids: Sequence[int],
    candidate_track_id: int,
    source: str | None,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if source:
        for seed_track_id in seed_track_ids:
            label = feedback_map.get((seed_track_id, candidate_track_id, source))
            if label is not None:
                return label
        return None
    for seed_track_id in seed_track_ids:
        manual_label = feedback_map.get((seed_track_id, candidate_track_id, "manual"))
        if manual_label is not None:
            return manual_label
    for seed_track_id in seed_track_ids:
        for (label_seed_id, label_candidate_id, _label_source), label in feedback_map.items():
            if label_seed_id == seed_track_id and label_candidate_id == candidate_track_id:
                return label
    return None


def _total_relevant_for_session(
    seed_track_ids: Sequence[int],
    source: str | None,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> int:
    relevant_candidates: set[tuple[int, int]] = set()
    for label in feedback_map.values():
        seed_track_id = int(label["seed_track_id"])
        if seed_track_id not in seed_track_ids:
            continue
        if source is not None and label["source"] != source:
            continue
        if int(label["rating"]) >= RELEVANCE_THRESHOLD:
            relevant_candidates.add((seed_track_id, int(label["candidate_track_id"])))
    return len(relevant_candidates)


def _single_relevance_metrics(relevances: Sequence[int], total_relevant: int, k_values: Sequence[int]) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {
        "r_precision": r_precision(relevances, total_relevant, threshold=RELEVANCE_THRESHOLD),
        "recommended_songs_clicks": recommended_songs_clicks(relevances, threshold=RELEVANCE_THRESHOLD),
    }
    for k in k_values:
        metrics[f"precision_at_{k}"] = precision_at_k(relevances, k, threshold=RELEVANCE_THRESHOLD)
        metrics[f"recall_at_{k}"] = recall_at_k(relevances, total_relevant, k, threshold=RELEVANCE_THRESHOLD)
        metrics[f"ndcg_at_{k}"] = ndcg_at_k(relevances, k)
        metrics[f"average_precision_at_{k}"] = average_precision_at_k(relevances, k, threshold=RELEVANCE_THRESHOLD)
        metrics[f"bad_suggestion_rate_at_{k}"] = bad_suggestion_rate_at_k(relevances, k)
    return metrics


def _aggregate_report(session_reports: Sequence[Mapping[str, Any]], k_values: Sequence[int]) -> dict[str, float | int]:
    labeled_sessions = [session for session in session_reports if int(session["judged_results"]) > 0]
    if not labeled_sessions:
        return _empty_aggregate(k_values)
    relevance_lists = [_ratings_from_session(session) for session in labeled_sessions]
    total_relevants = [int(session["total_relevant_labels"]) for session in labeled_sessions]
    metrics: dict[str, float | int] = {
        "mean_r_precision": _mean(
            r_precision(relevances, total_relevant, threshold=RELEVANCE_THRESHOLD)
            for relevances, total_relevant in zip(relevance_lists, total_relevants)
        ),
        "mean_recommended_songs_clicks": _mean(
            recommended_songs_clicks(relevances, threshold=RELEVANCE_THRESHOLD) for relevances in relevance_lists
        ),
    }
    for k in k_values:
        metrics[f"mean_precision_at_{k}"] = _mean(precision_at_k(relevances, k, threshold=RELEVANCE_THRESHOLD) for relevances in relevance_lists)
        metrics[f"mean_recall_at_{k}"] = _mean(
            recall_at_k(relevances, total_relevant, k, threshold=RELEVANCE_THRESHOLD)
            for relevances, total_relevant in zip(relevance_lists, total_relevants)
        )
        metrics[f"mean_ndcg_at_{k}"] = _mean(ndcg_at_k(relevances, k) for relevances in relevance_lists)
        metrics[f"mean_average_precision_at_{k}"] = mean_average_precision(relevance_lists, k, threshold=RELEVANCE_THRESHOLD)
        metrics[f"mean_reciprocal_rank_at_{k}"] = mean_reciprocal_rank(relevance_lists, k, threshold=RELEVANCE_THRESHOLD)
        metrics[f"hit_rate_at_{k}"] = hit_rate_at_k(relevance_lists, k, threshold=RELEVANCE_THRESHOLD)
        metrics[f"mean_bad_suggestion_rate_at_{k}"] = _mean(bad_suggestion_rate_at_k(relevances, k) for relevances in relevance_lists)
    return metrics


def _mode_reports(session_reports: Sequence[Mapping[str, Any]], k_values: Sequence[int]) -> dict[str, dict[str, Any]]:
    sessions_by_mode: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for session in session_reports:
        sessions_by_mode[str(session["mode"])].append(session)
    return {
        mode: {
            "sessions_total": len(mode_sessions),
            "sessions_with_labels": sum(1 for session in mode_sessions if int(session["judged_results"]) > 0),
            "metrics": _aggregate_report(mode_sessions, k_values),
        }
        for mode, mode_sessions in sorted(sessions_by_mode.items())
    }


def _empty_aggregate(k_values: Sequence[int]) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {
        "mean_r_precision": 0.0,
        "mean_recommended_songs_clicks": 0,
    }
    for k in k_values:
        metrics[f"mean_precision_at_{k}"] = 0.0
        metrics[f"mean_recall_at_{k}"] = 0.0
        metrics[f"mean_ndcg_at_{k}"] = 0.0
        metrics[f"mean_average_precision_at_{k}"] = 0.0
        metrics[f"mean_reciprocal_rank_at_{k}"] = 0.0
        metrics[f"hit_rate_at_{k}"] = 0.0
        metrics[f"mean_bad_suggestion_rate_at_{k}"] = 0.0
    return metrics


def _ratings_from_session(session: Mapping[str, Any]) -> list[int]:
    return [int(event["rating"]) for event in session["judged_events"]]


def _session_feedback_source(session: Mapping[str, Any]) -> str | None:
    request = session.get("request")
    if not isinstance(request, Mapping):
        return None
    source = request.get("feedback_source") or request.get("label_source") or request.get("source")
    if source is None:
        return None
    text = str(source).strip()
    return text or None


def _all_labels_by_rating(feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]]) -> dict[str, int]:
    return _labels_by_rating([int(label["rating"]) for label in feedback_map.values()])


def _labels_by_rating(relevances: Sequence[int]) -> dict[str, int]:
    counts = Counter(int(relevance) for relevance in relevances)
    return {str(rating): counts.get(rating, 0) for rating in range(4)}


def _clean_k_values(k_values: Sequence[int]) -> tuple[int, ...]:
    clean_values = tuple(dict.fromkeys(sorted(int(k) for k in k_values if int(k) > 0)))
    if not clean_values:
        raise ValueError("At least one positive --k value is required")
    return clean_values


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(float(value) for value in items) / len(items)
