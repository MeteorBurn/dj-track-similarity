from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

import numpy as np

from .analysis_models import AnalysisTarget
from .tempo_resolution import (
    confidence_aware_tempo_score,
    measured_tempo_score,
    resolve_tempo_evidence_v7,
)
from .track_resolution import attenuate_harmonic_score, camelot_compatibility


@dataclass(frozen=True)
class ComparableTrack:
    target: AnalysisTarget
    features: Mapping[str, object]


VIBE_WEIGHTS = {
    "energy_score": 3.0,
    "danceability_score": 3.0,
    "valence_score": 1.4,
    "acousticness_score": 1.0,
    "integrated_loudness_lufs": 0.8,
    "dynamic_range_db": 0.8,
    "onset_density_per_second": 0.8,
    "rms_mean": 0.6,
}
SOUND_WEIGHTS = {
    "mfcc_mean_blob": 1.8,
    "spectral_centroid_hz": 1.0,
    "spectral_bandwidth_hz": 1.0,
    "spectral_rolloff_hz": 1.0,
    "spectral_flatness": 0.9,
    "spectral_contrast_mean_blob": 0.9,
    "zero_crossing_rate": 0.8,
    "rms_mean": 0.8,
    "rms_max": 0.5,
}
DJ_NUMERIC_WEIGHTS = {
    "detected_bpm": 3.0,
    "onset_density_per_second": 2.0,
    "energy_score": 1.3,
    "danceability_score": 1.3,
    "chord_changes_per_second": 1.0,
    "dissonance_score": 1.0,
}
TONAL_TEXT_WEIGHTS = {
    "detected_key_name": 4.0,
    "detected_key_camelot": 3.0,
    "predominant_chord": 3.0,
}
BALANCED_WEIGHTS = {
    **{key: weight * 0.9 for key, weight in VIBE_WEIGHTS.items()},
    **{key: weight * 0.7 for key, weight in SOUND_WEIGHTS.items()},
    "detected_bpm": 1.0,
    "chord_changes_per_second": 0.7,
    "dissonance_score": 0.7,
}
CUSTOM_GROUP_WEIGHTS = {
    "timbre": {
        "mfcc_mean_blob": 1.7,
        "spectral_centroid_hz": 1.0,
        "spectral_bandwidth_hz": 0.9,
        "spectral_rolloff_hz": 0.9,
        "spectral_flatness": 0.9,
        "spectral_contrast_mean_blob": 0.8,
    },
    "rhythm": {
        "onset_density_per_second": 1.4,
        "zero_crossing_rate": 0.9,
        "danceability_score": 0.9,
        "chord_changes_per_second": 0.4,
    },
    "dynamics": {
        "energy_score": 1.2,
        "energy_level": 0.7,
        "rms_mean": 1.0,
        "rms_max": 0.7,
        "integrated_loudness_lufs": 0.9,
        "max_momentary_loudness_lufs": 0.8,
        "loudness_range_lu": 0.8,
        "dynamic_range_db": 0.8,
    },
    "harmonic": {
        "chroma_mean_blob": 1.2,
        "dissonance_score": 0.9,
        "chord_changes_per_second": 0.8,
    },
    "tempo": {
        "detected_bpm": 1.0,
    },
}
DEFAULT_CUSTOM_MIXER_WEIGHTS = {
    "timbre": 1.0,
    "rhythm": 1.0,
    "dynamics": 0.8,
    "harmonic": 0.8,
    "tempo": 0.35,
}
CUSTOM_MODIFIER_FIELDS = {
    "energy": "energy_score",
    "valence": "valence_score",
    "acousticness": "acousticness_score",
    "brightness": "spectral_centroid_hz",
    "rhythm_density": "onset_density_per_second",
    "dynamic_range": "dynamic_range_db",
    "loudness": "integrated_loudness_lufs",
    "vocalness": "vocal_probability",
}
# The custom Harmonic knob should reflect harmonic color (chroma, dissonance, chord movement), not
# act as an exact-key gate. Standard modes weight exact key/chord text at 4.0/3.0; in the custom
# harmonic group we keep tonal-text agreement as a lighter nudge so a matching key helps without
# dominating the group.
CUSTOM_HARMONIC_TONAL_WEIGHTS = {
    "detected_key_name": 0.9,
    "detected_key_camelot": 0.9,
    "predominant_chord": 0.6,
}
# A modifier is a deliberate directional push. Give it enough weight that a maxed knob is actually
# felt in the final ranking instead of being averaged away by the mixer-group weights, while still
# staying bounded so it cannot completely override sonic similarity.
MODIFIER_GAIN = 2.5
KEY_TONAL_FIELDS = {"detected_key_name", "detected_key_camelot"}
KEY_CONFIDENCE_CONTEXT = "_key_confidence"
TonalContext = dict[str, set[str] | float]
SONARA_SIMILARITY_EMBEDDING_DIM = 48


def _scaled_weighted_euclidean_distance(
    left: np.ndarray,
    right: np.ndarray,
    *,
    scales: np.ndarray,
    weights: np.ndarray,
) -> float:
    """Distance for the data-only SONARA 48-d representation.

    The representation contract explicitly uses ``normalization='none'``.
    Consequently, it must never be compared with cosine similarity. A caller
    that eventually promotes this data-only output to a search surface must
    supply versioned positive per-dimension scales and non-negative weights.
    """

    expected_shape = (SONARA_SIMILARITY_EMBEDDING_DIM,)
    left_vector = np.asarray(left, dtype=np.float64).reshape(-1)
    right_vector = np.asarray(right, dtype=np.float64).reshape(-1)
    scale_vector = np.asarray(scales, dtype=np.float64).reshape(-1)
    weight_vector = np.asarray(weights, dtype=np.float64).reshape(-1)
    for field_name, vector in (
        ("left", left_vector),
        ("right", right_vector),
        ("scales", scale_vector),
        ("weights", weight_vector),
    ):
        if vector.shape != expected_shape:
            raise ValueError(
                f"SONARA {field_name} must have shape {expected_shape}"
            )
        if not bool(np.all(np.isfinite(vector))):
            raise ValueError(
                f"SONARA {field_name} contains non-finite values"
            )
    if bool(np.any(scale_vector <= 0.0)):
        raise ValueError("SONARA per-dimension scales must be positive")
    if bool(np.any(weight_vector < 0.0)):
        raise ValueError("SONARA per-dimension weights must be non-negative")
    total_weight = float(np.sum(weight_vector))
    if not math.isfinite(total_weight) or total_weight <= 0.0:
        raise ValueError(
            "SONARA per-dimension weights must include a positive value"
        )
    scaled_delta = (left_vector - right_vector) / scale_vector
    squared_distance = float(
        np.dot(weight_vector, np.square(scaled_delta))
        / total_weight
    )
    return math.sqrt(max(0.0, squared_distance))


def numeric_weights_for_mode(mode: str) -> dict[str, float]:
    if mode == "vibe":
        return VIBE_WEIGHTS
    if mode == "sound":
        return SOUND_WEIGHTS
    if mode == "dj_transition":
        return DJ_NUMERIC_WEIGHTS
    return BALANCED_WEIGHTS


def numeric_dimensions(
    tracks: list[ComparableTrack],
    field_weights: dict[str, float],
) -> tuple[list[tuple[str, int | None, float]], dict[tuple[str, int | None], tuple[float, float]]]:
    values: dict[tuple[str, int | None], list[float]] = {}
    for item in tracks:
        for field in field_weights:
            for key, value in feature_values(item.features, field):
                values.setdefault(key, []).append(value)

    dimensions: list[tuple[str, int | None, float]] = []
    ranges: dict[tuple[str, int | None], tuple[float, float]] = {}
    for field, weight in field_weights.items():
        indexes: Sequence[int | None]
        if (field, None) in values:
            indexes = [None]
        else:
            indexes = sorted(index for name, index in values if name == field and index is not None)
        valid_indexes = [index for index in indexes if len(values.get((field, index), [])) >= 2]
        if not valid_indexes:
            continue
        # A vector feature (e.g. mfcc_mean has 13 components, chroma_mean 12) expands into one
        # dimension per component. Split the field weight across its components so the field
        # contributes its intended weight once, instead of weight * component_count. Without this a
        # single vector field dominates its whole mixer group.
        per_dimension_weight = weight / len(valid_indexes)
        for index in valid_indexes:
            key = (field, index)
            dimensions.append((field, index, per_dimension_weight))
            ranges[key] = _robust_range(values[key])
    return dimensions, ranges


def _robust_range(observed: list[float]) -> tuple[float, float]:
    # Library-wide min/max is dominated by rare outliers (e.g. loudness_lufs reaches -70 dB, so its
    # useful inter-quartile band collapses to ~4% of the 0-1 scale and every knob barely moves the
    # ranking). Use the 2nd-98th percentile as the normalization band so typical values spread across
    # the full range; fall back to raw min/max when the percentile band is degenerate.
    array = np.asarray(observed, dtype=np.float64)
    lower = float(np.percentile(array, 2.0))
    upper = float(np.percentile(array, 98.0))
    if upper <= lower:
        return float(array.min()), float(array.max())
    return lower, upper


def feature_values(
    features: Mapping[str, object],
    field: str,
) -> list[tuple[tuple[str, int | None], float]]:
    value = unwrap_feature_value(features.get(field))
    if isinstance(value, (list, tuple)):
        pairs: list[tuple[tuple[str, int | None], float]] = []
        for index, item in enumerate(value):
            number = optional_float(item)
            if number is not None:
                pairs.append(((field, index), number))
        return pairs
    number = optional_float(value)
    return [((field, None), number)] if number is not None else []


def centroid(
    context: list[ComparableTrack],
    dimensions: list[tuple[str, int | None, float]],
    ranges: dict[tuple[str, int | None], tuple[float, float]],
) -> dict[tuple[str, int | None], float]:
    result: dict[tuple[str, int | None], float] = {}
    for field, index, _ in dimensions:
        key = (field, index)
        values = [
            normalized
            for item in context
            if (value := feature_value(item.features, field, index)) is not None
            if (normalized := normalize_feature(value, ranges[key])) is not None
        ]
        if values:
            result[key] = float(np.mean(values))
    return result


def score_candidate(
    item: ComparableTrack,
    mode: str,
    dimensions: list[tuple[str, int | None, float]],
    ranges: dict[tuple[str, int | None], tuple[float, float]],
    feature_centroid: dict[tuple[str, int | None], float],
    tonal_context: TonalContext,
    tempo_context: list[ComparableTrack] | None = None,
) -> float | None:
    weighted_score = 0.0
    total_weight = 0.0
    numeric_overlap = 0
    for field, index, weight in dimensions:
        key = (field, index)
        if key not in feature_centroid:
            continue
        raw_value = feature_value(item.features, field, index)
        if raw_value is None:
            continue
        if field == "detected_bpm":
            score = _tempo_similarity(item, tempo_context) if tempo_context else None
            if score is None:
                score = tempo_score(raw_value, denormalize_feature(feature_centroid[key], ranges[key]))
        else:
            value = normalize_feature(raw_value, ranges[key])
            if value is None:
                continue
            score = max(0.0, 1.0 - abs(value - feature_centroid[key]))
        weighted_score += score * weight
        total_weight += weight
        numeric_overlap += 1

    if mode in {"balanced", "dj_transition"}:
        for field, weight in TONAL_TEXT_WEIGHTS.items():
            context_values = _tonal_context_values(tonal_context, field)
            tonal_score = _tonal_similarity(item, field, context_values, tonal_context)
            if tonal_score is None:
                continue
            weighted_score += tonal_score * weight
            total_weight += weight

    if numeric_overlap < 2 or total_weight <= 0:
        return None
    return max(0.0, min(1.0, weighted_score / total_weight))


def score_custom_candidate(
    item: ComparableTrack,
    dimensions: list[tuple[str, int | None, float]],
    ranges: dict[tuple[str, int | None], tuple[float, float]],
    feature_centroid: dict[tuple[str, int | None], float],
    tonal_context: TonalContext,
    mixer_weights: dict[str, float],
    modifiers: dict[str, float],
    tempo_context: list[ComparableTrack] | None = None,
) -> tuple[float, dict[str, float]] | None:
    weighted_score = 0.0
    total_weight = 0.0
    breakdown: dict[str, float] = {}

    # A field driven by an active modifier is scored directionally by that modifier. Exclude it from
    # group similarity so the two do not fight (e.g. the Energy modifier pushing away from the seed
    # while the Dynamics group pulls toward it), which otherwise cancels the knob out.
    modifier_fields = {
        CUSTOM_MODIFIER_FIELDS[name] for name, direction in modifiers.items() if direction != 0
    }

    for group_name, group_weight in mixer_weights.items():
        if group_weight <= 0:
            continue
        group_score = score_custom_group(
            item,
            group_name,
            dimensions,
            ranges,
            feature_centroid,
            tonal_context,
            tempo_context=tempo_context,
            exclude_fields=modifier_fields,
        )
        if group_score is None:
            continue
        weighted_score += group_score * group_weight
        total_weight += group_weight
        breakdown[group_name] = round(group_score, 6)

    for modifier_name, direction in modifiers.items():
        if direction == 0:
            continue
        modifier_score = score_modifier(item, modifier_name, direction, ranges, feature_centroid)
        if modifier_score is None:
            continue
        modifier_weight = abs(direction) * MODIFIER_GAIN
        weighted_score += modifier_score * modifier_weight
        total_weight += modifier_weight
        breakdown[f"modifier_{modifier_name}"] = round(modifier_score, 6)

    if total_weight <= 0:
        return None
    score = max(0.0, min(1.0, weighted_score / total_weight))
    return score, breakdown


def score_custom_group(
    item: ComparableTrack,
    group_name: str,
    dimensions: list[tuple[str, int | None, float]],
    ranges: dict[tuple[str, int | None], tuple[float, float]],
    feature_centroid: dict[tuple[str, int | None], float],
    tonal_context: TonalContext,
    *,
    tempo_context: list[ComparableTrack] | None = None,
    exclude_fields: set[str] | None = None,
) -> float | None:
    field_weights = CUSTOM_GROUP_WEIGHTS[group_name]
    excluded = exclude_fields or set()
    # A vector feature (mfcc_mean=13, chroma_mean=12 components) expands into one dimension per
    # component. Split its group weight across those components so the field contributes its intended
    # weight once, instead of weight * component_count, which otherwise lets a single vector field
    # dominate the whole group and drown the scalar knobs.
    dimension_counts: dict[str, int] = {}
    for field, _index, _weight in dimensions:
        if field in field_weights:
            dimension_counts[field] = dimension_counts.get(field, 0) + 1
    weighted_score = 0.0
    total_weight = 0.0
    for field, index, _ in dimensions:
        if field not in field_weights:
            continue
        if field in excluded:
            continue
        key = (field, index)
        if key not in feature_centroid:
            continue
        raw_value = feature_value(item.features, field, index)
        if raw_value is None:
            continue
        if field == "detected_bpm":
            score = _tempo_similarity(item, tempo_context) if tempo_context else None
            if score is None:
                score = tempo_score(raw_value, denormalize_feature(feature_centroid[key], ranges[key]))
        else:
            value = normalize_feature(raw_value, ranges[key])
            if value is None:
                continue
            score = max(0.0, 1.0 - abs(value - feature_centroid[key]))
        weight = field_weights[field] / dimension_counts[field]
        weighted_score += score * weight
        total_weight += weight

    if group_name == "harmonic":
        for field, weight in CUSTOM_HARMONIC_TONAL_WEIGHTS.items():
            context_values = _tonal_context_values(tonal_context, field)
            tonal_score = _tonal_similarity(item, field, context_values, tonal_context)
            if tonal_score is None:
                continue
            weighted_score += tonal_score * weight
            total_weight += weight

    if total_weight <= 0:
        return None
    return max(0.0, min(1.0, weighted_score / total_weight))


def score_modifier(
    item: ComparableTrack,
    modifier_name: str,
    direction: float,
    ranges: dict[tuple[str, int | None], tuple[float, float]],
    feature_centroid: dict[tuple[str, int | None], float],
) -> float | None:
    field = CUSTOM_MODIFIER_FIELDS[modifier_name]
    key = (field, None)
    if key not in ranges or key not in feature_centroid:
        return None
    raw_value = feature_value(item.features, field, None)
    if raw_value is None:
        return None
    value = normalize_feature(raw_value, ranges[key])
    if value is None:
        return None
    signed_delta = value - feature_centroid[key]
    desired_delta = signed_delta if direction > 0 else -signed_delta
    return max(0.0, min(1.0, 0.5 + desired_delta / 2.0))


def clean_mixer_weights(mixer_weights: dict[str, float] | None) -> dict[str, float]:
    if mixer_weights is None:
        return dict(DEFAULT_CUSTOM_MIXER_WEIGHTS)
    cleaned = {name: 0.0 for name in CUSTOM_GROUP_WEIGHTS}
    for name, value in mixer_weights.items():
        if name not in CUSTOM_GROUP_WEIGHTS:
            raise ValueError(f"Unsupported SONARA mixer weight: {name}")
        number = optional_float(value)
        if number is None:
            raise ValueError(f"Invalid SONARA mixer weight: {name}")
        cleaned[name] = max(0.0, min(5.0, number))
    return cleaned


def clean_modifiers(modifiers: dict[str, float] | None) -> dict[str, float]:
    if not modifiers:
        return {}
    cleaned: dict[str, float] = {}
    for name, value in modifiers.items():
        if name not in CUSTOM_MODIFIER_FIELDS:
            raise ValueError(f"Unsupported SONARA modifier: {name}")
        number = optional_float(value)
        if number is None:
            raise ValueError(f"Invalid SONARA modifier: {name}")
        cleaned[name] = max(-1.0, min(1.0, number))
    return cleaned


def custom_numeric_fields(mixer_weights: dict[str, float], modifiers: dict[str, float]) -> dict[str, float]:
    fields: dict[str, float] = {}
    for group_name, group_weight in mixer_weights.items():
        if group_weight <= 0:
            continue
        for field in CUSTOM_GROUP_WEIGHTS[group_name]:
            fields[field] = 1.0
    for modifier_name, direction in modifiers.items():
        if direction != 0:
            fields[CUSTOM_MODIFIER_FIELDS[modifier_name]] = 1.0
    return fields


def tonal_context(context: list[ComparableTrack]) -> TonalContext:
    result: TonalContext = {}
    for field in TONAL_TEXT_WEIGHTS:
        values = [normalize_text(item.features.get(field)) for item in context]
        values = [value for value in values if value]
        if values:
            most_common_count = Counter(values).most_common(1)[0][1]
            result[field] = {value for value, count in Counter(values).items() if count == most_common_count}
    confidences = [
        confidence
        for item in context
        if (confidence := feature_value(item.features, "key_confidence", None)) is not None
    ]
    if confidences:
        result[KEY_CONFIDENCE_CONTEXT] = float(np.mean([max(0.0, min(1.0, value)) for value in confidences]))
    return result


def _tonal_context_values(context: TonalContext, field: str) -> set[str]:
    values = context.get(field)
    return values if isinstance(values, set) else set()


def _tonal_similarity(
    item: ComparableTrack,
    field: str,
    context_values: set[str],
    context: TonalContext,
) -> float | None:
    candidate = normalize_text(item.features.get(field))
    if not context_values or candidate is None:
        return None
    if field not in KEY_TONAL_FIELDS:
        return 1.0 if candidate in context_values else 0.0
    measured_score = max(camelot_compatibility(candidate, context_key)[1] for context_key in context_values)
    candidate_confidence = feature_value(item.features, "key_confidence", None)
    raw_context_confidence = context.get(KEY_CONFIDENCE_CONTEXT)
    context_confidence = float(raw_context_confidence) if isinstance(raw_context_confidence, (int, float)) else None
    return attenuate_harmonic_score(measured_score, candidate_confidence, context_confidence)


def feature_value(
    features: Mapping[str, object],
    field: str,
    index: int | None,
) -> float | None:
    value = unwrap_feature_value(features.get(field))
    if index is not None:
        if not isinstance(value, (list, tuple)) or index >= len(value):
            return None
        value = unwrap_feature_value(value[index])
    return optional_float(value)


def normalize_feature(value: float, value_range: tuple[float, float]) -> float | None:
    lower, upper = value_range
    if upper == lower:
        return 0.5
    # The range is a robust 2-98 percentile band, so values below/above the band land outside
    # [0, 1]. Clamp them so the extreme tails collapse onto the band edges instead of distorting
    # centroid means and similarity distances.
    return max(0.0, min(1.0, (value - lower) / (upper - lower)))


def denormalize_feature(value: float, value_range: tuple[float, float]) -> float:
    lower, upper = value_range
    return lower + value * (upper - lower)


def optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, np.integer, np.floating)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def normalize_text(value: object) -> str | None:
    value = unwrap_feature_value(value)
    if not isinstance(value, str):
        return None
    text = value.strip().casefold()
    return text or None


def unwrap_feature_value(value: object) -> object:
    """Return a typed v7 column value without legacy wrapper fallback."""

    return value


def tempo_score(candidate_bpm: float, centroid_bpm: float) -> float:
    return measured_tempo_score(candidate_bpm, centroid_bpm)


def _tempo_similarity(item: ComparableTrack, context: list[ComparableTrack] | None) -> float | None:
    if not context:
        return None
    candidate = resolve_tempo_evidence_v7(dict(item.features), None)
    scores: list[float] = []
    for reference_item in context:
        reference = resolve_tempo_evidence_v7(
            dict(reference_item.features),
            None,
        )
        score = confidence_aware_tempo_score(candidate, reference)
        if score is not None:
            scores.append(score)
    return float(np.mean(scores)) if scores else None
