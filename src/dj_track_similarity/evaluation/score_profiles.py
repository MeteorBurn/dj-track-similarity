from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from .candidates import ALLOWED_CANDIDATE_SOURCES, DEFAULT_FEEDBACK_SOURCE
from .metrics import (
    bad_suggestion_rate_at_k,
    hit_rate_at_k,
    mean_average_precision,
    mean_reciprocal_rank,
    ndcg_at_k,
    precision_at_k,
)
from .reports import RELEVANCE_THRESHOLD

if TYPE_CHECKING:
    from dj_track_similarity.database import LibraryDatabase


SCORE_PROFILE_VERSION = 1
PROFILE_KIND: Literal["unsupervised_source_profile"] = "unsupervised_source_profile"
WEIGHT_KIND: Literal["unsupervised_internal_profile"] = "unsupervised_internal_profile"
DEFAULT_RRF_K = 60
DEFAULT_K_VALUES = (5, 10)
WEIGHT_SUM_TOLERANCE = 1e-6
LABEL_POLICY = "unjudged_as_non_relevant_preserve_rank_positions"
DEFAULT_LIMITATIONS = (
    "This is an unsupervised automatic internal score profile built from source coverage and agreement only.",
    "These weights are not probability, calibrated confidence, or a direct measure of DJ taste.",
    "This profile is not human ground truth; manual feedback remains optional validation and audit data.",
    "Applying the profile ranks recorded candidate pools only; it does not write audio files, train classifiers, or change production search scoring.",
)


@dataclass(frozen=True)
class ScoreProfile:
    name: str
    profile_kind: Literal["unsupervised_source_profile"]
    weight_kind: Literal["unsupervised_internal_profile"]
    sources: list[str]
    weights: dict[str, float]
    created_at: str
    source_report_summary: dict[str, Any]
    limitations: list[str]
    version: int = SCORE_PROFILE_VERSION


@dataclass(frozen=True)
class RankedProfileCandidate:
    candidate_track_id: int
    rank_score: float


def build_score_profile_from_source_report(report: Mapping[str, Any], name: str) -> ScoreProfile:
    if not isinstance(report, Mapping):
        raise ValueError("Source profile report must be a JSON object")
    if report.get("status") != "ok":
        raise ValueError(f"Source profile report status must be ok before building a score profile; found {report.get('status')!r}")
    if report.get("profile_kind") != PROFILE_KIND:
        raise ValueError(f"Expected source profile report kind {PROFILE_KIND!r}")

    recommended_weights = _required_mapping(report, "recommended_weights")
    if recommended_weights.get("weight_kind") != WEIGHT_KIND:
        raise ValueError(f"Expected recommended_weights.weight_kind {WEIGHT_KIND!r}")

    profile = ScoreProfile(
        name=_profile_name(name),
        profile_kind=PROFILE_KIND,
        weight_kind=WEIGHT_KIND,
        sources=_source_list(report.get("sources")),
        weights=_weights(recommended_weights.get("weights")),
        created_at=_utc_timestamp(),
        source_report_summary=_source_report_summary(report),
        limitations=list(DEFAULT_LIMITATIONS),
        version=SCORE_PROFILE_VERSION,
    )
    validate_score_profile(profile)
    return profile


def build_score_profile_from_source_profile_report(report: Mapping[str, Any], name: str, rrf_k: int | None = None) -> ScoreProfile:
    _ = rrf_k
    return build_score_profile_from_source_report(report, name=name)


def load_score_profile(path: str | Path) -> ScoreProfile:
    input_path = Path(path)
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Score profile JSON is invalid: {error.msg}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("Score profile JSON must be an object")
    profile = _score_profile_from_mapping(payload)
    validate_score_profile(profile)
    return profile


def save_score_profile(profile: ScoreProfile, path: str | Path) -> None:
    validate_score_profile(profile)
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(score_profile_to_dict(profile), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")


def validate_score_profile(profile: ScoreProfile | Mapping[str, Any]) -> None:
    clean_profile = _score_profile_from_mapping(profile) if isinstance(profile, Mapping) else profile
    if not isinstance(clean_profile, ScoreProfile):
        raise ValueError("score profile must be a ScoreProfile or JSON object")
    if clean_profile.profile_kind != PROFILE_KIND:
        raise ValueError(f"profile_kind must be {PROFILE_KIND!r}")
    if clean_profile.weight_kind != WEIGHT_KIND:
        raise ValueError(f"weight_kind must be {WEIGHT_KIND!r}")
    if clean_profile.version != SCORE_PROFILE_VERSION:
        raise ValueError(f"Unsupported score profile version; expected {SCORE_PROFILE_VERSION}")

    sources = _source_list(clean_profile.sources)
    weights = _weights(clean_profile.weights)
    if set(weights) != set(sources):
        missing = sorted(set(sources) - set(weights))
        unknown = sorted(set(weights) - set(sources))
        details = []
        if missing:
            details.append(f"missing weights for: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown weights for: {', '.join(unknown)}")
        raise ValueError(f"Score profile weights must match sources exactly ({'; '.join(details)})")
    if not math.isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=WEIGHT_SUM_TOLERANCE):
        raise ValueError("Score profile weights must sum approximately to 1.0")
    if not _limitations_are_explicit(clean_profile.limitations):
        raise ValueError("Score profile limitations must state it is unsupervised, not probability, and not human ground truth")


def score_profile_to_dict(profile: ScoreProfile) -> dict[str, Any]:
    validate_score_profile(profile)
    return asdict(profile)


def rank_candidates_with_profile(
    candidate_source_contributions: Mapping[int, Mapping[str, Any]],
    profile: ScoreProfile,
    rrf_k: int = DEFAULT_RRF_K,
) -> tuple[RankedProfileCandidate, ...]:
    validate_score_profile(profile)
    clean_rrf_k = _positive_int(rrf_k, "rrf_k")
    candidate_scores: dict[int, float] = {}
    candidate_best_ranks: dict[int, int] = {}
    for candidate_track_id, source_contributions in candidate_source_contributions.items():
        clean_candidate_id = _positive_int(candidate_track_id, "candidate_track_id")
        if not isinstance(source_contributions, Mapping):
            raise ValueError("candidate source contributions must be source mappings")
        for source in profile.sources:
            weight = profile.weights[source]
            if weight <= 0:
                continue
            rank = _rank_from_contribution(source_contributions.get(source))
            if rank is None:
                continue
            candidate_scores[clean_candidate_id] = candidate_scores.get(clean_candidate_id, 0.0) + weight * (1.0 / (clean_rrf_k + rank))
            candidate_best_ranks[clean_candidate_id] = min(candidate_best_ranks.get(clean_candidate_id, rank), rank)
    return tuple(
        RankedProfileCandidate(candidate_track_id=candidate_track_id, rank_score=score)
        for candidate_track_id, score in sorted(
            candidate_scores.items(),
            key=lambda item: (-item[1], candidate_best_ranks[item[0]], item[0]),
        )
    )


def build_score_profile_application_report(
    db: LibraryDatabase,
    profile: ScoreProfile,
    *,
    k_values: Sequence[int] = DEFAULT_K_VALUES,
    rrf_k: int = DEFAULT_RRF_K,
) -> dict[str, Any]:
    validate_score_profile(profile)
    clean_k_values = _clean_k_values(k_values)
    clean_rrf_k = _positive_int(rrf_k, "rrf_k")
    sessions = db.list_search_sessions_with_events()
    feedback_map = db.get_pair_feedback_map()
    ranked_sessions = [
        ranked_session
        for session in sessions
        if (ranked_session := _ranked_session_report(session, feedback_map, profile, clean_rrf_k)) is not None
    ]
    judged_results = sum(int(session["judged_results"]) for session in ranked_sessions)
    unjudged_results = sum(int(session["unjudged_results"]) for session in ranked_sessions)
    sessions_with_labels = sum(1 for session in ranked_sessions if int(session["judged_results"]) > 0)
    ranked_candidate_count = sum(int(session["ranked_candidate_count"]) for session in ranked_sessions)
    report: dict[str, Any] = {
        "status": "ok" if ranked_sessions else "insufficient_data",
        "label_status": "ok" if judged_results > 0 else "insufficient_data",
        "label_policy": LABEL_POLICY,
        "profile_name": profile.name,
        "profile_kind": profile.profile_kind,
        "weight_kind": profile.weight_kind,
        "weights": dict(profile.weights),
        "sources": list(profile.sources),
        "rrf_k": clean_rrf_k,
        "k_values": list(clean_k_values),
        "sessions_total": len(sessions),
        "ranked_session_count": len(ranked_sessions),
        "sessions_with_labels": sessions_with_labels,
        "judged_results": judged_results,
        "unjudged_results": unjudged_results,
        "ranked_candidate_count": ranked_candidate_count,
        "counts": {
            "sessions_total": len(sessions),
            "ranked_session_count": len(ranked_sessions),
            "sessions_with_labels": sessions_with_labels,
            "judged_results": judged_results,
            "unjudged_results": unjudged_results,
            "ranked_candidate_count": ranked_candidate_count,
            "label_policy": LABEL_POLICY,
        },
        "ranked_sessions": ranked_sessions,
        "limitations": list(profile.limitations),
        "note": "Automatic internal score profile using weighted RRF over recorded source ranks only; unjudged candidates are treated as non-relevant for conservative metrics without changing rank positions. Not probability, not human ground truth, and not production search scoring.",
    }
    if judged_results > 0:
        report["metrics"] = _aggregate_profile_metrics(ranked_sessions, clean_k_values)
    return report


def _ranked_session_report(
    session: Mapping[str, Any],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    profile: ScoreProfile,
    rrf_k: int,
) -> dict[str, Any] | None:
    candidate_source_contributions = _candidate_source_contributions(session.get("events"))
    if not candidate_source_contributions:
        return None

    ranked_candidates = rank_candidates_with_profile(candidate_source_contributions, profile, rrf_k=rrf_k)
    if not ranked_candidates:
        return None

    seed_track_ids = tuple(_positive_int(track_id, "seed_track_id") for track_id in session.get("seed_track_ids", ()))
    feedback_source = _session_feedback_source(session)
    relevances_for_metrics: list[int] = []
    judged_relevances: list[int] = []
    judged_candidate_track_ids: list[int] = []
    unjudged_candidate_track_ids: list[int] = []
    for candidate in ranked_candidates:
        label = _matching_label(seed_track_ids, candidate.candidate_track_id, feedback_source, feedback_map)
        if label is None:
            relevances_for_metrics.append(0)
            unjudged_candidate_track_ids.append(candidate.candidate_track_id)
            continue
        rating = int(label["rating"])
        relevances_for_metrics.append(rating)
        judged_relevances.append(rating)
        judged_candidate_track_ids.append(candidate.candidate_track_id)

    return {
        "session_id": int(session["id"]),
        "mode": str(session["mode"]),
        "seed_track_ids": list(seed_track_ids),
        "feedback_source": feedback_source,
        "label_policy": LABEL_POLICY,
        "ranked_candidate_count": len(ranked_candidates),
        "ranked_candidate_track_ids": [candidate.candidate_track_id for candidate in ranked_candidates],
        "ranked_candidates": [asdict(candidate) for candidate in ranked_candidates],
        "judged_results": len(judged_relevances),
        "unjudged_results": len(unjudged_candidate_track_ids),
        "judged_candidate_track_ids": judged_candidate_track_ids,
        "unjudged_candidate_track_ids": unjudged_candidate_track_ids,
        "judged_relevances": judged_relevances,
        "relevances_for_metrics": relevances_for_metrics,
    }


def _candidate_source_contributions(events: object) -> dict[int, dict[str, Any]]:
    if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
        return {}
    contributions: dict[int, dict[str, Any]] = {}
    for event in events:
        if not isinstance(event, Mapping):
            continue
        source_payload = _source_payload(event)
        if not source_payload:
            continue
        candidate_track_id = _positive_int(event.get("track_id"), "candidate_track_id")
        contributions[candidate_track_id] = dict(source_payload)
    return contributions


def _source_payload(event: Mapping[str, Any]) -> Mapping[str, Any]:
    sources_json = event.get("sources_json")
    if isinstance(sources_json, str) and sources_json.strip():
        try:
            parsed_sources = json.loads(sources_json)
        except json.JSONDecodeError:
            parsed_sources = None
        if isinstance(parsed_sources, Mapping):
            return parsed_sources

    score_breakdown = event.get("score_breakdown")
    if not isinstance(score_breakdown, Mapping):
        return {}
    sources = score_breakdown.get("sources")
    if isinstance(sources, Mapping):
        return sources
    nested_sources_json = score_breakdown.get("sources_json")
    if isinstance(nested_sources_json, str) and nested_sources_json.strip():
        try:
            parsed_nested_sources = json.loads(nested_sources_json)
        except json.JSONDecodeError:
            parsed_nested_sources = None
        if isinstance(parsed_nested_sources, Mapping):
            return parsed_nested_sources
    return {source: score_breakdown[source] for source in ALLOWED_CANDIDATE_SOURCES if source in score_breakdown}


def _rank_from_contribution(value: object) -> int | None:
    if not isinstance(value, Mapping):
        return None
    rank = value.get("rank")
    if rank is None or isinstance(rank, bool):
        return None
    try:
        clean_rank = int(rank)
    except (TypeError, ValueError):
        return None
    if clean_rank <= 0:
        return None
    return clean_rank


def _aggregate_profile_metrics(ranked_sessions: Sequence[Mapping[str, Any]], k_values: Sequence[int]) -> dict[str, float]:
    relevance_lists = [list(session["relevances_for_metrics"]) for session in ranked_sessions if int(session["judged_results"]) > 0]
    if not relevance_lists:
        return _empty_metrics(k_values)

    metrics: dict[str, float] = {}
    for k in k_values:
        metrics[f"mean_ndcg_at_{k}"] = _mean(ndcg_at_k(relevances, k) for relevances in relevance_lists)
        metrics[f"mean_average_precision_at_{k}"] = mean_average_precision(relevance_lists, k, threshold=RELEVANCE_THRESHOLD)
        metrics[f"mean_reciprocal_rank_at_{k}"] = mean_reciprocal_rank(relevance_lists, k, threshold=RELEVANCE_THRESHOLD)
        metrics[f"mean_precision_at_{k}"] = _mean(precision_at_k(relevances, k, threshold=RELEVANCE_THRESHOLD) for relevances in relevance_lists)
        metrics[f"mean_bad_suggestion_rate_at_{k}"] = _mean(bad_suggestion_rate_at_k(relevances, k) for relevances in relevance_lists)
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
        metrics[f"hit_rate_at_{k}"] = 0.0
    return metrics


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


def _score_profile_from_mapping(payload: Mapping[str, Any]) -> ScoreProfile:
    return ScoreProfile(
        name=_profile_name(payload.get("name")),
        profile_kind=_literal_text(payload, "profile_kind", PROFILE_KIND),
        weight_kind=_literal_text(payload, "weight_kind", WEIGHT_KIND),
        sources=_source_list(payload.get("sources")),
        weights=_weights(payload.get("weights")),
        created_at=_required_text(payload, "created_at"),
        source_report_summary=dict(_required_mapping(payload, "source_report_summary")),
        limitations=_limitations(payload.get("limitations")),
        version=_positive_int(payload.get("version", SCORE_PROFILE_VERSION), "version"),
    )


def _source_report_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    recommended_weights = report.get("recommended_weights") if isinstance(report.get("recommended_weights"), Mapping) else {}
    return {
        "status": report.get("status"),
        "profile_kind": report.get("profile_kind"),
        "weight_kind": report.get("weight_kind") or recommended_weights.get("weight_kind"),
        "sources": _source_list(report.get("sources")),
        "seed_count": report.get("seed_count"),
        "per_source": _per_source_summary(report.get("per_source")),
        "consensus": _consensus_summary(report.get("consensus")),
        "warnings": _string_list(report.get("warnings")),
        "recommended_weight_note": recommended_weights.get("note"),
    }


def _per_source_summary(value: object) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    summary: dict[str, dict[str, Any]] = {}
    for source, metrics in value.items():
        source_name = str(source).strip().lower()
        if not source_name or not isinstance(metrics, Mapping):
            continue
        summary[source_name] = {
            "seeds_with_results": metrics.get("seeds_with_results"),
            "seed_coverage_rate": metrics.get("seed_coverage_rate"),
            "consensus_support": metrics.get("consensus_support"),
            "conflict_rate": metrics.get("conflict_rate"),
        }
    return summary


def _consensus_summary(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        "method": value.get("method"),
        "rrf_k": value.get("rrf_k"),
        "top_k": value.get("top_k"),
        "seeds_with_consensus": value.get("seeds_with_consensus"),
    }


def _source_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("sources must be a list of source names")
    sources = [str(source).strip().lower() for source in value if str(source).strip()]
    if not sources:
        raise ValueError("sources must contain at least one source")
    if len(set(sources)) != len(sources):
        raise ValueError("sources must not contain duplicates")
    unknown_sources = [source for source in sources if source not in ALLOWED_CANDIDATE_SOURCES]
    if unknown_sources:
        allowed = ", ".join(ALLOWED_CANDIDATE_SOURCES)
        raise ValueError(f"Unsupported source(s): {', '.join(unknown_sources)}. Allowed: {allowed}")
    return sources


def _weights(value: object) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("weights must be a JSON object")
    weights: dict[str, float] = {}
    for source, weight in value.items():
        source_name = str(source).strip().lower()
        if not source_name:
            raise ValueError("weights keys must be non-empty source names")
        if source_name in weights:
            raise ValueError(f"Duplicate source weight after normalization: {source_name}")
        if source_name not in ALLOWED_CANDIDATE_SOURCES:
            allowed = ", ".join(ALLOWED_CANDIDATE_SOURCES)
            raise ValueError(f"Unsupported source weight: {source_name}. Allowed: {allowed}")
        weights[source_name] = _non_negative_finite_float(weight, f"weights.{source_name}")
    if not weights:
        raise ValueError("At least one source weight is required")
    if not any(weight > 0 for weight in weights.values()):
        raise ValueError("At least one source weight must be positive")
    return weights


def _limitations_are_explicit(limitations: Sequence[str]) -> bool:
    text = "\n".join(limitations).lower()
    return "unsupervised" in text and "not probability" in text and "not human ground truth" in text


def _limitations(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("limitations must be a list of strings")
    limitations = [str(item).strip() for item in value if str(item).strip()]
    if not limitations:
        raise ValueError("limitations must contain at least one item")
    return limitations


def _required_mapping(payload: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a JSON object")
    return value


def _literal_text(payload: Mapping[str, Any], field_name: str, expected: str) -> Any:
    value = _required_text(payload, field_name)
    if value != expected:
        raise ValueError(f"{field_name} must be {expected!r}")
    return value


def _required_text(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _profile_name(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("name must be a non-empty string")
    return value.strip()


def _non_negative_finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a finite non-negative number") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
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


def _clean_k_values(k_values: Sequence[int]) -> tuple[int, ...]:
    clean_values = tuple(dict.fromkeys(sorted(_positive_int(k, "k") for k in k_values)))
    if not clean_values:
        raise ValueError("At least one positive --k value is required")
    return clean_values


def _string_list(value: object) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value]


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(float(value) for value in items) / len(items)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
