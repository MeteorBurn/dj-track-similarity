from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .analysis_config import (
    ANALYSIS_DEVICE_PATTERN,
    ANALYSIS_MODEL_ORDER,
    DEFAULT_ANALYSIS_DEVICE,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    DEFAULT_ANALYSIS_TOP_K,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    MAX_ANALYSIS_INFERENCE_BATCH_SIZE,
    MAX_ANALYSIS_TOP_K,
    MAX_ANALYSIS_TRACK_BATCH_SIZE,
    MIN_ANALYSIS_INFERENCE_BATCH_SIZE,
    MIN_ANALYSIS_TOP_K,
    MIN_ANALYSIS_TRACK_BATCH_SIZE,
)


EvaluationSource = Literal["mert", "maest", "sonara", "clap"]
HybridSearchSource = Literal["mert", "maest", "sonara", "clap"]
EvaluationPairReasonTag = Literal[
    "good_groove",
    "good_density",
    "good_texture",
    "good_mood",
    "good_tonal",
    "too_vocal",
    "bad_density",
    "bad_tonal",
    "too_obvious",
    "interesting_adjacent",
    "wrong_energy",
    "wrong_texture",
    "bad_transition_risk",
]
EvaluationTrackId = Annotated[int, Field(ge=1)]
EvaluationTopK = Annotated[int, Field(ge=1, le=100)]
ClassifierPreference = Annotated[float, Field(ge=-1.0, le=1.0)]
ClassifierRiskWeight = Annotated[float, Field(ge=0.0, le=1.0)]


class ScanRequest(BaseModel):
    root: str
    workers: int = Field(default=1, ge=1, le=64)


class TagRefreshRequest(BaseModel):
    workers: int = Field(default=1, ge=1, le=64)


class RelocateLibraryRequest(BaseModel):
    old_root: str
    new_root: str
    apply: bool = False


class DatabaseSwitchRequest(BaseModel):
    path: str


class AnalysisJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int | None = None
    models: list[str] = Field(default_factory=lambda: list(ANALYSIS_MODEL_ORDER))
    classifier_keys: list[str] = Field(default_factory=list)
    device: str = Field(default=DEFAULT_ANALYSIS_DEVICE, pattern=ANALYSIS_DEVICE_PATTERN)
    top_k: int = Field(default=DEFAULT_ANALYSIS_TOP_K, ge=MIN_ANALYSIS_TOP_K, le=MAX_ANALYSIS_TOP_K)
    track_batch_size: int = Field(
        default=DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
        ge=MIN_ANALYSIS_TRACK_BATCH_SIZE,
        le=MAX_ANALYSIS_TRACK_BATCH_SIZE,
    )
    inference_batch_size: int = Field(
        default=DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
        ge=MIN_ANALYSIS_INFERENCE_BATCH_SIZE,
        le=MAX_ANALYSIS_INFERENCE_BATCH_SIZE,
    )


class AudioDedupJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    root: str
    path_contains: list[str] = Field(default_factory=list)
    preset: str = Field(default="safe", pattern="^(safe|balanced|aggressive)$")
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    limit_groups: int | None = Field(default=None, ge=1)
    out_dir: str | None = None
    apply: bool = False
    confirmation: str | None = None


class ClassifierAnalyzeRequest(BaseModel):
    limit: int | None = None


class ClassifierResetRequest(BaseModel):
    classifiers: list[str] = Field(default_factory=list)


class AnalysisResetRequest(BaseModel):
    adapter: str = Field(pattern="^(sonara|maest|mert|clap)$")


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    seed_track_ids: list[int]
    limit: int = 10
    bpm_tolerance: float | None = None
    key_compatibility: str | None = None
    energy_min: float | None = None
    energy_max: float | None = None
    min_similarity: float | None = None
    epsilon: float | None = Field(default=None, alias="Epsilon")
    noise: float = 0.0


class SonaraMixerWeights(BaseModel):
    timbre: float = Field(default=1.0, ge=0.0, le=5.0)
    rhythm: float = Field(default=1.0, ge=0.0, le=5.0)
    dynamics: float = Field(default=0.8, ge=0.0, le=5.0)
    harmonic: float = Field(default=0.8, ge=0.0, le=5.0)
    tempo: float = Field(default=0.35, ge=0.0, le=5.0)


class SonaraModifiers(BaseModel):
    energy: float = Field(default=0.0, ge=-1.0, le=1.0)
    valence: float = Field(default=0.0, ge=-1.0, le=1.0)
    acousticness: float = Field(default=0.0, ge=-1.0, le=1.0)
    brightness: float = Field(default=0.0, ge=-1.0, le=1.0)
    rhythm_density: float = Field(default=0.0, ge=-1.0, le=1.0)
    dynamic_range: float = Field(default=0.0, ge=-1.0, le=1.0)
    loudness: float = Field(default=0.0, ge=-1.0, le=1.0)


class SonaraSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_track_ids: list[int]
    limit: int = Field(default=10, ge=1, le=500)
    mode: str = Field(default="balanced", pattern="^(balanced|vibe|sound|dj_transition|custom)$")
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    mixer_weights: SonaraMixerWeights | None = None
    modifiers: SonaraModifiers | None = None


class TextSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    positive_queries: list[str] = Field(default_factory=list)
    negative_queries: list[str] = Field(default_factory=list)
    adaptive_contrast: bool = True
    preset: str | None = None
    limit: int = Field(default=10, ge=1, le=500)
    min_similarity: float | None = None
    device: str = Field(default=DEFAULT_ANALYSIS_DEVICE, pattern=ANALYSIS_DEVICE_PATTERN)


class HybridSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_track_ids: list[EvaluationTrackId] = Field(min_length=1, max_length=5)
    sources: list[HybridSearchSource] = Field(default_factory=lambda: ["mert", "maest", "sonara", "clap"], min_length=1, max_length=4)
    weights: dict[str, float] | None = None
    score_profile: dict[str, Any] | None = None
    per_source: int = Field(default=30, ge=1, le=100)
    limit: int = Field(default=25, ge=1, le=100)
    rrf_k: int = Field(default=60, ge=1, le=1000)
    random_seed: int = 123
    transition_risk_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    transition_risk_version: Literal["v1", "v2"] = "v2"
    classifier_preferences: dict[str, ClassifierPreference] = Field(default_factory=dict)
    classifier_risk_weights: dict[str, ClassifierRiskWeight] = Field(default_factory=dict)
    include_diagnostics: bool = True
    record_session: bool = False

    @model_validator(mode="after")
    def reject_multiple_weight_inputs(self) -> "HybridSearchRequest":
        if self.weights is not None and self.score_profile is not None:
            raise ValueError("Provide either weights or score_profile, not both")
        if len(set(self.seed_track_ids)) != len(self.seed_track_ids):
            raise ValueError("seed_track_ids must be unique")
        return self


class HybridSearchResult(BaseModel):
    track: dict[str, Any]
    score: float
    total_score: float
    calibrated_score: None = None
    adjusted_score: float
    transition_risk: float | None = None
    transition_risk_penalty: float
    transition_risk_weight: float
    raw_rrf_score: float
    rank: int
    score_breakdown: dict[str, dict[str, float | int]]
    risk_breakdown: dict[str, float | None] = Field(default_factory=dict)
    source_support: dict[str, dict[str, Any]] = Field(default_factory=dict)
    classifier_support: dict[str, dict[str, Any]] = Field(default_factory=dict)
    match_character: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    explanation: list[str] = Field(default_factory=list)
    transition_diagnostics: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    feedback: dict[str, Any] | None = None


class HybridSearchResponse(BaseModel):
    results: list[HybridSearchResult]
    warnings: list[str] = Field(default_factory=list)
    weights_used: dict[str, float]
    sources: list[HybridSearchSource]
    limitations: list[str]
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    session_id: int | None = None


class SetBuilderGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_mode: str = Field(default="manual", pattern="^(manual|auto)$")
    seed_track_ids: list[int] = Field(default_factory=list)
    auto_seed_count: int = Field(default=5, ge=1, le=5)
    mode: str = Field(default="balanced_set", pattern="^(similar_crate|weird_adjacent|balanced_set|discovery)$")
    limit: int = Field(default=24, ge=1, le=500)
    diversity: float = Field(default=0.35, ge=0.0, le=1.0)
    energy_curve: str = Field(default="balanced", pattern="^(warmup|balanced|peak|wave)$")
    bpm_mode: str = Field(default="general", pattern="^(general|low_to_high|high_to_low)$")
    bpm_change: str = Field(default="medium", pattern="^(slow|medium|fast)$")
    bpm_start: float | None = Field(default=None, ge=20.0, le=300.0)
    bpm_target: float | None = Field(default=None, ge=20.0, le=300.0)
    classifier_preferences: dict[str, Annotated[float, Field(ge=-1.0, le=1.0)]] = Field(default_factory=dict)
    classifier_flows: dict[str, Literal["flat", "rise", "fall"]] = Field(default_factory=dict)
    random_seed: int | None = None


class FilteredTracksRequest(BaseModel):
    query: str = ""
    search_mode: str = Field(default="like", pattern="^(like|fts)$")
    preset: str = Field(default="all", pattern="^(all|syncopated)$")
    liked: bool = False
    classifier_min_scores: dict[str, float] = Field(default_factory=dict)


class TrackLikedRequest(BaseModel):
    liked: bool


class ExportRequest(BaseModel):
    name: str
    track_ids: list[int]
    output_dir: str
    format: str = Field(default="m3u", pattern="^(m3u|csv)$")


class GenreTagRequest(BaseModel):
    track_ids: list[int] | None = None


class EvaluationPairFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: int | None = Field(default=None, ge=1)
    seed_track_ids: list[EvaluationTrackId] = Field(min_length=1, max_length=5)
    candidate_track_id: int = Field(ge=1)
    rating: int = Field(ge=0, le=3)
    reason_tags: list[EvaluationPairReasonTag] = Field(default_factory=list)
    notes: str | None = None
    source: str = Field(default="manual", min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_seed_track_ids(self) -> "EvaluationPairFeedbackRequest":
        if len(set(self.seed_track_ids)) != len(self.seed_track_ids):
            raise ValueError("seed_track_ids must be unique")
        return self


class EvaluationTransitionFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outgoing_track_id: int = Field(ge=1)
    incoming_track_id: int = Field(ge=1)
    rating: int = Field(ge=0, le=3)
    risk_tags: list[str] = Field(default_factory=list)
    notes: str | None = None
    source: str = Field(default="manual", min_length=1)


class EvaluationSourceProfileRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_track_ids: list[EvaluationTrackId] | None = Field(default=None, max_length=200)
    sample_count: int = Field(default=50, ge=1, le=200)
    sources: list[EvaluationSource] = Field(default_factory=lambda: ["mert", "maest", "sonara", "clap"], min_length=1, max_length=4)
    per_source: int = Field(default=30, ge=1, le=100)
    top_k: list[EvaluationTopK] = Field(default_factory=lambda: [10], min_length=1, max_length=5)
    random_seed: int = 123
    profile_name: str | None = None
    include_profile: bool = True


class EvaluationApplyScoreProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: dict[str, Any] | None = None
    weights: dict[str, float] | None = None
    name: str | None = None
    k: list[EvaluationTopK] = Field(default_factory=lambda: [5, 10], min_length=1, max_length=5)
    rrf_k: int = Field(default=60, ge=1, le=1000)

    @model_validator(mode="after")
    def require_profile_or_weights(self) -> "EvaluationApplyScoreProfileRequest":
        has_profile = self.profile is not None
        has_weights = self.weights is not None
        if has_profile == has_weights:
            raise ValueError("Provide exactly one of profile or weights")
        return self


class EvaluationWeightedCandidatesRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: dict[str, Any] | None = None
    weights: dict[str, float] | None = None
    name: str | None = None
    seed_track_ids: list[EvaluationTrackId] | None = Field(default=None, max_length=200)
    sample_count: int = Field(default=50, ge=1, le=200)
    sources: list[EvaluationSource] | None = Field(default=None, min_length=1, max_length=4)
    per_source: int = Field(default=30, ge=1, le=100)
    random_seed: int = 123
    rrf_k: int = Field(default=60, ge=1, le=1000)
    transition_risk_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    record_session: bool = False
    limit_per_seed: int = Field(default=30, ge=1, le=100)

    @model_validator(mode="after")
    def require_profile_or_weights(self) -> "EvaluationWeightedCandidatesRunRequest":
        has_profile = self.profile is not None
        has_weights = self.weights is not None
        if has_profile == has_weights:
            raise ValueError("Provide exactly one of profile or weights")
        return self
