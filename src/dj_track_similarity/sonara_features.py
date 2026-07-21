from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import numpy as np

from .analysis_config import DEFAULT_SONARA_OUTPUTS, normalize_sonara_outputs
from .database import LibraryDatabase
from .models import Track
from .sonara_contract import (
    SONARA_ANALYSIS_MODE,
    SONARA_BPM_MAX,
    SONARA_BPM_MIN,
    SONARA_DECODER_BACKEND,
    SONARA_EXECUTION_PATH,
    SONARA_SAMPLE_RATE,
    build_sonara_analysis_signature,
    expected_sonara_analysis_signature,
)


SONARA_MODEL_NAME = "sonara-playlist-lab"

# Each output owns an independent, deterministic request profile. A combined job uses the union of
# these names, but persisted signatures remain per output so adding Timeline later never invalidates
# an already-current Core result.
SONARA_REQUEST_ORDER = (
    "bpm", "beats", "onsets", "rms", "dynamic_range", "centroid", "zcr",
    "onset_density", "bandwidth", "rolloff", "flatness", "contrast", "mfcc",
    "chroma", "chords", "dissonance", "energy", "danceability", "key",
    "valence", "acousticness", "tempo_curve", "time_signature", "beatgrid",
    "structure", "embedding", "fingerprint", "loudness", "silence",
    "key_candidates", "vocalness", "mood", "instrumentalness",
)
SONARA_OUTPUT_FEATURE_REQUESTS = {
    "core": (
        "bpm", "beats", "rms", "dynamic_range", "centroid", "zcr",
        "onset_density", "bandwidth", "rolloff", "flatness", "contrast", "mfcc",
        "chroma", "chords", "dissonance", "energy", "danceability", "key",
        "valence", "acousticness", "tempo_curve", "time_signature", "beatgrid",
        "structure", "loudness", "silence", "key_candidates", "vocalness", "mood",
        "instrumentalness",
    ),
    "timeline": ("beats", "onsets", "chords", "tempo_curve", "beatgrid", "structure", "loudness"),
    "representations": ("embedding", "fingerprint"),
}

SONARA_CORE_KEYS = (
    "bpm", "bpm_raw", "bpm_confidence", "bpm_candidates", "onset_density", "n_beats",
    "rms_mean", "rms_max", "loudness_lufs", "dynamic_range_db", "spectral_centroid_mean",
    "zero_crossing_rate", "duration_sec", "energy", "danceability", "valence", "acousticness",
    "key", "key_camelot", "key_confidence", "key_candidates", "predominant_chord",
    "chord_change_rate", "dissonance", "spectral_bandwidth_mean", "spectral_rolloff_mean",
    "spectral_flatness_mean", "spectral_contrast_mean", "mfcc_mean", "chroma_mean",
    "tempo_variability", "time_signature", "time_signature_confidence", "energy_level",
    "intro_end_sec", "outro_start_sec", "energy_curve_hop_sec", "true_peak_db", "replaygain_db",
    "loudness_momentary_max_db", "loudness_range_lu", "grid_offset_sec", "grid_stability",
    "vocalness", "mood_happy", "mood_aggressive", "mood_relaxed", "mood_sad",
    "instrumentalness", "leading_silence_sec", "trailing_silence_sec",
)
SONARA_TIMELINE_KEYS = (
    "beats", "onset_frames", "chord_sequence", "chord_events", "tempo_curve", "downbeats",
    "energy_curve", "segments", "loudness_curve",
)


def _feature_names_for_outputs(outputs: Sequence[str] | None) -> list[str]:
    selected = normalize_sonara_outputs(DEFAULT_SONARA_OUTPUTS if outputs is None else outputs)
    requested = {
        name
        for output in selected
        for name in SONARA_OUTPUT_FEATURE_REQUESTS[output]
    }
    return [name for name in SONARA_REQUEST_ORDER if name in requested]


def sonara_analysis_signatures_for_outputs(
    outputs: Sequence[str] | None,
) -> dict[str, dict[str, object]]:
    selected = normalize_sonara_outputs(DEFAULT_SONARA_OUTPUTS if outputs is None else outputs)
    return {
        output: expected_sonara_analysis_signature(SONARA_OUTPUT_FEATURE_REQUESTS[output])
        for output in selected
    }


@dataclass(frozen=True)
class SonaraBatchTrackResult:
    track: Track
    error: Exception | None = None


def analyze_and_store_sonara_batch(
    db: LibraryDatabase,
    tracks: Sequence[Track],
    *,
    sonara_module: Any | None = None,
    outputs: Sequence[str] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> list[SonaraBatchTrackResult]:
    """Analyze one native SONARA batch and persist successful results in input order."""

    if not tracks:
        return []
    sonara = sonara_module or _import_sonara()
    selected = normalize_sonara_outputs(DEFAULT_SONARA_OUTPUTS if outputs is None else outputs)
    raw_results = sonara.analyze_batch(
        [track.path for track in tracks],
        sr=SONARA_SAMPLE_RATE,
        mode=SONARA_ANALYSIS_MODE,
        bpm_min=SONARA_BPM_MIN,
        bpm_max=SONARA_BPM_MAX,
        progress=progress,
        **_analysis_kwargs(selected),
    )
    if len(raw_results) != len(tracks):
        raise RuntimeError("SONARA batch result count does not match track count")

    prepared: list[tuple[Track, dict[str, object]] | Exception] = []
    for track, raw_result in zip(tracks, raw_results):
        analysis = dict(raw_result)
        if bool(getattr(raw_result, "failed", False)) or analysis.get("error") is not None:
            kind = str(analysis.get("error_kind") or "analysis")
            prepared.append(RuntimeError(f"SONARA {kind} failure: {analysis.get('error') or 'unknown error'}"))
            continue
        _analysis_with_package_provenance(analysis, sonara, native_batch=True)
        prepared.append((track, analysis))

    stored: list[SonaraBatchTrackResult] = []
    for track, prepared_result in zip(tracks, prepared):
        if isinstance(prepared_result, Exception):
            stored.append(SonaraBatchTrackResult(track=track, error=prepared_result))
            continue
        _, analysis = prepared_result
        try:
            _store_sonara_analysis(db, track, analysis, outputs=selected)
        except Exception as error:
            stored.append(SonaraBatchTrackResult(track=track, error=error))
        else:
            stored.append(SonaraBatchTrackResult(track=track))
    return stored


def _analysis_kwargs(outputs: Sequence[str] | None) -> dict[str, object]:
    selected = normalize_sonara_outputs(DEFAULT_SONARA_OUTPUTS if outputs is None else outputs)
    kwargs: dict[str, object] = {"features": _feature_names_for_outputs(selected)}
    if "core" in selected:
        kwargs["vocalness_model"] = "bundled"
    return kwargs


def _store_sonara_analysis(
    db: LibraryDatabase,
    track: Track,
    analysis: dict[str, object],
    *,
    outputs: Sequence[str] | None = None,
) -> None:
    selected = normalize_sonara_outputs(DEFAULT_SONARA_OUTPUTS if outputs is None else outputs)
    provenance = _sonara_provenance(analysis)
    features: dict[str, object] = {}
    if "core" in selected:
        for key in SONARA_CORE_KEYS:
            if key in analysis and analysis[key] is not None:
                features[key] = _feature_payload(analysis[key])
        if analysis.get("energy_curve") is not None:
            features["energy_curve_summary"] = _feature_payload(analysis["energy_curve"])
        if not features:
            raise RuntimeError("SONARA Core output did not contain any core fields")

    timeline = {
        key: _curve_payload(analysis[key])
        for key in SONARA_TIMELINE_KEYS
        if "timeline" in selected and key in analysis and analysis[key] is not None
    }
    if "timeline" in selected and not timeline:
        raise RuntimeError("SONARA Timeline output did not contain any timeline fields")

    embedding_value = analysis.get("embedding") if "representations" in selected else None
    fingerprint_value = analysis.get("fingerprint") if "representations" in selected else None
    if "representations" in selected:
        if embedding_value is None or fingerprint_value is None:
            raise RuntimeError("SONARA Representations output requires both embedding and fingerprint")
        embedding_array = np.asarray(embedding_value, dtype=np.float32).reshape(-1)
        if not embedding_array.size or not np.isfinite(embedding_array).all():
            raise RuntimeError("SONARA embedding is empty or contains non-finite values")

    if "core" in selected:
        db.save_sonara_features(
            track.id,
            features,
            bpm=_optional_float(analysis.get("bpm")),
            musical_key=_sonara_musical_key(analysis),
            energy=_optional_float(analysis.get("energy")),
            duration=_optional_float(analysis.get("duration_sec")),
            model_name=SONARA_MODEL_NAME,
            provenance=provenance,
            analysis_signature=_sonara_analysis_signature(analysis, "core"),
        )
    if "timeline" in selected:
        db.save_sonara_timeline(
            track.id,
            timeline,
            provenance=provenance,
            analysis_signature=_sonara_analysis_signature(analysis, "timeline"),
        )
    if "representations" in selected:
        db.save_sonara_representations(
            track.id,
            embedding=embedding_array,
            fingerprint=_curve_payload(fingerprint_value),
            embedding_version=_optional_string(analysis.get("embedding_version")),
            fingerprint_version=_optional_string(analysis.get("fingerprint_version")),
            model_name=SONARA_MODEL_NAME,
            provenance=provenance,
            analysis_signature=_sonara_analysis_signature(analysis, "representations"),
        )


def _import_sonara():
    try:
        import sonara
    except ImportError as error:
        raise RuntimeError("sonara is not installed. Install it with: python -m pip install -e \".[sonara,dev]\"") from error
    return sonara


def _feature_payload(value: object) -> dict[str, object]:
    # Core keeps compact vectors such as Contrast (7), MFCC (13), and Chroma (12) in full.
    # Only genuinely long numeric sequences are reduced to descriptors in the hot database.
    include_full_value = True
    if isinstance(value, np.ndarray):
        include_full_value = int(np.asarray(value).size) <= 64
    elif _is_numeric_sequence(value):
        include_full_value = len(value) <= 64
    serialized = _serialize_value(value, include_full_value=include_full_value)
    payload = {
        "value": serialized["value"],
        "type": serialized["type"],
    }
    for key in ("shape", "size", "dtype", "summary", "storage", "length", "fields"):
        if key in serialized:
            payload[key] = serialized[key]
    return payload


def _curve_payload(value: object) -> dict[str, object]:
    """Serialize a heavy curve/sequence field with every value for a sidecar database. Unlike
    _feature_payload (which strips long sequences to a summary for the hot path) and _serialize_value
    (which truncates numeric sequences over 64 elements even when include_full_value is set), this
    keeps the FULL structure, because these payloads are stored out-of-band and loaded on demand."""
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
    if isinstance(value, dict):
        fields = {str(key): _curve_payload(item) for key, item in value.items()}
        return {
            "value": {key: item["value"] for key, item in fields.items()},
            "type": "dict",
            "fields": fields,
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


def _analysis_with_package_provenance(
    analysis: dict[str, object],
    sonara: Any,
    *,
    native_batch: bool = False,
) -> dict[str, object]:
    raw_provenance = analysis.get("provenance")
    provenance = dict(raw_provenance) if isinstance(raw_provenance, dict) else {}
    package_version = _optional_string(getattr(sonara, "__version__", None))
    if package_version is None:
        try:
            package_version = version("sonara")
        except PackageNotFoundError:
            package_version = None
    if package_version:
        provenance["package_version"] = package_version
    if native_batch:
        provenance["decoder_backend"] = SONARA_DECODER_BACKEND
        provenance["execution_path"] = SONARA_EXECUTION_PATH
    if provenance:
        analysis["provenance"] = provenance
    return analysis


def _sonara_provenance(analysis: dict[str, object]) -> dict[str, object] | None:
    value = analysis.get("provenance")
    if not isinstance(value, dict):
        return None
    return {str(key): _serialize_value(item)["value"] for key, item in value.items()}


def _sonara_analysis_signature(
    analysis: dict[str, object],
    output: str,
) -> dict[str, object]:
    provenance = _sonara_provenance(analysis)
    return build_sonara_analysis_signature(
        requested_features=SONARA_OUTPUT_FEATURE_REQUESTS[output],
        provenance=provenance,
    )
