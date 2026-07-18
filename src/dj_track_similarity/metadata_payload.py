from __future__ import annotations

import json
import math
from typing import Any

import numpy as np

from .sonara_contract import sonara_analysis_is_current


def optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def string_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_maest_genre_label(label: str | None) -> str | None:
    if not label:
        return None
    text = label.replace("_", " ").strip()
    if "---" in text:
        text = text.rsplit("---", 1)[-1].strip()
    return text or None


def metadata_from_json(metadata_json: object) -> dict[str, object]:
    try:
        metadata = json.loads(str(metadata_json or "{}"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(metadata, dict):
        return {}
    sanitized = json_safe_value(metadata)
    return sanitized if isinstance(sanitized, dict) else {}


def metadata_to_json(metadata: dict[str, object], *, sort_keys: bool = True) -> str:
    sanitized = json_safe_value(metadata)
    return json.dumps(sanitized, ensure_ascii=False, sort_keys=sort_keys, allow_nan=False)


def json_safe_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe_value(value.tolist())
    if isinstance(value, np.generic):
        return json_safe_value(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def genres_from_metadata(metadata: dict[str, object]) -> tuple[list[str] | None, dict[str, float] | None]:
    raw_genres = metadata.get("maest_genres")
    if not isinstance(raw_genres, list):
        return None, None
    labels: list[str] = []
    scores: dict[str, float] = {}
    for item in raw_genres:
        if not isinstance(item, dict):
            continue
        label = string_or_none(item.get("label"))
        score = optional_float(item.get("score"))
        if label is None:
            continue
        labels.append(label)
        scores[label] = float(score or 0.0)
    return (labels or None), (scores or None)


def analyses_from_row(row: Any, metadata: dict[str, object]) -> list[str] | None:
    analyses_set: set[str] = set()
    row_keys = set(row.keys())
    if "has_sonara" in row_keys:
        if row["has_sonara"]:
            analyses_set.add("sonara")
    elif sonara_analysis_is_current(metadata):
        analyses_set.add("sonara")
    keys_json = row["embedding_keys_json"] if "embedding_keys_json" in row_keys else None
    try:
        keys = json.loads(str(keys_json or "[]"))
    except json.JSONDecodeError:
        keys = []
    if isinstance(keys, list):
        for key in keys:
            text = string_or_none(key)
            if text:
                analyses_set.add(text)
    ordered = [name for name in ("sonara", "maest", "mert", "muq", "clap") if name in analyses_set]
    extras = sorted(name for name in analyses_set if name not in {"maest", "sonara", "mert", "muq", "clap"})
    analyses = ordered + extras
    return analyses or None
