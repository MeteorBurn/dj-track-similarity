from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from .api_schemas import SearchRequest, SonaraSearchRequest, TextSearchRequest
from .api_state import AppDatabaseState
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
        adapter = clap_embedding_adapter(device=request.device)
        vector = adapter.embed_text(query)
        filters = SearchFilters(min_similarity=request.min_similarity)
        try:
            return SimilaritySearch(state.require_db(), embedding_key=adapter.embedding_key).search_vector(
                vector,
                filters=filters,
                limit=request.limit,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
