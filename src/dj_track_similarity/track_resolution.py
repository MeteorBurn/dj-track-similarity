from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .metadata_payload import optional_float, string_or_none
from .models import Track
from .sonara_similarity_scoring import unwrap_feature_value


def resolve_track_bpm(
    track: Mapping[str, Any] | Track,
    *,
    sonara_values: Mapping[str, object] | None = None,
    sonara_features: Mapping[str, object] | None = None,
) -> float | None:
    metadata = _track_metadata(track)
    if sonara_values is not None:
        sonara_bpm = optional_float(sonara_values.get("bpm"))
        if sonara_bpm is not None:
            return sonara_bpm
    features = sonara_features if sonara_features is not None else _track_sonara_features(track)
    if features is not None:
        sonara_bpm = optional_float(unwrap_feature_value(features.get("bpm")))
        if sonara_bpm is not None:
            return sonara_bpm
    tag_bpm = _metadata_float(metadata, "bpm")
    if tag_bpm is not None:
        return tag_bpm
    return optional_float(_track_value(track, "bpm"))


def resolve_track_key(
    track: Mapping[str, Any] | Track,
    *,
    sonara_features: Mapping[str, object] | None = None,
) -> str | None:
    metadata = _track_metadata(track)
    tag_key = _metadata_text(metadata, "key", "initialkey")
    if tag_key:
        return tag_key
    track_key = string_or_none(_track_value(track, "musical_key")) or string_or_none(_track_value(track, "key"))
    if track_key:
        return track_key
    features = sonara_features if sonara_features is not None else _track_sonara_features(track)
    if features is None:
        return None
    return string_or_none(unwrap_feature_value(features.get("key")))


def camelot_compatibility(candidate_key: str | None, previous_key: str | None) -> tuple[str, float]:
    if not candidate_key or not previous_key:
        return "unknown", 0.55
    candidate = _parse_camelot(candidate_key)
    previous = _parse_camelot(previous_key)
    if candidate is None or previous is None:
        if candidate_key.strip().casefold() == previous_key.strip().casefold():
            return "same", 1.0
        return "unknown", 0.55
    candidate_number, candidate_letter = candidate
    previous_number, previous_letter = previous
    if candidate_number == previous_number and candidate_letter == previous_letter:
        return "same", 1.0
    if candidate_number == previous_number and candidate_letter != previous_letter:
        return "relative", 0.9
    if candidate_letter == previous_letter and candidate_number in {_wrap_camelot(previous_number - 1), _wrap_camelot(previous_number + 1)}:
        return "adjacent", 0.95
    return "clash", 0.2


def camelot_compatible(candidate_key: str | None, previous_key: str | None) -> bool:
    relation, _score = camelot_compatibility(candidate_key, previous_key)
    return relation in {"same", "relative", "adjacent"}


def _metadata_float(metadata: Mapping[str, object], *keys: str) -> float | None:
    for key in keys:
        number = optional_float(_first_metadata_value(metadata.get(key)))
        if number is not None:
            return number
    return None


def _metadata_text(metadata: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        text = string_or_none(metadata.get(key))
        if text:
            return text
    return None


def _first_metadata_value(value: object) -> object:
    if isinstance(value, (list, tuple)):
        for item in value:
            if item is not None and item != "":
                return item
        return None
    return value


def _track_value(track: Mapping[str, Any] | Track, field_name: str) -> object:
    if isinstance(track, Mapping):
        return track.get(field_name)
    return getattr(track, field_name, None)


def _track_metadata(track: Mapping[str, Any] | Track) -> Mapping[str, object]:
    metadata = track.get("metadata") if isinstance(track, Mapping) else track.metadata
    return metadata if isinstance(metadata, Mapping) else {}


def _track_sonara_features(track: Mapping[str, Any] | Track) -> Mapping[str, object] | None:
    features = _track_metadata(track).get("sonara_features")
    return features if isinstance(features, Mapping) else None


def _parse_camelot(value: str) -> tuple[int, str] | None:
    text = value.strip().upper()
    if len(text) not in {2, 3}:
        return None
    number_text, letter = text[:-1], text[-1]
    if letter not in {"A", "B"}:
        return None
    try:
        number = int(number_text)
    except ValueError:
        return None
    if not 1 <= number <= 12:
        return None
    return number, letter


def _wrap_camelot(number: int) -> int:
    return ((number - 1) % 12) + 1
