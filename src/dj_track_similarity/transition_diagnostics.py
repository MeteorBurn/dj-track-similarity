from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import math
from typing import Any

from .metadata_payload import optional_float, string_or_none
from .models import Track


COMPONENT_NAMES = (
    "bpm_risk",
    "key_risk",
    "energy_jump_risk",
    "source_disagreement_risk",
)


@dataclass(frozen=True)
class TransitionDiagnostics:
    transition_risk: float | None
    components: dict[str, float | None]
    warnings: list[str]
    available_components: list[str]


def compute_transition_diagnostics(
    seed_track: Mapping[str, Any] | Track,
    candidate_track: Mapping[str, Any] | Track,
    source_count: int | None = None,
    max_source_count: int | None = None,
) -> TransitionDiagnostics:
    """Return lightweight transition-risk diagnostics from stored metadata only."""

    bpm_risk, bpm_warning = _bpm_risk(_track_bpm(seed_track), _track_bpm(candidate_track))
    key_risk, key_warning = _key_risk(_track_key(seed_track), _track_key(candidate_track))
    energy_risk, energy_warning = _energy_jump_risk(_track_energy(seed_track), _track_energy(candidate_track))
    source_risk, source_warning = _source_disagreement_risk(source_count, max_source_count)
    components = {
        "bpm_risk": bpm_risk,
        "key_risk": key_risk,
        "energy_jump_risk": energy_risk,
        "source_disagreement_risk": source_risk,
    }
    warnings = [
        warning
        for warning in (bpm_warning, key_warning, energy_warning, source_warning)
        if warning is not None
    ]
    available_components = [name for name in COMPONENT_NAMES if components[name] is not None]
    return TransitionDiagnostics(
        transition_risk=_mean_available(components[name] for name in COMPONENT_NAMES),
        components=components,
        warnings=warnings,
        available_components=available_components,
    )


def _bpm_risk(seed_bpm: float | None, candidate_bpm: float | None) -> tuple[float | None, str | None]:
    if seed_bpm is None or candidate_bpm is None:
        return None, "missing_bpm"
    if seed_bpm <= 0 or candidate_bpm <= 0:
        return None, "invalid_bpm"
    relative_delta = _best_relative_tempo_delta(seed_bpm, candidate_bpm)
    return _clamp(relative_delta / 0.12), None


def _key_risk(seed_key: str | None, candidate_key: str | None) -> tuple[float | None, str | None]:
    if seed_key is None or candidate_key is None:
        return None, "missing_key"
    if seed_key.casefold() == candidate_key.casefold():
        return 0.0, None
    return 0.5, None


def _energy_jump_risk(seed_energy: float | None, candidate_energy: float | None) -> tuple[float | None, str | None]:
    if seed_energy is None or candidate_energy is None:
        return None, "missing_energy"
    return _clamp(abs(candidate_energy - seed_energy)), None


def _source_disagreement_risk(source_count: int | None, max_source_count: int | None) -> tuple[float | None, str | None]:
    clean_source_count = _optional_non_negative_int(source_count)
    clean_max_source_count = _optional_non_negative_int(max_source_count)
    if clean_source_count is None and clean_max_source_count is None:
        return None, None
    if clean_source_count is None or clean_max_source_count is None or clean_max_source_count <= 0:
        return None, "invalid_source_consensus"
    consensus_ratio = _clamp(clean_source_count / clean_max_source_count)
    return 1.0 - consensus_ratio, None


def _track_bpm(track: Mapping[str, Any] | Track) -> float | None:
    return optional_float(_first_present(_track_value(track, "bpm"), _track_metadata(track).get("bpm")))


def _track_key(track: Mapping[str, Any] | Track) -> str | None:
    metadata = _track_metadata(track)
    return (
        string_or_none(_track_value(track, "musical_key"))
        or string_or_none(_track_value(track, "key"))
        or string_or_none(metadata.get("key"))
        or string_or_none(metadata.get("initialkey"))
    )


def _track_energy(track: Mapping[str, Any] | Track) -> float | None:
    return optional_float(_first_present(_track_value(track, "energy"), _track_metadata(track).get("energy")))


def _track_value(track: Mapping[str, Any] | Track, field_name: str) -> object:
    if isinstance(track, Mapping):
        return track.get(field_name)
    return getattr(track, field_name, None)


def _track_metadata(track: Mapping[str, Any] | Track) -> Mapping[str, Any]:
    metadata = track.get("metadata") if isinstance(track, Mapping) else track.metadata
    return metadata if isinstance(metadata, Mapping) else {}


def _first_present(*values: object) -> object:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _best_relative_tempo_delta(seed_bpm: float, candidate_bpm: float) -> float:
    seed_variants = (seed_bpm / 2.0, seed_bpm, seed_bpm * 2.0)
    return min(
        abs(candidate_bpm - seed_variant) / seed_variant
        for seed_variant in seed_variants
        if seed_variant > 0
    )


def _optional_non_negative_int(value: int | None) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        clean_value = int(value)
    except (TypeError, ValueError):
        return None
    if clean_value < 0:
        return None
    return clean_value


def _mean_available(values: Iterable[float | None]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _clamp(value: float) -> float:
    if not math.isfinite(value):
        return 1.0
    return min(1.0, max(0.0, value))
