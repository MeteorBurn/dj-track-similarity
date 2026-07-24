"""Canonical semantic validation for persisted MAEST analysis rows."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Mapping
from typing import TypeAlias

from .analysis_contracts import ContractIdentity


MaestAnalysisRow: TypeAlias = Mapping[str, object] | sqlite3.Row

MAEST_ANALYSIS_COLUMNS = (
    "track_id",
    "content_generation",
    "contract_hash",
    "syncopated_rhythm",
    "genres_json",
    "analyzed_at",
)


def validate_maest_analysis_row(
    row: MaestAnalysisRow,
    *,
    expected_contract: ContractIdentity,
    expected_track_id: int,
    expected_content_generation: int,
) -> tuple[bool, str | None]:
    """Validate one complete MAEST analysis row against writer semantics."""

    try:
        values = _row_values(row)
        if (
            expected_contract.analysis_family,
            expected_contract.output_kind,
        ) != ("maest", "analysis"):
            raise ValueError("expected contract must be a MAEST analysis contract")
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
        syncopated = values["syncopated_rhythm"]
        if syncopated is not None:
            _required_int(
                syncopated,
                "syncopated_rhythm",
                minimum=0,
                maximum=1,
            )
        top_k = _required_int(
            expected_contract.parameters.get("top_k"),
            "contract.parameters.top_k",
            minimum=1,
        )
        parse_maest_genres_json(
            values["genres_json"],
            expected_top_k=top_k,
        )
        _required_text(values["analyzed_at"], "analyzed_at")
    except (TypeError, ValueError, OverflowError) as error:
        return False, str(error)
    return True, None


def parse_maest_genres_json(
    raw: object,
    *,
    expected_top_k: int | None = None,
) -> tuple[tuple[str, float], ...]:
    """Parse canonical MAEST genre JSON without silently dropping entries."""

    if not isinstance(raw, str):
        raise ValueError("genres_json must be a JSON string")
    try:
        values = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("genres_json is not valid JSON") from error
    if not isinstance(values, list):
        raise ValueError("genres_json must be a JSON array")
    if not values:
        raise ValueError("genres_json must contain at least one genre")
    if expected_top_k is not None and len(values) > expected_top_k:
        raise ValueError(
            f"genres_json must contain at most contract top_k={expected_top_k} entries"
        )
    normalized: list[dict[str, object]] = []
    parsed: list[tuple[str, float]] = []
    seen_labels: set[str] = set()
    previous_score = math.inf
    for index, value in enumerate(values):
        field_name = f"genres_json[{index}]"
        if not isinstance(value, Mapping):
            raise ValueError(f"{field_name} must be a JSON object")
        if set(value) != {"label", "score"}:
            raise ValueError(f"{field_name} fields must be exactly ['label', 'score']")
        label = _required_text(value["label"], f"{field_name}.label")
        score = value["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError(f"{field_name}.score must be a finite number")
        number = float(score)
        if not math.isfinite(number):
            raise ValueError(f"{field_name}.score must be a finite number")
        if not 0.0 <= number <= 1.0:
            raise ValueError(f"{field_name}.score must be between 0 and 1")
        normalized_label = label.casefold()
        if normalized_label in seen_labels:
            raise ValueError("genres_json labels must be unique")
        seen_labels.add(normalized_label)
        if number > previous_score:
            raise ValueError("genres_json must be sorted by descending score")
        previous_score = number
        normalized.append({"label": label, "score": number})
        parsed.append((label, number))
    canonical = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    if raw != canonical:
        raise ValueError("genres_json is not canonical MAEST JSON")
    return tuple(parsed)


def _row_values(row: MaestAnalysisRow) -> dict[str, object]:
    if isinstance(row, sqlite3.Row):
        available = set(row.keys())
        missing = sorted(set(MAEST_ANALYSIS_COLUMNS) - available)
        if missing:
            raise ValueError(
                "MAEST analysis row is missing fields: " + ", ".join(missing)
            )
        return {column: row[column] for column in MAEST_ANALYSIS_COLUMNS}
    if isinstance(row, Mapping):
        missing = sorted(set(MAEST_ANALYSIS_COLUMNS) - set(row))
        if missing:
            raise ValueError(
                "MAEST analysis row is missing fields: " + ", ".join(missing)
            )
        return {column: row[column] for column in MAEST_ANALYSIS_COLUMNS}
    raise TypeError("MAEST analysis row must be a row mapping")


def _required_int(
    value: object,
    field_name: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    number = int(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{field_name} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field_name} must be at most {maximum}")
    return number


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    return value
