from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from fastapi import FastAPI, HTTPException
from numpy.typing import NDArray

from .analysis_model_runners import (
    current_embedding_analysis_output,
    embedding_analysis_output,
)
from .api_schemas import (
    HybridSearchRequest,
    HybridSearchResponse,
    SearchRequest,
    SimilaritySearchResultV7,
    SonaraSearchRequest,
    TextSearchRequest,
)
from .api_state import AppDatabaseState
from .database import LibraryDatabase
from .hybrid_search import build_hybrid_search_preview
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
    adaptive_contrast: bool


def register_search_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    clap_embedding_adapter: Callable[..., _TextEmbeddingAdapter],
) -> None:
    @app.post(
        "/api/search",
        response_model=list[SimilaritySearchResultV7],
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
        "/api/search/sonara",
        response_model=list[SimilaritySearchResultV7],
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
        "/api/search/text",
        response_model=list[SimilaritySearchResultV7],
    )
    def text_search(request: TextSearchRequest):
        database = state.require_db()
        try:
            plan = _clap_text_search_plan(request)
            adapter = clap_embedding_adapter(device=request.device)
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

    @app.post("/api/search/hybrid", response_model=HybridSearchResponse)
    def hybrid_search(request: HybridSearchRequest):
        try:
            result = build_hybrid_search_preview(
                state.require_db(),
                seed_track_ids=request.seed_track_ids,
                analysis_outputs={
                    family: current_embedding_analysis_output(family)
                    for family in ("mert", "maest", "clap")
                },
                sources=request.sources,
                weights=request.weights,
                score_profile=request.score_profile,
                per_source=request.per_source,
                limit=request.limit,
                rrf_k=request.rrf_k,
                random_seed=request.random_seed,
                transition_risk_weight=request.transition_risk_weight,
                transition_risk_version=request.transition_risk_version,
                classifier_preferences=request.classifier_preferences,
                classifier_risk_weights=request.classifier_risk_weights,
                record_session=request.record_session,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return result.api_response(include_diagnostics=request.include_diagnostics)


def _clap_text_search_plan(request: TextSearchRequest) -> _ClapTextSearchPlan:
    query = request.query.strip()
    if not query:
        raise ValueError("Text query is required")
    positive_queries = _clean_text_queries(request.positive_queries) or (query,)
    return _ClapTextSearchPlan(
        prompt_bank=_TextPromptBank(
            primary_query=positive_queries[0],
            positive_queries=positive_queries,
            negative_queries=_clean_text_queries(request.negative_queries),
        ),
        filters=SearchFilters(min_similarity=request.min_similarity),
        limit=request.limit,
        adaptive_contrast=request.adaptive_contrast,
    )


def _search_clap_text_prompts(
    searcher: SimilaritySearch,
    adapter: _TextEmbeddingAdapter,
    plan: _ClapTextSearchPlan,
) -> list[SimilaritySearchResult]:
    positive_queries = plan.prompt_bank.positive_queries
    negative_queries = plan.prompt_bank.negative_queries
    if plan.adaptive_contrast and (negative_queries or len(positive_queries) > 1):
        return searcher.search_contrast_vectors(
            positive_vectors=[adapter.embed_text(text) for text in positive_queries],
            negative_vectors=[adapter.embed_text(text) for text in negative_queries],
            filters=plan.filters,
            limit=plan.limit,
            negative_weight=CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT,
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
            or track.content_generation != result.target.content_generation
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
