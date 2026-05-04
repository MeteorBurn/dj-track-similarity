from __future__ import annotations

import shutil
import subprocess
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from .database import LibraryDatabase
from .models import Track


SONARA_ANALYSIS_MODE = "playlist"
SONARA_MODEL_NAME = "sonara-playlist-lab"
SUMMARY_AUDIO_MAX_SECONDS = 5.0


FEATURE_DESCRIPTIONS = {
    "bpm": "Analyzed tempo in beats per minute; useful for DJ tempo compatibility.",
    "beats": "Beat frame positions detected by sonara.",
    "onset_frames": "Detected onset frame positions; shows where rhythmic or transient events begin.",
    "onset_density": "Onsets per second; a proxy for rhythmic activity.",
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
    "chord_sequence": "Chord labels over time.",
    "predominant_chord": "Most frequent chord in the analyzed track.",
    "chord_change_rate": "Chord changes per second; a harmonic complexity proxy.",
    "yin": "Fundamental frequency estimate from YIN pitch tracking.",
    "pyin": "Probabilistic YIN pitch estimate and voiced probabilities.",
    "piptrack": "Pitch salience tracks from spectral peaks.",
    "estimate_tuning": "Estimated tuning offset.",
    "pitch_tuning": "Pitch tuning estimated from detected pitches.",
    "salience": "Harmonic salience representation from spectral energy.",
    "detect_key": "Standalone key detection availability; Sonara playlist analysis also provides key/key_confidence.",
}


REQUESTED_FEATURE_KEYS = [
    "bpm",
    "beats",
    "tempo",
    "tempo_curve",
    "tempo_variability",
    "beat_track",
    "onset_detect",
    "onset_strength",
    "onset_strength_multi",
    "onset_density",
    "tempogram",
    "fourier_tempogram",
    "metrogram",
    "plp",
    "detect_time_signature",
    "loudness_lufs",
    "dynamic_range_db",
    "melspectrogram",
    "mfcc",
    "chroma_stft",
    "spectral_centroid",
    "spectral_bandwidth",
    "spectral_rolloff",
    "spectral_flatness",
    "spectral_contrast",
    "zero_crossing_rate",
    "poly_features",
    "hpcp",
    "chords_from_beats",
    "chords_from_frames",
    "chord_descriptors",
    "key_detection",
    "key_confidence",
    "chord_sequence",
    "predominant_chord",
    "chord_change_rate",
    "dissonance",
    "yin",
    "pyin",
    "piptrack",
    "estimate_tuning",
    "pitch_tuning",
    "salience",
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "detect_key",
]


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
    analysis_started = time.perf_counter()
    analysis, audio, sr, decode_note = _analyze_file_or_signal(sonara, track.path)
    analysis_seconds = time.perf_counter() - analysis_started

    y = audio
    summary_audio_note = "audio_not_loaded"
    y_summary = y
    if y_summary is not None:
        y_summary, summary_audio_note = _summary_audio_window(y_summary, sr)

    mel_payload: dict[str, object] = {}
    mel_seconds: float | None = None
    try:
        mel_started = time.perf_counter()
        if y_summary is None:
            y, sr = sonara.load(track.path, sr=22050)
            y_summary, summary_audio_note = _summary_audio_window(y, sr)
        mel = sonara.melspectrogram(y=y_summary, sr=float(sr))
        mel_db = sonara.power_to_db(mel)
        mel_payload = {
            "mel_spectrogram": _feature_payload(mel, "mel_spectrogram"),
            "melspectrogram": _feature_payload(mel, "melspectrogram"),
            "mel_spectrogram_db": _feature_payload(mel_db, "mel_spectrogram_db"),
        }
        mel_seconds = time.perf_counter() - mel_started
    except Exception as error:
        mel_payload = {"mel_spectrogram_error": {"value": str(error), "description": "Mel spectrogram extraction error."}}

    features = {str(key): _feature_payload(value, str(key)) for key, value in dict(analysis).items()}
    features.update(mel_payload)
    _fill_requested_feature_aliases(features)
    elapsed = time.perf_counter() - started
    features["analysis_seconds"] = {
        "value": analysis_seconds,
        "type": "float",
        "description": "Wall-clock seconds spent in sonara.analyze_file for this track.",
    }
    features["decode_path"] = {
        "value": decode_note,
        "type": "str",
        "description": "How audio was decoded before Sonara feature analysis.",
    }
    if mel_seconds is not None:
        features["mel_seconds"] = {
            "value": mel_seconds,
            "type": "float",
            "description": "Wall-clock seconds spent generating mel spectrogram values.",
        }
    features["summary_audio_window"] = {
        "value": summary_audio_note,
        "type": "str",
        "description": "Audio window used only for optional mel summary; Sonara full fused pipeline analyzes the track independently for BPM/key/tonal/perceptual summaries.",
    }
    features["total_seconds"] = {
        "value": elapsed,
        "type": "float",
        "description": "Total wall-clock seconds for sonara lab extraction and JSON preparation.",
    }
    features["requested_feature_count"] = {
        "value": len(REQUESTED_FEATURE_KEYS),
        "type": "int",
        "description": "Number of requested feature names explicitly represented in this JSON.",
    }

    db.save_sonara_features(
        track.id,
        features,
        bpm=_optional_float(analysis.get("bpm")),
        musical_key=_optional_string(analysis.get("key")),
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


def _analyze_file_or_signal(sonara: Any, path: str | Path) -> tuple[dict[str, object], np.ndarray | None, int, str]:
    try:
        return dict(sonara.analyze_file(str(path), sr=22050, mode=SONARA_ANALYSIS_MODE)), None, 22050, f"sonara.analyze_file(mode={SONARA_ANALYSIS_MODE})"
    except Exception as error:
        if Path(path).suffix.lower() not in {".wav", ".wave"}:
            raise
        audio, detail = _load_wav_fallback(path, sonara)
        analysis = dict(sonara.analyze_signal(audio, sr=22050, mode=SONARA_ANALYSIS_MODE))
        return analysis, audio, 22050, f"tolerant WAV fallback after analyze_file failed: {error}; {detail}"


def _load_wav_fallback(path: str | Path, sonara: Any) -> tuple[np.ndarray, str]:
    try:
        return _load_wav_with_ffmpeg(path)
    except Exception as ffmpeg_error:
        audio, sr_native, detail = _load_wav_tolerant(path)
        if sr_native != 22050:
            audio = sonara.resample(audio, orig_sr=sr_native, target_sr=22050)
        return audio, f"{detail}; ffmpeg fallback unavailable/failed: {ffmpeg_error}"


def _load_wav_with_ffmpeg(path: str | Path) -> tuple[np.ndarray, str]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found on PATH")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-ac",
        "1",
        "-ar",
        "22050",
        "-f",
        "f32le",
        "pipe:1",
    ]
    completed = subprocess.run(command, check=True, capture_output=True)
    if not completed.stdout:
        raise RuntimeError("ffmpeg produced no PCM samples")
    audio = np.frombuffer(completed.stdout, dtype="<f4").copy()
    return audio, f"decoded with ffmpeg to mono f32 PCM at 22050 Hz ({len(audio) / 22050:.1f}s)"


def _load_wav_tolerant(path: str | Path) -> tuple[np.ndarray, int, str]:
    audio_path = Path(path)
    try:
        with wave.open(str(audio_path), "rb") as audio:
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            sample_rate = audio.getframerate()
            expected_audio_bytes = audio.getnframes() * channels * sample_width
            raw = audio.readframes(audio.getnframes())
    except (EOFError, wave.Error) as error:
        raise RuntimeError(f"Tolerant WAV fallback cannot read header: {error}") from error
    if not raw:
        raise RuntimeError("Tolerant WAV fallback read no audio bytes")
    usable = len(raw) - (len(raw) % (channels * sample_width))
    raw = raw[:usable]
    samples = _decode_pcm_bytes(raw, sample_width)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    actual_payload_bytes = len(raw)
    detail = (
        f"read {actual_payload_bytes / 1_000_000:.1f} MB of PCM from WAV"
        f" (header expected {expected_audio_bytes / 1_000_000:.1f} MB)"
    )
    return samples.astype(np.float32, copy=False), sample_rate, detail


def _decode_pcm_bytes(raw: bytes, sample_width: int) -> np.ndarray:
    if sample_width == 1:
        return (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    if sample_width == 2:
        return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if sample_width == 3:
        data = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        values = data[:, 0].astype(np.int32) | (data[:, 1].astype(np.int32) << 8) | (data[:, 2].astype(np.int32) << 16)
        values = np.where(values & 0x800000, values - 0x1000000, values)
        return values.astype(np.float32) / 8388608.0
    if sample_width == 4:
        return np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    raise RuntimeError(f"Unsupported WAV sample width for fallback: {sample_width} bytes")


def _summary_audio_window(y: np.ndarray, sr: int) -> tuple[np.ndarray, str]:
    audio = np.asarray(y, dtype=np.float32)
    max_samples = max(1, int(float(sr) * SUMMARY_AUDIO_MAX_SECONDS))
    if audio.size <= max_samples:
        return audio, f"full decoded audio used for summary features ({audio.size / float(sr):.1f}s)"
    return audio[:max_samples], (
        f"first {SUMMARY_AUDIO_MAX_SECONDS:.0f}s used for array-like summary features "
        f"out of {audio.size / float(sr):.1f}s to keep CPU/RAM bounded"
    )


def _expanded_feature_payloads(
    sonara: Any,
    y: np.ndarray | None,
    sr: int,
    existing_features: dict[str, object],
) -> dict[str, object]:
    features: dict[str, object] = {}
    if y is None:
        return {
            key: _unavailable_payload(key, "audio_not_loaded")
            for key in REQUESTED_FEATURE_KEYS
            if key not in existing_features
        }

    hop_length = 512
    n_fft = 2048
    duration_sec = float(len(y) / float(sr)) if sr else 0.0
    stft = None
    power_spec = None
    freqs = None

    def add(name: str, value: object) -> object:
        features[name] = _feature_payload(value, name)
        return value

    def call(name: str, *args: object, **kwargs: object) -> object | None:
        func = getattr(sonara, name, None)
        if func is None:
            features[name] = _unavailable_payload(name, f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
            return None
        try:
            return add(name, func(*args, **kwargs))
        except Exception as error:
            features[name] = _error_payload(name, error)
            return None

    onset_strength = call("onset_strength", y, sr=int(sr), hop_length=hop_length)
    onset_frames = None
    onset_func = getattr(sonara, "onset_detect", None)
    if onset_func is None:
        features["onset_detect"] = _unavailable_payload("onset_detect", f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
    else:
        try:
            onset_frames = onset_func(y=y, onset_envelope=onset_strength, sr=int(sr), hop_length=hop_length)
            add("onset_detect", onset_frames)
        except Exception as error:
            features["onset_detect"] = _error_payload("onset_detect", error)

    beat_frames = None
    beat_func = getattr(sonara, "beat_track", None)
    if beat_func is None:
        features["beat_track"] = _unavailable_payload("beat_track", f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
    else:
        try:
            beat_result = beat_func(y=y, onset_envelope=onset_strength, sr=int(sr), hop_length=hop_length)
            if isinstance(beat_result, tuple) and len(beat_result) >= 2:
                tempo_value, beat_frames = beat_result[0], beat_result[1]
                features["tempo"] = _feature_payload(tempo_value, "tempo")
                features["beat_track"] = _feature_payload({"tempo": tempo_value, "beats": beat_frames}, "beat_track")
            else:
                add("beat_track", beat_result)
        except Exception as error:
            features["beat_track"] = _error_payload("beat_track", error)

    if beat_frames is None and "beats" in existing_features:
        raw_beats = existing_features["beats"]
        if isinstance(raw_beats, dict) and isinstance(raw_beats.get("value"), list):
            beat_frames = np.asarray(raw_beats["value"], dtype=np.float32)

    tempo_curve_func = getattr(sonara, "tempo_curve", None)
    tempo_curve = None
    if tempo_curve_func is None:
        features["tempo_curve"] = _unavailable_payload("tempo_curve", f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
    elif beat_frames is not None:
        try:
            tempo_curve = tempo_curve_func(beat_frames, sr=int(sr), hop_length=hop_length)
            add("tempo_curve", tempo_curve)
        except Exception as error:
            features["tempo_curve"] = _error_payload("tempo_curve", error)
    else:
        features["tempo_curve"] = _unavailable_payload("tempo_curve", "requires_beats")

    variability_func = getattr(sonara, "tempo_variability", None)
    if variability_func is None:
        features["tempo_variability"] = _unavailable_payload("tempo_variability", f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
    elif tempo_curve is not None:
        try:
            add("tempo_variability", variability_func(tempo_curve))
        except Exception as error:
            features["tempo_variability"] = _error_payload("tempo_variability", error)
    else:
        features["tempo_variability"] = _unavailable_payload("tempo_variability", "requires_tempo_curve")

    call("mfcc", y=y, sr=int(sr))
    call("chroma_stft", y=y, sr=int(sr))
    call("spectral_centroid", y=y, sr=int(sr))
    call("yin", y, fmin=50, fmax=2000, sr=int(sr), hop_length=hop_length)
    _add_pyin_features(sonara, y, sr, hop_length, features)
    pitch_values = _add_piptrack_features(sonara, y, sr, hop_length, features)
    call("estimate_tuning", y=y, sr=int(sr))
    _add_pitch_tuning(sonara, pitch_values, features)

    try:
        stft_func = getattr(sonara, "stft", None)
        freqs_func = getattr(sonara, "fft_frequencies", None)
        if stft_func is not None and freqs_func is not None:
            stft = stft_func(y, n_fft=n_fft, hop_length=hop_length)
            power_spec = np.abs(np.asarray(stft)) ** 2
            freqs = freqs_func(sr=int(sr), n_fft=n_fft)
    except Exception:
        stft = None
        power_spec = None
        freqs = None

    if power_spec is not None and freqs is not None:
        hpcp = call("hpcp", power_spec, freqs)
        if hpcp is not None:
            chords_beats_func = getattr(sonara, "chords_from_beats", None)
            if chords_beats_func is not None and beat_frames is not None:
                try:
                    add("chords_from_beats", chords_beats_func(hpcp, beat_frames))
                except Exception as error:
                    features["chords_from_beats"] = _error_payload("chords_from_beats", error)
            elif chords_beats_func is None:
                features["chords_from_beats"] = _unavailable_payload("chords_from_beats", f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
            else:
                features["chords_from_beats"] = _unavailable_payload("chords_from_beats", "requires_beats")

            chords_frames = call("chords_from_frames", hpcp)
            descriptors_func = getattr(sonara, "chord_descriptors", None)
            if descriptors_func is not None and chords_frames is not None:
                try:
                    add("chord_descriptors", descriptors_func(chords_frames, duration_sec))
                except Exception as error:
                    features["chord_descriptors"] = _error_payload("chord_descriptors", error)
            elif descriptors_func is None:
                features["chord_descriptors"] = _unavailable_payload("chord_descriptors", f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
        call("salience", power_spec, freqs, harmonics=[1, 2, 3, 4])
    else:
        for name in ("hpcp", "chords_from_beats", "chords_from_frames", "chord_descriptors", "salience"):
            features.setdefault(name, _unavailable_payload(name, "requires_stft_and_frequencies"))

    for name in ("onset_strength_multi", "tempogram", "fourier_tempogram", "metrogram", "plp", "poly_features"):
        if name not in features:
            func = getattr(sonara, name, None)
            if func is None:
                features[name] = _unavailable_payload(name, f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
            else:
                features[name] = _unavailable_payload(name, "exported_but_no_safe_default_call_signature_used")

    return features


def _add_pyin_features(
    sonara: Any,
    y: np.ndarray,
    sr: int,
    hop_length: int,
    features: dict[str, object],
) -> None:
    func = getattr(sonara, "pyin", None)
    if func is None:
        features["pyin"] = _unavailable_payload("pyin", f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
        return
    try:
        result = func(y, fmin=50, fmax=2000, sr=int(sr), hop_length=hop_length)
        if isinstance(result, tuple) and len(result) >= 3:
            f0, voiced_flag, voiced_prob = result[:3]
            features["pyin"] = _feature_payload(
                {
                    "f0": _serialize_value(f0, include_full_value=False),
                    "voiced_flag": _serialize_value(voiced_flag, include_full_value=False),
                    "voiced_probability": _serialize_value(voiced_prob, include_full_value=False),
                },
                "pyin",
            )
        else:
            features["pyin"] = _feature_payload(result, "pyin")
    except Exception as error:
        features["pyin"] = _error_payload("pyin", error)


def _add_piptrack_features(
    sonara: Any,
    y: np.ndarray,
    sr: int,
    hop_length: int,
    features: dict[str, object],
) -> np.ndarray | None:
    func = getattr(sonara, "piptrack", None)
    if func is None:
        features["piptrack"] = _unavailable_payload("piptrack", f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
        return None
    try:
        result = func(y, sr=int(sr), hop_length=hop_length)
        if isinstance(result, tuple) and len(result) >= 2:
            pitches, magnitudes = result[:2]
            pitch_array = np.asarray(pitches, dtype=np.float32)
            magnitude_array = np.asarray(magnitudes, dtype=np.float32)
            features["piptrack"] = _feature_payload(
                {
                    "pitches": _serialize_value(pitch_array, include_full_value=False),
                    "magnitudes": _serialize_value(magnitude_array, include_full_value=False),
                },
                "piptrack",
            )
            positive = pitch_array[pitch_array > 0]
            return positive[:5000] if positive.size else None
        features["piptrack"] = _feature_payload(result, "piptrack")
    except Exception as error:
        features["piptrack"] = _error_payload("piptrack", error)
    return None


def _add_pitch_tuning(sonara: Any, pitch_values: np.ndarray | None, features: dict[str, object]) -> None:
    func = getattr(sonara, "pitch_tuning", None)
    if func is None:
        features["pitch_tuning"] = _unavailable_payload("pitch_tuning", f"not_exported_by_sonara_{getattr(sonara, '__version__', 'unknown')}")
        return
    if pitch_values is None or not len(pitch_values):
        features["pitch_tuning"] = _unavailable_payload("pitch_tuning", "requires_detected_pitches")
        return
    try:
        features["pitch_tuning"] = _feature_payload(func(pitch_values), "pitch_tuning")
    except Exception as error:
        features["pitch_tuning"] = _error_payload("pitch_tuning", error)


def _fill_requested_feature_aliases(features: dict[str, object]) -> None:
    alias_pairs = {
        "tempo": "bpm",
        "melspectrogram": "mel_spectrogram",
        "beat_track": "beats",
        "onset_detect": "onset_frames",
        "mfcc": "mfcc_mean",
        "chroma_stft": "chroma_mean",
        "spectral_centroid": "spectral_centroid_mean",
        "key_detection": "key",
        "spectral_bandwidth": "spectral_bandwidth_mean",
        "spectral_rolloff": "spectral_rolloff_mean",
        "spectral_flatness": "spectral_flatness_mean",
        "spectral_contrast": "spectral_contrast_mean",
    }
    for target, source in alias_pairs.items():
        if target not in features and source in features:
            payload = dict(features[source]) if isinstance(features[source], dict) else _feature_payload(features[source], target)
            payload["description"] = FEATURE_DESCRIPTIONS.get(target, payload.get("description", "Sonara analysis feature."))
            payload["source_feature"] = source
            features[target] = payload

    if "detect_time_signature" not in features:
        if "time_signature" in features:
            payload = dict(features["time_signature"]) if isinstance(features["time_signature"], dict) else _feature_payload(features["time_signature"], "detect_time_signature")
            payload["description"] = FEATURE_DESCRIPTIONS["detect_time_signature"]
            payload["source_feature"] = "time_signature"
            features["detect_time_signature"] = payload
        else:
            features["detect_time_signature"] = _unavailable_payload("detect_time_signature", "not_produced_by_sonara_playlist_pipeline")

    if "detect_key" not in features:
        if "key" in features:
            payload = dict(features["key"]) if isinstance(features["key"], dict) else _feature_payload(features["key"], "detect_key")
            payload["description"] = FEATURE_DESCRIPTIONS["detect_key"]
            payload["source_feature"] = "key"
            payload["status"] = "fulfilled_by_sonara_playlist_key_analysis"
            features["detect_key"] = payload
        else:
            features["detect_key"] = _unavailable_payload("detect_key", "key_not_available")

    for key in REQUESTED_FEATURE_KEYS:
        features.setdefault(key, _unavailable_payload(key, "not_produced_by_this_run"))


def _unavailable_payload(name: str, reason: str) -> dict[str, object]:
    return {
        "value": None,
        "type": "unavailable",
        "status": reason,
        "description": FEATURE_DESCRIPTIONS.get(name, "Requested Sonara feature is not available in this run."),
    }


def _error_payload(name: str, error: Exception) -> dict[str, object]:
    return {
        "value": str(error),
        "type": "error",
        "status": "error",
        "description": FEATURE_DESCRIPTIONS.get(name, "Sonara feature extraction error."),
    }


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
