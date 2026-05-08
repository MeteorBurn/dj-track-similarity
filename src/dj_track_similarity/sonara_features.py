from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .audio_loader import load_audio_mono
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
            "chord_sequence",
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


FEATURE_DESCRIPTIONS = {
    "bpm": "Analyzed tempo in beats per minute; useful for DJ tempo compatibility.",
    "beats": "Beat frame positions detected by sonara.",
    "onset_frames": "Detected onset frame positions; shows where rhythmic or transient events begin.",
    "onset_density": "Onset density measured as value/sec; a proxy for rhythmic activity.",
    "rms_mean": "Average RMS loudness.",
    "rms_max": "Peak RMS loudness.",
    "loudness_lufs": "Integrated loudness in LUFS.",
    "dynamic_range_db": "Loudness range in dB between quiet and loud passages.",
    "spectral_centroid_mean": "Average brightness in Hz.",
    "zero_crossing_rate": "Zero crossing rate; a rough proxy for noisiness or percussiveness.",
    "duration_sec": "Analyzed track duration in seconds.",
    "energy": "Perceived intensity from loudness, brightness, and activity.",
    "danceability": "Beat regularity and rhythm suitability for dancing.",
    "valence": "Mood estimate: lower is darker/sadder, higher is brighter/happier.",
    "acousticness": "Acoustic versus electronic character estimate.",
    "key": "Analyzed musical key, independent of file tags.",
    "key_confidence": "Confidence of analyzed musical key.",
    "chord_sequence": "Beat-synchronous chord labels.",
    "predominant_chord": "Most frequent chord in the analyzed track.",
    "chord_change_rate": "Chord changes per second; a harmonic complexity proxy.",
    "dissonance": "Sensory dissonance estimate from harmonic roughness.",
    "spectral_bandwidth_mean": "Average frequency spread.",
    "spectral_rolloff_mean": "Frequency below which most spectral energy sits.",
    "spectral_flatness_mean": "Tonal versus noise-like spectrum estimate.",
    "spectral_contrast_mean": "Peak-valley contrast across spectral bands.",
    "mfcc_mean": "Mean MFCC vector; compact timbre fingerprint.",
    "chroma_mean": "Mean pitch-class vector; compact harmonic color fingerprint.",
    "mel_spectrogram": "Mel-frequency power spectrogram values; useful for visual texture and model inputs.",
    "melspectrogram": "Mel-frequency power spectrogram values; Sonara-compatible alias for mel_spectrogram.",
    "mel_spectrogram_db": "Mel-frequency power spectrogram converted to dB; useful for visual texture and model inputs.",
    "tempo": "Analyzed tempo in beats per minute; Sonara playlist pipeline aliases this to BPM.",
    "tempo_curve": "Beat-to-beat tempo curve; available in Sonara full mode, not playlist mode.",
    "tempo_variability": "Variation in local tempo; available in Sonara full mode, not playlist mode.",
    "beat_track": "Tempo plus beat frame positions from Sonara beat tracking.",
    "onset_detect": "Detected onset frame positions; shows where rhythmic or transient events begin.",
    "onset_strength": "Onset strength envelope; shows transient/rhythmic activity over time.",
    "onset_strength_multi": "Multi-band onset strength envelope when exported by the installed Sonara version.",
    "tempogram": "Tempo-period representation when exported by the installed Sonara version.",
    "fourier_tempogram": "Fourier tempogram when exported by the installed Sonara version.",
    "metrogram": "Meter/rhythm representation when exported by the installed Sonara version.",
    "plp": "Predominant local pulse curve when exported by the installed Sonara version.",
    "detect_time_signature": "Detected time signature or availability status.",
    "mfcc": "MFCC timbre coefficients over time.",
    "chroma_stft": "Pitch-class chroma features over time.",
    "spectral_centroid": "Spectral brightness over time in Hz.",
    "spectral_bandwidth": "Frequency spread over time or Sonara summary value.",
    "spectral_rolloff": "Frequency below which most spectral energy sits.",
    "spectral_flatness": "Tonal versus noise-like spectrum estimate.",
    "spectral_contrast": "Peak-valley contrast across spectral bands.",
    "poly_features": "Polynomial spectral features when exported by the installed Sonara version.",
    "hpcp": "Harmonic pitch class profile for chord/key analysis.",
    "chords_from_beats": "Beat-synchronous chord labels produced from HPCP and beats.",
    "chords_from_frames": "Frame/segment chord labels produced from HPCP.",
    "chord_descriptors": "Summary statistics for a chord sequence.",
    "key_detection": "Analyzed musical key, independent of file tags.",
    "yin": "Fundamental frequency estimate from YIN pitch tracking.",
    "pyin": "Probabilistic YIN pitch estimate and voiced probabilities.",
    "piptrack": "Pitch salience tracks from spectral peaks.",
    "estimate_tuning": "Estimated tuning offset.",
    "pitch_tuning": "Pitch tuning estimated from detected pitches.",
    "salience": "Harmonic salience representation from spectral energy.",
    "detect_key": "Standalone key detection availability; Sonara playlist analysis also provides key/key_confidence.",
}


HUMAN_FEATURES = {
    "bpm",
    "key",
    "key_confidence",
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "loudness_lufs",
    "dynamic_range_db",
    "onset_density",
    "spectral_centroid_mean",
    "zero_crossing_rate",
    "duration_sec",
    "predominant_chord",
    "chord_change_rate",
    "dissonance",
    "spectral_bandwidth_mean",
    "spectral_rolloff_mean",
    "spectral_flatness_mean",
    "spectral_contrast_mean",
    "mfcc_mean",
    "chroma_mean",
}


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

    features: dict[str, object] = {}
    for key in PLAYLIST_FEATURE_KEYS:
        if key in analysis:
            features[key] = _feature_payload(analysis[key], key)
    elapsed = time.perf_counter() - started

    db.save_sonara_features(
        track.id,
        features,
        bpm=_optional_float(analysis.get("bpm")),
        musical_key=_sonara_musical_key(analysis),
        energy=_optional_float(analysis.get("energy")),
        duration=_optional_float(analysis.get("duration_sec")),
        model_name=SONARA_MODEL_NAME,
    )
    return SonaraFeatureResult(track.id, track.path, elapsed)


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


def _feature_payload(value: object, name: str) -> dict[str, object]:
    serialized = _serialize_value(value, include_full_value=False)
    payload = {
        "value": serialized["value"],
        "type": serialized["type"],
        "description": FEATURE_DESCRIPTIONS.get(name, "Sonara analysis feature."),
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
        return float(value)
    except (TypeError, ValueError):
        return None


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
