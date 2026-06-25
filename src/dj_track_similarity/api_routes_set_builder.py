from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, HTTPException

from .api_schemas import SetBuilderGenerateRequest
from .api_state import AppDatabaseState
from .set_builder import SetBuilderConfig, SmartSetBuilder


def register_set_builder_routes(
    app: FastAPI,
    state: AppDatabaseState,
    *,
    promoted_classifiers: Callable[[], list[dict[str, object]]],
) -> None:
    @app.post("/api/set-builder/generate")
    def generate_set(request: SetBuilderGenerateRequest):
        _validate_classifier_keys(request, promoted_classifiers)
        config = SetBuilderConfig(
            seed_mode=request.seed_mode,
            seed_track_ids=request.seed_track_ids,
            auto_seed_count=request.auto_seed_count,
            mode=request.mode,
            limit=request.limit,
            diversity=request.diversity,
            energy_curve=request.energy_curve,
            bpm_mode=request.bpm_mode,
            bpm_change=request.bpm_change,
            bpm_start=request.bpm_start,
            bpm_target=request.bpm_target,
            classifier_preferences=request.classifier_preferences,
            classifier_flows=request.classifier_flows,
            random_seed=request.random_seed,
        )
        try:
            return SmartSetBuilder(state.require_db()).generate(config)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error


def _validate_classifier_keys(
    request: SetBuilderGenerateRequest,
    promoted_classifiers: Callable[[], list[dict[str, object]]],
) -> None:
    requested = set(request.classifier_preferences) | set(request.classifier_flows)
    if not requested:
        return
    available = {
        str(classifier["classifier_key"]): classifier
        for classifier in promoted_classifiers()
        if str(classifier.get("classifier_key") or "").strip()
    }
    unknown = sorted(key for key in requested if key not in available)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown classifier: {', '.join(unknown)}")
    incompatible = sorted(key for key in requested if not bool(available[key].get("is_scoring_compatible", True)))
    if incompatible:
        raise HTTPException(status_code=400, detail=f"Classifier manifest is invalid: {', '.join(incompatible)}")
