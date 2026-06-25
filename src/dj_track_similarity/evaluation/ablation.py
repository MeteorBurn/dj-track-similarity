from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
from typing import TYPE_CHECKING, Any

from .candidates import ALLOWED_CANDIDATE_SOURCES, DEFAULT_FEEDBACK_SOURCE
from .metrics import (
    bad_suggestion_rate_at_k,
    explanation_tag_agreement_at_k,
    hit_rate_at_k,
    maybe_rate_at_k,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
    reject_rate_at_k,
    strong_match_rate_at_k,
)
from .judged import (
    build_judged_label_gate,
    matching_label as matched_judged_label,
    report_status_for_judged_gate,
    session_feedback_source as judged_session_feedback_source,
)
from .reports import RELEVANCE_THRESHOLD
from .score_profiles import LABEL_POLICY, ScoreProfile, rank_candidates_with_profile, score_profile_to_dict

if TYPE_CHECKING:
    from dj_track_similarity.database import LibraryDatabase


DEFAULT_RRF_K = 60
DEFAULT_K_VALUES = (5, 10, 20)


@dataclass(frozen=True)
class SourceContribution:
    rank: int | None
    score: float | None


@dataclass(frozen=True)
class CandidateEvent:
    candidate_track_id: int
    source_contributions: Mapping[str, SourceContribution]


@dataclass(frozen=True)
class CandidatePoolSession:
    session_id: int
    mode: str
    seed_track_ids: tuple[int, ...]
    feedback_source: str
    candidate_events: tuple[CandidateEvent, ...]


@dataclass(frozen=True)
class RankedCandidate:
    candidate_track_id: int
    rank_score: float


@dataclass(frozen=True)
class SessionVariant:
    ranked_candidates: tuple[RankedCandidate, ...]
    relevances_for_metrics: tuple[int, ...]
    judged_relevances: tuple[int, ...]
    judged_candidate_track_ids: tuple[int, ...]
    unjudged_candidate_track_ids: tuple[int, ...]

    @property
    def judged_results(self) -> int:
        return len(self.judged_relevances)

    @property
    def unjudged_results(self) -> int:
        return len(self.unjudged_candidate_track_ids)


def build_source_ablation_report(
    db: LibraryDatabase,
    *,
    k_values: Sequence[int] = DEFAULT_K_VALUES,
    rrf_k: int = DEFAULT_RRF_K,
    score_profile: ScoreProfile | None = None,
    judged_only: bool = False,
) -> dict[str, Any]:
    clean_k_values = _clean_k_values(k_values)
    clean_rrf_k = _positive_int(rrf_k, "rrf_k")
    clean_score_profile = _clean_score_profile(score_profile)
    raw_sessions = db.list_search_sessions_with_events()
    sessions = _candidate_pool_sessions(raw_sessions)
    feedback_map = db.get_pair_feedback_map()
    judged_gate = build_judged_label_gate(raw_sessions, feedback_map, judged_only=judged_only)
    session_variants = {
        session.session_id: _build_session_variants(session, feedback_map, clean_rrf_k, clean_score_profile, judged_only) for session in sessions
    }
    variant_names = _variant_names(session_variants)
    baseline_metrics = _aggregate_variant_metrics(session_variants, "fusion:rrf_all", clean_k_values)
    score_profile_variant_name = _score_profile_variant_name(clean_score_profile) if clean_score_profile is not None else None
    variants = {
        variant_name: _variant_report(
            variant_name,
            session_variants,
            clean_k_values,
            baseline_metrics,
            score_profile=clean_score_profile if variant_name == score_profile_variant_name else None,
        )
        for variant_name in variant_names
    }
    counts = _report_counts(sessions, session_variants)
    default_status = "ok" if counts["judged_results"] > 0 else "insufficient_data"
    return {
        "status": report_status_for_judged_gate(default_status, judged_gate, judged_only=judged_only),
        "evaluation_mode": judged_gate["evaluation_mode"],
        "label_status": judged_gate["label_status"],
        "judged_pairs": judged_gate["judged_pairs"],
        "judged_seeds": judged_gate["judged_seeds"],
        "can_create_candidate_profile": judged_gate["can_create_candidate_profile"],
        "can_update_defaults": judged_gate["can_update_defaults"],
        "label_guidance": judged_gate["guidance"],
        "k_values": list(clean_k_values),
        "rrf_k": clean_rrf_k,
        "label_policy": LABEL_POLICY,
        "judged_only": judged_only,
        "score_profile": _score_profile_report_metadata(clean_score_profile),
        "counts": counts,
        "judged_label_gate": judged_gate,
        "metric_availability": {"explanation_tag_agreement_at_3": explanation_tag_agreement_at_k(3)},
        "variants": variants,
        "sessions": [_session_report(session, session_variants.get(session.session_id, {})) for session in sessions],
        "confidence_intervals": None,
    }


def _candidate_pool_sessions(sessions: Sequence[Mapping[str, Any]]) -> tuple[CandidatePoolSession, ...]:
    candidate_sessions: list[CandidatePoolSession] = []
    for session in sessions:
        candidate_events = tuple(_candidate_event(event) for event in session.get("events", ()))
        candidate_events = tuple(event for event in candidate_events if event is not None)
        if not candidate_events:
            continue
        candidate_sessions.append(
            CandidatePoolSession(
                session_id=int(session["id"]),
                mode=str(session["mode"]),
                seed_track_ids=tuple(int(track_id) for track_id in session["seed_track_ids"]),
                feedback_source=_session_feedback_source(session),
                candidate_events=candidate_events,
            ),
        )
    return tuple(candidate_sessions)


def _candidate_event(event: Mapping[str, Any]) -> CandidateEvent | None:
    candidate_track_id = int(event["track_id"])
    source_contributions = _source_contributions(event.get("score_breakdown"))
    if not source_contributions:
        return None
    return CandidateEvent(candidate_track_id=candidate_track_id, source_contributions=source_contributions)


def _source_contributions(score_breakdown: object) -> dict[str, SourceContribution]:
    if not isinstance(score_breakdown, Mapping):
        return {}
    source_payload = _source_payload(score_breakdown)
    contributions: dict[str, SourceContribution] = {}
    for source, payload in source_payload.items():
        source_name = str(source).strip().lower()
        if source_name not in ALLOWED_CANDIDATE_SOURCES:
            continue
        contribution = _parse_source_contribution(payload)
        if contribution is None:
            continue
        contributions[source_name] = contribution
    return contributions


def _source_payload(score_breakdown: Mapping[str, Any]) -> Mapping[str, Any]:
    sources = score_breakdown.get("sources")
    if isinstance(sources, Mapping):
        return sources
    sources_json = score_breakdown.get("sources_json")
    if isinstance(sources_json, str) and sources_json.strip():
        try:
            parsed_sources = json.loads(sources_json)
        except json.JSONDecodeError:
            parsed_sources = None
        if isinstance(parsed_sources, Mapping):
            return parsed_sources
    return {source: score_breakdown[source] for source in ALLOWED_CANDIDATE_SOURCES if source in score_breakdown}


def _parse_source_contribution(payload: object) -> SourceContribution | None:
    if isinstance(payload, Mapping):
        rank = _optional_positive_rank(payload.get("rank"))
        score = _optional_finite_float(payload.get("score"))
        if rank is None and score is None:
            return None
        return SourceContribution(rank=rank, score=score)
    score = _optional_finite_float(payload)
    if score is None:
        return None
    return SourceContribution(rank=None, score=score)


def _build_session_variants(
    session: CandidatePoolSession,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    rrf_k: int,
    score_profile: ScoreProfile | None,
    judged_only: bool,
) -> dict[str, SessionVariant]:
    source_ranks = _source_ranks(session.candidate_events)
    if not source_ranks:
        return {}

    variants: dict[str, tuple[RankedCandidate, ...]] = {
        f"source:{source}": _source_ranking(source_ranks[source])
        for source in ALLOWED_CANDIDATE_SOURCES
        if source in source_ranks
    }
    sources_seen = tuple(source for source in ALLOWED_CANDIDATE_SOURCES if source in source_ranks)
    variants["fusion:rrf_all"] = _rrf_ranking(source_ranks, sources_seen, rrf_k)
    if score_profile is not None:
        variants[_score_profile_variant_name(score_profile)] = _weighted_rrf_ranking(source_ranks, score_profile, rrf_k)
    if len(sources_seen) >= 2:
        for removed_source in sources_seen:
            kept_sources = tuple(source for source in sources_seen if source != removed_source)
            variants[f"fusion:rrf_without_{removed_source}"] = _rrf_ranking(source_ranks, kept_sources, rrf_k)

    return {
        variant_name: _session_variant(ranked_candidates, session, feedback_map, judged_only)
        for variant_name, ranked_candidates in variants.items()
        if ranked_candidates
    }


def _source_ranks(candidate_events: Sequence[CandidateEvent]) -> dict[str, dict[int, int]]:
    sources = sorted({source for event in candidate_events for source in event.source_contributions})
    return {
        source: ranks
        for source in sources
        if (ranks := _ranks_for_source(candidate_events, source))
    }


def _ranks_for_source(candidate_events: Sequence[CandidateEvent], source: str) -> dict[int, int]:
    explicit_ranks: dict[int, int] = {}
    score_only_candidates: list[tuple[float, int]] = []
    for event in candidate_events:
        contribution = event.source_contributions.get(source)
        if contribution is None:
            continue
        if contribution.rank is not None:
            explicit_ranks[event.candidate_track_id] = contribution.rank
            continue
        if contribution.score is not None:
            score_only_candidates.append((contribution.score, event.candidate_track_id))

    inferred_start_rank = max(explicit_ranks.values(), default=0) + 1
    inferred_ranks = {
        candidate_track_id: inferred_start_rank + offset
        for offset, (_score, candidate_track_id) in enumerate(sorted(score_only_candidates, key=lambda item: (-item[0], item[1])))
    }
    return {**explicit_ranks, **inferred_ranks}


def _source_ranking(source_ranks: Mapping[int, int]) -> tuple[RankedCandidate, ...]:
    return tuple(
        RankedCandidate(candidate_track_id=candidate_track_id, rank_score=1 / rank)
        for candidate_track_id, rank in sorted(source_ranks.items(), key=lambda item: (item[1], item[0]))
    )


def _rrf_ranking(
    source_ranks: Mapping[str, Mapping[int, int]],
    sources: Sequence[str],
    rrf_k: int,
) -> tuple[RankedCandidate, ...]:
    candidate_scores: dict[int, float] = {}
    candidate_best_ranks: dict[int, int] = {}
    for source in sources:
        for candidate_track_id, rank in source_ranks[source].items():
            candidate_scores[candidate_track_id] = candidate_scores.get(candidate_track_id, 0.0) + 1 / (rrf_k + rank)
            candidate_best_ranks[candidate_track_id] = min(candidate_best_ranks.get(candidate_track_id, rank), rank)
    return tuple(
        RankedCandidate(candidate_track_id=candidate_track_id, rank_score=score)
        for candidate_track_id, score in sorted(
            candidate_scores.items(),
            key=lambda item: (-item[1], candidate_best_ranks[item[0]], item[0]),
        )
    )


def _weighted_rrf_ranking(
    source_ranks: Mapping[str, Mapping[int, int]],
    score_profile: ScoreProfile,
    rrf_k: int,
) -> tuple[RankedCandidate, ...]:
    candidate_contributions = _candidate_contributions_from_source_ranks(source_ranks)
    return tuple(
        RankedCandidate(candidate_track_id=candidate.candidate_track_id, rank_score=candidate.rank_score)
        for candidate in rank_candidates_with_profile(candidate_contributions, score_profile, rrf_k=rrf_k)
    )


def _candidate_contributions_from_source_ranks(source_ranks: Mapping[str, Mapping[int, int]]) -> dict[int, dict[str, dict[str, int]]]:
    candidate_contributions: dict[int, dict[str, dict[str, int]]] = {}
    for source, ranks in source_ranks.items():
        for candidate_track_id, rank in ranks.items():
            candidate_contributions.setdefault(candidate_track_id, {})[source] = {"rank": rank}
    return candidate_contributions


def _session_variant(
    ranked_candidates: Sequence[RankedCandidate],
    session: CandidatePoolSession,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    judged_only: bool,
) -> SessionVariant:
    relevances_for_metrics: list[int] = []
    judged_relevances: list[int] = []
    judged_candidate_track_ids: list[int] = []
    unjudged_candidate_track_ids: list[int] = []
    for candidate in ranked_candidates:
        label = _matching_label(session.seed_track_ids, candidate.candidate_track_id, session.feedback_source, feedback_map)
        if label is None:
            unjudged_candidate_track_ids.append(candidate.candidate_track_id)
            if not judged_only:
                relevances_for_metrics.append(0)
            continue
        rating = int(label["rating"])
        relevances_for_metrics.append(rating)
        judged_relevances.append(rating)
        judged_candidate_track_ids.append(candidate.candidate_track_id)
    return SessionVariant(
        ranked_candidates=tuple(ranked_candidates),
        relevances_for_metrics=tuple(relevances_for_metrics),
        judged_relevances=tuple(judged_relevances),
        judged_candidate_track_ids=tuple(judged_candidate_track_ids),
        unjudged_candidate_track_ids=tuple(unjudged_candidate_track_ids),
    )


def _matching_label(
    seed_track_ids: Sequence[int],
    candidate_track_id: int,
    preferred_source: str,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    return matched_judged_label(seed_track_ids, candidate_track_id, preferred_source, feedback_map)


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


def _variant_names(session_variants: Mapping[int, Mapping[str, SessionVariant]]) -> tuple[str, ...]:
    names = {variant_name for variants in session_variants.values() for variant_name in variants}
    source_names = tuple(f"source:{source}" for source in ALLOWED_CANDIDATE_SOURCES if f"source:{source}" in names)
    fusion_names = tuple(name for name in sorted(names) if name.startswith("fusion:"))
    return source_names + fusion_names


def _variant_report(
    variant_name: str,
    session_variants: Mapping[int, Mapping[str, SessionVariant]],
    k_values: Sequence[int],
    baseline_metrics: Mapping[str, float | int],
    *,
    score_profile: ScoreProfile | None = None,
) -> dict[str, Any]:
    metrics = _aggregate_variant_metrics(session_variants, variant_name, k_values)
    report = {
        "type": variant_name.split(":", 1)[0],
        "sources": _variant_sources(variant_name, score_profile),
        "counts": _variant_counts(session_variants, variant_name),
        "metrics": metrics,
        "delta_vs_fusion_rrf_all": _metric_deltas(metrics, baseline_metrics),
    }
    if score_profile is not None:
        report["score_profile"] = _score_profile_report_metadata(score_profile)
    return report


def _variant_sources(variant_name: str, score_profile: ScoreProfile | None = None) -> list[str]:
    if variant_name.startswith("source:"):
        return [variant_name.split(":", 1)[1]]
    if variant_name.startswith("fusion:weighted_rrf:") and score_profile is not None:
        return [source for source in score_profile.sources if score_profile.weights[source] > 0]
    if variant_name == "fusion:rrf_all":
        return list(ALLOWED_CANDIDATE_SOURCES)
    if variant_name.startswith("fusion:rrf_without_"):
        removed_source = variant_name.removeprefix("fusion:rrf_without_")
        return [source for source in ALLOWED_CANDIDATE_SOURCES if source != removed_source]
    return []


def _aggregate_variant_metrics(
    session_variants: Mapping[int, Mapping[str, SessionVariant]],
    variant_name: str,
    k_values: Sequence[int],
) -> dict[str, float]:
    relevance_lists = [
        list(variant.relevances_for_metrics)
        for variants in session_variants.values()
        if (variant := variants.get(variant_name)) is not None and variant.judged_results > 0
    ]
    if not relevance_lists:
        return _empty_metrics(k_values)

    metrics: dict[str, float] = {}
    for k in k_values:
        metrics[f"mean_ndcg_at_{k}"] = _mean(ndcg_at_k(relevances, k) for relevances in relevance_lists)
        metrics[f"mean_average_precision_at_{k}"] = mean_average_precision(
            relevance_lists,
            k,
            threshold=RELEVANCE_THRESHOLD,
        )
        metrics[f"mean_reciprocal_rank_at_{k}"] = mean_reciprocal_rank(
            relevance_lists,
            k,
            threshold=RELEVANCE_THRESHOLD,
        )
        metrics[f"mean_precision_at_{k}"] = _mean(
            precision_at_k(relevances, k, threshold=RELEVANCE_THRESHOLD) for relevances in relevance_lists
        )
        metrics[f"mean_bad_suggestion_rate_at_{k}"] = _mean(
            bad_suggestion_rate_at_k(relevances, k) for relevances in relevance_lists
        )
        metrics[f"mean_strong_match_rate_at_{k}"] = _mean(strong_match_rate_at_k(relevances, k) for relevances in relevance_lists)
        metrics[f"mean_maybe_rate_at_{k}"] = _mean(maybe_rate_at_k(relevances, k) for relevances in relevance_lists)
        metrics[f"mean_reject_rate_at_{k}"] = _mean(reject_rate_at_k(relevances, k) for relevances in relevance_lists)
        metrics[f"hit_rate_at_{k}"] = hit_rate_at_k(relevance_lists, k, threshold=RELEVANCE_THRESHOLD)
    return metrics


def _empty_metrics(k_values: Sequence[int]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for k in k_values:
        metrics[f"mean_ndcg_at_{k}"] = 0.0
        metrics[f"mean_average_precision_at_{k}"] = 0.0
        metrics[f"mean_reciprocal_rank_at_{k}"] = 0.0
        metrics[f"mean_precision_at_{k}"] = 0.0
        metrics[f"mean_bad_suggestion_rate_at_{k}"] = 0.0
        metrics[f"mean_strong_match_rate_at_{k}"] = 0.0
        metrics[f"mean_maybe_rate_at_{k}"] = 0.0
        metrics[f"mean_reject_rate_at_{k}"] = 0.0
        metrics[f"hit_rate_at_{k}"] = 0.0
    return metrics


def _variant_counts(
    session_variants: Mapping[int, Mapping[str, SessionVariant]],
    variant_name: str,
) -> dict[str, Any]:
    variants = [variants[variant_name] for variants in session_variants.values() if variant_name in variants]
    return {
        "sessions_total": len(variants),
        "sessions_with_labels": sum(1 for variant in variants if variant.judged_results > 0),
        "judged_results": sum(variant.judged_results for variant in variants),
        "unjudged_results": sum(variant.unjudged_results for variant in variants),
        "candidate_count": sum(len(variant.ranked_candidates) for variant in variants),
        "label_policy": LABEL_POLICY,
    }


def _metric_deltas(
    metrics: Mapping[str, float | int],
    baseline_metrics: Mapping[str, float | int],
) -> dict[str, float]:
    return {
        metric_name: float(metric_value) - float(baseline_metrics[metric_name])
        for metric_name, metric_value in metrics.items()
        if metric_name in baseline_metrics
    }


def _report_counts(
    sessions: Sequence[CandidatePoolSession],
    session_variants: Mapping[int, Mapping[str, SessionVariant]],
) -> dict[str, Any]:
    baseline_variants = [variants["fusion:rrf_all"] for variants in session_variants.values() if "fusion:rrf_all" in variants]
    return {
        "sessions_total": len(sessions),
        "sessions_with_labels": sum(1 for variant in baseline_variants if variant.judged_results > 0),
        "judged_results": sum(variant.judged_results for variant in baseline_variants),
        "unjudged_results": sum(variant.unjudged_results for variant in baseline_variants),
        "candidate_count": sum(len(session.candidate_events) for session in sessions),
        "label_policy": LABEL_POLICY,
        "sources_seen": _sources_seen(sessions),
    }


def _sources_seen(sessions: Sequence[CandidatePoolSession]) -> list[str]:
    return [
        source
        for source in ALLOWED_CANDIDATE_SOURCES
        if any(source in event.source_contributions for session in sessions for event in session.candidate_events)
    ]


def _clean_score_profile(score_profile: ScoreProfile | None) -> ScoreProfile | None:
    if score_profile is None:
        return None
    return ScoreProfile(**score_profile_to_dict(score_profile))


def _score_profile_variant_name(score_profile: ScoreProfile) -> str:
    return f"fusion:weighted_rrf:{score_profile.name}"


def _score_profile_report_metadata(score_profile: ScoreProfile | None) -> dict[str, Any] | None:
    if score_profile is None:
        return None
    return score_profile_to_dict(score_profile)


def _session_report(
    session: CandidatePoolSession,
    variants: Mapping[str, SessionVariant],
) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "mode": session.mode,
        "seed_track_ids": list(session.seed_track_ids),
        "feedback_source": session.feedback_source,
        "candidate_count": len(session.candidate_events),
        "sources_seen": _sources_seen([session]),
        "variants": {
            variant_name: {
                "candidate_count": len(variant.ranked_candidates),
                "label_policy": LABEL_POLICY,
                "judged_results": variant.judged_results,
                "unjudged_results": variant.unjudged_results,
                "ranked_candidate_track_ids": [candidate.candidate_track_id for candidate in variant.ranked_candidates],
                "judged_candidate_track_ids": list(variant.judged_candidate_track_ids),
                "unjudged_candidate_track_ids": list(variant.unjudged_candidate_track_ids),
                "judged_relevances": list(variant.judged_relevances),
                "relevances_for_metrics": list(variant.relevances_for_metrics),
            }
            for variant_name, variant in sorted(variants.items())
        },
    }


def _session_feedback_source(session: Mapping[str, Any]) -> str:
    return judged_session_feedback_source(session) or DEFAULT_FEEDBACK_SOURCE


def _clean_k_values(k_values: Sequence[int]) -> tuple[int, ...]:
    clean_values = tuple(dict.fromkeys(sorted(_positive_int(k, "k") for k in k_values)))
    if not clean_values:
        raise ValueError("At least one positive --k value is required")
    return clean_values


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


def _optional_positive_rank(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        rank = int(value)
    except (TypeError, ValueError):
        return None
    if rank <= 0:
        return None
    return rank


def _optional_finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(float(value) for value in items) / len(items)
