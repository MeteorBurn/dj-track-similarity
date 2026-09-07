from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Literal, Protocol, cast

from ..analysis.model_runners import current_embedding_analysis_output
from ..analysis_models import AnalysisTarget
from ..library_models import TrackSummary
from .engine import (
    AnalysisSearchRepository,
    SimilaritySearch,
    SimilaritySearchResult,
)
from .sonara import (
    SonaraSearchRepository,
    SonaraSearchUnavailable,
    SonaraSimilaritySearch,
)
from ..track_models import TrackIdentity
from .vector_index import VectorIndexUnavailable


LOGGER = logging.getLogger(__name__)

ReferenceCompareModel = Literal[
    "clap",
    "mert",
    "muq",
    "mulan",
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
] = ("clap", "mert", "muq", "mulan", "maest", "sonara")
_REFERENCE_COMPARE_MODELS = frozenset(
    ("clap", "mert", "muq", "mulan", "maest", "sonara")
)
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
    def get_track_summaries(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]:
        ...

    def upsert_track_pair_feedback_exact(
        self,
        seed: TrackIdentity,
        candidate: TrackIdentity,
        rating: int,
        reason_tags: Sequence[str] = (),
        notes: str | None = None,
        source: str = "manual",
    ) -> int:
        ...

    def get_track_pair_feedback_tags_exact(
        self,
        seed: TrackIdentity,
        candidates: Sequence[TrackIdentity],
        sources: Sequence[str],
    ) -> dict[tuple[int, str], tuple[str, ...]]:
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
    """One search hit hydrated with the typed library summary."""

    target: AnalysisTarget
    track: TrackSummary
    score: float
    score_breakdown: Mapping[str, float] | None = None
    saved_verdict: ReferenceCompareVerdict | None = None


@dataclass(frozen=True, slots=True)
class ReferenceCompareGroup:
    model: ReferenceCompareModel
    available: bool
    reason: str | None
    results: tuple[ReferenceCompareResult, ...]


@dataclass(frozen=True, slots=True)
class _ReferenceCompareSearchGroup:
    model: ReferenceCompareModel
    available: bool
    reason: str | None
    results: tuple[SimilaritySearchResult, ...]


class ReferenceCompareConflict(RuntimeError):
    """A track changed while its comparison was being assembled."""


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
    try:
        (seed_summary,) = repository.get_track_summaries((query.seed_track_id,))
    except KeyError as error:
        raise ValueError(f"Unknown current track: {query.seed_track_id}") from error
    seed = AnalysisTarget(
        seed_summary.catalog_uuid,
        seed_summary.track_id,
        seed_summary.track_uuid,
    )
    groups = tuple(
        _reference_compare_group(repository, query, model, seed)
        for model in query.models
    )
    selected_ids = tuple(dict.fromkeys((
        seed.track_id,
        *(result.target.track_id for group in groups for result in group.results),
    )))
    summary_by_id: dict[int, TrackSummary] = {}
    started = perf_counter()
    # The existing summary gateway uses indexed requested-ID reads up to 500 rows.
    # Keep that path even at the API's maximum six models x 100 results.
    for offset in range(0, len(selected_ids), 500):
        try:
            summaries = repository.get_track_summaries(
                selected_ids[offset:offset + 500]
            )
        except KeyError as error:
            raise ReferenceCompareConflict(
                "Tracks changed during comparison. Compare again."
            ) from error
        summary_by_id.update((summary.track_id, summary) for summary in summaries)
    _require_matching_summary(seed, summary_by_id)
    LOGGER.info(
        "LAB compare summaries loaded seed=%s tracks=%s seconds=%.3f",
        seed.track_id,
        len(summary_by_id),
        perf_counter() - started,
    )
    candidates = tuple(dict.fromkeys(
        TrackIdentity(
            result.target.catalog_uuid,
            result.target.track_id,
            result.target.track_uuid,
        )
        for group in groups for result in group.results
    ))
    try:
        feedback = repository.get_track_pair_feedback_tags_exact(
            TrackIdentity(seed.catalog_uuid, seed.track_id, seed.track_uuid),
            candidates,
            tuple(_feedback_source(group.model) for group in groups if group.results),
        )
    except RuntimeError as error:
        raise ReferenceCompareConflict(str(error)) from error
    return ReferenceCompareResponse(
        seed_track_id=query.seed_track_id,
        groups=tuple(
            ReferenceCompareGroup(
                model=group.model,
                available=group.available,
                reason=group.reason,
                results=_hydrate_results(
                    group.results, summary_by_id, group.model, feedback
                ),
            )
            for group in groups
        ),
    )


def record_reference_compare_verdict_exact(
    repository: ReferenceCompareRepository,
    *,
    seed: TrackIdentity,
    candidate: TrackIdentity,
    model: ReferenceCompareModel,
    verdict: ReferenceCompareVerdict,
    notes: str | None,
) -> ReferenceCompareVerdictResult:
    """Persist a verdict only if both displayed identities are still current."""

    if model not in _REFERENCE_COMPARE_MODELS:
        raise ValueError(
            f"Unsupported reference compare model: {model}"
        )
    if verdict not in _REFERENCE_COMPARE_VERDICTS:
        raise ValueError(
            f"Unsupported reference compare verdict: {verdict}"
        )
    source = _feedback_source(model)
    rating = _verdict_rating(verdict)
    feedback_id = repository.upsert_track_pair_feedback_exact(
        seed,
        candidate,
        rating,
        reason_tags=(verdict,),
        notes=notes,
        source=source,
    )
    return ReferenceCompareVerdictResult(
        id=feedback_id,
        seed_track_id=seed.track_id,
        candidate_track_id=candidate.track_id,
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
    seed: AnalysisTarget,
) -> _ReferenceCompareSearchGroup:
    started = perf_counter()
    LOGGER.info(
        "LAB compare model started seed=%s model=%s",
        query.seed_track_id,
        model,
    )
    try:
        if model == "sonara":
            group = _sonara_group(repository, query, seed)
        else:
            group = _embedding_group(repository, query, model, seed)
    except Exception:
        LOGGER.warning(
            "LAB compare model failed seed=%s model=%s seconds=%.3f",
            query.seed_track_id,
            model,
            perf_counter() - started,
        )
        raise
    LOGGER.info(
        "LAB compare model completed seed=%s model=%s available=%s "
        "results=%s seconds=%.3f reason=%s",
        query.seed_track_id,
        model,
        group.available,
        len(group.results),
        perf_counter() - started,
        group.reason,
    )
    return group


def _embedding_group(
    repository: ReferenceCompareRepository,
    query: ReferenceCompareQuery,
    model: Literal["clap", "mert", "muq", "mulan", "maest"],
    expected_seed: AnalysisTarget,
) -> _ReferenceCompareSearchGroup:
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
    if seed != (expected_seed,):
        raise ReferenceCompareConflict(
            f"Track identity changed during comparison: {query.seed_track_id}. "
            "Compare again."
        )
    results = searcher.search(seed, limit=query.limit)
    return _ReferenceCompareSearchGroup(
        model=model,
        available=True,
        reason=None,
        results=tuple(results),
    )


def _sonara_group(
    repository: ReferenceCompareRepository,
    query: ReferenceCompareQuery,
    expected_seed: AnalysisTarget,
) -> _ReferenceCompareSearchGroup:
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
    if seed != (expected_seed,):
        raise ReferenceCompareConflict(
            f"Track identity changed during comparison: {query.seed_track_id}. "
            "Compare again."
        )
    results = searcher.search(
        seed,
        mode="balanced",
        min_similarity=0.0,
        limit=query.limit,
    )
    return _ReferenceCompareSearchGroup(
        model="sonara",
        available=True,
        reason=None,
        results=tuple(results),
    )


def _hydrate_results(
    results: Sequence[SimilaritySearchResult],
    summary_by_id: Mapping[int, TrackSummary],
    model: ReferenceCompareModel,
    feedback: Mapping[tuple[int, str], tuple[str, ...]],
) -> tuple[ReferenceCompareResult, ...]:
    hydrated: list[ReferenceCompareResult] = []
    for result in results:
        summary = _require_matching_summary(result.target, summary_by_id)
        tags = feedback.get((result.target.track_id, _feedback_source(model)), ())
        verdict = (
            cast(ReferenceCompareVerdict, tags[0])
            if len(tags) == 1 and tags[0] in _REFERENCE_COMPARE_VERDICTS
            else None
        )
        hydrated.append(
            ReferenceCompareResult(
                target=result.target,
                track=summary,
                score=result.score,
                score_breakdown=result.score_breakdown,
                saved_verdict=verdict,
            )
        )
    return tuple(hydrated)


def _unavailable_group(
    model: ReferenceCompareModel,
    reason: str,
) -> _ReferenceCompareSearchGroup:
    return _ReferenceCompareSearchGroup(
        model=model,
        available=False,
        reason=reason,
        results=(),
    )


def _require_matching_summary(
    target: AnalysisTarget,
    summary_by_id: Mapping[int, TrackSummary],
) -> TrackSummary:
    try:
        summary = summary_by_id[target.track_id]
    except KeyError as error:
        raise ReferenceCompareConflict(
            f"Track disappeared during comparison: {target.track_id}. Compare again."
        ) from error
    if (
        summary.catalog_uuid != target.catalog_uuid
        or summary.track_uuid != target.track_uuid
    ):
        raise ReferenceCompareConflict(
            f"Track identity changed during comparison: {target.track_id}. Compare again."
        )
    return summary


def _feedback_source(model: ReferenceCompareModel) -> str:
    return f"reference_compare:{model}"


def _verdict_rating(verdict: ReferenceCompareVerdict) -> int:
    if verdict == "miss":
        return 0
    return 2
