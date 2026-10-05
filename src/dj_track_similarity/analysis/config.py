from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from .sonara_runtime import SONARA_BPM_PRESETS, SONARA_BPM_RANGE_NONE
from .sonara_staging import SonaraStagingConfig
from .ml_staging import MLStagingConfig

ML_ANALYSIS_MODEL_ORDER = ("maest", "mert_v2", "muq", "mulan", "clap")
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
# Outer bounds for a user-supplied analysis range. The pair must also span at
# least one octave in SONARA's sense, MAX + 1 >= 2 * MIN, which takes
# Rekordbox's one-octave ranges such as 68-135; the library schema and the
# Core validator enforce the same rule on write.
MIN_SONARA_BPM = 20.0
MAX_SONARA_BPM = 400.0


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
    # The range a SONARA run folds its tempo into, resolved against the library
    # when the job is created; both None for an unfolded run and for ML runs.
    sonara_bpm_min: float | None
    sonara_bpm_max: float | None
    sonara_staging_config: SonaraStagingConfig | None
    ml_staging_config: MLStagingConfig | None


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


def parse_sonara_bpm_range(value: str) -> tuple[float, float] | None:
    """Read the one SONARA BPM range argument: a preset name, ``none`` or ``MIN-MAX``.

    ``none`` returns None: the run reports SONARA's own tempo unfolded. A
    custom range must span at least an octave, like every preset. An argument
    that is not given at all is the caller's to handle: it means the library's
    claimed range, or the default preset for a library without one.
    """
    text = value.strip().lower()
    if text == SONARA_BPM_RANGE_NONE:
        return None
    if text in SONARA_BPM_PRESETS:
        return SONARA_BPM_PRESETS[text]
    message = (
        f"sonara_bpm_range must be a preset ({', '.join(SONARA_BPM_PRESETS)}), "
        f"{SONARA_BPM_RANGE_NONE} or MIN-MAX such as 68-135"
    )
    bounds = text.split("-")
    if len(bounds) != 2:
        raise ValueError(message)
    try:
        low, high = (float(bound) for bound in bounds)
    except ValueError as error:
        raise ValueError(message) from error
    return normalize_sonara_bpm_range(low, high)


def normalize_sonara_bpm_range(bpm_min: float, bpm_max: float) -> tuple[float, float]:
    """Validate a SONARA analysis range and return it as a float pair."""
    low = _finite_bpm(bpm_min, name="sonara_bpm_min")
    high = _finite_bpm(bpm_max, name="sonara_bpm_max")
    # Tempo folding needs an octave to resolve half/double detections, which is
    # why the stored Core row requires it too. Reject it here so the run fails
    # on its settings instead of on the first successful analysis.
    if high + 1 < 2 * low:
        raise ValueError(
            "sonara_bpm_max must be at least twice sonara_bpm_min minus 1 "
            f"({high:g} is below {2 * low - 1:g})"
        )
    return low, high


def _finite_bpm(value: float, *, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise ValueError(f"{name} must be a finite number")
    if number < MIN_SONARA_BPM or number > MAX_SONARA_BPM:
        raise ValueError(f"{name} must be between {MIN_SONARA_BPM} and {MAX_SONARA_BPM}")
    return number


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
    sonara_bpm_range: str | None = None,
    sonara_staging_config: SonaraStagingConfig | None = None,
    ml_staging_config: MLStagingConfig | None = None,
) -> AnalysisJobConfig:
    normalized_models = normalize_analysis_models(models)
    # Each layer takes only its own settings; the other layer would ignore them.
    is_sonara = normalized_models == ("sonara",)
    if not is_sonara and sonara_bpm_range is not None:
        raise ValueError("The SONARA BPM range applies only to SONARA analysis")
    if is_sonara and ml_staging_config is not None:
        raise ValueError("ML staged mode applies only to ML models")
    normalized_sonara_mode = normalize_sonara_mode(sonara_mode)
    if normalized_sonara_mode == "staged" and sonara_staging_config is None:
        raise ValueError("Staged SONARA mode requires staging settings")
    # Reject a malformed range with the other settings. The range itself is
    # resolved against the library by the SONARA job when it is created.
    if sonara_bpm_range is not None:
        parse_sonara_bpm_range(sonara_bpm_range)
    effective_inference_batch_size = _int_in_range(
        inference_batch_size,
        name="inference_batch_size",
        minimum=MIN_ANALYSIS_INFERENCE_BATCH_SIZE,
        maximum=MAX_ANALYSIS_INFERENCE_BATCH_SIZE,
    )
    if ml_staging_config is not None:
        effective_inference_batch_size = min(
            effective_inference_batch_size,
            ml_staging_config.inference_batch_size,
        )
        ml_staging_config = replace(
            ml_staging_config,
            inference_batch_size=effective_inference_batch_size,
        )
    return AnalysisJobConfig(
        models=normalized_models,
        require_current_sonara=not is_sonara,
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
        inference_batch_size=effective_inference_batch_size,
        sonara_batch_size=_int_in_range(
            sonara_batch_size,
            name="sonara_batch_size",
            minimum=MIN_SONARA_BATCH_SIZE,
            maximum=MAX_SONARA_BATCH_SIZE,
        ),
        sonara_mode=normalized_sonara_mode,
        sonara_bpm_min=None,
        sonara_bpm_max=None,
        sonara_staging_config=(
            sonara_staging_config if normalized_sonara_mode == "staged" else None
        ),
        ml_staging_config=ml_staging_config,
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
