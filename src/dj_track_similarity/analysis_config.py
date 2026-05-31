from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


ANALYSIS_MODEL_ORDER = ("sonara", "maest", "mert", "clap")
ANALYSIS_DEVICE_CHOICES = ("auto", "cpu", "cuda")
ANALYSIS_DEVICE_PATTERN = "^(auto|cpu|cuda)$"
DEFAULT_ANALYSIS_DEVICE = "auto"
DEFAULT_ANALYSIS_TOP_K = 3
DEFAULT_ANALYSIS_TRACK_BATCH_SIZE = 6
DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE = 24
MIN_ANALYSIS_TOP_K = 1
MAX_ANALYSIS_TOP_K = 10
MIN_ANALYSIS_TRACK_BATCH_SIZE = 1
MAX_ANALYSIS_TRACK_BATCH_SIZE = 64
MIN_ANALYSIS_INFERENCE_BATCH_SIZE = 1
MAX_ANALYSIS_INFERENCE_BATCH_SIZE = 128


@dataclass(frozen=True)
class AnalysisJobConfig:
    models: tuple[str, ...]
    limit: int | None
    device: str
    top_k: int
    track_batch_size: int
    inference_batch_size: int


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


def normalize_analysis_device(device: str | None) -> str:
    text = (device or DEFAULT_ANALYSIS_DEVICE).strip().lower()
    if text not in ANALYSIS_DEVICE_CHOICES:
        raise ValueError(f"Unknown torch device: {device}")
    return text


def build_analysis_job_config(
    *,
    models: Sequence[str] | None = None,
    limit: int | None = None,
    device: str | None = DEFAULT_ANALYSIS_DEVICE,
    top_k: int = DEFAULT_ANALYSIS_TOP_K,
    track_batch_size: int = DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    inference_batch_size: int = DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
) -> AnalysisJobConfig:
    return AnalysisJobConfig(
        models=normalize_analysis_models(models),
        limit=limit,
        device=normalize_analysis_device(device),
        top_k=_int_in_range(top_k, name="top_k", minimum=MIN_ANALYSIS_TOP_K, maximum=MAX_ANALYSIS_TOP_K),
        track_batch_size=_int_in_range(
            track_batch_size,
            name="track_batch_size",
            minimum=MIN_ANALYSIS_TRACK_BATCH_SIZE,
            maximum=MAX_ANALYSIS_TRACK_BATCH_SIZE,
        ),
        inference_batch_size=_int_in_range(
            inference_batch_size,
            name="inference_batch_size",
            minimum=MIN_ANALYSIS_INFERENCE_BATCH_SIZE,
            maximum=MAX_ANALYSIS_INFERENCE_BATCH_SIZE,
        ),
    )


def _int_in_range(value: int, *, name: str, minimum: int, maximum: int) -> int:
    integer = int(value)
    if integer < minimum or integer > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return integer
