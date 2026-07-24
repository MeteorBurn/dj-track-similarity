from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .analysis_models import SonaraFeatureRow
from .library_models import TrackSummary
from .tempo_resolution import (
    LOW_BPM_CONFIDENCE,
    confidence_aware_tempo_risk,
    resolve_tempo_evidence_v7,
    tempo_pair_reliability,
)
from .track_models import TrackIdentity
from .track_resolution import (
    attenuate_harmonic_score,
    camelot_compatibility,
    canonical_camelot,
    key_name_to_camelot,
)


TRANSITION_RISK_V1 = "v1"
TRANSITION_RISK_V2 = "v2"
TRANSITION_RISK_VERSIONS = (TRANSITION_RISK_V1, TRANSITION_RISK_V2)
V1_COMPONENT_NAMES = (
    "bpm_risk",
    "key_risk",
    "energy_jump_risk",
    "source_disagreement_risk",
)
COMPONENT_NAMES = (
    *V1_COMPONENT_NAMES,
    "density_jump_risk",
    "texture_clash_risk",
    "mood_clash_risk",
    "vocal_conflict_risk",
    "grid_instability_risk",
    "structure_transition_risk",
    "confidence_missingness_risk",
)
V2_COMPONENT_WEIGHTS = {
    "bpm_risk": 1.0,
    "key_risk": 1.0,
    "energy_jump_risk": 1.0,
    "source_disagreement_risk": 1.0,
    "density_jump_risk": 0.75,
    "texture_clash_risk": 0.75,
    "mood_clash_risk": 0.75,
    "vocal_conflict_risk": 0.6,
    "grid_instability_risk": 0.6,
    "structure_transition_risk": 0.65,
    "confidence_missingness_risk": 0.4,
}
DENSITY_FEATURE_FIELDS = (
    "onset_density",
    "rhythm_density",
    "rms_mean",
    "loudness_lufs",
    "dynamic_range_db",
)
TEXTURE_FEATURE_FIELDS = (
    "mfcc_mean",
    "spectral_centroid_mean",
    "spectral_bandwidth_mean",
    "spectral_rolloff_mean",
    "spectral_flatness_mean",
    "spectral_contrast_mean",
)
MOOD_FEATURE_FIELDS = ("valence", "acousticness", "energy", "brightness")
VOCAL_CLASSIFIER_KEYWORDS = ("voice", "vocal")
OPTIONAL_V2_COMPONENT_NAMES = (
    "density_jump_risk",
    "texture_clash_risk",
    "mood_clash_risk",
    "vocal_conflict_risk",
)
MISSINGNESS_COMPONENT_NAMES = (
    "density_jump_risk",
    "texture_clash_risk",
    "mood_clash_risk",
)

_FEATURE_COLUMNS: Mapping[str, str] = {
    "onset_density": "onset_density_per_second",
    "rhythm_density": "onset_density_per_second",
    "rms_mean": "rms_mean",
    "loudness_lufs": "integrated_loudness_lufs",
    "dynamic_range_db": "dynamic_range_db",
    "mfcc_mean": "mfcc_mean_blob",
    "spectral_centroid_mean": "spectral_centroid_hz",
    "spectral_bandwidth_mean": "spectral_bandwidth_hz",
    "spectral_rolloff_mean": "spectral_rolloff_hz",
    "spectral_flatness_mean": "spectral_flatness",
    "spectral_contrast_mean": "spectral_contrast_mean_blob",
    "valence": "valence_score",
    "acousticness": "acousticness_score",
    "energy": "energy_score",
    "brightness": "spectral_centroid_hz",
    "energy_level": "energy_level",
    "grid_stability": "beat_grid_stability",
}


@dataclass(frozen=True)
class TransitionTrack:
    """One current v7 library row and its identity-bound SONARA output."""

    identity: TrackIdentity
    summary: TrackSummary
    sonara: SonaraFeatureRow | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, TrackIdentity):
            raise TypeError("identity must be a TrackIdentity")
        if not isinstance(self.summary, TrackSummary):
            raise TypeError("summary must be a TrackSummary")
        if (
            self.identity.catalog_uuid != self.summary.catalog_uuid
            or self.identity.track_id != self.summary.track_id
            or self.identity.track_uuid != self.summary.track_uuid
            or self.identity.content_generation != self.summary.content_generation
        ):
            raise ValueError("track identity does not match the current track summary")
        if self.sonara is None:
            return
        target = self.sonara.target
        if (
            target.catalog_uuid != self.identity.catalog_uuid
            or target.track_id != self.identity.track_id
            or target.track_uuid != self.identity.track_uuid
            or target.content_generation != self.identity.content_generation
        ):
            raise ValueError(
                "SONARA row identity does not match the current track summary"
            )


@dataclass(frozen=True)
class TransitionDiagnostics:
    transition_risk: float | None
    components: dict[str, float | None]
    warnings: list[str]
    available_components: list[str]
    risk_version: str = TRANSITION_RISK_V2
    transition_risk_v1: float | None = None
    components_v1: dict[str, float | None] | None = None


def structure_transition_score(
    seed_track: TransitionTrack,
    candidate_track: TransitionTrack,
) -> float | None:
    """Return compatibility from current, typed v7 structure fields."""

    risk, _warning = _structure_transition_risk(
        seed_track,
        candidate_track,
    )
    return None if risk is None else _clamp(1.0 - risk)


def compute_transition_diagnostics(
    seed_track: TransitionTrack,
    candidate_track: TransitionTrack,
    source_count: int | None = None,
    max_source_count: int | None = None,
    *,
    risk_version: str = TRANSITION_RISK_V2,
    classifier_risk_weights: Mapping[str, float] | None = None,
) -> TransitionDiagnostics:
    """Compute transition risk from identity-validated v7 repository rows."""

    if not isinstance(seed_track, TransitionTrack) or not isinstance(
        candidate_track,
        TransitionTrack,
    ):
        raise TypeError("transition diagnostics require TransitionTrack values")
    clean_risk_version = _risk_version(risk_version)
    clean_classifier_risk_weights = _clean_classifier_risk_weights(
        classifier_risk_weights
    )
    bpm_risk, bpm_warning = _bpm_risk(
        _track_bpm(seed_track),
        _track_bpm(candidate_track),
    )
    key_risk, key_warning = _plain_key_risk(
        _track_key_name(seed_track),
        _track_key_name(candidate_track),
    )
    energy_risk, energy_warning = _energy_jump_risk(
        _track_energy(seed_track),
        _track_energy(candidate_track),
    )
    source_risk, source_warning = _source_disagreement_risk(
        source_count,
        max_source_count,
    )
    v1_components = {
        "bpm_risk": bpm_risk,
        "key_risk": key_risk,
        "energy_jump_risk": energy_risk,
        "source_disagreement_risk": source_risk,
    }
    v1_warnings = [
        warning
        for warning in (
            bpm_warning,
            key_warning,
            energy_warning,
            source_warning,
        )
        if warning is not None
    ]
    transition_risk_v1 = _mean_available(
        v1_components[name] for name in V1_COMPONENT_NAMES
    )
    if clean_risk_version == TRANSITION_RISK_V1:
        return TransitionDiagnostics(
            transition_risk=transition_risk_v1,
            components=v1_components,
            warnings=v1_warnings,
            available_components=[
                name for name in V1_COMPONENT_NAMES if v1_components[name] is not None
            ],
            risk_version=TRANSITION_RISK_V1,
            transition_risk_v1=transition_risk_v1,
            components_v1=dict(v1_components),
        )

    bpm_risk, bpm_warning = _confidence_aware_bpm_risk(
        seed_track,
        candidate_track,
    )
    key_risk, key_warning = _key_risk(seed_track, candidate_track)
    density_risk, density_warning = _feature_group_risk(
        seed_track,
        candidate_track,
        DENSITY_FEATURE_FIELDS,
        "missing_density_features",
    )
    texture_risk, texture_warning = _feature_group_risk(
        seed_track,
        candidate_track,
        TEXTURE_FEATURE_FIELDS,
        "missing_texture_features",
    )
    mood_risk, mood_warning = _feature_group_risk(
        seed_track,
        candidate_track,
        MOOD_FEATURE_FIELDS,
        "missing_mood_features",
    )
    vocal_risk, vocal_warning = _vocal_conflict_risk(
        seed_track,
        candidate_track,
        classifier_risk_weights=clean_classifier_risk_weights,
    )
    grid_risk, grid_warning = _grid_instability_risk(
        seed_track,
        candidate_track,
    )
    structure_risk, structure_warning = _structure_transition_risk(
        seed_track,
        candidate_track,
    )
    components = {
        **v1_components,
        "bpm_risk": bpm_risk,
        "key_risk": key_risk,
        "density_jump_risk": density_risk,
        "texture_clash_risk": texture_risk,
        "mood_clash_risk": mood_risk,
        "vocal_conflict_risk": vocal_risk,
        "grid_instability_risk": grid_risk,
        "structure_transition_risk": structure_risk,
    }
    missingness_risk, missingness_warning = _confidence_missingness_risk(components)
    components["confidence_missingness_risk"] = missingness_risk
    warnings = [
        warning
        for warning in (
            bpm_warning,
            key_warning,
            energy_warning,
            source_warning,
            density_warning,
            texture_warning,
            mood_warning,
            vocal_warning,
            grid_warning,
            structure_warning,
            missingness_warning,
        )
        if warning is not None
    ]
    return TransitionDiagnostics(
        transition_risk=_weighted_mean_available(
            components,
            V2_COMPONENT_WEIGHTS,
        ),
        components=components,
        warnings=warnings,
        available_components=[
            name for name in COMPONENT_NAMES if components[name] is not None
        ],
        risk_version=TRANSITION_RISK_V2,
        transition_risk_v1=transition_risk_v1,
        components_v1=dict(v1_components),
    )


def _bpm_risk(
    seed_bpm: float | None,
    candidate_bpm: float | None,
) -> tuple[float | None, str | None]:
    if seed_bpm is None or candidate_bpm is None:
        return None, "missing_bpm"
    if seed_bpm <= 0 or candidate_bpm <= 0:
        return None, "invalid_bpm"
    relative_delta = _best_relative_tempo_delta(seed_bpm, candidate_bpm)
    return _clamp(relative_delta / 0.12), None


def _confidence_aware_bpm_risk(
    seed_track: TransitionTrack,
    candidate_track: TransitionTrack,
) -> tuple[float | None, str | None]:
    seed_tempo = _tempo_evidence(seed_track)
    candidate_tempo = _tempo_evidence(candidate_track)
    risk = confidence_aware_tempo_risk(candidate_tempo, seed_tempo)
    if risk is None:
        return None, "missing_bpm"
    warning = None
    if tempo_pair_reliability(candidate_tempo, seed_tempo) < LOW_BPM_CONFIDENCE:
        warning = "low_bpm_confidence"
    return risk, warning


def _key_risk(
    seed_track: TransitionTrack,
    candidate_track: TransitionTrack,
) -> tuple[float | None, str | None]:
    seed_key = _track_camelot(seed_track)
    candidate_key = _track_camelot(candidate_track)
    if seed_key is None or candidate_key is None:
        return None, "missing_key"
    _relation, compatibility_score = camelot_compatibility(
        candidate_key,
        seed_key,
    )
    seed_confidence = _track_key_confidence(seed_track)
    candidate_confidence = _track_key_confidence(candidate_track)
    compatibility_score = attenuate_harmonic_score(
        compatibility_score,
        seed_confidence,
        candidate_confidence,
    )
    confidence_values = [
        value for value in (seed_confidence, candidate_confidence) if value is not None
    ]
    warning = None
    if (
        confidence_values
        and math.prod(confidence_values) ** (1.0 / len(confidence_values)) < 0.45
    ):
        warning = "low_key_confidence"
    return _clamp(1.0 - compatibility_score), warning


def _plain_key_risk(
    seed_key: str | None,
    candidate_key: str | None,
) -> tuple[float | None, str | None]:
    if seed_key is None or candidate_key is None:
        return None, "missing_key"
    seed_camelot = canonical_camelot(seed_key) or key_name_to_camelot(seed_key)
    candidate_camelot = canonical_camelot(candidate_key) or key_name_to_camelot(
        candidate_key
    )
    if seed_camelot is None or candidate_camelot is None:
        score = (
            1.0
            if seed_key.strip().casefold() == candidate_key.strip().casefold()
            else 0.55
        )
    else:
        _relation, score = camelot_compatibility(
            candidate_camelot,
            seed_camelot,
        )
    return _clamp(1.0 - score), None


def _energy_jump_risk(
    seed_energy: float | None,
    candidate_energy: float | None,
) -> tuple[float | None, str | None]:
    if seed_energy is None or candidate_energy is None:
        return None, "missing_energy"
    return _clamp(abs(candidate_energy - seed_energy)), None


def _source_disagreement_risk(
    source_count: int | None,
    max_source_count: int | None,
) -> tuple[float | None, str | None]:
    clean_source_count = _optional_non_negative_int(source_count)
    clean_max_source_count = _optional_non_negative_int(max_source_count)
    if clean_source_count is None and clean_max_source_count is None:
        return None, None
    if (
        clean_source_count is None
        or clean_max_source_count is None
        or clean_max_source_count <= 0
    ):
        return None, "invalid_source_consensus"
    consensus_ratio = _clamp(clean_source_count / clean_max_source_count)
    return 1.0 - consensus_ratio, None


def _feature_group_risk(
    seed_track: TransitionTrack,
    candidate_track: TransitionTrack,
    fields: Sequence[str],
    missing_warning: str,
) -> tuple[float | None, str | None]:
    if seed_track.sonara is None and candidate_track.sonara is None:
        return None, None
    if seed_track.sonara is None or candidate_track.sonara is None:
        return None, missing_warning
    similarities = [
        similarity
        for field in fields
        if (
            similarity := _feature_similarity(
                seed_track,
                candidate_track,
                field,
            )
        )
        is not None
    ]
    if not similarities:
        return None, missing_warning
    return _clamp(1.0 - _mean(similarities)), None


def _feature_similarity(
    seed_track: TransitionTrack,
    candidate_track: TransitionTrack,
    field: str,
) -> float | None:
    seed_values = _feature_values(seed_track, field)
    candidate_values = _feature_values(candidate_track, field)
    if not seed_values or not candidate_values:
        return None
    pair_count = min(len(seed_values), len(candidate_values))
    return _mean(
        _numeric_similarity(seed_values[index], candidate_values[index])
        for index in range(pair_count)
    )


def _feature_values(
    track: TransitionTrack,
    field: str,
) -> tuple[float, ...]:
    if track.sonara is None:
        return ()
    if field == "energy_curve_summary":
        return tuple(
            value
            for name in (
                "energy_curve_mean",
                "energy_curve_stddev",
                "energy_curve_min",
                "energy_curve_max",
            )
            if (value := _finite_float(track.sonara.values.get(name))) is not None
        )
    column = _FEATURE_COLUMNS.get(field)
    if column is None:
        return ()
    value = track.sonara.values.get(column)
    if isinstance(value, (tuple, list)):
        return tuple(
            number for item in value if (number := _finite_float(item)) is not None
        )
    number = _finite_float(value)
    return (number,) if number is not None else ()


def _numeric_similarity(seed_value: float, candidate_value: float) -> float:
    scale = max(abs(seed_value), abs(candidate_value), 1.0)
    return _clamp(1.0 - abs(candidate_value - seed_value) / scale)


def _vocal_conflict_risk(
    seed_track: TransitionTrack,
    candidate_track: TransitionTrack,
    *,
    classifier_risk_weights: Mapping[str, float],
) -> tuple[float | None, str | None]:
    seed_scores = _classifier_scores(
        seed_track,
        VOCAL_CLASSIFIER_KEYWORDS,
    )
    candidate_scores = _classifier_scores(
        candidate_track,
        VOCAL_CLASSIFIER_KEYWORDS,
    )
    if not seed_scores and not candidate_scores and not classifier_risk_weights:
        return None, None
    risk_values: list[float] = []
    for key, candidate_score in candidate_scores.items():
        requested_weight = classifier_risk_weights.get(key, 0.0)
        if requested_weight > 0.0:
            risk_values.append(_clamp(candidate_score * requested_weight))
            continue
        seed_score = seed_scores.get(key)
        if seed_score is not None:
            risk_values.append(_clamp(abs(candidate_score - seed_score)))
    if risk_values:
        return _mean(risk_values), None
    return None, None


def _grid_instability_risk(
    seed_track: TransitionTrack,
    candidate_track: TransitionTrack,
) -> tuple[float | None, str | None]:
    seed_stability = _sonara_number(
        seed_track,
        "beat_grid_stability",
    )
    candidate_stability = _sonara_number(
        candidate_track,
        "beat_grid_stability",
    )
    if seed_stability is None and candidate_stability is None:
        return None, None
    if seed_stability is None or candidate_stability is None:
        return None, "missing_grid_stability"
    reliability = math.sqrt(_clamp(seed_stability) * _clamp(candidate_stability))
    return _clamp(1.0 - reliability), None


def _structure_transition_risk(
    seed_track: TransitionTrack,
    candidate_track: TransitionTrack,
) -> tuple[float | None, str | None]:
    if seed_track.sonara is None and candidate_track.sonara is None:
        return None, None
    if seed_track.sonara is None or candidate_track.sonara is None:
        return None, "missing_structure_features"

    risks: list[float] = []
    seed_outro_start = _sonara_number(seed_track, "outro_start_seconds")
    seed_duration = _track_duration(seed_track)
    candidate_intro_end = _sonara_number(
        candidate_track,
        "intro_end_seconds",
    )
    if (
        seed_outro_start is not None
        and seed_duration is not None
        and candidate_intro_end is not None
    ):
        outro_length = max(0.0, seed_duration - seed_outro_start)
        intro_length = max(0.0, candidate_intro_end)
        shared_mix_window = min(outro_length, intro_length)
        risks.append(_clamp(1.0 - shared_mix_window / 16.0))

    seed_energy_level = _sonara_number(seed_track, "energy_level")
    candidate_energy_level = _sonara_number(
        candidate_track,
        "energy_level",
    )
    if seed_energy_level is not None and candidate_energy_level is not None:
        risks.append(_clamp(abs(candidate_energy_level - seed_energy_level) / 10.0))

    curve_similarity = _feature_similarity(
        seed_track,
        candidate_track,
        "energy_curve_summary",
    )
    if curve_similarity is not None:
        risks.append(_clamp(1.0 - curve_similarity))

    if not risks:
        return None, "missing_structure_features"
    return _mean(risks), None


def _confidence_missingness_risk(
    components: Mapping[str, float | None],
) -> tuple[float | None, str | None]:
    present_optional = [
        name for name in MISSINGNESS_COMPONENT_NAMES if components.get(name) is not None
    ]
    if not present_optional:
        return None, None
    missing_count = len(MISSINGNESS_COMPONENT_NAMES) - len(present_optional)
    if missing_count <= 0:
        return 0.0, None
    risk = (missing_count / len(MISSINGNESS_COMPONENT_NAMES)) * 0.35
    return _clamp(risk), "partial_risk_feature_coverage"


def _track_bpm(track: TransitionTrack) -> float | None:
    detected = _sonara_number(track, "detected_bpm")
    return detected if detected is not None else _finite_float(track.summary.tag_bpm)


def _track_energy(track: TransitionTrack) -> float | None:
    return _sonara_number(track, "energy_score")


def _track_duration(track: TransitionTrack) -> float | None:
    analyzed = _sonara_number(track, "analyzed_duration_seconds")
    return (
        analyzed
        if analyzed is not None
        else _finite_float(track.summary.audio_duration_seconds)
    )


def _track_key_name(track: TransitionTrack) -> str | None:
    tag_key = _text(track.summary.tag_key)
    if tag_key:
        return tag_key
    return _sonara_text(track, "detected_key_name")


def _track_camelot(track: TransitionTrack) -> str | None:
    tag_key = _text(track.summary.tag_key)
    if (value := canonical_camelot(tag_key)) is not None:
        return value
    analyzed = _sonara_text(track, "detected_key_camelot")
    if (value := canonical_camelot(analyzed)) is not None:
        return value
    for key_name in (tag_key, _sonara_text(track, "detected_key_name")):
        if (value := key_name_to_camelot(key_name)) is not None:
            return value
    return None


def _track_key_confidence(track: TransitionTrack) -> float | None:
    tag_key = _text(track.summary.tag_key)
    if canonical_camelot(tag_key) is not None:
        return None
    analyzed_camelot = _sonara_text(track, "detected_key_camelot")
    analyzed_name = _sonara_text(track, "detected_key_name")
    if (
        canonical_camelot(analyzed_camelot) is None
        and key_name_to_camelot(analyzed_name) is None
    ):
        return None
    value = _sonara_number(track, "key_confidence")
    return _clamp(value) if value is not None else None


def _tempo_evidence(track: TransitionTrack):
    values: Mapping[str, object]
    if track.sonara is None:
        values = {}
    else:
        values = track.sonara.values
    return resolve_tempo_evidence_v7(values, tag_bpm=track.summary.tag_bpm)


def _classifier_scores(
    track: TransitionTrack,
    keywords: Sequence[str],
) -> dict[str, float]:
    return {
        score.classifier_key: _clamp(score.score)
        for score in track.summary.classifier_scores
        if _contains_keyword(score.classifier_key, keywords)
    }


def _sonara_number(track: TransitionTrack, field: str) -> float | None:
    if track.sonara is None:
        return None
    return _finite_float(track.sonara.values.get(field))


def _sonara_text(track: TransitionTrack, field: str) -> str | None:
    if track.sonara is None:
        return None
    return _text(track.sonara.values.get(field))


def _contains_keyword(value: object, keywords: Sequence[str]) -> bool:
    text = str(value).casefold()
    return any(keyword in text for keyword in keywords)


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


def _json_array(value: object) -> list[object]:
    if not isinstance(value, str):
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _best_relative_tempo_delta(
    seed_bpm: float,
    candidate_bpm: float,
) -> float:
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


def _risk_version(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in TRANSITION_RISK_VERSIONS:
        return text
    raise ValueError(
        f"transition_risk_version must be one of: {', '.join(TRANSITION_RISK_VERSIONS)}"
    )


def _clean_classifier_risk_weights(
    values: Mapping[str, float] | None,
) -> dict[str, float]:
    if not values:
        return {}
    clean_values: dict[str, float] = {}
    for key, value in values.items():
        classifier_key = str(key).strip()
        if not classifier_key:
            continue
        clean_values[classifier_key] = _unit_interval(
            value,
            f"classifier_risk_weights.{classifier_key}",
        )
    return clean_values


def _unit_interval(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be between 0 and 1")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be between 0 and 1") from error
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return number


def _mean_available(values: Iterable[float | None]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _weighted_mean_available(
    values: Mapping[str, float | None],
    weights: Mapping[str, float],
) -> float | None:
    weighted_sum = 0.0
    total_weight = 0.0
    for name, value in values.items():
        if value is None:
            continue
        weight = max(0.0, float(weights.get(name, 1.0)))
        if weight <= 0.0:
            continue
        weighted_sum += _clamp(float(value)) * weight
        total_weight += weight
    if total_weight <= 0.0:
        return None
    return weighted_sum / total_weight


def _mean(values: Iterable[float]) -> float:
    numbers = [float(value) for value in values]
    if not numbers:
        raise ValueError("Cannot average an empty value sequence")
    return sum(numbers) / len(numbers)


def _clamp(value: float) -> float:
    if not math.isfinite(value):
        return 1.0
    return min(1.0, max(0.0, value))
