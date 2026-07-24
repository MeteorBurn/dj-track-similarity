"""Typed v7 analysis repository contracts.

The models in this module deliberately carry the complete Core/Artifacts track
identity.  A numeric ``track_id`` alone is not a safe write target because it
does not distinguish another library catalog, a replaced track UUID, or a
newer content generation.
"""

from __future__ import annotations

import hashlib
from itertools import combinations
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

import numpy as np

from .analysis_contracts import FLOAT32_LE_ENCODING, ContractIdentity
from .db_schema_v7 import ClassifierScoreV7, SonaraRowV7
from .sonara_contract import (
    SONARA_ANALYSIS_HOP_SAMPLES,
    SONARA_EXPECTED_SCHEMA_VERSION,
    SONARA_EXPECTED_VERSION,
    SONARA_PROJECT_FEATURE_REVISION,
    SONARA_UNIT_INTERVAL_CLAMP_EPSILON,
    SONARA_UNIT_INTERVAL_CLAMP_FIELDS,
    SONARA_UNIT_INTERVAL_CLAMP_POLICY,
)


ACTIVE_CONTRACT_SETTING_PREFIX = "analysis.active_contract"
SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY = "sonara.active_release_hash"

MAEST_MODEL_NAME = "discogs-maest-30s-pw-129e-519l"
MERT_MODEL_NAME = "m-a-p/MERT-v1-95M"
MUQ_MODEL_NAME = "OpenMuQ/MuQ-large-msd-iter"
CLAP_MODEL_NAME = "lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt"
CLAP_TEXT_MODEL_NAME = "roberta-base"

MAEST_ADAPTER_REVISION = "maest-adapter-v1"
MERT_ADAPTER_REVISION = "mert-adapter-v1"
MUQ_ADAPTER_REVISION = "muq-adapter-v1"
CLAP_ADAPTER_REVISION = "clap-adapter-v2"

MAEST_MODEL_VERSION = "maest-infer==0.1.0;release=v0.0.0-beta"
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

_HUGGINGFACE_HUB_PACKAGE = "huggingface-hub==1.22.0"
_ML_PARAMETER_DEFAULTS: dict[str, Mapping[str, object]] = {
    "maest": {
        "adapter_revision": MAEST_ADAPTER_REVISION,
        "dtype": "float32",
        "device_precision": "float32-eval",
        "loader_package": "maest-infer==0.1.0",
        "package_wheel_sha256": (
            "1638ad5b6590ffecadbd9b71f7d4f0e0a9beb5d3862dde0ee447323a1e693e6e"
        ),
        "checkpoint_release": "v0.0.0-beta",
        "checkpoint_filename": "discogs-maest-30s-pw-129e-519l-swa.ckpt",
    },
    "mert": {
        "adapter_revision": MERT_ADAPTER_REVISION,
        "dtype": "float32",
        "device_precision": "float32-eval-no-autocast",
        "loader_package": "transformers==5.13.0",
        "hub_package": _HUGGINGFACE_HUB_PACKAGE,
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
        "loader_package": "muq==0.1.0",
        "hub_package": _HUGGINGFACE_HUB_PACKAGE,
        "checkpoint_filename": "model.safetensors",
        "snapshot_files": ("config.json", "model.safetensors"),
        "snapshot_sha256": MUQ_SNAPSHOT_SHA256,
    },
    "clap": {
        "adapter_revision": CLAP_ADAPTER_REVISION,
        "dtype": "float32",
        "device_precision": "fp32-eval",
        "loader_package": "laion-clap==1.1.7",
        "text_loader_package": "transformers==5.13.0",
        "hub_package": _HUGGINGFACE_HUB_PACKAGE,
        "checkpoint_filename": "music_audioset_epoch_15_esc_90.14.pt",
        "text_model_name": CLAP_TEXT_MODEL_NAME,
        "text_model_revision": CLAP_TEXT_MODEL_REVISION,
        "text_snapshot_files": tuple(
            file_name for file_name, _digest in CLAP_TEXT_SNAPSHOT_SHA256
        ),
        "text_snapshot_sha256": CLAP_TEXT_SNAPSHOT_SHA256,
    },
}

_ML_CANONICAL_CONTRACT_FIELDS: dict[str, Mapping[str, object]] = {
    "maest": {
        "model_name": MAEST_MODEL_NAME,
        "model_version": MAEST_MODEL_VERSION,
        "checkpoint_id": MAEST_CHECKPOINT_ID,
        "preprocessing": MAEST_PREPROCESSING,
    },
    "mert": {
        "model_name": MERT_MODEL_NAME,
        "model_version": MERT_MODEL_REVISION,
        "checkpoint_id": MERT_CHECKPOINT_ID,
        "preprocessing": MERT_PREPROCESSING,
    },
    "muq": {
        "model_name": MUQ_MODEL_NAME,
        "model_version": MUQ_MODEL_REVISION,
        "checkpoint_id": MUQ_CHECKPOINT_ID,
        "preprocessing": MUQ_PREPROCESSING,
    },
    "clap": {
        "model_name": CLAP_MODEL_NAME,
        "model_version": CLAP_MODEL_REVISION,
        "checkpoint_id": CLAP_CHECKPOINT_ID,
        "preprocessing": CLAP_PREPROCESSING,
    },
}

_ML_CANONICAL_RUNTIME_PARAMETERS: dict[
    tuple[str, str], Mapping[str, object]
] = {
    ("maest", "analysis"): {
        "sample_rate_hz": 16_000,
        "input_seconds": 30.0,
        "analysis_offset_seconds": 60.0,
        "analysis_window_ratios": (0.38, 0.72),
        "channel_downmix": "arithmetic-mean",
        "decoder": "shared-load-audio-mono-v1",
        "resampler": "torchaudio",
        "window_selection": (
            "offset60s+duration-ratios-0.38,0.72-clamped-dedup-1s"
        ),
        "short_audio": "right-zero-pad-to-30s",
        "model_input": "raw-waveform-melspectrogram-input-false",
        "score_activation": "sigmoid-logits",
        "score_pooling": "window-mean-then-top-k",
    },
    ("maest", "embedding"): {
        "sample_rate_hz": 16_000,
        "input_seconds": 30.0,
        "analysis_offset_seconds": 60.0,
        "analysis_window_ratios": (0.38, 0.72),
        "pooling": "distilled-token-mean+window-mean+l2",
        "channel_downmix": "arithmetic-mean",
        "decoder": "shared-load-audio-mono-v1",
        "resampler": "torchaudio",
        "window_selection": (
            "offset60s+duration-ratios-0.38,0.72-clamped-dedup-1s"
        ),
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
    "maest": MAEST_EMBEDDING_DIM,
    "mert": MERT_EMBEDDING_DIM,
    "muq": MUQ_EMBEDDING_DIM,
    "clap": CLAP_EMBEDDING_DIM,
}
_REQUIRED_PARAMETER_KEYS = {
    ("maest", "analysis"): frozenset(
        {
            "adapter_revision",
            "sample_rate_hz",
            "input_seconds",
            "analysis_offset_seconds",
            "analysis_window_ratios",
            "top_k",
            "dtype",
            "device_precision",
            "loader_package",
            "package_wheel_sha256",
            "checkpoint_release",
            "checkpoint_filename",
        }
    ),
    ("maest", "embedding"): frozenset(
        {
            "adapter_revision",
            "sample_rate_hz",
            "input_seconds",
            "analysis_offset_seconds",
            "analysis_window_ratios",
            "pooling",
            "dtype",
            "device_precision",
            "loader_package",
            "package_wheel_sha256",
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
            "loader_package",
            "hub_package",
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
            "loader_package",
            "hub_package",
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
            "loader_package",
            "text_loader_package",
            "hub_package",
            "text_model_name",
            "text_model_revision",
            "text_snapshot_files",
            "text_snapshot_sha256",
        }
    ),
}
_SONARA_REQUIRED_PARAMETER_KEYS = frozenset(
    {
        "identity_factory",
        "package_version",
        "package_build_id",
        "schema_version",
        "mode",
        "sample_rate_hz",
        "bpm_min",
        "bpm_max",
        "project_feature_revision",
        "decoder_backend",
        "execution_path",
        "analysis_hop_samples",
        "unit_interval_clamp_policy",
        "unit_interval_clamp_epsilon",
        "unit_interval_clamp_fields",
        "vocalness_model_selector",
        "vocalness_model_id",
        "vocalness_model_build_id",
        "requested_features",
    }
)


class StaleAnalysisTargetError(RuntimeError):
    """Raised when a write target no longer names the current track content."""


class InactiveAnalysisOutputError(RuntimeError):
    """Raised when a stale job tries to read or write a superseded contract."""


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


def _non_negative_number(value: object, field_name: str) -> float:
    number = _finite_number(value, field_name)
    if number < 0:
        raise ValueError(f"{field_name} must be non-negative")
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


def _parameter_positive_int(
    parameters: Mapping[str, object],
    key: str,
) -> int:
    return _positive_int(parameters.get(key), f"contract.parameters.{key}")


def _parameter_positive_number(
    parameters: Mapping[str, object],
    key: str,
) -> float:
    return _positive_number(
        parameters.get(key),
        f"contract.parameters.{key}",
    )


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


def _json_copy(
    value: object, *, expected: Literal["object", "array"], field_name: str
) -> object:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        decoded = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be finite JSON") from error
    expected_type = dict if expected == "object" else list
    if not isinstance(decoded, expected_type):
        raise ValueError(f"{field_name} must be a JSON {expected}")
    return decoded


def _readonly_float32_vector(
    value: Sequence[float] | np.ndarray,
    *,
    contract: ContractIdentity,
) -> np.ndarray:
    if contract.output_kind != "embedding":
        raise ValueError("vector output requires an embedding contract")
    vector = np.asarray(value, dtype="<f4")
    if vector.ndim != 1 or vector.shape != (contract.dim,):
        raise ValueError(
            f"embedding shape {vector.shape} does not match contract dim {contract.dim}"
        )
    if not bool(np.all(np.isfinite(vector))):
        raise ValueError("embedding contains non-finite values")
    if contract.normalization == "l2":
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


def _readonly_uint32_words(value: Sequence[int] | np.ndarray) -> np.ndarray:
    raw = np.asarray(value)
    if raw.ndim != 1:
        raise ValueError("fingerprint words must be one-dimensional")
    if raw.dtype.kind not in {"i", "u"}:
        raise ValueError("fingerprint words must be integers")
    if raw.size and (
        bool(np.any(raw < 0))
        or bool(np.any(raw.astype(object) > np.iinfo(np.uint32).max))
    ):
        raise ValueError("fingerprint words must fit uint32")
    words = np.ascontiguousarray(raw, dtype="<u4").copy()
    words.setflags(write=False)
    return words


def _validate_short_float_blob(blob: bytes, *, dim: int, field_name: str) -> None:
    if not isinstance(blob, bytes) or len(blob) != dim * 4:
        raise ValueError(f"{field_name} must contain exactly {dim} float32-le values")
    vector = np.frombuffer(blob, dtype="<f4")
    if vector.shape != (dim,) or not bool(np.all(np.isfinite(vector))):
        raise ValueError(f"{field_name} must contain only finite float32-le values")


def active_contract_setting_key(output: "AnalysisOutput") -> str:
    return (
        f"{ACTIVE_CONTRACT_SETTING_PREFIX}."
        f"{output.contract.analysis_family}.{output.contract.output_kind}"
    )


def validate_production_contract(contract: ContractIdentity) -> None:
    """Reject underspecified identities before they enter the active registry."""

    _required_text(contract.model_name, "contract.model_name")
    _required_text(contract.model_version, "contract.model_version")
    _required_text(contract.checkpoint_id, "contract.checkpoint_id")
    _required_text(contract.preprocessing, "contract.preprocessing")
    parameters = dict(contract.parameters)
    if not parameters:
        raise ValueError("contract.parameters must identify immutable runtime settings")

    if contract.analysis_family == "sonara":
        missing = sorted(_SONARA_REQUIRED_PARAMETER_KEYS - parameters.keys())
        if missing:
            raise ValueError(
                f"SONARA contract parameters are incomplete; missing={missing}"
            )
        if parameters.get("identity_factory") != "sonara-runtime-v1":
            raise ValueError(
                "SONARA contracts must be built by the sonara-runtime-v1 factory"
            )
        if (
            contract.release_hash is None
            or re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                contract.release_hash,
            )
            is None
        ):
            raise ValueError("SONARA release_hash must be a lowercase sha256 digest")
        if parameters.get("package_version") != SONARA_EXPECTED_VERSION:
            raise ValueError(
                f"SONARA package_version must be {SONARA_EXPECTED_VERSION!r}"
            )
        if contract.model_name != "sonara-playlist":
            raise ValueError("SONARA model_name must be 'sonara-playlist'")
        if contract.model_version != parameters.get("package_version"):
            raise ValueError("SONARA model_version must equal package_version")
        package_build_id = _required_text(
            parameters.get("package_build_id"),
            "contract.parameters.package_build_id",
        )
        if re.fullmatch(r"sha256:[0-9a-f]{64}", package_build_id) is None:
            raise ValueError(
                "SONARA package_build_id must be a lowercase sha256 digest"
            )
        if contract.checkpoint_id != package_build_id:
            raise ValueError("SONARA checkpoint_id must equal package_build_id")
        if (
            _parameter_positive_int(parameters, "schema_version")
            != SONARA_EXPECTED_SCHEMA_VERSION
        ):
            raise ValueError(
                f"SONARA schema_version must be {SONARA_EXPECTED_SCHEMA_VERSION}"
            )
        if parameters.get("mode") != "playlist":
            raise ValueError("SONARA mode must be 'playlist'")
        if _parameter_positive_int(parameters, "sample_rate_hz") != 22_050:
            raise ValueError("SONARA sample_rate_hz must be 22050")
        if _parameter_positive_int(parameters, "bpm_min") != 70:
            raise ValueError("SONARA bpm_min must be 70")
        if _parameter_positive_int(parameters, "bpm_max") != 180:
            raise ValueError("SONARA bpm_max must be 180")
        if (
            _parameter_positive_int(parameters, "project_feature_revision")
            != SONARA_PROJECT_FEATURE_REVISION
        ):
            raise ValueError(
                "SONARA project_feature_revision must be "
                f"{SONARA_PROJECT_FEATURE_REVISION}"
            )
        if parameters.get("decoder_backend") != "sonara-symphonia":
            raise ValueError("SONARA decoder_backend must be 'sonara-symphonia'")
        if parameters.get("execution_path") != "analyze_batch":
            raise ValueError("SONARA execution_path must be 'analyze_batch'")
        analysis_hop_samples = _parameter_positive_int(
            parameters,
            "analysis_hop_samples",
        )
        if analysis_hop_samples != SONARA_ANALYSIS_HOP_SAMPLES:
            raise ValueError(
                f"SONARA analysis_hop_samples must be {SONARA_ANALYSIS_HOP_SAMPLES}"
            )
        if (
            parameters.get("unit_interval_clamp_policy")
            != SONARA_UNIT_INTERVAL_CLAMP_POLICY
        ):
            raise ValueError(
                "SONARA unit_interval_clamp_policy must be "
                f"{SONARA_UNIT_INTERVAL_CLAMP_POLICY!r}"
            )
        unit_interval_clamp_epsilon = _finite_number(
            parameters.get("unit_interval_clamp_epsilon"),
            "contract.parameters.unit_interval_clamp_epsilon",
        )
        if unit_interval_clamp_epsilon != SONARA_UNIT_INTERVAL_CLAMP_EPSILON:
            raise ValueError(
                "SONARA unit_interval_clamp_epsilon must be "
                f"{SONARA_UNIT_INTERVAL_CLAMP_EPSILON}"
            )
        unit_interval_clamp_fields = parameters.get("unit_interval_clamp_fields")
        if not isinstance(unit_interval_clamp_fields, Sequence) or isinstance(
            unit_interval_clamp_fields,
            (str, bytes, bytearray, memoryview),
        ):
            raise ValueError("SONARA unit_interval_clamp_fields must be a sequence")
        if tuple(unit_interval_clamp_fields) != SONARA_UNIT_INTERVAL_CLAMP_FIELDS:
            raise ValueError(
                "SONARA unit_interval_clamp_fields must match the canonical "
                "sorted field-path list"
            )
        expected_preprocessing = (
            "sonara-symphonia/analyze_batch/playlist-sr22050-"
            f"hop{analysis_hop_samples}/"
            f"{SONARA_UNIT_INTERVAL_CLAMP_POLICY}-"
            f"epsilon{SONARA_UNIT_INTERVAL_CLAMP_EPSILON:g}"
        )
        if contract.preprocessing != expected_preprocessing:
            raise ValueError(
                "SONARA preprocessing identity does not match runtime settings"
            )
        if parameters.get("vocalness_model_selector") != "bundled":
            raise ValueError("SONARA vocalness_model_selector must be 'bundled'")
        _required_text(
            parameters.get("vocalness_model_id"),
            "contract.parameters.vocalness_model_id",
        )
        vocalness_build_id = _required_text(
            parameters.get("vocalness_model_build_id"),
            "contract.parameters.vocalness_model_build_id",
        )
        if (
            re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                vocalness_build_id,
            )
            is None
        ):
            raise ValueError(
                "SONARA vocalness_model_build_id must be a lowercase sha256 digest"
            )
        requested_features = parameters.get("requested_features")
        if not isinstance(requested_features, Sequence) or isinstance(
            requested_features,
            (str, bytes, bytearray, memoryview),
        ):
            raise ValueError("SONARA requested_features must be a non-empty sequence")
        if not tuple(requested_features) or any(
            not isinstance(feature, str) or not feature.strip()
            for feature in requested_features
        ):
            raise ValueError("SONARA requested_features must contain non-empty strings")
        feature_tuple = tuple(str(feature) for feature in requested_features)
        if feature_tuple != tuple(sorted(set(feature_tuple))):
            raise ValueError("SONARA requested_features must be sorted and unique")
        if contract.output_kind == "embedding":
            if contract.dim != 48:
                raise ValueError("SONARA similarity embedding dim must be 48")
            if contract.encoding != FLOAT32_LE_ENCODING:
                raise ValueError("SONARA similarity embedding must use float32-le")
            if contract.normalization != "none":
                raise ValueError(
                    "SONARA similarity embedding normalization must be none"
                )
            expected_embedding_parameters = {
                "embedding_version": 2,
                "embedding_dim": 48,
                "embedding_encoding": FLOAT32_LE_ENCODING,
                "embedding_normalization": "none",
            }
            for key, expected_value in expected_embedding_parameters.items():
                if parameters.get(key) != expected_value:
                    raise ValueError(f"SONARA {key} must be {expected_value!r}")
        elif contract.output_kind == "fingerprint":
            expected_fingerprint_parameters = {
                "fingerprint_version": 1,
                "fingerprint_encoding": "uint32-le",
                "fingerprint_byte_order": "little",
            }
            for key, expected_value in expected_fingerprint_parameters.items():
                if parameters.get(key) != expected_value:
                    raise ValueError(f"SONARA {key} must be {expected_value!r}")
        return

    required = _REQUIRED_PARAMETER_KEYS.get(
        (contract.analysis_family, contract.output_kind)
    )
    if required is None:
        raise ValueError(
            "unsupported production analysis contract "
            f"{contract.analysis_family}/{contract.output_kind}"
        )
    missing = sorted(required - parameters.keys())
    if missing:
        raise ValueError(f"contract parameters are incomplete; missing={missing}")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", contract.checkpoint_id) is None:
        raise ValueError(
            "production ML checkpoint_id must be a lowercase sha256 digest"
        )

    canonical_fields = _ML_CANONICAL_CONTRACT_FIELDS[contract.analysis_family]
    for field_name, expected_value in canonical_fields.items():
        actual_value = getattr(contract, field_name)
        if actual_value != expected_value:
            raise ValueError(
                f"{contract.analysis_family} {field_name} must be "
                f"{expected_value!r}"
            )

    expected_identity = _ML_PARAMETER_DEFAULTS[contract.analysis_family]
    for key, expected_value in expected_identity.items():
        if parameters.get(key) != expected_value:
            raise ValueError(
                f"{contract.analysis_family} {key} must be {expected_value!r}"
            )

    expected_parameters = {
        **expected_identity,
        **_ML_CANONICAL_RUNTIME_PARAMETERS[
            (contract.analysis_family, contract.output_kind)
        ],
    }
    if contract.analysis_family in {"mert", "muq", "clap"}:
        expected_parameters["model_revision"] = canonical_fields["model_version"]
    if contract.analysis_family == "mert":
        expected_parameters["remote_code_revision"] = canonical_fields[
            "model_version"
        ]
    dynamic_keys = (
        {"top_k"}
        if (contract.analysis_family, contract.output_kind)
        == ("maest", "analysis")
        else set()
    )
    expected_keys = set(expected_parameters).union(dynamic_keys)
    actual_keys = set(parameters)
    if actual_keys != expected_keys:
        missing_keys = sorted(expected_keys - actual_keys)
        unexpected_keys = sorted(actual_keys - expected_keys)
        raise ValueError(
            "production ML contract parameters must match the canonical "
            f"{contract.analysis_family}/{contract.output_kind} identity; "
            f"missing={missing_keys}, unexpected={unexpected_keys}"
        )
    for key, expected_value in expected_parameters.items():
        if parameters.get(key) != expected_value:
            raise ValueError(
                f"{contract.analysis_family} {key} must be {expected_value!r}"
            )

    if contract.output_kind == "embedding":
        expected_dim = _EMBEDDING_DIM_BY_FAMILY[contract.analysis_family]
        if contract.dim != expected_dim:
            raise ValueError(
                f"{contract.analysis_family} embedding dim must be {expected_dim}"
            )
        if contract.encoding != FLOAT32_LE_ENCODING:
            raise ValueError("production embeddings must use float32-le encoding")
        if contract.normalization != "l2":
            raise ValueError("production embeddings must use l2 normalization")

    sample_rate = _parameter_positive_int(parameters, "sample_rate_hz")
    expected_sample_rates = {
        "maest": 16_000,
        "mert": 24_000,
        "muq": 24_000,
        "clap": 48_000,
    }
    expected_sample_rate = expected_sample_rates[contract.analysis_family]
    if sample_rate != expected_sample_rate:
        raise ValueError(
            f"{contract.analysis_family} sample_rate_hz must be {expected_sample_rate}"
        )

    if contract.analysis_family == "maest":
        _parameter_positive_number(parameters, "input_seconds")
        _non_negative_number(
            parameters.get("analysis_offset_seconds"),
            "contract.parameters.analysis_offset_seconds",
        )
        _validate_window_ratios(
            parameters.get("analysis_window_ratios"),
            "contract.parameters.analysis_window_ratios",
        )
        if contract.output_kind == "analysis":
            _parameter_positive_int(parameters, "top_k")
        else:
            _required_text(
                parameters.get("pooling"),
                "contract.parameters.pooling",
            )
    elif contract.analysis_family == "mert":
        model_revision = _required_text(
            parameters.get("model_revision"),
            "contract.parameters.model_revision",
        )
        if re.fullmatch(r"[0-9a-f]{40}", model_revision) is None:
            raise ValueError("MERT model_revision must be a full lowercase commit SHA")
        if contract.model_version != model_revision:
            raise ValueError("MERT model_version must equal model_revision")
        if parameters.get("remote_code_revision") != model_revision:
            raise ValueError("MERT remote_code_revision must equal model_revision")
        _parameter_positive_number(parameters, "window_seconds")
        _parameter_positive_int(parameters, "max_windows")
        _validate_positive_int_sequence(
            parameters.get("hidden_layers"),
            "contract.parameters.hidden_layers",
        )
        _required_text(
            parameters.get("pooling"),
            "contract.parameters.pooling",
        )
    elif contract.analysis_family == "muq":
        model_revision = _required_text(
            parameters.get("model_revision"),
            "contract.parameters.model_revision",
        )
        if re.fullmatch(r"[0-9a-f]{40}", model_revision) is None:
            raise ValueError("MuQ model_revision must be a full lowercase commit SHA")
        if contract.model_version != model_revision:
            raise ValueError("MuQ model_version must equal model_revision")
        _parameter_positive_number(parameters, "window_seconds")
        _parameter_positive_int(parameters, "max_windows")
        _required_text(
            parameters.get("pooling"),
            "contract.parameters.pooling",
        )
        if parameters.get("dtype") != "float32":
            raise ValueError("MuQ dtype must be 'float32'")
    elif contract.analysis_family == "clap":
        model_revision = _required_text(
            parameters.get("model_revision"),
            "contract.parameters.model_revision",
        )
        if re.fullmatch(r"[0-9a-f]{40}", model_revision) is None:
            raise ValueError("CLAP model_revision must be a full lowercase commit SHA")
        if contract.model_version != model_revision:
            raise ValueError("CLAP model_version must equal model_revision")
        _parameter_positive_number(parameters, "window_seconds")
        _parameter_positive_int(parameters, "max_windows")
        _required_text(
            parameters.get("pooling"),
            "contract.parameters.pooling",
        )
        _required_text(
            parameters.get("amodel"),
            "contract.parameters.amodel",
        )
        if not isinstance(parameters.get("enable_fusion"), bool):
            raise ValueError("CLAP enable_fusion must be a boolean")


def _embedding_output(
    *,
    family: Literal["maest", "mert", "muq", "clap"],
    model_name: str,
    model_version: str,
    checkpoint_id: str,
    preprocessing: str,
    parameters: Mapping[str, object],
) -> "AnalysisOutput":
    expected_dim = _EMBEDDING_DIM_BY_FAMILY[family]
    output = AnalysisOutput(
        ContractIdentity(
            analysis_family=family,
            output_kind="embedding",
            model_name=model_name,
            model_version=model_version,
            dim=expected_dim,
            encoding=FLOAT32_LE_ENCODING,
            normalization="l2",
            checkpoint_id=checkpoint_id,
            preprocessing=preprocessing,
            parameters=parameters,
        )
    )
    validate_production_contract(output.contract)
    return output


def maest_analysis_output(
    *,
    model_version: str,
    checkpoint_id: str,
    preprocessing: str,
    sample_rate_hz: int,
    input_seconds: float,
    analysis_offset_seconds: float,
    analysis_window_ratios: Sequence[float],
    top_k: int,
    model_name: str = MAEST_MODEL_NAME,
    parameters: Mapping[str, object] | None = None,
) -> "AnalysisOutput":
    ratios = _validate_window_ratios(
        analysis_window_ratios,
        "analysis_window_ratios",
    )
    reserved: dict[str, object] = {
        "sample_rate_hz": _positive_int(sample_rate_hz, "sample_rate_hz"),
        "input_seconds": _positive_number(input_seconds, "input_seconds"),
        "analysis_offset_seconds": _non_negative_number(
            analysis_offset_seconds,
            "analysis_offset_seconds",
        ),
        "analysis_window_ratios": ratios,
        "top_k": _positive_int(top_k, "top_k"),
    }
    values = _with_ml_runtime_identity(
        "maest",
        model_version,
        _merge_parameters(reserved, parameters),
    )
    output = AnalysisOutput(
        ContractIdentity(
            analysis_family="maest",
            output_kind="analysis",
            model_name=model_name,
            model_version=model_version,
            checkpoint_id=checkpoint_id,
            preprocessing=preprocessing,
            parameters=values,
        )
    )
    validate_production_contract(output.contract)
    return output


def maest_embedding_output(
    *,
    model_version: str,
    checkpoint_id: str,
    preprocessing: str,
    sample_rate_hz: int,
    input_seconds: float,
    analysis_offset_seconds: float,
    analysis_window_ratios: Sequence[float],
    pooling: str,
    model_name: str = MAEST_MODEL_NAME,
    parameters: Mapping[str, object] | None = None,
) -> "AnalysisOutput":
    reserved: dict[str, object] = {
        "sample_rate_hz": _positive_int(sample_rate_hz, "sample_rate_hz"),
        "input_seconds": _positive_number(input_seconds, "input_seconds"),
        "analysis_offset_seconds": _non_negative_number(
            analysis_offset_seconds,
            "analysis_offset_seconds",
        ),
        "analysis_window_ratios": _validate_window_ratios(
            analysis_window_ratios,
            "analysis_window_ratios",
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
    content_generation: int

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
        object.__setattr__(
            self,
            "content_generation",
            _positive_int(self.content_generation, "content_generation"),
        )


@dataclass(frozen=True)
class AnalysisOutput:
    contract: ContractIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.contract, ContractIdentity):
            raise TypeError("contract must be a ContractIdentity")

    @property
    def key(self) -> tuple[str, str]:
        return self.contract.analysis_family, self.contract.output_kind

    @property
    def contract_hash(self) -> str:
        return self.contract.contract_hash


@dataclass(frozen=True)
class AnalysisCandidate:
    target: AnalysisTarget
    file_path: str
    file_size_bytes: int
    file_modified_ns: int
    missing_outputs: tuple[AnalysisOutput, ...]

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


@dataclass(frozen=True)
class EmbeddingOutput:
    contract: ContractIdentity
    vector: Sequence[float] | np.ndarray
    analyzed_at: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "analyzed_at",
            _required_text(self.analyzed_at, "analyzed_at"),
        )
        object.__setattr__(
            self,
            "vector",
            _readonly_float32_vector(self.vector, contract=self.contract),
        )


@dataclass(frozen=True)
class SonaraTimelineOutput:
    contract: ContractIdentity
    payload: Mapping[str, object]
    analyzed_at: str

    def __post_init__(self) -> None:
        if (
            self.contract.analysis_family,
            self.contract.output_kind,
        ) != ("sonara", "timeline"):
            raise ValueError("timeline output requires a SONARA timeline contract")
        payload = _json_copy(
            self.payload,
            expected="object",
            field_name="timeline payload",
        )
        object.__setattr__(self, "payload", MappingProxyType(payload))
        object.__setattr__(
            self,
            "analyzed_at",
            _required_text(self.analyzed_at, "analyzed_at"),
        )

    @property
    def payload_json(self) -> str:
        return json.dumps(
            dict(self.payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )


@dataclass(frozen=True)
class SonaraFingerprintOutput:
    contract: ContractIdentity
    fingerprint_version: str
    words: Sequence[int] | np.ndarray
    analyzed_at: str

    def __post_init__(self) -> None:
        if (
            self.contract.analysis_family,
            self.contract.output_kind,
        ) != ("sonara", "fingerprint"):
            raise ValueError(
                "fingerprint output requires a SONARA fingerprint contract"
            )
        object.__setattr__(
            self,
            "fingerprint_version",
            _required_text(self.fingerprint_version, "fingerprint_version"),
        )
        object.__setattr__(self, "words", _readonly_uint32_words(self.words))
        object.__setattr__(
            self,
            "analyzed_at",
            _required_text(self.analyzed_at, "analyzed_at"),
        )

    @property
    def fingerprint_blob(self) -> bytes:
        return self.words.tobytes(order="C")


@dataclass(frozen=True)
class SonaraWrite:
    target: AnalysisTarget
    core_contract: ContractIdentity
    core: SonaraRowV7
    timeline: SonaraTimelineOutput | None = None
    similarity_embedding: EmbeddingOutput | None = None
    fingerprint: SonaraFingerprintOutput | None = None

    def __post_init__(self) -> None:
        if (
            self.core_contract.analysis_family,
            self.core_contract.output_kind,
        ) != ("sonara", "core"):
            raise ValueError("core_contract must be a SONARA core contract")
        if self.core.track_id != self.target.track_id:
            raise ValueError("SONARA Core track_id does not match target")
        if self.core.content_generation != self.target.content_generation:
            raise ValueError("SONARA Core generation does not match target")
        if self.core.contract_hash != self.core_contract.contract_hash:
            raise ValueError("SONARA Core contract_hash does not match contract")
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

        optional_contracts = [
            value.contract
            for value in (
                self.timeline,
                self.similarity_embedding,
                self.fingerprint,
            )
            if value is not None
        ]
        if self.similarity_embedding is not None and (
            self.similarity_embedding.contract.analysis_family,
            self.similarity_embedding.contract.output_kind,
        ) != ("sonara", "embedding"):
            raise ValueError(
                "similarity_embedding requires a SONARA embedding contract"
            )
        for contract in optional_contracts:
            if contract.release_hash != self.core_contract.release_hash:
                raise ValueError(
                    "all SONARA outputs in one write must use the same release"
                )

    @property
    def outputs(self) -> tuple[AnalysisOutput, ...]:
        contracts = [self.core_contract]
        contracts.extend(
            value.contract
            for value in (
                self.timeline,
                self.similarity_embedding,
                self.fingerprint,
            )
            if value is not None
        )
        return tuple(AnalysisOutput(contract) for contract in contracts)


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
    analysis_contract: ContractIdentity
    genres: tuple[MaestGenreScore, ...]
    syncopated_rhythm: bool | None
    analyzed_at: str
    embedding: EmbeddingOutput | None = None

    def __post_init__(self) -> None:
        if (
            self.analysis_contract.analysis_family,
            self.analysis_contract.output_kind,
        ) != ("maest", "analysis"):
            raise ValueError("analysis_contract must be a MAEST analysis contract")
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
        if self.embedding is not None and (
            self.embedding.contract.analysis_family,
            self.embedding.contract.output_kind,
        ) != ("maest", "embedding"):
            raise ValueError("embedding must use a MAEST embedding contract")

    @property
    def outputs(self) -> tuple[AnalysisOutput, ...]:
        contracts = [self.analysis_contract]
        if self.embedding is not None:
            contracts.append(self.embedding.contract)
        return tuple(AnalysisOutput(contract) for contract in contracts)

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
        if self.output.contract.analysis_family not in {"mert", "muq", "clap"}:
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


def classifier_required_outputs_hash(
    required_outputs: Sequence[AnalysisOutput],
) -> str:
    """Hash one canonical, key-ordered set of classifier input contracts."""

    outputs = tuple(required_outputs)
    if not outputs:
        raise ValueError("required_outputs must not be empty")
    if any(not isinstance(output, AnalysisOutput) for output in outputs):
        raise TypeError("required_outputs must contain only AnalysisOutput values")
    keys = [output.key for output in outputs]
    if len(set(keys)) != len(keys):
        raise ValueError(
            "required_outputs must contain at most one contract per output"
        )
    payload = [
        {
            "contract_hash": output.contract_hash,
            "canonical_payload": output.contract.canonical_payload,
        }
        for output in sorted(outputs, key=lambda value: value.key)
    ]
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return f"sha256:{hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()}"


def active_classifier_required_outputs_hashes(
    active_outputs: Sequence[AnalysisOutput],
) -> frozenset[str]:
    """Return every non-empty classifier input subset valid under active contracts."""

    outputs = tuple(sorted(active_outputs, key=lambda value: value.key))
    if any(not isinstance(output, AnalysisOutput) for output in outputs):
        raise TypeError("active_outputs must contain only AnalysisOutput values")
    keys = [output.key for output in outputs]
    if len(set(keys)) != len(keys):
        raise ValueError("active_outputs must contain at most one contract per output")
    return frozenset(
        classifier_required_outputs_hash(selected)
        for size in range(1, len(outputs) + 1)
        for selected in combinations(outputs, size)
    )


@dataclass(frozen=True)
class ClassifierSpecification:
    classifier_key: str
    model_id: str
    feature_set: str
    feature_manifest_hash: str
    required_outputs_hash: str
    feature_names: tuple[str, ...]
    required_outputs: tuple[AnalysisOutput, ...]
    label_order: tuple[str, ...]
    positive_label: str

    def __post_init__(self) -> None:
        for field_name in (
            "classifier_key",
            "model_id",
            "feature_set",
            "feature_manifest_hash",
            "required_outputs_hash",
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
                "required_outputs must contain at most one contract per output"
            )
        object.__setattr__(self, "required_outputs", outputs)
        expected_outputs_hash = classifier_required_outputs_hash(outputs)
        if self.required_outputs_hash != expected_outputs_hash:
            raise ValueError(
                "required_outputs_hash does not match the canonical required_outputs"
            )
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

    @property
    def sonara_release_hash(self) -> str | None:
        releases = {
            output.contract.release_hash
            for output in self.required_outputs
            if output.contract.analysis_family == "sonara"
        }
        if not releases:
            return None
        if len(releases) != 1:
            raise ValueError("classifier SONARA requirements must use one release")
        return next(iter(releases))


@dataclass(frozen=True)
class ClassifierReadiness:
    total_tracks: int
    ready_tracks: int
    missing_input_tracks: int
    already_scored_tracks: int
    candidate_tracks: int
    missing_by_output: Mapping[str, int] = field(default_factory=dict)


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
    score: ClassifierScoreV7

    def __post_init__(self) -> None:
        if not isinstance(self.specification, ClassifierSpecification):
            raise TypeError("specification must be a ClassifierSpecification")
        if self.score.track_id != self.target.track_id:
            raise ValueError("classifier score track_id does not match target")
        if self.score.content_generation != self.target.content_generation:
            raise ValueError("classifier score generation does not match target")
        expected_identity = (
            self.specification.classifier_key,
            self.specification.model_id,
            self.specification.feature_set,
            self.specification.feature_manifest_hash,
            self.specification.required_outputs_hash,
            int(self.specification.sonara_release_hash is not None),
            self.specification.sonara_release_hash,
            self.specification.positive_label,
        )
        score_identity = (
            self.score.classifier_key,
            self.score.model_id,
            self.score.feature_set,
            self.score.feature_manifest_hash,
            self.score.required_outputs_hash,
            self.score.uses_sonara,
            self.score.sonara_release_hash,
            self.score.positive_label,
        )
        if score_identity != expected_identity:
            raise ValueError(
                "classifier score identity does not match its specification"
            )


@dataclass(frozen=True)
class AnalysisResetResult:
    core_rows_deleted: int = 0
    artifact_rows_deleted: int = 0
    classifier_rows_deleted: int = 0
