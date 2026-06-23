from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from .api_schemas import HybridSearchRequest, HybridSearchResponse, SearchRequest, SonaraSearchRequest, TextSearchRequest
from .api_state import AppDatabaseState
from .hybrid_search import build_hybrid_search_preview
from .search import SearchFilters, SimilaritySearch
from .sonara_similarity import SonaraSimilaritySearch


def register_search_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    clap_embedding_adapter: Callable[..., object],
) -> None:
    @app.post("/api/search")
    def search(request: SearchRequest):
        filters = SearchFilters(
            bpm_tolerance=request.bpm_tolerance,
            key_compatibility=request.key_compatibility,
            energy_min=request.energy_min,
            energy_max=request.energy_max,
            min_similarity=request.min_similarity,
            epsilon=request.epsilon,
            noise=request.noise,
        )
        try:
            return SimilaritySearch(state.require_db()).search(
                request.seed_track_ids,
                filters=filters,
                limit=request.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/search/sonara")
    def sonara_search(request: SonaraSearchRequest):
        try:
            return SonaraSimilaritySearch(state.require_db()).search(
                request.seed_track_ids,
                mode=request.mode,  # type: ignore[arg-type]
                mixer_weights=request.mixer_weights.model_dump() if request.mixer_weights else None,
                modifiers=request.modifiers.model_dump() if request.modifiers else None,
                min_similarity=request.min_similarity,
                limit=request.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/search/text")
    def text_search(request: TextSearchRequest):
        query = request.query.strip()
        if not query:
            raise HTTPException(status_code=400, detail="Text query is required")
        positive_queries = _clean_text_queries(request.positive_queries) or [query]
        negative_queries = _clean_text_queries(request.negative_queries)
        adapter = clap_embedding_adapter(device=request.device)
        filters = SearchFilters(min_similarity=request.min_similarity)
        try:
            searcher = SimilaritySearch(state.require_db(), embedding_key=adapter.embedding_key)
            if request.adaptive_contrast and negative_queries:
                positive_vectors = [adapter.embed_text(text) for text in positive_queries]
                negative_vectors = [adapter.embed_text(text) for text in negative_queries]
                return searcher.search_contrast_vectors(
                    positive_vectors=positive_vectors,
                    negative_vectors=negative_vectors,
                    filters=filters,
                    limit=request.limit,
                )
            vector = adapter.embed_text(positive_queries[0])
            return searcher.search_vector(vector, filters=filters, limit=request.limit)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/search/hybrid", response_model=HybridSearchResponse)
    def hybrid_search(request: HybridSearchRequest):
        try:
            result = build_hybrid_search_preview(
                state.require_db(),
                seed_track_ids=request.seed_track_ids,
                sources=request.sources,
                weights=request.weights,
                score_profile=request.score_profile,
                per_source=request.per_source,
                limit=request.limit,
                rrf_k=request.rrf_k,
                random_seed=request.random_seed,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return result.api_response(include_diagnostics=request.include_diagnostics)


def _clean_text_queries(queries: list[str]) -> list[str]:
    return [query.strip() for query in queries if query.strip()]
