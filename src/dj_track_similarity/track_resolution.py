from __future__ import annotations

from collections.abc import Mapping
import math
import re
from typing import Any

from .metadata_payload import optional_float, string_or_none
from .models import Track
from .sonara_contract import current_sonara_features
from .tempo_resolution import resolve_tempo_evidence


def resolve_track_bpm(
    track: Mapping[str, Any] | Track,
    *,
    sonara_values: Mapping[str, object] | None = None,
    sonara_features: Mapping[str, object] | None = None,
) -> float | None:
    return resolve_tempo_evidence(
        track,
        sonara_values=sonara_values,
        sonara_features=sonara_features,
    ).bpm


def resolve_track_key(
    track: Mapping[str, Any] | Track,
    *,
    sonara_features: Mapping[str, object] | None = None,
) -> str | None:
    metadata = _track_metadata(track)
    tag_key = _metadata_text(metadata, "key", "initialkey")
    if tag_key:
        return tag_key
    features = sonara_features if sonara_features is not None else _track_sonara_features(track)
    if features is not None:
        sonara_key = string_or_none(_unwrap_feature_value(features.get("key")))
        if sonara_key:
            return sonara_key
    if _has_persisted_sonara(track, metadata):
        return None
    return string_or_none(_track_value(track, "musical_key")) or string_or_none(_track_value(track, "key"))


def resolve_track_energy(
    track: Mapping[str, Any] | Track,
    *,
    sonara_features: Mapping[str, object] | None = None,
) -> float | None:
    """Resolve energy without trusting a column left behind by stale SONARA analysis."""

    metadata = _track_metadata(track)
    features = sonara_features if sonara_features is not None else _track_sonara_features(track)
    if features is not None:
        sonara_energy = optional_float(_unwrap_feature_value(features.get("energy")))
        if sonara_energy is not None and math.isfinite(sonara_energy):
            return float(sonara_energy)
    tag_energy = optional_float(_first_metadata_value(metadata.get("energy")))
    if tag_energy is not None and math.isfinite(tag_energy):
        return float(tag_energy)
    if _has_persisted_sonara(track, metadata):
        return None
    track_energy = optional_float(_track_value(track, "energy"))
    return float(track_energy) if track_energy is not None and math.isfinite(track_energy) else None


def resolve_track_camelot(
    track: Mapping[str, Any] | Track,
    *,
    sonara_features: Mapping[str, object] | None = None,
) -> str | None:
    """Resolve one canonical Camelot code without treating a key name as a Camelot code.

    An explicit Camelot tag is authoritative. Otherwise SONARA's analyzed ``key_camelot`` wins
    before ordinary key names are converted. This keeps a conventional tag such as ``A minor``
    from masking SONARA's already-normalized ``8A`` value.
    """

    camelot, _source = _resolve_track_camelot_with_source(track, sonara_features=sonara_features)
    return camelot


def resolve_track_key_confidence(
    track: Mapping[str, Any] | Track,
    *,
    sonara_features: Mapping[str, object] | None = None,
) -> float | None:
    """Return SONARA key confidence only when the resolved Camelot value came from SONARA."""

    _camelot, source = _resolve_track_camelot_with_source(track, sonara_features=sonara_features)
    if source != "sonara":
        return None
    features = sonara_features if sonara_features is not None else _track_sonara_features(track)
    if features is None:
        return None
    sonara_camelot = string_or_none(_unwrap_feature_value(features.get("key_camelot")))
    sonara_key = string_or_none(_unwrap_feature_value(features.get("key")))
    if canonical_camelot(sonara_camelot) is None and key_name_to_camelot(sonara_key) is None:
        return None
    confidence = optional_float(_unwrap_feature_value(features.get("key_confidence")))
    if confidence is None or not math.isfinite(confidence):
        return None
    return max(0.0, min(1.0, confidence))


def _resolve_track_camelot_with_source(
    track: Mapping[str, Any] | Track,
    *,
    sonara_features: Mapping[str, object] | None = None,
) -> tuple[str | None, str | None]:
    metadata = _track_metadata(track)
    tag_keys = _metadata_key_texts(metadata)
    for tag_key in tag_keys:
        if (camelot := canonical_camelot(tag_key)) is not None:
            return camelot, "tag"

    features = sonara_features if sonara_features is not None else _track_sonara_features(track)
    if features is not None:
        sonara_camelot = string_or_none(_unwrap_feature_value(features.get("key_camelot")))
        if (camelot := canonical_camelot(sonara_camelot)) is not None:
            return camelot, "sonara"

    sonara_key = string_or_none(_unwrap_feature_value(features.get("key"))) if features is not None else None
    track_key = None
    if not _has_persisted_sonara(track, metadata):
        track_key = string_or_none(_track_value(track, "musical_key")) or string_or_none(_track_value(track, "key"))
    for value, source in (
        *((tag_key, "tag") for tag_key in tag_keys),
        (sonara_key, "sonara"),
        (track_key, "track"),
    ):
        if (camelot := key_name_to_camelot(value)) is not None:
            return camelot, source
    return None, None


def camelot_compatibility(candidate_key: str | None, previous_key: str | None) -> tuple[str, float]:
    if not candidate_key or not previous_key:
        return "unknown", 0.55
    candidate = _parse_camelot(key_name_to_camelot(candidate_key) or "")
    previous = _parse_camelot(key_name_to_camelot(previous_key) or "")
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


def attenuate_harmonic_score(
    score: float,
    *confidences: float | None,
    neutral_score: float = 0.55,
) -> float:
    """Pull harmonic evidence toward neutral below the usable-confidence threshold."""

    clean = [
        max(0.0, min(1.0, value / KEY_CONFIDENCE_FULL_WEIGHT))
        for value in confidences
        if value is not None and math.isfinite(value)
    ]
    if not clean:
        return max(0.0, min(1.0, score))
    reliability = math.prod(clean) ** (1.0 / len(clean))
    attenuated = neutral_score + reliability * (score - neutral_score)
    return max(0.0, min(1.0, attenuated))


def canonical_camelot(value: str | None) -> str | None:
    parsed = _parse_camelot(value or "")
    if parsed is None:
        return None
    number, letter = parsed
    return f"{number}{letter}"


def key_name_to_camelot(value: str | None) -> str | None:
    if not value:
        return None
    if (camelot := canonical_camelot(value)) is not None:
        return camelot
    match = _KEY_NAME_PATTERN.fullmatch(value.strip())
    if match is None:
        return None
    note = match.group(1).upper() + match.group(2).replace("♯", "#").replace("♭", "b")
    quality = (match.group(3) or "major").casefold()
    mode = "minor" if quality in {"m", "min", "minor"} else "major"
    return _KEY_NAME_TO_CAMELOT.get((note, mode))


def _metadata_text(metadata: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        text = string_or_none(_first_metadata_value(metadata.get(key)))
        if text:
            return text
    return None


def _metadata_key_texts(metadata: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("key", "initialkey"):
        raw_value = metadata.get(key)
        items = raw_value if isinstance(raw_value, (list, tuple)) else (raw_value,)
        for item in items:
            text = string_or_none(item)
            if text is not None and text not in values:
                values.append(text)
    return tuple(values)


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
    return current_sonara_features(_track_metadata(track), allow_unsigned=isinstance(track, Mapping))


def _has_persisted_sonara(track: Mapping[str, Any] | Track, metadata: Mapping[str, object]) -> bool:
    return isinstance(track, Track) and isinstance(metadata.get("sonara_features"), Mapping)


def _unwrap_feature_value(value: object) -> object:
    if isinstance(value, Mapping) and "value" in value:
        return value.get("value")
    return value


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


_KEY_NAME_PATTERN = re.compile(r"([A-Ga-g])\s*([#b♯♭]?)\s*(major|maj|minor|min|m)?", re.IGNORECASE)
KEY_CONFIDENCE_FULL_WEIGHT = 0.45

_KEY_NAME_TO_CAMELOT = {
    ("G#", "minor"): "1A",
    ("Ab", "minor"): "1A",
    ("D#", "minor"): "2A",
    ("Eb", "minor"): "2A",
    ("A#", "minor"): "3A",
    ("Bb", "minor"): "3A",
    ("F", "minor"): "4A",
    ("C", "minor"): "5A",
    ("G", "minor"): "6A",
    ("D", "minor"): "7A",
    ("A", "minor"): "8A",
    ("E", "minor"): "9A",
    ("B", "minor"): "10A",
    ("F#", "minor"): "11A",
    ("Gb", "minor"): "11A",
    ("C#", "minor"): "12A",
    ("Db", "minor"): "12A",
    ("B", "major"): "1B",
    ("F#", "major"): "2B",
    ("Gb", "major"): "2B",
    ("C#", "major"): "3B",
    ("Db", "major"): "3B",
    ("G#", "major"): "4B",
    ("Ab", "major"): "4B",
    ("D#", "major"): "5B",
    ("Eb", "major"): "5B",
    ("A#", "major"): "6B",
    ("Bb", "major"): "6B",
    ("F", "major"): "7B",
    ("C", "major"): "8B",
    ("G", "major"): "9B",
    ("D", "major"): "10B",
    ("A", "major"): "11B",
    ("E", "major"): "12B",
}
