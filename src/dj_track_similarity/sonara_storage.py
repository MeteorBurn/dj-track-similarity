"""Pure SONARA result conversion for the typed analysis repository."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence

import numpy as np

from .analysis_models import (
    AnalysisCandidate,
    EmbeddingOutput,
    SonaraWrite,
)
from .db_ddl import SonaraRow
from .sonara_runtime import (
    SONARA_BPM_MAX,
    SONARA_BPM_MIN,
    SONARA_UNIT_INTERVAL_EPSILON,
)

_IMPLEMENTED_UNIT_INTERVAL_CLAMP_FIELDS = frozenset(
    {
        "acousticness",
        "aggression_confidence",
        "aggression_forcefulness",
        "aggression_harshness",
        "aggression_rhythm",
        "aggression_score",
        "aggression_tension",
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
    analyzed_at: str,
) -> SonaraWrite:
    """Validate one analyzer result and convert it to a typed repository write."""

    if not isinstance(candidate, AnalysisCandidate):
        raise TypeError("candidate must be an AnalysisCandidate")
    if not isinstance(analysis, Mapping):
        raise TypeError("SONARA analysis result must be a mapping")
    core = _sonara_core_row(
        candidate,
        analysis,
        analyzed_at=analyzed_at,
    )

    return SonaraWrite(
        target=candidate.target,
        core=core,
        embedding=EmbeddingOutput(
            family="sonara",
            vector=_float32_vector(
                analysis.get("embedding"),
                dim=48,
                field_name="embedding",
            ),
            analyzed_at=analyzed_at,
        ),
    )


def _sonara_core_row(
    candidate: AnalysisCandidate,
    analysis: Mapping[str, object],
    *,
    analyzed_at: str,
) -> SonaraRow:
    detected_bpm = _optional_float(
        analysis,
        "bpm",
        minimum=float(SONARA_BPM_MIN),
        maximum=float(SONARA_BPM_MAX),
    )
    raw_bpm = _optional_float(analysis, "bpm_raw", minimum=0.0, strict_minimum=True)
    bpm_confidence = _optional_unit_interval(
        analysis,
        "bpm_confidence",
        epsilon=SONARA_UNIT_INTERVAL_EPSILON,
    )
    beat_count = _beat_count(analysis)
    detected_key_name = _optional_text(analysis, "key")
    detected_key_camelot = _optional_text(analysis, "key_camelot")

    energy_curve = _optional_float32_curve(
        analysis.get("energy_curve"),
        epsilon=SONARA_UNIT_INTERVAL_EPSILON,
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

    return SonaraRow(
        track_id=candidate.target.track_id,
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
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        bpm_candidates_json=_bpm_candidates_json(analysis.get("bpm_candidates")),
        detected_key_name=detected_key_name,
        detected_key_camelot=detected_key_camelot,
        key_confidence=_optional_unit_interval(
            analysis,
            "key_confidence",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
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
            unit_interval_epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        energy_score=_optional_unit_interval(
            analysis,
            "energy",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
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
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        valence_score=_optional_unit_interval(
            analysis,
            "valence",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        acousticness_score=_optional_unit_interval(
            analysis,
            "acousticness",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        dissonance_score=_optional_unit_interval(
            analysis,
            "dissonance",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
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
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        zero_crossing_rate=_optional_unit_interval(
            analysis,
            "zero_crossing_rate",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
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
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        mood_happy_score=_optional_unit_interval(
            analysis,
            "mood_happy",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        mood_aggressive_score=_optional_unit_interval(
            analysis,
            "mood_aggressive",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        mood_relaxed_score=_optional_unit_interval(
            analysis,
            "mood_relaxed",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        mood_sad_score=_optional_unit_interval(
            analysis,
            "mood_sad",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        aggression_score=_optional_unit_interval(
            analysis,
            "aggression_score",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        aggression_confidence=_optional_unit_interval(
            analysis,
            "aggression_confidence",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        aggression_forcefulness=_optional_unit_interval(
            analysis,
            "aggression_forcefulness",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        aggression_harshness=_optional_unit_interval(
            analysis,
            "aggression_harshness",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        aggression_tension=_optional_unit_interval(
            analysis,
            "aggression_tension",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
        ),
        aggression_rhythm=_optional_unit_interval(
            analysis,
            "aggression_rhythm",
            epsilon=SONARA_UNIT_INTERVAL_EPSILON,
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
