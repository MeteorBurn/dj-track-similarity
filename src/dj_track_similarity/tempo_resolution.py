from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

from .analysis_models import SonaraFeatureRow
from .library_models import TrackSummary
from .track_models import TrackIdentity


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
    identity: TrackIdentity,
    track: TrackSummary,
    sonara: SonaraFeatureRow | None = None,
) -> TempoEvidence:
    """Resolve tempo from one current v7 summary and optional SONARA row."""

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
    if sonara is not None:
        target = sonara.target
        if (
            target.catalog_uuid != identity.catalog_uuid
            or target.track_id != identity.track_id
            or target.track_uuid != identity.track_uuid
            or target.content_generation != identity.content_generation
        ):
            raise ValueError(
                "SONARA row identity does not match the current track summary"
            )
    return resolve_tempo_evidence_v7(
        sonara.values if sonara is not None else None,
        tag_bpm=track.tag_bpm,
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
    return _clamp01(
        reliability * _clamp01(measured_risk)
        + (1.0 - reliability) * _clamp01(neutral_risk)
    )


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
    return _clamp01(
        evidence.reliability * measured
        + (1.0 - evidence.reliability) * _clamp01(neutral_score)
    )


def tempo_filter_compatible(
    candidate: TempoEvidence, reference: TempoEvidence, tolerance_bpm: float
) -> bool:
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
    return _clamp01(
        1.0 - best_tempo_distance(candidate_bpm, reference_bpm) / TEMPO_MATCH_WINDOW_BPM
    )


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


def _candidate_bpms(value: object) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    result: list[float] = []
    for item in value:
        raw_bpm = item[0] if isinstance(item, (list, tuple)) and item else item
        bpm = _valid_bpm(raw_bpm)
        if bpm is not None:
            result.append(bpm)
    return _ordered_unique_bpms(result)


def _valid_bpm(value: object) -> float | None:
    bpm = _finite_float(value)
    if bpm is None or not 20.0 <= bpm <= 300.0:
        return None
    return float(bpm)


def _unit_interval_or_none(value: object) -> float | None:
    number = _finite_float(value)
    if number is None:
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


def resolve_tempo_evidence_v7(
    sonara_row: Mapping[str, object] | None,
    tag_bpm: float | None,
) -> TempoEvidence:
    """Resolve tempo from canonical v7 columns.

    A NULL SONARA confidence deliberately has zero reliability. It keeps the
    detected BPM as evidence, does not promote the tag BPM, and therefore
    yields the neutral 0.5 score in confidence-aware comparisons.
    """

    if sonara_row is None:
        fallback = _valid_bpm(tag_bpm)
        return TempoEvidence(
            bpm=fallback,
            alternatives=(fallback,) if fallback is not None else (),
            confidence=None,
            grid_stability=None,
            reliability=1.0 if fallback is not None else 0.0,
            source="tag" if fallback is not None else None,
        )

    sonara_bpm = _valid_bpm(sonara_row.get("detected_bpm"))
    confidence = _unit_interval_or_none(sonara_row.get("bpm_confidence"))
    grid_stability = _unit_interval_or_none(sonara_row.get("beat_grid_stability"))

    # Parse bpm_candidates_json — stored as a JSON array string in v7
    raw_candidates = sonara_row.get("bpm_candidates_json")
    candidate_bpms: tuple[float, ...] = ()
    if isinstance(raw_candidates, str):
        try:
            parsed = json.loads(raw_candidates)
        except (ValueError, TypeError):
            parsed = None
        candidate_bpms = _candidate_bpms(parsed)
    elif raw_candidates is not None:
        candidate_bpms = _candidate_bpms(raw_candidates)

    clean_tag_bpm = _valid_bpm(tag_bpm)

    if sonara_bpm is None:
        fallback = clean_tag_bpm
        return TempoEvidence(
            bpm=fallback,
            alternatives=(fallback,) if fallback is not None else (),
            confidence=None,
            grid_stability=None,
            reliability=1.0 if fallback is not None else 0.0,
            source="tag" if fallback is not None else None,
        )

    # BUG-R3 fix: NULL bpm_confidence → reliability = 0.0 → neutral 0.5
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
    if confidence is None:
        # NULL confidence → reliability stays 0.0; yield neutral score.
        # Tag BPM is not used as a scoring input when confidence is missing.
        pass
    elif clean_tag_bpm is not None:
        sonara_options = (sonara_bpm, *candidate_bpms)
        if any(
            best_tempo_distance(clean_tag_bpm, option) <= TAG_CANDIDATE_TOLERANCE_BPM
            for option in sonara_options
        ):
            selected_bpm = clean_tag_bpm
            source = "tag_confirmed_by_sonara_candidate"
            alternatives = _ordered_unique_bpms((*alternatives, clean_tag_bpm))

    return TempoEvidence(
        bpm=selected_bpm,
        alternatives=alternatives,
        confidence=confidence,
        grid_stability=grid_stability,
        reliability=_clamp01(reliability),
        source=source,
    )


def _finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
