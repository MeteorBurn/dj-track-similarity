"""Canonical semantic validation for persisted SONARA Core rows."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Mapping
from dataclasses import fields
from typing import TypeAlias

import numpy as np

from .analysis_contracts import ContractIdentity
from .db_schema_v7 import SonaraRowV7


SonaraCoreRow: TypeAlias = SonaraRowV7 | Mapping[str, object] | sqlite3.Row

SONARA_CORE_COLUMNS = tuple(field.name for field in fields(SonaraRowV7))
SONARA_CORE_VECTOR_DIMS: Mapping[str, int] = {
    "mfcc_mean_blob": 13,
    "chroma_mean_blob": 12,
    "spectral_contrast_mean_blob": 7,
}

_UNIT_INTERVAL_FIELDS = (
    "bpm_confidence",
    "beat_grid_stability",
    "key_confidence",
    "energy_score",
    "danceability_score",
    "valence_score",
    "acousticness_score",
    "dissonance_score",
    "spectral_flatness",
    "zero_crossing_rate",
    "vocal_probability",
    "mood_happy_score",
    "mood_aggressive_score",
    "mood_relaxed_score",
    "mood_sad_score",
)
_NON_NEGATIVE_FIELDS = (
    "onset_density_per_second",
    "tempo_variability",
    "beat_grid_offset_seconds",
    "chord_changes_per_second",
    "spectral_centroid_hz",
    "spectral_bandwidth_hz",
    "spectral_rolloff_hz",
    "rms_mean",
    "rms_max",
    "dynamic_range_db",
    "loudness_range_lu",
    "analyzed_duration_seconds",
    "intro_end_seconds",
    "outro_start_seconds",
    "leading_silence_seconds",
    "trailing_silence_seconds",
)
_UNBOUNDED_FINITE_FIELDS = (
    "integrated_loudness_lufs",
    "true_peak_dbtp",
    "replay_gain_db",
    "max_momentary_loudness_lufs",
)
_OPTIONAL_TEXT_FIELDS = (
    "detected_key_name",
    "detected_key_camelot",
    "predominant_chord",
)
_ENERGY_CURVE_FIELDS = (
    "energy_curve_hop_seconds",
    "energy_curve_sample_count",
    "energy_curve_min",
    "energy_curve_max",
    "energy_curve_mean",
    "energy_curve_stddev",
)


def validate_sonara_core_row(
    row: SonaraCoreRow,
    *,
    expected_contract: ContractIdentity,
    expected_track_id: int,
    expected_content_generation: int,
) -> tuple[bool, str | None]:
    """Validate one complete SONARA Core row against writer semantics."""

    try:
        values = _row_values(row)
        _validate_identity(
            values,
            expected_contract=expected_contract,
            expected_track_id=expected_track_id,
            expected_content_generation=expected_content_generation,
        )
        _validate_scalars(values, expected_contract=expected_contract)
        _validate_candidate_json(values)
        _validate_vectors(values)
    except (TypeError, ValueError, OverflowError) as error:
        return False, str(error)
    return True, None


def _row_values(row: SonaraCoreRow) -> dict[str, object]:
    if isinstance(row, SonaraRowV7):
        return {column: getattr(row, column) for column in SONARA_CORE_COLUMNS}
    if isinstance(row, sqlite3.Row):
        available = set(row.keys())
        missing = sorted(set(SONARA_CORE_COLUMNS) - available)
        if missing:
            raise ValueError("SONARA Core row is missing fields: " + ", ".join(missing))
        return {column: row[column] for column in SONARA_CORE_COLUMNS}
    if isinstance(row, Mapping):
        missing = sorted(set(SONARA_CORE_COLUMNS) - set(row))
        if missing:
            raise ValueError("SONARA Core row is missing fields: " + ", ".join(missing))
        return {column: row[column] for column in SONARA_CORE_COLUMNS}
    raise TypeError("SONARA Core row must be a SonaraRowV7 or row mapping")


def _validate_identity(
    values: Mapping[str, object],
    *,
    expected_contract: ContractIdentity,
    expected_track_id: int,
    expected_content_generation: int,
) -> None:
    if (
        expected_contract.analysis_family,
        expected_contract.output_kind,
    ) != ("sonara", "core"):
        raise ValueError("expected contract must be a SONARA Core contract")
    track_id = _required_int(values["track_id"], "track_id", minimum=1)
    if track_id != expected_track_id:
        raise ValueError("track_id does not match the expected track")
    generation = _required_int(
        values["content_generation"],
        "content_generation",
        minimum=1,
    )
    if generation != expected_content_generation:
        raise ValueError("content_generation does not match the expected track")
    contract_hash = _required_text(values["contract_hash"], "contract_hash")
    if contract_hash != expected_contract.contract_hash:
        raise ValueError("contract_hash does not match the expected contract")
    _required_text(values["analyzed_at"], "analyzed_at")


def _validate_scalars(
    values: Mapping[str, object],
    *,
    expected_contract: ContractIdentity,
) -> None:
    bpm_min = _contract_number(expected_contract, "bpm_min")
    bpm_max = _contract_number(expected_contract, "bpm_max")
    if bpm_min >= bpm_max:
        raise ValueError("contract bpm_min must be lower than bpm_max")
    _optional_number(
        values["detected_bpm"],
        "detected_bpm",
        minimum=bpm_min,
        maximum=bpm_max,
    )
    _optional_number(
        values["raw_bpm"],
        "raw_bpm",
        minimum=0.0,
        strict_minimum=True,
    )
    for field_name in _UNIT_INTERVAL_FIELDS:
        _optional_number(
            values[field_name],
            field_name,
            minimum=0.0,
            maximum=1.0,
        )
    for field_name in _NON_NEGATIVE_FIELDS:
        _optional_number(
            values[field_name],
            field_name,
            minimum=0.0,
        )
    for field_name in _UNBOUNDED_FINITE_FIELDS:
        _optional_number(values[field_name], field_name)
    _optional_int(values["beat_count"], "beat_count", minimum=0)
    _optional_int(values["energy_level"], "energy_level", minimum=1, maximum=10)
    for field_name in _OPTIONAL_TEXT_FIELDS:
        _optional_text(values[field_name], field_name)
    _validate_structure(values)
    _validate_energy_curve(values)


def _validate_structure(values: Mapping[str, object]) -> None:
    duration = _optional_number(
        values["analyzed_duration_seconds"],
        "analyzed_duration_seconds",
        minimum=0.0,
    )
    intro_end = _optional_number(
        values["intro_end_seconds"],
        "intro_end_seconds",
        minimum=0.0,
    )
    outro_start = _optional_number(
        values["outro_start_seconds"],
        "outro_start_seconds",
        minimum=0.0,
    )
    if duration is not None:
        if intro_end is not None and intro_end > duration:
            raise ValueError(
                "intro_end_seconds must not exceed analyzed_duration_seconds"
            )
        if outro_start is not None and outro_start > duration:
            raise ValueError(
                "outro_start_seconds must not exceed analyzed_duration_seconds"
            )
    if intro_end is not None and outro_start is not None and intro_end > outro_start:
        raise ValueError("intro_end_seconds must not exceed outro_start_seconds")


def _validate_energy_curve(values: Mapping[str, object]) -> None:
    present = [values[field_name] is not None for field_name in _ENERGY_CURVE_FIELDS]
    if not any(present):
        return
    if not all(present):
        raise ValueError("energy curve summary fields must be all NULL or all present")
    _optional_number(
        values["energy_curve_hop_seconds"],
        "energy_curve_hop_seconds",
        minimum=0.0,
        strict_minimum=True,
    )
    _optional_int(
        values["energy_curve_sample_count"],
        "energy_curve_sample_count",
        minimum=1,
    )
    minimum = _optional_number(
        values["energy_curve_min"],
        "energy_curve_min",
        minimum=0.0,
        maximum=1.0,
    )
    maximum = _optional_number(
        values["energy_curve_max"],
        "energy_curve_max",
        minimum=0.0,
        maximum=1.0,
    )
    mean = _optional_number(
        values["energy_curve_mean"],
        "energy_curve_mean",
        minimum=0.0,
        maximum=1.0,
    )
    _optional_number(
        values["energy_curve_stddev"],
        "energy_curve_stddev",
        minimum=0.0,
    )
    assert minimum is not None and maximum is not None and mean is not None
    if not minimum <= mean <= maximum:
        raise ValueError("energy curve summary must satisfy minimum <= mean <= maximum")


def _validate_candidate_json(values: Mapping[str, object]) -> None:
    _validate_bpm_candidates(values["bpm_candidates_json"])
    _validate_key_candidates(
        values["key_candidates_json"],
        detected_key_name=values["detected_key_name"],
        detected_key_camelot=values["detected_key_camelot"],
    )


def _validate_bpm_candidates(raw: object) -> None:
    if raw is None:
        return
    candidates = _json_array(raw, "bpm_candidates_json")
    if len(candidates) > 5:
        raise ValueError("bpm_candidates_json must contain at most 5 entries")
    normalized: list[dict[str, float | int]] = []
    previous_score = math.inf
    for index, candidate in enumerate(candidates):
        field_name = f"bpm_candidates_json[{index}]"
        entry = _exact_object(candidate, field_name, {"rank", "bpm", "score"})
        rank = _required_int(entry["rank"], f"{field_name}.rank", minimum=1)
        if rank != index + 1:
            raise ValueError(f"{field_name}.rank must equal {index + 1}")
        bpm = _required_number(
            entry["bpm"],
            f"{field_name}.bpm",
            minimum=0.0,
            strict_minimum=True,
        )
        score = _required_number(entry["score"], f"{field_name}.score")
        if score > previous_score:
            raise ValueError("bpm_candidates_json must be sorted by descending score")
        previous_score = score
        normalized.append({"rank": rank, "bpm": bpm, "score": score})
    _require_canonical_json(raw, normalized, "bpm_candidates_json")


def _validate_key_candidates(
    raw: object,
    *,
    detected_key_name: object,
    detected_key_camelot: object,
) -> None:
    if raw is None:
        return
    candidates = _json_array(raw, "key_candidates_json")
    if len(candidates) > 3:
        raise ValueError("key_candidates_json must contain at most 3 entries")
    normalized: list[dict[str, float | int | str]] = []
    previous_score = math.inf
    for index, candidate in enumerate(candidates):
        field_name = f"key_candidates_json[{index}]"
        entry = _exact_object(
            candidate,
            field_name,
            {"rank", "key_name", "camelot", "score"},
        )
        rank = _required_int(entry["rank"], f"{field_name}.rank", minimum=1)
        if rank != index + 1:
            raise ValueError(f"{field_name}.rank must equal {index + 1}")
        key_name = _required_text(entry["key_name"], f"{field_name}.key_name")
        camelot = _required_text(entry["camelot"], f"{field_name}.camelot")
        score = _required_number(
            entry["score"],
            f"{field_name}.score",
            minimum=0.0,
            maximum=1.0,
        )
        if score > previous_score:
            raise ValueError("key_candidates_json must be sorted by descending score")
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
            raise ValueError(
                "first key_candidates_json entry must match detected_key_name"
            )
        if (
            detected_key_camelot is not None
            and first["camelot"] != detected_key_camelot
        ):
            raise ValueError(
                "first key_candidates_json entry must match detected_key_camelot"
            )
    _require_canonical_json(raw, normalized, "key_candidates_json")


def _validate_vectors(values: Mapping[str, object]) -> None:
    for field_name, dim in SONARA_CORE_VECTOR_DIMS.items():
        value = values[field_name]
        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise ValueError(f"{field_name} must be a float32-le BLOB")
        payload = bytes(value)
        if len(payload) != dim * 4:
            raise ValueError(
                f"{field_name} must contain exactly {dim} float32-le values"
            )
        vector = np.frombuffer(payload, dtype="<f4")
        if vector.shape != (dim,):
            raise ValueError(
                f"{field_name} must contain exactly {dim} float32-le values"
            )
        if not bool(np.all(np.isfinite(vector))):
            raise ValueError(f"{field_name} contains non-finite values")


def _contract_number(contract: ContractIdentity, field_name: str) -> float:
    if field_name not in contract.parameters:
        raise ValueError(f"SONARA Core contract is missing {field_name}")
    return _required_number(
        contract.parameters[field_name],
        f"contract.parameters.{field_name}",
    )


def _optional_number(
    value: object,
    field_name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    strict_minimum: bool = False,
) -> float | None:
    if value is None:
        return None
    return _required_number(
        value,
        field_name,
        minimum=minimum,
        maximum=maximum,
        strict_minimum=strict_minimum,
    )


def _required_number(
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
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    if minimum is not None and (
        number <= minimum if strict_minimum else number < minimum
    ):
        comparator = "greater than" if strict_minimum else "at least"
        raise ValueError(f"{field_name} must be {comparator} {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return number


def _optional_int(
    value: object,
    field_name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    if value is None:
        return None
    return _required_int(
        value,
        field_name,
        minimum=minimum,
        maximum=maximum,
    )


def _required_int(
    value: object,
    field_name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{field_name} must be an integer")
    number = int(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return number


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name)


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    return value


def _json_array(raw: object, field_name: str) -> list[object]:
    if not isinstance(raw, str):
        raise ValueError(f"{field_name} must be a JSON string")
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(f"{field_name} is not valid JSON") from error
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a JSON array")
    return value


def _exact_object(
    value: object,
    field_name: str,
    expected_keys: set[str],
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a JSON object")
    if set(value) != expected_keys:
        raise ValueError(f"{field_name} fields must be exactly {sorted(expected_keys)}")
    return value


def _require_canonical_json(
    raw: object,
    normalized: list[dict[str, object]],
    field_name: str,
) -> None:
    canonical = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    if raw != canonical:
        raise ValueError(f"{field_name} is not canonical SONARA JSON")
