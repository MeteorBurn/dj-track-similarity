from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
import hashlib
import math
from typing import Any, Protocol

import numpy as np

from .analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
    SonaraFeatureRow,
)
from .evaluation.score_profiles import ScoreProfile, score_profile_from_dict
from .hybrid_explanation import build_hybrid_explanation
from .hybrid_transition import (
    candidate_transition_diagnostics as _candidate_transition_diagnostics,
)
from .library_models import (
    ClassifierScoreDetail,
    TrackDetail,
    TrackSummary,
)
from .track_models import TrackIdentity
from .tempo_resolution import (
    TempoEvidence,
    confidence_aware_tempo_score,
    resolve_tempo_evidence_v7,
)
from .transition_diagnostics import TRANSITION_RISK_V2, TRANSITION_RISK_VERSIONS
from .transition_diagnostics import TransitionTrack


class HybridRepository(Protocol):
    def list_track_summaries(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]: ...

    def get_track_detail(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> TrackDetail: ...

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

    def get_pair_feedback_map(
        self,
    ) -> Mapping[tuple[int, int, str], Mapping[str, Any]]: ...

    def create_search_session(
        self,
        mode: str,
        seed_track_ids: Sequence[int],
        request: Mapping[str, Any],
    ) -> int: ...

    def record_search_result_event(
        self,
        session_id: int,
        candidate_track_id: int,
        *,
        rank: int,
        total_score: float,
        score_breakdown: Mapping[str, Any],
    ) -> None: ...


DEFAULT_HYBRID_SOURCES = ("mert", "maest", "sonara", "clap")
ALLOWED_CANDIDATE_SOURCES = DEFAULT_HYBRID_SOURCES
HYBRID_UI_FEEDBACK_SOURCE = "hybrid_ui"
HYBRID_SEARCH_SESSION_MODE = "hybrid_search_preview"
HYBRID_SEARCH_LIMITATIONS = (
    "Hybrid search is an explicit weighted rank-fusion preview over existing MERT, MAEST, SONARA, and CLAP analysis data.",
    "CLAP is used only as stored audio embeddings in this preview; prompt-aware CLAP hybrid search is not part of this path.",
    "Optional classifier controls read stored promoted classifier scores only; missing scores stay neutral and no audio is decoded.",
    "The score is an optional transition-risk-adjusted weighted RRF preview score; it is diagnostic ranking output, not calibrated human-taste evidence.",
    "Transition risk is diagnostic only and is not AutoMix, beatgrid, cue-point detection, or a calibrated transition estimate.",
    "The endpoint reads the selected SQLite database only. By default it writes no rows; with record_session=true it writes only evaluation search_sessions/search_result_events rows and never trains classifiers, modifies production search scoring, or writes audio files.",
)
CLASSIFIER_SCORE_ADJUSTMENT_SCALE = 0.15


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
    repository: HybridRepository,
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
            f"{family!r} contract; reanalysis is required before Hybrid search"
        )
    return expected


@dataclass(frozen=True)
class HybridSearchResultRow:
    track: TrackSummary
    score: float
    total_score: float
    calibrated_score: None
    adjusted_score: float
    transition_risk: float | None
    transition_risk_penalty: float
    transition_risk_weight: float
    raw_rrf_score: float
    rank: int
    score_breakdown: Mapping[str, Mapping[str, float | int]]
    risk_breakdown: Mapping[str, float | None]
    source_support: Mapping[str, Mapping[str, Any]]
    classifier_support: Mapping[str, Mapping[str, Any]]
    match_character: Mapping[str, float]
    warnings: tuple[str, ...]
    explanation: tuple[str, ...]
    transition_diagnostics: Mapping[str, Any]
    diagnostics: Mapping[str, Any]
    feedback: Mapping[str, Any] | None

    def api_row(self, *, include_diagnostics: bool) -> dict[str, Any]:
        return {
            "track": asdict(self.track),
            "score": self.score,
            "total_score": self.total_score,
            "calibrated_score": self.calibrated_score,
            "adjusted_score": self.adjusted_score,
            "transition_risk": self.transition_risk,
            "transition_risk_penalty": self.transition_risk_penalty,
            "transition_risk_weight": self.transition_risk_weight,
            "raw_rrf_score": self.raw_rrf_score,
            "rank": self.rank,
            "score_breakdown": dict(self.score_breakdown),
            "risk_breakdown": dict(self.risk_breakdown),
            "source_support": {
                source: dict(support) for source, support in self.source_support.items()
            },
            "classifier_support": {
                classifier: dict(support)
                for classifier, support in self.classifier_support.items()
            },
            "match_character": dict(self.match_character),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation),
            "transition_diagnostics": dict(self.transition_diagnostics)
            if include_diagnostics
            else {},
            "diagnostics": dict(self.diagnostics) if include_diagnostics else {},
            "feedback": dict(self.feedback) if self.feedback is not None else None,
        }


@dataclass(frozen=True)
class HybridSearchResult:
    results: tuple[HybridSearchResultRow, ...]
    warnings: tuple[str, ...]
    weights_used: Mapping[str, float]
    sources: tuple[str, ...]
    limitations: tuple[str, ...]
    diagnostics: Mapping[str, Any]
    session_id: int | None
    source_contract_hashes: Mapping[str, str]

    def api_response(self, *, include_diagnostics: bool) -> dict[str, Any]:
        return {
            "results": [
                row.api_row(include_diagnostics=include_diagnostics)
                for row in self.results
            ],
            "warnings": list(self.warnings),
            "weights_used": dict(self.weights_used),
            "sources": list(self.sources),
            "limitations": list(self.limitations),
            "diagnostics": dict(self.diagnostics) if include_diagnostics else {},
            "session_id": self.session_id,
            "source_contract_hashes": dict(self.source_contract_hashes),
        }


@dataclass(frozen=True)
class _SourceContribution:
    rank: int
    score: float


@dataclass(frozen=True)
class _HybridCandidate:
    track: TrackSummary
    source_contributions: Mapping[str, _SourceContribution]
    source_seed_diagnostics: Mapping[str, Mapping[str, Any]]
    seed_track_ids: tuple[int, ...]
    identity: TrackIdentity | None = None
    sonara: SonaraFeatureRow | None = None

    @property
    def transition_track(self) -> TransitionTrack:
        if self.identity is None:
            raise RuntimeError("Hybrid candidate is missing its current track identity")
        return TransitionTrack(self.identity, self.track, self.sonara)


@dataclass(frozen=True)
class _ScoredHybridCandidate:
    candidate: _HybridCandidate
    raw_rrf_score: float
    score_breakdown: Mapping[str, Mapping[str, float | int]]
    classifier_adjustment: float
    tie_token: int


@dataclass(frozen=True)
class _RankedHybridCandidate:
    scored_candidate: _ScoredHybridCandidate
    normalized_rrf_score: float
    adjusted_score: float
    transition_risk: float | None
    transition_risk_penalty: float
    transition_diagnostics: Mapping[str, Any]


@dataclass(frozen=True)
class _ClassifierControls:
    preferences: Mapping[str, float]
    risk_weights: Mapping[str, float]

    @property
    def requested_keys(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.preferences) | set(self.risk_weights)))

    @property
    def has_score_preferences(self) -> bool:
        return any(value != 0.0 for value in self.preferences.values())


def build_hybrid_search_preview(
    db: HybridRepository,
    *,
    seed_track_ids: Sequence[int],
    analysis_outputs: Mapping[str, AnalysisOutput],
    sources: Sequence[str] | None = None,
    weights: Mapping[str, float] | None = None,
    score_profile: Mapping[str, Any] | None = None,
    per_source: int = 30,
    limit: int = 25,
    rrf_k: int = 60,
    random_seed: int = 123,
    transition_risk_weight: float = 0.0,
    transition_risk_version: str = TRANSITION_RISK_V2,
    classifier_preferences: Mapping[str, float] | None = None,
    classifier_risk_weights: Mapping[str, float] | None = None,
    record_session: bool = False,
) -> HybridSearchResult:
    clean_seed_track_ids = _positive_unique_ints(seed_track_ids, "seed_track_id")
    clean_sources = _clean_sources(sources)
    expected_outputs = _required_embedding_outputs(
        analysis_outputs,
        tuple(source for source in clean_sources if source != "sonara"),
    )
    clean_weights = _resolve_weights(
        clean_sources, weights=weights, score_profile=score_profile
    )
    clean_per_source = _positive_int(per_source, "per_source")
    clean_limit = _positive_int(limit, "limit")
    clean_rrf_k = _positive_int(rrf_k, "rrf_k")
    clean_random_seed = _int_value(random_seed, "random_seed")
    clean_transition_risk_weight = _risk_weight(
        transition_risk_weight, "transition_risk_weight"
    )
    clean_transition_risk_version = _transition_risk_version(transition_risk_version)
    clean_classifier_controls = _classifier_controls(
        classifier_preferences=classifier_preferences,
        classifier_risk_weights=classifier_risk_weights,
    )
    clean_record_session = bool(record_session)

    (
        candidates,
        clean_seed_tracks,
        warnings,
        source_contract_hashes,
        candidate_row_count,
    ) = _load_hybrid_candidates(
        db,
        seed_track_ids=clean_seed_track_ids,
        sources=clean_sources,
        analysis_outputs=expected_outputs,
        per_source=clean_per_source,
    )
    scored_candidates = _scored_hybrid_candidates(
        candidates,
        weights=clean_weights,
        rrf_k=clean_rrf_k,
        random_seed=clean_random_seed,
        classifier_controls=clean_classifier_controls,
    )
    results = _ranked_result_rows(
        db,
        scored_candidates,
        limit=clean_limit,
        sources=clean_sources,
        weights=clean_weights,
        seed_tracks=clean_seed_tracks,
        seed_track_ids=clean_seed_track_ids,
        feedback_map=db.get_pair_feedback_map(),
        feedback_source=HYBRID_UI_FEEDBACK_SOURCE,
        transition_risk_weight=clean_transition_risk_weight,
        transition_risk_version=clean_transition_risk_version,
        classifier_controls=clean_classifier_controls,
    )
    all_warnings = tuple(
        [*warnings, *_classifier_control_warnings(clean_classifier_controls, results)]
    )
    session_id = _record_hybrid_search_session(
        db,
        results,
        seed_track_ids=clean_seed_track_ids,
        sources=clean_sources,
        weights=clean_weights,
        per_source=clean_per_source,
        limit=clean_limit,
        rrf_k=clean_rrf_k,
        random_seed=clean_random_seed,
        transition_risk_weight=clean_transition_risk_weight,
        transition_risk_version=clean_transition_risk_version,
        classifier_controls=clean_classifier_controls,
        source_contract_hashes=source_contract_hashes,
        feedback_source=HYBRID_UI_FEEDBACK_SOURCE,
        record_session=clean_record_session,
    )
    return HybridSearchResult(
        results=results,
        warnings=all_warnings,
        weights_used=clean_weights,
        sources=clean_sources,
        limitations=HYBRID_SEARCH_LIMITATIONS,
        session_id=session_id,
        source_contract_hashes=source_contract_hashes,
        diagnostics={
            "method": "weighted_rrf",
            "seed_track_ids": list(clean_seed_track_ids),
            "per_source": clean_per_source,
            "rrf_k": clean_rrf_k,
            "random_seed": clean_random_seed,
            "transition_risk_weight": clean_transition_risk_weight,
            "transition_risk_version": clean_transition_risk_version,
            "classifier_preferences": dict(clean_classifier_controls.preferences),
            "classifier_risk_weights": dict(clean_classifier_controls.risk_weights),
            "record_session": clean_record_session,
            "session_id": session_id,
            "candidate_rows": candidate_row_count,
            "unique_candidates": len(candidates),
            "results_returned": len(results),
            "source_contract_hashes": dict(source_contract_hashes),
        },
    )


def _load_hybrid_candidates(
    db: HybridRepository,
    *,
    seed_track_ids: Sequence[int],
    sources: Sequence[str],
    analysis_outputs: Mapping[str, AnalysisOutput],
    per_source: int,
) -> tuple[
    tuple[_HybridCandidate, ...],
    tuple[TransitionTrack, ...],
    tuple[str, ...],
    dict[str, str],
    int,
]:
    summaries = db.list_track_summaries(include_missing=False)
    summaries_by_id = {track.track_id: track for track in summaries}
    identities = db.get_track_identities(
        tuple(summaries_by_id),
        include_missing=False,
    )
    missing_identities = sorted(set(summaries_by_id) - set(identities))
    if missing_identities:
        raise RuntimeError(
            f"library repository omitted current track identities: {missing_identities}"
        )
    _validate_summary_identities(summaries_by_id, identities)
    missing_seeds = [
        track_id for track_id in seed_track_ids if track_id not in identities
    ]
    if missing_seeds:
        raise ValueError(f"Unknown current seed tracks: {missing_seeds}")

    warnings: list[str] = []
    source_contract_hashes: dict[str, str] = {}
    vectors_by_source: dict[str, dict[int, np.ndarray]] = {}

    sonara_output = db.active_analysis_output("sonara", "core")
    sonara_rows = (
        db.load_sonara_feature_rows(sonara_output) if sonara_output is not None else ()
    )
    sonara_by_id = _validate_sonara_rows(
        sonara_rows,
        summaries_by_id,
        identities,
        expected_output=sonara_output,
    )
    if "sonara" in sources:
        if sonara_output is None:
            warnings.append("source=sonara skipped: no active SONARA Core contract")
        else:
            source_contract_hashes["sonara"] = sonara_output.contract_hash

    for source in sources:
        if source == "sonara":
            continue
        output = _require_current_embedding_output(
            db,
            source,
            analysis_outputs[source],
        )
        rows = db.load_analysis_vectors(output)
        vectors_by_source[source] = _validate_vector_rows(
            rows,
            summaries_by_id,
            identities,
            expected_output=output,
        )
        source_contract_hashes[source] = output.contract_hash

    candidates: dict[int, dict[str, Any]] = {}
    candidate_row_count = 0
    seed_ids = set(seed_track_ids)
    for source in sources:
        if source not in source_contract_hashes:
            continue
        for seed_track_id in seed_track_ids:
            if source == "sonara":
                ranked = _rank_sonara_source(
                    seed_track_id,
                    sonara_by_id,
                )
            else:
                ranked = _rank_embedding_source(
                    seed_track_id,
                    vectors_by_source[source],
                )
            ranked = [item for item in ranked if item[0] not in seed_ids][:per_source]
            if not ranked:
                warnings.append(
                    f"seed_track_id={seed_track_id} source={source} "
                    "returned no current candidates"
                )
                continue
            candidate_row_count += len(ranked)
            for rank, (candidate_id, score) in enumerate(ranked, start=1):
                payload = candidates.setdefault(
                    candidate_id,
                    {
                        "source_contributions": {},
                        "source_seed_diagnostics": {},
                        "seed_track_ids": set(),
                    },
                )
                payload["seed_track_ids"].add(seed_track_id)
                _merge_source_contribution(
                    payload,
                    source=source,
                    seed_track_id=seed_track_id,
                    contribution=_SourceContribution(rank=rank, score=score),
                )

    result = tuple(
        _HybridCandidate(
            track=summaries_by_id[track_id],
            source_contributions=dict(sorted(payload["source_contributions"].items())),
            source_seed_diagnostics=dict(
                sorted(payload["source_seed_diagnostics"].items())
            ),
            seed_track_ids=tuple(sorted(payload["seed_track_ids"])),
            identity=identities[track_id],
            sonara=sonara_by_id.get(track_id),
        )
        for track_id, payload in sorted(candidates.items())
    )
    seed_tracks = tuple(
        TransitionTrack(
            identities[track_id],
            summaries_by_id[track_id],
            sonara_by_id.get(track_id),
        )
        for track_id in seed_track_ids
    )
    return (
        result,
        seed_tracks,
        tuple(warnings),
        dict(sorted(source_contract_hashes.items())),
        candidate_row_count,
    )


def _merge_source_contribution(
    candidate: dict[str, Any],
    *,
    source: str,
    seed_track_id: int,
    contribution: _SourceContribution,
) -> None:
    contributions: dict[str, _SourceContribution] = candidate["source_contributions"]
    diagnostics: dict[str, dict[str, Any]] = candidate["source_seed_diagnostics"]
    current = contributions.get(source)
    source_diagnostics = diagnostics.get(source)
    supporting_ids = {
        seed_track_id,
        *(
            source_diagnostics.get("supporting_seed_track_ids", ())
            if source_diagnostics is not None
            else ()
        ),
    }
    if (
        current is None
        or contribution.rank < current.rank
        or (contribution.rank == current.rank and contribution.score > current.score)
    ):
        contributions[source] = contribution
        diagnostics[source] = {
            "best_seed_track_id": seed_track_id,
            "best_rank": contribution.rank,
            "best_source_score": contribution.score,
            "supporting_seed_track_ids": sorted(supporting_ids),
        }
        return
    assert source_diagnostics is not None
    source_diagnostics["supporting_seed_track_ids"] = sorted(supporting_ids)


def _rank_embedding_source(
    seed_track_id: int,
    vectors: Mapping[int, np.ndarray],
) -> list[tuple[int, float]]:
    seed = vectors.get(seed_track_id)
    if seed is None:
        return []
    return sorted(
        (
            (track_id, float(np.dot(seed, vector)))
            for track_id, vector in vectors.items()
            if track_id != seed_track_id
        ),
        key=lambda item: (-item[1], item[0]),
    )


_SONARA_DISTANCE_FIELDS: Mapping[str, float] = {
    "detected_bpm": 3.0,
    "onset_density_per_second": 2.0,
    "energy_score": 1.3,
    "danceability_score": 1.3,
    "chord_changes_per_second": 1.0,
    "dissonance_score": 1.0,
    "mfcc_mean_blob": 1.8,
    "chroma_mean_blob": 1.2,
    "spectral_centroid_hz": 1.0,
    "spectral_bandwidth_hz": 1.0,
    "spectral_rolloff_hz": 1.0,
    "spectral_flatness": 0.9,
    "spectral_contrast_mean_blob": 0.9,
    "zero_crossing_rate": 0.8,
    "rms_mean": 0.8,
    "rms_max": 0.5,
}


def _rank_sonara_source(
    seed_track_id: int,
    rows: Mapping[int, SonaraFeatureRow],
) -> list[tuple[int, float]]:
    seed = rows.get(seed_track_id)
    if seed is None:
        return []
    ranges = _sonara_dimension_ranges(rows.values())
    scored = [
        (
            track_id,
            _sonara_weighted_euclidean_similarity(
                seed,
                row,
                ranges,
            ),
        )
        for track_id, row in rows.items()
        if track_id != seed_track_id
    ]
    return sorted(
        ((track_id, score) for track_id, score in scored if score is not None),
        key=lambda item: (-item[1], item[0]),
    )


def _sonara_dimension_ranges(
    rows: Sequence[SonaraFeatureRow],
) -> dict[tuple[str, int | None], tuple[float, float]]:
    observed: dict[tuple[str, int | None], list[float]] = {}
    for row in rows:
        for field in _SONARA_DISTANCE_FIELDS:
            for dimension, value in _sonara_field_values(row, field):
                observed.setdefault((field, dimension), []).append(value)
    return {
        key: (min(values), max(values))
        for key, values in observed.items()
        if len(values) >= 2
    }


def _sonara_weighted_euclidean_similarity(
    seed: SonaraFeatureRow,
    candidate: SonaraFeatureRow,
    ranges: Mapping[tuple[str, int | None], tuple[float, float]],
) -> float | None:
    squared_distance = 0.0
    total_weight = 0.0
    for field, field_weight in _SONARA_DISTANCE_FIELDS.items():
        if field == "detected_bpm":
            seed_tempo = _tempo_from_sonara(seed)
            candidate_tempo = _tempo_from_sonara(
                candidate,
            )
            tempo_score = _tempo_similarity(candidate_tempo, seed_tempo)
            if tempo_score is None:
                continue
            squared_distance += field_weight * (1.0 - tempo_score) ** 2
            total_weight += field_weight
            continue
        seed_values = dict(_sonara_field_values(seed, field))
        candidate_values = dict(_sonara_field_values(candidate, field))
        shared = sorted(set(seed_values) & set(candidate_values))
        dimensions = [dimension for dimension in shared if (field, dimension) in ranges]
        if not dimensions:
            continue
        per_dimension_weight = field_weight / len(dimensions)
        for dimension in dimensions:
            lower, upper = ranges[(field, dimension)]
            if upper == lower:
                distance = 0.0
            else:
                seed_value = (seed_values[dimension] - lower) / (upper - lower)
                candidate_value = (candidate_values[dimension] - lower) / (
                    upper - lower
                )
                distance = min(1.0, abs(candidate_value - seed_value))
            squared_distance += per_dimension_weight * distance**2
            total_weight += per_dimension_weight
    if total_weight <= 0.0:
        return None
    return _clamp01(1.0 - math.sqrt(squared_distance / total_weight))


def _sonara_field_values(
    row: SonaraFeatureRow,
    field: str,
) -> tuple[tuple[int | None, float], ...]:
    value = row.values.get(field)
    if isinstance(value, (tuple, list, np.ndarray)):
        return tuple(
            (index, number)
            for index, item in enumerate(value)
            if (number := _optional_finite_float(item)) is not None
        )
    number = _optional_finite_float(value)
    return ((None, number),) if number is not None else ()


def _tempo_from_sonara(
    row: SonaraFeatureRow,
) -> TempoEvidence:
    return resolve_tempo_evidence_v7(row.values, tag_bpm=None)


def _tempo_similarity(
    candidate: TempoEvidence,
    seed: TempoEvidence,
) -> float | None:
    return confidence_aware_tempo_score(candidate, seed)


def _validate_summary_identities(
    summaries: Mapping[int, TrackSummary],
    identities: Mapping[int, TrackIdentity],
) -> None:
    for track_id, summary in summaries.items():
        identity = identities.get(track_id)
        if identity is None or (
            identity.catalog_uuid != summary.catalog_uuid
            or identity.track_id != summary.track_id
            or identity.track_uuid != summary.track_uuid
            or identity.content_generation != summary.content_generation
        ):
            raise RuntimeError(
                "library summary identity does not match the current "
                f"track identity: track_id={track_id}"
            )
    if len({identity.catalog_uuid for identity in identities.values()}) > 1:
        raise RuntimeError("library repository returned multiple catalog UUIDs")


def _validate_sonara_rows(
    rows: Sequence[SonaraFeatureRow],
    summaries: Mapping[int, TrackSummary],
    identities: Mapping[int, TrackIdentity],
    *,
    expected_output: AnalysisOutput | None,
) -> dict[int, SonaraFeatureRow]:
    result: dict[int, SonaraFeatureRow] = {}
    for row in rows:
        _validate_analysis_target(
            row.target,
            summaries,
            identities,
        )
        if expected_output is None or row.output != expected_output:
            raise RuntimeError(
                "analysis repository returned SONARA data for the wrong contract"
            )
        result[row.target.track_id] = row
    return result


def _validate_vector_rows(
    rows: Sequence[AnalysisVectorRow],
    summaries: Mapping[int, TrackSummary],
    identities: Mapping[int, TrackIdentity],
    *,
    expected_output: AnalysisOutput,
) -> dict[int, np.ndarray]:
    result: dict[int, np.ndarray] = {}
    for row in rows:
        _validate_analysis_target(
            row.target,
            summaries,
            identities,
        )
        if row.output != expected_output:
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


def _validate_analysis_target(
    target: AnalysisTarget,
    summaries: Mapping[int, TrackSummary],
    identities: Mapping[int, TrackIdentity],
) -> None:
    summary = summaries.get(target.track_id)
    identity = identities.get(target.track_id)
    if summary is None or identity is None:
        raise RuntimeError("analysis repository returned a row without a current track")
    if (
        target.catalog_uuid != identity.catalog_uuid
        or target.track_id != identity.track_id
        or target.track_uuid != identity.track_uuid
        or target.content_generation != identity.content_generation
        or summary.catalog_uuid != identity.catalog_uuid
        or summary.track_uuid != identity.track_uuid
        or summary.content_generation != identity.content_generation
    ):
        raise RuntimeError("analysis row identity does not match the current track")


def _scored_hybrid_candidates(
    candidates: Sequence[_HybridCandidate],
    *,
    weights: Mapping[str, float],
    rrf_k: int,
    random_seed: int,
    classifier_controls: _ClassifierControls,
) -> tuple[_ScoredHybridCandidate, ...]:
    scored_candidates: list[_ScoredHybridCandidate] = []
    for candidate in candidates:
        source_score_breakdown = _weighted_rrf_components_with_source_scores(
            candidate.source_contributions, weights, rrf_k
        )
        classifier_score_breakdown, classifier_adjustment = _classifier_score_breakdown(
            candidate.track, classifier_controls
        )
        score_breakdown = {**source_score_breakdown, **classifier_score_breakdown}
        raw_rrf_score = _weighted_rrf_score(
            candidate.source_contributions,
            weights,
            rrf_k,
        )
        if raw_rrf_score <= 0:
            continue
        scored_candidates.append(
            _ScoredHybridCandidate(
                candidate=candidate,
                raw_rrf_score=raw_rrf_score,
                score_breakdown=score_breakdown,
                classifier_adjustment=classifier_adjustment,
                tie_token=_tie_token(
                    random_seed,
                    _scoring_track_id(candidate.track),
                ),
            ),
        )
    return tuple(
        sorted(
            scored_candidates,
            key=lambda candidate: (
                -candidate.raw_rrf_score,
                candidate.tie_token,
                _scoring_track_id(candidate.candidate.track),
            ),
        ),
    )


def _weighted_rrf_components_with_source_scores(
    contributions: Mapping[str, object],
    weights: Mapping[str, float],
    rrf_k: int,
) -> dict[str, dict[str, float | int]]:
    components = _weighted_rrf_components(contributions, weights, rrf_k)
    return {
        source: {
            **component,
            "score": float(getattr(contributions[source], "score")),
        }
        for source, component in components.items()
    }


def _weighted_rrf_score(
    contributions: Mapping[str, object],
    weights: Mapping[str, float],
    rrf_k: int,
) -> float:
    return sum(
        float(component["contribution"])
        for component in _weighted_rrf_components(
            contributions,
            weights,
            rrf_k,
        ).values()
    )


def _weighted_rrf_components(
    contributions: Mapping[str, object],
    weights: Mapping[str, float],
    rrf_k: int,
) -> dict[str, dict[str, float | int]]:
    clean_rrf_k = _positive_int(rrf_k, "rrf_k")
    components: dict[str, dict[str, float | int]] = {}
    for source, weight in sorted(weights.items()):
        contribution = contributions.get(source)
        if contribution is None:
            continue
        rank = _positive_int(
            getattr(contribution, "rank", None),
            f"{source}.rank",
        )
        clean_weight = _non_negative_finite_float(
            weight,
            f"weights.{source}",
        )
        if clean_weight <= 0.0:
            continue
        components[source] = {
            "rank": rank,
            "weight": clean_weight,
            "contribution": clean_weight / (clean_rrf_k + rank),
        }
    return components


def _ranked_result_rows(
    db: HybridRepository,
    scored_candidates: Sequence[_ScoredHybridCandidate],
    *,
    limit: int,
    sources: Sequence[str],
    weights: Mapping[str, float],
    seed_tracks: Sequence[TransitionTrack],
    seed_track_ids: Sequence[int],
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    feedback_source: str,
    transition_risk_weight: float,
    transition_risk_version: str,
    classifier_controls: _ClassifierControls,
) -> tuple[HybridSearchResultRow, ...]:
    max_score = max(
        (candidate.raw_rrf_score for candidate in scored_candidates), default=0.0
    )
    transition_sources = _effective_transition_sources(
        scored_candidates,
        sources,
        weights,
    )
    ranked_candidates = _ranked_candidates_with_transition_risk(
        scored_candidates,
        limit=limit,
        sources=transition_sources,
        seed_tracks=seed_tracks,
        max_score=max_score,
        transition_risk_weight=transition_risk_weight,
        transition_risk_version=transition_risk_version,
        classifier_controls=classifier_controls,
    )
    result_rows: list[HybridSearchResultRow] = []
    for rank, ranked_candidate in enumerate(ranked_candidates, start=1):
        candidate = ranked_candidate.scored_candidate
        candidate_track = candidate.candidate.transition_track
        candidate_detail = (
            db.get_track_detail(
                candidate_track.summary.track_id,
                include_missing=False,
            )
            if classifier_controls.requested_keys
            else None
        )
        classifier_support = _classifier_support(
            candidate_detail,
            classifier_controls,
            score_breakdown=candidate.score_breakdown,
        )
        explanation = build_hybrid_explanation(
            candidate_track=candidate_track,
            seed_tracks=seed_tracks,
            source_contributions=candidate.candidate.source_contributions,
            source_seed_diagnostics=candidate.candidate.source_seed_diagnostics,
            score_breakdown=candidate.score_breakdown,
            classifier_support=classifier_support,
            transition_diagnostics=ranked_candidate.transition_diagnostics,
            sources=sources,
            total_score=ranked_candidate.adjusted_score,
        )
        result_rows.append(
            HybridSearchResultRow(
                track=candidate_track.summary,
                score=ranked_candidate.adjusted_score,
                total_score=explanation.total_score,
                calibrated_score=explanation.calibrated_score,
                adjusted_score=ranked_candidate.adjusted_score,
                transition_risk=ranked_candidate.transition_risk,
                transition_risk_penalty=ranked_candidate.transition_risk_penalty,
                transition_risk_weight=transition_risk_weight,
                raw_rrf_score=candidate.raw_rrf_score,
                rank=rank,
                score_breakdown=explanation.score_breakdown,
                risk_breakdown=explanation.risk_breakdown,
                source_support=explanation.source_support,
                classifier_support=explanation.classifier_support,
                match_character=explanation.match_character,
                warnings=explanation.warnings,
                explanation=explanation.explanation,
                transition_diagnostics=ranked_candidate.transition_diagnostics,
                diagnostics=_candidate_diagnostics(candidate.candidate),
                feedback=_candidate_feedback(
                    seed_track_ids,
                    candidate.candidate.track.track_id,
                    feedback_map=feedback_map,
                    source=feedback_source,
                ),
            ),
        )
    return tuple(result_rows)


def _effective_transition_sources(
    scored_candidates: Sequence[_ScoredHybridCandidate],
    sources: Sequence[str],
    weights: Mapping[str, float],
) -> tuple[str, ...]:
    positive_sources = tuple(
        source for source in sources if float(weights.get(source, 0.0)) > 0.0
    )
    effective_sources = tuple(
        source
        for source in positive_sources
        if any(
            source in candidate.candidate.source_contributions
            for candidate in scored_candidates
        )
    )
    if effective_sources:
        return effective_sources
    return positive_sources


def _record_hybrid_search_session(
    db: HybridRepository,
    results: Sequence[HybridSearchResultRow],
    *,
    seed_track_ids: Sequence[int],
    sources: Sequence[str],
    weights: Mapping[str, float],
    per_source: int,
    limit: int,
    rrf_k: int,
    random_seed: int,
    transition_risk_weight: float,
    transition_risk_version: str,
    classifier_controls: _ClassifierControls,
    source_contract_hashes: Mapping[str, str],
    feedback_source: str,
    record_session: bool,
) -> int | None:
    if not record_session:
        return None
    contributing_sources = {
        source
        for row in results
        for source in row.source_support
        if row.source_support[source].get("available") is True
    }
    unproven_sources = sorted(contributing_sources - set(source_contract_hashes))
    if unproven_sources:
        raise RuntimeError(
            "cannot record Hybrid session with unproven source contracts: "
            f"{unproven_sources}"
        )
    session_id = db.create_search_session(
        HYBRID_SEARCH_SESSION_MODE,
        seed_track_ids,
        {
            "sources": list(sources),
            "weights": dict(weights),
            "per_source": per_source,
            "limit": limit,
            "rrf_k": rrf_k,
            "random_seed": random_seed,
            "transition_risk_weight": transition_risk_weight,
            "transition_risk_version": transition_risk_version,
            "classifier_preferences": dict(classifier_controls.preferences),
            "classifier_risk_weights": dict(classifier_controls.risk_weights),
            "feedback_source": feedback_source,
            "record_session": True,
            "candidate_count": len(results),
            "source_contract_hashes": dict(source_contract_hashes),
        },
    )
    for row in results:
        db.record_search_result_event(
            session_id,
            row.track.track_id,
            rank=row.rank,
            total_score=row.score,
            score_breakdown=_hybrid_event_score_breakdown(
                row,
                rrf_k=rrf_k,
                source_contract_hashes=source_contract_hashes,
            ),
        )
    return session_id


def _hybrid_event_score_breakdown(
    row: HybridSearchResultRow,
    *,
    rrf_k: int,
    source_contract_hashes: Mapping[str, str],
) -> dict[str, Any]:
    source_payload = {
        source: {
            "rank": details.get("rank"),
            "score": details.get("score"),
            "weight": details.get("weight"),
            "contribution": details.get("contribution"),
        }
        for source, details in sorted(row.score_breakdown.items())
        if source in ALLOWED_CANDIDATE_SOURCES
    }
    return {
        "score_kind": _hybrid_score_kind(row),
        "rank": row.rank,
        "total_score": row.total_score,
        "calibrated_score": row.calibrated_score,
        "adjusted_score": row.adjusted_score,
        "raw_rrf_score": row.raw_rrf_score,
        "transition_risk": row.transition_risk,
        "transition_risk_penalty": row.transition_risk_penalty,
        "transition_risk_weight": row.transition_risk_weight,
        "rrf_k": rrf_k,
        "source_ranks": {
            source: details.get("rank")
            for source, details in sorted(source_payload.items())
        },
        "weighted_rrf": {
            "score": row.score,
            "components": source_payload,
        },
        "sources": source_payload,
        "source_contract_hashes": dict(source_contract_hashes),
        "score_breakdown": {
            source: dict(details)
            for source, details in sorted(row.score_breakdown.items())
        },
        "risk_breakdown": dict(row.risk_breakdown),
        "source_support": {
            source: dict(support)
            for source, support in sorted(row.source_support.items())
        },
        "classifier_support": {
            classifier: dict(support)
            for classifier, support in sorted(row.classifier_support.items())
        },
        "match_character": dict(row.match_character),
        "warnings": list(row.warnings),
        "explanation": list(row.explanation),
        "transition_diagnostics": dict(row.transition_diagnostics),
    }


def _hybrid_score_kind(row: HybridSearchResultRow) -> str:
    has_classifier_adjustment = any(
        abs(float(support.get("score_contribution") or 0.0)) > 0.0
        for support in row.classifier_support.values()
    )
    if row.transition_risk_weight > 0 and has_classifier_adjustment:
        return "weighted_rrf_classifier_risk_adjusted"
    if row.transition_risk_weight > 0:
        return "weighted_rrf_adjusted"
    if has_classifier_adjustment:
        return "weighted_rrf_classifier_adjusted"
    return "weighted_rrf"


def _ranked_candidates_with_transition_risk(
    scored_candidates: Sequence[_ScoredHybridCandidate],
    *,
    limit: int,
    sources: Sequence[str],
    seed_tracks: Sequence[TransitionTrack],
    max_score: float,
    transition_risk_weight: float,
    transition_risk_version: str,
    classifier_controls: _ClassifierControls,
) -> tuple[_RankedHybridCandidate, ...]:
    applies_adjustment = (
        transition_risk_weight > 0 or classifier_controls.has_score_preferences
    )
    candidates_to_score = (
        scored_candidates if applies_adjustment else scored_candidates[:limit]
    )
    ranked_candidates = tuple(
        _ranked_candidate(
            candidate,
            sources=sources,
            seed_tracks=seed_tracks,
            max_score=max_score,
            transition_risk_weight=transition_risk_weight,
            transition_risk_version=transition_risk_version,
            classifier_controls=classifier_controls,
        )
        for candidate in candidates_to_score
    )
    if not applies_adjustment:
        return ranked_candidates
    return tuple(
        sorted(
            ranked_candidates,
            key=lambda candidate: (
                -candidate.adjusted_score,
                -candidate.normalized_rrf_score,
                candidate.scored_candidate.tie_token,
                _scoring_track_id(candidate.scored_candidate.candidate.track),
            ),
        )[:limit]
    )


def _ranked_candidate(
    candidate: _ScoredHybridCandidate,
    *,
    sources: Sequence[str],
    seed_tracks: Sequence[TransitionTrack],
    max_score: float,
    transition_risk_weight: float,
    transition_risk_version: str,
    classifier_controls: _ClassifierControls,
) -> _RankedHybridCandidate:
    normalized_rrf_score = _normalized_response_score(
        candidate.raw_rrf_score, max_score
    )
    transition_diagnostics = _candidate_transition_diagnostics(
        candidate.candidate,
        seed_tracks=seed_tracks,
        sources=sources,
        risk_version=transition_risk_version,
        classifier_risk_weights=classifier_controls.risk_weights,
    )
    transition_risk = transition_diagnostics["transition_risk"]
    transition_risk_penalty = transition_risk_weight * (
        float(transition_risk) if transition_risk is not None else 0.0
    )
    adjusted_score = (
        normalized_rrf_score + candidate.classifier_adjustment - transition_risk_penalty
    )
    return _RankedHybridCandidate(
        scored_candidate=candidate,
        normalized_rrf_score=normalized_rrf_score,
        adjusted_score=adjusted_score,
        transition_risk=transition_risk,
        transition_risk_penalty=transition_risk_penalty,
        transition_diagnostics=transition_diagnostics,
    )


def _candidate_diagnostics(candidate: _HybridCandidate) -> dict[str, Any]:
    return {
        "supporting_seed_track_ids": list(candidate.seed_track_ids),
        "source_support": {
            source: {
                "best_seed_track_id": values["best_seed_track_id"],
                "best_rank": values["best_rank"],
                "supporting_seed_track_ids": values["supporting_seed_track_ids"],
            }
            for source, values in candidate.source_seed_diagnostics.items()
        },
    }


def _candidate_feedback(
    seed_track_ids: Sequence[int],
    candidate_track_id: int,
    *,
    feedback_map: Mapping[tuple[int, int, str], Mapping[str, Any]],
    source: str,
) -> dict[str, Any] | None:
    rows = [
        feedback
        for seed_track_id in seed_track_ids
        if (feedback := feedback_map.get((seed_track_id, candidate_track_id, source)))
        is not None
    ]
    if not rows:
        return None
    per_seed = [
        {
            "id": int(row["id"]),
            "seed_track_id": int(row["seed_track_id"]),
            "candidate_track_id": int(row["candidate_track_id"]),
            "rating": int(row["rating"]),
            "reason_tags": list(row["reason_tags"]),
            "notes": row.get("notes"),
            "source": str(row["source"]),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]
    ratings = {int(row["rating"]) for row in rows}
    reason_tag_sets = {tuple(row["reason_tags"]) for row in rows}
    notes = {row.get("notes") for row in rows}
    is_complete = len(rows) == len(seed_track_ids)
    is_consistent = len(ratings) == 1 and len(reason_tag_sets) == 1 and len(notes) == 1
    return {
        "state": "rated" if is_complete and is_consistent else "mixed",
        "source": source,
        "seed_track_ids": list(seed_track_ids),
        "candidate_track_id": candidate_track_id,
        "rating": next(iter(ratings)) if len(ratings) == 1 else None,
        "reason_tags": list(next(iter(reason_tag_sets)))
        if len(reason_tag_sets) == 1
        else _sorted_reason_tag_union(rows),
        "notes": next(iter(notes)) if len(notes) == 1 else None,
        "per_seed": per_seed,
    }


def _sorted_reason_tag_union(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted({str(tag) for row in rows for tag in row["reason_tags"]})


def _classifier_score_breakdown(
    track: TrackSummary,
    controls: _ClassifierControls,
) -> tuple[dict[str, dict[str, float | int]], float]:
    if not controls.preferences:
        return {}, 0.0
    denominator = sum(abs(preference) for preference in controls.preferences.values())
    if denominator <= 0.0:
        return {}, 0.0

    adjustment = 0.0
    breakdown: dict[str, dict[str, float | int]] = {}
    for classifier_key, preference in controls.preferences.items():
        score = _track_classifier_score(track, classifier_key)
        if score is None:
            continue
        contribution = (
            CLASSIFIER_SCORE_ADJUSTMENT_SCALE
            * preference
            * (score * 2.0 - 1.0)
            / denominator
        )
        adjustment += contribution
        breakdown[_classifier_breakdown_key(classifier_key)] = {
            "rank": 0,
            "score": score,
            "weight": preference,
            "contribution": contribution,
        }
    return breakdown, adjustment


def _classifier_support(
    track: TrackDetail | None,
    controls: _ClassifierControls,
    *,
    score_breakdown: Mapping[str, Mapping[str, float | int]],
) -> dict[str, dict[str, Any]]:
    support: dict[str, dict[str, Any]] = {}
    for classifier_key in controls.requested_keys:
        detail = _classifier_detail(track, classifier_key)
        score = detail.score if detail is not None else None
        contribution = _optional_finite_float(
            (score_breakdown.get(_classifier_breakdown_key(classifier_key)) or {}).get(
                "contribution"
            )
        )
        risk_weight = float(controls.risk_weights.get(classifier_key, 0.0))
        role = "risk_penalty" if risk_weight > 0.0 else "preference"
        support[classifier_key] = {
            "available": score is not None,
            "score": score,
            "preference": controls.preferences.get(classifier_key, 0.0),
            "risk_weight": risk_weight,
            "score_contribution": contribution,
            "risk_contribution": _clamp01(score * risk_weight)
            if score is not None and risk_weight > 0.0
            else None,
            "fresh": None,
            "stale": None,
            "stored_model_id": detail.model_id if detail is not None else None,
            "current_model_id": None,
            "manifest_status": None,
            "production_status": None,
            "hybrid_signal_source": "request_control",
            "role": role,
            "axis": None,
            "label": (detail.predicted_class if detail is not None else None),
            "description": (
                "Current-generation stored classifier score"
                if detail is not None
                else None
            ),
            "missing_score_policy": "neutral",
            "feature_set": (detail.feature_set if detail is not None else None),
            "feature_manifest_hash": (
                detail.feature_manifest_hash if detail is not None else None
            ),
            "uses_sonara": (detail.uses_sonara if detail is not None else None),
            "sonara_release_hash": (
                detail.sonara_release_hash if detail is not None else None
            ),
            "positive_label": (detail.positive_label if detail is not None else None),
        }
    return support


def _classifier_control_warnings(
    controls: _ClassifierControls,
    rows: Sequence[HybridSearchResultRow],
) -> tuple[str, ...]:
    if not controls.requested_keys:
        return ()
    available_keys = {
        key
        for row in rows
        for key, support in row.classifier_support.items()
        if support.get("available") is True
    }
    warnings: list[str] = []
    for classifier_key in controls.requested_keys:
        if classifier_key not in available_keys:
            warnings.append(
                f"Classifier signal {classifier_key!r} has no stored scores in this preview; contribution stayed neutral."
            )
            continue
    return tuple(warnings)


def _track_classifier_score(
    track: TrackSummary,
    classifier_key: str,
) -> float | None:
    for score in track.classifier_scores:
        if score.classifier_key == classifier_key:
            return _clamp01(score.score)
    return None


def _classifier_detail(
    track: TrackDetail | None,
    classifier_key: str,
) -> ClassifierScoreDetail | None:
    if track is None:
        return None
    for detail in track.classifier_scores_detail:
        if detail.classifier_key == classifier_key:
            return detail
    return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _classifier_breakdown_key(classifier_key: str) -> str:
    safe_key = "_".join(part for part in str(classifier_key).strip().split() if part)
    return f"classifier_{safe_key}"


def _resolve_weights(
    sources: Sequence[str],
    *,
    weights: Mapping[str, float] | None,
    score_profile: Mapping[str, Any] | None,
) -> dict[str, float]:
    has_weights = weights is not None
    has_score_profile = score_profile is not None
    if has_weights and has_score_profile:
        raise ValueError("Provide either weights or score_profile, not both")
    if has_score_profile:
        profile = score_profile_from_dict(score_profile or {})
        _require_profile_sources_match(sources, profile)
        return _normalize_weights(profile.weights, sources)
    if has_weights:
        return _normalize_weights(weights or {}, sources)
    return {source: 1.0 / len(sources) for source in sources}


def _require_profile_sources_match(
    sources: Sequence[str], profile: ScoreProfile
) -> None:
    profile_sources = tuple(profile.sources)
    if set(profile_sources) == set(sources):
        return
    raise ValueError(
        "score_profile sources must match requested sources exactly: "
        f"profile={', '.join(profile_sources)} requested={', '.join(sources)}",
    )


def _normalize_weights(
    weights: Mapping[str, float], sources: Sequence[str]
) -> dict[str, float]:
    source_set = set(sources)
    clean_weights: dict[str, float] = {}
    for source, value in weights.items():
        source_name = str(source).strip().lower()
        if source_name in clean_weights:
            raise ValueError(
                f"weights contains duplicate normalized source {source_name!r}"
            )
        if source_name not in source_set:
            raise ValueError(
                f"weights contains source {source_name!r} outside requested sources: {', '.join(sources)}"
            )
        clean_weights[source_name] = _non_negative_finite_float(
            value, f"weights.{source_name}"
        )
    missing = sorted(source_set - set(clean_weights))
    if missing:
        raise ValueError(f"weights missing requested source(s): {', '.join(missing)}")
    weight_sum = sum(clean_weights.values())
    if weight_sum <= 0:
        raise ValueError("weights must contain at least one positive value")
    return {source: clean_weights[source] / weight_sum for source in sources}


def _clean_sources(sources: Sequence[str] | None) -> tuple[str, ...]:
    values = DEFAULT_HYBRID_SOURCES if sources is None else sources
    clean_sources = tuple(
        dict.fromkeys(
            text for source in values if (text := str(source).strip().lower())
        )
    )
    if not clean_sources:
        raise ValueError("At least one hybrid source is required")
    unsupported = [
        source for source in clean_sources if source not in ALLOWED_CANDIDATE_SOURCES
    ]
    if unsupported:
        allowed = ", ".join(ALLOWED_CANDIDATE_SOURCES)
        raise ValueError(
            f"Unsupported hybrid source(s): {', '.join(unsupported)}. Allowed: {allowed}"
        )
    return clean_sources


def _classifier_controls(
    *,
    classifier_preferences: Mapping[str, float] | None,
    classifier_risk_weights: Mapping[str, float] | None,
) -> _ClassifierControls:
    preferences = _clean_signed_weight_map(
        classifier_preferences, "classifier_preferences"
    )
    risk_weights = _clean_unit_weight_map(
        classifier_risk_weights, "classifier_risk_weights"
    )
    return _ClassifierControls(preferences=preferences, risk_weights=risk_weights)


def _clean_signed_weight_map(
    values: Mapping[str, float] | None, field_name: str
) -> dict[str, float]:
    if not values:
        return {}
    clean_values: dict[str, float] = {}
    for key, value in values.items():
        classifier_key = str(key).strip()
        if not classifier_key:
            continue
        if classifier_key in clean_values:
            raise ValueError(
                f"{field_name} contains duplicate classifier key {classifier_key!r}"
            )
        weight = _signed_weight(value, f"{field_name}.{classifier_key}")
        if weight != 0.0:
            clean_values[classifier_key] = weight
    return clean_values


def _clean_unit_weight_map(
    values: Mapping[str, float] | None, field_name: str
) -> dict[str, float]:
    if not values:
        return {}
    clean_values: dict[str, float] = {}
    for key, value in values.items():
        classifier_key = str(key).strip()
        if not classifier_key:
            continue
        if classifier_key in clean_values:
            raise ValueError(
                f"{field_name} contains duplicate classifier key {classifier_key!r}"
            )
        weight = _risk_weight(value, f"{field_name}.{classifier_key}")
        if weight != 0.0:
            clean_values[classifier_key] = weight
    return clean_values


def _transition_risk_version(value: object) -> str:
    text = str(value or "").strip().lower()
    if text in TRANSITION_RISK_VERSIONS:
        return text
    raise ValueError(
        f"transition_risk_version must be one of: {', '.join(TRANSITION_RISK_VERSIONS)}"
    )


def _positive_unique_ints(values: Sequence[int], field_name: str) -> tuple[int, ...]:
    clean_values = tuple(
        dict.fromkeys(_positive_int(value, field_name) for value in values)
    )
    if not clean_values:
        raise ValueError(f"At least one {field_name} value is required")
    return clean_values


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        clean_value = int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if clean_value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return clean_value


def _int_value(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(str(value).strip())
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer") from error


def _non_negative_finite_float(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite non-negative number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} must be a finite non-negative number"
        ) from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field_name} must be a finite non-negative number")
    return number


def _risk_weight(value: object, field_name: str) -> float:
    number = _non_negative_finite_float(value, field_name)
    if number > 1.0:
        raise ValueError(f"{field_name} must be between 0 and 1")
    return number


def _signed_weight(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be between -1 and 1")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be between -1 and 1") from error
    if not math.isfinite(number) or not -1.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be between -1 and 1")
    return number


def _clamp01(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, value))


def _normalized_response_score(raw_score: float, max_score: float) -> float:
    if max_score <= 0:
        return 0.0
    return raw_score / max_score


def _tie_token(random_seed: int, candidate_track_id: int) -> int:
    digest = hashlib.sha256(
        f"hybrid:{random_seed}:{candidate_track_id}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big")


def _scoring_track_id(track: object) -> int:
    """Return the candidate id for pure scoring tests and v7 DTOs."""

    if isinstance(track, TrackSummary):
        return track.track_id
    value = getattr(track, "id", None)
    return _positive_int(value, "candidate_track_id")
