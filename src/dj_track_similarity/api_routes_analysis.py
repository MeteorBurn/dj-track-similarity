from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from .analysis_config import normalize_analysis_models
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
            models = list(normalize_analysis_models(request.models))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return state.require_analysis_jobs().start(
            models=models,
            limit=request.limit,
            track_batch_size=request.track_batch_size,
            inference_batch_size=request.inference_batch_size,
            device=request.device,
            top_k=request.top_k,
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
