"""Exact-query provenance shared by HTTP and persistence."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from typing import Any, Literal


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def content_hash(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_query_context(context: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(context)
    required = {
        "context_version",
        "catalog_uuid",
        "analysis_family",
        "analysis_output_identity",
        "bank_hash",
        "positive_queries",
        "negative_queries",
        "negative_weight",
        "composition",
        "selected_preset_keys",
        "input_mode",
        "scope",
    }
    if set(value) != required or value["context_version"] != 1:
        raise ValueError("Invalid text query context shape/version")
    if not isinstance(value["catalog_uuid"], str) or not value["catalog_uuid"].strip():
        raise ValueError("catalog_uuid is required")
    if value["analysis_family"] not in ("clap", "mulan") or value["input_mode"] not in (
        "preset",
        "custom",
    ):
        raise ValueError("Invalid query family/input mode")
    identity = value["analysis_output_identity"]
    if not isinstance(identity, dict) or any(
        not isinstance(identity.get(key), str) or not identity[key].strip()
        for key in ("model_name", "model_version", "checkpoint_id", "preprocessing")
    ):
        raise ValueError("Full analysis output identity is required")
    for key in ("positive_queries", "negative_queries", "selected_preset_keys"):
        if not isinstance(value[key], list) or any(
            not isinstance(item, str) or not item.strip() or item != item.strip()
            for item in value[key]
        ):
            raise ValueError(f"Invalid {key}")
    if not value["positive_queries"] or value["selected_preset_keys"] != sorted(
        set(value["selected_preset_keys"])
    ):
        raise ValueError("Invalid positive queries or preset key set")
    weight = value["negative_weight"]
    if (
        isinstance(weight, bool)
        or not isinstance(weight, (float, int))
        or not math.isfinite(weight)
        or not 0 <= weight <= 2
    ):
        raise ValueError("Invalid negative weight")
    if not value["negative_queries"] and weight != 0:
        raise ValueError("An empty negative bank must have zero effective weight")
    value["negative_weight"] = float(weight)
    bank = {
        key: value[key]
        for key in ("positive_queries", "negative_queries", "negative_weight")
    }
    if value["bank_hash"] != content_hash(bank):
        raise ValueError("Text bank hash does not match executed bank")
    if value["composition"] != "positive-centroid-top2-negative-v1":
        raise ValueError("Unsupported query composition")
    scope = value["scope"]
    if (
        not isinstance(scope, dict)
        or set(scope) != {"kind", "filters"}
        or scope["kind"] != "all_eligible_tracks"
        or not isinstance(scope["filters"], dict)
    ):
        raise ValueError("Invalid query scope")
    canonical_json(value)
    return value


def query_context_key(context: Mapping[str, Any]) -> str:
    return content_hash(validate_query_context(context))


@dataclass(frozen=True)
class QueryContext:
    catalog_uuid: str
    analysis_family: str
    analysis_output_identity: dict[str, Any]
    positive_queries: tuple[str, ...]
    negative_queries: tuple[str, ...]
    negative_weight: float
    selected_preset_keys: tuple[str, ...]
    input_mode: Literal["preset", "custom"]
    scope: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("positive_queries", "negative_queries", "selected_preset_keys"):
            value[key] = list(value[key])
        value["selected_preset_keys"] = sorted(set(value["selected_preset_keys"]))
        value["negative_weight"] = float(
            self.negative_weight if self.negative_queries else 0
        )
        value["bank_hash"] = content_hash(
            {
                key: value[key]
                for key in ("positive_queries", "negative_queries", "negative_weight")
            }
        )
        value.update(
            context_version=1, composition="positive-centroid-top2-negative-v1"
        )
        return validate_query_context(value)


@dataclass(frozen=True)
class TextSearchRun:
    """Canonical serialized snapshot prevents mutation after cache admission."""

    execution_json: str
    membership: tuple[tuple[str, int], ...]
    database_generation: int

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.execution_json)

    def for_track(self, track_uuid: str) -> dict[str, Any]:
        rank = dict(self.membership).get(track_uuid)
        if rank is None:
            raise ValueError("Track was not returned by this text search run")
        value = self.to_dict()
        value["rank"] = rank
        value["analysis_family"] = value["query_context"]["analysis_family"]
        return value
