from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import random
from typing import TYPE_CHECKING, Any

from .candidates import ALLOWED_CANDIDATE_SOURCES
from .judged import (
    CANDIDATE_PROFILE_JUDGED_PAIRS,
    DEFAULT_UPDATE_JUDGED_PAIRS,
    build_judged_label_gate,
    matching_labels,
    session_feedback_source,
    session_seed_track_ids,
)
from .metrics import bad_suggestion_rate_at_k, ndcg_at_k, precision_at_k
from .reports import RELEVANCE_THRESHOLD

if TYPE_CHECKING:
    from dj_track_similarity.database import LibraryDatabase


DEFAULT_PROFILE_NAME = "hybrid_judged_v1"
DEFAULT_OBJECTIVE = "balanced"
DEFAULT_SPLIT_BY = "seed"
DEFAULT_MIN_JUDGED_PAIRS = CANDIDATE_PROFILE_JUDGED_PAIRS
DEFAULT_RRF_K = 60
DEFAULT_K_VALUES = (10,)
DEFAULT_GRID_STEP = 0.25
DEFAULT_BOOTSTRAP_SAMPLES = 30
DEFAULT_RANDOM_SEED = 123
GUARDRAIL_METRIC_CUTOFF = 10
BOOTSTRAP_PASS_RATE = 0.60
METRIC_TOLERANCE = 1e-12
SOURCE = "judged_feedback"
DEFAULT_RISK_WEIGHTS = {"transition_risk": 0.0}
PROPOSAL_NOTES = (
    "This optimizer uses only matched judged feedback tied to recorded search_result_events.",
    "The output is a proposal/report only; it does not change production defaults, app settings, UI defaults, or database defaults.",
    "RRF, adjusted scores, and raw source scores are ranking diagnostics, not confidence or probability.",
    "Default review is manual-only even when the PR-23 500+ judged-pair gate is reached.",
)
PROMOTED_PROFILE_SOURCE = "score_profile_optimizer"


@dataclass(frozen=True)
class SourceContribution:
    rank: int | None
    score: float | None


@dataclass(frozen=True)
class OptimizerExample:
    session_id: int
    event_id: int
    seed_track_id: int
    candidate_track_id: int
    rating: int
    source: str
    source_contributions: Mapping[str, SourceContribution]
    transition_risk: float


@dataclass(frozen=True)
class OptimizerRequest:
    profile_name: str
    objective: str
    split_by: str
    min_judged_pairs: int
    effective_min_judged_pairs: int
    rrf_k: int
    k_values: tuple[int, ...]
    random_seed: int
    grid_step: float
    bootstrap_samples: int


@dataclass(frozen=True)
class SeedSplit:
    train_examples: tuple[OptimizerExample, ...]
    validation_examples: tuple[OptimizerExample, ...]
    train_seed_ids: tuple[int, ...]
    validation_seed_ids: tuple[int, ...]


def build_score_profile_optimizer_report(
    db: LibraryDatabase,
    *,
    profile_name: str = DEFAULT_PROFILE_NAME,
    objective: str = DEFAULT_OBJECTIVE,
    split_by: str = DEFAULT_SPLIT_BY,
    min_judged_pairs: int = DEFAULT_MIN_JUDGED_PAIRS,
    rrf_k: int = DEFAULT_RRF_K,
    k_values: Sequence[int] = DEFAULT_K_VALUES,
    random_seed: int = DEFAULT_RANDOM_SEED,
    grid_step: float = DEFAULT_GRID_STEP,
    bootstrap_samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
) -> dict[str, Any]:
    request = _optimizer_request(
        profile_name=profile_name,
        objective=objective,
        split_by=split_by,
        min_judged_pairs=min_judged_pairs,
        rrf_k=rrf_k,
        k_values=k_values,
        random_seed=random_seed,
        grid_step=grid_step,
        bootstrap_samples=bootstrap_samples,
    )
    sessions = db.list_search_sessions_with_events()
    feedback_map = db.get_pair_feedback_map()
    judged_gate = build_judged_label_gate(sessions, feedback_map, judged_only=True)
    examples = _matched_optimizer_examples(sessions, feedback_map)
    sources = _sources_seen(examples)

    if int(judged_gate["judged_pairs"]) < request.effective_min_judged_pairs:
        return _rejected_report(
            request,
            judged_gate,
            examples,
            sources,
            decision="insufficient_matched_judged_pairs",
            guidance=(
                f"Need at least {request.effective_min_judged_pairs} matched judged pairs for a candidate profile; "
                f"found {judged_gate['judged_pairs']}."
            ),
        )
    if not judged_gate.get("can_create_candidate_profile"):
        return _rejected_report(
            request,
            judged_gate,
            examples,
            sources,
            decision="pr23_candidate_profile_gate_not_met",
            guidance="The PR-23 judged-label gate has not reached the 200-pair candidate-profile threshold.",
        )
    if not examples:
        return _rejected_report(
            request,
            judged_gate,
            examples,
            sources,
            decision="no_usable_matched_judged_examples",
            guidance="Matched judged labels exist, but none had usable recorded source payloads.",
        )
    if not sources:
        return _rejected_report(
            request,
            judged_gate,
            examples,
            sources,
            decision="no_source_contributions",
            guidance="Matched judged examples did not contain MERT, MAEST, SONARA, or CLAP source contributions.",
        )

    split = _split_examples_by_seed(examples, request.random_seed)
    if split is None:
        return _rejected_report(
            request,
            judged_gate,
            examples,
            sources,
            decision="insufficient_seed_split",
            guidance="At least two judged seed IDs with usable source payloads are required for a no-leakage train/validation split.",
        )

    baseline_weights = _equal_weights(sources)
    baseline_train_metrics = _metrics_for_examples(split.train_examples, baseline_weights, request.rrf_k, request.k_values, DEFAULT_RISK_WEIGHTS)
    baseline_validation_metrics = _metrics_for_examples(split.validation_examples, baseline_weights, request.rrf_k, request.k_values, DEFAULT_RISK_WEIGHTS)
    weights, train_metrics = _optimized_weights(split.train_examples, sources, request)
    validation_metrics = _metrics_for_examples(split.validation_examples, weights, request.rrf_k, request.k_values, DEFAULT_RISK_WEIGHTS)
    bootstrap = _bootstrap_stability(
        split.validation_examples,
        baseline_weights,
        weights,
        request,
    )
    guardrails = _guardrails(
        request,
        baseline_validation_metrics,
        validation_metrics,
        bootstrap,
    )
    rejected_guardrails = [name for name, passed in guardrails["checks"].items() if not passed]
    status = "rejected" if rejected_guardrails else "ok"
    decision = _accepted_decision(judged_gate) if status == "ok" else "guardrail_failure"
    guidance = _decision_guidance(status, judged_gate, rejected_guardrails)

    report = _base_report(request, judged_gate, examples, sources)
    report.update(
        {
            "status": status,
            "decision": decision,
            "guidance": guidance,
            "weights": weights,
            "risk_weights": dict(DEFAULT_RISK_WEIGHTS),
            "train_metrics": train_metrics,
            "validation_metrics": validation_metrics,
            "baseline_train_metrics": baseline_train_metrics,
            "baseline_validation_metrics": baseline_validation_metrics,
            "split": _split_report(split),
            "bootstrap_stability": bootstrap,
            "guardrails": guardrails,
            "candidate_profile_allowed": status == "ok" and bool(judged_gate.get("can_create_candidate_profile")),
            "can_consider_default_review": status == "ok" and int(judged_gate["judged_pairs"]) >= DEFAULT_UPDATE_JUDGED_PAIRS,
            "can_apply_as_default": False,
        },
    )
    return report


def optimizer_record_config(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "objective": report["objective"],
        "split_by": report["split_by"],
        "min_judged_pairs": report["min_judged_pairs"],
        "effective_min_judged_pairs": report["effective_min_judged_pairs"],
        "rrf_k": report["rrf_k"],
        "k_values": list(report["k_values"]),
        "random_seed": report["random_seed"],
        "grid_step": report["grid_step"],
        "bootstrap_samples": report["bootstrap_samples"],
        "sources": list(report["sources"]),
        "source": SOURCE,
        "default_update_policy": report["default_update_policy"],
    }


def optimizer_record_metrics(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": report["status"],
        "decision": report["decision"],
        "label_status": report["label_status"],
        "judged_pairs": report["judged_pairs"],
        "judged_seeds": report["judged_seeds"],
        "matched_judged_examples": report["matched_judged_examples"],
        "usable_seed_count": report["usable_seed_count"],
        "weights": dict(report["weights"]),
        "risk_weights": dict(report["risk_weights"]),
        "train_metrics": dict(report["train_metrics"]),
        "validation_metrics": dict(report["validation_metrics"]),
        "baseline_validation_metrics": dict(report["baseline_validation_metrics"]),
        "guardrails": dict(report["guardrails"]),
        "bootstrap_stability": dict(report["bootstrap_stability"]),
        "can_apply_as_default": bool(report["can_apply_as_default"]),
    }


def build_promoted_score_profile_payload(report: Mapping[str, Any]) -> dict[str, Any]:
    _require_promotable_optimizer_report(report)
    weights = _report_weights(report)
    risk_weights = _report_risk_weights(report)
    guardrails = _required_mapping(report.get("guardrails"), "guardrails")
    payload = {
        "profile_name": _required_text(report.get("profile_name"), "profile_name"),
        "source": SOURCE,
        "promotion_source": PROMOTED_PROFILE_SOURCE,
        "label_status": _required_text(report.get("label_status"), "label_status"),
        "created_at": _required_text(report.get("created_at"), "created_at"),
        "promoted_at": _utc_timestamp(),
        "objective": _objective(str(report.get("objective", DEFAULT_OBJECTIVE))),
        "split_by": _split_by(str(report.get("split_by", DEFAULT_SPLIT_BY))),
        "judged_pairs": _non_negative_int(report.get("judged_pairs"), "judged_pairs"),
        "judged_seeds": _non_negative_int(report.get("judged_seeds"), "judged_seeds"),
        "rrf_k": _positive_int(report.get("rrf_k"), "rrf_k"),
        "k_values": list(_clean_k_values(_required_sequence(report.get("k_values"), "k_values"))),
        "train_metrics": dict(_required_mapping(report.get("train_metrics"), "train_metrics")),
        "validation_metrics": dict(_required_mapping(report.get("validation_metrics"), "validation_metrics")),
        "baseline_validation_metrics": dict(
            _required_mapping(report.get("baseline_validation_metrics"), "baseline_validation_metrics"),
        ),
        "sources": list(weights),
        "weights": weights,
        "risk_weights": risk_weights,
        "can_apply_as_default": True,
        "guardrails": {
            "split_by": "seed_track_id",
            "min_judged_pairs": _positive_int(guardrails.get("min_judged_pairs"), "guardrails.min_judged_pairs"),
            "effective_min_judged_pairs": _positive_int(
                guardrails.get("effective_min_judged_pairs"),
                "guardrails.effective_min_judged_pairs",
            ),
            "bad_rate_did_not_increase": True,
            "validation_ndcg_improved": True,
            "bootstrap_stability_passed": True,
        },
        "decision": _required_text(report.get("decision"), "decision"),
        "default_update_policy": _required_text(report.get("default_update_policy"), "default_update_policy"),
    }
    _validate_promoted_score_profile_payload(payload)
    return payload


def _require_promotable_optimizer_report(report: Mapping[str, Any]) -> None:
    if not isinstance(report, Mapping):
        raise ValueError("Optimizer report must be a JSON object")
    if report.get("source") != SOURCE:
        raise ValueError("Only judged-feedback optimizer reports can be promoted")
    if report.get("status") != "ok":
        raise ValueError("Only optimizer reports with status=ok can be promoted")
    if not bool(report.get("can_update_defaults")):
        raise ValueError(
            "Cannot promote score profile until the PR-23 500 matched judged-pair default-review gate is met",
        )
    guardrails = _required_mapping(report.get("guardrails"), "guardrails")
    checks = _required_mapping(guardrails.get("checks"), "guardrails.checks")
    failed_checks = sorted(name for name, passed in checks.items() if not bool(passed))
    if failed_checks:
        raise ValueError("Cannot promote score profile because guardrails failed: " + ", ".join(failed_checks))


def _report_weights(report: Mapping[str, Any]) -> dict[str, float]:
    raw_weights = _required_mapping(report.get("weights"), "weights")
    sources = _source_list(report.get("sources"))
    weights = {
        str(source).strip().lower(): _non_negative_finite_float(weight, f"weights.{source}")
        for source, weight in raw_weights.items()
    }
    if set(weights) != set(sources):
        raise ValueError("Promoted score profile weights must match optimizer sources exactly")
    _assert_normalized_weights(weights)
    return weights


def _report_risk_weights(report: Mapping[str, Any]) -> dict[str, float]:
    raw_risk_weights = _required_mapping(report.get("risk_weights"), "risk_weights")
    risk_weights = {
        _required_text(name, "risk weight name"): _non_negative_finite_float(weight, f"risk_weights.{name}")
        for name, weight in raw_risk_weights.items()
    }
    if not risk_weights:
        raise ValueError("Promoted score profile requires at least one risk weight")
    return risk_weights


def _validate_promoted_score_profile_payload(payload: Mapping[str, Any]) -> None:
    _report_weights(payload)
    _report_risk_weights(payload)
    if payload.get("source") != SOURCE:
        raise ValueError("Promoted score profile source must be judged_feedback")
    if payload.get("promotion_source") != PROMOTED_PROFILE_SOURCE:
        raise ValueError("Promoted score profile promotion_source must be score_profile_optimizer")
    if not bool(payload.get("can_apply_as_default")):
        raise ValueError("Promoted score profile must be marked can_apply_as_default")
    guardrails = _required_mapping(payload.get("guardrails"), "guardrails")
    required_true_guardrails = ("bad_rate_did_not_increase", "validation_ndcg_improved", "bootstrap_stability_passed")
    failed_guardrails = [name for name in required_true_guardrails if guardrails.get(name) is not True]
    if failed_guardrails:
        raise ValueError("Promoted score profile guardrails must all pass: " + ", ".join(failed_guardrails))
    validation_metrics = _required_mapping(payload.get("validation_metrics"), "validation_metrics")
    baseline_metrics = _required_mapping(payload.get("baseline_validation_metrics"), "baseline_validation_metrics")
    metric_cutoff = GUARDRAIL_METRIC_CUTOFF
    _non_negative_finite_float(validation_metrics.get(f"ndcg_at_{metric_cutoff}"), f"validation_metrics.ndcg_at_{metric_cutoff}")
    _non_negative_finite_float(baseline_metrics.get(f"ndcg_at_{metric_cutoff}"), f"baseline_validation_metrics.ndcg_at_{metric_cutoff}")


def _required_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a JSON object")
    return value


def _required_sequence(value: object, field_name: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a JSON array")
    return value


def _source_list(value: object) -> tuple[str, ...]:
    raw_sources = _required_sequence(value, "sources")
    sources = tuple(dict.fromkeys(str(source).strip().lower() for source in raw_sources if str(source).strip()))
    if not sources:
        raise ValueError("sources must contain at least one source")
    unknown_sources = sorted(source for source in sources if source not in ALLOWED_CANDIDATE_SOURCES)
    if unknown_sources:
        raise ValueError("Unknown optimizer sources: " + ", ".join(unknown_sources))
    return sources


def _optimizer_request(
    *,
    profile_name: str,
    objective: str,
    split_by: str,
    min_judged_pairs: int,
    rrf_k: int,
    k_values: Sequence[int],
    random_seed: int,
    grid_step: float,
    bootstrap_samples: int,
) -> OptimizerRequest:
    clean_min_judged_pairs = _positive_int(min_judged_pairs, "min_judged_pairs")
    clean_k_values = _clean_k_values(k_values)
    return OptimizerRequest(
        profile_name=_required_text(profile_name, "profile_name"),
        objective=_objective(objective),
        split_by=_split_by(split_by),
        min_judged_pairs=clean_min_judged_pairs,
        effective_min_judged_pairs=max(clean_min_judged_pairs, CANDIDATE_PROFILE_JUDGED_PAIRS),
        rrf_k=_positive_int(rrf_k, "rrf_k"),
        k_values=clean_k_values,
        random_seed=_int_value(random_seed, "random_seed"),
        grid_step=_grid_step(grid_step),
        bootstrap_samples=_non_negative_int(bootstrap_samples, "bootstrap_samples"),
    )


def _matched_optimizer_examples(
    sessions: Sequence[Mapping[str, Any]],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> tuple[OptimizerExample, ...]:
    examples_by_key: dict[tuple[int, int, str], OptimizerExample] = {}
    for session in sessions:
        seed_track_ids = session_seed_track_ids(session)
        if not seed_track_ids:
            continue
        feedback_source = session_feedback_source(session, default=None)
        for event in session.get("events", ()):
            if not isinstance(event, Mapping):
                continue
            source_contributions = _source_contributions(event.get("score_breakdown"))
            if not source_contributions:
                continue
            candidate_track_id = _positive_int(event.get("track_id"), "candidate_track_id")
            labels = matching_labels(seed_track_ids, candidate_track_id, feedback_source, feedback_map)
            for label in labels:
                key = (int(label["seed_track_id"]), int(label["candidate_track_id"]), str(label["source"]))
                examples_by_key.setdefault(
                    key,
                    OptimizerExample(
                        session_id=_positive_int(session.get("id"), "session_id"),
                        event_id=_positive_int(event.get("id"), "event_id"),
                        seed_track_id=int(label["seed_track_id"]),
                        candidate_track_id=int(label["candidate_track_id"]),
                        rating=_rating(label.get("rating")),
                        source=str(label["source"]),
                        source_contributions=source_contributions,
                        transition_risk=_transition_risk(event.get("score_breakdown")),
                    ),
                )
    return tuple(examples_by_key[key] for key in sorted(examples_by_key))


def _split_examples_by_seed(examples: Sequence[OptimizerExample], random_seed: int) -> SeedSplit | None:
    examples_by_seed = _examples_by_seed(examples)
    seed_ids = sorted(examples_by_seed)
    if len(seed_ids) < 2:
        return None

    shuffled_seed_ids = list(seed_ids)
    random.Random(random_seed).shuffle(shuffled_seed_ids)
    validation_count = max(1, round(len(shuffled_seed_ids) * 0.2))
    validation_count = min(validation_count, len(shuffled_seed_ids) - 1)
    validation_seed_ids = tuple(sorted(shuffled_seed_ids[:validation_count]))
    train_seed_ids = tuple(sorted(seed_id for seed_id in shuffled_seed_ids[validation_count:]))
    if not train_seed_ids or not validation_seed_ids:
        return None

    return SeedSplit(
        train_examples=_examples_for_seeds(examples_by_seed, train_seed_ids),
        validation_examples=_examples_for_seeds(examples_by_seed, validation_seed_ids),
        train_seed_ids=train_seed_ids,
        validation_seed_ids=validation_seed_ids,
    )


def _optimized_weights(
    train_examples: Sequence[OptimizerExample],
    sources: Sequence[str],
    request: OptimizerRequest,
) -> tuple[dict[str, float], dict[str, float]]:
    best_weights: dict[str, float] | None = None
    best_metrics: dict[str, float] | None = None
    best_score: float | None = None
    for weights in _weight_grid(sources, request.grid_step):
        metrics = _metrics_for_examples(train_examples, weights, request.rrf_k, request.k_values, DEFAULT_RISK_WEIGHTS)
        objective_score = _objective_score(metrics, GUARDRAIL_METRIC_CUTOFF)
        if _is_better_candidate(objective_score, metrics, weights, best_score, best_metrics, best_weights):
            best_weights = weights
            best_metrics = metrics
            best_score = objective_score

    if best_weights is None or best_metrics is None:
        raise ValueError("At least one finite source-weight candidate is required")
    return best_weights, best_metrics


def _metrics_for_examples(
    examples: Sequence[OptimizerExample],
    weights: Mapping[str, float],
    rrf_k: int,
    k_values: Sequence[int],
    risk_weights: Mapping[str, float],
) -> dict[str, float]:
    seed_groups = tuple(_examples_by_seed(examples).values())
    return _metrics_for_seed_groups(seed_groups, weights, rrf_k, k_values, risk_weights)


def _metrics_for_seed_groups(
    seed_groups: Sequence[Sequence[OptimizerExample]],
    weights: Mapping[str, float],
    rrf_k: int,
    k_values: Sequence[int],
    risk_weights: Mapping[str, float],
) -> dict[str, float]:
    relevance_lists = [_ranked_relevances(seed_group, weights, rrf_k, risk_weights) for seed_group in seed_groups]
    relevance_lists = [relevances for relevances in relevance_lists if relevances]
    metrics = {
        "seed_count": float(len(relevance_lists)),
        "example_count": float(sum(len(relevances) for relevances in relevance_lists)),
    }
    for k in k_values:
        metrics[f"ndcg_at_{k}"] = _mean(ndcg_at_k(relevances, k) for relevances in relevance_lists)
        metrics[f"precision_at_{k}"] = _mean(precision_at_k(relevances, k, threshold=RELEVANCE_THRESHOLD) for relevances in relevance_lists)
        metrics[f"bad_suggestion_rate_at_{k}"] = _mean(bad_suggestion_rate_at_k(relevances, k) for relevances in relevance_lists)
    return metrics


def _ranked_relevances(
    examples: Sequence[OptimizerExample],
    weights: Mapping[str, float],
    rrf_k: int,
    risk_weights: Mapping[str, float],
) -> list[int]:
    source_ranks = _source_ranks(examples)
    scored_examples = [
        (_example_score(example, source_ranks, weights, rrf_k, risk_weights), example)
        for example in examples
    ]
    return [
        example.rating
        for score, example in sorted(
            scored_examples,
            key=lambda item: (-item[0], item[1].candidate_track_id, item[1].event_id, item[1].source),
        )
        if math.isfinite(score)
    ]


def _example_score(
    example: OptimizerExample,
    source_ranks: Mapping[str, Mapping[int, int]],
    weights: Mapping[str, float],
    rrf_k: int,
    risk_weights: Mapping[str, float],
) -> float:
    weighted_score = 0.0
    present_weight = 0.0
    for source, weight in weights.items():
        rank = source_ranks.get(source, {}).get(example.candidate_track_id)
        if rank is None or weight <= 0.0:
            continue
        weighted_score += weight * (1.0 / (rrf_k + rank))
        present_weight += weight
    normalized_score = weighted_score / present_weight if present_weight > 0.0 else 0.0
    transition_risk_weight = _non_negative_finite_float(risk_weights.get("transition_risk", 0.0), "risk_weights.transition_risk")
    return normalized_score - transition_risk_weight * example.transition_risk


def _source_ranks(examples: Sequence[OptimizerExample]) -> dict[str, dict[int, int]]:
    sources = sorted({source for example in examples for source in example.source_contributions})
    return {source: ranks for source in sources if (ranks := _ranks_for_source(examples, source))}


def _ranks_for_source(examples: Sequence[OptimizerExample], source: str) -> dict[int, int]:
    explicit_ranks: dict[int, int] = {}
    score_only_candidates: list[tuple[float, int]] = []
    for example in examples:
        contribution = example.source_contributions.get(source)
        if contribution is None:
            continue
        if contribution.rank is not None:
            existing_rank = explicit_ranks.get(example.candidate_track_id)
            explicit_ranks[example.candidate_track_id] = contribution.rank if existing_rank is None else min(existing_rank, contribution.rank)
            continue
        if contribution.score is not None:
            score_only_candidates.append((contribution.score, example.candidate_track_id))
    inferred_start_rank = max(explicit_ranks.values(), default=0) + 1
    inferred_ranks = {
        candidate_track_id: inferred_start_rank + offset
        for offset, (_score, candidate_track_id) in enumerate(sorted(score_only_candidates, key=lambda item: (-item[0], item[1])))
        if candidate_track_id not in explicit_ranks
    }
    return {**explicit_ranks, **inferred_ranks}


def _bootstrap_stability(
    validation_examples: Sequence[OptimizerExample],
    baseline_weights: Mapping[str, float],
    proposal_weights: Mapping[str, float],
    request: OptimizerRequest,
) -> dict[str, Any]:
    if request.bootstrap_samples <= 0:
        return {"enabled": False, "samples": 0, "improvement_rate": None, "passed": True, "required_rate": BOOTSTRAP_PASS_RATE}

    validation_groups_by_seed = _examples_by_seed(validation_examples)
    validation_groups = tuple(validation_groups_by_seed[seed_id] for seed_id in sorted(validation_groups_by_seed))
    if not validation_groups:
        return {"enabled": True, "samples": request.bootstrap_samples, "improvement_rate": 0.0, "passed": False, "required_rate": BOOTSTRAP_PASS_RATE}

    rng = random.Random(request.random_seed + 7919)
    improved_samples = 0
    for _index in range(request.bootstrap_samples):
        sampled_groups = tuple(rng.choice(validation_groups) for _seed_index in validation_groups)
        baseline_metrics = _metrics_for_seed_groups(sampled_groups, baseline_weights, request.rrf_k, request.k_values, DEFAULT_RISK_WEIGHTS)
        proposal_metrics = _metrics_for_seed_groups(sampled_groups, proposal_weights, request.rrf_k, request.k_values, DEFAULT_RISK_WEIGHTS)
        if _validation_improved_without_bad_rate_increase(baseline_metrics, proposal_metrics, GUARDRAIL_METRIC_CUTOFF):
            improved_samples += 1
    improvement_rate = improved_samples / request.bootstrap_samples
    return {
        "enabled": True,
        "samples": request.bootstrap_samples,
        "improved_samples": improved_samples,
        "improvement_rate": improvement_rate,
        "passed": improvement_rate >= BOOTSTRAP_PASS_RATE,
        "required_rate": BOOTSTRAP_PASS_RATE,
    }


def _guardrails(
    request: OptimizerRequest,
    baseline_validation_metrics: Mapping[str, float],
    validation_metrics: Mapping[str, float],
    bootstrap: Mapping[str, Any],
) -> dict[str, Any]:
    ndcg_key = f"ndcg_at_{GUARDRAIL_METRIC_CUTOFF}"
    bad_rate_key = f"bad_suggestion_rate_at_{GUARDRAIL_METRIC_CUTOFF}"
    validation_ndcg_improved = validation_metrics[ndcg_key] > baseline_validation_metrics[ndcg_key] + METRIC_TOLERANCE
    bad_rate_did_not_increase = validation_metrics[bad_rate_key] <= baseline_validation_metrics[bad_rate_key] + METRIC_TOLERANCE
    checks = {
        "finite_non_negative_normalized_source_weights": True,
        "finite_non_negative_risk_weights": True,
        "split_by_seed_no_leakage": True,
        "validation_ndcg_improved": validation_ndcg_improved,
        "bad_rate_did_not_increase": bad_rate_did_not_increase,
        "bootstrap_stability_passed": bool(bootstrap["passed"]),
    }
    return {
        "split_by": "seed_track_id",
        "min_judged_pairs": request.min_judged_pairs,
        "effective_min_judged_pairs": request.effective_min_judged_pairs,
        "metric_cutoff": GUARDRAIL_METRIC_CUTOFF,
        "bad_rate_did_not_increase": bad_rate_did_not_increase,
        "validation_ndcg_improved": validation_ndcg_improved,
        "bootstrap_stability_passed": bool(bootstrap["passed"]),
        "checks": checks,
        "rejected_checks": [name for name, passed in checks.items() if not passed],
    }


def _rejected_report(
    request: OptimizerRequest,
    judged_gate: Mapping[str, Any],
    examples: Sequence[OptimizerExample],
    sources: Sequence[str],
    *,
    decision: str,
    guidance: str,
) -> dict[str, Any]:
    report = _base_report(request, judged_gate, examples, sources)
    report.update(
        {
            "status": "rejected",
            "decision": decision,
            "guidance": guidance,
            "weights": {},
            "risk_weights": dict(DEFAULT_RISK_WEIGHTS),
            "train_metrics": {},
            "validation_metrics": {},
            "baseline_train_metrics": {},
            "baseline_validation_metrics": {},
            "split": None,
            "bootstrap_stability": {"enabled": request.bootstrap_samples > 0, "samples": request.bootstrap_samples, "passed": False},
            "guardrails": {
                "split_by": "seed_track_id",
                "min_judged_pairs": request.min_judged_pairs,
                "effective_min_judged_pairs": request.effective_min_judged_pairs,
                "metric_cutoff": GUARDRAIL_METRIC_CUTOFF,
                "bad_rate_did_not_increase": False,
                "validation_ndcg_improved": False,
                "bootstrap_stability_passed": False,
                "checks": {},
                "rejected_checks": [decision],
            },
            "candidate_profile_allowed": False,
            "can_consider_default_review": False,
            "can_apply_as_default": False,
        },
    )
    return report


def _base_report(
    request: OptimizerRequest,
    judged_gate: Mapping[str, Any],
    examples: Sequence[OptimizerExample],
    sources: Sequence[str],
) -> dict[str, Any]:
    usable_seed_ids = sorted({example.seed_track_id for example in examples})
    return {
        "profile_name": request.profile_name,
        "source": SOURCE,
        "created_at": _utc_timestamp(),
        "objective": request.objective,
        "split_by": request.split_by,
        "label_status": judged_gate["label_status"],
        "evaluation_mode": judged_gate["evaluation_mode"],
        "judged_pairs": judged_gate["judged_pairs"],
        "judged_seeds": judged_gate["judged_seeds"],
        "matched_result_events": judged_gate["matched_result_events"],
        "matched_label_rows": judged_gate["matched_label_rows"],
        "matched_judged_examples": len(examples),
        "usable_seed_count": len(usable_seed_ids),
        "sources": list(sources),
        "rrf_k": request.rrf_k,
        "k_values": list(request.k_values),
        "min_judged_pairs": request.min_judged_pairs,
        "effective_min_judged_pairs": request.effective_min_judged_pairs,
        "random_seed": request.random_seed,
        "grid_step": request.grid_step,
        "bootstrap_samples": request.bootstrap_samples,
        "judged_label_gate": dict(judged_gate),
        "can_create_candidate_profile": judged_gate["can_create_candidate_profile"],
        "can_update_defaults": judged_gate["can_update_defaults"],
        "default_update_policy": "manual_review_only_never_automatic",
        "notes": list(PROPOSAL_NOTES),
        "limitations": list(PROPOSAL_NOTES),
    }


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
        if contribution is not None:
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
        rank = _optional_positive_int(payload.get("rank"))
        score = _optional_finite_float(payload.get("score"))
        if rank is None and score is None:
            return None
        return SourceContribution(rank=rank, score=score)
    score = _optional_finite_float(payload)
    if score is None:
        return None
    return SourceContribution(rank=None, score=score)


def _transition_risk(score_breakdown: object) -> float:
    if not isinstance(score_breakdown, Mapping):
        return 0.0
    value = _optional_finite_float(score_breakdown.get("transition_risk"))
    if value is None or value < 0.0:
        return 0.0
    return value


def _sources_seen(examples: Sequence[OptimizerExample]) -> tuple[str, ...]:
    return tuple(source for source in ALLOWED_CANDIDATE_SOURCES if any(source in example.source_contributions for example in examples))


def _examples_by_seed(examples: Sequence[OptimizerExample]) -> dict[int, tuple[OptimizerExample, ...]]:
    grouped: dict[int, list[OptimizerExample]] = {}
    for example in examples:
        grouped.setdefault(example.seed_track_id, []).append(example)
    return {
        seed_id: tuple(sorted(seed_examples, key=lambda example: (example.candidate_track_id, example.event_id, example.source)))
        for seed_id, seed_examples in sorted(grouped.items())
    }


def _examples_for_seeds(
    examples_by_seed: Mapping[int, Sequence[OptimizerExample]],
    seed_ids: Sequence[int],
) -> tuple[OptimizerExample, ...]:
    return tuple(example for seed_id in seed_ids for example in examples_by_seed.get(seed_id, ()))


def _equal_weights(sources: Sequence[str]) -> dict[str, float]:
    if not sources:
        return {}
    weight = 1.0 / len(sources)
    return {source: weight for source in sources}


def _weight_grid(sources: Sequence[str], grid_step: float) -> Iterable[dict[str, float]]:
    clean_sources = tuple(sources)
    if len(clean_sources) == 1:
        yield {clean_sources[0]: 1.0}
        return

    units = max(1, round(1.0 / grid_step))
    for unit_weights in _unit_weight_grid(len(clean_sources), units):
        weights = {source: unit_weight / units for source, unit_weight in zip(clean_sources, unit_weights)}
        _assert_normalized_weights(weights)
        yield weights


def _unit_weight_grid(count: int, units: int) -> Iterable[tuple[int, ...]]:
    if count == 1:
        yield (units,)
        return
    for value in range(units + 1):
        for rest in _unit_weight_grid(count - 1, units - value):
            yield (value, *rest)


def _assert_normalized_weights(weights: Mapping[str, float]) -> None:
    if not weights:
        raise ValueError("At least one source weight is required")
    if not any(weight > 0.0 for weight in weights.values()):
        raise ValueError("At least one source weight must be positive")
    for source, weight in weights.items():
        _non_negative_finite_float(weight, f"weights.{source}")
    if not math.isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("Source weights must sum to 1.0")


def _is_better_candidate(
    objective_score: float,
    metrics: Mapping[str, float],
    weights: Mapping[str, float],
    best_score: float | None,
    best_metrics: Mapping[str, float] | None,
    best_weights: Mapping[str, float] | None,
) -> bool:
    if best_score is None or best_metrics is None or best_weights is None:
        return True
    if objective_score > best_score + METRIC_TOLERANCE:
        return True
    if objective_score < best_score - METRIC_TOLERANCE:
        return False
    return _candidate_tie_break(metrics, weights) > _candidate_tie_break(best_metrics, best_weights)


def _candidate_tie_break(metrics: Mapping[str, float], weights: Mapping[str, float]) -> tuple[float, float, tuple[float, ...]]:
    return (
        metrics[f"ndcg_at_{GUARDRAIL_METRIC_CUTOFF}"],
        -metrics[f"bad_suggestion_rate_at_{GUARDRAIL_METRIC_CUTOFF}"],
        tuple(weights[source] for source in sorted(weights)),
    )


def _objective_score(metrics: Mapping[str, float], k: int) -> float:
    return metrics[f"ndcg_at_{k}"] + 0.25 * metrics[f"precision_at_{k}"] - 0.25 * metrics[f"bad_suggestion_rate_at_{k}"]


def _validation_improved_without_bad_rate_increase(
    baseline_metrics: Mapping[str, float],
    proposal_metrics: Mapping[str, float],
    k: int,
) -> bool:
    return (
        proposal_metrics[f"ndcg_at_{k}"] > baseline_metrics[f"ndcg_at_{k}"] + METRIC_TOLERANCE
        and proposal_metrics[f"bad_suggestion_rate_at_{k}"] <= baseline_metrics[f"bad_suggestion_rate_at_{k}"] + METRIC_TOLERANCE
    )


def _accepted_decision(judged_gate: Mapping[str, Any]) -> str:
    if int(judged_gate["judged_pairs"]) >= DEFAULT_UPDATE_JUDGED_PAIRS:
        return "default_review_candidate_manual_only"
    return "candidate_profile_proposal"


def _decision_guidance(status: str, judged_gate: Mapping[str, Any], rejected_guardrails: Sequence[str]) -> str:
    if status == "ok" and int(judged_gate["judged_pairs"]) >= DEFAULT_UPDATE_JUDGED_PAIRS:
        return "Guardrails passed with 500+ matched judged pairs. Treat this as a manual default-review candidate only; no default is applied automatically."
    if status == "ok":
        return "Guardrails passed for a candidate judged score profile. Review the JSON before using it in diagnostic candidate-pool workflows."
    return "Rejected by guardrails: " + ", ".join(rejected_guardrails)


def _split_report(split: SeedSplit) -> dict[str, Any]:
    return {
        "split_by": "seed_track_id",
        "train_seed_count": len(split.train_seed_ids),
        "validation_seed_count": len(split.validation_seed_ids),
        "train_seeds": list(split.train_seed_ids),
        "validation_seeds": list(split.validation_seed_ids),
        "train_examples": len(split.train_examples),
        "validation_examples": len(split.validation_examples),
        "seed_leakage": sorted(set(split.train_seed_ids) & set(split.validation_seed_ids)),
    }


def _clean_k_values(k_values: Sequence[int]) -> tuple[int, ...]:
    clean_values = tuple(dict.fromkeys(sorted(_positive_int(k, "k") for k in k_values)))
    if not clean_values:
        return (GUARDRAIL_METRIC_CUTOFF,)
    if GUARDRAIL_METRIC_CUTOFF in clean_values:
        return clean_values
    return tuple(sorted((*clean_values, GUARDRAIL_METRIC_CUTOFF)))


def _objective(value: str) -> str:
    text = str(value).strip().lower()
    if text == DEFAULT_OBJECTIVE:
        return text
    raise ValueError("objective must be balanced")


def _split_by(value: str) -> str:
    text = str(value).strip().lower().replace("-", "_")
    if text in {"seed", "seed_track_id"}:
        return "seed"
    raise ValueError("split_by must be seed")


def _grid_step(value: float) -> float:
    number = _non_negative_finite_float(value, "grid_step")
    if number <= 0.0 or number > 1.0:
        raise ValueError("grid_step must be greater than 0 and no more than 1")
    return number


def _required_text(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} must not be empty")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if clean_value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return clean_value


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a non-negative integer") from error
    if clean_value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return clean_value


def _int_value(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer") from error


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


def _non_negative_finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a finite non-negative number") from error
    if not math.isfinite(number) or number < 0.0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return number


def _rating(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("rating must be an integer between 0 and 3")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("rating must be an integer between 0 and 3") from error
    if clean_value < 0 or clean_value > 3:
        raise ValueError("rating must be an integer between 0 and 3")
    return clean_value


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(float(value) for value in items) / len(items)


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
