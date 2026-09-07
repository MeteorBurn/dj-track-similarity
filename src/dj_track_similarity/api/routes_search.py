from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import uuid4
import time

import numpy as np
from fastapi import FastAPI, HTTPException
from numpy.typing import NDArray

from ..analysis_models import AnalysisTarget
from ..analysis.model_runners import (
    current_embedding_analysis_output,
    embedding_analysis_output,
    _adapter_identity,
)
from .schemas import (
    EmbeddingRandomTrackRequest,
    SearchRequest,
    SimilaritySearchResultResponse,
    SonaraRandomTrackRequest,
    SonaraSearchRequest,
    TrackSummaryResponse,
    TextSearchFeedbackLookupRequest,
    TextSearchFeedbackLookupResponse,
    TextSearchFeedbackRequest,
    TextSearchFeedbackResponse,
    TextSearchLoadedAdapter,
    TextSearchRequest,
    TextSearchResponse,
    TextSearchWarmupRequest,
    TextSearchWarmupResponse,
    TextSearchWarmupStatusResponse,
)
from .state import AppDatabaseState, DatabaseBusy
from .text_search_context import TextSearchRunCache
from ..text_search_models import QueryContext, TextSearchRun, canonical_json, content_hash, query_context_key
from ..db.text_feedback import TextFeedbackSchemaError, TextFeedbackConflict
from ..database import LibraryDatabase
from ..embedding.contracts import TextEmbeddingAdapter
from ..search.engine import (
    CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT,
    SearchFilters,
    SimilaritySearch,
    SimilaritySearchResult,
)
from ..search.sonara import (
    SonaraSearchMode,
    SonaraSearchUnavailable,
    SonaraSimilaritySearch,
)
from ..search.vector_index import VectorIndexUnavailable

FloatArray = NDArray[np.float32]

# One short prompt is enough to force the deserialization and the first forward
# pass; nothing is kept, so the wording carries no meaning of its own.
_WARMUP_PROMPT = "warmup"


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
        AbstractContextManager[TextEmbeddingAdapter],
    ],
    loaded_text_embedding_adapters: Callable[[], Sequence[tuple[str, str]]],
    text_search_runs: TextSearchRunCache,
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

    @app.post("/api/search/text", response_model=TextSearchResponse)
    def text_search(request: TextSearchRequest):
        database, generation = state.capture_db()
        try:
            plan = _clap_text_search_plan(request)
            capability = database.text_feedback_capability()
            with text_embedding_adapter(request.analysis_family, device=request.device) as adapter:
                analysis_output = embedding_analysis_output(adapter.embedding_key, adapter)
                context = QueryContext(
                    catalog_uuid=database.catalog_uuid,
                    analysis_family=request.analysis_family,
                    analysis_output_identity={
                        **_adapter_identity(adapter),
                        "analysis_family": analysis_output.analysis_family,
                        "output_kind": analysis_output.output_kind,
                    },
                    positive_queries=plan.prompt_bank.positive_queries,
                    negative_queries=plan.prompt_bank.negative_queries,
                    negative_weight=plan.negative_weight,
                    selected_preset_keys=tuple(bank.key for bank in request.preset_banks),
                    input_mode=request.input_mode,
                    scope={"kind": "all_eligible_tracks", "filters": ({"min_similarity": request.min_similarity} if request.min_similarity is not None else {})},
                ).to_dict()
                query_key = query_context_key(context)
                history = None
                feedback_enabled = request.use_feedback and request.comparison_mode == "single" and capability == "ready"
                if feedback_enabled:
                    history = database.list_text_query_feedback_tracks(query_key)
                    plan = replace(plan, feedback_track_ids={key: history[key] for key in ("relevant", "irrelevant")})
                searcher = SimilaritySearch(database, adapter.embedding_key, analysis_output=analysis_output)
                results = _search_clap_text_prompts(searcher, adapter, plan)
                resolved_device = str(adapter.device or (request.device if request.device != "auto" else "unavailable"))
            feedback = {
                "requested": request.use_feedback,
                "applied": False,
                "reason": "not_requested",
                "policy_version": "exact-query-rocchio-v1",
                "history_revision": history["history_revision"] if history else None,
                "usable_relevant_count": 0,
                "usable_irrelevant_count": 0,
            }
            if capability != "ready":
                feedback["reason"] = "schema_unavailable"
            elif request.comparison_mode == "product_ab":
                feedback["reason"] = "disabled_for_product_ab"
            elif feedback_enabled:
                feedback.update(searcher.text_feedback_status)
                usable_ids = set(searcher.text_feedback_track_ids["relevant"]) | set(searcher.text_feedback_track_ids["irrelevant"])
                feedback["history_revision"] = content_hash(sorted(
                    [judgement["track_uuid"], judgement["verdict"], judgement["revision"]]
                    for track_id, judgement in history["judgements"].items()
                    if track_id in usable_ids
                ))
            execution = {
                "run_id": uuid4().hex,
                "query_key": query_key,
                "query_context": context,
                "executed_at": datetime.now(timezone.utc).isoformat(),
                "code_revision": None,
                "device": resolved_device,
                "mode": request.comparison_mode,
                "comparison_id": request.comparison_id,
                "bank_origin": {key: context[key] for key in ("input_mode", "selected_preset_keys", "bank_hash")},
                "limit": request.limit,
                "eligible_count": searcher.text_eligible_count,
                "eligibility_digest": None,
                "eligibility_digest_reason": "index_revision_unavailable",
                "feedback": feedback,
                "feedback_capability": capability,
            }
            with state.captured_db(database, generation):
                hydrated = _hydrate_similarity_results(database, results)
                text_search_runs.put(TextSearchRun(
                    execution_json=canonical_json(execution),
                    membership=tuple((result.target.track_uuid, rank) for rank, result in enumerate(results, 1)),
                    database_generation=generation,
                ))
            return {"results": hydrated, "execution": execution}
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

    def require_run(run_id: str) -> TextSearchRun:
        run = text_search_runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=409, detail="text_search_context_expired")
        return run

    @app.post("/api/search/text/feedback", response_model=TextSearchFeedbackResponse)
    def text_search_feedback(request: TextSearchFeedbackRequest):
        run = require_run(request.run_id)
        database, generation = state.capture_db()
        try:
            if generation != run.database_generation:
                raise DatabaseBusy("text_search_context_expired")
            snapshot = run.for_track(request.track_uuid)
            with state.captured_db(database, generation):
                result = database.record_text_query_feedback(
                    context=snapshot["query_context"], run=snapshot,
                    track_uuid=request.track_uuid, verdict=request.verdict,
                    expected_revision=request.expected_revision,
                )
            return {"query_key": snapshot["query_key"], "track_uuid": request.track_uuid, "verdict": result["verdict"], "revision": result["revision"]}
        except TextFeedbackConflict as error:
            raise HTTPException(status_code=409, detail={"code": "text_feedback_revision_conflict", "current": error.current}) from error
        except TextFeedbackSchemaError as error:
            raise HTTPException(status_code=409, detail="text_feedback_schema_required") from error
        except DatabaseBusy as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/search/text/feedback/lookup", response_model=TextSearchFeedbackLookupResponse)
    def lookup_text_search_feedback(request: TextSearchFeedbackLookupRequest):
        run = require_run(request.run_id)
        database, generation = state.capture_db()
        try:
            if generation != run.database_generation:
                raise DatabaseBusy("text_search_context_expired")
            for track_uuid in request.track_uuids:
                run.for_track(track_uuid)
            snapshot = run.to_dict()
            with state.captured_db(database, generation):
                verdicts = database.read_text_query_feedback(snapshot["query_key"], request.track_uuids)
            return {"query_key": snapshot["query_key"], "verdicts": verdicts}
        except TextFeedbackSchemaError as error:
            raise HTTPException(status_code=409, detail="text_feedback_schema_required") from error
        except DatabaseBusy as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


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
    adapter: TextEmbeddingAdapter,
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
    if negative_queries or len(positive_queries) > 1 or preset_vectors or plan.feedback_track_ids is not None:
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
