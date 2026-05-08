from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import inf
from typing import Literal

import numpy as np

from .database import LibraryDatabase
from .models import SearchResult, Track


SonaraSearchMode = Literal["balanced", "vibe", "sound", "dj_transition"]


@dataclass(frozen=True)
class _ComparableTrack:
    track: Track
    features: dict[str, object]


_VIBE_WEIGHTS = {
    "energy": 3.0,
    "danceability": 3.0,
    "valence": 1.4,
    "acousticness": 1.0,
    "loudness_lufs": 0.8,
    "dynamic_range_db": 0.8,
    "onset_density": 0.8,
    "rms_mean": 0.6,
}
_SOUND_WEIGHTS = {
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
_DJ_NUMERIC_WEIGHTS = {
    "bpm": 3.0,
    "onset_density": 2.0,
    "energy": 1.3,
    "danceability": 1.3,
    "key_confidence": 0.6,
    "chord_change_rate": 1.0,
    "dissonance": 1.0,
}
_TONAL_TEXT_WEIGHTS = {
    "key": 4.0,
    "predominant_chord": 3.0,
}
_BALANCED_WEIGHTS = {
    **{key: weight * 0.9 for key, weight in _VIBE_WEIGHTS.items()},
    **{key: weight * 0.7 for key, weight in _SOUND_WEIGHTS.items()},
    "bpm": 1.0,
    "chord_change_rate": 0.7,
    "dissonance": 0.7,
    "key_confidence": 0.4,
}


class SonaraSimilaritySearch:
    def __init__(self, db: LibraryDatabase) -> None:
        self.db = db

    def search(
        self,
        seed_track_ids: list[int],
        *,
        lookback_track_ids: list[int] | None = None,
        mode: SonaraSearchMode = "balanced",
        min_similarity: float | None = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        if not seed_track_ids:
            raise ValueError("At least one seed track is required")
        if mode not in {"balanced", "vibe", "sound", "dj_transition"}:
            raise ValueError(f"Unsupported SONARA search mode: {mode}")

        lookback_track_ids = lookback_track_ids or []
        all_tracks = self.db.list_tracks()
        context_ids = set(seed_track_ids) | set(lookback_track_ids)
        existing_ids = {track.id for track in all_tracks}
        unknown = [track_id for track_id in list(seed_track_ids) + list(lookback_track_ids) if track_id not in existing_ids]
        if unknown:
            raise ValueError(f"Unknown context tracks: {unknown}")

        tracks = [_ComparableTrack(track, features) for track in all_tracks if (features := _sonara_features(track))]
        track_by_id = {item.track.id: item for item in tracks}
        missing = [track_id for track_id in list(seed_track_ids) + list(lookback_track_ids) if track_id not in track_by_id]
        if missing:
            raise ValueError(f"Context tracks missing SONARA features: {missing}")
        if not tracks:
            return []

        numeric_weights = _numeric_weights_for_mode(mode)
        dimensions, ranges = _numeric_dimensions(tracks, numeric_weights)
        context = [track_by_id[track_id] for track_id in context_ids]
        centroid = _centroid(context, dimensions, ranges)
        tonal_context = _tonal_context(context)

        candidates: list[SearchResult] = []
        for item in tracks:
            if item.track.id in context_ids:
                continue
            score = _score_candidate(item, mode, dimensions, ranges, centroid, tonal_context)
            if score is None:
                continue
            if min_similarity is not None and score < min_similarity:
                continue
            candidates.append(SearchResult(track=item.track, score=score))

        candidates.sort(key=lambda result: result.score, reverse=True)
        return candidates[: max(0, limit)]


def _sonara_features(track: Track) -> dict[str, object] | None:
    metadata = track.metadata or {}
    features = metadata.get("sonara_features")
    return features if isinstance(features, dict) else None


def _numeric_weights_for_mode(mode: SonaraSearchMode) -> dict[str, float]:
    if mode == "vibe":
        return _VIBE_WEIGHTS
    if mode == "sound":
        return _SOUND_WEIGHTS
    if mode == "dj_transition":
        return _DJ_NUMERIC_WEIGHTS
    return _BALANCED_WEIGHTS


def _numeric_dimensions(
    tracks: list[_ComparableTrack],
    field_weights: dict[str, float],
) -> tuple[list[tuple[str, int | None, float]], dict[tuple[str, int | None], tuple[float, float]]]:
    values: dict[tuple[str, int | None], list[float]] = {}
    for item in tracks:
        for field in field_weights:
            for key, value in _feature_values(item.features, field):
                values.setdefault(key, []).append(value)

    dimensions: list[tuple[str, int | None, float]] = []
    ranges: dict[tuple[str, int | None], tuple[float, float]] = {}
    for field, weight in field_weights.items():
        indexes = sorted(index for name, index in values if name == field)
        if not indexes and (field, None) in values:
            indexes = [None]
        for index in indexes:
            key = (field, index)
            observed = values.get(key, [])
            if len(observed) < 2:
                continue
            dimensions.append((field, index, weight))
            ranges[key] = (min(observed), max(observed))
    return dimensions, ranges


def _feature_values(features: dict[str, object], field: str) -> list[tuple[tuple[str, int | None], float]]:
    value = features.get(field)
    if isinstance(value, (list, tuple)):
        pairs: list[tuple[tuple[str, int | None], float]] = []
        for index, item in enumerate(value):
            number = _optional_float(item)
            if number is not None:
                pairs.append(((field, index), number))
        return pairs
    number = _optional_float(value)
    return [((field, None), number)] if number is not None else []


def _centroid(
    context: list[_ComparableTrack],
    dimensions: list[tuple[str, int | None, float]],
    ranges: dict[tuple[str, int | None], tuple[float, float]],
) -> dict[tuple[str, int | None], float]:
    centroid: dict[tuple[str, int | None], float] = {}
    for field, index, _ in dimensions:
        key = (field, index)
        values = [
            normalized
            for item in context
            if (value := _feature_value(item.features, field, index)) is not None
            if (normalized := _normalize_feature(value, ranges[key])) is not None
        ]
        if values:
            centroid[key] = float(np.mean(values))
    return centroid


def _score_candidate(
    item: _ComparableTrack,
    mode: SonaraSearchMode,
    dimensions: list[tuple[str, int | None, float]],
    ranges: dict[tuple[str, int | None], tuple[float, float]],
    centroid: dict[tuple[str, int | None], float],
    tonal_context: dict[str, set[str]],
) -> float | None:
    weighted_score = 0.0
    total_weight = 0.0
    numeric_overlap = 0
    for field, index, weight in dimensions:
        key = (field, index)
        if key not in centroid:
            continue
        raw_value = _feature_value(item.features, field, index)
        if raw_value is None:
            continue
        if field == "bpm":
            score = _tempo_score(raw_value, _denormalize_feature(centroid[key], ranges[key]))
        else:
            value = _normalize_feature(raw_value, ranges[key])
            if value is None:
                continue
            score = max(0.0, 1.0 - abs(value - centroid[key]))
        weighted_score += score * weight
        total_weight += weight
        numeric_overlap += 1

    if mode in {"balanced", "dj_transition"}:
        for field, weight in _TONAL_TEXT_WEIGHTS.items():
            context_values = tonal_context.get(field, set())
            candidate = _normalize_text(item.features.get(field))
            if not context_values or candidate is None:
                continue
            weighted_score += (1.0 if candidate in context_values else 0.0) * weight
            total_weight += weight

    if numeric_overlap < 2 or total_weight <= 0:
        return None
    return max(0.0, min(1.0, weighted_score / total_weight))


def _tonal_context(context: list[_ComparableTrack]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for field in _TONAL_TEXT_WEIGHTS:
        values = [_normalize_text(item.features.get(field)) for item in context]
        values = [value for value in values if value]
        if values:
            most_common_count = Counter(values).most_common(1)[0][1]
            result[field] = {value for value, count in Counter(values).items() if count == most_common_count}
    return result


def _feature_value(features: dict[str, object], field: str, index: int | None) -> float | None:
    value = features.get(field)
    if index is not None:
        if not isinstance(value, (list, tuple)) or index >= len(value):
            return None
        value = value[index]
    return _optional_float(value)


def _normalize_feature(value: float, value_range: tuple[float, float]) -> float | None:
    lower, upper = value_range
    if upper == lower:
        return 0.5
    return (value - lower) / (upper - lower)


def _denormalize_feature(value: float, value_range: tuple[float, float]) -> float:
    lower, upper = value_range
    return lower + value * (upper - lower)


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number):
        return None
    return number


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().casefold()
    return text or None


def _tempo_score(candidate_bpm: float, centroid_bpm: float) -> float:
    candidate_variants = [candidate_bpm / 2, candidate_bpm, candidate_bpm * 2]
    centroid_variants = [centroid_bpm / 2, centroid_bpm, centroid_bpm * 2]
    best = inf
    for candidate in candidate_variants:
        for centroid in centroid_variants:
            best = min(best, abs(candidate - centroid))
    return max(0.0, 1.0 - best / 16.0)
