from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from math import inf
from pathlib import Path
from typing import Any

import numpy as np

from .database import LibraryDatabase
from .metadata_payload import optional_float, string_or_none
from .models import Track
from .sonara_similarity_scoring import unwrap_feature_value


SET_BUILDER_MODES = {"similar_crate", "weird_adjacent", "balanced_set", "discovery"}
SET_BUILDER_SEED_MODES = {"manual", "auto"}
SET_BUILDER_ENERGY_CURVES = {"warmup", "balanced", "peak", "wave"}
REQUIRED_EMBEDDINGS = ("mert", "maest", "clap")
DEFAULT_MODEL_WEIGHTS = {
    "mert": 0.30,
    "clap": 0.22,
    "maest": 0.18,
    "sonara_broad": 0.30,
}
SONARA_GROUP_WEIGHTS = {
    "rhythm": 1.0,
    "dynamics": 1.1,
    "perception": 1.0,
    "tonal": 0.8,
    "timbre": 1.2,
}
SONARA_NUMERIC_FIELDS: dict[str, tuple[str, float]] = {
    "bpm": ("rhythm", 1.2),
    "n_beats": ("rhythm", 0.4),
    "onset_density": ("rhythm", 1.0),
    "beats.summary.mean": ("rhythm", 0.25),
    "beats.summary.std": ("rhythm", 0.25),
    "onset_frames.summary.mean": ("rhythm", 0.25),
    "onset_frames.summary.std": ("rhythm", 0.25),
    "rms_mean": ("dynamics", 0.8),
    "rms_max": ("dynamics", 0.5),
    "loudness_lufs": ("dynamics", 0.8),
    "dynamic_range_db": ("dynamics", 0.7),
    "energy": ("dynamics", 1.1),
    "danceability": ("perception", 1.0),
    "valence": ("perception", 0.7),
    "acousticness": ("perception", 0.7),
    "key_confidence": ("tonal", 0.5),
    "chord_change_rate": ("tonal", 0.8),
    "dissonance": ("tonal", 0.8),
    "spectral_centroid_mean": ("timbre", 0.8),
    "spectral_bandwidth_mean": ("timbre", 0.7),
    "spectral_rolloff_mean": ("timbre", 0.7),
    "spectral_flatness_mean": ("timbre", 0.7),
    "spectral_contrast_mean": ("timbre", 0.7),
    "zero_crossing_rate": ("timbre", 0.5),
    "mfcc_mean.summary.min": ("timbre", 0.45),
    "mfcc_mean.summary.max": ("timbre", 0.45),
    "mfcc_mean.summary.mean": ("timbre", 0.9),
    "mfcc_mean.summary.std": ("timbre", 0.65),
    "chroma_mean.summary.min": ("tonal", 0.35),
    "chroma_mean.summary.max": ("tonal", 0.35),
    "chroma_mean.summary.mean": ("tonal", 0.7),
    "chroma_mean.summary.std": ("tonal", 0.55),
}


@dataclass(frozen=True)
class SetBuilderConfig:
    seed_mode: str = "manual"
    seed_track_ids: list[int] = field(default_factory=list)
    auto_seed_count: int = 5
    mode: str = "balanced_set"
    limit: int = 24
    diversity: float = 0.35
    energy_curve: str = "balanced"
    classifier_targets: dict[str, float] = field(default_factory=dict)
    classifier_avoid: dict[str, float] = field(default_factory=dict)
    classifier_curves: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class _Candidate:
    track: Track
    vectors: dict[str, np.ndarray]
    sonara_features: dict[str, object]
    sonara_values: dict[str, float]
    text_values: dict[str, str]
    duplicate_key: str


@dataclass(frozen=True)
class _ScoredCandidate:
    candidate: _Candidate
    base_score: float
    breakdown: dict[str, float]
    sonara_groups: dict[str, float]
    model_scores: dict[str, float]


class SmartSetBuilder:
    def __init__(self, db: LibraryDatabase) -> None:
        self.db = db

    def generate(self, config: SetBuilderConfig) -> dict[str, object]:
        cleaned = _clean_config(config)
        manual_seed_ids = _manual_seed_ids(cleaned.seed_track_ids) if cleaned.seed_mode == "manual" else []
        candidates, coverage = self._load_candidates()

        candidate_by_id = {candidate.track.id: candidate for candidate in candidates}
        if cleaned.seed_mode == "manual":
            seed_ids = manual_seed_ids
            self._validate_manual_seeds(seed_ids, candidate_by_id)
        else:
            if not candidates:
                raise ValueError("No feature-complete tracks are available for Smart Set Builder")
            seed_ids = self._auto_seed_ids(candidates, cleaned.auto_seed_count)
        seeds = [candidate_by_id[track_id] for track_id in seed_ids]

        ranges = _numeric_ranges(candidates)
        context = _Context(seeds=seeds, ranges=ranges)
        scored = [
            self._score_candidate(candidate, context, cleaned)
            for candidate in candidates
            if candidate.track.id not in seed_ids
        ]
        scored = [item for item in scored if item is not None]
        ordered_items = self._ordered_items(seeds, scored, cleaned, ranges)

        return {
            "mode": cleaned.mode,
            "seed_mode": cleaned.seed_mode,
            "seed_track_ids": seed_ids,
            "coverage": coverage,
            "items": ordered_items[: cleaned.limit],
        }

    def _load_candidates(self) -> tuple[list[_Candidate], dict[str, int]]:
        all_tracks = self.db.list_tracks(include_metadata=False)
        all_track_ids = {track.id for track in all_tracks}
        embedding_maps: dict[str, dict[int, np.ndarray]] = {}
        for key in REQUIRED_EMBEDDINGS:
            tracks, matrix = self.db.load_embedding_matrix(key)
            embedding_maps[key] = {track.id: matrix[index].astype(np.float32, copy=False) for index, track in enumerate(tracks)}

        sonara_tracks, sonara_rows = self.db.load_sonara_feature_rows()
        sonara_by_id = {track.id: (track, features) for track, features in zip(sonara_tracks, sonara_rows)}

        eligible_ids = set(sonara_by_id)
        for key in REQUIRED_EMBEDDINGS:
            eligible_ids &= set(embedding_maps[key])

        candidates: list[_Candidate] = []
        for track_id in sorted(eligible_ids):
            track, features = sonara_by_id[track_id]
            values, text_values = _sonara_values(features)
            candidates.append(
                _Candidate(
                    track=track,
                    vectors={key: embedding_maps[key][track_id] for key in REQUIRED_EMBEDDINGS},
                    sonara_features=features,
                    sonara_values=values,
                    text_values=text_values,
                    duplicate_key=_duplicate_key(track),
                )
            )

        coverage = {
            "tracks": len(all_track_ids),
            "eligible_tracks": len(candidates),
            "missing_mert": len(all_track_ids - set(embedding_maps["mert"])),
            "missing_maest": len(all_track_ids - set(embedding_maps["maest"])),
            "missing_clap": len(all_track_ids - set(embedding_maps["clap"])),
            "missing_sonara": len(all_track_ids - set(sonara_by_id)),
        }
        return candidates, coverage

    def _validate_manual_seeds(self, seed_ids: list[int], candidate_by_id: dict[int, _Candidate]) -> None:
        missing = [track_id for track_id in seed_ids if track_id not in candidate_by_id]
        if not missing:
            return
        unknown: list[int] = []
        missing_analysis: list[int] = []
        for track_id in missing:
            try:
                self.db.get_track(track_id)
            except KeyError:
                unknown.append(track_id)
            else:
                missing_analysis.append(track_id)
        if unknown:
            raise ValueError(f"Unknown seed tracks: {unknown}")
        raise ValueError(f"Seed tracks missing required analysis: {missing_analysis}")

    def _auto_seed_ids(self, candidates: list[_Candidate], requested_count: int) -> list[int]:
        count = max(3, min(5, int(requested_count)))
        if len(candidates) < count:
            raise ValueError(f"Auto seed mode requires at least {count} feature-complete tracks")
        ranges = _numeric_ranges(candidates)
        global_context = _Context(seeds=candidates, ranges=ranges)
        centrality = [
            (candidate, _sonara_similarity(candidate, global_context)[0])
            for candidate in candidates
        ]
        centrality.sort(key=lambda item: (-item[1], item[0].track.artist or "", item[0].track.title or "", item[0].track.path))
        seeds: list[_Candidate] = []
        seen_keys: set[str] = set()
        for candidate, _score in centrality:
            if candidate.duplicate_key in seen_keys:
                continue
            if seeds and max(_combined_similarity(candidate, seed, ranges) for seed in seeds) > 0.995:
                continue
            seeds.append(candidate)
            seen_keys.add(candidate.duplicate_key)
            if len(seeds) >= count:
                break
        if len(seeds) < count:
            for candidate, _score in centrality:
                if candidate in seeds:
                    continue
                seeds.append(candidate)
                if len(seeds) >= count:
                    break
        return [candidate.track.id for candidate in seeds]

    def _score_candidate(
        self,
        candidate: _Candidate,
        context: "_Context",
        config: SetBuilderConfig,
    ) -> _ScoredCandidate | None:
        model_scores = {
            "mert": _embedding_similarity(candidate, context, "mert"),
            "maest_embedding": _embedding_similarity(candidate, context, "maest"),
            "clap_audio": _embedding_similarity(candidate, context, "clap"),
        }
        sonara_score, sonara_groups = _sonara_similarity(candidate, context)
        if sonara_score is None:
            return None
        classifier_target, classifier_avoid, classifier_confidence = _classifier_modifiers(candidate.track, config)
        base = (
            model_scores["mert"] * DEFAULT_MODEL_WEIGHTS["mert"]
            + model_scores["clap_audio"] * DEFAULT_MODEL_WEIGHTS["clap"]
            + model_scores["maest_embedding"] * DEFAULT_MODEL_WEIGHTS["maest"]
            + sonara_score * DEFAULT_MODEL_WEIGHTS["sonara_broad"]
        )
        base += classifier_target * 0.08
        base += classifier_avoid * 0.08
        disagreement = float(np.std(list(model_scores.values()) + [sonara_score]))
        if config.mode == "weird_adjacent":
            base = base * 0.88 + min(1.0, disagreement * 3.0) * 0.12
        elif config.mode == "discovery":
            uncertainty = 1.0 - abs(base - 0.5) * 2.0
            base = base * 0.88 + max(0.0, uncertainty) * 0.12
        elif config.mode == "similar_crate":
            base = base * 0.96 + max(0.0, 1.0 - disagreement) * 0.04

        breakdown = {
            **model_scores,
            "sonara_broad": sonara_score,
            "classifier_target": classifier_target,
            "classifier_avoid": classifier_avoid,
            "classifier_confidence": classifier_confidence,
            "model_disagreement": disagreement,
            "consensus": _bounded(base),
        }
        return _ScoredCandidate(
            candidate=candidate,
            base_score=_bounded(base),
            breakdown=breakdown,
            sonara_groups=sonara_groups,
            model_scores=model_scores,
        )

    def _ordered_items(
        self,
        seeds: list[_Candidate],
        scored_candidates: list[_ScoredCandidate],
        config: SetBuilderConfig,
        ranges: dict[str, tuple[float, float]],
    ) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        previous: _Candidate | None = None
        seen_duplicates: set[str] = set()
        for seed in seeds:
            transition = _transition(previous, seed)
            items.append(_item(seed, "seed_anchor", 1.0, _seed_breakdown(transition), {}, transition))
            previous = seed
            seen_duplicates.add(seed.duplicate_key)

        remaining = [item for item in scored_candidates if item.candidate.duplicate_key not in seen_duplicates]
        selected_sequence = list(seeds)
        target_count = max(config.limit, len(seeds) + len(remaining))
        while remaining and len(items) < config.limit:
            position = len(items)
            selected = max(
                remaining,
                key=lambda item: self._sequence_score(item, previous, selected_sequence, position, target_count, config, ranges),
            )
            transition = _transition(previous, selected.candidate)
            curve_score = _classifier_curve_score(selected.candidate.track, config, position, target_count)
            diversity_score = _diversity_score(selected.candidate, selected_sequence, ranges)
            breakdown = dict(selected.breakdown)
            breakdown["transition"] = transition["confidence"]
            breakdown["classifier_curve"] = curve_score
            breakdown["diversity"] = diversity_score
            reason = _reason(selected, config, transition, curve_score)
            final_score = self._sequence_score(selected, previous, selected_sequence, position, target_count, config, ranges)
            items.append(_item(selected.candidate, reason, final_score, breakdown, selected.sonara_groups, transition))
            previous = selected.candidate
            selected_sequence.append(selected.candidate)
            seen_duplicates.add(selected.candidate.duplicate_key)
            remaining = [item for item in remaining if item.candidate.duplicate_key not in seen_duplicates]
        public_items: list[dict[str, object]] = []
        for index, item in enumerate(items, start=1):
            public_item = {key: value for key, value in item.items() if key != "candidate"}
            public_item["position"] = index
            public_items.append(public_item)
        return public_items

    def _sequence_score(
        self,
        item: _ScoredCandidate,
        previous: _Candidate | None,
        selected_sequence: list[_Candidate],
        position: int,
        target_count: int,
        config: SetBuilderConfig,
        ranges: dict[str, tuple[float, float]],
    ) -> float:
        transition_score = _transition(previous, item.candidate)["confidence"]
        curve_score = _energy_curve_score(item.candidate, config.energy_curve, position, target_count)
        classifier_curve = _classifier_curve_score(item.candidate.track, config, position, target_count)
        diversity_score = _diversity_score(item.candidate, selected_sequence, ranges)
        diversity_weight = config.diversity * 0.10
        if config.mode == "balanced_set":
            score = item.base_score * (0.68 - diversity_weight) + transition_score * 0.20 + curve_score * 0.07 + classifier_curve * 0.05 + diversity_score * diversity_weight
        elif config.mode == "weird_adjacent":
            weird = min(1.0, item.breakdown["model_disagreement"] * 3.0)
            score = item.base_score * (0.72 - diversity_weight) + weird * 0.18 + transition_score * 0.06 + classifier_curve * 0.04 + diversity_score * diversity_weight
        elif config.mode == "discovery":
            uncertainty = 1.0 - abs(item.base_score - 0.5) * 2.0
            score = item.base_score * (0.70 - diversity_weight) + max(0.0, uncertainty) * 0.15 + transition_score * 0.08 + classifier_curve * 0.07 + diversity_score * diversity_weight
        else:
            score = item.base_score * (0.88 - diversity_weight) + transition_score * 0.06 + classifier_curve * 0.06 + diversity_score * diversity_weight
        return _bounded(score)


@dataclass(frozen=True)
class _Context:
    seeds: list[_Candidate]
    ranges: dict[str, tuple[float, float]]


def _clean_config(config: SetBuilderConfig) -> SetBuilderConfig:
    seed_mode = config.seed_mode.strip()
    mode = config.mode.strip()
    energy_curve = config.energy_curve.strip()
    if seed_mode not in SET_BUILDER_SEED_MODES:
        raise ValueError(f"Unsupported seed mode: {seed_mode}")
    if mode not in SET_BUILDER_MODES:
        raise ValueError(f"Unsupported set builder mode: {mode}")
    if energy_curve not in SET_BUILDER_ENERGY_CURVES:
        raise ValueError(f"Unsupported energy curve: {energy_curve}")
    return SetBuilderConfig(
        seed_mode=seed_mode,
        seed_track_ids=list(dict.fromkeys(int(track_id) for track_id in config.seed_track_ids)),
        auto_seed_count=max(3, min(5, int(config.auto_seed_count))),
        mode=mode,
        limit=max(1, min(500, int(config.limit))),
        diversity=max(0.0, min(1.0, float(config.diversity))),
        energy_curve=energy_curve,
        classifier_targets=_clean_score_map(config.classifier_targets),
        classifier_avoid=_clean_score_map(config.classifier_avoid),
        classifier_curves=_clean_curves(config.classifier_curves),
    )


def _clean_score_map(values: dict[str, float]) -> dict[str, float]:
    cleaned: dict[str, float] = {}
    for key, value in values.items():
        name = str(key).strip()
        if name:
            cleaned[name] = max(0.0, min(1.0, float(value)))
    return cleaned


def _clean_curves(values: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    cleaned: dict[str, dict[str, float]] = {}
    for key, curve in values.items():
        name = str(key).strip()
        if not name:
            continue
        cleaned[name] = {
            "start": max(0.0, min(1.0, float(curve.get("start", 0.5)))),
            "end": max(0.0, min(1.0, float(curve.get("end", 0.5)))),
        }
    return cleaned


def _manual_seed_ids(seed_track_ids: list[int]) -> list[int]:
    seed_ids = list(dict.fromkeys(seed_track_ids))
    if not 1 <= len(seed_ids) <= 5:
        raise ValueError("Manual set builder requires 1-5 seed tracks")
    return seed_ids


def _numeric_ranges(candidates: list[_Candidate]) -> dict[str, tuple[float, float]]:
    observed: dict[str, list[float]] = {}
    for candidate in candidates:
        for key, value in candidate.sonara_values.items():
            observed.setdefault(key, []).append(value)
    ranges: dict[str, tuple[float, float]] = {}
    for key, values in observed.items():
        if len(values) >= 2:
            ranges[key] = (min(values), max(values))
    return ranges


def _sonara_values(features: dict[str, object]) -> tuple[dict[str, float], dict[str, str]]:
    values: dict[str, float] = {}
    for key in SONARA_NUMERIC_FIELDS:
        number = _feature_number(features, key)
        if number is not None:
            values[key] = number
    text_values: dict[str, str] = {}
    for key in ("predominant_chord",):
        value = string_or_none(unwrap_feature_value(features.get(key)))
        if value:
            text_values[key] = value.casefold()
    return values, text_values


def _feature_number(features: dict[str, object], path: str) -> float | None:
    parts = path.split(".")
    value: object = features.get(parts[0])
    for part in parts[1:]:
        if isinstance(value, dict):
            value = value.get(part)
        else:
            return None
    value = unwrap_feature_value(value)
    return optional_float(value)


def _embedding_similarity(candidate: _Candidate, context: _Context, key: str) -> float:
    centroid = np.mean([seed.vectors[key] for seed in context.seeds], axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm <= 0:
        return 0.0
    centroid = centroid / norm
    return _bounded(float(candidate.vectors[key] @ centroid))


def _sonara_similarity(candidate: _Candidate, context: _Context) -> tuple[float | None, dict[str, float]]:
    seed_centroid = _sonara_centroid(context.seeds, context.ranges)
    group_scores: dict[str, list[tuple[float, float]]] = {group: [] for group in SONARA_GROUP_WEIGHTS}
    for key, value in candidate.sonara_values.items():
        if key not in seed_centroid or key not in context.ranges:
            continue
        normalized = _normalize(value, context.ranges[key])
        if normalized is None:
            continue
        group, weight = SONARA_NUMERIC_FIELDS[key]
        score = max(0.0, 1.0 - abs(normalized - seed_centroid[key]))
        group_scores[group].append((score, weight))

    chord_context = _text_context(context.seeds, "predominant_chord")
    candidate_chord = candidate.text_values.get("predominant_chord")
    if chord_context and candidate_chord:
        group_scores["tonal"].append((1.0 if candidate_chord in chord_context else 0.0, 0.35))

    collapsed: dict[str, float] = {}
    weighted_total = 0.0
    weight_total = 0.0
    for group, values in group_scores.items():
        if not values:
            continue
        group_score = sum(score * weight for score, weight in values) / sum(weight for _score, weight in values)
        collapsed[group] = _bounded(group_score)
        group_weight = SONARA_GROUP_WEIGHTS[group]
        weighted_total += collapsed[group] * group_weight
        weight_total += group_weight
    if weight_total <= 0:
        return None, {}
    return _bounded(weighted_total / weight_total), collapsed


def _sonara_centroid(seeds: list[_Candidate], ranges: dict[str, tuple[float, float]]) -> dict[str, float]:
    centroid: dict[str, float] = {}
    for key in ranges:
        values = [
            normalized
            for seed in seeds
            if key in seed.sonara_values
            if (normalized := _normalize(seed.sonara_values[key], ranges[key])) is not None
        ]
        if values:
            centroid[key] = float(np.mean(values))
    return centroid


def _text_context(seeds: list[_Candidate], key: str) -> set[str]:
    values = [seed.text_values.get(key) for seed in seeds if seed.text_values.get(key)]
    if not values:
        return set()
    counts = Counter(values)
    most_common_count = counts.most_common(1)[0][1]
    return {value for value, count in counts.items() if count == most_common_count}


def _normalize(value: float, value_range: tuple[float, float]) -> float | None:
    lower, upper = value_range
    if upper == lower:
        return 0.5
    normalized = (value - lower) / (upper - lower)
    if not np.isfinite(normalized):
        return None
    return float(normalized)


def _classifier_modifiers(track: Track, config: SetBuilderConfig) -> tuple[float, float, float]:
    scores = _classifier_scores(track)
    used_keys = set(config.classifier_targets) | set(config.classifier_avoid) | set(config.classifier_curves)
    if not used_keys:
        return 0.0, 0.0, 1.0
    present = 0
    target_scores: list[float] = []
    for key, threshold in config.classifier_targets.items():
        score = scores.get(key)
        if score is None:
            continue
        present += 1
        denominator = max(1.0 - threshold, 0.0001)
        target_scores.append(max(0.0, (score - threshold) / denominator))
    avoid_scores: list[float] = []
    for key, threshold in config.classifier_avoid.items():
        score = scores.get(key)
        if score is None:
            continue
        present += 1
        denominator = max(1.0 - threshold, 0.0001)
        avoid_scores.append(-max(0.0, (score - threshold) / denominator))
    target = float(np.mean(target_scores)) if target_scores else 0.0
    avoid = float(np.mean(avoid_scores)) if avoid_scores else 0.0
    confidence = present / len(used_keys) if used_keys else 1.0
    return _bounded(target), -_bounded(abs(avoid)) if avoid < 0 else 0.0, _bounded(confidence)


def _classifier_curve_score(track: Track, config: SetBuilderConfig, position: int, target_count: int) -> float:
    if not config.classifier_curves:
        return 0.5
    scores = _classifier_scores(track)
    progress = 0.0 if target_count <= 1 else position / max(target_count - 1, 1)
    values: list[float] = []
    for key, curve in config.classifier_curves.items():
        actual = scores.get(key)
        if actual is None:
            values.append(0.5)
            continue
        desired = curve["start"] + (curve["end"] - curve["start"]) * progress
        values.append(max(0.0, 1.0 - abs(actual - desired)))
    return _bounded(float(np.mean(values))) if values else 0.5


def _classifier_scores(track: Track) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, payload in (track.classifier_scores or {}).items():
        if isinstance(payload, dict):
            score = optional_float(payload.get("score"))
            if score is not None:
                result[str(key)] = _bounded(score)
    return result


def _energy_curve_score(candidate: _Candidate, curve: str, position: int, target_count: int) -> float:
    energy = _track_energy(candidate)
    if energy is None:
        return 0.5
    progress = 0.0 if target_count <= 1 else position / max(target_count - 1, 1)
    if curve == "warmup":
        desired = 0.25 + progress * 0.55
    elif curve == "peak":
        desired = 0.55 + progress * 0.35
    elif curve == "wave":
        desired = 0.55 + 0.25 * np.sin(progress * np.pi * 2.0)
    else:
        desired = 0.55
    return _bounded(1.0 - abs(energy - desired))


def _track_energy(candidate: _Candidate) -> float | None:
    if candidate.track.energy is not None:
        return _bounded(float(candidate.track.energy))
    value = candidate.sonara_values.get("energy")
    return _bounded(value) if value is not None else None


def _transition(previous: _Candidate | None, candidate: _Candidate) -> dict[str, object]:
    if previous is None:
        return {
            "from_track_id": None,
            "bpm_delta": None,
            "key_relation": "anchor",
            "confidence": 1.0,
        }
    bpm_delta = _tempo_distance(_track_bpm(candidate), _track_bpm(previous))
    bpm_score = 0.55 if bpm_delta is None else max(0.0, 1.0 - bpm_delta / 18.0)
    key_relation, key_score = _key_relation(_track_key(candidate), _track_key(previous))
    confidence = _bounded(bpm_score * 0.6 + key_score * 0.4)
    return {
        "from_track_id": previous.track.id,
        "bpm_delta": bpm_delta,
        "key_relation": key_relation,
        "confidence": confidence,
    }


def _track_bpm(candidate: _Candidate) -> float | None:
    metadata = candidate.track.metadata or {}
    tag_bpm = optional_float(metadata.get("bpm"))
    if tag_bpm is not None:
        return tag_bpm
    if candidate.track.bpm is not None:
        return float(candidate.track.bpm)
    return candidate.sonara_values.get("bpm")


def _track_key(candidate: _Candidate) -> str | None:
    metadata = candidate.track.metadata or {}
    tag_key = string_or_none(metadata.get("key")) or string_or_none(metadata.get("initialkey"))
    if tag_key:
        return tag_key
    if candidate.track.musical_key:
        return candidate.track.musical_key
    value = unwrap_feature_value(candidate.sonara_features.get("key"))
    return string_or_none(value)


def _tempo_distance(candidate_bpm: float | None, previous_bpm: float | None) -> float | None:
    if candidate_bpm is None or previous_bpm is None:
        return None
    candidate_variants = [candidate_bpm / 2, candidate_bpm, candidate_bpm * 2]
    previous_variants = [previous_bpm / 2, previous_bpm, previous_bpm * 2]
    return min(abs(candidate - previous) for candidate in candidate_variants for previous in previous_variants)


def _key_relation(candidate_key: str | None, previous_key: str | None) -> tuple[str, float]:
    if not candidate_key or not previous_key:
        return "unknown", 0.55
    candidate = _parse_camelot(candidate_key)
    previous = _parse_camelot(previous_key)
    if candidate is None or previous is None:
        return ("same", 1.0) if candidate_key.strip().casefold() == previous_key.strip().casefold() else ("unknown", 0.55)
    candidate_number, candidate_letter = candidate
    previous_number, previous_letter = previous
    if candidate_number == previous_number and candidate_letter == previous_letter:
        return "same", 1.0
    if candidate_number == previous_number and candidate_letter != previous_letter:
        return "relative", 0.9
    if candidate_letter == previous_letter and candidate_number in {_wrap_camelot(previous_number - 1), _wrap_camelot(previous_number + 1)}:
        return "adjacent", 0.95
    return "clash", 0.2


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


def _combined_similarity(candidate: _Candidate, seed: _Candidate, ranges: dict[str, tuple[float, float]]) -> float:
    embedding_score = float(np.mean([_bounded(float(candidate.vectors[key] @ seed.vectors[key])) for key in REQUIRED_EMBEDDINGS]))
    context = _Context(seeds=[seed], ranges=ranges)
    sonara_score, _groups = _sonara_similarity(candidate, context)
    return embedding_score * 0.7 + (sonara_score or 0.0) * 0.3


def _diversity_score(candidate: _Candidate, selected: list[_Candidate], ranges: dict[str, tuple[float, float]]) -> float:
    if not selected:
        return 0.5
    nearest = max(_combined_similarity(candidate, item, ranges) for item in selected)
    return _bounded(1.0 - nearest)


def _reason(item: _ScoredCandidate, config: SetBuilderConfig, transition: dict[str, object], classifier_curve: float) -> str:
    if item.breakdown["classifier_target"] > 0.5:
        return "classifier_match"
    if classifier_curve > 0.75 and config.classifier_curves:
        return "mood_shift"
    if transition["confidence"] >= 0.85 and config.mode == "balanced_set":
        return "bridge"
    if config.mode == "weird_adjacent":
        return "weird_adjacent"
    if config.mode == "discovery":
        return "discovery"
    return "similar_to_seed"


def _seed_breakdown(transition: dict[str, object]) -> dict[str, float]:
    return {
        "mert": 1.0,
        "maest_embedding": 1.0,
        "clap_audio": 1.0,
        "sonara_broad": 1.0,
        "classifier_target": 0.0,
        "classifier_avoid": 0.0,
        "classifier_confidence": 1.0,
        "model_disagreement": 0.0,
        "consensus": 1.0,
        "transition": float(transition["confidence"]),
        "classifier_curve": 0.5,
        "diversity": 0.0,
    }


def _item(
    candidate: _Candidate,
    reason: str,
    score: float,
    breakdown: dict[str, float],
    sonara_groups: dict[str, float],
    transition: dict[str, object],
) -> dict[str, object]:
    return {
        "candidate": candidate,
        "track": candidate.track,
        "reason": reason,
        "score": _bounded(score),
        "score_breakdown": {key: round(float(value), 6) for key, value in breakdown.items()},
        "sonara_groups": {key: round(float(value), 6) for key, value in sonara_groups.items()},
        "classifier_scores": _classifier_scores(candidate.track),
        "transition": transition,
    }


def _duplicate_key(track: Track) -> str:
    artist = (track.artist or "").strip().casefold()
    title = (track.title or "").strip().casefold()
    if artist or title:
        return f"{artist}|{title}"
    return Path(track.path).stem.casefold()


def _bounded(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))
