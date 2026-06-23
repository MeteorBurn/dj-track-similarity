from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
from typing import TYPE_CHECKING, Any

from ..transition_diagnostics import compute_transition_diagnostics
from .candidates import DEFAULT_FEEDBACK_SOURCE
from .metrics import (
    bad_suggestion_rate_at_k,
    hit_rate_at_k,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
)
from .reports import RELEVANCE_THRESHOLD
from .score_profiles import DEFAULT_K_VALUES, DEFAULT_RRF_K, LABEL_POLICY, ScoreProfile, score_profile_to_dict, validate_score_profile

if TYPE_CHECKING:
    from ..database import LibraryDatabase
    from ..models import Track


DEFAULT_RISK_SWEEP_WEIGHTS = (0.0, 0.25, 0.5, 1.0)
RISK_SWEEP_REPORT_VERSION = 1
RISK_WEIGHT_METRIC_PREFIX = "transition_risk_weight"
LOWER_IS_BETTER_METRICS = ("mean_bad_suggestion_rate",)


@dataclass(frozen=True)
class RiskSweepCandidate:
    candidate_track_id: int
    raw_rrf_score: float
    normalized_rrf_score: float
    adjusted_score: float
    transition_risk: float | None
    transition_risk_penalty: float
    source_count: int
    best_source_rank: int
    sources: Mapping[str, Mapping[str, float | int]]
    rating: int | None


@dataclass(frozen=True)
class RiskSweepSession:
    session_id: int
    mode: str
    seed_track_ids: tuple[int, ...]
    feedback_source: str
    candidates: tuple[RiskSweepCandidate, ...]


def build_risk_penalty_sweep_report(
    db: LibraryDatabase,
    profile: ScoreProfile,
    *,
    weights: Sequence[float] | None = None,
    k_values: Sequence[int] = DEFAULT_K_VALUES,
    rrf_k: int = DEFAULT_RRF_K,
) -> dict[str, Any]:
    validate_score_profile(profile)
    clean_weights = _clean_risk_weights(DEFAULT_RISK_SWEEP_WEIGHTS if weights is None else weights)
    clean_k_values = _clean_k_values(k_values)
    clean_rrf_k = _positive_int(rrf_k, "rrf_k")

    feedback_map = db.get_pair_feedback_map()
    parsed_sessions, warnings = _recorded_candidate_sessions(db, profile, feedback_map, clean_rrf_k)
    variants = {
        _variant_key(weight): _variant_report(parsed_sessions, weight, clean_k_values)
        for weight in clean_weights
    }
    judged_results = sum(candidate.rating is not None for session in parsed_sessions for candidate in session.candidates)
    unjudged_results = sum(candidate.rating is None for session in parsed_sessions for candidate in session.candidates)
    sessions_with_labels = sum(1 for session in parsed_sessions if any(candidate.rating is not None for candidate in session.candidates))
    ranked_candidate_count = sum(len(session.candidates) for session in parsed_sessions)
    label_status = "ok" if judged_results > 0 else "insufficient_data"

    report: dict[str, Any] = {
        "status": "ok" if parsed_sessions else "insufficient_data",
        "label_status": label_status,
        "label_policy": LABEL_POLICY,
        "report_version": RISK_SWEEP_REPORT_VERSION,
        "profile": score_profile_to_dict(profile),
        "profile_name": profile.name,
        "profile_kind": profile.profile_kind,
        "weight_kind": profile.weight_kind,
        "weights": dict(profile.weights),
        "sources": list(profile.sources),
        "risk_weights": list(clean_weights),
        "k_values": list(clean_k_values),
        "rrf_k": clean_rrf_k,
        "ranked_session_count": len(parsed_sessions),
        "sessions_with_labels": sessions_with_labels,
        "judged_results": judged_results,
        "unjudged_results": unjudged_results,
        "ranked_candidate_count": ranked_candidate_count,
        "counts": {
            "ranked_session_count": len(parsed_sessions),
            "sessions_with_labels": sessions_with_labels,
            "judged_results": judged_results,
            "unjudged_results": unjudged_results,
            "ranked_candidate_count": ranked_candidate_count,
            "label_policy": LABEL_POLICY,
        },
        "variants": variants,
        "warnings": warnings,
        "limitations": list(profile.limitations),
        "note": "Evaluation-only sweep over recorded candidate-pool events. Scores are weighted RRF diagnostics plus a lightweight transition-risk penalty; they are not AutoMix, beatgrid/cue detection, calibrated confidence, calibrated transition probability, or production search scoring.",
    }
    if label_status == "ok":
        report["best_by_metric"] = _best_by_metric(variants)
    return report


def _recorded_candidate_sessions(
    db: LibraryDatabase,
    profile: ScoreProfile,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    rrf_k: int,
) -> tuple[tuple[RiskSweepSession, ...], list[str]]:
    warnings: list[str] = []
    track_cache: dict[int, Track] = {}
    sessions: list[RiskSweepSession] = []
    for session in db.list_search_sessions_with_events():
        parsed_session = _recorded_candidate_session(db, session, profile, feedback_map, rrf_k, track_cache, warnings)
        if parsed_session is None:
            continue
        sessions.append(parsed_session)
    if not sessions:
        warnings.append("No recorded candidate-pool sessions with reusable source ranks were found")
    return tuple(sessions), warnings


def _recorded_candidate_session(
    db: LibraryDatabase,
    session: Mapping[str, Any],
    profile: ScoreProfile,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    rrf_k: int,
    track_cache: dict[int, Track],
    warnings: list[str],
) -> RiskSweepSession | None:
    seed_track_ids = _seed_track_ids(session.get("seed_track_ids"))
    if not seed_track_ids:
        return None

    candidates = _session_candidates(db, session, seed_track_ids, profile, feedback_map, rrf_k, track_cache, warnings)
    if not candidates:
        return None
    return RiskSweepSession(
        session_id=_positive_int(session.get("id"), "session_id"),
        mode=str(session.get("mode") or ""),
        seed_track_ids=seed_track_ids,
        feedback_source=_session_feedback_source(session),
        candidates=candidates,
    )


def _session_candidates(
    db: LibraryDatabase,
    session: Mapping[str, Any],
    seed_track_ids: tuple[int, ...],
    profile: ScoreProfile,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    rrf_k: int,
    track_cache: dict[int, Track],
    warnings: list[str],
) -> tuple[RiskSweepCandidate, ...]:
    raw_candidates: list[dict[str, Any]] = []
    max_source_count = _max_source_count(session, profile)
    for event in _event_mappings(session.get("events")):
        candidate = _raw_candidate(db, session, event, seed_track_ids, profile, feedback_map, rrf_k, max_source_count, track_cache, warnings)
        if candidate is None:
            continue
        raw_candidates.append(candidate)
    if not raw_candidates:
        return ()

    max_raw_score = max(float(candidate["raw_rrf_score"]) for candidate in raw_candidates)
    candidates = [
        _risk_sweep_candidate(candidate, max_raw_score)
        for candidate in raw_candidates
    ]
    return tuple(sorted(candidates, key=lambda candidate: (-candidate.raw_rrf_score, candidate.best_source_rank, candidate.candidate_track_id)))


def _raw_candidate(
    db: LibraryDatabase,
    session: Mapping[str, Any],
    event: Mapping[str, Any],
    seed_track_ids: tuple[int, ...],
    profile: ScoreProfile,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    rrf_k: int,
    max_source_count: int,
    track_cache: dict[int, Track],
    warnings: list[str],
) -> dict[str, Any] | None:
    sources = _source_payload(event)
    if not sources:
        return None
    candidate_track_id = _positive_int(event.get("track_id"), "candidate_track_id")
    raw_rrf_score = _weighted_rrf_score(sources, profile, rrf_k)
    if raw_rrf_score <= 0.0:
        return None
    transition_risk, risk_source = _event_transition_risk(db, event, seed_track_ids[0], candidate_track_id, len(sources), max_source_count, track_cache)
    if risk_source == "missing":
        warnings.append(f"session_id={session.get('id')} candidate_track_id={candidate_track_id} has no usable transition risk")
    rating = _matching_rating(seed_track_ids, candidate_track_id, _session_feedback_source(session), feedback_map)
    return {
        "candidate_track_id": candidate_track_id,
        "raw_rrf_score": raw_rrf_score,
        "transition_risk": transition_risk,
        "source_count": len(sources),
        "best_source_rank": _best_source_rank(sources),
        "sources": sources,
        "rating": rating,
    }


def _risk_sweep_candidate(candidate: Mapping[str, Any], max_raw_score: float) -> RiskSweepCandidate:
    raw_rrf_score = float(candidate["raw_rrf_score"])
    return RiskSweepCandidate(
        candidate_track_id=int(candidate["candidate_track_id"]),
        raw_rrf_score=raw_rrf_score,
        normalized_rrf_score=_normalized_score(raw_rrf_score, max_raw_score),
        adjusted_score=_normalized_score(raw_rrf_score, max_raw_score),
        transition_risk=candidate["transition_risk"],
        transition_risk_penalty=0.0,
        source_count=int(candidate["source_count"]),
        best_source_rank=int(candidate["best_source_rank"]),
        sources=candidate["sources"],
        rating=candidate["rating"],
    )


def _variant_report(sessions: Sequence[RiskSweepSession], risk_weight: float, k_values: Sequence[int]) -> dict[str, Any]:
    ranked_sessions = [_ranked_session_report(session, risk_weight) for session in sessions]
    judged_results = sum(int(session["judged_results"]) for session in ranked_sessions)
    variant: dict[str, Any] = {
        "transition_risk_weight": risk_weight,
        "label_status": "ok" if judged_results > 0 else "insufficient_data",
        "ranked_session_count": len(ranked_sessions),
        "judged_results": judged_results,
        "unjudged_results": sum(int(session["unjudged_results"]) for session in ranked_sessions),
        "ranked_candidate_count": sum(int(session["ranked_candidate_count"]) for session in ranked_sessions),
        "ranked_sessions": ranked_sessions,
        "diagnostics": _variant_diagnostics(ranked_sessions, k_values),
    }
    if judged_results > 0:
        variant["metrics"] = _aggregate_metrics(ranked_sessions, k_values)
    return variant


def _ranked_session_report(session: RiskSweepSession, risk_weight: float) -> dict[str, Any]:
    ranked_candidates = _rank_candidates_with_risk_weight(session.candidates, risk_weight)
    relevances_for_metrics = [int(candidate.rating) if candidate.rating is not None else 0 for candidate in ranked_candidates]
    judged_candidate_track_ids = [candidate.candidate_track_id for candidate in ranked_candidates if candidate.rating is not None]
    return {
        "session_id": session.session_id,
        "mode": session.mode,
        "seed_track_ids": list(session.seed_track_ids),
        "feedback_source": session.feedback_source,
        "label_policy": LABEL_POLICY,
        "ranked_candidate_count": len(ranked_candidates),
        "ranked_candidate_track_ids": [candidate.candidate_track_id for candidate in ranked_candidates],
        "ranked_candidates": [_candidate_payload(candidate, rank) for rank, candidate in enumerate(ranked_candidates, start=1)],
        "judged_results": len(judged_candidate_track_ids),
        "unjudged_results": len(ranked_candidates) - len(judged_candidate_track_ids),
        "judged_candidate_track_ids": judged_candidate_track_ids,
        "unjudged_candidate_track_ids": [candidate.candidate_track_id for candidate in ranked_candidates if candidate.rating is None],
        "judged_relevances": [int(candidate.rating) for candidate in ranked_candidates if candidate.rating is not None],
        "relevances_for_metrics": relevances_for_metrics,
    }


def _rank_candidates_with_risk_weight(candidates: Sequence[RiskSweepCandidate], risk_weight: float) -> tuple[RiskSweepCandidate, ...]:
    weighted_candidates = tuple(_candidate_with_risk_weight(candidate, risk_weight) for candidate in candidates)
    if risk_weight <= 0.0:
        return tuple(sorted(weighted_candidates, key=lambda candidate: (-candidate.raw_rrf_score, candidate.best_source_rank, candidate.candidate_track_id)))
    return tuple(
        sorted(
            weighted_candidates,
            key=lambda candidate: (-candidate.adjusted_score, -candidate.raw_rrf_score, candidate.best_source_rank, candidate.candidate_track_id),
        ),
    )


def _candidate_with_risk_weight(candidate: RiskSweepCandidate, risk_weight: float) -> RiskSweepCandidate:
    risk = float(candidate.transition_risk) if candidate.transition_risk is not None else 0.0
    penalty = risk_weight * risk
    return RiskSweepCandidate(
        candidate_track_id=candidate.candidate_track_id,
        raw_rrf_score=candidate.raw_rrf_score,
        normalized_rrf_score=candidate.normalized_rrf_score,
        adjusted_score=candidate.normalized_rrf_score - penalty,
        transition_risk=candidate.transition_risk,
        transition_risk_penalty=penalty,
        source_count=candidate.source_count,
        best_source_rank=candidate.best_source_rank,
        sources=candidate.sources,
        rating=candidate.rating,
    )


def _candidate_payload(candidate: RiskSweepCandidate, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "candidate_track_id": candidate.candidate_track_id,
        "raw_rrf_score": candidate.raw_rrf_score,
        "normalized_rrf_score": candidate.normalized_rrf_score,
        "adjusted_score": candidate.adjusted_score,
        "transition_risk": candidate.transition_risk,
        "transition_risk_penalty": candidate.transition_risk_penalty,
        "source_count": candidate.source_count,
        "best_source_rank": candidate.best_source_rank,
        "sources": dict(candidate.sources),
        "rating": candidate.rating,
    }


def _variant_diagnostics(ranked_sessions: Sequence[Mapping[str, Any]], k_values: Sequence[int]) -> dict[str, Any]:
    ranked_candidates = [candidate for session in ranked_sessions for candidate in session["ranked_candidates"]]
    return {
        "average_transition_risk_at_k": {
            str(k): _average_transition_risk_at_k(ranked_sessions, k)
            for k in k_values
        },
        "source_count_at_k": {
            str(k): _source_count_at_k(ranked_sessions, k)
            for k in k_values
        },
        "score_distribution": {
            "raw_rrf_score": _number_distribution(candidate["raw_rrf_score"] for candidate in ranked_candidates),
            "adjusted_score": _number_distribution(candidate["adjusted_score"] for candidate in ranked_candidates),
            "transition_risk": _number_distribution(candidate["transition_risk"] for candidate in ranked_candidates if candidate["transition_risk"] is not None),
        },
    }


def _average_transition_risk_at_k(ranked_sessions: Sequence[Mapping[str, Any]], k: int) -> float | None:
    risks = [
        float(candidate["transition_risk"])
        for session in ranked_sessions
        for candidate in session["ranked_candidates"][:k]
        if candidate["transition_risk"] is not None
    ]
    return _mean_or_none(risks)


def _source_count_at_k(ranked_sessions: Sequence[Mapping[str, Any]], k: int) -> dict[str, Any]:
    source_counts = [
        int(candidate["source_count"])
        for session in ranked_sessions
        for candidate in session["ranked_candidates"][:k]
    ]
    histogram = Counter(source_counts)
    return {
        "average": _mean_or_none(source_counts),
        "histogram": {str(source_count): histogram[source_count] for source_count in sorted(histogram)},
    }


def _aggregate_metrics(ranked_sessions: Sequence[Mapping[str, Any]], k_values: Sequence[int]) -> dict[str, float]:
    relevance_lists = [list(session["relevances_for_metrics"]) for session in ranked_sessions if int(session["judged_results"]) > 0]
    metrics: dict[str, float] = {}
    for k in k_values:
        metrics[f"mean_ndcg_at_{k}"] = _mean(ndcg_at_k(relevances, k) for relevances in relevance_lists)
        metrics[f"mean_average_precision_at_{k}"] = mean_average_precision(relevance_lists, k, threshold=RELEVANCE_THRESHOLD)
        metrics[f"mean_reciprocal_rank_at_{k}"] = mean_reciprocal_rank(relevance_lists, k, threshold=RELEVANCE_THRESHOLD)
        metrics[f"mean_precision_at_{k}"] = _mean(precision_at_k(relevances, k, threshold=RELEVANCE_THRESHOLD) for relevances in relevance_lists)
        metrics[f"mean_bad_suggestion_rate_at_{k}"] = _mean(bad_suggestion_rate_at_k(relevances, k) for relevances in relevance_lists)
        metrics[f"hit_rate_at_{k}"] = hit_rate_at_k(relevance_lists, k, threshold=RELEVANCE_THRESHOLD)
    return metrics


def _best_by_metric(variants: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    metric_names = sorted({metric for variant in variants.values() for metric in variant.get("metrics", {})})
    best: dict[str, dict[str, Any]] = {}
    for metric_name in metric_names:
        direction = "min" if _lower_is_better(metric_name) else "max"
        candidates = [
            (str(variant_key), float(variant["transition_risk_weight"]), float(variant["metrics"][metric_name]))
            for variant_key, variant in variants.items()
            if "metrics" in variant and metric_name in variant["metrics"]
        ]
        if not candidates:
            continue
        selected = min(candidates, key=lambda item: (item[2], item[1])) if direction == "min" else max(candidates, key=lambda item: (item[2], -item[1]))
        best[metric_name] = {
            "variant": selected[0],
            "transition_risk_weight": selected[1],
            "value": selected[2],
            "direction": direction,
        }
    return best


def _lower_is_better(metric_name: str) -> bool:
    return any(metric_name.startswith(prefix) for prefix in LOWER_IS_BETTER_METRICS)


def _event_transition_risk(
    db: LibraryDatabase,
    event: Mapping[str, Any],
    seed_track_id: int,
    candidate_track_id: int,
    source_count: int,
    max_source_count: int,
    track_cache: dict[int, Track],
) -> tuple[float | None, str]:
    stored_risk = _stored_transition_risk(event)
    if stored_risk is not None:
        return stored_risk, "stored"
    recomputed_risk = _recomputed_transition_risk(db, seed_track_id, candidate_track_id, source_count, max_source_count, track_cache)
    if recomputed_risk is not None:
        return recomputed_risk, "recomputed"
    return None, "missing"


def _stored_transition_risk(event: Mapping[str, Any]) -> float | None:
    score_breakdown = event.get("score_breakdown")
    if not isinstance(score_breakdown, Mapping):
        return None
    direct_risk = _optional_risk(score_breakdown.get("transition_risk"))
    if direct_risk is not None:
        return direct_risk
    diagnostics = score_breakdown.get("transition_diagnostics")
    if isinstance(diagnostics, Mapping):
        return _optional_risk(diagnostics.get("transition_risk"))
    return None


def _recomputed_transition_risk(
    db: LibraryDatabase,
    seed_track_id: int,
    candidate_track_id: int,
    source_count: int,
    max_source_count: int,
    track_cache: dict[int, Track],
) -> float | None:
    try:
        seed_track = _cached_track(db, seed_track_id, track_cache)
        candidate_track = _cached_track(db, candidate_track_id, track_cache)
    except KeyError:
        return None
    diagnostics = compute_transition_diagnostics(seed_track, candidate_track, source_count=source_count, max_source_count=max_source_count)
    return diagnostics.transition_risk


def _cached_track(db: LibraryDatabase, track_id: int, track_cache: dict[int, Track]) -> Track:
    if track_id not in track_cache:
        track_cache[track_id] = db.get_track(track_id)
    return track_cache[track_id]


def _source_payload(event: Mapping[str, Any]) -> dict[str, dict[str, float | int]]:
    event_sources_json = event.get("sources_json")
    event_sources = _sources_from_json_text(event_sources_json)
    if event_sources:
        return event_sources

    score_breakdown = event.get("score_breakdown")
    if not isinstance(score_breakdown, Mapping):
        return {}
    sources = score_breakdown.get("sources")
    if not isinstance(sources, Mapping):
        nested_sources = _sources_from_json_text(score_breakdown.get("sources_json"))
        if nested_sources:
            return nested_sources
        sources = {source: score_breakdown[source] for source in ("mert", "maest", "sonara") if source in score_breakdown}
    return _source_payload_from_mapping(sources)


def _sources_from_json_text(value: object) -> dict[str, dict[str, float | int]]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, Mapping):
        return {}
    return _source_payload_from_mapping(parsed)


def _source_payload_from_mapping(sources: Mapping[str, Any]) -> dict[str, dict[str, float | int]]:
    payload: dict[str, dict[str, float | int]] = {}
    for source, contribution in sources.items():
        source_name = str(source).strip().lower()
        clean_contribution = _source_contribution(contribution)
        if clean_contribution is None:
            continue
        payload[source_name] = clean_contribution
    return dict(sorted(payload.items()))


def _source_contribution(value: object) -> dict[str, float | int] | None:
    if not isinstance(value, Mapping):
        return None
    rank = _optional_positive_int(value.get("rank"))
    if rank is None:
        return None
    score = _optional_float(value.get("score"))
    return {"rank": rank, "score": 0.0 if score is None else score}


def _weighted_rrf_score(sources: Mapping[str, Mapping[str, float | int]], profile: ScoreProfile, rrf_k: int) -> float:
    score = 0.0
    for source in profile.sources:
        contribution = sources.get(source)
        if contribution is None:
            continue
        rank = _optional_positive_int(contribution.get("rank"))
        if rank is None:
            continue
        score += float(profile.weights[source]) * (1.0 / (rrf_k + rank))
    if not math.isfinite(score):
        raise ValueError("weighted RRF produced a non-finite score")
    return score


def _best_source_rank(sources: Mapping[str, Mapping[str, float | int]]) -> int:
    ranks = [_optional_positive_int(contribution.get("rank")) for contribution in sources.values()]
    clean_ranks = [rank for rank in ranks if rank is not None]
    return min(clean_ranks, default=1_000_000)


def _matching_rating(
    seed_track_ids: Sequence[int],
    candidate_track_id: int,
    preferred_source: str,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> int | None:
    label = _matching_label(seed_track_ids, candidate_track_id, preferred_source, feedback_map)
    if label is None:
        return None
    return int(label["rating"])


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


def _session_feedback_source(session: Mapping[str, Any]) -> str:
    request = session.get("request")
    if not isinstance(request, Mapping):
        return DEFAULT_FEEDBACK_SOURCE
    source = request.get("feedback_source") or request.get("label_source") or request.get("source")
    if source is None:
        return DEFAULT_FEEDBACK_SOURCE
    text = str(source).strip()
    return text or DEFAULT_FEEDBACK_SOURCE


def _event_mappings(events: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        return ()
    return tuple(event for event in events if isinstance(event, Mapping))


def _seed_track_ids(value: object) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(_positive_int(track_id, "seed_track_id") for track_id in value)


def _max_source_count(session: Mapping[str, Any], profile: ScoreProfile) -> int:
    request = session.get("request")
    if not isinstance(request, Mapping):
        return len(profile.sources)
    sources = request.get("sources")
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
        return len(profile.sources)
    clean_sources = {str(source).strip().lower() for source in sources if str(source).strip()}
    return max(1, len(clean_sources) or len(profile.sources))


def _clean_risk_weights(weights: Sequence[float]) -> tuple[float, ...]:
    clean_weights = tuple(dict.fromkeys(_risk_weight(weight) for weight in weights))
    if not clean_weights:
        raise ValueError("At least one --weight value is required")
    return clean_weights


def _clean_k_values(k_values: Sequence[int]) -> tuple[int, ...]:
    clean_values = tuple(dict.fromkeys(_positive_int(value, "k") for value in k_values))
    if not clean_values:
        raise ValueError("At least one --k value is required")
    return clean_values


def _risk_weight(value: object) -> float:
    number = _finite_float(value, "weight")
    if number < 0.0 or number > 1.0:
        raise ValueError("weight must be between 0 and 1")
    return number


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        clean_value = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if clean_value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return clean_value


def _optional_positive_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        clean_value = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    if clean_value <= 0:
        return None
    return clean_value


def _finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be finite")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be finite") from error
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _optional_risk(value: object) -> float | None:
    number = _optional_float(value)
    if number is None or number < 0.0 or number > 1.0:
        return None
    return number


def _normalized_score(raw_score: float, max_raw_score: float) -> float:
    if max_raw_score <= 0.0:
        return 0.0
    return raw_score / max_raw_score


def _mean(values: Iterable[float]) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        return 0.0
    return sum(numbers) / len(numbers)


def _mean_or_none(values: Sequence[int | float]) -> float | None:
    numbers = [float(value) for value in values]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _number_distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    numbers = sorted(float(value) for value in values)
    if not numbers:
        return {"count": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None, "mean": None}
    return {
        "count": len(numbers),
        "min": numbers[0],
        "p25": _quantile(numbers, 0.25),
        "median": _quantile(numbers, 0.5),
        "p75": _quantile(numbers, 0.75),
        "max": numbers[-1],
        "mean": sum(numbers) / len(numbers),
    }


def _quantile(numbers: Sequence[float], quantile: float) -> float:
    if len(numbers) == 1:
        return numbers[0]
    position = (len(numbers) - 1) * quantile
    lower_index = int(math.floor(position))
    upper_index = int(math.ceil(position))
    if lower_index == upper_index:
        return numbers[lower_index]
    fraction = position - lower_index
    return numbers[lower_index] * (1.0 - fraction) + numbers[upper_index] * fraction


def _variant_key(weight: float) -> str:
    return f"{RISK_WEIGHT_METRIC_PREFIX}:{weight:g}"
