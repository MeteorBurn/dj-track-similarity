from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
from typing import TYPE_CHECKING

from ..analysis_model_runners import current_embedding_analysis_output
from ..analysis_models import AnalysisOutput, AnalysisTarget
from ..search import SimilaritySearch, SimilaritySearchResult
from ..sonara_similarity import SonaraSimilaritySearch
from ..tempo_resolution import resolve_tempo_evidence
from ..track_resolution import resolve_track_camelot, resolve_track_energy, resolve_track_key
from ..transition_diagnostics import TransitionTrack
from .csv_io import CsvRow, write_csv_rows
from .track_views import load_transition_tracks_for_targets

if TYPE_CHECKING:
    from ..database import LibraryDatabase
    from ..track_models import TrackIdentity


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
    contract_hash: str = ""


@dataclass(frozen=True)
class CandidatePoolRow:
    seed_track: TransitionTrack
    candidate_track: TransitionTrack
    blind_rank: int
    source_contributions: Mapping[str, CandidateSourceContribution]
    feedback_source: str = DEFAULT_FEEDBACK_SOURCE

    @property
    def seed_track_id(self) -> int:
        return self.seed_track.identity.track_id

    @property
    def candidate_track_id(self) -> int:
        return self.candidate_track.identity.track_id

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
        seed = self.seed_track.summary
        candidate = self.candidate_track.summary
        candidate_key = resolve_track_camelot(
            self.candidate_track.identity,
            candidate,
            self.candidate_track.sonara,
        ) or resolve_track_key(
            self.candidate_track.identity,
            candidate,
            self.candidate_track.sonara,
        )
        return {
            "seed_track_id": self.seed_track_id,
            "candidate_track_id": self.candidate_track_id,
            "blind_rank": self.blind_rank,
            "rating": "",
            "reason_tags": "",
            "notes": "",
            "source": self.feedback_source,
            "seed_artist": _optional_text(seed.artist),
            "seed_title": _optional_text(seed.title),
            "candidate_artist": _optional_text(candidate.artist),
            "candidate_title": _optional_text(candidate.title),
            "candidate_bpm": _optional_number(
                resolve_tempo_evidence(
                    self.candidate_track.identity,
                    candidate,
                    self.candidate_track.sonara,
                ).bpm
            ),
            "candidate_key": _optional_text(candidate_key),
            "candidate_energy": _optional_number(
                resolve_track_energy(
                    self.candidate_track.identity,
                    candidate,
                    self.candidate_track.sonara,
                )
            ),
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
    target: AnalysisTarget
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
        identity = db.get_track_identity(seed_track_id)
        if identity is None:
            warnings.append(
                f"seed_track_id={seed_track_id} is unavailable in the current catalog"
            )
            continue
        seed_target = _analysis_target(identity)
        candidates = _collect_candidates_for_seed(
            db,
            seed_target,
            request,
            warnings,
        )
        if not candidates:
            warnings.append(f"seed_track_id={seed_track_id} produced no candidate rows")
            continue
        views = load_transition_tracks_for_targets(
            db,
            (
                seed_target,
                *(candidate.target for candidate in candidates.values()),
            ),
        )
        seed_track = views.get(seed_track_id)
        if seed_track is None:
            warnings.append(
                f"seed_track_id={seed_track_id} changed while candidates were generated"
            )
            continue
        stale_candidate_ids = sorted(set(candidates) - set(views))
        if stale_candidate_ids:
            warnings.append(
                f"seed_track_id={seed_track_id} dropped stale candidate track IDs: "
                f"{stale_candidate_ids}"
            )
        candidate_rows = _blind_candidate_rows(
            seed_track,
            candidates,
            views,
            rng,
        )
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
        source_contract_hashes = _source_contract_hashes(seed_rows)
        session_id = db.create_search_session(
            "evaluation_candidate_pool",
            [seed_track_id],
            {
                "catalog_uuid": seed_rows[0].seed_track.identity.catalog_uuid,
                "seed_identities": [
                    _identity_payload(seed_rows[0].seed_track)
                ],
                "sources": list(request.sources),
                "per_source": request.per_source,
                "random_seed": request.random_seed,
                "feedback_source": DEFAULT_FEEDBACK_SOURCE,
                "candidate_count": len(seed_rows),
                "source_contract_hashes": source_contract_hashes,
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
                    "candidate_identity": _identity_payload(
                        row.candidate_track
                    ),
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
    seed_target: AnalysisTarget,
    request: CandidateExportRequest,
    warnings: list[str],
) -> dict[int, _CandidateAccumulator]:
    candidates: dict[int, _CandidateAccumulator] = {}
    for source in request.sources:
        try:
            output, results = _search_source(
                db,
                seed_target,
                source,
                request.per_source,
            )
        except (RuntimeError, ValueError) as error:
            warnings.append(
                f"seed_track_id={seed_target.track_id} source={source} skipped: "
                f"{error}"
            )
            continue
        if not results:
            warnings.append(
                f"seed_track_id={seed_target.track_id} source={source} "
                "returned no candidates"
            )
            continue
        _merge_source_results(
            candidates,
            source,
            output,
            seed_target,
            results,
        )
    return candidates


def _search_source(
    db: LibraryDatabase,
    seed_target: AnalysisTarget,
    source: str,
    per_source: int,
) -> tuple[AnalysisOutput, list[SimilaritySearchResult]]:
    if source == "sonara":
        resolver = SonaraSimilaritySearch(db)
        output = resolver.active_output()
        search = SonaraSimilaritySearch(db, analysis_output=output)
        return output, search.search(
            [seed_target],
            mode="balanced",
            limit=per_source,
        )
    if source in {"mert", "maest", "clap"}:
        output = current_embedding_analysis_output(source)
        search = SimilaritySearch(
            db,
            source,
            analysis_output=output,
        )
        return output, search.search([seed_target], limit=per_source)
    raise ValueError(f"Unsupported candidate source: {source}")


def _merge_source_results(
    candidates: dict[int, _CandidateAccumulator],
    source: str,
    output: AnalysisOutput,
    seed_target: AnalysisTarget,
    results: Sequence[SimilaritySearchResult],
) -> None:
    rank = 0
    for result in results:
        candidate_target = result.target
        if candidate_target.catalog_uuid != seed_target.catalog_uuid:
            raise ValueError(
                f"source={source} returned a candidate from another catalog"
            )
        candidate_track_id = candidate_target.track_id
        if candidate_track_id == seed_target.track_id:
            continue
        rank += 1
        score = _finite_score(result.score, source, candidate_track_id)
        accumulator = candidates.get(candidate_track_id)
        if accumulator is None:
            accumulator = _CandidateAccumulator(
                target=candidate_target,
                source_contributions={},
            )
            candidates[candidate_track_id] = accumulator
        elif accumulator.target != candidate_target:
            raise ValueError(
                "Candidate sources returned conflicting identity snapshots for "
                f"track_id={candidate_track_id}"
            )
        accumulator.source_contributions[source] = CandidateSourceContribution(
            rank=rank,
            score=score,
            contract_hash=output.contract_hash,
        )


def _blind_candidate_rows(
    seed_track: TransitionTrack,
    candidates: Mapping[int, _CandidateAccumulator],
    views: Mapping[int, TransitionTrack],
    rng: random.Random,
) -> list[CandidatePoolRow]:
    ordered_candidates = [
        candidates[track_id]
        for track_id in sorted(candidates)
        if track_id in views
    ]
    rng.shuffle(ordered_candidates)
    return [
        CandidatePoolRow(
            seed_track=seed_track,
            candidate_track=views[candidate.target.track_id],
            blind_rank=blind_rank,
            source_contributions=dict(sorted(candidate.source_contributions.items())),
        )
        for blind_rank, candidate in enumerate(ordered_candidates, start=1)
    ]


def _source_contributions_json(contributions: Mapping[str, CandidateSourceContribution]) -> str:
    return json.dumps(_source_contribution_payload(contributions), ensure_ascii=False, sort_keys=True)


def _source_contribution_payload(
    contributions: Mapping[str, CandidateSourceContribution],
) -> dict[str, dict[str, float | int | str]]:
    return {
        source: {
            "rank": contribution.rank,
            "score": contribution.score,
            "contract_hash": contribution.contract_hash,
        }
        for source, contribution in sorted(contributions.items())
    }


def _source_contract_hashes(
    rows: Sequence[CandidatePoolRow],
) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for row in rows:
        for source, contribution in row.source_contributions.items():
            contract_hash = contribution.contract_hash.strip()
            if not contract_hash:
                raise ValueError(
                    f"Candidate source={source} has no contract hash"
                )
            existing = hashes.get(source)
            if existing is not None and existing != contract_hash:
                raise ValueError(
                    "Candidate rows contain multiple contract hashes for "
                    f"source={source}"
                )
            hashes[source] = contract_hash
    return dict(sorted(hashes.items()))


def _analysis_target(identity: TrackIdentity) -> AnalysisTarget:
    return AnalysisTarget(
        catalog_uuid=identity.catalog_uuid,
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
    )


def _identity_payload(track: TransitionTrack) -> dict[str, object]:
    identity = track.identity
    return {
        "catalog_uuid": identity.catalog_uuid,
        "track_id": identity.track_id,
        "track_uuid": identity.track_uuid,
        "content_generation": identity.content_generation,
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
