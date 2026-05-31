from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .audio_loader import DecodedAudio, load_audio_mono
from .database import LibraryDatabase
from .models import Track


SONARA_ANALYSIS_MODE = "playlist"
SONARA_MODEL_NAME = "sonara-playlist-lab"


PLAYLIST_FEATURE_GROUPS = (
    (
        "Core features",
        (
            "bpm",
            "beats",
            "onset_frames",
            "onset_density",
            "n_beats",
            "rms_mean",
            "rms_max",
            "loudness_lufs",
            "dynamic_range_db",
            "spectral_centroid_mean",
            "zero_crossing_rate",
            "duration_sec",
        ),
    ),
    (
        "Perceptual features (0.0 - 1.0)",
        (
            "energy",
            "danceability",
            "valence",
            "acousticness",
        ),
    ),
    (
        "Musical key",
        (
            "key",
            "key_confidence",
        ),
    ),
    (
        "Tonal analysis",
        (
            "predominant_chord",
            "chord_change_rate",
            "dissonance",
        ),
    ),
    (
        "Spectral features",
        (
            "spectral_bandwidth_mean",
            "spectral_rolloff_mean",
            "spectral_flatness_mean",
            "spectral_contrast_mean",
            "mfcc_mean",
            "chroma_mean",
        ),
    ),
)

PLAYLIST_FEATURE_KEYS = tuple(key for _group, keys in PLAYLIST_FEATURE_GROUPS for key in keys)


@dataclass(frozen=True)
class SonaraFeatureResult:
    track_id: int
    path: str
    elapsed_seconds: float


def analyze_and_store_sonara_features(
    db: LibraryDatabase,
    track: Track,
    *,
    sonara_module: Any | None = None,
) -> SonaraFeatureResult:
    sonara = sonara_module or _import_sonara()
    started = time.perf_counter()
    analysis = _analyze_file_or_signal(sonara, track.path)
    elapsed = time.perf_counter() - started
    _store_sonara_analysis(db, track, analysis)
    return SonaraFeatureResult(track.id, track.path, elapsed)


def analyze_and_store_sonara_features_from_audio(
    db: LibraryDatabase,
    track: Track,
    decoded: DecodedAudio,
    *,
    sonara_module: Any | None = None,
) -> SonaraFeatureResult:
    sonara = sonara_module or _import_sonara()
    started = time.perf_counter()
    audio = np.asarray(decoded.audio, dtype=np.float32)
    if decoded.sample_rate != 22050:
        resample = getattr(sonara, "resample", None)
        if not callable(resample):
            raise RuntimeError("sonara shared-audio analysis requires sonara.resample for non-22050 Hz input")
        audio = np.asarray(resample(audio, orig_sr=decoded.sample_rate, target_sr=22050), dtype=np.float32)
    analysis = dict(sonara.analyze_signal(audio, sr=22050, mode=SONARA_ANALYSIS_MODE))
    elapsed = time.perf_counter() - started
    _store_sonara_analysis(db, track, analysis)
    return SonaraFeatureResult(track.id, track.path, elapsed)


def _store_sonara_analysis(db: LibraryDatabase, track: Track, analysis: dict[str, object]) -> None:
    features: dict[str, object] = {}
    for key in PLAYLIST_FEATURE_KEYS:
        if key in analysis:
            features[key] = _feature_payload(analysis[key])

    db.save_sonara_features(
        track.id,
        features,
        bpm=_optional_float(analysis.get("bpm")),
        musical_key=_sonara_musical_key(analysis),
        energy=_optional_float(analysis.get("energy")),
        duration=_optional_float(analysis.get("duration_sec")),
        model_name=SONARA_MODEL_NAME,
    )


def _import_sonara():
    try:
        import sonara
    except ImportError as error:
        raise RuntimeError("sonara is not installed. Install it with: python -m pip install -e \".[sonara,dev]\"") from error
    return sonara


def _analyze_file_or_signal(sonara: Any, path: str | Path) -> dict[str, object]:
    try:
        return dict(sonara.analyze_file(str(path), sr=22050, mode=SONARA_ANALYSIS_MODE))
    except Exception:
        if Path(path).suffix.lower() not in {".wav", ".wave"}:
            raise
        audio, _detail = _load_wav_fallback(path, sonara)
        return dict(sonara.analyze_signal(audio, sr=22050, mode=SONARA_ANALYSIS_MODE))


def _load_wav_fallback(path: str | Path, sonara: Any) -> tuple[np.ndarray, str]:
    audio, sr_native, detail = load_audio_mono(path)
    if sr_native != 22050:
        audio = sonara.resample(audio, orig_sr=sr_native, target_sr=22050)
    return audio, detail


def _feature_payload(value: object) -> dict[str, object]:
    serialized = _serialize_value(value, include_full_value=False)
    payload = {
        "value": serialized["value"],
        "type": serialized["type"],
    }
    for key in ("shape", "size", "dtype", "summary", "storage", "length", "fields"):
        if key in serialized:
            payload[key] = serialized[key]
    return payload


def _serialize_value(value: object, *, include_full_value: bool = True) -> dict[str, object]:
    if isinstance(value, np.ndarray):
        array = np.asarray(value)
        payload = {
            "value": array.tolist() if include_full_value else None,
            "type": "ndarray",
            "shape": list(array.shape),
            "size": int(array.size),
            "dtype": str(array.dtype),
            "summary": _array_summary(array),
        }
        if not include_full_value:
            payload["storage"] = "summary_only_no_full_array_saved"
        return payload
    if isinstance(value, np.generic):
        return _serialize_value(value.item(), include_full_value=include_full_value)
    if isinstance(value, (list, tuple)):
        if _is_numeric_sequence(value) and len(value) > 64:
            array = np.asarray(value, dtype=np.float32)
            return {
                "value": None if not include_full_value else list(value[:16]),
                "type": type(value).__name__,
                "length": len(value),
                "size": int(array.size),
                "summary": _array_summary(array),
                "storage": "summary_only_no_full_sequence_saved" if not include_full_value else "first_16_values_only",
            }
        return {
            "value": [_serialize_value(item, include_full_value=include_full_value)["value"] for item in value],
            "type": type(value).__name__,
            "length": len(value),
        }
    if isinstance(value, dict):
        fields = {str(key): _serialize_value(item, include_full_value=include_full_value) for key, item in value.items()}
        return {
            "value": {key: item["value"] for key, item in fields.items()},
            "type": "dict",
            "fields": fields,
        }
    if isinstance(value, bool):
        return {"value": value, "type": "bool"}
    if isinstance(value, int):
        return {"value": value, "type": "int"}
    if isinstance(value, float):
        return {"value": value, "type": "float"}
    if value is None:
        return {"value": None, "type": "null"}
    return {"value": str(value), "type": type(value).__name__}


def _array_summary(array: np.ndarray) -> dict[str, float]:
    if array.size == 0:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0}
    finite = np.asarray(array, dtype=np.float32)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return {"min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0}
    return {
        "min": float(np.nanmin(finite)),
        "max": float(np.nanmax(finite)),
        "mean": float(np.nanmean(finite)),
        "std": float(np.nanstd(finite)),
    }


def _is_numeric_sequence(value: object) -> bool:
    if not isinstance(value, (list, tuple)) or not value:
        return False
    return all(isinstance(item, (int, float, np.integer, np.floating)) for item in value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _sonara_musical_key(analysis: dict[str, object]) -> str | None:
    for key in ("key", "key_detection", "detect_key", "predominant_key"):
        value = _optional_string(analysis.get(key))
        if value:
            return value
    return None
