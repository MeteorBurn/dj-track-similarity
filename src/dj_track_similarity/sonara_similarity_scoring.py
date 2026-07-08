from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from math import inf

import numpy as np

from .models import Track


@dataclass(frozen=True)
class ComparableTrack:
    track: Track
    features: dict[str, object]


VIBE_WEIGHTS = {
    "energy": 3.0,
    "danceability": 3.0,
    "valence": 1.4,
    "acousticness": 1.0,
    "loudness_lufs": 0.8,
    "dynamic_range_db": 0.8,
    "onset_density": 0.8,
    "rms_mean": 0.6,
}
SOUND_WEIGHTS = {
    "mfcc_mean": 1.8,
    "spectral_centroid_mean": 1.0,
    "spectral_bandwidth_mean": 1.0,
    "spectral_rolloff_mean": 1.0,
    "spectral_flatness_mean": 0.9,
    "spectral_contrast_mean": 0.9,
    "zero_crossing_rate": 0.8,
    "rms_mean": 0.8,
    "rms_max": 0.5,
}
DJ_NUMERIC_WEIGHTS = {
    "bpm": 3.0,
    "onset_density": 2.0,
    "energy": 1.3,
    "danceability": 1.3,
    "key_confidence": 0.6,
    "chord_change_rate": 1.0,
    "dissonance": 1.0,
}
TONAL_TEXT_WEIGHTS = {
    "key": 4.0,
    "key_camelot": 3.0,
    "predominant_chord": 3.0,
}
BALANCED_WEIGHTS = {
    **{key: weight * 0.9 for key, weight in VIBE_WEIGHTS.items()},
    **{key: weight * 0.7 for key, weight in SOUND_WEIGHTS.items()},
    "bpm": 1.0,
    "chord_change_rate": 0.7,
    "dissonance": 0.7,
    "key_confidence": 0.4,
}
CUSTOM_GROUP_WEIGHTS = {
    "timbre": {
        "mfcc_mean": 1.7,
        "spectral_centroid_mean": 1.0,
        "spectral_bandwidth_mean": 0.9,
        "spectral_rolloff_mean": 0.9,
        "spectral_flatness_mean": 0.9,
        "spectral_contrast_mean": 0.8,
    },
    "rhythm": {
        "onset_density": 1.4,
        "zero_crossing_rate": 0.9,
        "danceability": 0.9,
        "chord_change_rate": 0.4,
    },
    "dynamics": {
        "energy": 1.2,
        "energy_level": 0.7,
        "rms_mean": 1.0,
        "rms_max": 0.7,
        "loudness_lufs": 0.9,
        "loudness_momentary_max_db": 0.8,
        "loudness_range_lu": 0.8,
        "dynamic_range_db": 0.8,
    },
    "harmonic": {
        "chroma_mean": 1.2,
        "dissonance": 0.9,
        "chord_change_rate": 0.8,
        "key_confidence": 0.4,
    },
    "tempo": {
        "bpm": 1.0,
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
    "energy": "energy",
    "valence": "valence",
    "acousticness": "acousticness",
    "brightness": "spectral_centroid_mean",
    "rhythm_density": "onset_density",
    "dynamic_range": "dynamic_range_db",
    "loudness": "loudness_lufs",
    "vocalness": "vocalness",
}
# The custom Harmonic knob should reflect harmonic color (chroma, dissonance, chord movement), not
# act as an exact-key gate. Standard modes weight exact key/chord text at 4.0/3.0; in the custom
# harmonic group we keep tonal-text agreement as a lighter nudge so a matching key helps without
# dominating the group.
CUSTOM_HARMONIC_TONAL_WEIGHTS = {
    "key": 0.9,
    "key_camelot": 0.9,
    "predominant_chord": 0.6,
}
# A modifier is a deliberate directional push. Give it enough weight that a maxed knob is actually
# felt in the final ranking instead of being averaged away by the mixer-group weights, while still
# staying bounded so it cannot completely override sonic similarity.
MODIFIER_GAIN = 2.5


def sonara_features(track: Track) -> dict[str, object] | None:
    metadata = track.metadata or {}
    features = metadata.get("sonara_features")
    return features if isinstance(features, dict) else None


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


def feature_values(features: dict[str, object], field: str) -> list[tuple[tuple[str, int | None], float]]:
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
    tonal_context: dict[str, set[str]],
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
        if field == "bpm":
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
            context_values = tonal_context.get(field, set())
            candidate = normalize_text(item.features.get(field))
            if not context_values or candidate is None:
                continue
            weighted_score += (1.0 if candidate in context_values else 0.0) * weight
            total_weight += weight

    if numeric_overlap < 2 or total_weight <= 0:
        return None
    return max(0.0, min(1.0, weighted_score / total_weight))


def score_custom_candidate(
    item: ComparableTrack,
    dimensions: list[tuple[str, int | None, float]],
    ranges: dict[tuple[str, int | None], tuple[float, float]],
    feature_centroid: dict[tuple[str, int | None], float],
    tonal_context: dict[str, set[str]],
    mixer_weights: dict[str, float],
    modifiers: dict[str, float],
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
            item, group_name, dimensions, ranges, feature_centroid, tonal_context, exclude_fields=modifier_fields
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
    tonal_context: dict[str, set[str]],
    *,
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
        if field == "bpm":
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
            context_values = tonal_context.get(field, set())
            candidate = normalize_text(item.features.get(field))
            if not context_values or candidate is None:
                continue
            weighted_score += (1.0 if candidate in context_values else 0.0) * weight
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


def tonal_context(context: list[ComparableTrack]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for field in TONAL_TEXT_WEIGHTS:
        values = [normalize_text(item.features.get(field)) for item in context]
        values = [value for value in values if value]
        if values:
            most_common_count = Counter(values).most_common(1)[0][1]
            result[field] = {value for value, count in Counter(values).items() if count == most_common_count}
    return result


def feature_value(features: dict[str, object], field: str, index: int | None) -> float | None:
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
    if value is None or value == "":
        return None
    if not isinstance(value, (str, bytes, int, float, np.integer, np.floating)):
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
    if value is None:
        return None
    text = str(value).strip().casefold()
    return text or None


def unwrap_feature_value(value: object) -> object:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def tempo_score(candidate_bpm: float, centroid_bpm: float) -> float:
    candidate_variants = [candidate_bpm / 2, candidate_bpm, candidate_bpm * 2]
    centroid_variants = [centroid_bpm / 2, centroid_bpm, centroid_bpm * 2]
    best = inf
    for candidate in candidate_variants:
        for centroid_value in centroid_variants:
            best = min(best, abs(candidate - centroid_value))
    return max(0.0, 1.0 - best / 16.0)
