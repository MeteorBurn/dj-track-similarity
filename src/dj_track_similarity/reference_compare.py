from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from .analysis_model_runners import current_embedding_analysis_output
from .analysis_models import AnalysisTarget
from .library_models import TrackSummary
from .search import (
    AnalysisSearchRepository,
    SimilaritySearch,
    SimilaritySearchResult,
)
from .sonara_similarity import (
    SonaraSearchRepository,
    SonaraSearchUnavailable,
    SonaraSimilaritySearch,
)
from .vector_index import VectorIndexUnavailable


ReferenceCompareModel = Literal[
    "clap",
    "mert",
    "muq",
    "maest",
    "sonara",
]
ReferenceCompareVerdict = Literal[
    "mood",
    "palette",
    "instruments",
    "groove",
    "genre",
    "transition",
    "miss",
]

DEFAULT_REFERENCE_COMPARE_MODELS: tuple[
    ReferenceCompareModel,
    ...,
] = ("clap", "mert", "muq", "maest", "sonara")
_REFERENCE_COMPARE_MODELS = frozenset(DEFAULT_REFERENCE_COMPARE_MODELS)
_REFERENCE_COMPARE_VERDICTS = frozenset(
    {
        "mood",
        "palette",
        "instruments",
        "groove",
        "genre",
        "transition",
        "miss",
    }
)


class ReferenceCompareRepository(
    AnalysisSearchRepository,
    SonaraSearchRepository,
    Protocol,
):
    def list_track_summaries(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]:
        ...

    def upsert_track_pair_feedback(
        self,
        seed_track_id: int,
        candidate_track_id: int,
        rating: int,
        reason_tags: Sequence[str] = (),
        notes: str | None = None,
        source: str = "manual",
    ) -> int:
        ...


@dataclass(frozen=True, slots=True)
class ReferenceCompareQuery:
    seed_track_id: int
    models: tuple[ReferenceCompareModel, ...]
    limit: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.seed_track_id, bool)
            or not isinstance(self.seed_track_id, int)
            or self.seed_track_id <= 0
        ):
            raise ValueError("seed_track_id must be a positive integer")
        if not self.models:
            raise ValueError("models must not be empty")
        if len(set(self.models)) != len(self.models):
            raise ValueError("models must not contain duplicates")
        invalid = sorted(set(self.models) - _REFERENCE_COMPARE_MODELS)
        if invalid:
            raise ValueError(
                f"Unsupported reference compare models: {invalid}"
            )
        if (
            isinstance(self.limit, bool)
            or not isinstance(self.limit, int)
            or self.limit < 0
        ):
            raise ValueError("limit must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ReferenceCompareResult:
    """One search hit hydrated with the typed v7 library summary."""

    target: AnalysisTarget
    track: TrackSummary
    score: float
    score_breakdown: Mapping[str, float] | None = None


@dataclass(frozen=True, slots=True)
class ReferenceCompareGroup:
    model: ReferenceCompareModel
    available: bool
    reason: str | None
    results: tuple[ReferenceCompareResult, ...]


@dataclass(frozen=True, slots=True)
class ReferenceCompareResponse:
    seed_track_id: int
    groups: tuple[ReferenceCompareGroup, ...]


@dataclass(frozen=True, slots=True)
class ReferenceCompareVerdictResult:
    id: int
    seed_track_id: int
    candidate_track_id: int
    model: ReferenceCompareModel
    verdict: ReferenceCompareVerdict
    source: str
    rating: int
    notes: str | None


def build_reference_compare(
    repository: ReferenceCompareRepository,
    query: ReferenceCompareQuery,
) -> ReferenceCompareResponse:
    summaries = repository.list_track_summaries()
    summary_by_id = {
        summary.track_id: summary for summary in summaries
    }
    _require_summary(summary_by_id, query.seed_track_id)
    return ReferenceCompareResponse(
        seed_track_id=query.seed_track_id,
        groups=tuple(
            _reference_compare_group(
                repository,
                query,
                model,
                summary_by_id,
            )
            for model in query.models
        ),
    )


def record_reference_compare_verdict(
    repository: ReferenceCompareRepository,
    *,
    seed_track_id: int,
    candidate_track_id: int,
    model: ReferenceCompareModel,
    verdict: ReferenceCompareVerdict,
    notes: str | None,
) -> ReferenceCompareVerdictResult:
    if model not in _REFERENCE_COMPARE_MODELS:
        raise ValueError(
            f"Unsupported reference compare model: {model}"
        )
    if verdict not in _REFERENCE_COMPARE_VERDICTS:
        raise ValueError(
            f"Unsupported reference compare verdict: {verdict}"
        )
    summaries = repository.list_track_summaries()
    summary_by_id = {
        summary.track_id: summary for summary in summaries
    }
    _require_summary(summary_by_id, seed_track_id)
    _require_summary(summary_by_id, candidate_track_id)
    source = _feedback_source(model)
    rating = _verdict_rating(verdict)
    feedback_id = repository.upsert_track_pair_feedback(
        seed_track_id,
        candidate_track_id,
        rating,
        reason_tags=(verdict,),
        notes=notes,
        source=source,
    )
    return ReferenceCompareVerdictResult(
        id=feedback_id,
        seed_track_id=seed_track_id,
        candidate_track_id=candidate_track_id,
        model=model,
        verdict=verdict,
        source=source,
        rating=rating,
        notes=notes,
    )


def _reference_compare_group(
    repository: ReferenceCompareRepository,
    query: ReferenceCompareQuery,
    model: ReferenceCompareModel,
    summary_by_id: Mapping[int, TrackSummary],
) -> ReferenceCompareGroup:
    if model == "sonara":
        return _sonara_group(
            repository,
            query,
            summary_by_id,
        )
    return _embedding_group(
        repository,
        query,
        model,
        summary_by_id,
    )


def _embedding_group(
    repository: ReferenceCompareRepository,
    query: ReferenceCompareQuery,
    model: Literal["clap", "mert", "muq", "maest"],
    summary_by_id: Mapping[int, TrackSummary],
) -> ReferenceCompareGroup:
    try:
        output = current_embedding_analysis_output(model)
        searcher = SimilaritySearch(
            repository,
            model,
            analysis_output=output,
        )
    except VectorIndexUnavailable as error:
        return _unavailable_group(model, str(error))
    try:
        seed = searcher.resolve_targets((query.seed_track_id,))
    except ValueError:
        return _unavailable_group(
            model,
            f"Seed track is missing {model.upper()} embedding",
        )
    results = searcher.search(seed, limit=query.limit)
    return ReferenceCompareGroup(
        model=model,
        available=True,
        reason=None,
        results=_hydrate_results(results, summary_by_id),
    )


def _sonara_group(
    repository: ReferenceCompareRepository,
    query: ReferenceCompareQuery,
    summary_by_id: Mapping[int, TrackSummary],
) -> ReferenceCompareGroup:
    resolver = SonaraSimilaritySearch(repository)
    try:
        output = resolver.active_output()
    except SonaraSearchUnavailable as error:
        return _unavailable_group("sonara", str(error))
    searcher = SonaraSimilaritySearch(
        repository,
        analysis_output=output,
    )
    try:
        seed = searcher.resolve_targets((query.seed_track_id,))
    except ValueError:
        return _unavailable_group(
            "sonara",
            "Seed track is missing SONARA features",
        )
    results = searcher.search(
        seed,
        mode="balanced",
        min_similarity=0.0,
        limit=query.limit,
    )
    return ReferenceCompareGroup(
        model="sonara",
        available=True,
        reason=None,
        results=_hydrate_results(results, summary_by_id),
    )


def _hydrate_results(
    results: Sequence[SimilaritySearchResult],
    summary_by_id: Mapping[int, TrackSummary],
) -> tuple[ReferenceCompareResult, ...]:
    hydrated: list[ReferenceCompareResult] = []
    for result in results:
        try:
            summary = summary_by_id[result.target.track_id]
        except KeyError as error:
            raise RuntimeError(
                "Search returned a current target without a typed "
                f"library summary: {result.target.track_id}"
            ) from error
        hydrated.append(
            ReferenceCompareResult(
                target=result.target,
                track=summary,
                score=result.score,
                score_breakdown=result.score_breakdown,
            )
        )
    return tuple(hydrated)


def _unavailable_group(
    model: ReferenceCompareModel,
    reason: str,
) -> ReferenceCompareGroup:
    return ReferenceCompareGroup(
        model=model,
        available=False,
        reason=reason,
        results=(),
    )


def _require_summary(
    summary_by_id: Mapping[int, TrackSummary],
    track_id: int,
) -> TrackSummary:
    if (
        isinstance(track_id, bool)
        or not isinstance(track_id, int)
        or track_id <= 0
    ):
        raise ValueError("Track id must be a positive integer")
    try:
        return summary_by_id[track_id]
    except KeyError as error:
        raise ValueError(f"Unknown current track: {track_id}") from error


def _feedback_source(model: ReferenceCompareModel) -> str:
    return f"reference_compare:{model}"


def _verdict_rating(verdict: ReferenceCompareVerdict) -> int:
    if verdict == "miss":
        return 0
    return 2
