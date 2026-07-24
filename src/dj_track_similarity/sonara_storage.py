"""Pure SONARA result conversion for the typed v7 analysis repository."""

from __future__ import annotations

import base64
import binascii
import json
import math
from collections.abc import Mapping, Sequence

import numpy as np

from .analysis_models import (
    AnalysisCandidate,
    EmbeddingOutput,
    SonaraFingerprintOutput,
    SonaraTimelineOutput,
    SonaraWrite,
)
from .db_schema_v7 import SonaraRowV7
from .sonara_contract import (
    SonaraContractSet,
    normalize_sonara_outputs,
    sonara_requested_features,
)


SONARA_TIMELINE_KEYS = (
    "beats",
    "onset_frames",
    "chord_sequence",
    "chord_events",
    "tempo_curve",
    "downbeats",
    "energy_curve",
    "segments",
    "loudness_curve",
)

_IMPLEMENTED_UNIT_INTERVAL_CLAMP_FIELDS = frozenset(
    {
        "acousticness",
        "bpm_confidence",
        "danceability",
        "dissonance",
        "energy",
        "energy_curve[]",
        "grid_stability",
        "key_candidates[].score",
        "key_confidence",
        "mood_aggressive",
        "mood_happy",
        "mood_relaxed",
        "mood_sad",
        "segments[].energy",
        "spectral_flatness_mean",
        "valence",
        "vocalness",
        "zero_crossing_rate",
    }
)


def prepare_sonara_write(
    candidate: AnalysisCandidate,
    analysis: Mapping[str, object],
    *,
    contracts: SonaraContractSet,
    outputs: Sequence[str] | None,
    analyzed_at: str,
) -> SonaraWrite:
    """Validate one analyzer result and convert it to a typed repository write."""

    if not isinstance(candidate, AnalysisCandidate):
        raise TypeError("candidate must be an AnalysisCandidate")
    if not isinstance(analysis, Mapping):
        raise TypeError("SONARA analysis result must be a mapping")
    declared_clamp_fields = frozenset(contracts.runtime.unit_interval_clamp_fields)
    if declared_clamp_fields != _IMPLEMENTED_UNIT_INTERVAL_CLAMP_FIELDS:
        raise ValueError(
            "SONARA unit-interval clamp field contract does not match "
            "the converter implementation"
        )
    selected = normalize_sonara_outputs(outputs)
    requested_features = sonara_requested_features(runtime=contracts.runtime)
    _validate_provenance(
        analysis,
        contracts=contracts,
        requested_features=requested_features,
    )

    core = _sonara_core_row(
        candidate,
        analysis,
        contracts=contracts,
        analyzed_at=analyzed_at,
    )

    timeline = None
    if "timeline" in selected:
        timeline_payload = _timeline_payload(
            analysis,
            unit_interval_epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        )
        timeline = SonaraTimelineOutput(
            contract=contracts.timeline,
            payload=timeline_payload,
            analyzed_at=analyzed_at,
        )

    similarity_embedding = None
    if "embedding" in selected:
        embedding_version = _required_positive_int(
            analysis.get("embedding_version"),
            "embedding_version",
        )
        if embedding_version != contracts.runtime.embedding_version:
            raise ValueError(
                "SONARA embedding_version does not match the active runtime contract"
            )
        vector = _float32_vector(
            analysis.get("embedding"),
            dim=contracts.runtime.embedding_dim,
            field_name="embedding",
        )
        similarity_embedding = EmbeddingOutput(
            contract=contracts.embedding,
            vector=vector,
            analyzed_at=analyzed_at,
        )

    fingerprint = None
    if "fingerprint" in selected:
        fingerprint_version = _required_positive_int(
            analysis.get("fingerprint_version"),
            "fingerprint_version",
        )
        if fingerprint_version != contracts.runtime.fingerprint_version:
            raise ValueError(
                "SONARA fingerprint_version does not match the active runtime contract"
            )
        words = _decode_fingerprint_words(analysis.get("fingerprint"))
        fingerprint = SonaraFingerprintOutput(
            contract=contracts.fingerprint,
            fingerprint_version=str(fingerprint_version),
            words=words,
            analyzed_at=analyzed_at,
        )

    return SonaraWrite(
        target=candidate.target,
        core_contract=contracts.core,
        core=core,
        timeline=timeline,
        similarity_embedding=similarity_embedding,
        fingerprint=fingerprint,
    )


def _validate_provenance(
    analysis: Mapping[str, object],
    *,
    contracts: SonaraContractSet,
    requested_features: tuple[str, ...],
) -> None:
    provenance = analysis.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("SONARA result provenance must be an object")
    runtime = contracts.runtime
    expected = {
        "schema_version": runtime.schema_version,
        "sample_rate": runtime.sample_rate_hz,
        "hop_length": runtime.analysis_hop_samples,
        "mode": runtime.mode,
    }
    for field_name, expected_value in expected.items():
        if provenance.get(field_name) != expected_value:
            raise ValueError(
                f"SONARA provenance {field_name} does not match the active runtime"
            )
    raw_features = provenance.get("requested_features")
    if not isinstance(raw_features, (list, tuple)) or any(
        not isinstance(feature, str) or not feature.strip() for feature in raw_features
    ):
        raise ValueError(
            "SONARA provenance requested_features must be a list of strings"
        )
    if tuple(raw_features) != requested_features:
        raise ValueError(
            "SONARA provenance requested_features do not match the requested outputs"
        )
    if "vocalness" in requested_features:
        if provenance.get("vocalness_model_id") != runtime.vocalness_model_id:
            raise ValueError(
                "SONARA provenance vocalness_model_id does not match the active runtime"
            )
    package_version = provenance.get("package_version")
    if package_version is not None and package_version != runtime.package_version:
        raise ValueError(
            "SONARA provenance package_version does not match the active runtime"
        )


def _sonara_core_row(
    candidate: AnalysisCandidate,
    analysis: Mapping[str, object],
    *,
    contracts: SonaraContractSet,
    analyzed_at: str,
) -> SonaraRowV7:
    detected_bpm = _optional_float(
        analysis,
        "bpm",
        minimum=float(contracts.runtime.bpm_min),
        maximum=float(contracts.runtime.bpm_max),
    )
    raw_bpm = _optional_float(analysis, "bpm_raw", minimum=0.0, strict_minimum=True)
    bpm_confidence = _optional_unit_interval(
        analysis,
        "bpm_confidence",
        epsilon=contracts.runtime.unit_interval_clamp_epsilon,
    )
    beat_count = _beat_count(analysis)
    detected_key_name = _optional_text(analysis, "key")
    detected_key_camelot = _optional_text(analysis, "key_camelot")

    energy_curve = _optional_float32_curve(
        analysis.get("energy_curve"),
        epsilon=contracts.runtime.unit_interval_clamp_epsilon,
    )
    if energy_curve is None:
        energy_curve_hop_seconds = _optional_float(
            analysis,
            "energy_curve_hop_sec",
            minimum=0.0,
            strict_minimum=True,
        )
        if energy_curve_hop_seconds is not None:
            raise ValueError(
                "energy_curve_hop_sec requires a finite one-dimensional energy_curve"
            )
        energy_curve_sample_count = None
        energy_curve_min = None
        energy_curve_max = None
        energy_curve_mean = None
        energy_curve_stddev = None
    else:
        energy_curve_hop_seconds = _required_float(
            analysis.get("energy_curve_hop_sec"),
            "energy_curve_hop_sec",
            minimum=0.0,
            strict_minimum=True,
        )
        energy_curve_sample_count = int(energy_curve.size)
        energy_curve_min = float(np.min(energy_curve))
        energy_curve_max = float(np.max(energy_curve))
        energy_curve_mean = float(np.mean(energy_curve, dtype=np.float64))
        energy_curve_stddev = float(np.std(energy_curve, dtype=np.float64))

    duration = _optional_float(
        analysis,
        "duration_sec",
        minimum=0.0,
    )
    intro_end = _optional_float(analysis, "intro_end_sec", minimum=0.0)
    outro_start = _optional_float(analysis, "outro_start_sec", minimum=0.0)
    if duration is not None:
        for field_name, value in (
            ("intro_end_sec", intro_end),
            ("outro_start_sec", outro_start),
        ):
            if value is not None and value > duration:
                raise ValueError(f"{field_name} must not exceed duration_sec")
    if intro_end is not None and outro_start is not None and intro_end > outro_start:
        raise ValueError("intro_end_sec must not exceed outro_start_sec")

    return SonaraRowV7(
        track_id=candidate.target.track_id,
        content_generation=candidate.target.content_generation,
        contract_hash=contracts.core.contract_hash,
        detected_bpm=detected_bpm,
        raw_bpm=raw_bpm,
        bpm_confidence=bpm_confidence,
        onset_density_per_second=_optional_float(
            analysis,
            "onset_density",
            minimum=0.0,
        ),
        beat_count=beat_count,
        tempo_variability=_optional_float(
            analysis,
            "tempo_variability",
            minimum=0.0,
        ),
        beat_grid_offset_seconds=_optional_float(
            analysis,
            "grid_offset_sec",
            minimum=0.0,
        ),
        beat_grid_stability=_optional_unit_interval(
            analysis,
            "grid_stability",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        bpm_candidates_json=_bpm_candidates_json(analysis.get("bpm_candidates")),
        detected_key_name=detected_key_name,
        detected_key_camelot=detected_key_camelot,
        key_confidence=_optional_unit_interval(
            analysis,
            "key_confidence",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        predominant_chord=_optional_text(analysis, "predominant_chord"),
        chord_changes_per_second=_optional_float(
            analysis,
            "chord_change_rate",
            minimum=0.0,
        ),
        key_candidates_json=_key_candidates_json(
            analysis.get("key_candidates"),
            detected_key_name=detected_key_name,
            detected_key_camelot=detected_key_camelot,
            unit_interval_epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        energy_score=_optional_unit_interval(
            analysis,
            "energy",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        energy_level=_optional_int(
            analysis,
            "energy_level",
            minimum=1,
            maximum=10,
        ),
        danceability_score=_optional_unit_interval(
            analysis,
            "danceability",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        valence_score=_optional_unit_interval(
            analysis,
            "valence",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        acousticness_score=_optional_unit_interval(
            analysis,
            "acousticness",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        dissonance_score=_optional_unit_interval(
            analysis,
            "dissonance",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        spectral_centroid_hz=_optional_float(
            analysis,
            "spectral_centroid_mean",
            minimum=0.0,
        ),
        spectral_bandwidth_hz=_optional_float(
            analysis,
            "spectral_bandwidth_mean",
            minimum=0.0,
        ),
        spectral_rolloff_hz=_optional_float(
            analysis,
            "spectral_rolloff_mean",
            minimum=0.0,
        ),
        spectral_flatness=_optional_unit_interval(
            analysis,
            "spectral_flatness_mean",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        zero_crossing_rate=_optional_unit_interval(
            analysis,
            "zero_crossing_rate",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        rms_mean=_optional_float(analysis, "rms_mean", minimum=0.0),
        rms_max=_optional_float(analysis, "rms_max", minimum=0.0),
        integrated_loudness_lufs=_optional_float(analysis, "loudness_lufs"),
        dynamic_range_db=_optional_float(
            analysis,
            "dynamic_range_db",
            minimum=0.0,
        ),
        true_peak_dbtp=_optional_float(analysis, "true_peak_db"),
        replay_gain_db=_optional_float(analysis, "replaygain_db"),
        max_momentary_loudness_lufs=_optional_float(
            analysis,
            "loudness_momentary_max_db",
        ),
        loudness_range_lu=_optional_float(
            analysis,
            "loudness_range_lu",
            minimum=0.0,
        ),
        analyzed_duration_seconds=duration,
        intro_end_seconds=intro_end,
        outro_start_seconds=outro_start,
        leading_silence_seconds=_optional_float(
            analysis,
            "leading_silence_sec",
            minimum=0.0,
        ),
        trailing_silence_seconds=_optional_float(
            analysis,
            "trailing_silence_sec",
            minimum=0.0,
        ),
        energy_curve_hop_seconds=energy_curve_hop_seconds,
        energy_curve_sample_count=energy_curve_sample_count,
        energy_curve_min=energy_curve_min,
        energy_curve_max=energy_curve_max,
        energy_curve_mean=energy_curve_mean,
        energy_curve_stddev=energy_curve_stddev,
        vocal_probability=_optional_unit_interval(
            analysis,
            "vocalness",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        mood_happy_score=_optional_unit_interval(
            analysis,
            "mood_happy",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        mood_aggressive_score=_optional_unit_interval(
            analysis,
            "mood_aggressive",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        mood_relaxed_score=_optional_unit_interval(
            analysis,
            "mood_relaxed",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        mood_sad_score=_optional_unit_interval(
            analysis,
            "mood_sad",
            epsilon=contracts.runtime.unit_interval_clamp_epsilon,
        ),
        mfcc_mean_blob=_float32_blob(analysis.get("mfcc_mean"), 13, "mfcc_mean"),
        chroma_mean_blob=_float32_blob(
            analysis.get("chroma_mean"),
            12,
            "chroma_mean",
        ),
        spectral_contrast_mean_blob=_float32_blob(
            analysis.get("spectral_contrast_mean"),
            7,
            "spectral_contrast_mean",
        ),
        analyzed_at=analyzed_at,
    )


def _beat_count(analysis: Mapping[str, object]) -> int | None:
    declared = _optional_int(analysis, "n_beats", minimum=0)
    raw_beats = analysis.get("beats")
    if raw_beats is None:
        return declared
    beats = _frame_indices(raw_beats, "beats")
    count = len(beats)
    if declared is not None and declared != count:
        raise ValueError("n_beats does not match the beats sequence")
    return count


def _optional_float32_curve(
    value: object,
    *,
    epsilon: float,
) -> np.ndarray | None:
    if value is None:
        return None
    raw_curve = np.asarray(value)
    if raw_curve.dtype.kind not in "iuf":
        raise ValueError("energy_curve must contain only numbers")
    if raw_curve.ndim != 1 or not raw_curve.size:
        raise ValueError("energy_curve must be a non-empty one-dimensional vector")
    clamped = [
        _unit_interval(
            child,
            f"energy_curve[{index}]",
            epsilon=epsilon,
        )
        for index, child in enumerate(raw_curve)
    ]
    curve = np.asarray(clamped, dtype="<f4")
    return curve


def _float32_vector(value: object, *, dim: int, field_name: str) -> np.ndarray:
    if value is None:
        raise ValueError(f"{field_name} is required")
    raw_vector = np.asarray(value)
    if raw_vector.dtype.kind not in "iuf":
        raise ValueError(f"{field_name} must contain only numbers")
    vector = np.asarray(raw_vector, dtype="<f4")
    if vector.ndim != 1 or vector.shape != (dim,):
        raise ValueError(f"{field_name} must contain exactly {dim} float32 values")
    if not bool(np.all(np.isfinite(vector))):
        raise ValueError(f"{field_name} contains non-finite values")
    return np.ascontiguousarray(vector, dtype="<f4")


def _float32_blob(value: object, dim: int, field_name: str) -> bytes:
    return _float32_vector(value, dim=dim, field_name=field_name).tobytes(order="C")


def _decode_fingerprint_words(value: object) -> np.ndarray:
    if not isinstance(value, str) or not value:
        raise ValueError("fingerprint must be a non-empty base64 string")
    try:
        payload = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError("fingerprint must be strict base64") from error
    if not payload or len(payload) % 4:
        raise ValueError("fingerprint must encode one or more complete uint32-le words")
    return np.frombuffer(payload, dtype="<u4").copy()


def _required_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{field_name} must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return result


def _required_float(
    value: object,
    field_name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    strict_minimum: bool = False,
) -> float:
    if isinstance(value, bool) or not isinstance(
        value,
        (int, float, np.integer, np.floating),
    ):
        raise ValueError(f"{field_name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be a finite number")
    if minimum is not None and (
        result <= minimum if strict_minimum else result < minimum
    ):
        comparator = "greater than" if strict_minimum else "at least"
        raise ValueError(f"{field_name} must be {comparator} {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return result


def _optional_float(
    values: Mapping[str, object],
    key: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    strict_minimum: bool = False,
) -> float | None:
    value = values.get(key)
    if value is None:
        return None
    return _required_float(
        value,
        key,
        minimum=minimum,
        maximum=maximum,
        strict_minimum=strict_minimum,
    )


def _optional_unit_interval(
    values: Mapping[str, object],
    key: str,
    *,
    epsilon: float,
) -> float | None:
    value = values.get(key)
    if value is None:
        return None
    return _unit_interval(value, key, epsilon=epsilon)


def _unit_interval(
    value: object,
    field_name: str,
    *,
    epsilon: float,
) -> float:
    number = _required_float(value, field_name)
    lower_bound = _float32_policy_bound(-epsilon)
    upper_bound = _float32_policy_bound(1.0 + epsilon)
    if number < lower_bound or number > upper_bound:
        raise ValueError(
            f"{field_name} is outside the unit interval by more than "
            f"the allowed epsilon {epsilon:g}"
        )
    return min(1.0, max(0.0, number))


def _float32_policy_bound(boundary: float) -> float:
    """Represent a policy boundary in SONARA's upstream f32 precision."""

    return float(np.float32(boundary))


def _optional_int(
    values: Mapping[str, object],
    key: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    value = values.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{key} must be an integer")
    result = int(value)
    if minimum is not None and result < minimum:
        raise ValueError(f"{key} must be at least {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{key} must be at most {maximum}")
    return result


def _optional_text(values: Mapping[str, object], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _bpm_candidates_json(value: object) -> str | None:
    if value is None:
        return None
    candidates = _candidate_sequence(value, "bpm_candidates")
    if len(candidates) > 5:
        raise ValueError("bpm_candidates must contain at most 5 entries")
    normalized: list[dict[str, float | int]] = []
    previous_score = math.inf
    for rank, candidate in enumerate(candidates, start=1):
        if not _is_non_text_sequence(candidate) or len(candidate) != 2:
            raise ValueError("bpm_candidates entries must be raw (bpm, score) pairs")
        entry = candidate
        bpm = _required_float(
            entry[0],
            f"bpm_candidates[{rank - 1}].bpm",
            minimum=0.0,
            strict_minimum=True,
        )
        score = _required_float(
            entry[1],
            f"bpm_candidates[{rank - 1}].score",
        )
        if score > previous_score:
            raise ValueError("bpm_candidates must be sorted by descending score")
        previous_score = score
        normalized.append({"rank": rank, "bpm": bpm, "score": score})
    return _canonical_json_array(normalized)


def _key_candidates_json(
    value: object,
    *,
    detected_key_name: str | None,
    detected_key_camelot: str | None,
    unit_interval_epsilon: float,
) -> str | None:
    if value is None:
        return None
    candidates = _candidate_sequence(value, "key_candidates")
    if len(candidates) > 3:
        raise ValueError("key_candidates must contain at most 3 entries")
    normalized: list[dict[str, float | int | str]] = []
    previous_score = math.inf
    for rank, candidate in enumerate(candidates, start=1):
        if not _is_non_text_sequence(candidate) or len(candidate) != 3:
            raise ValueError(
                "key_candidates entries must be raw (key_name, camelot, score) triples"
            )
        entry = candidate
        key_name = _required_candidate_text(
            entry[0],
            f"key_candidates[{rank - 1}].key_name",
        )
        camelot = _required_candidate_text(
            entry[1],
            f"key_candidates[{rank - 1}].camelot",
        )
        score = _unit_interval(
            entry[2],
            f"key_candidates[{rank - 1}].score",
            epsilon=unit_interval_epsilon,
        )
        if score > previous_score:
            raise ValueError("key_candidates must be sorted by descending score")
        previous_score = score
        normalized.append(
            {
                "rank": rank,
                "key_name": key_name,
                "camelot": camelot,
                "score": score,
            }
        )
    if normalized:
        first = normalized[0]
        if detected_key_name is not None and first["key_name"] != detected_key_name:
            raise ValueError("first key_candidates entry must match the detected key")
        if (
            detected_key_camelot is not None
            and first["camelot"] != detected_key_camelot
        ):
            raise ValueError(
                "first key_candidates entry must match detected key_camelot"
            )
    return _canonical_json_array(normalized)


def _candidate_sequence(value: object, field_name: str) -> Sequence[object]:
    if not _is_non_text_sequence(value):
        raise ValueError(f"{field_name} must be a sequence")
    return value


def _is_non_text_sequence(value: object) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (bytes, bytearray, memoryview, str),
    )


def _required_candidate_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _canonical_json_array(value: list[dict[str, object]]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _timeline_payload(
    analysis: Mapping[str, object],
    *,
    unit_interval_epsilon: float,
) -> dict[str, object]:
    missing = [key for key in SONARA_TIMELINE_KEYS if analysis.get(key) is None]
    if missing:
        raise ValueError(
            "SONARA timeline output is incomplete; "
            f"missing fields: {', '.join(missing)}"
        )

    beats = _frame_indices(analysis["beats"], "timeline.beats")
    onset_frames = _frame_indices(
        analysis["onset_frames"],
        "timeline.onset_frames",
    )
    downbeats = _frame_indices(analysis["downbeats"], "timeline.downbeats")
    if not set(downbeats).issubset(beats):
        raise ValueError("timeline.downbeats must be a subset of timeline.beats")

    tempo_curve = _finite_number_sequence(
        analysis["tempo_curve"],
        "timeline.tempo_curve",
        minimum=0.0,
        strict_minimum=True,
    )
    expected_tempo_count = max(len(beats) - 1, 0)
    if len(tempo_curve) != expected_tempo_count:
        raise ValueError(
            "timeline.tempo_curve length must equal max(len(beats) - 1, 0)"
        )

    energy_curve = _optional_float32_curve(
        analysis["energy_curve"],
        epsilon=unit_interval_epsilon,
    )
    if energy_curve is None:
        raise ValueError("timeline.energy_curve is required")

    duration = _optional_float(analysis, "duration_sec", minimum=0.0)
    return {
        "beats": beats,
        "onset_frames": onset_frames,
        "chord_sequence": _text_sequence(
            analysis["chord_sequence"],
            "timeline.chord_sequence",
        ),
        "chord_events": _timed_label_events(
            analysis["chord_events"],
            "timeline.chord_events",
            duration=duration,
        ),
        "tempo_curve": tempo_curve,
        "downbeats": downbeats,
        "energy_curve": energy_curve.astype(float).tolist(),
        "segments": _energy_segments(
            analysis["segments"],
            duration=duration,
            unit_interval_epsilon=unit_interval_epsilon,
        ),
        "loudness_curve": _finite_number_sequence(
            analysis["loudness_curve"],
            "timeline.loudness_curve",
        ),
    }


def _frame_indices(value: object, field_name: str) -> list[int]:
    array = np.asarray(value)
    if array.ndim != 1:
        raise ValueError(f"{field_name} must be one-dimensional")
    normalized: list[int] = []
    previous = -1
    for index, raw_value in enumerate(array.tolist()):
        if isinstance(raw_value, bool) or not isinstance(
            raw_value,
            (int, np.integer),
        ):
            raise ValueError(
                f"{field_name}[{index}] must be a non-negative frame integer"
            )
        frame = int(raw_value)
        if frame < 0:
            raise ValueError(
                f"{field_name}[{index}] must be a non-negative frame integer"
            )
        if frame <= previous:
            raise ValueError(f"{field_name} must be strictly increasing")
        previous = frame
        normalized.append(frame)
    return normalized


def _finite_number_sequence(
    value: object,
    field_name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    strict_minimum: bool = False,
) -> list[float]:
    if not _is_non_text_sequence(value) and not isinstance(value, np.ndarray):
        raise ValueError(f"{field_name} must be a sequence")
    return [
        _required_float(
            child,
            f"{field_name}[{index}]",
            minimum=minimum,
            maximum=maximum,
            strict_minimum=strict_minimum,
        )
        for index, child in enumerate(value)
    ]


def _text_sequence(value: object, field_name: str) -> list[str]:
    sequence = _candidate_sequence(value, field_name)
    return [
        _required_candidate_text(child, f"{field_name}[{index}]")
        for index, child in enumerate(sequence)
    ]


def _timed_label_events(
    value: object,
    field_name: str,
    *,
    duration: float | None,
) -> list[dict[str, object]]:
    sequence = _candidate_sequence(value, field_name)
    normalized: list[dict[str, object]] = []
    previous_end = 0.0
    for index, event in enumerate(sequence):
        if not isinstance(event, Mapping) or set(event) != {
            "label",
            "start_sec",
            "end_sec",
        }:
            raise ValueError(
                f"{field_name}[{index}] must contain exactly "
                "label, start_sec, and end_sec"
            )
        label = _required_candidate_text(
            event["label"],
            f"{field_name}[{index}].label",
        )
        start = _required_float(
            event["start_sec"],
            f"{field_name}[{index}].start_sec",
            minimum=0.0,
        )
        end = _required_float(
            event["end_sec"],
            f"{field_name}[{index}].end_sec",
            minimum=0.0,
        )
        if end < start:
            raise ValueError(f"{field_name}[{index}] end_sec precedes start_sec")
        if start < previous_end:
            raise ValueError(f"{field_name} events must not overlap")
        if duration is not None and end > duration:
            raise ValueError(f"{field_name}[{index}] exceeds duration_sec")
        previous_end = end
        normalized.append({"label": label, "start_sec": start, "end_sec": end})
    return normalized


def _energy_segments(
    value: object,
    *,
    duration: float | None,
    unit_interval_epsilon: float,
) -> list[dict[str, float]]:
    field_name = "timeline.segments"
    sequence = _candidate_sequence(value, field_name)
    normalized: list[dict[str, float]] = []
    previous_end = 0.0
    for index, segment in enumerate(sequence):
        if not isinstance(segment, Mapping) or set(segment) != {
            "start_sec",
            "end_sec",
            "energy",
        }:
            raise ValueError(
                f"{field_name}[{index}] must contain exactly "
                "start_sec, end_sec, and energy"
            )
        start = _required_float(
            segment["start_sec"],
            f"{field_name}[{index}].start_sec",
            minimum=0.0,
        )
        end = _required_float(
            segment["end_sec"],
            f"{field_name}[{index}].end_sec",
            minimum=0.0,
        )
        energy = _unit_interval(
            segment["energy"],
            f"{field_name}[{index}].energy",
            epsilon=unit_interval_epsilon,
        )
        if end <= start:
            raise ValueError(
                f"{field_name}[{index}] end_sec must be greater than start_sec"
            )
        if start < previous_end:
            raise ValueError(f"{field_name} entries must not overlap")
        if duration is not None and end > duration:
            raise ValueError(f"{field_name}[{index}] exceeds duration_sec")
        previous_end = end
        normalized.append({"start_sec": start, "end_sec": end, "energy": energy})
    return normalized
