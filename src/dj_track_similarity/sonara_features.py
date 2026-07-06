from __future__ import annotations

import math
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .audio_loader import DecodedAudio, load_audio_mono
from .database import LibraryDatabase
from .models import Track


SONARA_ANALYSIS_MODE = "playlist"
SONARA_MODEL_NAME = "sonara-playlist-lab"
SONARA_BPM_MIN = 79.0
SONARA_BPM_MAX = 192.0

# sonara 2.0 `features=[...]` REPLACES the mode preset instead of extending it: passing only an
# opt-in family drops the base playlist output (key, energy, chords, etc.). So when any opt-in family
# is requested we must pass the full playlist-equivalent feature list PLUS the family names. This
# list reproduces the plain playlist output exactly (verified against the real library: 0 lost,
# 0 extra keys). When no family is requested we pass no `features` at all (pure playlist = pre-2.0).
SONARA_PLAYLIST_FEATURE_REQUESTS = (
    "bpm", "beats", "onsets", "rms", "dynamic_range", "centroid", "zcr",
    "onset_density", "bandwidth", "rolloff", "flatness", "contrast", "mfcc",
    "chroma", "chords", "dissonance", "energy", "danceability", "key",
    "valence", "acousticness",
)

# SONARA 2.0 opt-in feature families -> the `features=[...]` names sonara.analyze_* expects.
# Requesting a family adds its playlist output; the plain playlist mode (empty families) is the
# pre-2.0 behavior. Family names match analysis_config.SONARA_FEATURE_FAMILIES.
SONARA_FEATURE_REQUESTS = {
    "structure": ("structure",),
    "loudness": ("loudness",),
    "beatgrid": ("beatgrid",),
    "key_candidates": ("key_candidates",),
    "vocalness": ("vocalness",),
    "silence": ("silence",),
}

# Light opt-in fields stored inside sonara_features JSON (hot search path). Grouped per family so a
# family that was not requested contributes nothing.
SONARA_OPTIN_LIGHT_KEYS = {
    "structure": ("energy_level", "intro_end_sec", "outro_start_sec", "segments", "energy_curve_hop_sec"),
    "loudness": ("true_peak_db", "replaygain_db", "loudness_momentary_max_db", "loudness_range_lu"),
    "beatgrid": ("grid_offset_sec", "grid_stability"),
    "key_candidates": ("key_candidates",),
    "vocalness": ("vocalness",),
    "silence": ("leading_silence_sec", "trailing_silence_sec"),
}

# Heavy per-family curve/array fields stored out-of-band in the sonara_curves table (UI-only, never
# read by the hot search path). Not part of sonara_features JSON.
SONARA_OPTIN_CURVE_KEYS = {
    "structure": ("energy_curve",),
    "loudness": ("loudness_curve",),
    "beatgrid": ("downbeats",),
}

# Default playlist fields new in sonara 2.0 that arrive without any opt-in request and are cheap to
# keep in the hot path. key_camelot is sonara's own analysis output (not a project-side Camelot
# derivation), so storing it is allowed.
SONARA_DEFAULT_EXTRA_KEYS = ("bpm_raw", "bpm_candidates", "key_camelot")


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


def _feature_names_for_families(families: Sequence[str] | None) -> list[str]:
    """Map requested opt-in families to the sonara `features=[...]` request list. Returns [] when no
    family is requested so sonara runs the plain playlist mode (pre-2.0 behavior). When any family is
    requested we must include the full playlist feature set, because sonara's `features=[...]`
    REPLACES the mode preset rather than extending it."""
    if not families:
        return []
    requested: list[str] = list(SONARA_PLAYLIST_FEATURE_REQUESTS)
    for family in families:
        for name in SONARA_FEATURE_REQUESTS.get(family, ()):
            if name not in requested:
                requested.append(name)
    return requested


def _split_optin_analysis(
    analysis: dict[str, object],
    families: Sequence[str] | None,
) -> tuple[dict[str, object], dict[str, object]]:
    """Split requested opt-in output into light fields (stored in sonara_features JSON) and heavy
    curve/array fields (stored in the sonara_curves table)."""
    light: dict[str, object] = {}
    curves: dict[str, object] = {}
    if not families:
        return light, curves
    for family in families:
        for key in SONARA_OPTIN_LIGHT_KEYS.get(family, ()):
            if key in analysis:
                light[key] = _feature_payload(analysis[key])
        for key in SONARA_OPTIN_CURVE_KEYS.get(family, ()):
            if key in analysis:
                curves[key] = _curve_payload(analysis[key])
    return light, curves


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
    feature_families: Sequence[str] | None = None,
) -> SonaraFeatureResult:
    sonara = sonara_module or _import_sonara()
    started = time.perf_counter()
    analysis = _analyze_file_or_signal(sonara, track.path, feature_families=feature_families)
    elapsed = time.perf_counter() - started
    _store_sonara_analysis(db, track, analysis, feature_families=feature_families)
    return SonaraFeatureResult(track.id, track.path, elapsed)


def analyze_and_store_sonara_features_from_audio(
    db: LibraryDatabase,
    track: Track,
    decoded: DecodedAudio,
    *,
    sonara_module: Any | None = None,
    feature_families: Sequence[str] | None = None,
) -> SonaraFeatureResult:
    analysis, elapsed = analyze_sonara_features_from_audio(
        decoded, sonara_module=sonara_module, feature_families=feature_families
    )
    _store_sonara_analysis(db, track, analysis, feature_families=feature_families)
    return SonaraFeatureResult(track.id, track.path, elapsed)


def analyze_sonara_features_from_audio(
    decoded: DecodedAudio,
    *,
    sonara_module: Any | None = None,
    feature_families: Sequence[str] | None = None,
) -> tuple[dict[str, object], float]:
    sonara = sonara_module or _import_sonara()
    started = time.perf_counter()
    audio = np.asarray(decoded.audio, dtype=np.float32)
    if decoded.sample_rate != 22050:
        resample = getattr(sonara, "resample", None)
        if not callable(resample):
            raise RuntimeError("sonara shared-audio analysis requires sonara.resample for non-22050 Hz input")
        audio = np.asarray(resample(audio, orig_sr=decoded.sample_rate, target_sr=22050), dtype=np.float32)
    analysis = dict(
        sonara.analyze_signal(
            audio,
            sr=22050,
            mode=SONARA_ANALYSIS_MODE,
            bpm_min=SONARA_BPM_MIN,
            bpm_max=SONARA_BPM_MAX,
            **_feature_kwargs(feature_families),
        )
    )
    elapsed = time.perf_counter() - started
    return analysis, elapsed


def _feature_kwargs(feature_families: Sequence[str] | None) -> dict[str, object]:
    """Build the sonara `features=[...]` kwarg. Empty families -> no kwarg (plain playlist mode)."""
    names = _feature_names_for_families(feature_families)
    return {"features": names} if names else {}


def _store_sonara_analysis(
    db: LibraryDatabase,
    track: Track,
    analysis: dict[str, object],
    *,
    feature_families: Sequence[str] | None = None,
) -> None:
    features: dict[str, object] = {}
    for key in PLAYLIST_FEATURE_KEYS:
        if key in analysis:
            features[key] = _feature_payload(analysis[key])

    # sonara 2.0 default playlist extras (bpm_raw, bpm_candidates, key_camelot) arrive without any
    # opt-in request and are cheap enough to keep in the hot path.
    for key in SONARA_DEFAULT_EXTRA_KEYS:
        if key in analysis:
            features[key] = _feature_payload(analysis[key])

    light, curves = _split_optin_analysis(analysis, feature_families)
    features.update(light)

    db.save_sonara_features(
        track.id,
        features,
        bpm=_optional_float(analysis.get("bpm")),
        musical_key=_sonara_musical_key(analysis),
        energy=_optional_float(analysis.get("energy")),
        duration=_optional_float(analysis.get("duration_sec")),
        model_name=SONARA_MODEL_NAME,
    )
    if curves:
        db.save_sonara_curves(track.id, curves)


def _import_sonara():
    try:
        import sonara
    except ImportError as error:
        raise RuntimeError("sonara is not installed. Install it with: python -m pip install -e \".[sonara,dev]\"") from error
    return sonara


def _analyze_file_or_signal(
    sonara: Any,
    path: str | Path,
    *,
    feature_families: Sequence[str] | None = None,
) -> dict[str, object]:
    feature_kwargs = _feature_kwargs(feature_families)
    try:
        return dict(
            sonara.analyze_file(
                str(path),
                sr=22050,
                mode=SONARA_ANALYSIS_MODE,
                bpm_min=SONARA_BPM_MIN,
                bpm_max=SONARA_BPM_MAX,
                **feature_kwargs,
            )
        )
    except Exception:
        if Path(path).suffix.lower() not in {".wav", ".wave"}:
            raise
        audio, _detail = _load_wav_fallback(path, sonara)
        return dict(
            sonara.analyze_signal(
                audio,
                sr=22050,
                mode=SONARA_ANALYSIS_MODE,
                bpm_min=SONARA_BPM_MIN,
                bpm_max=SONARA_BPM_MAX,
                **feature_kwargs,
            )
        )


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


def _curve_payload(value: object) -> dict[str, object]:
    """Serialize a heavy curve/array field WITH every value, for the sonara_curves table. Unlike
    _feature_payload (which strips long sequences to a summary for the hot path) and _serialize_value
    (which truncates numeric sequences over 64 elements even when include_full_value is set), this
    keeps the FULL sequence, because curves are stored out-of-band and loaded only for UI display."""
    if isinstance(value, np.ndarray):
        array = np.asarray(value)
        return {
            "value": array.tolist(),
            "type": "ndarray",
            "shape": list(array.shape),
            "size": int(array.size),
            "dtype": str(array.dtype),
            "summary": _array_summary(array),
        }
    if isinstance(value, (list, tuple)):
        return {
            "value": [_curve_payload(item)["value"] if isinstance(item, (list, tuple, dict, np.ndarray)) else _scalar_value(item) for item in value],
            "type": type(value).__name__,
            "length": len(value),
        }
    return {"value": _scalar_value(value), "type": type(value).__name__}


def _scalar_value(value: object) -> object:
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if value is None:
        return None
    return str(value)


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
