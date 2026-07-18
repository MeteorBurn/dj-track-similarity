from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from typing import TYPE_CHECKING

from ..models import SearchResult, Track
from ..search import SimilaritySearch
from ..sonara_similarity import SonaraSimilaritySearch
from ..tempo_resolution import resolve_tempo_evidence
from ..track_resolution import resolve_track_camelot, resolve_track_energy, resolve_track_key
from .csv_io import CsvRow, write_csv_rows

if TYPE_CHECKING:
    from ..database import LibraryDatabase


ALLOWED_CANDIDATE_SOURCES = ("mert", "maest", "sonara", "clap")
DEFAULT_FEEDBACK_SOURCE = "manual"
EXPORT_CANDIDATE_COLUMNS = (
    "seed_track_id",
    "candidate_track_id",
    "blind_rank",
    "rating",
    "reason_tags",
    "notes",
    "source",
    "seed_artist",
    "seed_title",
    "candidate_artist",
    "candidate_title",
    "candidate_bpm",
    "candidate_key",
    "candidate_energy",
    "sources_json",
)


@dataclass(frozen=True)
class CandidateSourceContribution:
    rank: int
    score: float


@dataclass(frozen=True)
class CandidatePoolRow:
    seed_track: Track
    candidate_track: Track
    blind_rank: int
    source_contributions: Mapping[str, CandidateSourceContribution]
    feedback_source: str = DEFAULT_FEEDBACK_SOURCE

    @property
    def seed_track_id(self) -> int:
        return self.seed_track.id

    @property
    def candidate_track_id(self) -> int:
        return self.candidate_track.id

    @property
    def sources_json(self) -> str:
        return _source_contributions_json(self.source_contributions)

    @property
    def best_score(self) -> float:
        scores = [contribution.score for contribution in self.source_contributions.values()]
        if not scores:
            raise ValueError("Candidate pool row must have at least one source contribution")
        return max(scores)

    def csv_row(self) -> CsvRow:
        candidate_key = resolve_track_camelot(self.candidate_track) or resolve_track_key(self.candidate_track)
        return {
            "seed_track_id": self.seed_track_id,
            "candidate_track_id": self.candidate_track_id,
            "blind_rank": self.blind_rank,
            "rating": "",
            "reason_tags": "",
            "notes": "",
            "source": self.feedback_source,
            "seed_artist": _optional_text(self.seed_track.artist),
            "seed_title": _optional_text(self.seed_track.title),
            "candidate_artist": _optional_text(self.candidate_track.artist),
            "candidate_title": _optional_text(self.candidate_track.title),
            "candidate_bpm": _optional_number(resolve_tempo_evidence(self.candidate_track).bpm),
            "candidate_key": _optional_text(candidate_key),
            "candidate_energy": _optional_number(resolve_track_energy(self.candidate_track)),
            "sources_json": self.sources_json,
        }


@dataclass(frozen=True)
class CandidateExportResult:
    rows: tuple[CandidatePoolRow, ...]
    warnings: tuple[str, ...]
    session_ids: tuple[int, ...]


@dataclass(frozen=True)
class CandidateExportRequest:
    seed_track_ids: tuple[int, ...]
    sources: tuple[str, ...]
    per_source: int
    random_seed: int
    record_session: bool


@dataclass
class _CandidateAccumulator:
    track: Track
    source_contributions: dict[str, CandidateSourceContribution]


def export_candidate_pools(
    db: LibraryDatabase,
    *,
    seed_track_ids: Sequence[int],
    sources: Sequence[str] | None = None,
    per_source: int = 10,
    random_seed: int = 123,
    record_session: bool = True,
) -> CandidateExportResult:
    request = _parse_export_request(
        seed_track_ids=seed_track_ids,
        sources=sources,
        per_source=per_source,
        random_seed=random_seed,
        record_session=record_session,
    )
    rows, warnings = generate_candidate_pool_rows(db, request)
    session_ids = record_candidate_pool_sessions(db, rows, request) if request.record_session and rows else ()
    return CandidateExportResult(rows=rows, warnings=warnings, session_ids=session_ids)


def generate_candidate_pool_rows(
    db: LibraryDatabase,
    request: CandidateExportRequest,
) -> tuple[tuple[CandidatePoolRow, ...], tuple[str, ...]]:
    rng = random.Random(request.random_seed)
    warnings: list[str] = []
    rows: list[CandidatePoolRow] = []
    for seed_track_id in request.seed_track_ids:
        seed_track = db.get_track(seed_track_id)
        candidates = _collect_candidates_for_seed(db, seed_track_id, request, warnings)
        if not candidates:
            warnings.append(f"seed_track_id={seed_track_id} produced no candidate rows")
            continue
        candidate_rows = _blind_candidate_rows(seed_track, candidates, rng)
        rows.extend(candidate_rows)
    return tuple(rows), tuple(warnings)


def record_candidate_pool_sessions(
    db: LibraryDatabase,
    rows: Sequence[CandidatePoolRow],
    request: CandidateExportRequest,
) -> tuple[int, ...]:
    rows_by_seed: dict[int, list[CandidatePoolRow]] = {}
    for row in rows:
        rows_by_seed.setdefault(row.seed_track_id, []).append(row)

    session_ids: list[int] = []
    for seed_track_id in request.seed_track_ids:
        seed_rows = sorted(rows_by_seed.get(seed_track_id, ()), key=lambda row: row.blind_rank)
        if not seed_rows:
            continue
        session_id = db.create_search_session(
            "evaluation_candidate_pool",
            [seed_track_id],
            {
                "sources": list(request.sources),
                "per_source": request.per_source,
                "random_seed": request.random_seed,
                "feedback_source": DEFAULT_FEEDBACK_SOURCE,
                "candidate_count": len(seed_rows),
            },
        )
        for row in seed_rows:
            db.record_search_result_event(
                session_id,
                row.candidate_track_id,
                rank=row.blind_rank,
                total_score=row.best_score,
                score_breakdown={
                    "blind_rank": row.blind_rank,
                    "sources": _source_contribution_payload(row.source_contributions),
                },
            )
        session_ids.append(session_id)
    return tuple(session_ids)


def write_candidate_pool_csv(path: str | Path, rows: Sequence[CandidatePoolRow]) -> None:
    write_csv_rows(path, EXPORT_CANDIDATE_COLUMNS, rows)


def _parse_export_request(
    *,
    seed_track_ids: Sequence[int],
    sources: Sequence[str] | None,
    per_source: int,
    random_seed: int,
    record_session: bool,
) -> CandidateExportRequest:
    clean_seed_track_ids = _positive_unique_ints(seed_track_ids, "seed_track_id")
    clean_sources = _clean_sources(sources)
    clean_per_source = _positive_int(per_source, "per_source")
    clean_random_seed = _int_value(random_seed, "random_seed")
    return CandidateExportRequest(
        seed_track_ids=clean_seed_track_ids,
        sources=clean_sources,
        per_source=clean_per_source,
        random_seed=clean_random_seed,
        record_session=bool(record_session),
    )


def _collect_candidates_for_seed(
    db: LibraryDatabase,
    seed_track_id: int,
    request: CandidateExportRequest,
    warnings: list[str],
) -> dict[int, _CandidateAccumulator]:
    candidates: dict[int, _CandidateAccumulator] = {}
    for source in request.sources:
        try:
            results = _search_source(db, seed_track_id, source, request.per_source)
        except ValueError as error:
            warnings.append(f"seed_track_id={seed_track_id} source={source} skipped: {error}")
            continue
        if not results:
            warnings.append(f"seed_track_id={seed_track_id} source={source} returned no candidates")
            continue
        _merge_source_results(candidates, source, seed_track_id, results)
    for track_id, accumulator in candidates.items():
        accumulator.track = db.get_track(track_id)
    return candidates


def _search_source(db: LibraryDatabase, seed_track_id: int, source: str, per_source: int) -> list[SearchResult]:
    if source == "sonara":
        return SonaraSimilaritySearch(db).search([seed_track_id], mode="balanced", limit=per_source)
    if source in {"mert", "maest", "clap"}:
        return SimilaritySearch(db, embedding_key=source).search([seed_track_id], limit=per_source)
    raise ValueError(f"Unsupported candidate source: {source}")


def _merge_source_results(
    candidates: dict[int, _CandidateAccumulator],
    source: str,
    seed_track_id: int,
    results: Sequence[SearchResult],
) -> None:
    rank = 0
    for result in results:
        candidate_track_id = int(result.track.id)
        if candidate_track_id == seed_track_id:
            continue
        rank += 1
        score = _finite_score(result.score, source, candidate_track_id)
        accumulator = candidates.get(candidate_track_id)
        if accumulator is None:
            accumulator = _CandidateAccumulator(track=result.track, source_contributions={})
            candidates[candidate_track_id] = accumulator
        accumulator.source_contributions[source] = CandidateSourceContribution(rank=rank, score=score)


def _blind_candidate_rows(
    seed_track: Track,
    candidates: Mapping[int, _CandidateAccumulator],
    rng: random.Random,
) -> list[CandidatePoolRow]:
    ordered_candidates = [candidates[track_id] for track_id in sorted(candidates)]
    rng.shuffle(ordered_candidates)
    return [
        CandidatePoolRow(
            seed_track=seed_track,
            candidate_track=candidate.track,
            blind_rank=blind_rank,
            source_contributions=dict(sorted(candidate.source_contributions.items())),
        )
        for blind_rank, candidate in enumerate(ordered_candidates, start=1)
    ]


def _source_contributions_json(contributions: Mapping[str, CandidateSourceContribution]) -> str:
    return json.dumps(_source_contribution_payload(contributions), ensure_ascii=False, sort_keys=True)


def _source_contribution_payload(contributions: Mapping[str, CandidateSourceContribution]) -> dict[str, dict[str, float | int]]:
    return {
        source: {"rank": contribution.rank, "score": contribution.score}
        for source, contribution in sorted(contributions.items())
    }


def _clean_sources(sources: Sequence[str] | None) -> tuple[str, ...]:
    if not sources:
        return ALLOWED_CANDIDATE_SOURCES
    clean_sources = tuple(dict.fromkeys(text for source in sources if (text := str(source).strip().lower())))
    if not clean_sources:
        raise ValueError("At least one --source value is required")
    unsupported = [source for source in clean_sources if source not in ALLOWED_CANDIDATE_SOURCES]
    if unsupported:
        allowed = ", ".join(ALLOWED_CANDIDATE_SOURCES)
        raise ValueError(f"Unsupported candidate source(s): {', '.join(unsupported)}. Allowed: {allowed}")
    return clean_sources


def _positive_unique_ints(values: Sequence[int], field_name: str) -> tuple[int, ...]:
    clean_values = tuple(dict.fromkeys(_positive_int(value, field_name) for value in values))
    if not clean_values:
        raise ValueError(f"At least one --{field_name.replace('_', '-')} value is required")
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


def _int_value(value: int, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer") from error


def _finite_score(value: float, source: str, candidate_track_id: int) -> float:
    score = float(value)
    if not math.isfinite(score):
        raise ValueError(f"source={source} candidate_track_id={candidate_track_id} produced a non-finite score")
    return score


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _optional_number(value: object) -> str:
    if value is None:
        return ""
    return str(float(value))
