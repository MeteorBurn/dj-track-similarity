from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, TypeVar

from . import models as models_module

_T = TypeVar("_T")


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def normalize_path_text(path: str | Path) -> str:
    text = str(path).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    normalized = text.replace("\\", "/").rstrip("/")
    return normalized or text.replace("\\", "/")


def _duration_distance(left: models_module.TrackRecord, right: models_module.TrackRecord) -> tuple[float | None, float | None]:
    if left.duration is None or right.duration is None or left.duration <= 0 or right.duration <= 0:
        return None, None
    diff = abs(float(left.duration) - float(right.duration))
    return diff, diff / min(float(left.duration), float(right.duration))


def _json_string_list(value: object) -> list[str]:
    if value is None:
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [
        item.strip()
        for item in parsed
        if isinstance(item, str) and item.strip()
    ]


def _float_or_none(value: object) -> float | None:
    if isinstance(value, dict) and "value" in value:
        value = value.get("value")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _round_float(value: object) -> float | None:
    number = _float_or_none(value)
    return None if number is None else round(number, 6)


def _format_float(value: object) -> str:
    number = _float_or_none(value)
    return "" if number is None else f"{number:.6f}"


def _chunks(values: list[_T], size: int) -> Iterable[list[_T]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]
