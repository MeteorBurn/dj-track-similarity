"""Pure SONARA result conversion for the typed analysis repository."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence

import numpy as np

from ..analysis_models import (
    AnalysisCandidate,
    EmbeddingOutput,
    FingerprintOutput,
    SONARA_EMBEDDING_DIM,
    SonaraWrite,
    TimelineOutput,
    sonara_unit_interval,
)
from ..db.ddl import FLOAT32_LE, SonaraRow

# Stored timeline key -> analyzer result key.
_TIMELINE_SOURCE_KEYS = {
    "beats": "beats",
    "chord_events": "chord_events",
    "downbeats": "downbeats",
    "energy_curve": "energy_curve",
    "energy_curve_hop_seconds": "energy_curve_hop_sec",
    "loudness_curve": "loudness_curve",
    "segments": "segments",
    "tempo_curve": "tempo_curve",
}


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
    # Timeline is the frame-level evidence; Core summarizes the validated curves.
    timeline = _timeline_output(analysis, analyzed_at=analyzed_at)
    core = _sonara_core_row(
        candidate,
        analysis,
        timeline=timeline,
        analyzed_at=analyzed_at,
    )

    return SonaraWrite(
        target=candidate.target,
        core=core,
        timeline=timeline,
        embedding=EmbeddingOutput(
            family="sonara",
            vector=_float32_vector(
                analysis.get("embedding"),
                dim=SONARA_EMBEDDING_DIM,
                field_name="embedding",
            ),
            analyzed_at=analyzed_at,
        ),
        fingerprint=FingerprintOutput(
            value=_required_fingerprint_base64(analysis.get("fingerprint")),
            version=_required_positive_int(
                analysis.get("fingerprint_version"),
                "fingerprint_version",
            ),
            analyzed_at=analyzed_at,
        ),
    )


def _timeline_output(
    analysis: Mapping[str, object],
    *,
    analyzed_at: str,
) -> TimelineOutput:
    missing = sorted(
        source for source in _TIMELINE_SOURCE_KEYS.values() if analysis.get(source) is None
    )
    if missing:
        raise ValueError(f"SONARA timeline is incomplete; missing fields: {', '.join(missing)}")
    provenance = analysis.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("provenance must be a mapping")
    return TimelineOutput(
        payload={key: analysis[source] for key, source in _TIMELINE_SOURCE_KEYS.items()},
        sample_rate_hz=_required_positive_int(
            provenance.get("sample_rate"),
            "provenance.sample_rate",
        ),
        hop_length=_required_positive_int(
            provenance.get("hop_length"),
            "provenance.hop_length",
        ),
        analyzed_at=analyzed_at,
    )


def _sonara_core_row(
    candidate: AnalysisCandidate,
    analysis: Mapping[str, object],
    *,
    timeline: TimelineOutput,
    analyzed_at: str,
) -> SonaraRow:
    provenance = analysis.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("provenance must be a mapping")
    analysis_schema_version = _required_positive_int(
        provenance.get("schema_version"),
        "provenance.schema_version",
    )
    bpm_min = _required_float(
        provenance.get("bpm_min"),
        "provenance.bpm_min",
        minimum=0.0,
        strict_minimum=True,
    )
    bpm_max = _required_float(
        provenance.get("bpm_max"),
        "provenance.bpm_max",
        minimum=2 * bpm_min,
    )
    # Bound the detected value by the range this run actually analysed with,
    # which provenance carries above, not by a project-wide constant. SONARA
    # accepts any bounds, so a library analysed with a different range must not
    # have its own results rejected. The pair itself is not stored per row: the
    # library holds the one range every run is locked to.
    detected_bpm = _optional_float(
        analysis,
        "bpm",
        minimum=bpm_min,
        maximum=bpm_max,
    )
    raw_bpm = _optional_float(analysis, "bpm_raw", minimum=0.0, strict_minimum=True)
    bpm_confidence = _optional_unit_interval(
        analysis,
        "bpm_confidence",    )
    beat_count = len(timeline.payload["beats"])
    declared_beat_count = _optional_int(analysis, "n_beats", minimum=0)
    if declared_beat_count is not None and declared_beat_count != beat_count:
        raise ValueError("n_beats does not match the beats sequence")
    detected_key_name = _optional_text(analysis, "key")
    detected_key_camelot = _optional_text(analysis, "key_camelot")

    # Not FLOAT32_LE: the curve itself is stored as Timeline JSON. Only REAL
    # scalars derived from it are stored here, so this rounding is a precision
    # choice that must not follow a change to the BLOB encoding.
    energy_curve = np.asarray(timeline.payload["energy_curve"], dtype="<f4")
    energy_curve_hop_seconds = timeline.payload["energy_curve_hop_seconds"]
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
            "grid_stability",        ),
        bpm_candidates_json=_bpm_candidates_json(analysis.get("bpm_candidates")),
        detected_key_name=detected_key_name,
        detected_key_camelot=detected_key_camelot,
        key_confidence=_optional_unit_interval(
            analysis,
            "key_confidence",        ),
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
        ),
        energy_score=_optional_unit_interval(
            analysis,
            "energy",        ),
        energy_level=_optional_int(
            analysis,
            "energy_level",
            minimum=1,
            maximum=10,
        ),
        danceability_score=_optional_unit_interval(
            analysis,
            "danceability",        ),
        valence_score=_optional_unit_interval(
            analysis,
            "valence",        ),
        acousticness_score=_optional_unit_interval(
            analysis,
            "acousticness",        ),
        dissonance_score=_optional_unit_interval(
            analysis,
            "dissonance",        ),
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
            "spectral_flatness_mean",        ),
        zero_crossing_rate=_optional_unit_interval(
            analysis,
            "zero_crossing_rate",        ),
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
            "vocalness",        ),
        mood_happy_score=_optional_unit_interval(
            analysis,
            "mood_happy",        ),
        mood_aggressive_score=_optional_unit_interval(
            analysis,
            "mood_aggressive",        ),
        mood_relaxed_score=_optional_unit_interval(
            analysis,
            "mood_relaxed",        ),
        mood_sad_score=_optional_unit_interval(
            analysis,
            "mood_sad",        ),
        aggression_score=_optional_unit_interval(
            analysis,
            "aggression_score",        ),
        aggression_confidence=_optional_unit_interval(
            analysis,
            "aggression_confidence",        ),
        aggression_forcefulness=_optional_unit_interval(
            analysis,
            "aggression_forcefulness",        ),
        aggression_harshness=_optional_unit_interval(
            analysis,
            "aggression_harshness",        ),
        aggression_tension=_optional_unit_interval(
            analysis,
            "aggression_tension",        ),
        aggression_rhythm=_optional_unit_interval(
            analysis,
            "aggression_rhythm",        ),
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
        analysis_schema_version=analysis_schema_version,
        analyzed_at=analyzed_at,
    )


def _float32_vector(value: object, *, dim: int, field_name: str) -> np.ndarray:
    if value is None:
        raise ValueError(f"{field_name} is required")
    raw_vector = np.asarray(value)
    if raw_vector.dtype.kind not in "iuf":
        raise ValueError(f"{field_name} must contain only numbers")
    vector = np.asarray(raw_vector, dtype=FLOAT32_LE)
    if vector.ndim != 1 or vector.shape != (dim,):
        raise ValueError(f"{field_name} must contain exactly {dim} float32 values")
    if not bool(np.all(np.isfinite(vector))):
        raise ValueError(f"{field_name} contains non-finite values")
    return np.ascontiguousarray(vector, dtype=FLOAT32_LE)


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
) -> float | None:
    value = values.get(key)
    if value is None:
        return None
    return sonara_unit_interval(value, key)


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


def _required_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{field_name} must be a positive integer")
    result = int(value)
    if result <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return result


def _required_fingerprint_base64(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("fingerprint must be a base64 string")
    return value


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
        score = sonara_unit_interval(
            entry[2],
            f"key_candidates[{rank - 1}].score",
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
