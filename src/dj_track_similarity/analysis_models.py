"""Typed analysis repository records.

The models in this module deliberately carry the complete library track
identity. A numeric ``track_id`` alone is not a safe write target because it
does not distinguish another library catalog, a replaced track UUID, or a
newer content generation.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

import numpy as np

from .db_ddl import ClassifierScoreRecord, SonaraRow
from .maest_windows import MaestWindowContext

OUTPUT_KINDS_BY_FAMILY: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "sonara": frozenset({"core"}),
        "maest": frozenset({"analysis", "embedding"}),
        "mert": frozenset({"embedding"}),
        "muq": frozenset({"embedding"}),
        "clap": frozenset({"embedding"}),
    }
)

MAEST_MODEL_NAME = "discogs-maest-30s-pw-129e-519l"
MERT_MODEL_NAME = "m-a-p/MERT-v1-95M"
MUQ_MODEL_NAME = "OpenMuQ/MuQ-large-msd-iter"
CLAP_MODEL_NAME = "lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt"
CLAP_TEXT_MODEL_NAME = "roberta-base"

MAEST_ADAPTER_REVISION = "maest-adapter-v2"
MERT_ADAPTER_REVISION = "mert-adapter-v1"
MUQ_ADAPTER_REVISION = "muq-adapter-v1"
CLAP_ADAPTER_REVISION = "clap-adapter-v2"

MAEST_MODEL_VERSION = "v0.0.0-beta"
MERT_MODEL_REVISION = "12af15fef9d0ac838c3f475bfbbf26d2060dd4f5"
MUQ_MODEL_REVISION = "0562a57814f6f8bbd9fdea0a25921a2fce1a841a"
CLAP_MODEL_REVISION = "b3708341862f581175dba5c356a4ebf74a9b6651"
CLAP_TEXT_MODEL_REVISION = "e2da8e2f811d1448a5b465c236feacd80ffbac7b"

MAEST_CHECKPOINT_ID = (
    "sha256:d6044e642b6ae295ee1164cc52b33ac663e247f03b4b100a0af1a5edfab18cdb"
)
MERT_CHECKPOINT_ID = (
    "sha256:a2b8b747f72c06e0595aeae41ae5473f4364938c6b39b2c58be38c48e6bd3fcd"
)
MUQ_CHECKPOINT_ID = (
    "sha256:273febab2be02872c37d2c37e48a9d6c52c1c9392f3eeeabd498efa281ccb7a6"
)
CLAP_CHECKPOINT_ID = (
    "sha256:fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd"
)

MERT_SNAPSHOT_SHA256 = (
    (
        "config.json",
        "ea2627c4c7825cd66f3c944b6b966331604c35928174e0100cd4a82829424e32",
    ),
    (
        "configuration_MERT.py",
        "ae0ec2bab8f59c724ba9878a7c20b67210189536ea62d34a56775968e9decb03",
    ),
    (
        "modeling_MERT.py",
        "6c3ee73cef6f0c30ef494f88d96f891fa6925ffe663fa391b512f4b57abecc6c",
    ),
    (
        "preprocessor_config.json",
        "cc5a5e4a5d3b1a758a5ed984b2eaa15bb0522d811d44a9eed82bfca4baa0dc8f",
    ),
    ("pytorch_model.bin", MERT_CHECKPOINT_ID.removeprefix("sha256:")),
)
MUQ_SNAPSHOT_SHA256 = (
    (
        "config.json",
        "237335ee27d8fb951ce778701a12a79e06c51ae636dd786f97e45f51ce532543",
    ),
    ("model.safetensors", MUQ_CHECKPOINT_ID.removeprefix("sha256:")),
)
CLAP_TEXT_SNAPSHOT_SHA256 = (
    (
        "config.json",
        "ef0185e2aae6e06c5f105a285006952c340e20c7dbf43c86ec82601b13fc45e9",
    ),
    (
        "merges.txt",
        "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5",
    ),
    (
        "model.safetensors",
        "5bde1d28afb363d0103324efeb5afc8b2b397fe5e04beabb9b1ef355255ade81",
    ),
    (
        "tokenizer_config.json",
        "994f46754c5bf4014f1aa92d34b1374319c3a6b3f702105cd5b742beaecd18ce",
    ),
    (
        "tokenizer.json",
        "847bbeab6174d66a88898f729d52fa8d355fafe1bea101cf960dd404581df70e",
    ),
    (
        "vocab.json",
        "9e7f63c2d15d666b52e21d250d2e513b87c9b713cfa6987a82ed89e5e6e50655",
    ),
)

MAEST_PREPROCESSING = "shared-mono/maest-16khz-30s-three-windows-v1"
MERT_PREPROCESSING = "shared-mono/mert-24khz-interior-windows-v1"
MUQ_PREPROCESSING = "shared-mono/muq-24khz-float32-interior-windows-v1"
CLAP_PREPROCESSING = "shared-mono/clap-48khz-10s-repeatpad-v1"

MAEST_EMBEDDING_DIM = 768
MERT_EMBEDDING_DIM = 768
MUQ_EMBEDDING_DIM = 1024
CLAP_EMBEDDING_DIM = 512


EmbeddingNormalization = Literal["l2", "none"]


@dataclass(frozen=True, slots=True)
class EmbeddingFamilySpec:
    dimension: int
    normalization: EmbeddingNormalization


CURRENT_EMBEDDING_SPECS: Mapping[str, EmbeddingFamilySpec] = MappingProxyType(
    {
        "maest": EmbeddingFamilySpec(MAEST_EMBEDDING_DIM, "l2"),
        "mert": EmbeddingFamilySpec(MERT_EMBEDDING_DIM, "l2"),
        "muq": EmbeddingFamilySpec(MUQ_EMBEDDING_DIM, "l2"),
        "clap": EmbeddingFamilySpec(CLAP_EMBEDDING_DIM, "l2"),
    }
)


def current_embedding_spec(family: str) -> EmbeddingFamilySpec:
    clean_family = _required_text(family, "family").lower()
    try:
        return CURRENT_EMBEDDING_SPECS[clean_family]
    except KeyError as error:
        raise ValueError(
            f"unsupported embedding family: {clean_family!r}"
        ) from error


_ML_PARAMETER_DEFAULTS: dict[str, Mapping[str, object]] = {
    "maest": {
        "adapter_revision": MAEST_ADAPTER_REVISION,
        "dtype": "float32",
        "device_precision": "float32-eval",
        "checkpoint_release": "v0.0.0-beta",
        "checkpoint_filename": "discogs-maest-30s-pw-129e-519l-swa.ckpt",
    },
    "mert": {
        "adapter_revision": MERT_ADAPTER_REVISION,
        "dtype": "float32",
        "device_precision": "float32-eval-no-autocast",
        "checkpoint_filename": "pytorch_model.bin",
        "snapshot_files": (
            "config.json",
            "configuration_MERT.py",
            "modeling_MERT.py",
            "preprocessor_config.json",
            "pytorch_model.bin",
        ),
        "snapshot_sha256": MERT_SNAPSHOT_SHA256,
    },
    "muq": {
        "adapter_revision": MUQ_ADAPTER_REVISION,
        "dtype": "float32",
        "device_precision": "float32-eval-no-autocast-no-compile",
        "checkpoint_filename": "model.safetensors",
        "snapshot_files": ("config.json", "model.safetensors"),
        "snapshot_sha256": MUQ_SNAPSHOT_SHA256,
    },
    "clap": {
        "adapter_revision": CLAP_ADAPTER_REVISION,
        "dtype": "float32",
        "device_precision": "fp32-eval",
        "checkpoint_filename": "music_audioset_epoch_15_esc_90.14.pt",
        "text_model_name": CLAP_TEXT_MODEL_NAME,
        "text_model_revision": CLAP_TEXT_MODEL_REVISION,
        "text_snapshot_files": tuple(
            file_name for file_name, _digest in CLAP_TEXT_SNAPSHOT_SHA256
        ),
        "text_snapshot_sha256": CLAP_TEXT_SNAPSHOT_SHA256,
    },
}

_ML_CANONICAL_RUNTIME_PARAMETERS: dict[
    tuple[str, str], Mapping[str, object]
] = {
    ("maest", "analysis"): {
        "sample_rate_hz": 16_000,
        "input_seconds": 30.0,
        "analysis_window_positions": (0.2, 0.5, 0.8),
        "channel_downmix": "arithmetic-mean",
        "decoder": "shared-load-audio-mono-v1",
        "resampler": "torchaudio",
        "window_selection": "structure-aware-main-range-centered-20-50-80",
        "window_context": "sonara-current-generation-optional",
        "window_fallback": "main-range->non-silent-range->full-duration",
        "window_dedup_tolerance_seconds": 1.0,
        "short_audio": "right-zero-pad-to-30s",
        "model_input": "raw-waveform-melspectrogram-input-false",
        "score_activation": "sigmoid-logits",
        "score_pooling": "window-mean-then-top-k",
    },
    ("maest", "embedding"): {
        "sample_rate_hz": 16_000,
        "input_seconds": 30.0,
        "analysis_window_positions": (0.2, 0.5, 0.8),
        "pooling": "distilled-token-mean+window-mean+l2",
        "channel_downmix": "arithmetic-mean",
        "decoder": "shared-load-audio-mono-v1",
        "resampler": "torchaudio",
        "window_selection": "structure-aware-main-range-centered-20-50-80",
        "window_context": "sonara-current-generation-optional",
        "window_fallback": "main-range->non-silent-range->full-duration",
        "window_dedup_tolerance_seconds": 1.0,
        "short_audio": "right-zero-pad-to-30s",
        "model_input": "raw-waveform-melspectrogram-input-false",
        "score_activation": "sigmoid-logits",
        "score_pooling": "window-mean-then-top-k",
    },
    ("mert", "embedding"): {
        "sample_rate_hz": 24_000,
        "window_seconds": 5.0,
        "max_windows": 5,
        "hidden_layers": (9, 10, 11, 12),
        "pooling": "last-4-layer-mean+masked-time-mean+window-mean+l2",
        "channel_downmix": "arithmetic-mean",
        "decoder": "shared-load-audio-mono-v1",
        "window_selection": "10%-90%-interior-evenly-spaced-rounded",
        "short_audio": "single-variable-length-window",
        "processor_normalization": "wav2vec2-do-normalize",
        "processor_padding": "right-zero-with-attention-mask",
    },
    ("muq", "embedding"): {
        "sample_rate_hz": 24_000,
        "window_seconds": 10.0,
        "max_windows": 5,
        "pooling": "last-hidden-time-mean+per-window-l2+window-mean+l2",
        "channel_downmix": "arithmetic-mean",
        "decoder": "shared-load-audio-mono-v1",
        "resampler": "torchaudio",
        "window_selection": "10%-90%-interior-evenly-spaced-rounded",
        "short_audio": "right-zero-pad-to-window",
    },
    ("clap", "embedding"): {
        "sample_rate_hz": 48_000,
        "window_seconds": 10.0,
        "max_windows": 5,
        "pooling": "clap-audio+per-window-l2+window-mean+l2",
        "amodel": "HTSAT-base",
        "tmodel": "roberta",
        "enable_fusion": False,
        "channel_downmix": "arithmetic-mean",
        "decoder": "shared-load-audio-mono-v1",
        "resampler": "torchaudio",
        "window_selection": "10%-90%-interior-evenly-spaced-rounded",
        "short_audio": "repeat-whole-window-then-right-zero-pad",
        "input_quantization": "laion-clap-float32-int16-float32",
        "text_model_class": "RobertaModel",
        "text_tokenizer_class": "RobertaTokenizer",
        "text_loader_policy": "verified-private-snapshot-local-files-only",
    },
}

_EMBEDDING_DIM_BY_FAMILY = {
    family: spec.dimension
    for family, spec in CURRENT_EMBEDDING_SPECS.items()
    if family != "sonara"
}
_REQUIRED_PARAMETER_KEYS = {
    ("maest", "analysis"): frozenset(
        {
            "adapter_revision",
            "sample_rate_hz",
            "input_seconds",
            "analysis_window_positions",
            "top_k",
            "dtype",
            "device_precision",
            "checkpoint_release",
            "checkpoint_filename",
        }
    ),
    ("maest", "embedding"): frozenset(
        {
            "adapter_revision",
            "sample_rate_hz",
            "input_seconds",
            "analysis_window_positions",
            "pooling",
            "dtype",
            "device_precision",
            "checkpoint_release",
            "checkpoint_filename",
        }
    ),
    ("mert", "embedding"): frozenset(
        {
            "adapter_revision",
            "sample_rate_hz",
            "window_seconds",
            "max_windows",
            "hidden_layers",
            "pooling",
            "dtype",
            "device_precision",
            "model_revision",
            "remote_code_revision",
            "checkpoint_filename",
            "snapshot_files",
            "snapshot_sha256",
        }
    ),
    ("muq", "embedding"): frozenset(
        {
            "adapter_revision",
            "sample_rate_hz",
            "window_seconds",
            "max_windows",
            "pooling",
            "dtype",
            "device_precision",
            "model_revision",
            "checkpoint_filename",
            "snapshot_files",
            "snapshot_sha256",
        }
    ),
    ("clap", "embedding"): frozenset(
        {
            "adapter_revision",
            "sample_rate_hz",
            "window_seconds",
            "max_windows",
            "pooling",
            "amodel",
            "tmodel",
            "enable_fusion",
            "dtype",
            "device_precision",
            "model_revision",
            "checkpoint_filename",
            "text_model_name",
            "text_model_revision",
            "text_snapshot_files",
            "text_snapshot_sha256",
        }
    ),
}
class StaleAnalysisTargetError(RuntimeError):
    """Raised when a write target no longer names the current track content."""


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a finite number") from error
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    return number


def _positive_number(value: object, field_name: str) -> float:
    number = _finite_number(value, field_name)
    if number <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return number


def _merge_parameters(
    reserved: Mapping[str, object],
    extras: Mapping[str, object] | None,
) -> dict[str, object]:
    extra_values = dict(extras or {})
    collisions = sorted(set(reserved).intersection(extra_values))
    if collisions:
        raise ValueError(
            "parameters must not override reserved factory fields; "
            f"collisions={collisions}"
        )
    return {**reserved, **extra_values}


def _with_ml_runtime_identity(
    family: Literal["maest", "mert", "muq", "clap"],
    model_version: str,
    parameters: Mapping[str, object],
) -> dict[str, object]:
    defaults = dict(_ML_PARAMETER_DEFAULTS[family])
    if family in {"mert", "muq", "clap"}:
        defaults["model_revision"] = model_version
    if family == "mert":
        defaults["remote_code_revision"] = model_version
    return {**defaults, **parameters}


def _validate_window_ratios(value: object, field_name: str) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray, memoryview),
    ):
        raise ValueError(f"{field_name} must be a non-empty sequence")
    ratios = tuple(_finite_number(item, f"{field_name}[]") for item in value)
    if not ratios:
        raise ValueError(f"{field_name} must not be empty")
    if any(ratio < 0.0 or ratio > 1.0 for ratio in ratios):
        raise ValueError(f"{field_name} values must be between 0 and 1")
    return ratios


def _validate_positive_int_sequence(
    value: object,
    field_name: str,
) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray, memoryview),
    ):
        raise ValueError(f"{field_name} must be a non-empty sequence")
    values = tuple(_positive_int(item, f"{field_name}[]") for item in value)
    if not values:
        raise ValueError(f"{field_name} must not be empty")
    return values


def _readonly_float32_vector(
    value: Sequence[float] | np.ndarray,
    *,
    family: str,
) -> np.ndarray:
    spec = current_embedding_spec(family)
    expected_dim = spec.dimension
    vector = np.asarray(value, dtype="<f4")
    if vector.ndim != 1 or vector.shape != (expected_dim,):
        raise ValueError(
            f"embedding shape {vector.shape} does not match "
            f"{family} dimension {expected_dim}"
        )
    if not bool(np.all(np.isfinite(vector))):
        raise ValueError("embedding contains non-finite values")
    if spec.normalization == "l2":
        norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
        if not math.isfinite(norm) or not np.isclose(
            norm,
            1.0,
            rtol=1e-4,
            atol=1e-5,
        ):
            raise ValueError("l2 embedding must be unit-normalized")
    result = np.ascontiguousarray(vector, dtype="<f4").copy()
    result.setflags(write=False)
    return result


def _validate_short_float_blob(blob: bytes, *, dim: int, field_name: str) -> None:
    if not isinstance(blob, bytes) or len(blob) != dim * 4:
        raise ValueError(f"{field_name} must contain exactly {dim} float32-le values")
    vector = np.frombuffer(blob, dtype="<f4")
    if vector.shape != (dim,) or not bool(np.all(np.isfinite(vector))):
        raise ValueError(f"{field_name} must contain only finite float32-le values")


def _embedding_output(
    *,
    family: Literal["maest", "mert", "muq", "clap"],
    model_name: str,
    model_version: str,
    checkpoint_id: str,
    preprocessing: str,
    parameters: Mapping[str, object],
) -> "AnalysisOutput":
    del model_name, model_version, checkpoint_id, preprocessing, parameters
    return AnalysisOutput(
        analysis_family=family,
        output_kind="embedding",
    )


def maest_analysis_output(
    *,
    model_version: str,
    checkpoint_id: str,
    preprocessing: str,
    sample_rate_hz: int,
    input_seconds: float,
    analysis_window_positions: Sequence[float],
    top_k: int,
    model_name: str = MAEST_MODEL_NAME,
    parameters: Mapping[str, object] | None = None,
) -> "AnalysisOutput":
    positions = _validate_window_ratios(
        analysis_window_positions,
        "analysis_window_positions",
    )
    reserved: dict[str, object] = {
        "sample_rate_hz": _positive_int(sample_rate_hz, "sample_rate_hz"),
        "input_seconds": _positive_number(input_seconds, "input_seconds"),
        "analysis_window_positions": positions,
        "top_k": _positive_int(top_k, "top_k"),
    }
    values = _with_ml_runtime_identity(
        "maest",
        model_version,
        _merge_parameters(reserved, parameters),
    )
    del model_name, checkpoint_id, preprocessing, values
    return AnalysisOutput(
        analysis_family="maest",
        output_kind="analysis",
    )


def maest_embedding_output(
    *,
    model_version: str,
    checkpoint_id: str,
    preprocessing: str,
    sample_rate_hz: int,
    input_seconds: float,
    analysis_window_positions: Sequence[float],
    pooling: str,
    model_name: str = MAEST_MODEL_NAME,
    parameters: Mapping[str, object] | None = None,
) -> "AnalysisOutput":
    reserved: dict[str, object] = {
        "sample_rate_hz": _positive_int(sample_rate_hz, "sample_rate_hz"),
        "input_seconds": _positive_number(input_seconds, "input_seconds"),
        "analysis_window_positions": _validate_window_ratios(
            analysis_window_positions,
            "analysis_window_positions",
        ),
        "pooling": _required_text(pooling, "pooling"),
    }
    values = _with_ml_runtime_identity(
        "maest",
        model_version,
        _merge_parameters(reserved, parameters),
    )
    return _embedding_output(
        family="maest",
        model_name=model_name,
        model_version=model_version,
        checkpoint_id=checkpoint_id,
        preprocessing=preprocessing,
        parameters=values,
    )


def mert_embedding_output(
    *,
    model_version: str,
    checkpoint_id: str,
    preprocessing: str,
    sample_rate_hz: int,
    window_seconds: float,
    max_windows: int,
    hidden_layers: Sequence[int],
    pooling: str,
    model_name: str = MERT_MODEL_NAME,
    parameters: Mapping[str, object] | None = None,
) -> "AnalysisOutput":
    layers = _validate_positive_int_sequence(
        hidden_layers,
        "hidden_layers",
    )
    reserved: dict[str, object] = {
        "sample_rate_hz": _positive_int(sample_rate_hz, "sample_rate_hz"),
        "window_seconds": _positive_number(
            window_seconds,
            "window_seconds",
        ),
        "max_windows": _positive_int(max_windows, "max_windows"),
        "hidden_layers": layers,
        "pooling": _required_text(pooling, "pooling"),
    }
    values = _with_ml_runtime_identity(
        "mert",
        model_version,
        _merge_parameters(reserved, parameters),
    )
    return _embedding_output(
        family="mert",
        model_name=model_name,
        model_version=model_version,
        checkpoint_id=checkpoint_id,
        preprocessing=preprocessing,
        parameters=values,
    )


def muq_embedding_output(
    *,
    model_version: str,
    checkpoint_id: str,
    preprocessing: str,
    sample_rate_hz: int,
    window_seconds: float,
    max_windows: int,
    pooling: str,
    dtype: str,
    model_name: str = MUQ_MODEL_NAME,
    parameters: Mapping[str, object] | None = None,
) -> "AnalysisOutput":
    if sample_rate_hz != 24_000:
        raise ValueError("MuQ sample_rate_hz must be 24000")
    if dtype != "float32":
        raise ValueError("MuQ dtype must be 'float32'")
    reserved: dict[str, object] = {
        "sample_rate_hz": _positive_int(sample_rate_hz, "sample_rate_hz"),
        "window_seconds": _positive_number(
            window_seconds,
            "window_seconds",
        ),
        "max_windows": _positive_int(max_windows, "max_windows"),
        "pooling": _required_text(pooling, "pooling"),
        "dtype": dtype,
    }
    values = _with_ml_runtime_identity(
        "muq",
        model_version,
        _merge_parameters(reserved, parameters),
    )
    return _embedding_output(
        family="muq",
        model_name=model_name,
        model_version=model_version,
        checkpoint_id=checkpoint_id,
        preprocessing=preprocessing,
        parameters=values,
    )


def clap_embedding_output(
    *,
    model_version: str,
    checkpoint_id: str,
    preprocessing: str,
    sample_rate_hz: int,
    window_seconds: float,
    max_windows: int,
    pooling: str,
    amodel: str,
    enable_fusion: bool,
    model_name: str = CLAP_MODEL_NAME,
    parameters: Mapping[str, object] | None = None,
) -> "AnalysisOutput":
    if not isinstance(enable_fusion, bool):
        raise ValueError("enable_fusion must be a boolean")
    reserved: dict[str, object] = {
        "sample_rate_hz": _positive_int(sample_rate_hz, "sample_rate_hz"),
        "window_seconds": _positive_number(
            window_seconds,
            "window_seconds",
        ),
        "max_windows": _positive_int(max_windows, "max_windows"),
        "pooling": _required_text(pooling, "pooling"),
        "amodel": _required_text(amodel, "amodel"),
        "enable_fusion": enable_fusion,
    }
    values = _with_ml_runtime_identity(
        "clap",
        model_version,
        _merge_parameters(reserved, parameters),
    )
    return _embedding_output(
        family="clap",
        model_name=model_name,
        model_version=model_version,
        checkpoint_id=checkpoint_id,
        preprocessing=preprocessing,
        parameters=values,
    )


@dataclass(frozen=True)
class AnalysisTarget:
    catalog_uuid: str
    track_id: int
    track_uuid: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "catalog_uuid",
            _required_text(self.catalog_uuid, "catalog_uuid"),
        )
        object.__setattr__(
            self,
            "track_id",
            _positive_int(self.track_id, "track_id"),
        )
        object.__setattr__(
            self,
            "track_uuid",
            _required_text(self.track_uuid, "track_uuid"),
        )


@dataclass(frozen=True, slots=True)
class AnalysisOutput:
    analysis_family: str
    output_kind: str

    def __post_init__(self) -> None:
        family = _required_text(self.analysis_family, "analysis_family").lower()
        kind = _required_text(self.output_kind, "output_kind").lower()
        supported_kinds = OUTPUT_KINDS_BY_FAMILY.get(family)
        if supported_kinds is None:
            raise ValueError(f"unsupported analysis_family: {family!r}")
        if kind not in supported_kinds:
            raise ValueError(
                f"unsupported output_kind {kind!r} "
                f"for analysis_family {family!r}"
            )
        object.__setattr__(self, "analysis_family", family)
        object.__setattr__(self, "output_kind", kind)

    @property
    def key(self) -> tuple[str, str]:
        return self.analysis_family, self.output_kind


@dataclass(frozen=True)
class AnalysisCandidate:
    target: AnalysisTarget
    file_path: str
    file_size_bytes: int
    file_modified_ns: int
    missing_outputs: tuple[AnalysisOutput, ...]
    maest_window_context: MaestWindowContext | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "file_path",
            _required_text(self.file_path, "file_path"),
        )
        if (
            isinstance(self.file_size_bytes, bool)
            or not isinstance(self.file_size_bytes, int)
            or self.file_size_bytes < 0
        ):
            raise ValueError("file_size_bytes must be a non-negative integer")
        if (
            isinstance(self.file_modified_ns, bool)
            or not isinstance(self.file_modified_ns, int)
            or self.file_modified_ns < 0
        ):
            raise ValueError("file_modified_ns must be a non-negative integer")
        missing = tuple(self.missing_outputs)
        if not missing:
            raise ValueError("analysis candidate must have at least one missing output")
        object.__setattr__(self, "missing_outputs", missing)
        if (
            self.maest_window_context is not None
            and not isinstance(self.maest_window_context, MaestWindowContext)
        ):
            raise TypeError(
                "maest_window_context must be a MaestWindowContext or None"
            )


@dataclass(frozen=True, slots=True)
class EmbeddingOutput:
    family: str
    vector: Sequence[float] | np.ndarray
    analyzed_at: str

    def __post_init__(self) -> None:
        family = _required_text(self.family, "family").lower()
        if family not in {*_EMBEDDING_DIM_BY_FAMILY, "sonara"}:
            raise ValueError(f"unsupported embedding family: {family!r}")
        object.__setattr__(self, "family", family)
        object.__setattr__(
            self,
            "analyzed_at",
            _required_text(self.analyzed_at, "analyzed_at"),
        )
        object.__setattr__(
            self,
            "vector",
            _readonly_float32_vector(self.vector, family=family),
        )


@dataclass(frozen=True)
class SonaraWrite:
    target: AnalysisTarget
    core: SonaraRow

    def __post_init__(self) -> None:
        if self.core.track_id != self.target.track_id:
            raise ValueError("SONARA Core track_id does not match target")
        _required_text(self.core.analyzed_at, "core.analyzed_at")
        _validate_short_float_blob(
            self.core.mfcc_mean_blob,
            dim=13,
            field_name="core.mfcc_mean_blob",
        )
        _validate_short_float_blob(
            self.core.chroma_mean_blob,
            dim=12,
            field_name="core.chroma_mean_blob",
        )
        _validate_short_float_blob(
            self.core.spectral_contrast_mean_blob,
            dim=7,
            field_name="core.spectral_contrast_mean_blob",
        )
    @property
    def outputs(self) -> tuple[AnalysisOutput, ...]:
        return (AnalysisOutput("sonara", "core"),)


@dataclass(frozen=True)
class MaestGenreScore:
    label: str
    score: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _required_text(self.label, "label"))
        score = _finite_number(self.score, "score")
        if not 0.0 <= score <= 1.0:
            raise ValueError("score must be between 0 and 1")
        object.__setattr__(self, "score", score)


@dataclass(frozen=True)
class MaestWrite:
    target: AnalysisTarget
    genres: tuple[MaestGenreScore, ...]
    syncopated_rhythm: bool | None
    analyzed_at: str
    embedding: EmbeddingOutput | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "genres", tuple(self.genres))
        if self.syncopated_rhythm is not None and not isinstance(
            self.syncopated_rhythm,
            bool,
        ):
            raise ValueError("syncopated_rhythm must be bool or None")
        object.__setattr__(
            self,
            "analyzed_at",
            _required_text(self.analyzed_at, "analyzed_at"),
        )
        if self.embedding is not None and self.embedding.family != "maest":
            raise ValueError("embedding must use family='maest'")

    @property
    def outputs(self) -> tuple[AnalysisOutput, ...]:
        outputs = [AnalysisOutput("maest", "analysis")]
        if self.embedding is not None:
            outputs.append(AnalysisOutput("maest", "embedding"))
        return tuple(outputs)

    @property
    def genres_json(self) -> str:
        return json.dumps(
            [{"label": genre.label, "score": genre.score} for genre in self.genres],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )


@dataclass(frozen=True)
class EmbeddingWrite:
    target: AnalysisTarget
    output: EmbeddingOutput

    def __post_init__(self) -> None:
        if self.output.family not in {"mert", "muq", "clap"}:
            raise ValueError(
                "standalone embedding writes support only MERT, MuQ, or CLAP"
            )


@dataclass(frozen=True)
class AnalysisWriteResult:
    target: AnalysisTarget
    written_outputs: tuple[AnalysisOutput, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class AnalysisVectorRow:
    target: AnalysisTarget
    output: AnalysisOutput
    vector: np.ndarray


@dataclass(frozen=True)
class SonaraFeatureRow:
    target: AnalysisTarget
    output: AnalysisOutput
    values: Mapping[str, object]


@dataclass(frozen=True)
class ClassifierSpecification:
    classifier_key: str
    feature_set: str
    feature_names: tuple[str, ...]
    required_outputs: tuple[AnalysisOutput, ...]
    label_order: tuple[str, ...]
    positive_label: str

    def __post_init__(self) -> None:
        for field_name in (
            "classifier_key",
            "feature_set",
            "positive_label",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name),
            )
        feature_names = tuple(
            _required_text(value, "feature_names[]") for value in self.feature_names
        )
        if not feature_names:
            raise ValueError("feature_names must not be empty")
        if len(set(feature_names)) != len(feature_names):
            raise ValueError("feature_names must not contain duplicates")
        object.__setattr__(self, "feature_names", feature_names)
        outputs = tuple(self.required_outputs)
        if not outputs:
            raise ValueError("required_outputs must not be empty")
        keys = [output.key for output in outputs]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "required_outputs must contain at most one entry per output"
            )
        object.__setattr__(self, "required_outputs", outputs)
        labels = tuple(
            _required_text(value, "label_order[]") for value in self.label_order
        )
        if not labels:
            raise ValueError("label_order must not be empty")
        if len(set(labels)) != len(labels):
            raise ValueError("label_order must not contain duplicates")
        if self.positive_label not in labels:
            raise ValueError("positive_label must be present in label_order")
        object.__setattr__(self, "label_order", labels)

@dataclass(frozen=True)
class ClassifierCandidate:
    target: AnalysisTarget
    file_path: str
    file_size_bytes: int
    file_modified_ns: int


@dataclass(frozen=True)
class ClassifierFeatureRow:
    target: AnalysisTarget
    specification: ClassifierSpecification
    vector: np.ndarray


@dataclass(frozen=True)
class ClassifierScoreWrite:
    target: AnalysisTarget
    specification: ClassifierSpecification
    score: ClassifierScoreRecord

    def __post_init__(self) -> None:
        if not isinstance(self.specification, ClassifierSpecification):
            raise TypeError("specification must be a ClassifierSpecification")
        if self.score.track_id != self.target.track_id:
            raise ValueError("classifier score track_id does not match target")
        if self.score.track_uuid != self.target.track_uuid:
            raise ValueError("classifier score track_uuid does not match target")
        expected_identity = (
            self.specification.classifier_key,
            self.specification.feature_set,
            self.specification.positive_label,
        )
        score_identity = (
            self.score.classifier_key,
            self.score.feature_set,
            self.score.positive_label,
        )
        if score_identity != expected_identity:
            raise ValueError(
                "classifier score identity does not match its specification"
            )
        expected_feature_names_json = json.dumps(
            list(self.specification.feature_names),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if self.score.feature_names_json != expected_feature_names_json:
            raise ValueError(
                "classifier score feature_names_json does not match its specification"
            )


@dataclass(frozen=True)
class AnalysisResetResult:
    feature_rows_deleted: int = 0
    embedding_rows_deleted: int = 0
    classifier_rows_deleted: int = 0
