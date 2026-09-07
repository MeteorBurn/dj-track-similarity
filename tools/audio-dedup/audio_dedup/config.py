from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, Mapping

from . import models as models_module

SCRIPT_DIR = Path(__file__).resolve().parent
TOOL_ROOT = SCRIPT_DIR.parent
REPO_ROOT = TOOL_ROOT.parents[1]
DEFAULT_DB = REPO_ROOT / "database" / "volumes.sqlite"
DEFAULT_RHYTHM_LAB_DB = REPO_ROOT / "tools" / "rhythm-lab" / "database" / "rhythm_lab.sqlite"
DEFAULT_OUT_DIR = TOOL_ROOT / "data" / "reports"
SUPPORTED_EMBEDDINGS = ("mert", "maest", "muq", "clap")
FINGERPRINT_REVIEW_MIN_SIMILARITY = 0.45
MODE_FINGERPRINT = "fingerprint"
MODE_EMBEDDING = "embedding"
SEARCH_MODES = (MODE_FINGERPRINT, MODE_EMBEDDING)
DELETION_MODE_PERMANENT = "permanent"
DELETION_MODE_TRASH = "trash"
DELETION_MODES = (DELETION_MODE_PERMANENT, DELETION_MODE_TRASH)
DEFAULT_SOURCE_WEIGHTS = {
    "mert": 0.43,
    "maest": 0.32,
    "muq": 0.12,
    "clap": 0.04,
}
DELETE_SAFETY_EMBEDDINGS = ("mert", "maest")
LEGACY_DELETE_SAFETY_SOURCES = ("mert", "maest", "clap")
LEGACY_DELETE_SAFETY_WEIGHTS = {
    source: DEFAULT_SOURCE_WEIGHTS[source]
    for source in LEGACY_DELETE_SAFETY_SOURCES
}
SCORE_SEMANTICS = {
    "score": {
        "kind": "weighted_duplicate_evidence",
        "range": "0..1",
        "notes": "Overall duplicate score from enabled audio-to-audio embeddings, SONARA features, and duration evidence; weights are renormalized over available evidence.",
    },
    "content_similarity": {
        "kind": "audio_to_audio_embedding_gate",
        "range": "0..1",
        "notes": "Embedding-only gate computed from enabled stored MERT, MAEST, MuQ, and CLAP audio embeddings; MERT plus MAEST remain mandatory for automatic deletion safety.",
    },
    "mert_similarity": {
        "kind": "audio_to_audio_cosine",
        "range": "-1..1",
        "notes": "Cosine similarity between stored MERT audio embeddings.",
    },
    "maest_similarity": {
        "kind": "audio_to_audio_cosine",
        "range": "-1..1",
        "notes": "Cosine similarity between stored MAEST audio embeddings.",
    },
    "muq_similarity": {
        "kind": "audio_to_audio_cosine",
        "range": "-1..1",
        "notes": "Cosine similarity between stored MuQ audio embeddings.",
    },
    "clap_similarity": {
        "kind": "audio_to_audio_cosine",
        "range": "-1..1",
        "text_search_comparable": False,
        "notes": "Cosine similarity between stored CLAP audio embeddings; not comparable to CLAP text-to-audio search scores.",
    },
    "fingerprint_similarity": {
        "kind": "sonara_native_fingerprint_match",
        "range": "0..1",
        "notes": "Exact native SONARA fingerprint comparison, run only after version-separated fingerprint LSH retrieval. A score of 0.45 or above creates a manual-review candidate; it never independently authorizes deletion.",
    },
}


def parse_weight_arguments(items: Iterable[str]) -> dict[str, float] | None:
    parsed: dict[str, float] = {}
    for raw_item in items:
        family_text, separator, value_text = str(raw_item).partition("=")
        family = family_text.strip().casefold()
        if not separator or not family or not value_text.strip():
            raise ValueError(
                f"Invalid --weight {raw_item!r}; expected FAMILY=VALUE"
            )
        if family in parsed:
            raise ValueError(f"Duplicate --weight for source: {family}")
        try:
            parsed[family] = float(value_text)
        except ValueError as error:
            raise ValueError(
                f"Invalid --weight {raw_item!r}; VALUE must be numeric"
            ) from error
    return parsed or None


def resolve_source_config(
    *,
    sources: Iterable[str] | None = None,
    weights: Mapping[str, float] | None = None,
) -> models_module.SourceConfig:
    if isinstance(sources, (str, bytes)):
        raise ValueError("sources must be a collection of embedding family names")
    selected_sources = tuple(
        str(source).strip().casefold()
        for source in (
            SUPPORTED_EMBEDDINGS
            if sources is None
            else sources
        )
    )
    if not selected_sources:
        raise ValueError("sources must enable at least one embedding family")
    if len(set(selected_sources)) != len(selected_sources):
        raise ValueError("sources must contain unique embedding family names")
    unsupported = [
        source
        for source in selected_sources
        if source not in SUPPORTED_EMBEDDINGS
    ]
    if unsupported:
        raise ValueError(
            "Unsupported embedding source(s): "
            + ", ".join(sorted(unsupported))
        )

    if weights is None:
        selected_weights = {
            source: DEFAULT_SOURCE_WEIGHTS[source]
            for source in selected_sources
        }
    else:
        normalized_weights: dict[str, float] = {}
        for raw_family, raw_weight in weights.items():
            family = str(raw_family).strip().casefold()
            if family in normalized_weights:
                raise ValueError(
                    f"weights contains duplicate normalized source: {family}"
                )
            if isinstance(raw_weight, bool):
                raise ValueError(f"Weight for {family} must be numeric")
            try:
                value = float(raw_weight)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Weight for {family} must be numeric"
                ) from error
            normalized_weights[family] = value
        expected = set(selected_sources)
        actual = set(normalized_weights)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if extra:
                details.append("unexpected " + ", ".join(extra))
            raise ValueError(
                "weights must contain exactly the enabled sources"
                + (f" ({'; '.join(details)})" if details else "")
            )
        selected_weights = {
            source: normalized_weights[source]
            for source in selected_sources
        }

    for source, weight in selected_weights.items():
        if not math.isfinite(weight) or weight < 0:
            raise ValueError(
                f"Weight for {source} must be finite and nonnegative"
            )
    if not any(weight > 0 for weight in selected_weights.values()):
        raise ValueError("At least one enabled source weight must be positive")
    return models_module.SourceConfig(
        sources=selected_sources,
        weights=selected_weights,
    )


def _uses_legacy_delete_safety_config(
    source_config: models_module.SourceConfig,
) -> bool:
    return (
        len(source_config.sources)
        == len(LEGACY_DELETE_SAFETY_SOURCES)
        and set(source_config.sources)
        == set(LEGACY_DELETE_SAFETY_SOURCES)
        and source_config.weights
        == LEGACY_DELETE_SAFETY_WEIGHTS
    )


def resolve_preset(name: str, *, min_score: float | None, min_similarity: float | None = None) -> models_module.PresetConfig:
    presets = {
        "safe": models_module.PresetConfig(
            name="safe",
            min_score=0.965,
            min_similarity=0.985,
            duration_seconds=2.0,
            duration_ratio=0.01,
            direct_keeper_score=0.98,
            strict_duration_ratio=0.01,
        ),
        "balanced": models_module.PresetConfig(
            name="balanced",
            min_score=0.95,
            min_similarity=0.97,
            duration_seconds=5.0,
            duration_ratio=0.025,
            direct_keeper_score=0.97,
            strict_duration_ratio=0.025,
        ),
        "aggressive": models_module.PresetConfig(
            name="aggressive",
            min_score=0.925,
            min_similarity=0.94,
            duration_seconds=15.0,
            duration_ratio=0.08,
            direct_keeper_score=0.965,
            strict_duration_ratio=0.08,
        ),
    }
    if name not in presets:
        raise ValueError(f"Unsupported preset: {name}")
    config = presets[name]
    selected_min_score = config.min_score if min_score is None else float(min_score)
    selected_min_similarity = config.min_similarity if min_similarity is None else float(min_similarity)
    if not 0.0 <= selected_min_score <= 1.0:
        raise ValueError("--min-score must be between 0 and 1")
    if not 0.0 <= selected_min_similarity <= 1.0:
        raise ValueError("--min-similarity must be between 0 and 1")
    return models_module.PresetConfig(
        name=config.name,
        min_score=selected_min_score,
        min_similarity=selected_min_similarity,
        duration_seconds=config.duration_seconds,
        duration_ratio=config.duration_ratio,
        direct_keeper_score=config.direct_keeper_score,
        strict_duration_ratio=config.strict_duration_ratio,
    )


def score_semantics_payload() -> dict[str, dict[str, object]]:
    return {key: dict(value) for key, value in SCORE_SEMANTICS.items()}
