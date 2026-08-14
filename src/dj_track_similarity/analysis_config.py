from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .sonara_staging import SonaraStagingConfig

ML_ANALYSIS_MODEL_ORDER = ("maest", "mert", "muq", "mulan", "clap")
ANALYSIS_MODEL_ORDER = ("sonara", *ML_ANALYSIS_MODEL_ORDER)
ANALYSIS_DEVICE_CHOICES = ("auto", "cpu", "cuda")
ANALYSIS_DEVICE_PATTERN = "^(auto|cpu|cuda)$"
DEFAULT_ANALYSIS_DEVICE = "auto"
DEFAULT_ANALYSIS_TOP_K = 3
DEFAULT_ANALYSIS_TRACK_BATCH_SIZE = 8
DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE = 16
DEFAULT_SONARA_BATCH_SIZE = 8
DEFAULT_SONARA_ANALYSIS_MODE = "direct"
SONARA_ANALYSIS_MODES = ("direct", "staged")
MIN_ANALYSIS_TOP_K = 1
MAX_ANALYSIS_TOP_K = 10
MIN_ANALYSIS_TRACK_BATCH_SIZE = 1
MAX_ANALYSIS_TRACK_BATCH_SIZE = 64
MIN_ANALYSIS_INFERENCE_BATCH_SIZE = 1
MAX_ANALYSIS_INFERENCE_BATCH_SIZE = 128
MIN_SONARA_BATCH_SIZE = 1
MAX_SONARA_BATCH_SIZE = 16


@dataclass(frozen=True)
class AnalysisJobConfig:
    models: tuple[str, ...]
    require_current_sonara: bool
    limit: int | None
    device: str
    top_k: int
    track_batch_size: int
    inference_batch_size: int
    sonara_batch_size: int
    sonara_mode: str
    sonara_staging_config: SonaraStagingConfig | None


def normalize_analysis_models(models: Sequence[str] | None) -> tuple[str, ...]:
    requested = ML_ANALYSIS_MODEL_ORDER if models is None else models
    selected: list[str] = []
    for model in requested:
        text = str(model).strip().lower()
        if text not in ANALYSIS_MODEL_ORDER:
            raise ValueError(f"Unknown analysis model: {model}")
        if text not in selected:
            selected.append(text)
    if not selected:
        raise ValueError("At least one analysis model must be selected")
    normalized = tuple(model for model in ANALYSIS_MODEL_ORDER if model in selected)
    if "sonara" in normalized and len(normalized) != 1:
        raise ValueError(
            "SONARA analysis must run alone and cannot be combined with ML models"
        )
    return normalized


def parse_analysis_models_text(value: str) -> tuple[str, ...]:
    return normalize_analysis_models(
        [item.strip() for item in value.split(",") if item.strip()]
    )


def normalize_analysis_device(device: str | None) -> str:
    text = (device or DEFAULT_ANALYSIS_DEVICE).strip().lower()
    if text not in ANALYSIS_DEVICE_CHOICES:
        raise ValueError(f"Unknown torch device: {device}")
    return text


def normalize_sonara_mode(mode: str | None) -> str:
    text = (mode or DEFAULT_SONARA_ANALYSIS_MODE).strip().lower()
    if text not in SONARA_ANALYSIS_MODES:
        raise ValueError(f"Unknown SONARA analysis mode: {mode}")
    return text


def build_analysis_job_config(
    *,
    models: Sequence[str] | None = None,
    limit: int | None = None,
    device: str | None = DEFAULT_ANALYSIS_DEVICE,
    top_k: int = DEFAULT_ANALYSIS_TOP_K,
    track_batch_size: int = DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    inference_batch_size: int = DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    sonara_batch_size: int = DEFAULT_SONARA_BATCH_SIZE,
    sonara_mode: str = DEFAULT_SONARA_ANALYSIS_MODE,
    sonara_staging_config: SonaraStagingConfig | None = None,
    allow_empty_models: bool = False,
) -> AnalysisJobConfig:
    normalized_models = (
        ()
        if allow_empty_models and models is not None and not models
        else normalize_analysis_models(models)
    )
    normalized_sonara_mode = normalize_sonara_mode(sonara_mode)
    if normalized_sonara_mode == "staged" and sonara_staging_config is None:
        raise ValueError("Staged SONARA mode requires staging settings")
    return AnalysisJobConfig(
        models=normalized_models,
        require_current_sonara=bool(
            normalized_models and normalized_models != ("sonara",)
        ),
        limit=_normalize_limit(limit),
        device=normalize_analysis_device(device),
        top_k=_int_in_range(
            top_k, name="top_k", minimum=MIN_ANALYSIS_TOP_K, maximum=MAX_ANALYSIS_TOP_K
        ),
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
        sonara_batch_size=_int_in_range(
            sonara_batch_size,
            name="sonara_batch_size",
            minimum=MIN_SONARA_BATCH_SIZE,
            maximum=MAX_SONARA_BATCH_SIZE,
        ),
        sonara_mode=normalized_sonara_mode,
        sonara_staging_config=(
            sonara_staging_config if normalized_sonara_mode == "staged" else None
        ),
    )


def _int_in_range(value: int, *, name: str, minimum: int, maximum: int) -> int:
    integer = int(value)
    if integer < minimum or integer > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return integer


def _normalize_limit(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("limit must be a non-negative integer or None")
    integer = int(value)
    if integer < 0:
        raise ValueError("limit must be a non-negative integer or None")
    return integer
