from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import csv
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PairFeedbackLabel:
    seed_track_id: int
    candidate_track_id: int
    rating: int
    reason_tags: tuple[str, ...]
    notes: str | None
    source: str


@dataclass(frozen=True)
class TransitionFeedbackLabel:
    outgoing_track_id: int
    incoming_track_id: int
    rating: int
    risk_tags: tuple[str, ...]
    notes: str | None
    source: str


PAIR_FEEDBACK_COLUMNS = ("seed_track_id", "candidate_track_id", "rating", "reason_tags", "notes", "source")
TRANSITION_FEEDBACK_COLUMNS = ("outgoing_track_id", "incoming_track_id", "rating", "risk_tags", "notes", "source")


def load_pair_feedback_labels(path: str | Path) -> list[PairFeedbackLabel]:
    input_path = Path(path)
    if input_path.suffix.lower() == ".csv":
        return _load_csv_labels(input_path, PAIR_FEEDBACK_COLUMNS, _parse_pair_feedback_row)
    if input_path.suffix.lower() == ".jsonl":
        return _load_jsonl_labels(input_path, _parse_pair_feedback_row)
    raise ValueError(f"Unsupported pair feedback input format: {input_path.suffix or '<none>'}. Use .csv or .jsonl")


def load_transition_feedback_labels(path: str | Path) -> list[TransitionFeedbackLabel]:
    input_path = Path(path)
    if input_path.suffix.lower() == ".csv":
        return _load_csv_labels(input_path, TRANSITION_FEEDBACK_COLUMNS, _parse_transition_feedback_row)
    if input_path.suffix.lower() == ".jsonl":
        return _load_jsonl_labels(input_path, _parse_transition_feedback_row)
    raise ValueError(f"Unsupported transition feedback input format: {input_path.suffix or '<none>'}. Use .csv or .jsonl")


def _load_csv_labels(path: Path, required_columns: Sequence[str], row_parser: Any) -> list[Any]:
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        _require_csv_columns(reader.fieldnames, required_columns, path)
        return [row_parser(row, reader.line_num) for row in reader]


def _load_jsonl_labels(path: Path, row_parser: Any) -> list[Any]:
    labels: list[Any] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            text = line.strip()
            if not text:
                continue
            labels.append(row_parser(_json_object(text, line_number), line_number))
    return labels


def _parse_pair_feedback_row(row: Mapping[str, Any], line_number: int) -> PairFeedbackLabel:
    return PairFeedbackLabel(
        seed_track_id=_positive_int(row.get("seed_track_id"), "seed_track_id", line_number),
        candidate_track_id=_positive_int(row.get("candidate_track_id"), "candidate_track_id", line_number),
        rating=_rating(row.get("rating"), line_number),
        reason_tags=_tags(row.get("reason_tags"), "reason_tags", line_number),
        notes=_optional_text(row.get("notes")),
        source=_source(row.get("source")),
    )


def _parse_transition_feedback_row(row: Mapping[str, Any], line_number: int) -> TransitionFeedbackLabel:
    return TransitionFeedbackLabel(
        outgoing_track_id=_positive_int(row.get("outgoing_track_id"), "outgoing_track_id", line_number),
        incoming_track_id=_positive_int(row.get("incoming_track_id"), "incoming_track_id", line_number),
        rating=_rating(row.get("rating"), line_number),
        risk_tags=_tags(row.get("risk_tags"), "risk_tags", line_number),
        notes=_optional_text(row.get("notes")),
        source=_source(row.get("source")),
    )


def _require_csv_columns(fieldnames: Sequence[str] | None, required_columns: Sequence[str], path: Path) -> None:
    if fieldnames is None:
        raise ValueError(f"{path} is missing a CSV header row")
    missing_columns = [column for column in required_columns if column not in fieldnames]
    if missing_columns:
        missing = ", ".join(missing_columns)
        raise ValueError(f"{path} CSV header is missing required columns on line 1: {missing}")


def _json_object(text: str, line_number: int) -> Mapping[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSONL object on line {line_number}: {error.msg}") from error
    if not isinstance(value, dict):
        raise ValueError(f"Invalid JSONL object on line {line_number}: expected an object")
    return value


def _positive_int(value: object, field_name: str, line_number: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Invalid {field_name} on line {line_number}: expected a positive integer")
    try:
        clean_value = int(str(value).strip())
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError(f"Invalid {field_name} on line {line_number}: expected a positive integer") from error
    if clean_value <= 0:
        raise ValueError(f"Invalid {field_name} on line {line_number}: expected a positive integer")
    return clean_value


def _rating(value: object, line_number: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"Invalid rating on line {line_number}: expected an integer between 0 and 3")
    try:
        clean_value = int(str(value).strip())
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError(f"Invalid rating on line {line_number}: expected an integer between 0 and 3") from error
    if clean_value < 0 or clean_value > 3:
        raise ValueError(f"Invalid rating on line {line_number}: expected an integer between 0 and 3")
    return clean_value


def _tags(value: object, field_name: str, line_number: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(tag for tag in (part.strip() for part in value.split(",")) if tag)
    if isinstance(value, Iterable):
        tags = [_tag_text(tag, field_name, line_number) for tag in value]
        return tuple(tag for tag in tags if tag)
    raise ValueError(f"Invalid {field_name} on line {line_number}: expected a comma-separated string or list")


def _tag_text(value: object, field_name: str, line_number: int) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if "," in text:
        raise ValueError(f"Invalid {field_name} on line {line_number}: list entries must not contain commas")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _source(value: object) -> str:
    text = _optional_text(value)
    return text or "manual"
