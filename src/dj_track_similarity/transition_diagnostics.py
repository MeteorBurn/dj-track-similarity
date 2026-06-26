from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from .metadata_payload import optional_float
from .models import Track
from .sonara_similarity_scoring import unwrap_feature_value
from .track_resolution import camelot_compatibility, resolve_track_bpm, resolve_track_key


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
    "confidence_missingness_risk": 0.4,
}
DENSITY_FEATURE_FIELDS = ("onset_density", "rhythm_density", "rms_mean", "loudness_lufs", "dynamic_range_db")
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


@dataclass(frozen=True)
class TransitionDiagnostics:
    transition_risk: float | None
    components: dict[str, float | None]
    warnings: list[str]
    available_components: list[str]
    risk_version: str = TRANSITION_RISK_V2
    transition_risk_v1: float | None = None
    components_v1: dict[str, float | None] | None = None


def compute_transition_diagnostics(
    seed_track: Mapping[str, Any] | Track,
    candidate_track: Mapping[str, Any] | Track,
    source_count: int | None = None,
    max_source_count: int | None = None,
    *,
    risk_version: str = TRANSITION_RISK_V2,
    classifier_risk_weights: Mapping[str, float] | None = None,
) -> TransitionDiagnostics:
    """Return lightweight transition-risk diagnostics from stored metadata only."""

    clean_risk_version = _risk_version(risk_version)
    clean_classifier_risk_weights = _clean_classifier_risk_weights(classifier_risk_weights)
    bpm_risk, bpm_warning = _bpm_risk(_track_bpm(seed_track), _track_bpm(candidate_track))
    key_risk, key_warning = _key_risk(_track_key(seed_track), _track_key(candidate_track))
    energy_risk, energy_warning = _energy_jump_risk(_track_energy(seed_track), _track_energy(candidate_track))
    source_risk, source_warning = _source_disagreement_risk(source_count, max_source_count)
    v1_components = {
        "bpm_risk": bpm_risk,
        "key_risk": key_risk,
        "energy_jump_risk": energy_risk,
        "source_disagreement_risk": source_risk,
    }
    v1_warnings = [
        warning
        for warning in (bpm_warning, key_warning, energy_warning, source_warning)
        if warning is not None
    ]
    transition_risk_v1 = _mean_available(v1_components[name] for name in V1_COMPONENT_NAMES)
    if clean_risk_version == TRANSITION_RISK_V1:
        return TransitionDiagnostics(
            transition_risk=transition_risk_v1,
            components=v1_components,
            warnings=v1_warnings,
            available_components=[name for name in V1_COMPONENT_NAMES if v1_components[name] is not None],
            risk_version=TRANSITION_RISK_V1,
            transition_risk_v1=transition_risk_v1,
            components_v1=dict(v1_components),
        )

    density_risk, density_warning = _feature_group_risk(seed_track, candidate_track, DENSITY_FEATURE_FIELDS, "missing_density_features")
    texture_risk, texture_warning = _feature_group_risk(seed_track, candidate_track, TEXTURE_FEATURE_FIELDS, "missing_texture_features")
    mood_risk, mood_warning = _feature_group_risk(seed_track, candidate_track, MOOD_FEATURE_FIELDS, "missing_mood_features")
    vocal_risk, vocal_warning = _vocal_conflict_risk(
        seed_track,
        candidate_track,
        classifier_risk_weights=clean_classifier_risk_weights,
    )
    components = {
        **v1_components,
        "density_jump_risk": density_risk,
        "texture_clash_risk": texture_risk,
        "mood_clash_risk": mood_risk,
        "vocal_conflict_risk": vocal_risk,
    }
    missingness_risk, missingness_warning = _confidence_missingness_risk(components)
    components["confidence_missingness_risk"] = missingness_risk
    warnings = [
        warning
        for warning in (
            *v1_warnings,
            density_warning,
            texture_warning,
            mood_warning,
            vocal_warning,
            missingness_warning,
        )
        if warning is not None
    ]
    return TransitionDiagnostics(
        transition_risk=_weighted_mean_available(components, V2_COMPONENT_WEIGHTS),
        components=components,
        warnings=warnings,
        available_components=[name for name in COMPONENT_NAMES if components[name] is not None],
        risk_version=TRANSITION_RISK_V2,
        transition_risk_v1=transition_risk_v1,
        components_v1=dict(v1_components),
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
    _relation, compatibility_score = camelot_compatibility(candidate_key, seed_key)
    return _clamp(1.0 - compatibility_score), None


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


def _feature_group_risk(
    seed_track: Mapping[str, Any] | Track,
    candidate_track: Mapping[str, Any] | Track,
    fields: Sequence[str],
    missing_warning: str,
) -> tuple[float | None, str | None]:
    seed_features = _track_sonara_features(seed_track)
    candidate_features = _track_sonara_features(candidate_track)
    if seed_features is None and candidate_features is None:
        return None, None
    if seed_features is None or candidate_features is None:
        return None, missing_warning
    similarities = [
        similarity
        for field in fields
        if (similarity := _feature_similarity(seed_features, candidate_features, field)) is not None
    ]
    if not similarities:
        return None, missing_warning
    return _clamp(1.0 - _mean(similarities)), None


def _feature_similarity(seed_features: Mapping[str, Any], candidate_features: Mapping[str, Any], field: str) -> float | None:
    seed_values = _numeric_values(seed_features.get(field))
    candidate_values = _numeric_values(candidate_features.get(field))
    if not seed_values or not candidate_values:
        return None
    pair_count = min(len(seed_values), len(candidate_values))
    return _mean(
        _numeric_similarity(seed_values[index], candidate_values[index])
        for index in range(pair_count)
    )


def _numeric_values(value: object) -> tuple[float, ...]:
    unwrapped = unwrap_feature_value(value)
    if isinstance(unwrapped, Mapping):
        summary = unwrapped.get("summary")
        if not isinstance(summary, Mapping):
            return ()
        return tuple(
            number
            for key in ("mean", "std", "min", "max")
            if (number := optional_float(summary.get(key))) is not None
        )
    if isinstance(unwrapped, (list, tuple)):
        return tuple(number for item in unwrapped if (number := optional_float(item)) is not None)
    number = optional_float(unwrapped)
    return (number,) if number is not None else ()


def _numeric_similarity(seed_value: float, candidate_value: float) -> float:
    scale = max(abs(seed_value), abs(candidate_value), 1.0)
    return _clamp(1.0 - abs(candidate_value - seed_value) / scale)


def _vocal_conflict_risk(
    seed_track: Mapping[str, Any] | Track,
    candidate_track: Mapping[str, Any] | Track,
    *,
    classifier_risk_weights: Mapping[str, float],
) -> tuple[float | None, str | None]:
    seed_scores = _classifier_scores(seed_track, VOCAL_CLASSIFIER_KEYWORDS)
    candidate_scores = _classifier_scores(candidate_track, VOCAL_CLASSIFIER_KEYWORDS)
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


def _confidence_missingness_risk(components: Mapping[str, float | None]) -> tuple[float | None, str | None]:
    present_optional = [name for name in MISSINGNESS_COMPONENT_NAMES if components.get(name) is not None]
    if not present_optional:
        return None, None
    missing_count = len(MISSINGNESS_COMPONENT_NAMES) - len(present_optional)
    if missing_count <= 0:
        return 0.0, None
    return _clamp((missing_count / len(MISSINGNESS_COMPONENT_NAMES)) * 0.35), "partial_risk_feature_coverage"


def _track_bpm(track: Mapping[str, Any] | Track) -> float | None:
    return resolve_track_bpm(track)


def _track_key(track: Mapping[str, Any] | Track) -> str | None:
    return resolve_track_key(track)


def _track_energy(track: Mapping[str, Any] | Track) -> float | None:
    return optional_float(_first_present(_track_value(track, "energy"), _track_metadata(track).get("energy")))


def _track_sonara_features(track: Mapping[str, Any] | Track) -> Mapping[str, Any] | None:
    features = _track_metadata(track).get("sonara_features")
    return features if isinstance(features, Mapping) else None


def _classifier_scores(track: Mapping[str, Any] | Track, keywords: Sequence[str]) -> dict[str, float]:
    raw_scores = _track_classifier_scores(track)
    result: dict[str, float] = {}
    for key, payload in raw_scores.items():
        classifier_key = str(key)
        if not _contains_keyword(classifier_key, keywords):
            continue
        score = optional_float(payload.get("score") if isinstance(payload, Mapping) else None)
        if score is not None:
            result[classifier_key] = _clamp(score)
    return result


def _track_classifier_scores(track: Mapping[str, Any] | Track) -> Mapping[str, Any]:
    if isinstance(track, Mapping):
        scores = track.get("classifier_scores")
    else:
        scores = track.classifier_scores
    return scores if isinstance(scores, Mapping) else {}


def _contains_keyword(value: object, keywords: Sequence[str]) -> bool:
    text = str(value).casefold()
    return any(keyword in text for keyword in keywords)


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


def _risk_version(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in TRANSITION_RISK_VERSIONS:
        return text
    raise ValueError(f"transition_risk_version must be one of: {', '.join(TRANSITION_RISK_VERSIONS)}")


def _clean_classifier_risk_weights(values: Mapping[str, float] | None) -> dict[str, float]:
    if not values:
        return {}
    clean_values: dict[str, float] = {}
    for key, value in values.items():
        classifier_key = str(key).strip()
        if not classifier_key:
            continue
        clean_values[classifier_key] = _unit_interval(value, f"classifier_risk_weights.{classifier_key}")
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


def _weighted_mean_available(values: Mapping[str, float | None], weights: Mapping[str, float]) -> float | None:
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
