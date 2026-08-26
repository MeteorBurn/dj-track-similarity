from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
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
    TextSearchFeedbackRequest,
    TextSearchFeedbackResponse,
    TextSearchRequest,
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


def register_search_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    text_embedding_adapter: Callable[
        ...,
        AbstractContextManager[_TextEmbeddingAdapter],
    ],
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
            plan = _clap_text_search_plan(request)
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
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return TextSearchFeedbackResponse(
            presets=presets,
            verdict=request.verdict,
        )

def _clap_text_search_plan(request: TextSearchRequest) -> _ClapTextSearchPlan:
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
    )


def _search_clap_text_prompts(
    searcher: SimilaritySearch,
    adapter: _TextEmbeddingAdapter,
    plan: _ClapTextSearchPlan,
) -> list[SimilaritySearchResult]:
    positive_queries = plan.prompt_bank.positive_queries
    negative_queries = plan.prompt_bank.negative_queries
    if negative_queries or len(positive_queries) > 1:
        return searcher.search_contrast_vectors(
            positive_vectors=adapter.embed_texts(positive_queries),
            negative_vectors=adapter.embed_texts(negative_queries),
            filters=plan.filters,
            limit=plan.limit,
            negative_weight=plan.negative_weight,
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
