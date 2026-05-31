from __future__ import annotations

from collections.abc import Sequence


ANALYSIS_MODEL_ORDER = ("sonara", "maest", "mert", "clap")
DEFAULT_ANALYSIS_TRACK_BATCH_SIZE = 6
DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE = 24


def normalize_analysis_models(models: Sequence[str] | None) -> tuple[str, ...]:
    requested = ANALYSIS_MODEL_ORDER if models is None else models
    selected: list[str] = []
    for model in requested:
        text = str(model).strip().lower()
        if text not in ANALYSIS_MODEL_ORDER:
            raise ValueError(f"Unknown analysis model: {model}")
        if text not in selected:
            selected.append(text)
    if not selected:
        raise ValueError("At least one analysis model must be selected")
    return tuple(model for model in ANALYSIS_MODEL_ORDER if model in selected)


def parse_analysis_models_text(value: str) -> tuple[str, ...]:
    return normalize_analysis_models([item.strip() for item in value.split(",") if item.strip()])
