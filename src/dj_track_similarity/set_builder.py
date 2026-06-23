from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field, replace
from math import inf
from pathlib import Path
from typing import Any

import numpy as np

from .database import LibraryDatabase
from .db_schema import TRACK_CLASSIFIER_SCORES_FIELD
from .metadata_payload import optional_float, string_or_none
from .models import Track
from .sonara_similarity_scoring import unwrap_feature_value


SET_BUILDER_MODES = {"similar_crate", "weird_adjacent", "balanced_set", "discovery"}
SET_BUILDER_SEED_MODES = {"manual", "auto"}
SET_BUILDER_ENERGY_CURVES = {"warmup", "balanced", "peak", "wave"}
SET_BUILDER_BPM_MODES = {"general", "low_to_high", "high_to_low"}
SET_BUILDER_BPM_CHANGES = {"slow", "medium", "fast"}
SET_BUILDER_CLASSIFIER_FLOWS = {"flat", "rise", "fall"}
REQUIRED_EMBEDDINGS = ("mert", "maest", "clap")
DEFAULT_MODEL_WEIGHTS = {
    "mert": 0.30,
    "clap": 0.22,
    "maest": 0.18,
    "sonara_broad": 0.30,
}
SEQUENCE_POOL_FACTOR = 20
SEQUENCE_POOL_MIN = 256
SEQUENCE_POOL_MAX = 512
PREFILTER_POOL_FACTOR = 50
PREFILTER_POOL_MIN = 1000
PREFILTER_POOL_MAX = 3000
SQLITE_IN_CHUNK_SIZE = 500
ARTIST_SET_MAX_TRACKS = 1
PREFILTER_ARTIST_POOL_MULTIPLIER = 8
SEQUENCE_ARTIST_POOL_MULTIPLIER = 4
BPM_MIN = 20.0
BPM_MAX = 300.0
BPM_CURVE_WEIGHTS = {
    "similar_crate": 0.12,
    "weird_adjacent": 0.14,
    "balanced_set": 0.20,
    "discovery": 0.16,
}
CLASSIFIER_BIAS_WEIGHT = 0.08
CLASSIFIER_CONFIDENCE_WEIGHT = 0.03
ARTIST_PRESSURE_WEIGHT = 0.035
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
QUICK_DIVERSITY_FIELDS = (
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "onset_density",
    "spectral_centroid_mean",
    "spectral_flatness_mean",
    "dynamic_range_db",
)


@dataclass(frozen=True)
class SetBuilderConfig:
    seed_mode: str = "manual"
    seed_track_ids: list[int] = field(default_factory=list)
    auto_seed_count: int = 5
    mode: str = "balanced_set"
    limit: int = 24
    diversity: float = 0.35
    energy_curve: str = "balanced"
    bpm_mode: str = "general"
    bpm_change: str = "medium"
    bpm_start: float | None = None
    bpm_target: float | None = None
    classifier_preferences: dict[str, float] = field(default_factory=dict)
    classifier_flows: dict[str, str] = field(default_factory=dict)
    random_seed: int | None = None


@dataclass(frozen=True)
class _LightCandidate:
    track: Track
    sonara_features: dict[str, object]
    sonara_values: dict[str, float]
    text_values: dict[str, str]
    duplicate_key: str


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


@dataclass(frozen=True)
class _BpmPlan:
    mode: str
    change: str
    start: float
    target: float


class SmartSetBuilder:
    def __init__(self, db: LibraryDatabase) -> None:
        self.db = db

    def generate(self, config: SetBuilderConfig) -> dict[str, object]:
        cleaned = _clean_config(config)
        rng = _random_generator(cleaned.random_seed)
        manual_seed_ids = _manual_seed_ids(cleaned.seed_track_ids) if cleaned.seed_mode == "manual" else []
        light_candidates, coverage = self._load_light_candidates(cleaned)

        light_by_id = {candidate.track.id: candidate for candidate in light_candidates}
        if cleaned.seed_mode == "manual":
            seed_ids = manual_seed_ids
            self._validate_manual_seeds(seed_ids, light_by_id)
            seed_light_candidates = [light_by_id[track_id] for track_id in seed_ids]
            prefiltered, _sonara_centrality = _prefilter_light_candidates(light_candidates, seed_light_candidates, cleaned)
            hydrate_ids = _ordered_unique([*seed_ids, *(candidate.track.id for candidate in prefiltered)])
        else:
            if not light_candidates:
                raise ValueError("No feature-complete tracks are available for Smart Set Builder")
            auto_start_plan = _bpm_plan(cleaned, light_candidates, [])
            first_seed_light = _select_auto_start_candidate(light_candidates, cleaned, rng, auto_start_plan)
            prefiltered, _sonara_centrality = _prefilter_light_candidates(light_candidates, [first_seed_light], cleaned)
            seed_ids = [first_seed_light.track.id]
            hydrate_ids = _ordered_unique([first_seed_light.track.id, *(candidate.track.id for candidate in prefiltered)])
        candidates = self._hydrate_candidates([light_by_id[track_id] for track_id in hydrate_ids if track_id in light_by_id])
        candidate_by_id = {candidate.track.id: candidate for candidate in candidates}
        if cleaned.seed_mode == "auto":
            if not candidates:
                raise ValueError("No feature-complete tracks are available for Smart Set Builder")
            initial_seeds = [candidate_by_id[track_id] for track_id in seed_ids if track_id in candidate_by_id]
            auto_bpm_plan = _bpm_plan(cleaned, candidates, initial_seeds)
            seed_ids = self._auto_seed_ids(candidates, cleaned, rng, bpm_plan=auto_bpm_plan, initial_seeds=initial_seeds)
        missing_hydrated_seeds = [track_id for track_id in seed_ids if track_id not in candidate_by_id]
        if missing_hydrated_seeds:
            raise ValueError(f"Seed tracks missing required analysis: {missing_hydrated_seeds}")
        seeds = [candidate_by_id[track_id] for track_id in seed_ids]
        bpm_plan = _bpm_plan(cleaned, candidates, seeds)

        ranges = _numeric_ranges(candidates)
        context = _build_context(seeds, ranges)
        scored = [
            self._score_candidate(candidate, context, cleaned)
            for candidate in candidates
            if candidate.track.id not in seed_ids
        ]
        scored = [item for item in scored if item is not None]
        ordered_items = self._ordered_items(seeds, scored, cleaned, ranges, rng, bpm_plan)

        return {
            "mode": cleaned.mode,
            "seed_mode": cleaned.seed_mode,
            "seed_track_ids": seed_ids,
            "coverage": coverage,
            "items": ordered_items[: cleaned.limit],
        }

    def _load_candidates(self) -> tuple[list[_Candidate], dict[str, int]]:
        light_candidates, coverage = self._load_light_candidates()
        return self._hydrate_candidates(light_candidates), coverage

    def _load_light_candidates(self, config: SetBuilderConfig | None = None) -> tuple[list[_LightCandidate], dict[str, int]]:
        summary = self.db.library_summary()
        classifier_scores_field = TRACK_CLASSIFIER_SCORES_FIELD if config and _uses_classifier_config(config) else "NULL AS classifier_scores_json"
        numeric_paths, numeric_slices = _json_path_plan(SONARA_NUMERIC_FIELDS)
        text_paths, text_slices = _json_path_plan(("predominant_chord", "key"))
        metadata_paths = ("$.bpm[0]", "$.bpm", "$.key[0]", "$.key", "$.initialkey[0]", "$.initialkey")
        with self.db.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    t.id, t.path, t.size, t.mtime, t.artist, t.title, t.album,
                    t.bpm, t.musical_key, t.energy, t.duration,
                    EXISTS(SELECT 1 FROM track_likes tl WHERE tl.track_id = t.id) AS liked,
                    {_json_extract_sql("t.metadata_json", numeric_paths)} AS sonara_values_json,
                    {_json_extract_sql("t.metadata_json", text_paths)} AS sonara_text_json,
                    {_json_extract_sql("t.metadata_json", metadata_paths)} AS metadata_values_json,
                    {classifier_scores_field}
                FROM tracks t
                WHERE t.has_sonara_analysis = 1
                  AND t.has_mert_embedding = 1
                  AND t.has_maest_embedding = 1
                  AND t.has_clap_embedding = 1
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                """
            ).fetchall()
        candidates: list[_LightCandidate] = []
        for row in rows:
            values = _values_from_json_row(row["sonara_values_json"], numeric_slices)
            text_values, sonara_features = _text_and_feature_values_from_json_row(row["sonara_text_json"], text_slices)
            metadata = _metadata_from_json_row(row["metadata_values_json"])
            track = Track(
                id=int(row["id"]),
                path=str(row["path"]),
                size=int(row["size"]),
                mtime=float(row["mtime"]),
                artist=row["artist"],
                title=row["title"],
                album=row["album"],
                bpm=row["bpm"],
                musical_key=row["musical_key"],
                energy=row["energy"],
                duration=row["duration"],
                liked=bool(row["liked"]),
                metadata=metadata,
                classifier_scores=_classifier_scores_from_json(row["classifier_scores_json"]),
                analyses=["sonara", "maest", "mert", "clap"],
            )
            candidates.append(
                _LightCandidate(
                    track=track,
                    sonara_features=sonara_features,
                    sonara_values=values,
                    text_values=text_values,
                    duplicate_key=_duplicate_key(track),
                )
            )

        coverage = {
            "tracks": int(summary["tracks"]),
            "eligible_tracks": len(candidates),
            "missing_mert": max(0, int(summary["tracks"]) - int(summary["mert"])),
            "missing_maest": max(0, int(summary["tracks"]) - int(summary["maest"])),
            "missing_clap": max(0, int(summary["tracks"]) - int(summary["clap"])),
            "missing_sonara": max(0, int(summary["tracks"]) - int(summary["sonara"])),
        }
        return candidates, coverage

    def _hydrate_candidates(self, light_candidates: list[_LightCandidate]) -> list[_Candidate]:
        track_ids = _ordered_unique([candidate.track.id for candidate in light_candidates])
        embedding_maps = self._load_embedding_maps_for_ids(track_ids)
        classifier_scores_by_id = self._load_classifier_scores_for_ids(track_ids)
        candidates: list[_Candidate] = []
        for light in light_candidates:
            track_id = light.track.id
            if not all(track_id in embedding_maps[key] for key in REQUIRED_EMBEDDINGS):
                continue
            track = replace(
                light.track,
                classifier_scores=classifier_scores_by_id.get(track_id, light.track.classifier_scores),
            )
            candidates.append(
                _Candidate(
                    track=track,
                    vectors={key: embedding_maps[key][track_id] for key in REQUIRED_EMBEDDINGS},
                    sonara_features=light.sonara_features,
                    sonara_values=light.sonara_values,
                    text_values=light.text_values,
                    duplicate_key=light.duplicate_key,
                )
            )
        return candidates

    def _load_embedding_maps_for_ids(self, track_ids: list[int]) -> dict[str, dict[int, np.ndarray]]:
        cleaned_ids = _ordered_unique(track_ids)
        embedding_maps: dict[str, dict[int, np.ndarray]] = {key: {} for key in REQUIRED_EMBEDDINGS}
        if not cleaned_ids:
            return embedding_maps
        with self.db.connect() as connection:
            for key in REQUIRED_EMBEDDINGS:
                for chunk in _chunks(cleaned_ids, SQLITE_IN_CHUNK_SIZE):
                    placeholders = ", ".join("?" for _ in chunk)
                    rows = connection.execute(
                        f"""
                        SELECT track_id, vector
                        FROM embeddings
                        WHERE embedding_key = ?
                          AND track_id IN ({placeholders})
                        """,
                        (key, *chunk),
                    ).fetchall()
                    for row in rows:
                        embedding_maps[key][int(row["track_id"])] = np.frombuffer(row["vector"], dtype=np.float32).copy()
        return embedding_maps

    def _load_classifier_scores_for_ids(self, track_ids: list[int]) -> dict[int, dict[str, dict[str, object]]]:
        cleaned_ids = _ordered_unique(track_ids)
        scores_by_id: dict[int, dict[str, dict[str, object]]] = {}
        if not cleaned_ids:
            return scores_by_id
        with self.db.connect() as connection:
            for chunk in _chunks(cleaned_ids, SQLITE_IN_CHUNK_SIZE):
                placeholders = ", ".join("?" for _ in chunk)
                rows = connection.execute(
                    f"""
                    SELECT track_id, classifier, score, label, confidence, probabilities_json, feature_set, model_id, analyzed_at
                    FROM track_classifier_scores
                    WHERE track_id IN ({placeholders})
                    """,
                    tuple(chunk),
                ).fetchall()
                for row in rows:
                    track_id = int(row["track_id"])
                    scores_by_id.setdefault(track_id, {})[str(row["classifier"])] = {
                        "score": float(row["score"]),
                        "label": row["label"],
                        "confidence": float(row["confidence"]),
                        "probabilities": _json_object(row["probabilities_json"]),
                        "feature_set": row["feature_set"],
                        "model_id": row["model_id"],
                        "analyzed_at": row["analyzed_at"],
                    }
        return scores_by_id

    def _validate_manual_seeds(self, seed_ids: list[int], candidate_by_id: dict[int, _LightCandidate]) -> None:
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

    def _auto_seed_ids(
        self,
        candidates: list[_Candidate],
        config: SetBuilderConfig,
        rng: np.random.Generator,
        *,
        sonara_centrality: dict[int, float] | None = None,
        bpm_plan: _BpmPlan | None = None,
        initial_seeds: list[_Candidate] | None = None,
    ) -> list[int]:
        count = max(1, min(5, int(config.auto_seed_count)))
        if len(candidates) < count:
            raise ValueError(f"Auto seed mode requires at least {count} feature-complete tracks")
        initial_seed_list = list(initial_seeds or [])
        if len(initial_seed_list) >= count:
            return [seed.track.id for seed in initial_seed_list[:count]]
        ranges = _numeric_ranges(candidates)
        anchor_positions = _anchor_positions(config.limit, count)
        target_count = max(config.limit, count)
        if sonara_centrality is None:
            sonara_centrality = _global_sonara_centrality_scores(candidates, ranges)
        embedding_centroids = _embedding_centroids(candidates)
        centrality = [
            (candidate, _auto_anchor_centrality(candidate, sonara_centrality, embedding_centroids))
            for candidate in candidates
        ]
        centrality.sort(key=lambda item: (-item[1], item[0].track.artist or "", item[0].track.title or "", item[0].track.path))
        seeds: list[_Candidate] = list(initial_seed_list)
        seen_keys: set[str] = {seed.duplicate_key for seed in seeds}
        artist_counts: Counter[str] = Counter()
        for seed in seeds:
            _record_artist(seed, artist_counts)
        while len(seeds) < count:
            scored_options: list[tuple[_Candidate, float]] = []
            for allow_near_duplicate in (False, True):
                scored_options = []
                for candidate, centrality_score in centrality:
                    if candidate.duplicate_key in seen_keys:
                        continue
                    if not _artist_allowed(candidate, seeds[-1] if seeds else None, artist_counts):
                        continue
                    if not allow_near_duplicate and seeds and max(_fast_diversity_similarity(candidate, seed, ranges) for seed in seeds) > 0.995:
                        continue
                    score = _auto_anchor_selection_score(candidate, centrality_score, seeds, ranges, config.mode)
                    anchor_position = anchor_positions[len(seeds)] if len(seeds) < len(anchor_positions) else len(seeds)
                    if bpm_plan is not None:
                        bpm_score = _bpm_curve_score(candidate, bpm_plan, anchor_position, target_count)
                        score = score * 0.45 + bpm_score * 0.55
                    score = _auto_anchor_classifier_adjusted_score(candidate, score, config, anchor_position, target_count)
                    scored_options.append((candidate, score))
                if scored_options or not seeds:
                    break
            if not scored_options:
                break
            selected = _sample_scored_candidate(
                scored_options,
                rng,
                mode=config.mode,
                pool_size=_auto_anchor_sample_pool_size(config.mode, count, len(scored_options)),
                force_sample=True,
            )
            seeds.append(selected)
            seen_keys.add(selected.duplicate_key)
            _record_artist(selected, artist_counts)
        if len(seeds) < count:
            raise ValueError(f"Auto seed mode could not choose {count} artist-diverse anchors")
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
        classifier_preference, classifier_confidence = _classifier_modifiers(candidate.track, config)
        base = (
            model_scores["mert"] * DEFAULT_MODEL_WEIGHTS["mert"]
            + model_scores["clap_audio"] * DEFAULT_MODEL_WEIGHTS["clap"]
            + model_scores["maest_embedding"] * DEFAULT_MODEL_WEIGHTS["maest"]
            + sonara_score * DEFAULT_MODEL_WEIGHTS["sonara_broad"]
        )
        disagreement = float(np.std(list(model_scores.values()) + [sonara_score]))
        base = _mode_adjusted_base_score(base, disagreement, config.mode)

        breakdown = {
            **model_scores,
            "sonara_broad": sonara_score,
            "classifier_preference": classifier_preference,
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
        rng: np.random.Generator,
        bpm_plan: _BpmPlan | None,
    ) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        previous: _Candidate | None = None
        seen_duplicates: set[str] = set()
        artist_counts: Counter[str] = Counter()
        anchor_positions = _anchor_positions(config.limit, len(seeds))
        next_seed_index = 0

        seed_artist_counts = Counter(artist for artist in (_artist_key(seed.track) for seed in seeds) if artist is not None)
        if any(count > ARTIST_SET_MAX_TRACKS for count in seed_artist_counts.values()):
            raise ValueError("Seed tracks violate artist spacing limits: use at most 1 track per known artist")

        seed_duplicates = {seed.duplicate_key for seed in seeds}
        pending_seeds = list(seeds)
        scored_pool = _sequence_candidate_pool(scored_candidates, config.limit, len(seeds))
        remaining = [item for item in scored_pool if item.candidate.duplicate_key not in seed_duplicates]
        selected_sequence: list[_Candidate] = []
        target_count = max(config.limit, len(seeds))

        while len(items) < config.limit and (pending_seeds or remaining):
            position = len(items)
            if pending_seeds and next_seed_index < len(anchor_positions) and position >= anchor_positions[next_seed_index]:
                seed = pending_seeds.pop(0)
                if not _artist_allowed(seed, previous, artist_counts):
                    raise ValueError("Seed tracks violate artist spacing limits: use at most 1 track per known artist")
                transition = _transition(previous, seed)
                items.append(_item(seed, "seed_anchor", 1.0, _seed_breakdown(transition), {}, transition))
                previous = seed
                selected_sequence.append(seed)
                seen_duplicates.add(seed.duplicate_key)
                _record_artist(seed, artist_counts)
                next_seed_index += 1
                remaining = [item for item in remaining if item.candidate.duplicate_key not in seen_duplicates]
                continue

            pending_seed_artists = _pending_seed_artists(pending_seeds)
            valid_remaining = [
                item for item in remaining
                if _artist_allowed(item.candidate, previous, artist_counts)
                and not _uses_pending_seed_artist(item.candidate, pending_seed_artists)
            ]
            if not valid_remaining:
                if pending_seeds:
                    seed = pending_seeds.pop(0)
                    if not _artist_allowed(seed, previous, artist_counts):
                        raise ValueError("Seed tracks violate artist spacing limits: use at most 1 track per known artist")
                    transition = _transition(previous, seed)
                    items.append(_item(seed, "seed_anchor", 1.0, _seed_breakdown(transition), {}, transition))
                    previous = seed
                    selected_sequence.append(seed)
                    seen_duplicates.add(seed.duplicate_key)
                    _record_artist(seed, artist_counts)
                    next_seed_index += 1
                    remaining = [item for item in remaining if item.candidate.duplicate_key not in seen_duplicates]
                    continue
                break
            sequence_options = [
                (
                    item,
                    self._sequence_score(item, previous, selected_sequence, position, target_count, config, ranges, bpm_plan)
                    + _artist_pressure_score(item.candidate, remaining) * ARTIST_PRESSURE_WEIGHT,
                )
                for item in valid_remaining
            ]
            selected, final_score = _sample_scored_item(
                sequence_options,
                rng,
                mode=config.mode,
                pool_size=_sequence_sample_pool_size(config.mode, len(sequence_options)),
            )
            transition = _transition(previous, selected.candidate)
            flow_score = _classifier_flow_score(selected.candidate.track, config, position, target_count)
            bpm_curve_score = _bpm_curve_score(selected.candidate, bpm_plan, position, target_count)
            diversity_score = _diversity_score(selected.candidate, selected_sequence, ranges)
            breakdown = dict(selected.breakdown)
            breakdown["transition"] = transition["confidence"]
            breakdown["classifier_flow"] = flow_score
            breakdown["bpm_curve"] = bpm_curve_score
            breakdown["diversity"] = diversity_score
            reason = _reason(selected, config, transition, flow_score)
            items.append(_item(selected.candidate, reason, final_score, breakdown, selected.sonara_groups, transition))
            previous = selected.candidate
            selected_sequence.append(selected.candidate)
            seen_duplicates.add(selected.candidate.duplicate_key)
            _record_artist(selected.candidate, artist_counts)
            remaining = [item for item in remaining if item.candidate.duplicate_key not in seen_duplicates]
        if pending_seeds:
            raise ValueError("Seed tracks violate artist spacing limits: use at most 1 track per known artist")
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
        bpm_plan: _BpmPlan | None,
    ) -> float:
        transition_score = _transition(previous, item.candidate)["confidence"]
        curve_score = _energy_curve_score(item.candidate, config.energy_curve, position, target_count)
        classifier_flow = _classifier_flow_score(item.candidate.track, config, position, target_count)
        bpm_curve = _bpm_curve_score(item.candidate, bpm_plan, position, target_count)
        diversity_score = _diversity_score(item.candidate, selected_sequence, ranges)
        diversity_weight = config.diversity * 0.10
        bpm_weight = _bpm_curve_weight(config.mode, bpm_plan)
        if config.mode == "balanced_set":
            score = (
                item.base_score * (0.68 - diversity_weight - bpm_weight)
                + transition_score * 0.20
                + curve_score * 0.07
                + classifier_flow * 0.05
                + bpm_curve * bpm_weight
                + diversity_score * diversity_weight
            )
        elif config.mode == "weird_adjacent":
            weird = min(1.0, item.breakdown["model_disagreement"] * 3.0)
            score = (
                item.base_score * (0.72 - diversity_weight - bpm_weight)
                + weird * 0.18
                + transition_score * 0.06
                + classifier_flow * 0.04
                + bpm_curve * bpm_weight
                + diversity_score * diversity_weight
            )
        elif config.mode == "discovery":
            uncertainty = 1.0 - abs(item.base_score - 0.5) * 2.0
            score = (
                item.base_score * (0.70 - diversity_weight - bpm_weight)
                + max(0.0, uncertainty) * 0.15
                + transition_score * 0.08
                + classifier_flow * 0.07
                + bpm_curve * bpm_weight
                + diversity_score * diversity_weight
            )
        else:
            score = (
                item.base_score * (0.88 - diversity_weight - bpm_weight)
                + transition_score * 0.06
                + classifier_flow * 0.06
                + bpm_curve * bpm_weight
                + diversity_score * diversity_weight
            )
        return _bounded(score)


@dataclass(frozen=True)
class _Context:
    seeds: list[_Candidate]
    ranges: dict[str, tuple[float, float]]
    embedding_centroids: dict[str, np.ndarray] = field(default_factory=dict)
    sonara_centroid: dict[str, float] = field(default_factory=dict)
    chord_context: set[str] = field(default_factory=set)


def _build_context(seeds: list[_Candidate], ranges: dict[str, tuple[float, float]]) -> _Context:
    return _Context(
        seeds=seeds,
        ranges=ranges,
        embedding_centroids=_embedding_centroids(seeds),
        sonara_centroid=_sonara_centroid(seeds, ranges),
        chord_context=_text_context(seeds, "predominant_chord"),
    )


def _clean_config(config: SetBuilderConfig) -> SetBuilderConfig:
    seed_mode = config.seed_mode.strip()
    mode = config.mode.strip()
    energy_curve = config.energy_curve.strip()
    bpm_mode = config.bpm_mode.strip()
    bpm_change = config.bpm_change.strip()
    if seed_mode not in SET_BUILDER_SEED_MODES:
        raise ValueError(f"Unsupported seed mode: {seed_mode}")
    if mode not in SET_BUILDER_MODES:
        raise ValueError(f"Unsupported set builder mode: {mode}")
    if energy_curve not in SET_BUILDER_ENERGY_CURVES:
        raise ValueError(f"Unsupported energy curve: {energy_curve}")
    if bpm_mode not in SET_BUILDER_BPM_MODES:
        raise ValueError(f"Unsupported BPM mode: {bpm_mode}")
    if bpm_change not in SET_BUILDER_BPM_CHANGES:
        raise ValueError(f"Unsupported BPM change mode: {bpm_change}")
    return SetBuilderConfig(
        seed_mode=seed_mode,
        seed_track_ids=list(dict.fromkeys(int(track_id) for track_id in config.seed_track_ids)),
        auto_seed_count=max(1, min(5, int(config.auto_seed_count))),
        mode=mode,
        limit=max(1, min(500, int(config.limit))),
        diversity=max(0.0, min(1.0, float(config.diversity))),
        energy_curve=energy_curve,
        bpm_mode=bpm_mode,
        bpm_change=bpm_change,
        bpm_start=_clean_bpm_value(config.bpm_start, "bpm_start"),
        bpm_target=_clean_bpm_value(config.bpm_target, "bpm_target"),
        classifier_preferences=_clean_preference_map(config.classifier_preferences),
        classifier_flows=_clean_classifier_flows(config.classifier_flows),
        random_seed=None if config.random_seed is None else int(config.random_seed),
    )


def _clean_bpm_value(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    cleaned = optional_float(value)
    if cleaned is None or not np.isfinite(cleaned):
        raise ValueError(f"Invalid {name}: {value}")
    if not BPM_MIN <= cleaned <= BPM_MAX:
        raise ValueError(f"{name} must be between {BPM_MIN:g} and {BPM_MAX:g}")
    return float(cleaned)


def _clean_preference_map(values: dict[str, float]) -> dict[str, float]:
    cleaned: dict[str, float] = {}
    for key, value in values.items():
        name = str(key).strip()
        score = max(-1.0, min(1.0, float(value)))
        if name and score != 0.0:
            cleaned[name] = score
    return cleaned


def _clean_classifier_flows(values: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, flow in values.items():
        name = str(key).strip()
        if not name:
            continue
        normalized = str(flow).strip().lower()
        if normalized not in SET_BUILDER_CLASSIFIER_FLOWS:
            raise ValueError(f"Unsupported classifier flow: {flow}")
        if normalized == "flat":
            continue
        cleaned[name] = normalized
    return cleaned


def _classifier_bias_delta(classifier_preference: float) -> float:
    return classifier_preference * CLASSIFIER_BIAS_WEIGHT


def _mode_adjusted_base_score(base: float, disagreement: float, mode: str) -> float:
    if mode == "weird_adjacent":
        return base * 0.88 + min(1.0, disagreement * 3.0) * 0.12
    if mode == "discovery":
        uncertainty = 1.0 - abs(base - 0.5) * 2.0
        return base * 0.88 + max(0.0, uncertainty) * 0.12
    if mode == "similar_crate":
        return base * 0.96 + max(0.0, 1.0 - disagreement) * 0.04
    return base


def _manual_seed_ids(seed_track_ids: list[int]) -> list[int]:
    seed_ids = list(dict.fromkeys(seed_track_ids))
    if not 1 <= len(seed_ids) <= 5:
        raise ValueError("Manual set builder requires 1-5 seed tracks")
    return seed_ids


def _random_generator(seed: int | None) -> np.random.Generator:
    return np.random.default_rng(seed)


def _uses_classifier_config(config: SetBuilderConfig) -> bool:
    return bool(config.classifier_preferences)


def _uses_classifier_flow_config(config: SetBuilderConfig) -> bool:
    return any(config.classifier_flows.get(key, "flat") != "flat" for key in config.classifier_preferences)


def _ordered_unique(values: list[int]) -> list[int]:
    return list(dict.fromkeys(int(value) for value in values))


def _chunks(values: list[int], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _json_path_plan(fields) -> tuple[tuple[str, ...], dict[str, slice]]:
    paths: list[str] = []
    slices: dict[str, slice] = {}
    for field in fields:
        start = len(paths)
        parts = str(field).split(".")
        if len(parts) == 3 and parts[1] == "summary":
            paths.append(f"$.sonara_features.{parts[0]}.summary.{parts[2]}")
        else:
            paths.extend((f"$.sonara_features.{field}.value", f"$.sonara_features.{field}"))
        slices[str(field)] = slice(start, len(paths))
    return tuple(paths), slices


def _json_extract_sql(column: str, paths) -> str:
    quoted = ", ".join(f"'{path}'" for path in paths)
    return f"json_extract({column}, {quoted})"


def _json_array(raw: object) -> list[object]:
    if raw is None:
        return []
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else [parsed]


def _json_object(raw: object) -> dict[str, object]:
    if raw is None:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _first_present(values: list[object], value_slice: slice) -> object | None:
    for value in values[value_slice]:
        if value is not None:
            return value
    return None


def _values_from_json_row(raw: object, slices: dict[str, slice]) -> dict[str, float]:
    row_values = _json_array(raw)
    values: dict[str, float] = {}
    for key, value_slice in slices.items():
        number = optional_float(unwrap_feature_value(_first_present(row_values, value_slice)))
        if number is not None:
            values[key] = number
    return values


def _text_and_feature_values_from_json_row(raw: object, slices: dict[str, slice]) -> tuple[dict[str, str], dict[str, object]]:
    row_values = _json_array(raw)
    text_values: dict[str, str] = {}
    sonara_features: dict[str, object] = {}
    for key, value_slice in slices.items():
        text = string_or_none(unwrap_feature_value(_first_present(row_values, value_slice)))
        if not text:
            continue
        if key == "predominant_chord":
            text_values[key] = text.casefold()
        elif key == "key":
            sonara_features[key] = text
    return text_values, sonara_features


def _metadata_from_json_row(raw: object) -> dict[str, object]:
    row_values = _json_array(raw)
    metadata: dict[str, object] = {}
    bpm = _first_present(row_values, slice(0, 2))
    key = _first_present(row_values, slice(2, 4))
    initial_key = _first_present(row_values, slice(4, 6))
    if bpm is not None:
        metadata["bpm"] = bpm
    if key is not None:
        metadata["key"] = key
    if initial_key is not None:
        metadata["initialkey"] = initial_key
    return metadata


def _classifier_scores_from_json(raw: object) -> dict[str, dict[str, object]] | None:
    if raw is None:
        return None
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) and parsed else None


def _prefilter_light_candidates(
    candidates: list[_LightCandidate],
    seed_candidates: list[_LightCandidate],
    config: SetBuilderConfig,
) -> tuple[list[_LightCandidate], dict[int, float]]:
    if not candidates:
        return [], {}

    seed_ids = {candidate.track.id for candidate in seed_candidates}
    available = [candidate for candidate in candidates if candidate.track.id not in seed_ids]
    if not available:
        return [], {}

    pool_size = min(
        len(available),
        max(PREFILTER_POOL_MIN, max(config.limit, config.auto_seed_count) * PREFILTER_POOL_FACTOR),
        PREFILTER_POOL_MAX,
    )
    ranges = _numeric_ranges(candidates)
    sonara_centrality: dict[int, float] = {}

    if seed_candidates:
        seed_centroid = _sonara_centroid(seed_candidates, ranges)
        chord_context = _text_context(seed_candidates, "predominant_chord")
        seed_scores = _sonara_similarity_scores_to_centroid(available, ranges, seed_centroid, chord_context)

        def sonara_score(candidate: _LightCandidate) -> float:
            return seed_scores.get(candidate.track.id, 0.0)

    else:
        sonara_centrality = _global_sonara_centrality_scores(candidates, ranges)

        def sonara_score(candidate: _LightCandidate) -> float:
            return sonara_centrality.get(candidate.track.id, 0.0)

    scored: list[tuple[float, _LightCandidate]] = []
    for candidate in available:
        preference, confidence = _classifier_modifiers(candidate.track, config)
        score = sonara_score(candidate)
        score += _classifier_bias_delta(preference)
        if _uses_classifier_config(config):
            score += (confidence - 1.0) * CLASSIFIER_CONFIDENCE_WEIGHT
        scored.append((score, candidate))

    scored.sort(
        key=lambda item: (
            -item[0],
            item[1].track.artist or "",
            item[1].track.title or "",
            item[1].track.path,
        )
    )

    return _select_light_pool(scored, pool_size), sonara_centrality


def _select_light_pool(scored: list[tuple[float, _LightCandidate]], pool_size: int) -> list[_LightCandidate]:
    selected: list[_LightCandidate] = []
    seen_duplicates: set[str] = set()
    artist_counts: Counter[str] = Counter()
    per_artist_limit = max(ARTIST_SET_MAX_TRACKS * PREFILTER_ARTIST_POOL_MULTIPLIER, pool_size // 20)
    for _score, candidate in scored:
        if candidate.duplicate_key in seen_duplicates:
            continue
        artist_key = _artist_key(candidate.track)
        if artist_key and artist_counts[artist_key] >= per_artist_limit:
            continue
        selected.append(candidate)
        seen_duplicates.add(candidate.duplicate_key)
        if artist_key:
            artist_counts[artist_key] += 1
        if len(selected) >= pool_size:
            return selected
    for _score, candidate in scored:
        if candidate.duplicate_key in seen_duplicates:
            continue
        selected.append(candidate)
        seen_duplicates.add(candidate.duplicate_key)
        if len(selected) >= pool_size:
            break
    return selected


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
    cached = context.embedding_centroids.get(key)
    if cached is not None:
        return _bounded(float(candidate.vectors[key] @ cached))
    centroid = np.mean([seed.vectors[key] for seed in context.seeds], axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm <= 0:
        return 0.0
    centroid = centroid / norm
    return _bounded(float(candidate.vectors[key] @ centroid))


def _sonara_similarity(candidate: _Candidate, context: _Context) -> tuple[float | None, dict[str, float]]:
    seed_centroid = context.sonara_centroid or _sonara_centroid(context.seeds, context.ranges)
    chord_context = context.chord_context or _text_context(context.seeds, "predominant_chord")
    return _sonara_similarity_to_centroid(candidate, context.ranges, seed_centroid, chord_context)


def _global_sonara_centrality_scores(candidates: list[_Candidate], ranges: dict[str, tuple[float, float]]) -> dict[int, float]:
    seed_centroid = _sonara_centroid(candidates, ranges)
    chord_context = _text_context(candidates, "predominant_chord")
    return _sonara_similarity_scores_to_centroid(candidates, ranges, seed_centroid, chord_context)


def _sonara_similarity_scores_to_centroid(
    candidates: list[_Candidate],
    ranges: dict[str, tuple[float, float]],
    seed_centroid: dict[str, float],
    chord_context: set[str],
) -> dict[int, float]:
    if not candidates:
        return {}
    group_score_sums = {
        group: np.zeros(len(candidates), dtype=np.float32)
        for group in SONARA_GROUP_WEIGHTS
    }
    group_weight_sums = {
        group: np.zeros(len(candidates), dtype=np.float32)
        for group in SONARA_GROUP_WEIGHTS
    }
    for key, centroid in seed_centroid.items():
        value_range = ranges.get(key)
        if value_range is None:
            continue
        lower, upper = value_range
        raw_values = np.array(
            [candidate.sonara_values.get(key, np.nan) for candidate in candidates],
            dtype=np.float32,
        )
        mask = np.isfinite(raw_values)
        if not np.any(mask):
            continue
        if upper == lower:
            normalized = np.full(len(candidates), np.nan, dtype=np.float32)
            normalized[mask] = 0.5
        else:
            normalized = (raw_values - lower) / (upper - lower)
        scores = np.maximum(0.0, 1.0 - np.abs(normalized - centroid))
        scores[~mask] = 0.0
        group, weight = SONARA_NUMERIC_FIELDS[key]
        group_score_sums[group] += scores * weight
        group_weight_sums[group][mask] += weight

    if chord_context:
        tonal_scores = group_score_sums["tonal"]
        tonal_weights = group_weight_sums["tonal"]
        for index, candidate in enumerate(candidates):
            candidate_chord = candidate.text_values.get("predominant_chord")
            if candidate_chord:
                tonal_scores[index] += 0.35 if candidate_chord in chord_context else 0.0
                tonal_weights[index] += 0.35

    weighted_total = np.zeros(len(candidates), dtype=np.float32)
    weight_total = np.zeros(len(candidates), dtype=np.float32)
    for group, group_weight in SONARA_GROUP_WEIGHTS.items():
        group_weights = group_weight_sums[group]
        mask = group_weights > 0
        if not np.any(mask):
            continue
        group_scores = np.zeros(len(candidates), dtype=np.float32)
        group_scores[mask] = group_score_sums[group][mask] / group_weights[mask]
        weighted_total[mask] += group_scores[mask] * group_weight
        weight_total[mask] += group_weight

    scores: dict[int, float] = {}
    mask = weight_total > 0
    for index, candidate in enumerate(candidates):
        scores[candidate.track.id] = _bounded(float(weighted_total[index] / weight_total[index])) if mask[index] else 0.0
    return scores


def _sonara_similarity_to_centroid(
    candidate: _Candidate,
    ranges: dict[str, tuple[float, float]],
    seed_centroid: dict[str, float],
    chord_context: set[str],
) -> tuple[float | None, dict[str, float]]:
    group_scores: dict[str, list[tuple[float, float]]] = {group: [] for group in SONARA_GROUP_WEIGHTS}
    for key, value in candidate.sonara_values.items():
        if key not in seed_centroid or key not in ranges:
            continue
        normalized = _normalize(value, ranges[key])
        if normalized is None:
            continue
        group, weight = SONARA_NUMERIC_FIELDS[key]
        score = max(0.0, 1.0 - abs(normalized - seed_centroid[key]))
        group_scores[group].append((score, weight))

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


def _embedding_centroids(candidates: list[_Candidate]) -> dict[str, np.ndarray]:
    centroids: dict[str, np.ndarray] = {}
    for key in REQUIRED_EMBEDDINGS:
        centroid = np.mean([candidate.vectors[key] for candidate in candidates], axis=0)
        norm = float(np.linalg.norm(centroid))
        if norm > 0:
            centroids[key] = centroid / norm
    return centroids


def _auto_anchor_centrality(
    candidate: _Candidate,
    sonara_centrality: dict[int, float],
    embedding_centroids: dict[str, np.ndarray],
) -> float:
    embedding_scores = [
        _bounded(float(candidate.vectors[key] @ centroid))
        for key, centroid in embedding_centroids.items()
    ]
    embedding_score = float(np.mean(embedding_scores)) if embedding_scores else 0.0
    sonara_score = sonara_centrality.get(candidate.track.id, 0.0)
    return _bounded(embedding_score * 0.7 + sonara_score * 0.3)


def _select_auto_start_candidate(
    candidates: list[_LightCandidate],
    config: SetBuilderConfig,
    rng: np.random.Generator,
    bpm_plan: _BpmPlan | None,
) -> _LightCandidate:
    scored = [(candidate, _auto_start_selection_score(candidate, config, bpm_plan)) for candidate in candidates]
    index = _sample_ranked_index([score for _candidate, score in scored], rng, mode=config.mode, force_sample=True)
    return scored[index][0]


def _auto_start_selection_score(
    candidate: _LightCandidate,
    config: SetBuilderConfig,
    bpm_plan: _BpmPlan | None,
) -> float:
    score = 0.5
    if _uses_classifier_config(config):
        preference, confidence = _classifier_modifiers(candidate.track, config)
        score = _bounded(0.5 + preference * 0.5)
        score += (confidence - 1.0) * CLASSIFIER_CONFIDENCE_WEIGHT
    if bpm_plan is not None:
        bpm_score = _bpm_curve_score(candidate, bpm_plan, 0, max(config.limit, config.auto_seed_count))
        score = score * 0.55 + bpm_score * 0.45
    return _bounded(score)


def _auto_anchor_selection_score(
    candidate: _Candidate,
    centrality_score: float,
    selected: list[_Candidate],
    ranges: dict[str, tuple[float, float]],
    mode: str,
) -> float:
    if not selected:
        return _bounded(centrality_score)
    relatedness = max(_fast_diversity_similarity(candidate, seed, ranges) for seed in selected)
    if mode == "similar_crate":
        score = centrality_score * 0.35 + relatedness * 0.65
    elif mode == "weird_adjacent":
        diversity = 1.0 - relatedness
        score = centrality_score * 0.38 + relatedness * 0.47 + diversity * 0.15
    elif mode == "discovery":
        score = centrality_score * 0.55 + relatedness * 0.45
    else:
        score = centrality_score * 0.45 + relatedness * 0.55
    return _bounded(score)


def _auto_anchor_classifier_adjusted_score(
    candidate: _Candidate,
    base_score: float,
    config: SetBuilderConfig,
    position: int,
    target_count: int,
) -> float:
    if not _uses_classifier_config(config):
        return base_score
    preference, confidence = _classifier_modifiers(candidate.track, config)
    preference_values = [_bounded(0.5 + preference * 0.5)]
    flow_score = _classifier_flow_score(candidate.track, config, position, target_count)
    if flow_score != 0.5:
        preference_values.append(flow_score)
    preference = float(np.mean(preference_values)) if preference_values else 0.5
    adjusted = base_score * 0.90 + preference * 0.10
    adjusted += (confidence - 1.0) * CLASSIFIER_CONFIDENCE_WEIGHT
    return adjusted


def _auto_anchor_sample_pool_size(mode: str, count: int, total: int) -> int:
    if mode == "similar_crate":
        factor, floor, ceiling = 18, 16, 100
    elif mode == "weird_adjacent":
        factor, floor, ceiling = 45, 40, 240
    elif mode == "discovery":
        factor, floor, ceiling = 60, 50, 320
    else:
        factor, floor, ceiling = 32, 28, 180
    return min(total, max(floor, count * factor), ceiling)


def _sequence_sample_pool_size(mode: str, total: int) -> int:
    if mode == "similar_crate":
        return min(total, 8)
    if mode == "weird_adjacent":
        return min(total, 24)
    if mode == "discovery":
        return min(total, 28)
    return min(total, 14)


def _sampling_temperature(mode: str) -> float:
    if mode == "similar_crate":
        return 0.025
    if mode == "weird_adjacent":
        return 0.06
    if mode == "discovery":
        return 0.08
    return 0.025


def _sampling_margin(mode: str) -> float:
    if mode == "similar_crate":
        return 0.008
    if mode == "weird_adjacent":
        return 0.015
    if mode == "discovery":
        return 0.02
    return 0.006


def _sample_scored_candidate(
    options: list[tuple[_Candidate, float]],
    rng: np.random.Generator,
    *,
    mode: str,
    pool_size: int,
    force_sample: bool = False,
) -> _Candidate:
    ranked = sorted(
        options,
        key=lambda item: (
            -item[1],
            item[0].track.artist or "",
            item[0].track.title or "",
            item[0].track.path,
        ),
    )[: max(1, pool_size)]
    index = _sample_ranked_index([score for _candidate, score in ranked], rng, mode=mode, force_sample=force_sample)
    return ranked[index][0]


def _sample_scored_item(
    options: list[tuple[_ScoredCandidate, float]],
    rng: np.random.Generator,
    *,
    mode: str,
    pool_size: int,
) -> tuple[_ScoredCandidate, float]:
    ranked = sorted(
        options,
        key=lambda item: (
            -item[1],
            item[0].breakdown.get("consensus", 0.0),
            item[0].candidate.track.artist or "",
            item[0].candidate.track.title or "",
            item[0].candidate.track.path,
        ),
    )[: max(1, pool_size)]
    index = _sample_ranked_index([score for _item, score in ranked], rng, mode=mode, force_sample=False)
    return ranked[index]


def _sample_ranked_index(scores: list[float], rng: np.random.Generator, *, mode: str, force_sample: bool) -> int:
    if len(scores) <= 1:
        return 0
    cleaned = np.asarray([_bounded(score) for score in scores], dtype=np.float64)
    if not force_sample and cleaned[0] - cleaned[1] >= _sampling_margin(mode):
        return 0
    logits = (cleaned - float(np.max(cleaned))) / _sampling_temperature(mode)
    weights = np.exp(np.clip(logits, -60.0, 0.0))
    weight_sum = float(np.sum(weights))
    if not np.isfinite(weight_sum) or weight_sum <= 0:
        probabilities = np.full(len(scores), 1.0 / len(scores), dtype=np.float64)
    else:
        probabilities = weights / weight_sum
    return int(rng.choice(len(scores), p=probabilities))


def _normalize(value: float, value_range: tuple[float, float]) -> float | None:
    lower, upper = value_range
    if upper == lower:
        return 0.5
    normalized = (value - lower) / (upper - lower)
    if not np.isfinite(normalized):
        return None
    return float(normalized)


def _sequence_candidate_pool(scored_candidates: list[_ScoredCandidate], limit: int, seed_count: int) -> list[_ScoredCandidate]:
    remaining_slots = max(0, int(limit) - int(seed_count))
    if remaining_slots <= 0 or not scored_candidates:
        return []
    pool_size = min(
        len(scored_candidates),
        max(SEQUENCE_POOL_MIN, remaining_slots * SEQUENCE_POOL_FACTOR),
        SEQUENCE_POOL_MAX,
    )
    if len(scored_candidates) <= pool_size:
        return scored_candidates
    sorted_candidates = sorted(
        scored_candidates,
        key=lambda item: (
            item.base_score,
            item.breakdown.get("consensus", 0.0),
            item.candidate.track.artist or "",
            item.candidate.track.title or "",
            item.candidate.track.path,
        ),
        reverse=True,
    )
    return _select_scored_pool(sorted_candidates, pool_size)


def _anchor_positions(limit: int, seed_count: int) -> list[int]:
    if seed_count <= 0:
        return []
    target_count = max(int(limit), int(seed_count))
    if seed_count == 1:
        return [0]
    last_position = max(0, target_count - 1)
    return [int(round(index * last_position / (seed_count - 1))) for index in range(seed_count)]


def _select_scored_pool(scored: list[_ScoredCandidate], pool_size: int) -> list[_ScoredCandidate]:
    selected: list[_ScoredCandidate] = []
    artist_counts: Counter[str] = Counter()
    per_artist_limit = max(ARTIST_SET_MAX_TRACKS * SEQUENCE_ARTIST_POOL_MULTIPLIER, pool_size // 20)
    for item in scored:
        artist_key = _artist_key(item.candidate.track)
        if artist_key and artist_counts[artist_key] >= per_artist_limit:
            continue
        selected.append(item)
        if artist_key:
            artist_counts[artist_key] += 1
        if len(selected) >= pool_size:
            return selected
    for item in scored:
        if item in selected:
            continue
        selected.append(item)
        if len(selected) >= pool_size:
            break
    return selected


def _classifier_modifiers(track: Track, config: SetBuilderConfig) -> tuple[float, float]:
    scores = _classifier_scores(track)
    used_keys = set(config.classifier_preferences)
    if not used_keys:
        return 0.0, 1.0
    present = 0
    preference_scores: list[float] = []
    for key, preference in config.classifier_preferences.items():
        score = scores.get(key)
        if score is None:
            continue
        present += 1
        preference_scores.append(preference * (score * 2.0 - 1.0))
    preference = float(np.mean(preference_scores)) if preference_scores else 0.0
    confidence = present / len(used_keys) if used_keys else 1.0
    return _bounded_signed(preference), _bounded(confidence)


def _classifier_flow_score(track: Track, config: SetBuilderConfig, position: int, target_count: int) -> float:
    if not config.classifier_preferences:
        return 0.5
    scores = _classifier_scores(track)
    progress = 0.0 if target_count <= 1 else position / max(target_count - 1, 1)
    values: list[float] = []
    for key, preference in config.classifier_preferences.items():
        flow = config.classifier_flows.get(key, "flat")
        actual = scores.get(key)
        if actual is None:
            values.append(0.5)
            continue
        alignment = actual if preference > 0 else 1.0 - actual
        if flow == "rise":
            desired = progress
        elif flow == "fall":
            desired = 1.0 - progress
        else:
            desired = 1.0
        raw = max(0.0, 1.0 - abs(alignment - desired))
        values.append(0.5 + (raw - 0.5) * abs(preference))
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


def _bpm_plan(config: SetBuilderConfig, candidates: list[_Candidate], seeds: list[_Candidate]) -> _BpmPlan | None:
    if config.bpm_mode == "general":
        return None
    bpms = [
        bpm
        for candidate in candidates
        if (bpm := _usable_bpm(_track_bpm(candidate))) is not None
    ]
    if not bpms:
        return None
    seed_bpm = _usable_bpm(_track_bpm(seeds[0])) if seeds else None
    if config.bpm_mode == "low_to_high":
        start = _first_bpm(config.bpm_start, seed_bpm, min(bpms))
        target = config.bpm_target if config.bpm_target is not None else max(bpms)
        if target < start:
            start, target = target, start
    else:
        start = _first_bpm(config.bpm_start, seed_bpm, max(bpms))
        target = config.bpm_target if config.bpm_target is not None else min(bpms)
        if target > start:
            start, target = target, start
    return _BpmPlan(mode=config.bpm_mode, change=config.bpm_change, start=float(start), target=float(target))


def _first_bpm(*values: float | None) -> float:
    for value in values:
        if value is not None:
            return float(value)
    raise ValueError("No BPM value available")


def _bpm_curve_weight(mode: str, bpm_plan: _BpmPlan | None) -> float:
    if bpm_plan is None:
        return 0.0
    return BPM_CURVE_WEIGHTS.get(mode, 0.14)


def _bpm_curve_score(candidate: _Candidate, bpm_plan: _BpmPlan | None, position: int, target_count: int) -> float:
    if bpm_plan is None:
        return 0.5
    bpm = _usable_bpm(_track_bpm(candidate))
    if bpm is None:
        return 0.5
    desired = _bpm_curve_target(bpm_plan, position, target_count)
    tolerance = _bpm_curve_tolerance(bpm_plan)
    return _bounded(1.0 - abs(bpm - desired) / tolerance)


def _bpm_curve_target(bpm_plan: _BpmPlan, position: int, target_count: int) -> float:
    progress = 0.0 if target_count <= 1 else position / max(target_count - 1, 1)
    shaped = _bpm_curve_progress(progress, bpm_plan.change)
    return bpm_plan.start + (bpm_plan.target - bpm_plan.start) * shaped


def _bpm_curve_progress(progress: float, change: str) -> float:
    progress = _bounded(progress)
    if change == "slow":
        return float(progress**1.6)
    if change == "fast":
        return float(1.0 - (1.0 - progress) ** 1.6)
    return float(progress)


def _bpm_curve_tolerance(bpm_plan: _BpmPlan) -> float:
    span = abs(bpm_plan.target - bpm_plan.start)
    base = {"slow": 8.0, "medium": 12.0, "fast": 18.0}.get(bpm_plan.change, 12.0)
    return max(base, span / 8.0)


def _usable_bpm(value: float | None) -> float | None:
    if value is None or not np.isfinite(value):
        return None
    bpm = float(value)
    if not BPM_MIN <= bpm <= BPM_MAX:
        return None
    return bpm


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
    nearest = max(_fast_diversity_similarity(candidate, item, ranges) for item in selected)
    return _bounded(1.0 - nearest)


def _fast_diversity_similarity(candidate: _Candidate, selected: _Candidate, ranges: dict[str, tuple[float, float]]) -> float:
    embedding_score = float(np.mean([_bounded(float(candidate.vectors[key] @ selected.vectors[key])) for key in REQUIRED_EMBEDDINGS]))
    sonara_scores: list[float] = []
    for key in QUICK_DIVERSITY_FIELDS:
        value = candidate.sonara_values.get(key)
        selected_value = selected.sonara_values.get(key)
        value_range = ranges.get(key)
        if value is None or selected_value is None or value_range is None:
            continue
        normalized = _normalize(value, value_range)
        selected_normalized = _normalize(selected_value, value_range)
        if normalized is None or selected_normalized is None:
            continue
        sonara_scores.append(max(0.0, 1.0 - abs(normalized - selected_normalized)))
    sonara_score = float(np.mean(sonara_scores)) if sonara_scores else 0.5
    return _bounded(embedding_score * 0.8 + sonara_score * 0.2)


def _reason(item: _ScoredCandidate, config: SetBuilderConfig, transition: dict[str, object], classifier_flow: float) -> str:
    if item.breakdown["classifier_preference"] > 0.5:
        return "classifier_match"
    if classifier_flow > 0.75 and _uses_classifier_flow_config(config):
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
        "classifier_preference": 0.0,
        "classifier_confidence": 1.0,
        "model_disagreement": 0.0,
        "consensus": 1.0,
        "transition": float(transition["confidence"]),
        "classifier_flow": 0.5,
        "bpm_curve": 1.0,
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
        "track": replace(candidate.track, bpm=_track_bpm(candidate)),
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


def _artist_key(track: Track) -> str | None:
    artist = (track.artist or "").strip().casefold()
    return artist or None


def _artist_allowed(candidate: _Candidate, previous: _Candidate | None, artist_counts: Counter[str]) -> bool:
    artist = _artist_key(candidate.track)
    if artist is None:
        return True
    if previous is not None and _artist_key(previous.track) == artist:
        return False
    return artist_counts[artist] < ARTIST_SET_MAX_TRACKS


def _pending_seed_artists(pending_seeds: list[_Candidate]) -> set[str]:
    return {artist for seed in pending_seeds if (artist := _artist_key(seed.track)) is not None}


def _uses_pending_seed_artist(candidate: _Candidate, pending_seed_artists: set[str]) -> bool:
    artist = _artist_key(candidate.track)
    return artist is not None and artist in pending_seed_artists


def _record_artist(candidate: _Candidate, artist_counts: Counter[str]) -> None:
    artist = _artist_key(candidate.track)
    if artist is not None:
        artist_counts[artist] += 1


def _artist_pressure_score(candidate: _Candidate, remaining: list[_ScoredCandidate]) -> float:
    artist = _artist_key(candidate.track)
    if artist is None:
        return 0.0
    counts: Counter[str] = Counter()
    for item in remaining:
        item_artist = _artist_key(item.candidate.track)
        if item_artist is not None:
            counts[item_artist] += 1
    max_count = max(counts.values(), default=0)
    if max_count <= 1:
        return 0.0
    return _bounded((counts[artist] - 1) / max_count)


def _bounded(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _bounded_signed(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return max(-1.0, min(1.0, float(value)))
