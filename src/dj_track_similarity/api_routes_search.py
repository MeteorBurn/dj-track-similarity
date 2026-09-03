from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
import time
from typing import Protocol

import numpy as np
from fastapi import FastAPI, HTTPException
from numpy.typing import NDArray

from .analysis_models import AnalysisTarget
from .analysis_model_runners import (
    current_embedding_analysis_output,
    embedding_analysis_output,
)
from .api_schemas import (
    EmbeddingRandomTrackRequest,
    SearchRequest,
    SimilaritySearchResultResponse,
    SonaraRandomTrackRequest,
    SonaraSearchRequest,
    TrackSummaryResponse,
    TextSearchFeedbackLookupRequest,
    TextSearchFeedbackLookupResponse,
    TextSearchFeedbackSummaryResponse,
    TextSearchFeedbackRequest,
    TextSearchFeedbackResponse,
    TextSearchLoadedAdapter,
    TextSearchRequest,
    TextSearchWarmupRequest,
    TextSearchWarmupResponse,
    TextSearchWarmupStatusResponse,
)
from .api_state import AppDatabaseState
from .database import LibraryDatabase
from .search import (
    CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT,
    SearchFilters,
    SimilaritySearch,
    SimilaritySearchResult,
)
from .sonara_similarity import (
    SonaraSearchMode,
    SonaraSearchUnavailable,
    SonaraSimilaritySearch,
)
from .vector_index import VectorIndexUnavailable

FloatArray = NDArray[np.float32]

# One short prompt is enough to force the deserialization and the first forward
# pass; nothing is kept, so the wording carries no meaning of its own.
_WARMUP_PROMPT = "warmup"


class _TextEmbeddingAdapter(Protocol):
    embedding_key: str

    def embed_text(self, text: str) -> FloatArray:
        ...

    def embed_texts(self, texts: Sequence[str]) -> list[FloatArray]:
        ...


@dataclass(frozen=True)
class _TextPromptBank:
    primary_query: str
    positive_queries: tuple[str, ...]
    negative_queries: tuple[str, ...]


@dataclass(frozen=True)
class _ClapTextSearchPlan:
    prompt_bank: _TextPromptBank
    filters: SearchFilters
    limit: int
    negative_weight: float
    # Each selected label's own bank, kept apart from the merged query so the
    # search can say which of them a hit belongs to.
    preset_banks: tuple[tuple[str, tuple[str, ...]], ...]
    # Tracks already judged for those labels, split by verdict, or None when
    # the search was not asked to account for them.
    feedback_track_ids: dict[str, list[int]] | None


def register_search_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    text_embedding_adapter: Callable[
        ...,
        AbstractContextManager[_TextEmbeddingAdapter],
    ],
    loaded_text_embedding_adapters: Callable[[], Sequence[tuple[str, str]]],
) -> None:
    @app.post(
        "/api/search",
        response_model=list[SimilaritySearchResultResponse],
    )
    def search(request: SearchRequest):
        filters = SearchFilters(
            min_similarity=request.min_similarity,
            epsilon=request.epsilon,
            noise=request.noise,
        )
        database = state.require_db()
        try:
            analysis_output = current_embedding_analysis_output(
                request.analysis_family,
                device="auto",
            )
            searcher = SimilaritySearch(
                database,
                request.analysis_family,
                analysis_output=analysis_output,
            )
            results = searcher.search(
                searcher.resolve_targets(request.seed_track_ids),
                filters=filters,
                limit=request.limit,
            )
            return _hydrate_similarity_results(database, results)
        except VectorIndexUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/api/search/random-track",
        response_model=TrackSummaryResponse,
    )
    def random_embedding_track(request: EmbeddingRandomTrackRequest):
        database = state.require_db()
        try:
            analysis_output = current_embedding_analysis_output(
                request.analysis_family,
                device="auto",
            )
            searcher = SimilaritySearch(
                database,
                request.analysis_family,
                analysis_output=analysis_output,
            )
            target = searcher.random_target(
                exclude_track_ids=request.exclude_track_ids,
            )
            return _hydrate_search_target(database, target)
        except VectorIndexUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/api/search/sonara",
        response_model=list[SimilaritySearchResultResponse],
    )
    def sonara_search(request: SonaraSearchRequest):
        database = state.require_db()
        try:
            searcher = SonaraSimilaritySearch(database)
            results = searcher.search(
                searcher.resolve_targets(request.seed_track_ids),
                mode=_sonara_search_mode(request.mode),
                mixer_weights=request.mixer_weights.model_dump() if request.mixer_weights else None,
                modifiers=request.modifiers.model_dump() if request.modifiers else None,
                min_similarity=request.min_similarity,
                limit=request.limit,
            )
            return _hydrate_similarity_results(database, results)
        except SonaraSearchUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/api/search/sonara/random-track",
        response_model=TrackSummaryResponse,
    )
    def random_sonara_track(request: SonaraRandomTrackRequest):
        database = state.require_db()
        try:
            searcher = SonaraSimilaritySearch(database)
            target = searcher.random_target(
                exclude_track_ids=request.exclude_track_ids,
            )
            return _hydrate_search_target(database, target)
        except SonaraSearchUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post(
        "/api/search/text",
        response_model=list[SimilaritySearchResultResponse],
    )
    def text_search(request: TextSearchRequest):
        database = state.require_db()
        try:
            # Read before the model is touched: an accumulated opinion is a
            # database question, and a search that cannot answer it should
            # still run on the words alone.
            judged = (
                database.list_text_preset_feedback_tracks(
                    preset_keys=[bank.key for bank in request.preset_banks],
                    analysis_family=request.analysis_family,
                )
                if request.use_feedback and request.preset_banks
                else None
            )
            plan = _clap_text_search_plan(request, judged)
            with text_embedding_adapter(
                request.analysis_family,
                device=request.device,
            ) as adapter:
                analysis_output = embedding_analysis_output(
                    adapter.embedding_key,
                    adapter,
                )
                searcher = SimilaritySearch(
                    database,
                    adapter.embedding_key,
                    analysis_output=analysis_output,
                )
                results = _search_clap_text_prompts(searcher, adapter, plan)
            return _hydrate_similarity_results(database, results)
        except VectorIndexUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get(
        "/api/search/text/warmup",
        response_model=TextSearchWarmupStatusResponse,
    )
    def text_search_warmup_status():
        """Report which families are resident, so a first search can say
        that it is waiting on weights rather than on the library."""

        return TextSearchWarmupStatusResponse(
            loaded=[
                TextSearchLoadedAdapter(analysis_family=family, device=device)
                for family, device in loaded_text_embedding_adapters()
            ]
        )

    @app.post(
        "/api/search/text/warmup",
        response_model=TextSearchWarmupResponse,
    )
    def warm_text_search(request: TextSearchWarmupRequest):
        """Load the family's weights now so the next search does not wait.

        The endpoint deliberately touches no database: warming is about the
        model, and it stays useful on a library that has no text embeddings
        stored yet.
        """

        started = time.perf_counter()
        try:
            with text_embedding_adapter(
                request.analysis_family,
                device=request.device,
            ) as adapter:
                adapter.embed_text(_WARMUP_PROMPT)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return TextSearchWarmupResponse(
            analysis_family=request.analysis_family,
            device=request.device,
            seconds=time.perf_counter() - started,
        )

    @app.post(
        "/api/search/text/feedback",
        response_model=TextSearchFeedbackResponse,
    )
    def text_search_feedback(request: TextSearchFeedbackRequest):
        database = state.require_db()
        try:
            presets = database.record_text_preset_feedback(
                track_uuid=request.track_uuid,
                preset_keys=request.preset_keys,
                analysis_family=request.analysis_family,
                verdict=request.verdict,
                preset_scores=request.preset_scores,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return TextSearchFeedbackResponse(
            presets=presets,
            verdict=request.verdict,
        )

    @app.post(
        "/api/search/text/feedback/lookup",
        response_model=TextSearchFeedbackLookupResponse,
    )
    def lookup_text_search_feedback(request: TextSearchFeedbackLookupRequest):
        """Report what was already said about these tracks under this bank."""

        database = state.require_db()
        try:
            verdicts = database.read_text_preset_feedback(
                track_uuids=request.track_uuids,
                preset_keys=request.preset_keys,
                analysis_family=request.analysis_family,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return TextSearchFeedbackLookupResponse(verdicts=verdicts)

    @app.get(
        "/api/search/text/feedback/summary",
        response_model=TextSearchFeedbackSummaryResponse,
    )
    def summarise_text_search_feedback():
        """Report how much has been said about each label, per model."""

        database = state.require_db()
        return TextSearchFeedbackSummaryResponse(
            presets=database.summarise_text_preset_feedback()
        )

def _clap_text_search_plan(
    request: TextSearchRequest,
    feedback_track_ids: dict[str, list[int]] | None = None,
) -> _ClapTextSearchPlan:
    positive_queries = _clean_text_queries(request.positive_queries)
    if not positive_queries:
        raise ValueError("At least one positive query is required")
    return _ClapTextSearchPlan(
        prompt_bank=_TextPromptBank(
            primary_query=positive_queries[0],
            positive_queries=positive_queries,
            negative_queries=_clean_text_queries(request.negative_queries),
        ),
        filters=SearchFilters(min_similarity=request.min_similarity),
        limit=request.limit,
        negative_weight=(
            CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT
            if request.negative_weight is None
            else request.negative_weight
        ),
        preset_banks=tuple(
            (bank.key, cleaned)
            for bank in request.preset_banks
            if (cleaned := _clean_text_queries(bank.positive_queries))
        ),
        feedback_track_ids=feedback_track_ids,
    )


def _search_clap_text_prompts(
    searcher: SimilaritySearch,
    adapter: _TextEmbeddingAdapter,
    plan: _ClapTextSearchPlan,
) -> list[SimilaritySearchResult]:
    positive_queries = plan.prompt_bank.positive_queries
    negative_queries = plan.prompt_bank.negative_queries
    # Every line of every named bank is already a line of the merged bank, so
    # embedding them once and reusing the vectors costs one forward pass rather
    # than one per label.
    preset_vectors = {
        key: adapter.embed_texts(queries) for key, queries in plan.preset_banks
    } or None
    if negative_queries or len(positive_queries) > 1 or preset_vectors:
        return searcher.search_contrast_vectors(
            positive_vectors=adapter.embed_texts(positive_queries),
            negative_vectors=adapter.embed_texts(negative_queries),
            filters=plan.filters,
            limit=plan.limit,
            negative_weight=plan.negative_weight,
            preset_vectors=preset_vectors,
            feedback_track_ids=plan.feedback_track_ids,
        )
    vector = adapter.embed_text(plan.prompt_bank.primary_query)
    return searcher.search_vector(vector, filters=plan.filters, limit=plan.limit)


def _sonara_search_mode(mode: str) -> SonaraSearchMode:
    match mode:
        case "balanced" | "vibe" | "sound" | "dj_transition" | "custom":
            return mode
        case _:
            raise ValueError(f"Unsupported SONARA search mode: {mode}")


def _clean_text_queries(queries: list[str]) -> tuple[str, ...]:
    return tuple(query.strip() for query in queries if query.strip())


def _hydrate_similarity_results(
    database: LibraryDatabase,
    results: list[SimilaritySearchResult],
) -> list[dict[str, object]]:
    """Attach current typed library summaries to validated search identities."""

    tracks = database.get_track_summaries(
        [result.target.track_id for result in results]
    )
    hydrated: list[dict[str, object]] = []
    for result, track in zip(results, tracks, strict=True):
        if (
            track.catalog_uuid != result.target.catalog_uuid
            or track.track_uuid != result.target.track_uuid
        ):
            raise RuntimeError(
                "Search result became stale before response assembly: "
                f"track_id={result.target.track_id}"
            )
        hydrated.append(
            {
                "track": track,
                "score": result.score,
                "score_breakdown": (
                    dict(result.score_breakdown)
                    if result.score_breakdown is not None
                    else None
                ),
                "preset_scores": (
                    dict(result.preset_scores)
                    if result.preset_scores is not None
                    else None
                ),
            }
        )
    return hydrated


def _hydrate_search_target(
    database: LibraryDatabase,
    target: AnalysisTarget,
) -> object:
    """Return one current track summary after checking its exact identity."""

    track = database.get_track_summaries([target.track_id])[0]
    if (
        track.catalog_uuid != target.catalog_uuid
        or track.track_uuid != target.track_uuid
    ):
        raise RuntimeError(
            "Search target became stale before response assembly: "
            f"track_id={target.track_id}"
        )
    return track
