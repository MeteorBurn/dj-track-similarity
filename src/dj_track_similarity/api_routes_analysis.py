from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException, Query

from .analysis_config import build_analysis_job_config
from .analysis_models import AnalysisOutput, AnalysisResetResult
from .api_schemas import (
    AnalysisJobRequest,
    AnalysisPipelineRequest,
    AnalysisResetRequest,
    AnalysisResetResponse,
    ClassifierAnalyzeRequest,
    ClassifierResetRequest,
    ClassifiersAnalyzeRequest,
    PrepareSonaraReleaseRequest,
)
from .api_state import AppDatabaseState
from .classifier_production import build_classifier_calibration_report, normalize_label_suggestion_mode, suggest_classifier_labels
from .database import LibraryDatabase


def register_analysis_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    promoted_classifiers: Callable[[], list[dict[str, object]]],
) -> None:
    @app.post(
        "/api/analysis/reset",
        response_model=AnalysisResetResponse,
    )
    def reset_analysis(request: AnalysisResetRequest):
        try:
            with state.exclusive_db("reset analysis") as database:
                outputs = _active_outputs_for_family(
                    database,
                    request.analysis_family,
                )
                if not outputs:
                    return AnalysisResetResult()
                return database.reset_analysis_outputs(outputs)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

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
                sonara_batch_size=request.sonara_batch_size,
                sonara_outputs=request.sonara_outputs,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        try:
            manager = state.require_analysis_jobs()
            if "sonara" in config.models:
                manager.validate_sonara_preflight()
            return manager.start(
                models=list(config.models),
                limit=config.limit,
                track_batch_size=config.track_batch_size,
                inference_batch_size=config.inference_batch_size,
                sonara_batch_size=config.sonara_batch_size,
                device=config.device,
                top_k=config.top_k,
                sonara_outputs=list(config.sonara_outputs),
            )
        except RuntimeError as error:
            raise HTTPException(
                status_code=409,
                detail=_analysis_conflict_detail(error),
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/classifiers")
    def classifiers():
        available = promoted_classifiers()
        compatible = [
            str(item["classifier_key"])
            for item in available
            if bool(item.get("is_scoring_compatible", True))
        ]
        readiness = state.require_classifier_jobs().readiness(compatible)
        for item in available:
            key = str(item.get("classifier_key") or "")
            counts = readiness.get(key)
            if counts is None:
                errors = item.get("manifest_errors")
                item["ready"] = 0
                item["not_ready"] = 0
                item["candidate_count"] = 0
                item["readiness_blockers"] = list(errors) if isinstance(errors, list) else ["Classifier artifact is not scoring-compatible"]
                continue
            item["ready"] = int(counts["ready"])
            item["not_ready"] = int(counts["not_ready"])
            item["candidate_count"] = int(counts["candidates"])
            item["readiness_blockers"] = list(counts["blockers"])
        return available

    @app.post("/api/classifiers/analyze")
    def analyze_classifiers(request: ClassifiersAnalyzeRequest):
        classifier_keys = _validated_classifier_keys(request.classifier_keys, promoted_classifiers, all_when_empty=True)
        try:
            return state.require_classifier_jobs().start(classifiers=classifier_keys, limit=request.limit)
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/classifiers/{classifier_key}/analyze")
    def analyze_classifier(classifier_key: str, request: ClassifierAnalyzeRequest):
        _require_scoring_compatible_classifier(classifier_key, promoted_classifiers)
        try:
            return state.require_classifier_jobs().start(classifier=classifier_key, limit=request.limit)
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (FileNotFoundError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/api/analysis/pipelines")
    def analyze_pipeline(request: AnalysisPipelineRequest):
        try:
            sonara_settings: dict[str, object] = {}
            if "sonara" in request.stages:
                sonara_config = build_analysis_job_config(
                    models=["sonara"],
                    sonara_outputs=request.sonara.outputs,
                    sonara_batch_size=request.sonara.batch_size,
                )
                sonara_settings = {
                    "outputs": list(sonara_config.sonara_outputs),
                    "batch_size": sonara_config.sonara_batch_size,
                }

            ml_settings: dict[str, object] = {}
            if "ml" in request.stages:
                ml_config = build_analysis_job_config(
                    models=request.ml.models,
                    device=request.ml.device,
                    top_k=request.ml.top_k,
                    track_batch_size=request.ml.track_batch_size,
                    inference_batch_size=request.ml.inference_batch_size,
                )
                if "sonara" in ml_config.models:
                    raise ValueError("The ML pipeline stage accepts only MAEST, MERT, MuQ, and CLAP")
                ml_settings = {
                    "models": list(ml_config.models),
                    "device": ml_config.device,
                    "top_k": ml_config.top_k,
                    "track_batch_size": ml_config.track_batch_size,
                    "inference_batch_size": ml_config.inference_batch_size,
                }
            classifier_keys = (
                _validated_classifier_keys(
                    request.classifiers.classifier_keys,
                    promoted_classifiers,
                    all_when_empty=True,
                )
                if "classifiers" in request.stages
                else []
            )
            if "sonara" in request.stages:
                state.require_analysis_jobs().validate_sonara_preflight()
            return state.require_analysis_pipeline_jobs().start(
                stages=list(request.stages),
                limit=request.limit,
                sonara=sonara_settings,
                ml=ml_settings,
                classifiers={"classifier_keys": classifier_keys},
            )
        except RuntimeError as error:
            raise HTTPException(
                status_code=409,
                detail=_analysis_conflict_detail(error),
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/analysis/pipelines/latest")
    def latest_pipeline_job():
        return state.require_analysis_pipeline_jobs().latest()

    @app.get("/api/analysis/pipelines/{job_id}")
    def pipeline_job(job_id: str):
        try:
            return state.require_analysis_pipeline_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/analysis/pipelines/{job_id}/cancel")
    def cancel_pipeline_job(job_id: str):
        try:
            return state.require_analysis_pipeline_jobs().cancel(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

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

    @app.post(
        "/api/classifiers/reset",
        response_model=AnalysisResetResponse,
    )
    def reset_classifiers(request: ClassifierResetRequest):
        with state.exclusive_db("reset classifier scores") as database:
            return database.reset_classifier_scores(
                request.classifier_keys
            )

    @app.get("/api/classifiers/{classifier_key}/analyze/jobs/latest")
    def latest_classifier_job(classifier_key: str):
        return state.require_classifier_jobs().latest(classifier=classifier_key)

    @app.get("/api/classifiers/{classifier_key}/analyze/jobs/{job_id}")
    def classifier_job(classifier_key: str, job_id: str):
        try:
            return state.require_classifier_jobs().get(job_id, classifier=classifier_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.get("/api/classifiers/analyze/jobs/latest")
    def latest_aggregate_classifier_job():
        return state.require_classifier_jobs().latest()

    @app.get("/api/classifiers/analyze/jobs/{job_id}")
    def aggregate_classifier_job(job_id: str):
        try:
            return state.require_classifier_jobs().get(job_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @app.post("/api/classifiers/analyze/jobs/{job_id}/cancel")
    def cancel_aggregate_classifier_job(job_id: str):
        try:
            return state.require_classifier_jobs().cancel(job_id)
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

    @app.post("/api/analysis/sonara/releases/prepare")
    def prepare_sonara_release(request: PrepareSonaraReleaseRequest):
        from pathlib import Path

        from .prepare_sonara_release import (
            LockHeldError,
            PrepareSonaraReleaseError,
            prepare_sonara_release as _prepare,
        )

        try:
            with state.exclusive_db(
                "prepare a SONARA release"
            ) as database:
                receipt = _prepare(
                    database,
                    backup_dir=Path(request.backup_dir),
                    confirm=request.confirm,
                )
        except LockHeldError as error:
            raise HTTPException(
                status_code=409,
                detail=f"SONARA_RELEASE_PREPARATION_REQUIRED: {error}",
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (PrepareSonaraReleaseError, RuntimeError) as error:
            raise HTTPException(status_code=500, detail=str(error)) from error

        return receipt


def _validated_classifier_keys(
    requested: list[str],
    promoted_classifiers: Callable[[], list[dict[str, object]]],
    *,
    all_when_empty: bool = False,
) -> list[str]:
    cleaned = list(dict.fromkeys(key.strip() for key in requested if key.strip()))
    if not cleaned:
        if not all_when_empty:
            return []
        cleaned = [
            str(item.get("classifier_key") or "")
            for item in promoted_classifiers()
            if str(item.get("classifier_key") or "").strip() and bool(item.get("is_scoring_compatible", True))
        ]
        if not cleaned:
            raise HTTPException(
                status_code=400,
                detail="No scoring-compatible promoted classifiers are available; retrain and promote a compatible artifact",
            )
    available = _classifier_info_by_key(promoted_classifiers)
    unknown = [key for key in cleaned if key not in available]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown classifier: {', '.join(unknown)}")
    incompatible = [key for key in cleaned if not bool(available[key].get("is_scoring_compatible", True))]
    if incompatible:
        details = "; ".join(_classifier_manifest_error_text(available[key]) for key in incompatible)
        raise HTTPException(status_code=400, detail=details)
    return cleaned


def _active_outputs_for_family(
    database: LibraryDatabase,
    analysis_family: str,
) -> tuple[AnalysisOutput, ...]:
    output_kinds = {
        "sonara": ("core", "timeline", "embedding", "fingerprint"),
        "maest": ("analysis", "embedding"),
        "mert": ("embedding",),
        "muq": ("embedding",),
        "clap": ("embedding",),
    }[analysis_family]
    return tuple(
        output
        for output_kind in output_kinds
        if (
            output := database.active_analysis_output(
                analysis_family,
                output_kind,
            )
        )
        is not None
    )


def _analysis_conflict_detail(error: Exception) -> str:
    detail = str(error)
    if "SONARA_RELEASE_PREPARATION_REQUIRED" in detail:
        return detail
    if "release" in detail.casefold():
        return f"SONARA_RELEASE_PREPARATION_REQUIRED: {detail}"
    return detail


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
