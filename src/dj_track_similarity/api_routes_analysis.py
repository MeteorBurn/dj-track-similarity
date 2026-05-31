from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from .analysis_config import build_analysis_job_config
from .api_schemas import AnalysisJobRequest, AnalysisResetRequest, ClassifierAnalyzeRequest, ClassifierResetRequest
from .api_state import AppDatabaseState


def register_analysis_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    promoted_classifiers: Callable[[], list[dict[str, object]]],
) -> None:
    @app.post("/api/analysis/reset")
    def reset_analysis(request: AnalysisResetRequest):
        try:
            return state.require_db().reset_analysis(request.adapter)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/analysis/jobs")
    def analyze(request: AnalysisJobRequest):
        try:
            config = build_analysis_job_config(
                models=request.models,
                limit=request.limit,
                device=request.device,
                top_k=request.top_k,
                track_batch_size=request.track_batch_size,
                inference_batch_size=request.inference_batch_size,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        classifier_keys = _validated_classifier_keys(request.classifier_keys, promoted_classifiers)
        return state.require_analysis_jobs().start(
            models=list(config.models),
            limit=config.limit,
            track_batch_size=config.track_batch_size,
            inference_batch_size=config.inference_batch_size,
            device=config.device,
            top_k=config.top_k,
            classifier_keys=classifier_keys,
        )

    @app.get("/api/classifiers")
    def classifiers():
        return promoted_classifiers()

    @app.post("/api/classifiers/{classifier_key}/analyze")
    def analyze_classifier(classifier_key: str, request: ClassifierAnalyzeRequest):
        return state.require_classifier_jobs().start(classifier=classifier_key, limit=request.limit)

    @app.post("/api/classifiers/reset")
    def reset_classifiers(request: ClassifierResetRequest):
        return state.require_db().reset_classifier_scores(request.classifiers)

    @app.get("/api/classifiers/{classifier_key}/analyze/jobs/latest")
    def latest_classifier_job(classifier_key: str):
        return state.require_classifier_jobs().latest(classifier=classifier_key)

    @app.get("/api/classifiers/{classifier_key}/analyze/jobs/{job_id}")
    def classifier_job(classifier_key: str, job_id: str):
        try:
            return state.require_classifier_jobs().get(job_id, classifier=classifier_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/classifiers/{classifier_key}/analyze/jobs/{job_id}/cancel")
    def cancel_classifier_job(classifier_key: str, job_id: str):
        try:
            return state.require_classifier_jobs().cancel(job_id, classifier=classifier_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/analysis/jobs/latest")
    def latest_analyze_job():
        return state.require_analysis_jobs().latest()

    @app.get("/api/analysis/jobs/{job_id}")
    def analyze_job(job_id: str):
        try:
            return state.require_analysis_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/analysis/jobs/{job_id}/cancel")
    def cancel_analyze_job(job_id: str):
        try:
            return state.require_analysis_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


def _validated_classifier_keys(
    requested: list[str],
    promoted_classifiers: Callable[[], list[dict[str, object]]],
) -> list[str]:
    cleaned = list(dict.fromkeys(key.strip() for key in requested if key.strip()))
    if not cleaned:
        return []
    available = {str(classifier["classifier_key"]) for classifier in promoted_classifiers()}
    unknown = [key for key in cleaned if key not in available]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown classifier: {', '.join(unknown)}")
    return cleaned
