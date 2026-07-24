from __future__ import annotations

import math
import re

from .analysis_models import SonaraFeatureRow
from .library_models import TrackSummary
from .tempo_resolution import resolve_tempo_evidence
from .track_models import TrackIdentity


def resolve_track_bpm(
    identity: TrackIdentity,
    track: TrackSummary,
    sonara: SonaraFeatureRow | None = None,
) -> float | None:
    return resolve_tempo_evidence(identity, track, sonara).bpm


def resolve_track_key(
    identity: TrackIdentity,
    track: TrackSummary,
    sonara: SonaraFeatureRow | None = None,
) -> str | None:
    values = _validated_sonara_values(identity, track, sonara)
    tag_key = _text(track.tag_key)
    if tag_key:
        return tag_key
    return _text(values.get("detected_key_name"))


def resolve_track_energy(
    identity: TrackIdentity,
    track: TrackSummary,
    sonara: SonaraFeatureRow | None = None,
) -> float | None:
    """Resolve energy only from an identity-validated SONARA Core row."""

    values = _validated_sonara_values(identity, track, sonara)
    return _finite_float(values.get("energy_score"))


def resolve_track_camelot(
    identity: TrackIdentity,
    track: TrackSummary,
    sonara: SonaraFeatureRow | None = None,
) -> str | None:
    """Resolve one canonical Camelot code without treating a key name as a Camelot code.

    An explicit Camelot tag is authoritative. Otherwise SONARA's analyzed ``key_camelot`` wins
    before ordinary key names are converted. This keeps a conventional tag such as ``A minor``
    from masking SONARA's already-normalized ``8A`` value.
    """

    camelot, _source = _resolve_track_camelot_with_source(
        identity,
        track,
        sonara,
    )
    return camelot


def resolve_track_key_confidence(
    identity: TrackIdentity,
    track: TrackSummary,
    sonara: SonaraFeatureRow | None = None,
) -> float | None:
    """Return SONARA key confidence only when the resolved Camelot value came from SONARA."""

    _camelot, source = _resolve_track_camelot_with_source(
        identity,
        track,
        sonara,
    )
    if source != "sonara":
        return None
    values = _validated_sonara_values(identity, track, sonara)
    sonara_camelot = _text(values.get("detected_key_camelot"))
    sonara_key = _text(values.get("detected_key_name"))
    if (
        canonical_camelot(sonara_camelot) is None
        and key_name_to_camelot(sonara_key) is None
    ):
        return None
    confidence = _finite_float(values.get("key_confidence"))
    if confidence is None:
        return None
    return max(0.0, min(1.0, confidence))


def _resolve_track_camelot_with_source(
    identity: TrackIdentity,
    track: TrackSummary,
    sonara: SonaraFeatureRow | None,
) -> tuple[str | None, str | None]:
    values = _validated_sonara_values(identity, track, sonara)
    tag_key = _text(track.tag_key)
    if (camelot := canonical_camelot(tag_key)) is not None:
        return camelot, "tag"

    sonara_camelot = _text(values.get("detected_key_camelot"))
    if (camelot := canonical_camelot(sonara_camelot)) is not None:
        return camelot, "sonara"

    sonara_key = _text(values.get("detected_key_name"))
    for value, source in (
        (tag_key, "tag"),
        (sonara_key, "sonara"),
    ):
        if (camelot := key_name_to_camelot(value)) is not None:
            return camelot, source
    return None, None


def camelot_compatibility(
    candidate_key: str | None, previous_key: str | None
) -> tuple[str, float]:
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
    if candidate_letter == previous_letter and candidate_number in {
        _wrap_camelot(previous_number - 1),
        _wrap_camelot(previous_number + 1),
    }:
        return "adjacent", 0.95
    return "clash", 0.2


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


def _validated_sonara_values(
    identity: TrackIdentity,
    track: TrackSummary,
    sonara: SonaraFeatureRow | None,
) -> dict[str, object]:
    if not isinstance(identity, TrackIdentity):
        raise TypeError("identity must be a TrackIdentity")
    if not isinstance(track, TrackSummary):
        raise TypeError("track must be a TrackSummary")
    if (
        identity.catalog_uuid != track.catalog_uuid
        or identity.track_id != track.track_id
        or identity.track_uuid != track.track_uuid
        or identity.content_generation != track.content_generation
    ):
        raise ValueError("track identity does not match the current track summary")
    if sonara is None:
        return {}
    target = sonara.target
    if (
        target.catalog_uuid != identity.catalog_uuid
        or target.track_id != identity.track_id
        or target.track_uuid != identity.track_uuid
        or target.content_generation != identity.content_generation
    ):
        raise ValueError("SONARA row identity does not match the current track summary")
    return dict(sonara.values)


def _finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


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


_KEY_NAME_PATTERN = re.compile(
    r"([A-Ga-g])\s*([#b♯♭]?)\s*(major|maj|minor|min|m)?", re.IGNORECASE
)
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
