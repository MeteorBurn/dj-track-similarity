from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
import math
from typing import Any

from .database import LibraryDatabase
from .evaluation.candidates import (
    ALLOWED_CANDIDATE_SOURCES,
    CandidateExportRequest,
    CandidatePoolRow,
    CandidateSourceContribution,
    generate_candidate_pool_rows,
)
from .evaluation.score_profiles import ScoreProfile, score_profile_from_dict
from .evaluation.weighted_candidates import weighted_rrf_components, weighted_rrf_score
from .hybrid_explanation import build_hybrid_explanation
from .models import Track
from .transition_diagnostics import COMPONENT_NAMES, TransitionDiagnostics, compute_transition_diagnostics


DEFAULT_HYBRID_SOURCES = ("mert", "maest", "sonara", "clap")
HYBRID_UI_FEEDBACK_SOURCE = "hybrid_ui"
HYBRID_SEARCH_SESSION_MODE = "hybrid_search_preview"
HYBRID_SEARCH_LIMITATIONS = (
    "Hybrid search is an explicit weighted rank-fusion preview over existing MERT, MAEST, SONARA, and CLAP analysis data.",
    "CLAP is used only as stored audio embeddings in this preview; prompt-aware CLAP hybrid search is not part of this path.",
    "The score is an optional transition-risk-adjusted weighted RRF preview score; it is diagnostic ranking output, not calibrated human-taste evidence.",
    "Transition risk is diagnostic only and is not AutoMix, beatgrid, cue-point detection, or a calibrated transition estimate.",
    "The endpoint reads the selected SQLite database only and does not write sessions, train classifiers, modify production search scoring, or write audio files.",
)


@dataclass(frozen=True)
class HybridSearchResultRow:
    track: Track
    score: float
    total_score: float
    calibrated_score: None
    adjusted_score: float
    transition_risk: float | None
    transition_risk_penalty: float
    transition_risk_weight: float
    raw_rrf_score: float
    rank: int
    score_breakdown: Mapping[str, Mapping[str, float | int]]
    risk_breakdown: Mapping[str, float | None]
    source_support: Mapping[str, Mapping[str, Any]]
    match_character: Mapping[str, float]
    warnings: tuple[str, ...]
    explanation: tuple[str, ...]
    transition_diagnostics: Mapping[str, Any]
    diagnostics: Mapping[str, Any]
    feedback: Mapping[str, Any] | None

    def api_row(self, *, include_diagnostics: bool) -> dict[str, Any]:
        return {
            "track": asdict(self.track),
            "score": self.score,
            "total_score": self.total_score,
            "calibrated_score": self.calibrated_score,
            "adjusted_score": self.adjusted_score,
            "transition_risk": self.transition_risk,
            "transition_risk_penalty": self.transition_risk_penalty,
            "transition_risk_weight": self.transition_risk_weight,
            "raw_rrf_score": self.raw_rrf_score,
            "rank": self.rank,
            "score_breakdown": dict(self.score_breakdown),
            "risk_breakdown": dict(self.risk_breakdown),
            "source_support": {source: dict(support) for source, support in self.source_support.items()},
            "match_character": dict(self.match_character),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation),
            "transition_diagnostics": dict(self.transition_diagnostics) if include_diagnostics else {},
            "diagnostics": dict(self.diagnostics) if include_diagnostics else {},
            "feedback": dict(self.feedback) if self.feedback is not None else None,
        }


@dataclass(frozen=True)
class HybridSearchResult:
    results: tuple[HybridSearchResultRow, ...]
    warnings: tuple[str, ...]
    weights_used: Mapping[str, float]
    sources: tuple[str, ...]
    limitations: tuple[str, ...]
    diagnostics: Mapping[str, Any]
    session_id: int | None

    def api_response(self, *, include_diagnostics: bool) -> dict[str, Any]:
        return {
            "results": [row.api_row(include_diagnostics=include_diagnostics) for row in self.results],
            "warnings": list(self.warnings),
            "weights_used": dict(self.weights_used),
            "sources": list(self.sources),
            "limitations": list(self.limitations),
            "diagnostics": dict(self.diagnostics) if include_diagnostics else {},
            "session_id": self.session_id,
        }


@dataclass(frozen=True)
class _HybridCandidate:
    track: Track
    source_contributions: Mapping[str, CandidateSourceContribution]
    source_seed_diagnostics: Mapping[str, Mapping[str, Any]]
    seed_track_ids: tuple[int, ...]


@dataclass(frozen=True)
class _ScoredHybridCandidate:
    candidate: _HybridCandidate
    raw_rrf_score: float
    score_breakdown: Mapping[str, Mapping[str, float | int]]
    tie_token: int


@dataclass(frozen=True)
class _RankedHybridCandidate:
    scored_candidate: _ScoredHybridCandidate
    normalized_rrf_score: float
    adjusted_score: float
    transition_risk: float | None
    transition_risk_penalty: float
    transition_diagnostics: Mapping[str, Any]


def build_hybrid_search_preview(
    db: LibraryDatabase,
    *,
    seed_track_ids: Sequence[int],
    sources: Sequence[str] | None = None,
    weights: Mapping[str, float] | None = None,
    score_profile: Mapping[str, Any] | None = None,
    per_source: int = 30,
    limit: int = 25,
    rrf_k: int = 60,
    random_seed: int = 123,
    transition_risk_weight: float = 0.0,
    record_session: bool = False,
) -> HybridSearchResult:
    clean_seed_track_ids = _positive_unique_ints(seed_track_ids, "seed_track_id")
    clean_seed_tracks = _load_seed_tracks(db, clean_seed_track_ids)
    clean_sources = _clean_sources(sources)
    clean_weights = _resolve_weights(clean_sources, weights=weights, score_profile=score_profile)
    clean_per_source = _positive_int(per_source, "per_source")
    clean_limit = _positive_int(limit, "limit")
    clean_rrf_k = _positive_int(rrf_k, "rrf_k")
    clean_random_seed = _int_value(random_seed, "random_seed")
    clean_transition_risk_weight = _risk_weight(transition_risk_weight, "transition_risk_weight")
    clean_record_session = bool(record_session)

    candidate_rows, warnings = generate_candidate_pool_rows(
        db,
        CandidateExportRequest(
            seed_track_ids=clean_seed_track_ids,
            sources=clean_sources,
            per_source=clean_per_source,
            random_seed=clean_random_seed,
            record_session=False,
        ),
    )
    candidates = _hybrid_candidates(candidate_rows, seed_track_ids=clean_seed_track_ids)
    scored_candidates = _scored_hybrid_candidates(
        candidates,
        weights=clean_weights,
        rrf_k=clean_rrf_k,
        random_seed=clean_random_seed,
    )
    results = _ranked_result_rows(
        db,
        scored_candidates,
        limit=clean_limit,
        sources=clean_sources,
        seed_tracks=clean_seed_tracks,
        seed_track_ids=clean_seed_track_ids,
        feedback_map=db.get_pair_feedback_map(),
        feedback_source=HYBRID_UI_FEEDBACK_SOURCE,
        transition_risk_weight=clean_transition_risk_weight,
    )
    session_id = _record_hybrid_search_session(
        db,
        results,
        seed_track_ids=clean_seed_track_ids,
        sources=clean_sources,
        weights=clean_weights,
        per_source=clean_per_source,
        limit=clean_limit,
        rrf_k=clean_rrf_k,
        random_seed=clean_random_seed,
        transition_risk_weight=clean_transition_risk_weight,
        feedback_source=HYBRID_UI_FEEDBACK_SOURCE,
        record_session=clean_record_session,
    )
    return HybridSearchResult(
        results=results,
        warnings=warnings,
        weights_used=clean_weights,
        sources=clean_sources,
        limitations=HYBRID_SEARCH_LIMITATIONS,
        session_id=session_id,
        diagnostics={
            "method": "weighted_rrf",
            "seed_track_ids": list(clean_seed_track_ids),
            "per_source": clean_per_source,
            "rrf_k": clean_rrf_k,
            "random_seed": clean_random_seed,
            "transition_risk_weight": clean_transition_risk_weight,
            "record_session": clean_record_session,
            "session_id": session_id,
            "candidate_rows": len(candidate_rows),
            "unique_candidates": len(candidates),
            "results_returned": len(results),
        },
    )


def _hybrid_candidates(rows: Sequence[CandidatePoolRow], *, seed_track_ids: Sequence[int]) -> tuple[_HybridCandidate, ...]:
    seed_id_set = set(seed_track_ids)
    candidates: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row.candidate_track_id in seed_id_set:
            continue
        candidate = candidates.setdefault(
            row.candidate_track_id,
            {
                "track": row.candidate_track,
                "source_contributions": {},
                "source_seed_diagnostics": {},
                "seed_track_ids": set(),
            },
        )
        candidate["seed_track_ids"].add(row.seed_track_id)
        _merge_candidate_source_contributions(candidate, row)

    return tuple(
        _HybridCandidate(
            track=payload["track"],
            source_contributions=dict(sorted(payload["source_contributions"].items())),
            source_seed_diagnostics=dict(sorted(payload["source_seed_diagnostics"].items())),
            seed_track_ids=tuple(sorted(payload["seed_track_ids"])),
        )
        for _candidate_id, payload in sorted(candidates.items())
    )


def _merge_candidate_source_contributions(candidate: dict[str, Any], row: CandidatePoolRow) -> None:
    contributions: dict[str, CandidateSourceContribution] = candidate["source_contributions"]
    diagnostics: dict[str, dict[str, Any]] = candidate["source_seed_diagnostics"]
    for source, contribution in row.source_contributions.items():
        current = contributions.get(source)
        if current is None or contribution.rank < current.rank or (contribution.rank == current.rank and contribution.score > current.score):
            supporting_seed_track_ids = _source_supporting_seed_track_ids(diagnostics.get(source), row.seed_track_id)
            contributions[source] = contribution
            diagnostics[source] = {
                "best_seed_track_id": row.seed_track_id,
                "best_rank": contribution.rank,
                "best_source_score": contribution.score,
                "supporting_seed_track_ids": supporting_seed_track_ids,
            }
            continue
        source_diagnostics = diagnostics.setdefault(
            source,
            {
                "best_seed_track_id": row.seed_track_id,
                "best_rank": current.rank,
                "best_source_score": current.score,
                "supporting_seed_track_ids": [],
            },
        )
        source_diagnostics["supporting_seed_track_ids"] = sorted(
            set(source_diagnostics["supporting_seed_track_ids"]) | {row.seed_track_id},
        )


def _source_supporting_seed_track_ids(source_diagnostics: Mapping[str, Any] | None, seed_track_id: int) -> list[int]:
    if source_diagnostics is None:
        return [seed_track_id]
    return sorted(set(source_diagnostics["supporting_seed_track_ids"]) | {seed_track_id})


def _scored_hybrid_candidates(
    candidates: Sequence[_HybridCandidate],
    *,
    weights: Mapping[str, float],
    rrf_k: int,
    random_seed: int,
) -> tuple[_ScoredHybridCandidate, ...]:
    scored_candidates: list[_ScoredHybridCandidate] = []
    for candidate in candidates:
        score_breakdown = _weighted_rrf_components_with_source_scores(candidate.source_contributions, weights, rrf_k)
        raw_rrf_score = weighted_rrf_score(candidate.source_contributions, weights, rrf_k)
        if raw_rrf_score <= 0:
            continue
        scored_candidates.append(
            _ScoredHybridCandidate(
                candidate=candidate,
                raw_rrf_score=raw_rrf_score,
                score_breakdown=score_breakdown,
                tie_token=_tie_token(random_seed, candidate.track.id),
            ),
        )
    return tuple(
        sorted(
            scored_candidates,
            key=lambda candidate: (-candidate.raw_rrf_score, candidate.tie_token, candidate.candidate.track.id),
        ),
    )


def _weighted_rrf_components_with_source_scores(
    contributions: Mapping[str, CandidateSourceContribution],
    weights: Mapping[str, float],
    rrf_k: int,
) -> dict[str, dict[str, float | int]]:
    components = weighted_rrf_components(contributions, weights, rrf_k)
    return {
        source: {**component, "score": contributions[source].score}
        for source, component in components.items()
    }


def _ranked_result_rows(
    db: LibraryDatabase,
    scored_candidates: Sequence[_ScoredHybridCandidate],
    *,
    limit: int,
    sources: Sequence[str],
    seed_tracks: Sequence[Track],
    seed_track_ids: Sequence[int],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    feedback_source: str,
    transition_risk_weight: float,
) -> tuple[HybridSearchResultRow, ...]:
    max_score = max((candidate.raw_rrf_score for candidate in scored_candidates), default=0.0)
    transition_sources = _effective_transition_sources(scored_candidates, sources)
    ranked_candidates = _ranked_candidates_with_transition_risk(
        scored_candidates,
        limit=limit,
        sources=transition_sources,
        seed_tracks=seed_tracks,
        max_score=max_score,
        transition_risk_weight=transition_risk_weight,
    )
    result_rows: list[HybridSearchResultRow] = []
    for rank, ranked_candidate in enumerate(ranked_candidates, start=1):
        candidate = ranked_candidate.scored_candidate
        candidate_track = db.get_track(candidate.candidate.track.id)
        explanation = build_hybrid_explanation(
            candidate_track=candidate_track,
            seed_tracks=seed_tracks,
            source_contributions=candidate.candidate.source_contributions,
            source_seed_diagnostics=candidate.candidate.source_seed_diagnostics,
            score_breakdown=candidate.score_breakdown,
            transition_diagnostics=ranked_candidate.transition_diagnostics,
            sources=sources,
            total_score=ranked_candidate.adjusted_score,
        )
        result_rows.append(
            HybridSearchResultRow(
                track=candidate.candidate.track,
                score=ranked_candidate.adjusted_score,
                total_score=explanation.total_score,
                calibrated_score=explanation.calibrated_score,
                adjusted_score=ranked_candidate.adjusted_score,
                transition_risk=ranked_candidate.transition_risk,
                transition_risk_penalty=ranked_candidate.transition_risk_penalty,
                transition_risk_weight=transition_risk_weight,
                raw_rrf_score=candidate.raw_rrf_score,
                rank=rank,
                score_breakdown=explanation.score_breakdown,
                risk_breakdown=explanation.risk_breakdown,
                source_support=explanation.source_support,
                match_character=explanation.match_character,
                warnings=explanation.warnings,
                explanation=explanation.explanation,
                transition_diagnostics=ranked_candidate.transition_diagnostics,
                diagnostics=_candidate_diagnostics(candidate.candidate),
                feedback=_candidate_feedback(
                    seed_track_ids,
                    candidate.candidate.track.id,
                    feedback_map=feedback_map,
                    source=feedback_source,
                ),
            ),
        )
    return tuple(result_rows)


def _effective_transition_sources(scored_candidates: Sequence[_ScoredHybridCandidate], sources: Sequence[str]) -> tuple[str, ...]:
    effective_sources = tuple(
        source
        for source in sources
        if any(source in candidate.candidate.source_contributions for candidate in scored_candidates)
    )
    if effective_sources:
        return effective_sources
    return tuple(sources)


def _record_hybrid_search_session(
    db: LibraryDatabase,
    results: Sequence[HybridSearchResultRow],
    *,
    seed_track_ids: Sequence[int],
    sources: Sequence[str],
    weights: Mapping[str, float],
    per_source: int,
    limit: int,
    rrf_k: int,
    random_seed: int,
    transition_risk_weight: float,
    feedback_source: str,
    record_session: bool,
) -> int | None:
    if not record_session:
        return None
    session_id = db.create_search_session(
        HYBRID_SEARCH_SESSION_MODE,
        seed_track_ids,
        {
            "sources": list(sources),
            "weights": dict(weights),
            "per_source": per_source,
            "limit": limit,
            "rrf_k": rrf_k,
            "random_seed": random_seed,
            "transition_risk_weight": transition_risk_weight,
            "feedback_source": feedback_source,
            "record_session": True,
            "candidate_count": len(results),
        },
    )
    for row in results:
        db.record_search_result_event(
            session_id,
            row.track.id,
            rank=row.rank,
            total_score=row.score,
            score_breakdown=_hybrid_event_score_breakdown(row, rrf_k=rrf_k),
        )
    return session_id


def _hybrid_event_score_breakdown(row: HybridSearchResultRow, *, rrf_k: int) -> dict[str, Any]:
    source_payload = {
        source: {
            "rank": details.get("rank"),
            "score": details.get("score"),
            "weight": details.get("weight"),
            "contribution": details.get("contribution"),
        }
        for source, details in sorted(row.score_breakdown.items())
    }
    return {
        "score_kind": "weighted_rrf_adjusted" if row.transition_risk_weight > 0 else "weighted_rrf",
        "rank": row.rank,
        "total_score": row.total_score,
        "calibrated_score": row.calibrated_score,
        "adjusted_score": row.adjusted_score,
        "raw_rrf_score": row.raw_rrf_score,
        "transition_risk": row.transition_risk,
        "transition_risk_penalty": row.transition_risk_penalty,
        "transition_risk_weight": row.transition_risk_weight,
        "rrf_k": rrf_k,
        "source_ranks": {source: details.get("rank") for source, details in sorted(row.score_breakdown.items())},
        "weighted_rrf": {
            "score": row.score,
            "components": source_payload,
        },
        "sources": source_payload,
        "score_breakdown": {source: dict(details) for source, details in sorted(row.score_breakdown.items())},
        "risk_breakdown": dict(row.risk_breakdown),
        "source_support": {source: dict(support) for source, support in sorted(row.source_support.items())},
        "match_character": dict(row.match_character),
        "warnings": list(row.warnings),
        "explanation": list(row.explanation),
        "transition_diagnostics": dict(row.transition_diagnostics),
    }


def _ranked_candidates_with_transition_risk(
    scored_candidates: Sequence[_ScoredHybridCandidate],
    *,
    limit: int,
    sources: Sequence[str],
    seed_tracks: Sequence[Track],
    max_score: float,
    transition_risk_weight: float,
) -> tuple[_RankedHybridCandidate, ...]:
    candidates_to_score = scored_candidates if transition_risk_weight > 0 else scored_candidates[:limit]
    ranked_candidates = tuple(
        _ranked_candidate(
            candidate,
            sources=sources,
            seed_tracks=seed_tracks,
            max_score=max_score,
            transition_risk_weight=transition_risk_weight,
        )
        for candidate in candidates_to_score
    )
    if transition_risk_weight <= 0:
        return ranked_candidates
    return tuple(
        sorted(
            ranked_candidates,
            key=lambda candidate: (
                -candidate.adjusted_score,
                -candidate.normalized_rrf_score,
                candidate.scored_candidate.tie_token,
                candidate.scored_candidate.candidate.track.id,
            ),
        )[:limit]
    )


def _ranked_candidate(
    candidate: _ScoredHybridCandidate,
    *,
    sources: Sequence[str],
    seed_tracks: Sequence[Track],
    max_score: float,
    transition_risk_weight: float,
) -> _RankedHybridCandidate:
    normalized_rrf_score = _normalized_response_score(candidate.raw_rrf_score, max_score)
    transition_diagnostics = _candidate_transition_diagnostics(candidate.candidate, seed_tracks=seed_tracks, sources=sources)
    transition_risk = transition_diagnostics["transition_risk"]
    transition_risk_penalty = transition_risk_weight * (float(transition_risk) if transition_risk is not None else 0.0)
    adjusted_score = normalized_rrf_score - transition_risk_penalty
    return _RankedHybridCandidate(
        scored_candidate=candidate,
        normalized_rrf_score=normalized_rrf_score,
        adjusted_score=adjusted_score,
        transition_risk=transition_risk,
        transition_risk_penalty=transition_risk_penalty,
        transition_diagnostics=transition_diagnostics,
    )


def _candidate_diagnostics(candidate: _HybridCandidate) -> dict[str, Any]:
    return {
        "supporting_seed_track_ids": list(candidate.seed_track_ids),
        "source_support": {
            source: {
                "best_seed_track_id": values["best_seed_track_id"],
                "best_rank": values["best_rank"],
                "supporting_seed_track_ids": values["supporting_seed_track_ids"],
            }
            for source, values in candidate.source_seed_diagnostics.items()
        },
    }


def _candidate_feedback(
    seed_track_ids: Sequence[int],
    candidate_track_id: int,
    *,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    source: str,
) -> dict[str, Any] | None:
    rows = [
        feedback
        for seed_track_id in seed_track_ids
        if (feedback := feedback_map.get((seed_track_id, candidate_track_id, source))) is not None
    ]
    if not rows:
        return None
    per_seed = [
        {
            "id": int(row["id"]),
            "seed_track_id": int(row["seed_track_id"]),
            "candidate_track_id": int(row["candidate_track_id"]),
            "rating": int(row["rating"]),
            "reason_tags": list(row["reason_tags"]),
            "notes": row.get("notes"),
            "source": str(row["source"]),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]
    ratings = {int(row["rating"]) for row in rows}
    reason_tag_sets = {tuple(row["reason_tags"]) for row in rows}
    notes = {row.get("notes") for row in rows}
    is_complete = len(rows) == len(seed_track_ids)
    is_consistent = len(ratings) == 1 and len(reason_tag_sets) == 1 and len(notes) == 1
    return {
        "state": "rated" if is_complete and is_consistent else "mixed",
        "source": source,
        "seed_track_ids": list(seed_track_ids),
        "candidate_track_id": candidate_track_id,
        "rating": next(iter(ratings)) if len(ratings) == 1 else None,
        "reason_tags": list(next(iter(reason_tag_sets))) if len(reason_tag_sets) == 1 else _sorted_reason_tag_union(rows),
        "notes": next(iter(notes)) if len(notes) == 1 else None,
        "per_seed": per_seed,
    }


def _sorted_reason_tag_union(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({str(tag) for row in rows for tag in row["reason_tags"]})


def _candidate_transition_diagnostics(candidate: _HybridCandidate, *, seed_tracks: Sequence[Track], sources: Sequence[str]) -> dict[str, Any]:
    seed_tracks_by_id = {track.id: track for track in seed_tracks}
    supporting_seed_track_ids, seed_scope = _transition_seed_scope(candidate, seed_tracks_by_id)
    diagnostics = tuple(
        compute_transition_diagnostics(
            seed_tracks_by_id[seed_track_id],
            candidate.track,
            source_count=len(candidate.source_contributions),
            max_source_count=len(sources),
        )
        for seed_track_id in supporting_seed_track_ids
    )
    return _mean_transition_diagnostics(
        diagnostics,
        supporting_seed_track_ids=supporting_seed_track_ids,
        seed_scope=seed_scope,
    )


def _transition_seed_scope(candidate: _HybridCandidate, seed_tracks_by_id: Mapping[int, Track]) -> tuple[tuple[int, ...], str]:
    candidate_seed_track_ids = _known_seed_track_ids(candidate.seed_track_ids, seed_tracks_by_id)
    if candidate_seed_track_ids:
        return candidate_seed_track_ids, "candidate_supporting_seeds"

    source_seed_track_ids = _known_seed_track_ids(_source_diagnostic_seed_track_ids(candidate), seed_tracks_by_id)
    if source_seed_track_ids:
        return source_seed_track_ids, "source_supporting_seeds"

    return tuple(seed_tracks_by_id), "all_request_seeds_fallback"


def _source_diagnostic_seed_track_ids(candidate: _HybridCandidate) -> tuple[int, ...]:
    seed_track_ids: list[int] = []
    for source_diagnostics in candidate.source_seed_diagnostics.values():
        seed_track_ids.extend(_iterable_ints(source_diagnostics.get("supporting_seed_track_ids")))
        seed_track_ids.extend(_iterable_ints((source_diagnostics.get("best_seed_track_id"),)))
    return tuple(dict.fromkeys(seed_track_ids))


def _known_seed_track_ids(seed_track_ids: Iterable[object], seed_tracks_by_id: Mapping[int, Track]) -> tuple[int, ...]:
    known_seed_track_ids: list[int] = []
    for value in seed_track_ids:
        seed_track_id = _optional_int(value)
        if seed_track_id is None or seed_track_id not in seed_tracks_by_id:
            continue
        known_seed_track_ids.append(seed_track_id)
    return tuple(dict.fromkeys(known_seed_track_ids))


def _iterable_ints(values: object) -> tuple[int, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        return ()
    return tuple(value for item in values if (value := _optional_int(item)) is not None)


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mean_transition_diagnostics(
    diagnostics: Sequence[TransitionDiagnostics],
    *,
    supporting_seed_track_ids: Sequence[int],
    seed_scope: str,
) -> dict[str, Any]:
    components = {
        name: _mean_optional(diagnostic.components[name] for diagnostic in diagnostics)
        for name in COMPONENT_NAMES
    }
    transition_risk = _mean_optional(components[name] for name in COMPONENT_NAMES)
    warnings = sorted({warning for diagnostic in diagnostics for warning in diagnostic.warnings})
    available_components = [name for name in COMPONENT_NAMES if components[name] is not None]
    return {
        "transition_risk": transition_risk,
        "components": components,
        "warnings": warnings,
        "available_components": available_components,
        "supporting_seed_count": len(supporting_seed_track_ids),
        "supporting_seed_track_ids": list(supporting_seed_track_ids),
        "seed_scope": seed_scope,
        "method": "mean_aggregated_component_risks",
    }


def _resolve_weights(
    sources: Sequence[str],
    *,
    weights: Mapping[str, float] | None,
    score_profile: Mapping[str, Any] | None,
) -> dict[str, float]:
    has_weights = weights is not None
    has_score_profile = score_profile is not None
    if has_weights and has_score_profile:
        raise ValueError("Provide either weights or score_profile, not both")
    if has_score_profile:
        profile = score_profile_from_dict(score_profile or {})
        _require_profile_sources_match(sources, profile)
        return _normalize_weights(profile.weights, sources)
    if has_weights:
        return _normalize_weights(weights or {}, sources)
    return {source: 1.0 / len(sources) for source in sources}


def _require_profile_sources_match(sources: Sequence[str], profile: ScoreProfile) -> None:
    profile_sources = tuple(profile.sources)
    if set(profile_sources) == set(sources):
        return
    raise ValueError(
        "score_profile sources must match requested sources exactly: "
        f"profile={', '.join(profile_sources)} requested={', '.join(sources)}",
    )


def _normalize_weights(weights: Mapping[str, float], sources: Sequence[str]) -> dict[str, float]:
    source_set = set(sources)
    clean_weights: dict[str, float] = {}
    for source, value in weights.items():
        source_name = str(source).strip().lower()
        if source_name in clean_weights:
            raise ValueError(f"weights contains duplicate normalized source {source_name!r}")
        if source_name not in source_set:
            raise ValueError(f"weights contains source {source_name!r} outside requested sources: {', '.join(sources)}")
        clean_weights[source_name] = _non_negative_finite_float(value, f"weights.{source_name}")
    missing = sorted(source_set - set(clean_weights))
    if missing:
        raise ValueError(f"weights missing requested source(s): {', '.join(missing)}")
    weight_sum = sum(clean_weights.values())
    if weight_sum <= 0:
        raise ValueError("weights must contain at least one positive value")
    return {source: clean_weights[source] / weight_sum for source in sources}


def _clean_sources(sources: Sequence[str] | None) -> tuple[str, ...]:
    values = DEFAULT_HYBRID_SOURCES if sources is None else sources
    clean_sources = tuple(dict.fromkeys(text for source in values if (text := str(source).strip().lower())))
    if not clean_sources:
        raise ValueError("At least one hybrid source is required")
    unsupported = [source for source in clean_sources if source not in ALLOWED_CANDIDATE_SOURCES]
    if unsupported:
        allowed = ", ".join(ALLOWED_CANDIDATE_SOURCES)
        raise ValueError(f"Unsupported hybrid source(s): {', '.join(unsupported)}. Allowed: {allowed}")
    return clean_sources


def _load_seed_tracks(db: LibraryDatabase, seed_track_ids: Sequence[int]) -> tuple[Track, ...]:
    seed_tracks: list[Track] = []
    unknown: list[int] = []
    for track_id in seed_track_ids:
        try:
            seed_tracks.append(db.get_track(track_id))
        except KeyError:
            unknown.append(track_id)
    if unknown:
        raise ValueError(f"Unknown seed track(s): {unknown}")
    return tuple(seed_tracks)


def _positive_unique_ints(values: Sequence[int], field_name: str) -> tuple[int, ...]:
    clean_values = tuple(dict.fromkeys(_positive_int(value, field_name) for value in values))
    if not clean_values:
        raise ValueError(f"At least one {field_name} value is required")
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


def _risk_weight(value: object, field_name: str) -> float:
    number = _non_negative_finite_float(value, field_name)
    if number > 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return number


def _mean_optional(values: Iterable[float | None]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _normalized_response_score(raw_score: float, max_score: float) -> float:
    if max_score <= 0:
        return 0.0
    return raw_score / max_score


def _tie_token(random_seed: int, candidate_track_id: int) -> int:
    digest = hashlib.sha256(f"hybrid:{random_seed}:{candidate_track_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")
