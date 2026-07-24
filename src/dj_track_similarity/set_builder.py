from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Protocol

import numpy as np

from .analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
    SonaraFeatureRow,
)
from .library_models import LibrarySummary, TrackSummary
from .track_models import TrackIdentity
from .set_sequence import (
    ARTIST_SET_MAX_TRACKS,
    artist_allowed as _artist_allowed,
    artist_key as _artist_key,
    artist_pressure_score as _artist_pressure_score,
    duplicate_key as _duplicate_key,
    pending_seed_artists as _pending_seed_artists,
    record_artist as _record_artist,
    uses_pending_seed_artist as _uses_pending_seed_artist,
)
from .tempo_resolution import (
    LOW_BPM_CONFIDENCE,
    TempoEvidence,
    best_tempo_distance,
    confidence_aware_target_score,
    confidence_aware_tempo_score,
    resolve_tempo_evidence,
)
from .transition_diagnostics import TransitionTrack, structure_transition_score
from .track_resolution import (
    attenuate_harmonic_score,
    camelot_compatibility,
    resolve_track_camelot,
    resolve_track_energy,
    resolve_track_key_confidence,
)


class SetBuilderRepository(Protocol):
    def list_track_summaries(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]: ...

    def library_summary(self) -> LibrarySummary: ...

    def get_track_identities(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> dict[int, TrackIdentity]: ...

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None: ...

    def load_analysis_vectors(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[AnalysisVectorRow, ...]: ...

    def load_sonara_feature_rows(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[SonaraFeatureRow, ...]: ...


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


def _required_embedding_outputs(
    outputs: Mapping[str, AnalysisOutput],
    families: Sequence[str],
) -> dict[str, AnalysisOutput]:
    selected: dict[str, AnalysisOutput] = {}
    for family in families:
        output = outputs.get(family)
        if not isinstance(output, AnalysisOutput):
            raise ValueError(
                f"analysis_outputs must include current {family}/embedding"
            )
        if output.key != (family, "embedding"):
            raise ValueError(
                "analysis_outputs contains the wrong output identity for "
                f"{family!r}: {output.key!r}"
            )
        selected[family] = output
    return selected


def _require_current_embedding_output(
    repository: SetBuilderRepository,
    family: str,
    expected: AnalysisOutput,
) -> AnalysisOutput:
    active = repository.active_analysis_output(family, "embedding")
    if active is None:
        raise RuntimeError(
            f"No active {family!r} embedding contract; reanalysis is required"
        )
    if (
        active.contract_hash != expected.contract_hash
        or active.contract.canonical_payload_json
        != expected.contract.canonical_payload_json
    ):
        raise RuntimeError(
            "Current runtime embedding contract does not match the active "
            f"{family!r} contract; reanalysis is required before SET building"
        )
    return expected
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
    track: TrackSummary
    sonara_features: dict[str, object]
    sonara_values: dict[str, float]
    text_values: dict[str, str]
    duplicate_key: str
    identity: TrackIdentity | None = None
    sonara: SonaraFeatureRow | None = None


@dataclass(frozen=True)
class _Candidate:
    track: TrackSummary
    vectors: dict[str, np.ndarray]
    sonara_features: dict[str, object]
    sonara_values: dict[str, float]
    text_values: dict[str, str]
    duplicate_key: str
    identity: TrackIdentity | None = None
    sonara: SonaraFeatureRow | None = None


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
    def __init__(
        self,
        db: SetBuilderRepository,
        *,
        analysis_outputs: Mapping[str, AnalysisOutput],
    ) -> None:
        self.db = db
        self.analysis_outputs = _required_embedding_outputs(
            analysis_outputs,
            REQUIRED_EMBEDDINGS,
        )
        self._summary_by_id: dict[int, TrackSummary] = {}
        self._embedding_maps: dict[str, dict[int, np.ndarray]] = {
            key: {} for key in REQUIRED_EMBEDDINGS
        }

    def generate(self, config: SetBuilderConfig) -> dict[str, object]:
        cleaned = _clean_config(config)
        rng = _random_generator(cleaned.random_seed)
        manual_seed_ids = (
            _manual_seed_ids(cleaned.seed_track_ids)
            if cleaned.seed_mode == "manual"
            else []
        )
        light_candidates, coverage = self._load_light_candidates(cleaned)

        light_by_id = {
            candidate.track.track_id: candidate for candidate in light_candidates
        }
        if cleaned.seed_mode == "manual":
            seed_ids = manual_seed_ids
            self._validate_manual_seeds(seed_ids, light_by_id)
            seed_light_candidates = [light_by_id[track_id] for track_id in seed_ids]
            prefiltered, _sonara_centrality = _prefilter_light_candidates(
                light_candidates, seed_light_candidates, cleaned
            )
            hydrate_ids = _ordered_unique(
                [
                    *seed_ids,
                    *(candidate.track.track_id for candidate in prefiltered),
                ]
            )
        else:
            if not light_candidates:
                raise ValueError(
                    "No feature-complete tracks are available for Smart Set Builder"
                )
            auto_start_plan = _bpm_plan(cleaned, light_candidates, [])
            first_seed_light = _select_auto_start_candidate(
                light_candidates, cleaned, rng, auto_start_plan
            )
            prefiltered, _sonara_centrality = _prefilter_light_candidates(
                light_candidates, [first_seed_light], cleaned
            )
            seed_ids = [first_seed_light.track.track_id]
            hydrate_ids = _ordered_unique(
                [
                    first_seed_light.track.track_id,
                    *(candidate.track.track_id for candidate in prefiltered),
                ]
            )
        candidates = self._hydrate_candidates(
            [
                light_by_id[track_id]
                for track_id in hydrate_ids
                if track_id in light_by_id
            ]
        )
        candidate_by_id = {
            candidate.track.track_id: candidate for candidate in candidates
        }
        if cleaned.seed_mode == "auto":
            if not candidates:
                raise ValueError(
                    "No feature-complete tracks are available for Smart Set Builder"
                )
            initial_seeds = [
                candidate_by_id[track_id]
                for track_id in seed_ids
                if track_id in candidate_by_id
            ]
            auto_bpm_plan = _bpm_plan(cleaned, candidates, initial_seeds)
            seed_ids = self._auto_seed_ids(
                candidates,
                cleaned,
                rng,
                bpm_plan=auto_bpm_plan,
                initial_seeds=initial_seeds,
            )
        missing_hydrated_seeds = [
            track_id for track_id in seed_ids if track_id not in candidate_by_id
        ]
        if missing_hydrated_seeds:
            raise ValueError(
                f"Seed tracks missing required analysis: {missing_hydrated_seeds}"
            )
        seeds = [candidate_by_id[track_id] for track_id in seed_ids]
        bpm_plan = _bpm_plan(cleaned, candidates, seeds)

        ranges = _numeric_ranges(candidates)
        context = _build_context(seeds, ranges)
        scored = [
            self._score_candidate(candidate, context, cleaned)
            for candidate in candidates
            if candidate.track.track_id not in seed_ids
        ]
        scored = [item for item in scored if item is not None]
        ordered_items = self._ordered_items(
            seeds, scored, cleaned, ranges, rng, bpm_plan
        )

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

    def _load_light_candidates(
        self,
        _config: SetBuilderConfig | None = None,
    ) -> tuple[list[_LightCandidate], dict[str, int]]:
        summary = self.db.library_summary()
        summaries = self.db.list_track_summaries(include_missing=False)
        self._summary_by_id = {track.track_id: track for track in summaries}
        identities = self.db.get_track_identities(
            tuple(self._summary_by_id),
            include_missing=False,
        )
        missing_identities = sorted(set(self._summary_by_id) - set(identities))
        if missing_identities:
            raise RuntimeError(
                "library repository omitted current track identities: "
                f"{missing_identities}"
            )
        _require_one_catalog(tuple(identities.values()))

        sonara_output = self.db.active_analysis_output("sonara", "core")
        sonara_rows = (
            self.db.load_sonara_feature_rows(sonara_output)
            if sonara_output is not None
            else ()
        )
        sonara_by_id = _validated_sonara_rows(
            sonara_rows,
            self._summary_by_id,
            identities,
            expected_output=sonara_output,
        )

        embedding_maps: dict[str, dict[int, np.ndarray]] = {}
        all_targets: list[AnalysisTarget] = [row.target for row in sonara_rows]
        for family in REQUIRED_EMBEDDINGS:
            output = _require_current_embedding_output(
                self.db,
                family,
                self.analysis_outputs[family],
            )
            rows = self.db.load_analysis_vectors(output)
            embedding_maps[family] = _validated_vector_rows(
                rows,
                self._summary_by_id,
                identities,
                expected_output=output,
            )
            all_targets.extend(row.target for row in rows)
        _require_one_catalog(all_targets)
        self._embedding_maps = embedding_maps

        candidates: list[_LightCandidate] = []
        for track in summaries:
            track_id = track.track_id
            sonara = sonara_by_id.get(track_id)
            if sonara is None or any(
                track_id not in embedding_maps[family] for family in REQUIRED_EMBEDDINGS
            ):
                continue
            sonara_features = _sonara_features_from_row(sonara)
            values, text_values = _sonara_values(sonara_features)
            candidates.append(
                _LightCandidate(
                    track=track,
                    sonara_features=sonara_features,
                    sonara_values=values,
                    text_values=text_values,
                    duplicate_key=_duplicate_key(track),
                    identity=identities[track_id],
                    sonara=sonara,
                )
            )

        coverage = {
            "tracks": int(summary.tracks),
            "eligible_tracks": len(candidates),
            "missing_mert": max(0, int(summary.tracks) - int(summary.mert)),
            "missing_maest": max(
                0,
                int(summary.tracks) - int(summary.maest_embedding),
            ),
            "missing_clap": max(0, int(summary.tracks) - int(summary.clap)),
            "missing_sonara": max(
                0,
                int(summary.tracks) - int(summary.sonara),
            ),
        }
        return candidates, coverage

    def _hydrate_candidates(
        self, light_candidates: list[_LightCandidate]
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        for light in light_candidates:
            track_id = light.track.track_id
            if not all(
                track_id in self._embedding_maps[key] for key in REQUIRED_EMBEDDINGS
            ):
                continue
            candidates.append(
                _Candidate(
                    track=light.track,
                    vectors={
                        key: self._embedding_maps[key][track_id]
                        for key in REQUIRED_EMBEDDINGS
                    },
                    sonara_features=light.sonara_features,
                    sonara_values=light.sonara_values,
                    text_values=light.text_values,
                    duplicate_key=light.duplicate_key,
                    identity=light.identity,
                    sonara=light.sonara,
                )
            )
        return candidates

    def _validate_manual_seeds(
        self, seed_ids: list[int], candidate_by_id: dict[int, _LightCandidate]
    ) -> None:
        missing = [track_id for track_id in seed_ids if track_id not in candidate_by_id]
        if not missing:
            return
        unknown: list[int] = []
        missing_analysis: list[int] = []
        for track_id in missing:
            if track_id not in self._summary_by_id:
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
            raise ValueError(
                f"Auto seed mode requires at least {count} feature-complete tracks"
            )
        initial_seed_list = list(initial_seeds or [])
        if len(initial_seed_list) >= count:
            return [seed.track.track_id for seed in initial_seed_list[:count]]
        ranges = _numeric_ranges(candidates)
        anchor_positions = _anchor_positions(config.limit, count)
        target_count = max(config.limit, count)
        if sonara_centrality is None:
            sonara_centrality = _global_sonara_centrality_scores(candidates, ranges)
        embedding_centroids = _embedding_centroids(candidates)
        centrality = [
            (
                candidate,
                _auto_anchor_centrality(
                    candidate, sonara_centrality, embedding_centroids
                ),
            )
            for candidate in candidates
        ]
        centrality.sort(
            key=lambda item: (
                -item[1],
                item[0].track.artist or "",
                item[0].track.title or "",
                item[0].track.file_path,
            )
        )
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
                    if not _artist_allowed(
                        candidate, seeds[-1] if seeds else None, artist_counts
                    ):
                        continue
                    if (
                        not allow_near_duplicate
                        and seeds
                        and max(
                            _fast_diversity_similarity(candidate, seed, ranges)
                            for seed in seeds
                        )
                        > 0.995
                    ):
                        continue
                    score = _auto_anchor_selection_score(
                        candidate, centrality_score, seeds, ranges, config.mode
                    )
                    anchor_position = (
                        anchor_positions[len(seeds)]
                        if len(seeds) < len(anchor_positions)
                        else len(seeds)
                    )
                    if bpm_plan is not None:
                        bpm_score = _bpm_curve_score(
                            candidate, bpm_plan, anchor_position, target_count
                        )
                        score = score * 0.45 + bpm_score * 0.55
                    score = _auto_anchor_classifier_adjusted_score(
                        candidate, score, config, anchor_position, target_count
                    )
                    scored_options.append((candidate, score))
                if scored_options or not seeds:
                    break
            if not scored_options:
                break
            selected = _sample_scored_candidate(
                scored_options,
                rng,
                mode=config.mode,
                pool_size=_auto_anchor_sample_pool_size(
                    config.mode, count, len(scored_options)
                ),
                force_sample=True,
            )
            seeds.append(selected)
            seen_keys.add(selected.duplicate_key)
            _record_artist(selected, artist_counts)
        if len(seeds) < count:
            raise ValueError(
                f"Auto seed mode could not choose {count} artist-diverse anchors"
            )
        return [candidate.track.track_id for candidate in seeds]

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
        classifier_preference, classifier_confidence = _classifier_modifiers(
            candidate.track, config
        )
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

        seed_artist_counts = Counter(
            artist
            for artist in (_artist_key(seed.track) for seed in seeds)
            if artist is not None
        )
        if any(count > ARTIST_SET_MAX_TRACKS for count in seed_artist_counts.values()):
            raise ValueError(
                "Seed tracks violate artist spacing limits: use at most 1 track per known artist"
            )

        seed_duplicates = {seed.duplicate_key for seed in seeds}
        pending_seeds = list(seeds)
        scored_pool = _sequence_candidate_pool(
            scored_candidates, config.limit, len(seeds)
        )
        remaining = [
            item
            for item in scored_pool
            if item.candidate.duplicate_key not in seed_duplicates
        ]
        selected_sequence: list[_Candidate] = []
        target_count = max(config.limit, len(seeds))

        while len(items) < config.limit and (pending_seeds or remaining):
            position = len(items)
            if (
                pending_seeds
                and next_seed_index < len(anchor_positions)
                and position >= anchor_positions[next_seed_index]
            ):
                seed = pending_seeds.pop(0)
                if not _artist_allowed(seed, previous, artist_counts):
                    raise ValueError(
                        "Seed tracks violate artist spacing limits: use at most 1 track per known artist"
                    )
                transition = _transition(previous, seed)
                items.append(
                    _item(
                        seed,
                        "seed_anchor",
                        1.0,
                        _seed_breakdown(transition),
                        {},
                        transition,
                    )
                )
                previous = seed
                selected_sequence.append(seed)
                seen_duplicates.add(seed.duplicate_key)
                _record_artist(seed, artist_counts)
                next_seed_index += 1
                remaining = [
                    item
                    for item in remaining
                    if item.candidate.duplicate_key not in seen_duplicates
                ]
                continue

            pending_seed_artists = _pending_seed_artists(pending_seeds)
            valid_remaining = [
                item
                for item in remaining
                if _artist_allowed(item.candidate, previous, artist_counts)
                and not _uses_pending_seed_artist(item.candidate, pending_seed_artists)
            ]
            if not valid_remaining:
                if pending_seeds:
                    seed = pending_seeds.pop(0)
                    if not _artist_allowed(seed, previous, artist_counts):
                        raise ValueError(
                            "Seed tracks violate artist spacing limits: use at most 1 track per known artist"
                        )
                    transition = _transition(previous, seed)
                    items.append(
                        _item(
                            seed,
                            "seed_anchor",
                            1.0,
                            _seed_breakdown(transition),
                            {},
                            transition,
                        )
                    )
                    previous = seed
                    selected_sequence.append(seed)
                    seen_duplicates.add(seed.duplicate_key)
                    _record_artist(seed, artist_counts)
                    next_seed_index += 1
                    remaining = [
                        item
                        for item in remaining
                        if item.candidate.duplicate_key not in seen_duplicates
                    ]
                    continue
                break
            sequence_options = [
                (
                    item,
                    self._sequence_score(
                        item,
                        previous,
                        selected_sequence,
                        position,
                        target_count,
                        config,
                        ranges,
                        bpm_plan,
                    )
                    + _artist_pressure_score(item.candidate, remaining)
                    * ARTIST_PRESSURE_WEIGHT,
                )
                for item in valid_remaining
            ]
            selected, final_score = _sample_scored_item(
                sequence_options,
                rng,
                mode=config.mode,
                pool_size=_sequence_sample_pool_size(
                    config.mode, len(sequence_options)
                ),
            )
            transition = _transition(previous, selected.candidate)
            flow_score = _classifier_flow_score(
                selected.candidate.track, config, position, target_count
            )
            bpm_curve_score = _bpm_curve_score(
                selected.candidate, bpm_plan, position, target_count
            )
            diversity_score = _diversity_score(
                selected.candidate, selected_sequence, ranges
            )
            breakdown = dict(selected.breakdown)
            breakdown["transition"] = transition["confidence"]
            breakdown["classifier_flow"] = flow_score
            breakdown["bpm_curve"] = bpm_curve_score
            breakdown["diversity"] = diversity_score
            reason = _reason(selected, config, transition, flow_score)
            items.append(
                _item(
                    selected.candidate,
                    reason,
                    final_score,
                    breakdown,
                    selected.sonara_groups,
                    transition,
                )
            )
            previous = selected.candidate
            selected_sequence.append(selected.candidate)
            seen_duplicates.add(selected.candidate.duplicate_key)
            _record_artist(selected.candidate, artist_counts)
            remaining = [
                item
                for item in remaining
                if item.candidate.duplicate_key not in seen_duplicates
            ]
        if pending_seeds:
            raise ValueError(
                "Seed tracks violate artist spacing limits: use at most 1 track per known artist"
            )
        public_items: list[dict[str, object]] = []
        for index, item in enumerate(items, start=1):
            public_item = {
                key: value for key, value in item.items() if key != "candidate"
            }
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
        curve_score = _energy_curve_score(
            item.candidate, config.energy_curve, position, target_count
        )
        classifier_flow = _classifier_flow_score(
            item.candidate.track, config, position, target_count
        )
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


def _build_context(
    seeds: list[_Candidate], ranges: dict[str, tuple[float, float]]
) -> _Context:
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
        seed_track_ids=list(
            dict.fromkeys(int(track_id) for track_id in config.seed_track_ids)
        ),
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
    cleaned = _finite_float(value)
    if cleaned is None:
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
    return any(
        config.classifier_flows.get(key, "flat") != "flat"
        for key in config.classifier_preferences
    )


def _ordered_unique(values: list[int]) -> list[int]:
    return list(dict.fromkeys(int(value) for value in values))


_V7_BLOB_FIELDS = (
    ("mfcc_mean_blob", 13, "mfcc_mean"),
    ("chroma_mean_blob", 12, "chroma_mean"),
    ("spectral_contrast_mean_blob", 7, "spectral_contrast_mean"),
)


def _short_vector_statistics(
    values: Mapping[str, object],
) -> dict[str, float]:
    result: dict[str, float] = {}
    for field_name, dimension, prefix in _V7_BLOB_FIELDS:
        raw = values.get(field_name)
        if isinstance(raw, bytes):
            vector = np.frombuffer(raw, dtype="<f4")
        elif isinstance(raw, (tuple, list, np.ndarray)):
            vector = np.asarray(raw, dtype="<f4")
        else:
            continue
        if vector.shape != (dimension,) or not bool(np.all(np.isfinite(vector))):
            continue
        if prefix == "spectral_contrast_mean":
            result[prefix] = float(np.mean(vector))
            continue
        result[f"{prefix}.summary.min"] = float(np.min(vector))
        result[f"{prefix}.summary.max"] = float(np.max(vector))
        result[f"{prefix}.summary.mean"] = float(np.mean(vector))
        result[f"{prefix}.summary.std"] = float(np.std(vector))
    return result


def _validated_sonara_rows(
    rows: Sequence[SonaraFeatureRow],
    summaries: Mapping[int, TrackSummary],
    identities: Mapping[int, TrackIdentity],
    *,
    expected_output: AnalysisOutput | None,
) -> dict[int, SonaraFeatureRow]:
    result: dict[int, SonaraFeatureRow] = {}
    for row in rows:
        summary = summaries.get(row.target.track_id)
        if summary is None:
            raise RuntimeError(
                "analysis repository returned a SONARA row without a "
                "current library summary"
            )
        _require_matching_target(
            row.target,
            identities[summary.track_id],
            summary,
        )
        if expected_output is None or row.output != expected_output:
            raise RuntimeError(
                "analysis repository returned SONARA data for the wrong contract"
            )
        result[summary.track_id] = row
    return result


def _validated_vector_rows(
    rows: Sequence[AnalysisVectorRow],
    summaries: Mapping[int, TrackSummary],
    identities: Mapping[int, TrackIdentity],
    *,
    expected_output: AnalysisOutput | None,
) -> dict[int, np.ndarray]:
    result: dict[int, np.ndarray] = {}
    for row in rows:
        summary = summaries.get(row.target.track_id)
        if summary is None:
            raise RuntimeError(
                "analysis repository returned a vector without a current "
                "library summary"
            )
        _require_matching_target(
            row.target,
            identities[summary.track_id],
            summary,
        )
        if expected_output is None or row.output != expected_output:
            raise RuntimeError(
                "analysis repository returned a vector for the wrong contract"
            )
        track_id = row.target.track_id
        if track_id in result:
            raise RuntimeError(
                "analysis repository returned duplicate embedding rows for one track"
            )
        vector = np.asarray(row.vector, dtype=np.float32)
        if vector.shape != (expected_output.contract.dim,):
            raise RuntimeError(
                "analysis repository returned an embedding vector with a "
                "dimension that does not match the active contract"
            )
        if not bool(np.all(np.isfinite(vector))):
            raise RuntimeError(
                "analysis repository returned an invalid embedding vector"
            )
        if expected_output.contract.normalization == "l2":
            norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
            if not math.isfinite(norm) or not np.isclose(
                norm,
                1.0,
                rtol=1e-4,
                atol=1e-5,
            ):
                raise RuntimeError(
                    "analysis repository returned an L2 embedding vector "
                    "that is not unit-normalized"
                )
        result[track_id] = vector
    return result


def _require_matching_target(
    target: AnalysisTarget,
    identity: TrackIdentity,
    summary: TrackSummary,
) -> None:
    if (
        identity.catalog_uuid != summary.catalog_uuid
        or identity.track_id != summary.track_id
        or identity.track_uuid != summary.track_uuid
        or identity.content_generation != summary.content_generation
        or target.catalog_uuid != identity.catalog_uuid
        or target.track_id != identity.track_id
        or target.track_uuid != identity.track_uuid
        or target.content_generation != identity.content_generation
    ):
        raise RuntimeError("analysis target does not match the current track identity")


def _require_one_catalog(
    targets: Sequence[AnalysisTarget | TrackIdentity],
) -> None:
    catalogs = {target.catalog_uuid for target in targets}
    if len(catalogs) > 1:
        raise RuntimeError(
            "analysis repository returned rows from multiple library catalogs"
        )


_SONARA_SCALAR_FEATURES: Mapping[str, str] = {
    "bpm": "detected_bpm",
    "n_beats": "beat_count",
    "onset_density": "onset_density_per_second",
    "rms_mean": "rms_mean",
    "rms_max": "rms_max",
    "loudness_lufs": "integrated_loudness_lufs",
    "dynamic_range_db": "dynamic_range_db",
    "energy": "energy_score",
    "danceability": "danceability_score",
    "valence": "valence_score",
    "acousticness": "acousticness_score",
    "chord_change_rate": "chord_changes_per_second",
    "dissonance": "dissonance_score",
    "spectral_centroid_mean": "spectral_centroid_hz",
    "spectral_bandwidth_mean": "spectral_bandwidth_hz",
    "spectral_rolloff_mean": "spectral_rolloff_hz",
    "spectral_flatness_mean": "spectral_flatness",
    "zero_crossing_rate": "zero_crossing_rate",
    "bpm_confidence": "bpm_confidence",
    "grid_stability": "beat_grid_stability",
    "key_confidence": "key_confidence",
    "duration_sec": "analyzed_duration_seconds",
    "intro_end_sec": "intro_end_seconds",
    "outro_start_sec": "outro_start_seconds",
    "energy_level": "energy_level",
}
_SONARA_TEXT_FEATURES: Mapping[str, str] = {
    "predominant_chord": "predominant_chord",
    "key": "detected_key_name",
    "key_camelot": "detected_key_camelot",
}


def _sonara_features_from_row(
    row: SonaraFeatureRow,
) -> dict[str, object]:
    source = row.values
    features: dict[str, object] = {}
    for feature_name, column_name in _SONARA_SCALAR_FEATURES.items():
        value = source.get(column_name)
        if _finite_float(value) is not None:
            features[feature_name] = value
    for feature_name, column_name in _SONARA_TEXT_FEATURES.items():
        if (value := _text(source.get(column_name))) is not None:
            features[feature_name] = value

    for field_name in ("mfcc_mean_blob", "chroma_mean_blob"):
        value = source.get(field_name)
        if isinstance(value, (tuple, list)):
            vector = tuple(
                number for item in value if (number := _finite_float(item)) is not None
            )
            expected = 13 if field_name == "mfcc_mean_blob" else 12
            if len(vector) == expected:
                name = field_name.removesuffix("_blob")
                array = np.asarray(vector, dtype=np.float32)
                features[name] = {
                    "value": vector,
                    "summary": {
                        "min": float(np.min(array)),
                        "max": float(np.max(array)),
                        "mean": float(np.mean(array)),
                        "std": float(np.std(array)),
                    },
                }
    features.update(_short_vector_statistics(source))

    raw_candidates = source.get("bpm_candidates_json")
    if isinstance(raw_candidates, str):
        try:
            parsed = json.loads(raw_candidates)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            features["bpm_candidates"] = parsed
    return features


def _prefilter_light_candidates(
    candidates: list[_LightCandidate],
    seed_candidates: list[_LightCandidate],
    config: SetBuilderConfig,
) -> tuple[list[_LightCandidate], dict[int, float]]:
    if not candidates:
        return [], {}

    seed_ids = {candidate.track.track_id for candidate in seed_candidates}
    available = [
        candidate
        for candidate in candidates
        if candidate.track.track_id not in seed_ids
    ]
    if not available:
        return [], {}

    pool_size = min(
        len(available),
        max(
            PREFILTER_POOL_MIN,
            max(config.limit, config.auto_seed_count) * PREFILTER_POOL_FACTOR,
        ),
        PREFILTER_POOL_MAX,
    )
    ranges = _numeric_ranges(candidates)
    sonara_centrality: dict[int, float] = {}

    if seed_candidates:
        seed_centroid = _sonara_centroid(seed_candidates, ranges)
        chord_context = _text_context(seed_candidates, "predominant_chord")
        seed_scores = _sonara_similarity_scores_to_centroid(
            available,
            ranges,
            seed_centroid,
            chord_context,
            tempo_context=seed_candidates,
        )

        def sonara_score(candidate: _LightCandidate) -> float:
            return seed_scores.get(candidate.track.track_id, 0.0)

    else:
        sonara_centrality = _global_sonara_centrality_scores(candidates, ranges)

        def sonara_score(candidate: _LightCandidate) -> float:
            return sonara_centrality.get(candidate.track.track_id, 0.0)

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
            item[1].track.file_path,
        )
    )

    return _select_light_pool(scored, pool_size), sonara_centrality


def _select_light_pool(
    scored: list[tuple[float, _LightCandidate]], pool_size: int
) -> list[_LightCandidate]:
    selected: list[_LightCandidate] = []
    seen_duplicates: set[str] = set()
    artist_counts: Counter[str] = Counter()
    per_artist_limit = max(
        ARTIST_SET_MAX_TRACKS * PREFILTER_ARTIST_POOL_MULTIPLIER, pool_size // 20
    )
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


def _sonara_values(
    features: dict[str, object],
) -> tuple[dict[str, float], dict[str, str]]:
    values: dict[str, float] = {}
    for key in SONARA_NUMERIC_FIELDS:
        number = _feature_number(features, key)
        if number is not None:
            values[key] = number
    text_values: dict[str, str] = {}
    for key in ("predominant_chord",):
        value = _text(features.get(key))
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
    if isinstance(value, Mapping) and "value" in value:
        value = value.get("value")
    return _finite_float(value)


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


def _sonara_similarity(
    candidate: _Candidate, context: _Context
) -> tuple[float | None, dict[str, float]]:
    seed_centroid = context.sonara_centroid or _sonara_centroid(
        context.seeds, context.ranges
    )
    chord_context = context.chord_context or _text_context(
        context.seeds, "predominant_chord"
    )
    return _sonara_similarity_to_centroid(
        candidate,
        context.ranges,
        seed_centroid,
        chord_context,
        tempo_context=context.seeds,
    )


def _global_sonara_centrality_scores(
    candidates: list[_LightCandidate] | list[_Candidate],
    ranges: dict[str, tuple[float, float]],
) -> dict[int, float]:
    seed_centroid = _sonara_centroid(candidates, ranges)
    chord_context = _text_context(candidates, "predominant_chord")
    return _sonara_similarity_scores_to_centroid(
        candidates, ranges, seed_centroid, chord_context
    )


def _sonara_similarity_scores_to_centroid(
    candidates: list[_LightCandidate] | list[_Candidate],
    ranges: dict[str, tuple[float, float]],
    seed_centroid: dict[str, float],
    chord_context: set[str],
    *,
    tempo_context: list[_LightCandidate] | list[_Candidate] | None = None,
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
        if key == "bpm":
            if not tempo_context:
                # Global auto-centrality must stay O(N), and confidence is not a similarity
                # dimension. Seeded paths pass their small context explicitly for pairwise tempo.
                continue
            raw_scores = np.array(
                [
                    score
                    if (
                        score := _tempo_similarity_for_candidate(
                            candidate, tempo_context
                        )
                    )
                    is not None
                    else np.nan
                    for candidate in candidates
                ],
                dtype=np.float32,
            )
            mask = np.isfinite(raw_scores)
            if not np.any(mask):
                continue
            scores = np.zeros(len(candidates), dtype=np.float32)
            scores[mask] = raw_scores[mask]
            group, weight = SONARA_NUMERIC_FIELDS[key]
            group_score_sums[group] += scores * weight
            group_weight_sums[group][mask] += weight
            continue
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
        scores[candidate.track.track_id] = (
            _bounded(float(weighted_total[index] / weight_total[index]))
            if mask[index]
            else 0.0
        )
    return scores


def _sonara_similarity_to_centroid(
    candidate: _Candidate,
    ranges: dict[str, tuple[float, float]],
    seed_centroid: dict[str, float],
    chord_context: set[str],
    *,
    tempo_context: list[_Candidate] | None = None,
) -> tuple[float | None, dict[str, float]]:
    group_scores: dict[str, list[tuple[float, float]]] = {
        group: [] for group in SONARA_GROUP_WEIGHTS
    }
    for key, value in candidate.sonara_values.items():
        if key not in seed_centroid or key not in ranges:
            continue
        group, weight = SONARA_NUMERIC_FIELDS[key]
        if key == "bpm":
            score = _tempo_similarity_for_candidate(candidate, tempo_context or [])
            if score is None:
                continue
        else:
            normalized = _normalize(value, ranges[key])
            if normalized is None:
                continue
            score = max(0.0, 1.0 - abs(normalized - seed_centroid[key]))
        group_scores[group].append((score, weight))

    candidate_chord = candidate.text_values.get("predominant_chord")
    if chord_context and candidate_chord:
        group_scores["tonal"].append(
            (1.0 if candidate_chord in chord_context else 0.0, 0.35)
        )

    collapsed: dict[str, float] = {}
    weighted_total = 0.0
    weight_total = 0.0
    for group, values in group_scores.items():
        if not values:
            continue
        group_score = sum(score * weight for score, weight in values) / sum(
            weight for _score, weight in values
        )
        collapsed[group] = _bounded(group_score)
        group_weight = SONARA_GROUP_WEIGHTS[group]
        weighted_total += collapsed[group] * group_weight
        weight_total += group_weight
    if weight_total <= 0:
        return None, {}
    return _bounded(weighted_total / weight_total), collapsed


def _sonara_centroid(
    seeds: list[_LightCandidate] | list[_Candidate],
    ranges: dict[str, tuple[float, float]],
) -> dict[str, float]:
    centroid: dict[str, float] = {}
    for key in ranges:
        values = [
            normalized
            for seed in seeds
            if key in seed.sonara_values
            if (normalized := _normalize(seed.sonara_values[key], ranges[key]))
            is not None
        ]
        if values:
            centroid[key] = float(np.mean(values))
    return centroid


def _tempo_similarity_for_candidate(
    candidate: _LightCandidate | _Candidate,
    references: list[_LightCandidate] | list[_Candidate],
) -> float | None:
    candidate_tempo = _tempo_evidence(candidate)
    scores: list[float] = []
    for reference in references:
        score = confidence_aware_tempo_score(
            candidate_tempo, _tempo_evidence(reference)
        )
        if score is not None:
            scores.append(score)
    return float(np.mean(scores)) if scores else None


def _text_context(
    seeds: list[_LightCandidate] | list[_Candidate], key: str
) -> set[str]:
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
    sonara_score = sonara_centrality.get(candidate.track.track_id, 0.0)
    return _bounded(embedding_score * 0.7 + sonara_score * 0.3)


def _select_auto_start_candidate(
    candidates: list[_LightCandidate],
    config: SetBuilderConfig,
    rng: np.random.Generator,
    bpm_plan: _BpmPlan | None,
) -> _LightCandidate:
    scored = [
        (candidate, _auto_start_selection_score(candidate, config, bpm_plan))
        for candidate in candidates
    ]
    index = _sample_ranked_index(
        [score for _candidate, score in scored],
        rng,
        mode=config.mode,
        force_sample=True,
    )
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
        bpm_score = _bpm_curve_score(
            candidate, bpm_plan, 0, max(config.limit, config.auto_seed_count)
        )
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
    relatedness = max(
        _fast_diversity_similarity(candidate, seed, ranges) for seed in selected
    )
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
            item[0].track.file_path,
        ),
    )[: max(1, pool_size)]
    index = _sample_ranked_index(
        [score for _candidate, score in ranked],
        rng,
        mode=mode,
        force_sample=force_sample,
    )
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
            item[0].candidate.track.file_path,
        ),
    )[: max(1, pool_size)]
    index = _sample_ranked_index(
        [score for _item, score in ranked], rng, mode=mode, force_sample=False
    )
    return ranked[index]


def _sample_ranked_index(
    scores: list[float], rng: np.random.Generator, *, mode: str, force_sample: bool
) -> int:
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


def _sequence_candidate_pool(
    scored_candidates: list[_ScoredCandidate], limit: int, seed_count: int
) -> list[_ScoredCandidate]:
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
            item.candidate.track.file_path,
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
    return [
        int(round(index * last_position / (seed_count - 1)))
        for index in range(seed_count)
    ]


def _select_scored_pool(
    scored: list[_ScoredCandidate], pool_size: int
) -> list[_ScoredCandidate]:
    selected: list[_ScoredCandidate] = []
    artist_counts: Counter[str] = Counter()
    per_artist_limit = max(
        ARTIST_SET_MAX_TRACKS * SEQUENCE_ARTIST_POOL_MULTIPLIER, pool_size // 20
    )
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


def _classifier_modifiers(
    track: TrackSummary,
    config: SetBuilderConfig,
) -> tuple[float, float]:
    used_keys = set(config.classifier_preferences)
    if not used_keys:
        return 0.0, 1.0
    scores = _classifier_scores(track)
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


def _classifier_flow_score(
    track: TrackSummary,
    config: SetBuilderConfig,
    position: int,
    target_count: int,
) -> float:
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


def _classifier_scores(track: TrackSummary) -> dict[str, float]:
    return {
        score.classifier_key: _bounded(score.score) for score in track.classifier_scores
    }


def _energy_curve_score(
    candidate: _Candidate, curve: str, position: int, target_count: int
) -> float:
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
    value = resolve_track_energy(
        _candidate_identity(candidate),
        candidate.track,
        candidate.sonara,
    )
    return _bounded(value) if value is not None else None


def _bpm_plan(
    config: SetBuilderConfig, candidates: list[_Candidate], seeds: list[_Candidate]
) -> _BpmPlan | None:
    if config.bpm_mode == "general":
        return None
    bpms = [
        bpm
        for candidate in candidates
        if (bpm := _reliable_track_bpm(candidate)) is not None
    ]
    if not bpms:
        return None
    seed_bpm = _reliable_track_bpm(seeds[0]) if seeds else None
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
    return _BpmPlan(
        mode=config.bpm_mode,
        change=config.bpm_change,
        start=float(start),
        target=float(target),
    )


def _first_bpm(*values: float | None) -> float:
    for value in values:
        if value is not None:
            return float(value)
    raise ValueError("No BPM value available")


def _bpm_curve_weight(mode: str, bpm_plan: _BpmPlan | None) -> float:
    if bpm_plan is None:
        return 0.0
    return BPM_CURVE_WEIGHTS.get(mode, 0.14)


def _bpm_curve_score(
    candidate: _Candidate, bpm_plan: _BpmPlan | None, position: int, target_count: int
) -> float:
    if bpm_plan is None:
        return 0.5
    desired = _bpm_curve_target(bpm_plan, position, target_count)
    tolerance = _bpm_curve_tolerance(bpm_plan)
    score = confidence_aware_target_score(
        _tempo_evidence(candidate), desired, tolerance
    )
    return 0.5 if score is None else score


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


def _transition(
    previous: _Candidate | None, candidate: _Candidate
) -> dict[str, object]:
    if previous is None:
        return {
            "from_track_id": None,
            "bpm_delta": None,
            "key_relation": "anchor",
            "confidence": 1.0,
        }
    candidate_tempo = _tempo_evidence(candidate)
    previous_tempo = _tempo_evidence(previous)
    bpm_delta = _tempo_evidence_distance(candidate_tempo, previous_tempo)
    bpm_score = confidence_aware_tempo_score(candidate_tempo, previous_tempo)
    if bpm_score is None:
        bpm_score = 0.5
    key_relation, key_score = _key_relation(
        _track_key(candidate),
        _track_key(previous),
        _track_key_confidence(candidate),
        _track_key_confidence(previous),
    )
    structure_score = structure_transition_score(
        TransitionTrack(
            _candidate_identity(previous),
            previous.track,
            previous.sonara,
        ),
        TransitionTrack(
            _candidate_identity(candidate),
            candidate.track,
            candidate.sonara,
        ),
    )
    if structure_score is None:
        confidence = _bounded(bpm_score * 0.6 + key_score * 0.4)
    else:
        confidence = _bounded(bpm_score * 0.5 + key_score * 0.3 + structure_score * 0.2)
    return {
        "from_track_id": previous.track.track_id,
        "bpm_delta": bpm_delta,
        "key_relation": key_relation,
        "structure_score": structure_score,
        "confidence": confidence,
    }


def _track_bpm(candidate: _Candidate) -> float | None:
    return _tempo_evidence(candidate).bpm


def _tempo_evidence(candidate: _LightCandidate | _Candidate) -> TempoEvidence:
    return resolve_tempo_evidence(
        _candidate_identity(candidate),
        candidate.track,
        candidate.sonara,
    )


def _reliable_track_bpm(candidate: _LightCandidate | _Candidate) -> float | None:
    evidence = _tempo_evidence(candidate)
    if evidence.reliability < LOW_BPM_CONFIDENCE:
        return None
    return _usable_bpm(evidence.bpm)


def _track_key(candidate: _Candidate) -> str | None:
    return resolve_track_camelot(
        _candidate_identity(candidate),
        candidate.track,
        candidate.sonara,
    )


def _track_key_confidence(candidate: _Candidate) -> float | None:
    return resolve_track_key_confidence(
        _candidate_identity(candidate),
        candidate.track,
        candidate.sonara,
    )


def _tempo_evidence_distance(
    candidate: TempoEvidence, previous: TempoEvidence
) -> float | None:
    if candidate.bpm is None or previous.bpm is None:
        return None
    return min(
        best_tempo_distance(candidate_bpm, previous_bpm)
        for candidate_bpm in candidate.alternatives or (candidate.bpm,)
        for previous_bpm in previous.alternatives or (previous.bpm,)
    )


def _key_relation(
    candidate_key: str | None,
    previous_key: str | None,
    candidate_confidence: float | None = None,
    previous_confidence: float | None = None,
) -> tuple[str, float]:
    relation, score = camelot_compatibility(candidate_key, previous_key)
    return relation, attenuate_harmonic_score(
        score, candidate_confidence, previous_confidence
    )


def _combined_similarity(
    candidate: _Candidate, seed: _Candidate, ranges: dict[str, tuple[float, float]]
) -> float:
    embedding_score = float(
        np.mean(
            [
                _bounded(float(candidate.vectors[key] @ seed.vectors[key]))
                for key in REQUIRED_EMBEDDINGS
            ]
        )
    )
    context = _Context(seeds=[seed], ranges=ranges)
    sonara_score, _groups = _sonara_similarity(candidate, context)
    return embedding_score * 0.7 + (sonara_score or 0.0) * 0.3


def _diversity_score(
    candidate: _Candidate,
    selected: list[_Candidate],
    ranges: dict[str, tuple[float, float]],
) -> float:
    if not selected:
        return 0.5
    nearest = max(
        _fast_diversity_similarity(candidate, item, ranges) for item in selected
    )
    return _bounded(1.0 - nearest)


def _fast_diversity_similarity(
    candidate: _Candidate, selected: _Candidate, ranges: dict[str, tuple[float, float]]
) -> float:
    embedding_score = float(
        np.mean(
            [
                _bounded(float(candidate.vectors[key] @ selected.vectors[key]))
                for key in REQUIRED_EMBEDDINGS
            ]
        )
    )
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


def _reason(
    item: _ScoredCandidate,
    config: SetBuilderConfig,
    transition: dict[str, object],
    classifier_flow: float,
) -> str:
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
        "track": asdict(candidate.track),
        "reason": reason,
        "score": _bounded(score),
        "score_breakdown": {
            key: round(float(value), 6) for key, value in breakdown.items()
        },
        "sonara_groups": {
            key: round(float(value), 6) for key, value in sonara_groups.items()
        },
        "classifier_scores": _classifier_scores(candidate.track),
        "transition": transition,
    }


def _bounded(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, float(value)))


def _bounded_signed(value: float) -> float:
    if not np.isfinite(value):
        return 0.0
    return max(-1.0, min(1.0, float(value)))


def _candidate_identity(
    candidate: _LightCandidate | _Candidate,
) -> TrackIdentity:
    if candidate.identity is None:
        raise RuntimeError("SET candidate is missing its current track identity")
    return candidate.identity


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
