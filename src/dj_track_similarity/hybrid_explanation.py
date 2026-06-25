from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Any

from .models import Track
from .sonara_similarity_scoring import optional_float, tempo_score, unwrap_feature_value


MATCH_CHARACTER_AXES = (
    "groove",
    "density",
    "texture",
    "mood",
    "tonal",
    "vocalness",
    "energy_flow",
    "novelty",
)
RISK_BREAKDOWN_COMPONENTS = {
    "bpm_risk": "bpm",
    "key_risk": "tonal",
    "energy_jump_risk": "energy_jump",
    "source_disagreement_risk": "source_disagreement",
}
EMBEDDING_SOURCES = {"mert", "maest", "clap"}
SONARA_GROOVE_FIELDS = ("bpm", "onset_density", "danceability")
SONARA_DENSITY_FIELDS = ("onset_density", "rms_mean", "loudness_lufs", "dynamic_range_db")
SONARA_TEXTURE_FIELDS = (
    "mfcc_mean",
    "spectral_centroid_mean",
    "spectral_bandwidth_mean",
    "spectral_rolloff_mean",
    "spectral_flatness_mean",
    "spectral_contrast_mean",
)
SONARA_MOOD_FIELDS = ("energy", "valence", "acousticness")
SONARA_TONAL_FIELDS = ("key_confidence", "chroma_mean", "dissonance")
VOCAL_CLASSIFIER_KEYWORDS = ("voice", "vocal")
TEXTURE_CLASSIFIER_KEYWORDS = ("live", "instrument")


@dataclass(frozen=True)
class HybridExplanation:
    total_score: float
    calibrated_score: None
    score_breakdown: Mapping[str, Mapping[str, float | int]]
    risk_breakdown: Mapping[str, float | None]
    source_support: Mapping[str, Mapping[str, Any]]
    match_character: Mapping[str, float]
    warnings: tuple[str, ...]
    explanation: tuple[str, ...]


def build_hybrid_explanation(
    *,
    candidate_track: Track,
    seed_tracks: Sequence[Track],
    source_contributions: Mapping[str, Any],
    source_seed_diagnostics: Mapping[str, Mapping[str, Any]],
    score_breakdown: Mapping[str, Mapping[str, float | int]],
    transition_diagnostics: Mapping[str, Any],
    sources: Sequence[str],
    total_score: float,
) -> HybridExplanation:
    clean_total_score = _finite_float(total_score, "total_score")
    clean_score_breakdown = _clean_score_breakdown(score_breakdown)
    risk_breakdown = _risk_breakdown(transition_diagnostics)
    source_support = _source_support(
        sources,
        source_contributions=source_contributions,
        source_seed_diagnostics=source_seed_diagnostics,
        score_breakdown=clean_score_breakdown,
    )
    match_character = _match_character(
        candidate_track=candidate_track,
        seed_tracks=seed_tracks,
        source_support=source_support,
        risk_breakdown=risk_breakdown,
    )
    warnings = _warnings(
        match_character=match_character,
        risk_breakdown=risk_breakdown,
        source_support=source_support,
        transition_diagnostics=transition_diagnostics,
    )
    explanation = _explanation_lines(match_character=match_character, source_support=source_support, risk_breakdown=risk_breakdown)
    return HybridExplanation(
        total_score=clean_total_score,
        calibrated_score=None,
        score_breakdown=clean_score_breakdown,
        risk_breakdown=risk_breakdown,
        source_support=source_support,
        match_character=match_character,
        warnings=warnings,
        explanation=explanation,
    )


def _clean_score_breakdown(score_breakdown: Mapping[str, Mapping[str, float | int]]) -> dict[str, dict[str, float | int]]:
    return {
        str(source): {
            str(name): _finite_number(value, f"score_breakdown.{source}.{name}")
            for name, value in details.items()
        }
        for source, details in sorted(score_breakdown.items())
    }


def _source_support(
    sources: Sequence[str],
    *,
    source_contributions: Mapping[str, Any],
    source_seed_diagnostics: Mapping[str, Mapping[str, Any]],
    score_breakdown: Mapping[str, Mapping[str, float | int]],
) -> dict[str, dict[str, Any]]:
    support: dict[str, dict[str, Any]] = {}
    for source in sources:
        source_name = str(source)
        details = score_breakdown.get(source_name, {})
        diagnostics = source_seed_diagnostics.get(source_name, {})
        contribution = source_contributions.get(source_name)
        support[source_name] = {
            "available": contribution is not None,
            "rank": _optional_int(details.get("rank")),
            "score": _optional_finite_float(details.get("score")),
            "weight": _optional_finite_float(details.get("weight")),
            "contribution": _optional_finite_float(details.get("contribution")),
            "best_seed_track_id": _optional_int(diagnostics.get("best_seed_track_id")),
            "best_rank": _optional_int(diagnostics.get("best_rank")),
            "supporting_seed_track_ids": _int_list(diagnostics.get("supporting_seed_track_ids")),
        }
    return support


def _risk_breakdown(transition_diagnostics: Mapping[str, Any]) -> dict[str, float | None]:
    components = transition_diagnostics.get("components")
    if not isinstance(components, Mapping):
        return {name: None for name in RISK_BREAKDOWN_COMPONENTS.values()}
    return {
        stable_name: _optional_unit_interval(components.get(component_name))
        for component_name, stable_name in RISK_BREAKDOWN_COMPONENTS.items()
    }


def _match_character(
    *,
    candidate_track: Track,
    seed_tracks: Sequence[Track],
    source_support: Mapping[str, Mapping[str, Any]],
    risk_breakdown: Mapping[str, float | None],
) -> dict[str, float]:
    source_scores = {source: _source_quality(source, support) for source, support in source_support.items()}
    values = {
        "groove": _axis_score(
            source_scores.get("mert"),
            source_scores.get("sonara"),
            _sonara_similarity(seed_tracks, candidate_track, SONARA_GROOVE_FIELDS),
        ),
        "density": _axis_score(
            source_scores.get("sonara"),
            _sonara_similarity(seed_tracks, candidate_track, SONARA_DENSITY_FIELDS),
            _risk_to_match(risk_breakdown.get("energy_jump")),
        ),
        "texture": _axis_score(
            source_scores.get("mert"),
            source_scores.get("maest"),
            _sonara_similarity(seed_tracks, candidate_track, SONARA_TEXTURE_FIELDS),
            _classifier_similarity(seed_tracks, candidate_track, TEXTURE_CLASSIFIER_KEYWORDS),
        ),
        "mood": _axis_score(
            source_scores.get("clap"),
            source_scores.get("maest"),
            _sonara_similarity(seed_tracks, candidate_track, SONARA_MOOD_FIELDS),
        ),
        "tonal": _axis_score(
            source_scores.get("sonara"),
            _risk_to_match(risk_breakdown.get("tonal")),
            _sonara_similarity(seed_tracks, candidate_track, SONARA_TONAL_FIELDS),
        ),
        "vocalness": _axis_score(
            _classifier_similarity(seed_tracks, candidate_track, VOCAL_CLASSIFIER_KEYWORDS),
        ),
        "energy_flow": _axis_score(
            _risk_to_match(risk_breakdown.get("energy_jump")),
            _track_energy_similarity(seed_tracks, candidate_track),
            _sonara_similarity(seed_tracks, candidate_track, ("energy",)),
        ),
        "novelty": _axis_score(_novelty_score(source_support)),
    }
    return {axis: values[axis] for axis in MATCH_CHARACTER_AXES}


def _source_quality(source: str, support: Mapping[str, Any]) -> float | None:
    if support.get("available") is not True:
        return None
    source_score = _optional_finite_float(support.get("score"))
    rank_quality = _rank_quality(_optional_int(support.get("rank")))
    score_quality = _score_quality(source, source_score)
    return _mean_unit_values(score_quality, rank_quality)


def _score_quality(source: str, score: float | None) -> float | None:
    if score is None:
        return None
    if source in EMBEDDING_SOURCES:
        return _clamp01((score + 1.0) / 2.0)
    return _clamp01(score)


def _rank_quality(rank: int | None) -> float | None:
    if rank is None or rank <= 0:
        return None
    return _clamp01(1.0 / (1.0 + (rank - 1) / 10.0))


def _risk_to_match(risk: float | None) -> float | None:
    if risk is None:
        return None
    return _clamp01(1.0 - risk)


def _sonara_similarity(seed_tracks: Sequence[Track], candidate_track: Track, fields: Sequence[str]) -> float | None:
    candidate_features = _sonara_features(candidate_track)
    if candidate_features is None:
        return None
    seed_features = [_sonara_features(track) for track in seed_tracks]
    seed_features = [features for features in seed_features if features is not None]
    if not seed_features:
        return None
    similarities = [
        similarity
        for seed_feature in seed_features
        for field in fields
        if (similarity := _feature_similarity(seed_feature, candidate_features, field)) is not None
    ]
    return _mean_unit_values(*similarities)


def _sonara_features(track: Track) -> Mapping[str, Any] | None:
    metadata = track.metadata or {}
    features = metadata.get("sonara_features")
    return features if isinstance(features, Mapping) else None


def _feature_similarity(seed_features: Mapping[str, Any], candidate_features: Mapping[str, Any], field: str) -> float | None:
    seed_value = unwrap_feature_value(seed_features.get(field))
    candidate_value = unwrap_feature_value(candidate_features.get(field))
    if field == "bpm":
        seed_bpm = optional_float(seed_value)
        candidate_bpm = optional_float(candidate_value)
        if seed_bpm is None or candidate_bpm is None:
            return None
        return _clamp01(tempo_score(candidate_bpm, seed_bpm))
    seed_values = _numeric_values(seed_value)
    candidate_values = _numeric_values(candidate_value)
    if not seed_values or not candidate_values:
        return None
    pair_count = min(len(seed_values), len(candidate_values))
    pair_similarities = [
        _numeric_similarity(seed_values[index], candidate_values[index])
        for index in range(pair_count)
    ]
    return _mean_unit_values(*pair_similarities)


def _numeric_values(value: object) -> tuple[float, ...]:
    value = unwrap_feature_value(value)
    if isinstance(value, Mapping):
        summary = value.get("summary")
        if isinstance(summary, Mapping):
            return tuple(
                number
                for key in ("mean", "std", "min", "max")
                if (number := optional_float(summary.get(key))) is not None
            )
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(number for item in value if (number := optional_float(item)) is not None)
    number = optional_float(value)
    return (number,) if number is not None else ()


def _numeric_similarity(seed_value: float, candidate_value: float) -> float:
    scale = max(abs(seed_value), abs(candidate_value), 1.0)
    return _clamp01(1.0 - abs(candidate_value - seed_value) / scale)


def _classifier_similarity(seed_tracks: Sequence[Track], candidate_track: Track, keywords: Sequence[str]) -> float | None:
    candidate_scores = _classifier_scores(candidate_track, keywords)
    if not candidate_scores:
        return None
    seed_scores = [_classifier_scores(track, keywords) for track in seed_tracks]
    similarities: list[float] = []
    for classifier_key, candidate_score in candidate_scores.items():
        comparable_seed_scores = [scores[classifier_key] for scores in seed_scores if classifier_key in scores]
        if not comparable_seed_scores:
            continue
        seed_score = sum(comparable_seed_scores) / len(comparable_seed_scores)
        similarities.append(_clamp01(1.0 - abs(candidate_score - seed_score)))
    return _mean_unit_values(*similarities)


def _classifier_scores(track: Track, keywords: Sequence[str]) -> dict[str, float]:
    scores = track.classifier_scores or {}
    result: dict[str, float] = {}
    for classifier_key, payload in scores.items():
        if not _contains_keyword(classifier_key, keywords):
            continue
        score = optional_float(payload.get("score") if isinstance(payload, Mapping) else None)
        if score is not None:
            result[str(classifier_key)] = _clamp01(score)
    return result


def _contains_keyword(value: object, keywords: Sequence[str]) -> bool:
    text = str(value).casefold()
    return any(keyword in text for keyword in keywords)


def _track_energy_similarity(seed_tracks: Sequence[Track], candidate_track: Track) -> float | None:
    candidate_energy = optional_float(candidate_track.energy)
    if candidate_energy is None:
        return None
    seed_energies = [energy for track in seed_tracks if (energy := optional_float(track.energy)) is not None]
    if not seed_energies:
        return None
    seed_energy = sum(seed_energies) / len(seed_energies)
    return _clamp01(1.0 - abs(candidate_energy - seed_energy))


def _novelty_score(source_support: Mapping[str, Mapping[str, Any]]) -> float | None:
    available_support = [support for support in source_support.values() if support.get("available") is True]
    if not available_support:
        return None
    ranks = [_optional_int(support.get("rank")) for support in available_support]
    rank_novelty = _mean_unit_values(*(_rank_novelty(rank) for rank in ranks if rank is not None))
    multi_source_bonus = _clamp01((len(available_support) - 1) / 3.0)
    if rank_novelty is None:
        return 0.5 + 0.15 * multi_source_bonus
    return _clamp01(0.5 + 0.35 * rank_novelty + 0.15 * multi_source_bonus)


def _rank_novelty(rank: int) -> float:
    if rank <= 1:
        return 0.0
    return _clamp01((rank - 1) / 9.0)


def _axis_score(*values: float | None) -> float:
    score = _mean_unit_values(*values)
    if score is None:
        return 0.5
    return score


def _warnings(
    *,
    match_character: Mapping[str, float],
    risk_breakdown: Mapping[str, float | None],
    source_support: Mapping[str, Mapping[str, Any]],
    transition_diagnostics: Mapping[str, Any],
) -> tuple[str, ...]:
    warning_items: list[tuple[int, str]] = []
    warning_items.extend(_risk_warning_items(risk_breakdown))
    warning_items.extend(_axis_warning_items(match_character))
    warning_items.extend(_source_warning_items(source_support))
    warning_items.extend(_transition_warning_items(transition_diagnostics))
    deduped = {text: severity for severity, text in warning_items}
    return tuple(text for text, _severity in sorted(deduped.items(), key=lambda item: (item[1], item[0])))


def _risk_warning_items(risk_breakdown: Mapping[str, float | None]) -> list[tuple[int, str]]:
    labels = {
        "bpm": "BPM",
        "tonal": "tonal",
        "energy_jump": "energy jump",
        "source_disagreement": "source disagreement",
    }
    warning_items: list[tuple[int, str]] = []
    for name, label in labels.items():
        risk = risk_breakdown.get(name)
        if risk is None:
            continue
        if risk >= 0.75:
            warning_items.append((0, f"Risk estimate: {label} risk is elevated."))
        elif risk >= 0.45:
            warning_items.append((1, f"Risk estimate: {label} needs a listening check."))
    return warning_items


def _axis_warning_items(match_character: Mapping[str, float]) -> list[tuple[int, str]]:
    warning_items: list[tuple[int, str]] = []
    if match_character["tonal"] <= 0.35:
        warning_items.append((1, "Reason signals: tonal match is weak."))
    if match_character["energy_flow"] <= 0.35:
        warning_items.append((1, "Reason signals: energy flow is uneven."))
    if match_character["density"] <= 0.35:
        warning_items.append((2, "Reason signals: density match is limited."))
    return warning_items


def _source_warning_items(source_support: Mapping[str, Mapping[str, Any]]) -> list[tuple[int, str]]:
    available_sources = [source for source, support in source_support.items() if support.get("available") is True]
    if len(available_sources) <= 1:
        return [(2, "Reason signals: source support is narrow.")]
    return []


def _transition_warning_items(transition_diagnostics: Mapping[str, Any]) -> list[tuple[int, str]]:
    raw_warnings = transition_diagnostics.get("warnings")
    if not isinstance(raw_warnings, list):
        return []
    missing_components = sorted(_missing_component_name(warning) for warning in raw_warnings if str(warning).startswith("missing_"))
    warning_items: list[tuple[int, str]] = []
    if missing_components:
        warning_items.append((3, f"Unsupervised diagnostic: unavailable {', '.join(missing_components)} data kept neutral."))
    for warning in raw_warnings:
        warning_text = str(warning)
        if warning_text.startswith("missing_"):
            continue
        warning_items.append((2, f"Unsupervised diagnostic: {warning_text.replace('_', ' ')}."))
    return warning_items


def _missing_component_name(warning: object) -> str:
    return str(warning).removeprefix("missing_").replace("_", " ")


def _explanation_lines(
    *,
    match_character: Mapping[str, float],
    source_support: Mapping[str, Mapping[str, Any]],
    risk_breakdown: Mapping[str, float | None],
) -> tuple[str, ...]:
    strongest_axes = _strongest_axes(match_character)
    lines = [
        f"Strongest match axes: {', '.join(_axis_label(axis) for axis in strongest_axes)}.",
        f"Reason signals: {_source_support_phrase(source_support)}.",
        f"Risk estimate: {_risk_phrase(risk_breakdown)}.",
    ]
    return tuple(lines)


def _strongest_axes(match_character: Mapping[str, float]) -> tuple[str, ...]:
    return tuple(
        axis
        for axis, _value in sorted(match_character.items(), key=lambda item: (-item[1], item[0]))[:3]
    )


def _source_support_phrase(source_support: Mapping[str, Mapping[str, Any]]) -> str:
    available_sources = [source.upper() for source, support in source_support.items() if support.get("available") is True]
    if not available_sources:
        return "no source returned a supported row"
    return f"{', '.join(available_sources)} support this row"


def _risk_phrase(risk_breakdown: Mapping[str, float | None]) -> str:
    available_risks = {name: risk for name, risk in risk_breakdown.items() if risk is not None}
    if not available_risks:
        return "risk data unavailable, neutral values used"
    highest_name, highest_risk = max(available_risks.items(), key=lambda item: (item[1], item[0]))
    return f"highest component is {highest_name.replace('_', ' ')} at {highest_risk:.2f}"


def _axis_label(axis: str) -> str:
    return axis.replace("_", " ")


def _mean_unit_values(*values: float | None) -> float | None:
    numbers = [_clamp01(value) for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def _optional_unit_interval(value: object) -> float | None:
    number = _optional_finite_float(value)
    if number is None:
        return None
    return _clamp01(number)


def _optional_finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _finite_float(value: object, field_name: str) -> float:
    number = _optional_finite_float(value)
    if number is None:
        raise ValueError(f"{field_name} must be finite")
    return number


def _finite_number(value: object, field_name: str) -> float | int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return _finite_float(value, field_name)


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _int_list(value: object) -> list[int]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        return []
    return sorted({number for item in value if (number := _optional_int(item)) is not None})


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.5
    return min(1.0, max(0.0, float(value)))
