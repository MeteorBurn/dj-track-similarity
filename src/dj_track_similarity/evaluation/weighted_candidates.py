from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..models import Track
from ..transition_diagnostics import TRANSITION_RISK_V2, compute_transition_diagnostics
from .candidates import (
    ALLOWED_CANDIDATE_SOURCES,
    DEFAULT_FEEDBACK_SOURCE,
    CandidateExportRequest,
    CandidatePoolRow,
    CandidateSourceContribution,
    generate_candidate_pool_rows,
)
from .csv_io import CsvRow, write_csv_rows
from .score_profiles import DEFAULT_RRF_K, ScoreProfile, score_profile_to_dict, validate_score_profile

if TYPE_CHECKING:
    from ..database import LibraryDatabase


WEIGHTED_CANDIDATE_SESSION_MODE = "evaluation_weighted_candidate_pool"
WEIGHTED_CANDIDATE_COLUMNS = (
    "seed_track_id",
    "candidate_track_id",
    "profile_rank",
    "profile_score",
    "adjusted_score",
    "raw_rrf_score",
    "transition_risk",
    "transition_risk_penalty",
    "transition_risk_weight",
    "rating",
    "reason_tags",
    "notes",
    "source",
    "seed_artist",
    "seed_title",
    "candidate_artist",
    "candidate_title",
    "candidate_album",
    "candidate_bpm",
    "candidate_musical_key",
    "candidate_energy",
    "source_count",
    "sources_json",
    "score_profile_name",
    "score_profile_weights_json",
)


@dataclass(frozen=True)
class WeightedCandidateRow:
    seed_track: Track
    candidate_track: Track
    profile_rank: int
    profile_score: float
    adjusted_score: float
    raw_rrf_score: float
    transition_risk: float | None
    transition_risk_penalty: float
    transition_risk_weight: float
    source_contributions: Mapping[str, CandidateSourceContribution]
    score_profile_name: str
    score_profile_weights: Mapping[str, float]
    feedback_source: str = DEFAULT_FEEDBACK_SOURCE

    @property
    def seed_track_id(self) -> int:
        return self.seed_track.id

    @property
    def candidate_track_id(self) -> int:
        return self.candidate_track.id

    @property
    def source_count(self) -> int:
        return len(self.source_contributions)

    @property
    def sources_json(self) -> str:
        return json.dumps(_source_contribution_payload(self.source_contributions), ensure_ascii=False, sort_keys=True)

    @property
    def score_profile_weights_json(self) -> str:
        return json.dumps(dict(sorted(self.score_profile_weights.items())), ensure_ascii=False, sort_keys=True)

    def csv_row(self) -> CsvRow:
        return {
            "seed_track_id": self.seed_track_id,
            "candidate_track_id": self.candidate_track_id,
            "profile_rank": self.profile_rank,
            "profile_score": self.profile_score,
            "adjusted_score": self.adjusted_score,
            "raw_rrf_score": self.raw_rrf_score,
            "transition_risk": _optional_number(self.transition_risk),
            "transition_risk_penalty": self.transition_risk_penalty,
            "transition_risk_weight": self.transition_risk_weight,
            "rating": "",
            "reason_tags": "",
            "notes": "",
            "source": self.feedback_source,
            "seed_artist": _optional_text(self.seed_track.artist),
            "seed_title": _optional_text(self.seed_track.title),
            "candidate_artist": _optional_text(self.candidate_track.artist),
            "candidate_title": _optional_text(self.candidate_track.title),
            "candidate_album": _optional_text(self.candidate_track.album),
            "candidate_bpm": _optional_number(self.candidate_track.bpm),
            "candidate_musical_key": _optional_text(self.candidate_track.musical_key),
            "candidate_energy": _optional_number(self.candidate_track.energy),
            "source_count": self.source_count,
            "sources_json": self.sources_json,
            "score_profile_name": self.score_profile_name,
            "score_profile_weights_json": self.score_profile_weights_json,
        }

    def api_row(self) -> dict[str, object]:
        row: dict[str, object] = dict(self.csv_row())
        row["transition_risk"] = self.transition_risk
        row["sources"] = _source_contribution_payload(self.source_contributions)
        row["score_profile_weights"] = dict(sorted(self.score_profile_weights.items()))
        return row


@dataclass(frozen=True)
class WeightedCandidatePoolResult:
    rows: tuple[WeightedCandidateRow, ...]
    warnings: tuple[str, ...]
    session_ids: tuple[int, ...]
    seed_track_ids: tuple[int, ...]
    sources: tuple[str, ...]
    score_profile_name: str


@dataclass(frozen=True)
class WeightedCandidatePoolRequest:
    seed_track_ids: tuple[int, ...]
    sources: tuple[str, ...]
    per_source: int
    random_seed: int
    record_session: bool
    rrf_k: int
    transition_risk_weight: float


@dataclass(frozen=True)
class _ScoredCandidate:
    row: CandidatePoolRow
    profile_score: float
    adjusted_score: float
    raw_rrf_score: float
    transition_risk: float | None
    transition_risk_penalty: float
    tie_token: int


def build_weighted_candidate_pool(
    db: LibraryDatabase,
    seed_track_ids: Sequence[int],
    profile: ScoreProfile,
    sources: Sequence[str] | None,
    per_source: int,
    random_seed: int,
    record_session: bool = False,
    rrf_k: int = DEFAULT_RRF_K,
    transition_risk_weight: float = 0.0,
) -> WeightedCandidatePoolResult:
    request = _parse_weighted_candidate_request(
        seed_track_ids=seed_track_ids,
        profile=profile,
        sources=sources,
        per_source=per_source,
        random_seed=random_seed,
        record_session=record_session,
        rrf_k=rrf_k,
        transition_risk_weight=transition_risk_weight,
    )
    candidate_rows, warnings = generate_candidate_pool_rows(
        db,
        CandidateExportRequest(
            seed_track_ids=request.seed_track_ids,
            sources=request.sources,
            per_source=request.per_source,
            random_seed=request.random_seed,
            record_session=False,
        ),
    )
    rows = _weighted_candidate_rows(candidate_rows, profile, request)
    session_ids = _record_weighted_candidate_sessions(db, rows, profile, request) if request.record_session and rows else ()
    return WeightedCandidatePoolResult(
        rows=rows,
        warnings=warnings,
        session_ids=session_ids,
        seed_track_ids=request.seed_track_ids,
        sources=request.sources,
        score_profile_name=profile.name,
    )


def write_weighted_candidate_pool_csv(path: str | Path, rows: Sequence[WeightedCandidateRow]) -> None:
    write_csv_rows(path, WEIGHTED_CANDIDATE_COLUMNS, rows)


def limit_weighted_candidate_rows_per_seed(rows: Sequence[WeightedCandidateRow], limit_per_seed: int) -> tuple[WeightedCandidateRow, ...]:
    clean_limit = _positive_int(limit_per_seed, "limit_per_seed")
    counts_by_seed: dict[int, int] = {}
    capped_rows: list[WeightedCandidateRow] = []
    for row in rows:
        seed_count = counts_by_seed.get(row.seed_track_id, 0)
        if seed_count >= clean_limit:
            continue
        capped_rows.append(row)
        counts_by_seed[row.seed_track_id] = seed_count + 1
    return tuple(capped_rows)


def _parse_weighted_candidate_request(
    *,
    seed_track_ids: Sequence[int],
    profile: ScoreProfile,
    sources: Sequence[str] | None,
    per_source: int,
    random_seed: int,
    record_session: bool,
    rrf_k: int,
    transition_risk_weight: float,
) -> WeightedCandidatePoolRequest:
    validate_score_profile(profile)
    clean_sources = _profile_sources(profile) if sources is None else _clean_sources(sources)
    _require_sources_match_profile(profile, clean_sources)
    return WeightedCandidatePoolRequest(
        seed_track_ids=_positive_unique_ints(seed_track_ids, "seed_track_id"),
        sources=clean_sources,
        per_source=_positive_int(per_source, "per_source"),
        random_seed=_int_value(random_seed, "random_seed"),
        record_session=bool(record_session),
        rrf_k=_positive_int(rrf_k, "rrf_k"),
        transition_risk_weight=_risk_weight(transition_risk_weight, "transition_risk_weight"),
    )


def _weighted_candidate_rows(
    candidate_rows: Sequence[CandidatePoolRow],
    profile: ScoreProfile,
    request: WeightedCandidatePoolRequest,
) -> tuple[WeightedCandidateRow, ...]:
    rows_by_seed: dict[int, list[CandidatePoolRow]] = {}
    for row in candidate_rows:
        if row.candidate_track_id == row.seed_track_id:
            continue
        rows_by_seed.setdefault(row.seed_track_id, []).append(row)

    weighted_rows: list[WeightedCandidateRow] = []
    for seed_track_id in request.seed_track_ids:
        scored_candidates = _scored_candidates_for_seed(rows_by_seed.get(seed_track_id, ()), profile, request)
        for profile_rank, scored_candidate in enumerate(scored_candidates, start=1):
            weighted_rows.append(
                WeightedCandidateRow(
                    seed_track=scored_candidate.row.seed_track,
                    candidate_track=scored_candidate.row.candidate_track,
                    profile_rank=profile_rank,
                    profile_score=scored_candidate.profile_score,
                    adjusted_score=scored_candidate.adjusted_score,
                    raw_rrf_score=scored_candidate.raw_rrf_score,
                    transition_risk=scored_candidate.transition_risk,
                    transition_risk_penalty=scored_candidate.transition_risk_penalty,
                    transition_risk_weight=request.transition_risk_weight,
                    source_contributions=dict(sorted(scored_candidate.row.source_contributions.items())),
                    score_profile_name=profile.name,
                    score_profile_weights=dict(sorted(profile.weights.items())),
                ),
            )
    return tuple(weighted_rows)


def _scored_candidates_for_seed(
    rows: Sequence[CandidatePoolRow],
    profile: ScoreProfile,
    request: WeightedCandidatePoolRequest,
) -> tuple[_ScoredCandidate, ...]:
    raw_scores = {
        row.candidate_track_id: _weighted_rrf_score(row.source_contributions, profile, request.rrf_k)
        for row in rows
    }
    max_raw_score = max(raw_scores.values(), default=0.0)
    max_source_count = _effective_source_count(rows, request.sources)
    scored_candidates = [
        _scored_candidate(
            row,
            raw_rrf_score=raw_scores[row.candidate_track_id],
            max_raw_score=max_raw_score,
            max_source_count=max_source_count,
            request=request,
        )
        for row in rows
    ]
    if request.transition_risk_weight > 0:
        return tuple(
            sorted(
                scored_candidates,
                key=lambda candidate: (-candidate.adjusted_score, -candidate.raw_rrf_score, candidate.tie_token, candidate.row.candidate_track_id),
            ),
        )
    return tuple(
        sorted(
            scored_candidates,
            key=lambda candidate: (-candidate.raw_rrf_score, candidate.tie_token, candidate.row.candidate_track_id),
        ),
    )


def _scored_candidate(
    row: CandidatePoolRow,
    *,
    raw_rrf_score: float,
    max_raw_score: float,
    max_source_count: int,
    request: WeightedCandidatePoolRequest,
) -> _ScoredCandidate:
    transition_diagnostics = compute_transition_diagnostics(
        row.seed_track,
        row.candidate_track,
        source_count=len(row.source_contributions),
        max_source_count=max_source_count,
    )
    normalized_rrf_score = _normalized_response_score(raw_rrf_score, max_raw_score)
    transition_risk = transition_diagnostics.transition_risk
    transition_risk_penalty = request.transition_risk_weight * (float(transition_risk) if transition_risk is not None else 0.0)
    adjusted_score = normalized_rrf_score - transition_risk_penalty
    profile_score = adjusted_score if request.transition_risk_weight > 0 else raw_rrf_score
    return _ScoredCandidate(
        row=row,
        profile_score=profile_score,
        adjusted_score=adjusted_score,
        raw_rrf_score=raw_rrf_score,
        transition_risk=transition_risk,
        transition_risk_penalty=transition_risk_penalty,
        tie_token=_tie_token(request.random_seed, row.seed_track_id, row.candidate_track_id),
    )


def _effective_source_count(rows: Sequence[CandidatePoolRow], sources: Sequence[str]) -> int:
    source_set = set(sources)
    effective_sources = {
        source
        for row in rows
        for source in row.source_contributions
        if source in source_set
    }
    return max(1, len(effective_sources))


def _record_weighted_candidate_sessions(
    db: LibraryDatabase,
    rows: Sequence[WeightedCandidateRow],
    profile: ScoreProfile,
    request: WeightedCandidatePoolRequest,
) -> tuple[int, ...]:
    rows_by_seed: dict[int, list[WeightedCandidateRow]] = {}
    for row in rows:
        rows_by_seed.setdefault(row.seed_track_id, []).append(row)

    session_ids: list[int] = []
    for seed_track_id in request.seed_track_ids:
        seed_rows = sorted(rows_by_seed.get(seed_track_id, ()), key=lambda row: row.profile_rank)
        if not seed_rows:
            continue
        session_id = db.create_search_session(
            WEIGHTED_CANDIDATE_SESSION_MODE,
            [seed_track_id],
            {
                "sources": list(request.sources),
                "per_source": request.per_source,
                "random_seed": request.random_seed,
                "rrf_k": request.rrf_k,
                "transition_risk_weight": request.transition_risk_weight,
                "transition_risk_version": TRANSITION_RISK_V2,
                "feedback_source": DEFAULT_FEEDBACK_SOURCE,
                "score_profile": score_profile_to_dict(profile),
                "score_profile_name": profile.name,
                "score_profile_weights": dict(sorted(profile.weights.items())),
                "candidate_count": len(seed_rows),
            },
        )
        for row in seed_rows:
            db.record_search_result_event(
                session_id,
                row.candidate_track_id,
                rank=row.profile_rank,
                total_score=row.profile_score,
                score_breakdown=_score_breakdown(row, profile, request.rrf_k),
            )
        session_ids.append(session_id)
    return tuple(session_ids)


def _score_breakdown(row: WeightedCandidateRow, profile: ScoreProfile, rrf_k: int) -> dict[str, Any]:
    components = _weighted_rrf_components(row.source_contributions, profile, rrf_k)
    return {
        "score_kind": "weighted_rrf",
        "profile_rank": row.profile_rank,
        "profile_score": row.profile_score,
        "adjusted_score": row.adjusted_score,
        "raw_rrf_score": row.raw_rrf_score,
        "transition_risk": row.transition_risk,
        "transition_risk_version": TRANSITION_RISK_V2,
        "transition_risk_penalty": row.transition_risk_penalty,
        "transition_risk_weight": row.transition_risk_weight,
        "rrf_k": rrf_k,
        "score_profile_name": profile.name,
        "profile_weights": dict(sorted(profile.weights.items())),
        "source_ranks": {source: component["rank"] for source, component in components.items()},
        "weighted_rrf": {
            "score": row.profile_score,
            "components": components,
        },
        "sources": _source_contribution_payload(row.source_contributions),
    }


def _weighted_rrf_score(contributions: Mapping[str, CandidateSourceContribution], profile: ScoreProfile, rrf_k: int) -> float:
    score = weighted_rrf_score(contributions, profile.weights, rrf_k)
    if not math.isfinite(score):
        raise ValueError("weighted RRF produced a non-finite score")
    return score


def weighted_rrf_score(contributions: Mapping[str, CandidateSourceContribution], weights: Mapping[str, float], rrf_k: int) -> float:
    score = sum(float(component["contribution"]) for component in weighted_rrf_components(contributions, weights, rrf_k).values())
    if not math.isfinite(score):
        raise ValueError("weighted RRF produced a non-finite score")
    return score


def weighted_rrf_components(
    contributions: Mapping[str, CandidateSourceContribution],
    weights: Mapping[str, float],
    rrf_k: int,
) -> dict[str, dict[str, float | int]]:
    clean_rrf_k = _positive_int(rrf_k, "rrf_k")
    components: dict[str, dict[str, float | int]] = {}
    for source, weight in sorted(weights.items()):
        contribution = contributions.get(source)
        if contribution is None:
            continue
        rank = _positive_int(contribution.rank, f"{source}.rank")
        clean_weight = _non_negative_finite_float(weight, f"weights.{source}")
        components[source] = {
            "rank": rank,
            "weight": clean_weight,
            "contribution": clean_weight * (1.0 / (clean_rrf_k + rank)),
        }
    return dict(sorted(components.items()))


def _weighted_rrf_components(
    contributions: Mapping[str, CandidateSourceContribution],
    profile: ScoreProfile,
    rrf_k: int,
) -> dict[str, dict[str, float | int]]:
    return weighted_rrf_components(contributions, profile.weights, rrf_k)


def _require_sources_match_profile(profile: ScoreProfile, sources: Sequence[str]) -> None:
    profile_sources = set(_profile_sources(profile))
    requested_sources = set(sources)
    missing_requested_sources = sorted(requested_sources - profile_sources)
    unrequested_profile_sources = sorted(profile_sources - requested_sources)
    if missing_requested_sources:
        raise ValueError(
            "Requested source(s) have no score profile weight: "
            f"{', '.join(missing_requested_sources)}. Profile sources: {', '.join(profile.sources)}",
        )
    if unrequested_profile_sources:
        raise ValueError(
            "Score profile contains source(s) not requested: "
            f"{', '.join(unrequested_profile_sources)}. Request all profile sources or use a matching profile.",
        )


def _profile_sources(profile: ScoreProfile) -> tuple[str, ...]:
    return tuple(str(source).strip().lower() for source in profile.sources)


def _source_contribution_payload(contributions: Mapping[str, CandidateSourceContribution]) -> dict[str, dict[str, float | int]]:
    return {
        source: {"rank": contribution.rank, "score": contribution.score}
        for source, contribution in sorted(contributions.items())
    }


def _clean_sources(sources: Sequence[str]) -> tuple[str, ...]:
    clean_sources = tuple(dict.fromkeys(text for source in sources if (text := str(source).strip().lower())))
    if not clean_sources:
        raise ValueError("At least one --source value is required")
    unsupported = [source for source in clean_sources if source not in ALLOWED_CANDIDATE_SOURCES]
    if unsupported:
        allowed = ", ".join(ALLOWED_CANDIDATE_SOURCES)
        raise ValueError(f"Unsupported source(s): {', '.join(unsupported)}. Allowed: {allowed}")
    return clean_sources


def _positive_unique_ints(values: Sequence[int], field_name: str) -> tuple[int, ...]:
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


def _normalized_response_score(raw_score: float, max_score: float) -> float:
    if max_score <= 0:
        return 0.0
    return raw_score / max_score


def _tie_token(random_seed: int, seed_track_id: int, candidate_track_id: int) -> int:
    digest = hashlib.sha256(f"{random_seed}:{seed_track_id}:{candidate_track_id}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _optional_number(value: object) -> str:
    if value is None:
        return ""
    return str(float(value))
