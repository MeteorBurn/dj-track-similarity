from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from .metadata_payload import optional_float
from .models import Track
from .sonara_contract import current_sonara_features


LOW_BPM_CONFIDENCE = 0.45
NEUTRAL_TEMPO_SCORE = 0.5
TEMPO_MATCH_WINDOW_BPM = 16.0
TAG_CANDIDATE_TOLERANCE_BPM = 4.0


@dataclass(frozen=True)
class TempoEvidence:
    bpm: float | None
    alternatives: tuple[float, ...]
    confidence: float | None
    grid_stability: float | None
    reliability: float
    source: str | None


def resolve_tempo_evidence(
    track: Mapping[str, Any] | Track,
    *,
    sonara_values: Mapping[str, object] | None = None,
    sonara_features: Mapping[str, object] | None = None,
) -> TempoEvidence:
    """Resolve tempo plus its trust signals without treating confidence as similarity.

    SONARA remains the primary source when its confidence is usable. Below the v0.2.4
    low-confidence threshold, candidates and the file-tag BPM are retained as alternatives. A tag
    corroborated by any SONARA candidate becomes the working BPM while the original confidence
    still controls how strongly tempo affects ranking.
    """

    metadata = _track_metadata(track)
    stored_features = _metadata_sonara_features(metadata, allow_unsigned=isinstance(track, Mapping))
    sources = tuple(
        source
        for source in (sonara_values, sonara_features, stored_features)
        if isinstance(source, Mapping)
    )
    sonara_bpm = _valid_bpm(_first_sonara_value(sources, "bpm"))
    confidence = _unit_interval_or_none(_first_sonara_value(sources, "bpm_confidence"))
    grid_stability = _unit_interval_or_none(_first_sonara_value(sources, "grid_stability"))
    candidate_bpms = _candidate_bpms(_first_sonara_value(sources, "bpm_candidates"))
    tag_bpm = _metadata_bpm(metadata)

    if sonara_bpm is None:
        persisted_sonara_is_stale = isinstance(track, Track) and isinstance(metadata.get("sonara_features"), Mapping)
        track_bpm = None if persisted_sonara_is_stale else _valid_bpm(_track_value(track, "bpm"))
        fallback = tag_bpm or track_bpm
        return TempoEvidence(
            bpm=fallback,
            alternatives=(fallback,) if fallback is not None else (),
            confidence=None,
            grid_stability=None,
            reliability=1.0 if fallback is not None else 0.0,
            source="tag" if tag_bpm is not None else ("track" if fallback is not None else None),
        )

    reliability = confidence if confidence is not None else 0.0
    if grid_stability is not None:
        reliability = math.sqrt(reliability * grid_stability)

    low_confidence = confidence is None or confidence < LOW_BPM_CONFIDENCE
    if not low_confidence:
        return TempoEvidence(
            bpm=sonara_bpm,
            alternatives=(sonara_bpm,),
            confidence=confidence,
            grid_stability=grid_stability,
            reliability=_clamp01(reliability),
            source="sonara",
        )

    alternatives = _ordered_unique_bpms((sonara_bpm, *candidate_bpms))
    selected_bpm = sonara_bpm
    source = "sonara_low_confidence"
    if confidence is None and tag_bpm is not None:
        selected_bpm = tag_bpm
        alternatives = (tag_bpm,)
        source = "legacy_tag_fallback"
        reliability = 1.0
    elif tag_bpm is not None:
        sonara_options = (sonara_bpm, *candidate_bpms)
        if any(best_tempo_distance(tag_bpm, option) <= TAG_CANDIDATE_TOLERANCE_BPM for option in sonara_options):
            selected_bpm = tag_bpm
            source = "tag_confirmed_by_sonara_candidate"
            alternatives = _ordered_unique_bpms((*alternatives, tag_bpm))

    return TempoEvidence(
        bpm=selected_bpm,
        alternatives=alternatives,
        confidence=confidence,
        grid_stability=grid_stability,
        reliability=_clamp01(reliability),
        source=source,
    )


def confidence_aware_tempo_score(
    candidate: TempoEvidence,
    reference: TempoEvidence,
    *,
    neutral_score: float = NEUTRAL_TEMPO_SCORE,
) -> float | None:
    if candidate.bpm is None or reference.bpm is None:
        return None
    measured_match = max(
        measured_tempo_score(candidate_bpm, reference_bpm)
        for candidate_bpm in candidate.alternatives or (candidate.bpm,)
        for reference_bpm in reference.alternatives or (reference.bpm,)
    )
    reliability = tempo_pair_reliability(candidate, reference)
    neutral = _clamp01(neutral_score)
    return _clamp01(reliability * measured_match + (1.0 - reliability) * neutral)


def confidence_aware_tempo_risk(
    candidate: TempoEvidence,
    reference: TempoEvidence,
    *,
    neutral_risk: float = NEUTRAL_TEMPO_SCORE,
    relative_tolerance: float = 0.12,
) -> float | None:
    if candidate.bpm is None or reference.bpm is None:
        return None
    measured_risk = min(
        _relative_tempo_delta(candidate_bpm, reference_bpm) / relative_tolerance
        for candidate_bpm in candidate.alternatives or (candidate.bpm,)
        for reference_bpm in reference.alternatives or (reference.bpm,)
    )
    reliability = tempo_pair_reliability(candidate, reference)
    return _clamp01(reliability * _clamp01(measured_risk) + (1.0 - reliability) * _clamp01(neutral_risk))


def confidence_aware_target_score(
    evidence: TempoEvidence,
    target_bpm: float,
    tolerance_bpm: float,
    *,
    neutral_score: float = NEUTRAL_TEMPO_SCORE,
) -> float | None:
    if evidence.bpm is None or tolerance_bpm <= 0:
        return None
    measured = max(
        _clamp01(1.0 - abs(option - target_bpm) / tolerance_bpm)
        for option in evidence.alternatives or (evidence.bpm,)
    )
    return _clamp01(evidence.reliability * measured + (1.0 - evidence.reliability) * _clamp01(neutral_score))


def tempo_filter_compatible(candidate: TempoEvidence, reference: TempoEvidence, tolerance_bpm: float) -> bool:
    if candidate.bpm is None or reference.bpm is None:
        return False
    distance = min(
        best_tempo_distance(candidate_bpm, reference_bpm)
        for candidate_bpm in candidate.alternatives or (candidate.bpm,)
        for reference_bpm in reference.alternatives or (reference.bpm,)
    )
    if distance <= max(0.0, float(tolerance_bpm)):
        return True
    # A hard BPM filter must not reject ambient/rubato material on an explicitly unreliable
    # estimate. Candidate/tag alternatives were already checked above.
    return tempo_pair_reliability(candidate, reference) < LOW_BPM_CONFIDENCE


def tempo_pair_reliability(candidate: TempoEvidence, reference: TempoEvidence) -> float:
    return math.sqrt(_clamp01(candidate.reliability) * _clamp01(reference.reliability))


def measured_tempo_score(candidate_bpm: float, reference_bpm: float) -> float:
    return _clamp01(1.0 - best_tempo_distance(candidate_bpm, reference_bpm) / TEMPO_MATCH_WINDOW_BPM)


def best_tempo_distance(candidate_bpm: float, reference_bpm: float) -> float:
    # Scale at most one side of the pair. Scaling both sides would make a quarter/quadruple ratio
    # (for example 60 vs 240) look like an exact match through 120 vs 120.
    pairs = (
        (candidate_bpm, reference_bpm),
        (candidate_bpm / 2.0, reference_bpm),
        (candidate_bpm * 2.0, reference_bpm),
        (candidate_bpm, reference_bpm / 2.0),
        (candidate_bpm, reference_bpm * 2.0),
    )
    return min(abs(candidate - reference) for candidate, reference in pairs)


def _relative_tempo_delta(candidate_bpm: float, reference_bpm: float) -> float:
    pairs = (
        (candidate_bpm, reference_bpm),
        (candidate_bpm / 2.0, reference_bpm),
        (candidate_bpm * 2.0, reference_bpm),
        (candidate_bpm, reference_bpm / 2.0),
        (candidate_bpm, reference_bpm * 2.0),
    )
    return min(
        abs(candidate - reference) / max(abs(reference), 1e-9)
        for candidate, reference in pairs
    )


def _first_sonara_value(sources: Sequence[Mapping[str, object]], key: str) -> object:
    for source in sources:
        if key in source:
            return _unwrap_feature_value(source.get(key))
    return None


def _candidate_bpms(value: object) -> tuple[float, ...]:
    value = _unwrap_feature_value(value)
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[float] = []
    for item in value:
        raw_bpm = item[0] if isinstance(item, (list, tuple)) and item else item
        bpm = _valid_bpm(raw_bpm)
        if bpm is not None:
            result.append(bpm)
    return _ordered_unique_bpms(result)


def _metadata_bpm(metadata: Mapping[str, object]) -> float | None:
    for key in ("bpm", "tbpm"):
        raw_value = metadata.get(key)
        if isinstance(raw_value, (list, tuple)):
            raw_value = next((item for item in raw_value if item not in (None, "")), None)
        bpm = _valid_bpm(raw_value)
        if bpm is not None:
            return bpm
    return None


def _metadata_sonara_features(
    metadata: Mapping[str, object],
    *,
    allow_unsigned: bool,
) -> Mapping[str, object] | None:
    return current_sonara_features(metadata, allow_unsigned=allow_unsigned)


def _track_metadata(track: Mapping[str, Any] | Track) -> Mapping[str, object]:
    metadata = track.get("metadata") if isinstance(track, Mapping) else track.metadata
    return metadata if isinstance(metadata, Mapping) else {}


def _track_value(track: Mapping[str, Any] | Track, field_name: str) -> object:
    if isinstance(track, Mapping):
        return track.get(field_name)
    return getattr(track, field_name, None)


def _unwrap_feature_value(value: object) -> object:
    if isinstance(value, Mapping) and "value" in value:
        return value.get("value")
    return value


def _valid_bpm(value: object) -> float | None:
    bpm = optional_float(value)
    if bpm is None or not math.isfinite(bpm) or not 20.0 <= bpm <= 300.0:
        return None
    return float(bpm)


def _unit_interval_or_none(value: object) -> float | None:
    number = optional_float(value)
    if number is None or not math.isfinite(number):
        return None
    return _clamp01(float(number))


def _ordered_unique_bpms(values: Sequence[float | None]) -> tuple[float, ...]:
    result: list[float] = []
    for raw_value in values:
        value = _valid_bpm(raw_value)
        if value is None or any(abs(existing - value) < 1e-6 for existing in result):
            continue
        result.append(value)
    return tuple(result)


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, float(value)))
