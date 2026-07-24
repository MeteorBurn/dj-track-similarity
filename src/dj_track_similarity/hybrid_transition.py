from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Protocol, TypeAlias

from .transition_diagnostics import (
    COMPONENT_NAMES,
    V2_COMPONENT_WEIGHTS,
    TransitionDiagnostics,
    TransitionTrack,
    compute_transition_diagnostics,
)

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | Sequence["JsonValue"] | Mapping[str, "JsonValue"]


class TransitionCandidate(Protocol):
    @property
    def transition_track(self) -> TransitionTrack: ...

    @property
    def source_contributions(self) -> Mapping[str, object]: ...

    @property
    def source_seed_diagnostics(self) -> Mapping[str, Mapping[str, JsonValue]]: ...

    @property
    def seed_track_ids(self) -> Sequence[int]: ...


def candidate_transition_diagnostics(
    candidate: TransitionCandidate,
    *,
    seed_tracks: Sequence[TransitionTrack],
    sources: Sequence[str],
    risk_version: str,
    classifier_risk_weights: Mapping[str, float],
) -> dict[str, JsonValue]:
    seed_tracks_by_id = {track.summary.track_id: track for track in seed_tracks}
    supporting_seed_track_ids, seed_scope = _transition_seed_scope(
        candidate, seed_tracks_by_id
    )
    source_count = sum(
        source in candidate.source_contributions for source in sources
    )
    diagnostics = tuple(
        compute_transition_diagnostics(
            seed_tracks_by_id[seed_track_id],
            candidate.transition_track,
            source_count=source_count,
            max_source_count=len(sources),
            risk_version=risk_version,
            classifier_risk_weights=classifier_risk_weights,
        )
        for seed_track_id in supporting_seed_track_ids
    )
    return _mean_transition_diagnostics(
        diagnostics,
        supporting_seed_track_ids=supporting_seed_track_ids,
        seed_scope=seed_scope,
        risk_version=risk_version,
    )


def _transition_seed_scope(
    candidate: TransitionCandidate,
    seed_tracks_by_id: Mapping[int, TransitionTrack],
) -> tuple[tuple[int, ...], str]:
    candidate_seed_track_ids = _known_seed_track_ids(
        candidate.seed_track_ids, seed_tracks_by_id
    )
    if candidate_seed_track_ids:
        return candidate_seed_track_ids, "candidate_supporting_seeds"

    source_seed_track_ids = _known_seed_track_ids(
        _source_diagnostic_seed_track_ids(candidate), seed_tracks_by_id
    )
    if source_seed_track_ids:
        return source_seed_track_ids, "source_supporting_seeds"

    return tuple(seed_tracks_by_id), "all_request_seeds"


def _source_diagnostic_seed_track_ids(
    candidate: TransitionCandidate,
) -> tuple[int, ...]:
    seed_track_ids: list[int] = []
    for source_diagnostics in candidate.source_seed_diagnostics.values():
        seed_track_ids.extend(
            _iterable_ints(source_diagnostics.get("supporting_seed_track_ids"))
        )
        seed_track_ids.extend(
            _iterable_ints((source_diagnostics.get("best_seed_track_id"),))
        )
    return tuple(dict.fromkeys(seed_track_ids))


def _known_seed_track_ids(
    seed_track_ids: Iterable[JsonValue],
    seed_tracks_by_id: Mapping[int, TransitionTrack],
) -> tuple[int, ...]:
    known_seed_track_ids: list[int] = []
    for value in seed_track_ids:
        seed_track_id = _optional_int(value)
        if seed_track_id is None or seed_track_id not in seed_tracks_by_id:
            continue
        known_seed_track_ids.append(seed_track_id)
    return tuple(dict.fromkeys(known_seed_track_ids))


def _iterable_ints(values: JsonValue) -> tuple[int, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
        return ()
    return tuple(value for item in values if (value := _optional_int(item)) is not None)


def _optional_int(value: JsonValue) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _mean_transition_diagnostics(
    diagnostics: Sequence[TransitionDiagnostics],
    *,
    supporting_seed_track_ids: Sequence[int],
    seed_scope: str,
    risk_version: str,
) -> dict[str, JsonValue]:
    components: dict[str, JsonValue] = {
        name: _mean_optional(
            diagnostic.components.get(name) for diagnostic in diagnostics
        )
        for name in COMPONENT_NAMES
    }
    transition_risk = _weighted_mean_components(components, V2_COMPONENT_WEIGHTS)
    components_v1: dict[str, JsonValue] = {
        name: _mean_optional(
            (diagnostic.components_v1 or {}).get(name) for diagnostic in diagnostics
        )
        for name in (
            "bpm_risk",
            "key_risk",
            "energy_jump_risk",
            "source_disagreement_risk",
        )
    }
    transition_risk_v1 = _mean_optional(
        diagnostic.transition_risk_v1 for diagnostic in diagnostics
    )
    warnings: list[JsonValue] = [
        warning
        for warning in sorted(
            {warning for diagnostic in diagnostics for warning in diagnostic.warnings}
        )
    ]
    available_components: list[JsonValue] = [
        name for name in COMPONENT_NAMES if components[name] is not None
    ]
    supporting_seed_ids: list[JsonValue] = [
        seed_track_id for seed_track_id in supporting_seed_track_ids
    ]
    return {
        "transition_risk": transition_risk,
        "components": components,
        "transition_risk_v1": transition_risk_v1,
        "components_v1": components_v1,
        "risk_version": risk_version,
        "warnings": warnings,
        "available_components": available_components,
        "supporting_seed_count": len(supporting_seed_track_ids),
        "supporting_seed_track_ids": supporting_seed_ids,
        "seed_scope": seed_scope,
        "method": "mean_aggregated_component_risks",
    }


def _mean_optional(values: Iterable[float | None]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _weighted_mean_components(
    values: Mapping[str, JsonValue], weights: Mapping[str, float]
) -> float | None:
    weighted_sum = 0.0
    total_weight = 0.0
    for name, value in values.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        weight = max(0.0, float(weights.get(name, 1.0)))
        if weight <= 0.0:
            continue
        weighted_sum += float(value) * weight
        total_weight += weight
    if total_weight <= 0.0:
        return None
    return weighted_sum / total_weight
