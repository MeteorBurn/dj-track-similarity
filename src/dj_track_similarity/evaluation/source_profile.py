from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
from dataclasses import dataclass
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .candidates import (
    ALLOWED_CANDIDATE_SOURCES,
    CandidateExportRequest,
    CandidatePoolRow,
    generate_candidate_pool_rows,
)
from .calibration import score_quantiles
from .seed_sampling import export_seed_sample

if TYPE_CHECKING:
    from ..database import LibraryDatabase


DEFAULT_PROFILE_SOURCES = ("mert", "maest", "sonara")
DEFAULT_PROFILE_TOP_K = (10,)
DEFAULT_RRF_K = 60
WEIGHT_KIND = "unsupervised_internal_profile"
PROFILE_KIND = "unsupervised_source_profile"
LIMITATIONS = (
    "This is an unsupervised internal consistency profile over the current library analysis data only.",
    "Recommended weights are not trained weights, probability calibration, confidence, or proof of human DJ taste.",
    "Manual feedback remains optional validation/audit data and is not required by this profile.",
    "The profile reads existing SQLite analysis/search data and does not write to audio files or train classifiers.",
)


@dataclass(frozen=True)
class SourceProfileRequest:
    seed_track_ids: tuple[int, ...]
    sources: tuple[str, ...]
    per_source: int
    top_k_values: tuple[int, ...]
    random_seed: int


def build_source_profile(
    db: LibraryDatabase,
    *,
    seed_track_ids: Sequence[int] | None = None,
    sample_count: int = 50,
    sources: Sequence[str] | None = None,
    per_source: int = 30,
    top_k_values: Sequence[int] | None = None,
    random_seed: int = 123,
) -> dict[str, Any]:
    clean_seed_track_ids = _seed_track_ids(db, seed_track_ids, sample_count=sample_count, random_seed=random_seed)
    request = SourceProfileRequest(
        seed_track_ids=clean_seed_track_ids,
        sources=_clean_sources(sources),
        per_source=_positive_int(per_source, "per_source"),
        top_k_values=_clean_top_k_values(top_k_values),
        random_seed=_int_value(random_seed, "random_seed"),
    )
    rows, warnings = generate_candidate_pool_rows(
        db,
        CandidateExportRequest(
            seed_track_ids=request.seed_track_ids,
            sources=request.sources,
            per_source=request.per_source,
            random_seed=request.random_seed,
            record_session=False,
        ),
    )
    return profile_candidate_rows(request, rows, warnings=warnings)


def load_seed_track_ids_from_csv(path: str | Path) -> tuple[int, ...]:
    input_path = Path(path)
    with input_path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        if reader.fieldnames is None or "track_id" not in reader.fieldnames:
            raise ValueError("Seed sample CSV must contain a track_id column")
        return _positive_unique_ints((row.get("track_id") for row in reader), "track_id")


def profile_candidate_rows(
    request: SourceProfileRequest,
    rows: Sequence[CandidatePoolRow],
    *,
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    clean_request = _clean_profile_request(request)
    seed_rankings = _rankings_by_seed(rows, clean_request.sources)
    per_source = _per_source_metrics(seed_rankings, clean_request)
    pairwise_agreement = _pairwise_agreement(seed_rankings, clean_request)
    consensus = _consensus_report(seed_rankings, clean_request)
    recommended_weights = _recommended_weights(per_source, len(clean_request.sources))
    report_warnings = _profile_warnings(per_source, warnings)
    return {
        "status": _profile_status(clean_request.seed_track_ids, per_source),
        "profile_kind": PROFILE_KIND,
        "weight_kind": WEIGHT_KIND,
        "sources": list(clean_request.sources),
        "seed_count": len(clean_request.seed_track_ids),
        "seed_track_ids": list(clean_request.seed_track_ids),
        "per_source": per_source,
        "pairwise_agreement": pairwise_agreement,
        "consensus": consensus,
        "recommended_weights": recommended_weights,
        "warnings": report_warnings,
        "limitations": list(LIMITATIONS),
    }


def _seed_track_ids(
    db: LibraryDatabase,
    seed_track_ids: Sequence[int] | None,
    *,
    sample_count: int,
    random_seed: int,
) -> tuple[int, ...]:
    if seed_track_ids is not None:
        return _positive_unique_ints(seed_track_ids, "seed_track_id")
    sample = export_seed_sample(
        db,
        count=_positive_int(sample_count, "sample_count"),
        random_seed=_int_value(random_seed, "random_seed"),
        require_complete_analysis=False,
    )
    return tuple(row.track_id for row in sample.rows)


def _clean_profile_request(request: SourceProfileRequest) -> SourceProfileRequest:
    return SourceProfileRequest(
        seed_track_ids=_positive_unique_ints(request.seed_track_ids, "seed_track_id"),
        sources=_clean_sources(request.sources),
        per_source=_positive_int(request.per_source, "per_source"),
        top_k_values=_clean_top_k_values(request.top_k_values),
        random_seed=_int_value(request.random_seed, "random_seed"),
    )


def _rankings_by_seed(
    rows: Sequence[CandidatePoolRow],
    sources: Sequence[str],
) -> dict[int, dict[str, dict[int, dict[str, float | int]]]]:
    rankings: dict[int, dict[str, dict[int, dict[str, float | int]]]] = {}
    source_set = set(sources)
    for row in rows:
        seed_rankings = rankings.setdefault(row.seed_track_id, {source: {} for source in sources})
        for source, contribution in row.source_contributions.items():
            if source not in source_set:
                continue
            seed_rankings[source][row.candidate_track_id] = {
                "rank": contribution.rank,
                "score": contribution.score,
            }
    return rankings


def _per_source_metrics(
    seed_rankings: Mapping[int, Mapping[str, Mapping[int, Mapping[str, float | int]]]],
    request: SourceProfileRequest,
) -> dict[str, dict[str, Any]]:
    return {
        source: _source_metrics(source, seed_rankings, request)
        for source in request.sources
    }


def _source_metrics(
    source: str,
    seed_rankings: Mapping[int, Mapping[str, Mapping[int, Mapping[str, float | int]]]],
    request: SourceProfileRequest,
) -> dict[str, Any]:
    top_k = max(request.top_k_values)
    seed_count = len(request.seed_track_ids)
    rankings = [_ranking_for_seed(seed_rankings, seed_track_id, source) for seed_track_id in request.seed_track_ids]
    covered_rankings = [ranking for ranking in rankings if ranking]
    support_values = _source_reciprocal_support_values(source, seed_rankings, request.sources, request.seed_track_ids, top_k)
    conflict_rate = _zero_rate(support_values)
    scores = _source_scores(covered_rankings)
    candidates_returned = sum(len(ranking) for ranking in covered_rankings)
    requested_slots = seed_count * request.per_source
    coverage_rate = _safe_ratio(len(covered_rankings), seed_count)
    consensus_support = _mean(support_values)
    stability_factor = 1.0 if covered_rankings else 0.0
    return {
        "seeds_requested": seed_count,
        "seeds_with_results": len(covered_rankings),
        "seeds_missing_or_empty": seed_count - len(covered_rankings),
        "seed_coverage_rate": coverage_rate,
        "seed_missing_rate": 1.0 - coverage_rate,
        "candidate_slots_requested": requested_slots,
        "candidates_returned": candidates_returned,
        "candidate_missing_rate": 1.0 - _safe_ratio(candidates_returned, requested_slots),
        "average_candidates_per_covered_seed": _safe_ratio(candidates_returned, len(covered_rankings)),
        "consensus_support": consensus_support,
        "average_reciprocal_support_from_other_sources": consensus_support,
        "unsupported_top_candidate_rate": conflict_rate,
        "conflict_rate": conflict_rate,
        "top_candidate_count_for_consensus": len(support_values),
        "stability_factor": stability_factor,
        "score_quantiles": score_quantiles(scores),
    }


def _source_reciprocal_support_values(
    source: str,
    seed_rankings: Mapping[int, Mapping[str, Mapping[int, Mapping[str, float | int]]]],
    sources: Sequence[str],
    seed_track_ids: Sequence[int],
    top_k: int,
) -> list[float]:
    support_values: list[float] = []
    other_sources = tuple(candidate_source for candidate_source in sources if candidate_source != source)
    if not other_sources:
        return [1.0 for seed_track_id in seed_track_ids if _ranking_for_seed(seed_rankings, seed_track_id, source)]

    for seed_track_id in seed_track_ids:
        ranking = _ranking_for_seed(seed_rankings, seed_track_id, source)
        for candidate_track_id in _top_candidate_ids(ranking, top_k):
            support_values.append(_reciprocal_support(seed_rankings, seed_track_id, candidate_track_id, other_sources, top_k))
    return support_values


def _reciprocal_support(
    seed_rankings: Mapping[int, Mapping[str, Mapping[int, Mapping[str, float | int]]]],
    seed_track_id: int,
    candidate_track_id: int,
    other_sources: Sequence[str],
    top_k: int,
) -> float:
    values: list[float] = []
    for source in other_sources:
        contribution = _ranking_for_seed(seed_rankings, seed_track_id, source).get(candidate_track_id)
        if contribution is None:
            values.append(0.0)
            continue
        rank = int(contribution["rank"])
        values.append((1.0 / rank) if rank <= top_k else 0.0)
    return _mean(values)


def _pairwise_agreement(
    seed_rankings: Mapping[int, Mapping[str, Mapping[int, Mapping[str, float | int]]]],
    request: SourceProfileRequest,
) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        left_source: {
            right_source: _pair_metrics(left_source, right_source, seed_rankings, request)
            for right_source in request.sources
        }
        for left_source in request.sources
    }


def _consensus_report(
    seed_rankings: Mapping[int, Mapping[str, Mapping[int, Mapping[str, float | int]]]],
    request: SourceProfileRequest,
) -> dict[str, Any]:
    top_k = max(request.top_k_values)
    per_seed = [
        seed_consensus
        for seed_track_id in request.seed_track_ids
        if (seed_consensus := _seed_consensus(seed_track_id, seed_rankings, request.sources, top_k)) is not None
    ]
    return {
        "method": "reciprocal_rank_fusion",
        "rrf_k": DEFAULT_RRF_K,
        "top_k": top_k,
        "seeds_with_consensus": len(per_seed),
        "per_seed_top_candidate_ids": per_seed,
    }


def _seed_consensus(
    seed_track_id: int,
    seed_rankings: Mapping[int, Mapping[str, Mapping[int, Mapping[str, float | int]]]],
    sources: Sequence[str],
    top_k: int,
) -> dict[str, Any] | None:
    candidate_scores: dict[int, float] = {}
    candidate_best_ranks: dict[int, int] = {}
    sources_seen: list[str] = []
    for source in sources:
        ranking = _ranking_for_seed(seed_rankings, seed_track_id, source)
        if not ranking:
            continue
        sources_seen.append(source)
        for candidate_track_id, contribution in ranking.items():
            rank = int(contribution["rank"])
            candidate_scores[candidate_track_id] = candidate_scores.get(candidate_track_id, 0.0) + 1.0 / (DEFAULT_RRF_K + rank)
            candidate_best_ranks[candidate_track_id] = min(candidate_best_ranks.get(candidate_track_id, rank), rank)
    if not candidate_scores:
        return None
    ranked_candidates = sorted(
        candidate_scores.items(),
        key=lambda item: (-item[1], candidate_best_ranks[item[0]], item[0]),
    )[:top_k]
    return {
        "seed_track_id": seed_track_id,
        "sources_seen": sources_seen,
        "candidate_track_ids": [candidate_track_id for candidate_track_id, _score in ranked_candidates],
    }


def _pair_metrics(
    left_source: str,
    right_source: str,
    seed_rankings: Mapping[int, Mapping[str, Mapping[int, Mapping[str, float | int]]]],
    request: SourceProfileRequest,
) -> dict[str, Any]:
    if left_source == right_source:
        return _self_pair_metrics(left_source, seed_rankings, request)

    comparable_seed_count = 0
    overlaps = {k: [] for k in request.top_k_values}
    jaccards = {k: [] for k in request.top_k_values}
    correlations: list[float] = []
    for seed_track_id in request.seed_track_ids:
        left_ranking = _ranking_for_seed(seed_rankings, seed_track_id, left_source)
        right_ranking = _ranking_for_seed(seed_rankings, seed_track_id, right_source)
        if not left_ranking or not right_ranking:
            continue
        comparable_seed_count += 1
        for k in request.top_k_values:
            left_top = set(_top_candidate_ids(left_ranking, k))
            right_top = set(_top_candidate_ids(right_ranking, k))
            overlaps[k].append(float(len(left_top & right_top)))
            jaccards[k].append(_jaccard(left_top, right_top))
        correlation = _rank_correlation(left_ranking, right_ranking)
        if correlation is not None:
            correlations.append(correlation)

    return {
        "seeds_compared": comparable_seed_count,
        "overlap_at_k": {str(k): _mean(overlaps[k]) for k in request.top_k_values},
        "jaccard_at_k": {str(k): _mean(jaccards[k]) for k in request.top_k_values},
        "rank_agreement": _mean_or_none(correlations),
    }


def _self_pair_metrics(
    source: str,
    seed_rankings: Mapping[int, Mapping[str, Mapping[int, Mapping[str, float | int]]]],
    request: SourceProfileRequest,
) -> dict[str, Any]:
    covered_rankings = [_ranking_for_seed(seed_rankings, seed_track_id, source) for seed_track_id in request.seed_track_ids]
    covered_rankings = [ranking for ranking in covered_rankings if ranking]
    return {
        "seeds_compared": len(covered_rankings),
        "overlap_at_k": {str(k): _mean([float(len(_top_candidate_ids(ranking, k))) for ranking in covered_rankings]) for k in request.top_k_values},
        "jaccard_at_k": {str(k): 1.0 if covered_rankings else 0.0 for k in request.top_k_values},
        "rank_agreement": 1.0 if covered_rankings else None,
    }


def _recommended_weights(per_source: Mapping[str, Mapping[str, Any]], source_count: int) -> dict[str, Any]:
    factors = {
        source: _weight_factors(source_metrics, source_count)
        for source, source_metrics in per_source.items()
    }
    raw_sum = sum(factor["raw_weight"] for factor in factors.values())
    if raw_sum <= 0:
        factors = _coverage_fallback_factors(per_source)
        raw_sum = sum(factor["raw_weight"] for factor in factors.values())
    weights = {
        source: (factor["raw_weight"] / raw_sum if raw_sum > 0 else 0.0)
        for source, factor in factors.items()
    }
    return {
        "weight_kind": WEIGHT_KIND,
        "weights": weights,
        "factors": factors,
        "note": "Weights are normalized non-negative internal diagnostics from coverage, consensus support, and deterministic stability; they are not trained or calibrated probabilities.",
    }


def _weight_factors(source_metrics: Mapping[str, Any], source_count: int) -> dict[str, float]:
    coverage = float(source_metrics["seed_coverage_rate"])
    consensus = 1.0 if source_count == 1 and coverage > 0 else float(source_metrics["consensus_support"])
    stability = float(source_metrics["stability_factor"])
    return {
        "coverage": coverage,
        "consensus_support": consensus,
        "stability_factor": stability,
        "raw_weight": max(0.0, coverage * consensus * stability),
    }


def _coverage_fallback_factors(per_source: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    return {
        source: {
            "coverage": float(source_metrics["seed_coverage_rate"]),
            "consensus_support": 0.0,
            "stability_factor": float(source_metrics["stability_factor"]),
            "raw_weight": max(0.0, float(source_metrics["seed_coverage_rate"]) * float(source_metrics["stability_factor"])),
        }
        for source, source_metrics in per_source.items()
    }


def _profile_warnings(per_source: Mapping[str, Mapping[str, Any]], warnings: Sequence[str]) -> list[str]:
    report_warnings = list(dict.fromkeys(str(warning) for warning in warnings if str(warning).strip()))
    for source, metrics in per_source.items():
        if int(metrics["seeds_with_results"]) == 0:
            report_warnings.append(f"source={source} has no coverage in the sampled seeds; recommended weight is 0")
    return list(dict.fromkeys(report_warnings))


def _profile_status(seed_track_ids: Sequence[int], per_source: Mapping[str, Mapping[str, Any]]) -> str:
    if not seed_track_ids:
        return "insufficient_data"
    if any(int(metrics["seeds_with_results"]) > 0 for metrics in per_source.values()):
        return "ok"
    return "insufficient_data"


def _ranking_for_seed(
    seed_rankings: Mapping[int, Mapping[str, Mapping[int, Mapping[str, float | int]]]],
    seed_track_id: int,
    source: str,
) -> Mapping[int, Mapping[str, float | int]]:
    return seed_rankings.get(seed_track_id, {}).get(source, {})


def _top_candidate_ids(ranking: Mapping[int, Mapping[str, float | int]], k: int) -> tuple[int, ...]:
    return tuple(
        candidate_track_id
        for candidate_track_id, _contribution in sorted(ranking.items(), key=lambda item: (int(item[1]["rank"]), item[0]))[:k]
    )


def _source_scores(rankings: Sequence[Mapping[int, Mapping[str, float | int]]]) -> list[float]:
    return [float(contribution["score"]) for ranking in rankings for contribution in ranking.values()]


def _rank_correlation(
    left_ranking: Mapping[int, Mapping[str, float | int]],
    right_ranking: Mapping[int, Mapping[str, float | int]],
) -> float | None:
    shared_ids = sorted(set(left_ranking) & set(right_ranking))
    if len(shared_ids) < 2:
        return None
    left_ranks = [float(left_ranking[candidate_id]["rank"]) for candidate_id in shared_ids]
    right_ranks = [float(right_ranking[candidate_id]["rank"]) for candidate_id in shared_ids]
    return _pearson_correlation(left_ranks, right_ranks)


def _pearson_correlation(left_values: Sequence[float], right_values: Sequence[float]) -> float | None:
    if len(left_values) != len(right_values) or len(left_values) < 2:
        return None
    left_mean = _mean(left_values)
    right_mean = _mean(right_values)
    numerator = sum((left - left_mean) * (right - right_mean) for left, right in zip(left_values, right_values))
    left_norm = math.sqrt(sum((left - left_mean) ** 2 for left in left_values))
    right_norm = math.sqrt(sum((right - right_mean) ** 2 for right in right_values))
    if left_norm == 0 or right_norm == 0:
        return None
    return numerator / (left_norm * right_norm)


def _jaccard(left: set[int], right: set[int]) -> float:
    if not left and not right:
        return 0.0
    return len(left & right) / len(left | right)


def _zero_rate(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(1 for value in values if value <= 0.0) / len(values)


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    if denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(float(value) for value in values) / len(values)


def _mean_or_none(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return _mean(values)


def _clean_sources(sources: Sequence[str] | None) -> tuple[str, ...]:
    if not sources:
        return DEFAULT_PROFILE_SOURCES
    clean_sources = tuple(dict.fromkeys(text for source in sources if (text := str(source).strip().lower())))
    if not clean_sources:
        raise ValueError("At least one --source value is required")
    unsupported = [source for source in clean_sources if source not in ALLOWED_CANDIDATE_SOURCES]
    if unsupported:
        allowed = ", ".join(ALLOWED_CANDIDATE_SOURCES)
        raise ValueError(f"Unsupported source(s): {', '.join(unsupported)}. Allowed: {allowed}")
    return clean_sources


def _clean_top_k_values(top_k_values: Sequence[int] | None) -> tuple[int, ...]:
    values = top_k_values or DEFAULT_PROFILE_TOP_K
    clean_values = tuple(dict.fromkeys(sorted(_positive_int(value, "top_k") for value in values)))
    if not clean_values:
        raise ValueError("At least one positive --top-k value is required")
    return clean_values


def _positive_unique_ints(values: Sequence[object], field_name: str) -> tuple[int, ...]:
    clean_values = tuple(dict.fromkeys(_positive_int(value, field_name) for value in values))
    if not clean_values:
        raise ValueError(f"At least one --{field_name.replace('_', '-')} value is required")
    return clean_values


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


def _int_value(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer") from error
