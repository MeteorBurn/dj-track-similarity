from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query

from .analysis_config import build_analysis_job_config
from .analysis_models import (
    AnalysisOutput,
    AnalysisResetResult,
)
from .api_schemas import (
    AnalysisJobRequest,
    AnalysisPipelineRequest,
    AnalysisResetRequest,
    AnalysisResetResponse,
    ClassifierAnalyzeRequest,
    ClassifierResetRequest,
    SonaraStatusResponse,
)
from .api_state import AppDatabaseState
from .classifier_production import build_classifier_calibration_report, normalize_label_suggestion_mode, suggest_classifier_labels
from .sonara_staging import SonaraStagingConfig
from .ml_staging import MLStagingConfig


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
                outputs = _outputs_for_family(request.analysis_family)
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
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        try:
            with state.job_start():
                manager = state.require_analysis_jobs()
                return manager.start(
                    models=list(config.models),
                    limit=config.limit,
                    track_batch_size=config.track_batch_size,
                    inference_batch_size=config.inference_batch_size,
                    sonara_batch_size=config.sonara_batch_size,
                    device=config.device,
                    top_k=config.top_k,
                )
        except RuntimeError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.get("/api/classifiers")
    def classifiers():
        profiles = promoted_classifiers()
        if state.db is None:
            return profiles
        score_counts = state.require_db().classifier_score_counts(
            tuple(str(profile.get("classifier_key") or "") for profile in profiles)
        )
        return [
            {
                **profile,
                "scored_tracks": score_counts.get(
                    str(profile.get("classifier_key") or ""),
                    0,
                ),
            }
            for profile in profiles
        ]

    @app.post("/api/classifiers/{classifier_key}/analyze")
    def analyze_classifier(classifier_key: str, request: ClassifierAnalyzeRequest):
        _require_scoring_compatible_classifier(classifier_key, promoted_classifiers)
        try:
            with state.job_start():
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
                staging_config: SonaraStagingConfig | None = None
                if request.sonara.mode == "staged":
                    folder = request.sonara.staged.folder.strip()
                    if not folder:
                        raise ValueError(
                            "Choose a staging folder before starting Staged Mode"
                        )
                    staging_root = Path(folder)
                    if not staging_root.is_dir():
                        raise ValueError(
                            f"SONARA staging folder does not exist: {staging_root}"
                        )
                    staging_config = SonaraStagingConfig(
                        root=staging_root,
                        processes=request.sonara.staged.processes,
                        rayon_threads=request.sonara.staged.threads,
                        max_native_batch_size=request.sonara.staged.batch_size,
                        stage_size=request.sonara.staged.stage_size,
                    )
                effective_batch_size = (
                    request.sonara.staged.batch_size
                    if request.sonara.mode == "staged"
                    else request.sonara.direct_batch_size
                )
                sonara_config = build_analysis_job_config(
                    models=["sonara"],
                    sonara_mode=request.sonara.mode,
                    sonara_batch_size=effective_batch_size,
                    sonara_staging_config=staging_config,
                )
                sonara_settings = {
                    "mode": sonara_config.sonara_mode,
                    "batch_size": sonara_config.sonara_batch_size,
                    "staging_config": sonara_config.sonara_staging_config,
                }

            ml_settings: dict[str, object] = {}
            if "ml" in request.stages:
                ml_staging_config: MLStagingConfig | None = None
                if request.ml.mode == "staged":
                    folder = request.ml.staged.folder.strip()
                    if not folder:
                        raise ValueError(
                            "Choose a staging folder before starting ML Staged Mode"
                        )
                    staging_root = Path(folder)
                    if not staging_root.is_dir():
                        raise ValueError(
                            f"ML staging folder does not exist: {staging_root}"
                        )
                    ml_staging_config = MLStagingConfig(
                        root=staging_root,
                        copy_workers=request.ml.staged.copy_workers,
                        decode_workers=request.ml.staged.decode_workers,
                        stage_size=request.ml.staged.stage_size,
                        inference_batch_size=request.ml.staged.inference_batch_size,
                        preflight_copy_enabled=request.ml.staged.preflight_copy_enabled,
                        preflight_copy_count=request.ml.staged.preflight_copy_count,
                    )
                
                ml_config = build_analysis_job_config(
                    models=request.ml.models,
                    device=request.ml.device,
                    top_k=request.ml.top_k,
                    track_batch_size=request.ml.track_batch_size,
                    inference_batch_size=request.ml.inference_batch_size,
                    ml_staging_config=ml_staging_config,
                )
                if "sonara" in ml_config.models:
                    raise ValueError(
                        "The ML pipeline stage accepts only MAEST, MERT, MuQ, "
                        "MuQ-MuLan, and CLAP"
                    )
                ml_settings = {
                    "models": list(ml_config.models),
                    "device": ml_config.device,
                    "top_k": ml_config.top_k,
                    "track_batch_size": ml_config.track_batch_size,
                    "inference_batch_size": ml_config.inference_batch_size,
                    "mode": request.ml.mode,
                    "ml_staging_config": ml_staging_config,
                }
            with state.job_start():
                return state.require_analysis_pipeline_jobs().start(
                    stages=list(request.stages),
                    limit=request.limit,
                    sonara=sonara_settings,
                    ml=ml_settings,
                )
        except RuntimeError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
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
                [request.classifier_key]
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

    @app.get(
        "/api/analysis/sonara/status",
        response_model=SonaraStatusResponse,
    )
    def sonara_status():
        try:
            return state.require_analysis_jobs().sonara_status()
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error


def _outputs_for_family(
    analysis_family: str,
) -> tuple[AnalysisOutput, ...]:
    output_kinds = {
        "sonara": ("core",),
        "maest": ("analysis", "embedding"),
        "mert": ("embedding",),
        "muq": ("embedding",),
        "mulan": ("embedding",),
        "clap": ("embedding",),
    }[analysis_family]
    return tuple(
        AnalysisOutput(analysis_family, output_kind)
        for output_kind in output_kinds
    )


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
