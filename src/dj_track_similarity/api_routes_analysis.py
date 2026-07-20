from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Query

from .analysis_config import build_analysis_job_config
from .api_schemas import AnalysisJobRequest, AnalysisResetRequest, ClassifierAnalyzeRequest, ClassifierResetRequest
from .api_state import AppDatabaseState
from .classifier_production import build_classifier_calibration_report, normalize_label_suggestion_mode, suggest_classifier_labels


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
        classifier_keys = _validated_classifier_keys(request.classifier_keys, promoted_classifiers)
        try:
            config = build_analysis_job_config(
                models=request.models,
                limit=request.limit,
                device=request.device,
                top_k=request.top_k,
                track_batch_size=request.track_batch_size,
                inference_batch_size=request.inference_batch_size,
                sonara_outputs=request.sonara_outputs,
                allow_empty_models=bool(classifier_keys),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        try:
            return state.require_analysis_jobs().start(
                models=list(config.models),
                limit=config.limit,
                track_batch_size=config.track_batch_size,
                inference_batch_size=config.inference_batch_size,
                device=config.device,
                top_k=config.top_k,
                classifier_keys=classifier_keys,
                sonara_outputs=list(config.sonara_outputs),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/classifiers")
    def classifiers():
        return promoted_classifiers()

    @app.post("/api/classifiers/{classifier_key}/analyze")
    def analyze_classifier(classifier_key: str, request: ClassifierAnalyzeRequest):
        _require_scoring_compatible_classifier(classifier_key, promoted_classifiers)
        return state.require_classifier_jobs().start(classifier=classifier_key, limit=request.limit)

    @app.get("/api/classifiers/{classifier_key}/calibration-report")
    def classifier_calibration_report(classifier_key: str):
        classifier_info = _require_known_classifier(classifier_key, promoted_classifiers)
        return build_classifier_calibration_report(
            state.require_db(),
            classifier_key,
            classifier_info=classifier_info,
        )

    @app.get("/api/classifiers/{classifier_key}/label-suggestions")
    def classifier_label_suggestions(
        classifier_key: str,
        mode: str = Query(default="uncertainty"),
        limit: int = Query(default=25, ge=1, le=500),
        random_seed: int = Query(default=123),
    ):
        classifier_info = _require_known_classifier(classifier_key, promoted_classifiers)
        try:
            clean_mode = normalize_label_suggestion_mode(mode)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return suggest_classifier_labels(
            state.require_db(),
            classifier_key,
            mode=clean_mode,
            limit=limit,
            random_seed=random_seed,
            classifier_info=classifier_info,
        )

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
    available = _classifier_info_by_key(promoted_classifiers)
    unknown = [key for key in cleaned if key not in available]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown classifier: {', '.join(unknown)}")
    incompatible = [key for key in cleaned if not bool(available[key].get("is_scoring_compatible", True))]
    if incompatible:
        details = "; ".join(_classifier_manifest_error_text(available[key]) for key in incompatible)
        raise HTTPException(status_code=400, detail=details)
    return cleaned


def _require_known_classifier(
    classifier_key: str,
    promoted_classifiers: Callable[[], list[dict[str, object]]],
) -> dict[str, object]:
    key = classifier_key.strip()
    available = _classifier_info_by_key(promoted_classifiers)
    classifier_info = available.get(key)
    if classifier_info is None:
        raise HTTPException(status_code=400, detail=f"Unknown classifier: {key}")
    return classifier_info


def _require_scoring_compatible_classifier(
    classifier_key: str,
    promoted_classifiers: Callable[[], list[dict[str, object]]],
) -> dict[str, object]:
    classifier_info = _require_known_classifier(classifier_key, promoted_classifiers)
    if bool(classifier_info.get("is_scoring_compatible", True)):
        return classifier_info
    raise HTTPException(status_code=400, detail=_classifier_manifest_error_text(classifier_info))


def _classifier_info_by_key(
    promoted_classifiers: Callable[[], list[dict[str, object]]],
) -> dict[str, dict[str, object]]:
    return {
        str(classifier["classifier_key"]): classifier
        for classifier in promoted_classifiers()
        if str(classifier.get("classifier_key") or "").strip()
    }


def _classifier_manifest_error_text(classifier_info: dict[str, object]) -> str:
    key = str(classifier_info.get("classifier_key") or "unknown")
    errors = classifier_info.get("manifest_errors")
    if isinstance(errors, list) and errors:
        return f"Classifier {key} manifest is invalid: {'; '.join(str(error) for error in errors)}"
    return f"Classifier {key} manifest is invalid"
