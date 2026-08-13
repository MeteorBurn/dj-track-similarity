from __future__ import annotations

from typing import Annotated, Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .analysis_config import (
    ANALYSIS_DEVICE_PATTERN,
    DEFAULT_ANALYSIS_DEVICE,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    ML_ANALYSIS_MODEL_ORDER,
    DEFAULT_ANALYSIS_TOP_K,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    DEFAULT_SONARA_BATCH_SIZE,
    MAX_ANALYSIS_INFERENCE_BATCH_SIZE,
    MAX_ANALYSIS_TOP_K,
    MAX_ANALYSIS_TRACK_BATCH_SIZE,
    MAX_SONARA_BATCH_SIZE,
    MIN_ANALYSIS_INFERENCE_BATCH_SIZE,
    MIN_ANALYSIS_TOP_K,
    MIN_ANALYSIS_TRACK_BATCH_SIZE,
    MIN_SONARA_BATCH_SIZE,
)


EmbeddingSource = Literal["mert", "maest", "muq", "clap"]
EvaluationSource = Literal["mert", "maest", "muq", "sonara", "clap"]
ReferenceCompareModel = Literal["clap", "mert", "muq", "maest", "sonara"]
ReferenceCompareVerdict = Literal[
    "mood", "palette", "instruments", "groove", "genre", "transition", "miss"
]
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
TrackId = Annotated[int, Field(ge=1)]
ClassifierPreference = Annotated[float, Field(ge=-1.0, le=1.0)]
ClassifierRiskWeight = Annotated[float, Field(ge=0.0, le=1.0)]


class ScanRequest(BaseModel):
    root: str
    workers: int = Field(default=8, ge=1, le=64)
    limit: int | None = Field(default=None, ge=1, le=100_000)


class TagRefreshRequest(BaseModel):
    workers: int = Field(default=8, ge=1, le=64)


class RelocateLibraryRequest(BaseModel):
    old_root: str
    new_root: str
    apply: bool = False


class DatabaseSwitchRequest(BaseModel):
    path: str


class DatabaseStateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | None
    evaluation_path: str | None
    catalog_uuid: str | None
    selected: bool


class AnalysisJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int | None = None
    models: list[str] = Field(default_factory=lambda: list(ML_ANALYSIS_MODEL_ORDER))
    device: str = Field(
        default=DEFAULT_ANALYSIS_DEVICE, pattern=ANALYSIS_DEVICE_PATTERN
    )
    top_k: int = Field(
        default=DEFAULT_ANALYSIS_TOP_K, ge=MIN_ANALYSIS_TOP_K, le=MAX_ANALYSIS_TOP_K
    )
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
    sonara_batch_size: int = Field(
        default=DEFAULT_SONARA_BATCH_SIZE,
        ge=MIN_SONARA_BATCH_SIZE,
        le=MAX_SONARA_BATCH_SIZE,
    )


class ClassifierAnalyzeRequest(BaseModel):
    limit: int | None = None


class SonaraPipelineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_size: int = Field(
        default=DEFAULT_SONARA_BATCH_SIZE,
        ge=MIN_SONARA_BATCH_SIZE,
        le=MAX_SONARA_BATCH_SIZE,
    )


class MlPipelineSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    models: list[str] = Field(default_factory=lambda: list(ML_ANALYSIS_MODEL_ORDER))
    device: str = Field(
        default=DEFAULT_ANALYSIS_DEVICE, pattern=ANALYSIS_DEVICE_PATTERN
    )
    top_k: int = Field(
        default=DEFAULT_ANALYSIS_TOP_K, ge=MIN_ANALYSIS_TOP_K, le=MAX_ANALYSIS_TOP_K
    )
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


class AnalysisPipelineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stages: list[Literal["sonara", "ml"]]
    limit: int | None = None
    sonara: SonaraPipelineSettings = Field(default_factory=SonaraPipelineSettings)
    ml: MlPipelineSettings = Field(default_factory=MlPipelineSettings)


class ClassifierResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classifier_key: str = Field(min_length=1)


class AnalysisResetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_family: Literal["sonara", "maest", "mert", "muq", "clap"]


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_family: Literal["maest", "mert", "muq", "clap"] = "mert"
    seed_track_ids: list[TrackId] = Field(min_length=1, max_length=5)
    limit: int = Field(default=10, ge=1, le=500)
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    epsilon: float | None = Field(default=None, ge=0.0)
    noise: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def reject_duplicate_seed_track_ids(self) -> "SearchRequest":
        if len(set(self.seed_track_ids)) != len(self.seed_track_ids):
            raise ValueError("seed_track_ids must be unique")
        return self


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
    vocalness: float = Field(default=0.0, ge=-1.0, le=1.0)
    aggression: float = Field(default=0.0, ge=-1.0, le=1.0)


class SonaraSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_track_ids: list[int]
    limit: int = Field(default=10, ge=1, le=500)
    mode: str = Field(
        default="balanced", pattern="^(balanced|vibe|sound|dj_transition|custom)$"
    )
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    mixer_weights: SonaraMixerWeights | None = None
    modifiers: SonaraModifiers | None = None


class SonaraRandomTrackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exclude_track_ids: list[TrackId] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_exclusions(self) -> "SonaraRandomTrackRequest":
        if len(set(self.exclude_track_ids)) != len(self.exclude_track_ids):
            raise ValueError("exclude_track_ids must be unique")
        return self


class TextSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    positive_queries: list[str] = Field(default_factory=list)
    negative_queries: list[str] = Field(default_factory=list)
    adaptive_contrast: bool = True
    preset: str | None = None
    limit: int = Field(default=10, ge=1, le=500)
    min_similarity: float | None = None
    device: str = Field(
        default=DEFAULT_ANALYSIS_DEVICE, pattern=ANALYSIS_DEVICE_PATTERN
    )


class TrackIdentityRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    track_id: TrackId
    catalog_uuid: str = Field(min_length=1)
    track_uuid: str = Field(min_length=1)


class ReferenceCompareRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    seed_track_id: EvaluationTrackId
    models: list[ReferenceCompareModel] = Field(
        default_factory=lambda: ["clap", "mert", "muq", "maest", "sonara"],
        min_length=1,
        max_length=5,
    )
    limit: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def reject_duplicate_models(self) -> "ReferenceCompareRequest":
        if len(set(self.models)) != len(self.models):
            raise ValueError("models must be unique")
        return self


class ReferenceCompareVerdictRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    seed: TrackIdentityRequest
    candidate: TrackIdentityRequest
    model: ReferenceCompareModel
    verdict: ReferenceCompareVerdict
    notes: str | None = None


class FilteredTracksRequest(BaseModel):
    query: str = ""
    search_mode: str = Field(default="like", pattern="^(like|fts)$")
    preset: str = Field(default="all", pattern="^(all|syncopated)$")
    liked: bool = False
    classifier_min_scores: dict[str, float] = Field(default_factory=dict)


class TrackMutationIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_uuid: str = Field(min_length=1)
    track_uuid: str = Field(min_length=1)


class TrackLikedRequest(TrackMutationIdentity):
    liked: bool


class ExportRequest(BaseModel):
    name: str
    track_ids: list[int]
    output_dir: str
    format: str = Field(default="m3u", pattern="^(m3u|csv)$")


class GenreTagRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    sources: list[EvaluationSource] = Field(
        default_factory=lambda: ["mert", "maest", "muq", "sonara", "clap"],
        min_length=1,
        max_length=5,
    )
    per_source: int = Field(default=30, ge=1, le=100)
    top_k: list[EvaluationTopK] = Field(
        default_factory=lambda: [10], min_length=1, max_length=5
    )
    random_seed: int = 123
    profile_name: str | None = None
    include_profile: bool = True


class EvaluationApplyScoreProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: dict[str, Any] | None = None
    weights: dict[str, float] | None = None
    name: str | None = None
    k: list[EvaluationTopK] = Field(
        default_factory=lambda: [5, 10], min_length=1, max_length=5
    )
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
    sources: list[EvaluationSource] | None = Field(
        default=None, min_length=1, max_length=5
    )
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


class _ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class SonaraStatusOutputResponse(_ResponseModel):
    output_kind: Literal["core", "embedding"]
    present_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)


class SonaraStatusResponse(_ResponseModel):
    catalog_uuid: str
    total_tracks: int = Field(ge=0)
    outputs: list[SonaraStatusOutputResponse]


class AnalysisCoverageResponse(_ResponseModel):
    sonara_core: bool
    maest_analysis: bool
    maest_embedding: bool
    mert: bool
    muq: bool
    clap: bool


class ClassifierScoreSummaryResponse(_ResponseModel):
    classifier_key: str
    score: float
    predicted_class: str
    score_bucket: Literal["low", "medium", "high"]
    confidence: float


class FileTechnicalResponse(_ResponseModel):
    file_size_bytes: int
    file_modified_ns: int
    audio_format: str | None
    sample_rate_hz: int | None
    channel_count: int | None
    bit_rate_bps: int | None
    bit_depth: int | None
    audio_duration_seconds: float | None
    last_scanned_at: str
    missing_since: str | None


class FileTagsResponse(_ResponseModel):
    title: str | None
    artist: str | None
    album: str | None
    tag_bpm: float | None
    tag_key: str | None
    comment: str | None
    year: int | None
    label: str | None
    country: str | None
    track_number: str | None
    genres: list[str]
    tags_read_at: str


class VectorSummaryResponse(_ResponseModel):
    vector_type: str
    dim: int


class SonaraCoreResponse(_ResponseModel):
    detected_bpm: float | None
    raw_bpm: float | None
    bpm_confidence: float | None
    onset_density_per_second: float | None
    beat_count: int | None
    tempo_variability: float | None
    beat_grid_offset_seconds: float | None
    beat_grid_stability: float | None
    bpm_candidates: list[dict]  # decoded from bpm_candidates_json
    detected_key_name: str | None
    detected_key_camelot: str | None
    key_confidence: float | None
    predominant_chord: str | None
    chord_changes_per_second: float | None
    key_candidates: list[dict]  # decoded from key_candidates_json
    energy_score: float | None
    energy_level: int | None
    danceability_score: float | None
    valence_score: float | None
    acousticness_score: float | None
    dissonance_score: float | None
    spectral_centroid_hz: float | None
    spectral_bandwidth_hz: float | None
    spectral_rolloff_hz: float | None
    spectral_flatness: float | None
    zero_crossing_rate: float | None
    rms_mean: float | None
    rms_max: float | None
    integrated_loudness_lufs: float | None
    dynamic_range_db: float | None
    true_peak_dbtp: float | None
    replay_gain_db: float | None
    max_momentary_loudness_lufs: float | None
    loudness_range_lu: float | None
    analyzed_duration_seconds: float | None
    intro_end_seconds: float | None
    outro_start_seconds: float | None
    leading_silence_seconds: float | None
    trailing_silence_seconds: float | None
    energy_curve_hop_seconds: float | None
    energy_curve_sample_count: int | None
    energy_curve_min: float | None
    energy_curve_max: float | None
    energy_curve_mean: float | None
    energy_curve_stddev: float | None
    vocal_probability: float | None
    mood_happy_score: float | None
    mood_aggressive_score: float | None
    mood_relaxed_score: float | None
    mood_sad_score: float | None
    aggression_score: float | None
    aggression_confidence: float | None
    aggression_forcefulness: float | None
    aggression_harshness: float | None
    aggression_tension: float | None
    aggression_rhythm: float | None
    vector_summaries: list[VectorSummaryResponse]
    analyzed_at: str


class MaestGenreResponse(_ResponseModel):
    rank: int
    genre_name: str
    score: float


class MaestResponse(_ResponseModel):
    syncopated_rhythm: bool | None
    genres: list[MaestGenreResponse]
    analyzed_at: str


class EmbeddingSummaryResponse(_ResponseModel):
    analysis_family: str
    dim: int
    normalization: str
    analyzed_at: str


class ClassifierScoreDetailResponse(ClassifierScoreSummaryResponse):
    probabilities: dict[str, float]
    feature_set: str
    feature_names: list[str]
    positive_label: str
    analyzed_at: str


class TrackSummaryResponse(_ResponseModel):
    track_id: int
    catalog_uuid: str
    track_uuid: str
    file_path: str
    title: str | None
    artist: str | None
    album: str | None
    tag_bpm: float | None
    tag_key: str | None
    audio_duration_seconds: float | None
    liked: bool
    analysis_coverage: AnalysisCoverageResponse
    classifier_scores: list[ClassifierScoreSummaryResponse]


class TrackDetailResponse(TrackSummaryResponse):
    file: FileTechnicalResponse
    file_tags: FileTagsResponse | None
    sonara_core: SonaraCoreResponse | None
    maest: MaestResponse | None
    embeddings: list[EmbeddingSummaryResponse]
    classifier_scores_detail: list[ClassifierScoreDetailResponse]


class TrackPageResponse(_ResponseModel):
    items: list[TrackSummaryResponse]
    total: int
    limit: int
    offset: int


class LibrarySummaryResponse(_ResponseModel):
    tracks: int
    sonara: int
    maest_analysis: int
    maest_embedding: int
    mert: int
    muq: int
    clap: int
    liked: int
    classifiers: int


class AnalysisResetResponse(_ResponseModel):
    feature_rows_deleted: int
    embedding_rows_deleted: int
    classifier_rows_deleted: int


class ClearLibraryResponse(_ResponseModel):
    tracks_deleted: int
    feature_rows_deleted: int
    embedding_rows_deleted: int
    classifier_rows_deleted: int


class GenreTagApplyResultResponse(_ResponseModel):
    catalog_uuid: str
    track_id: int
    track_uuid: str
    file_path: str
    tags: dict[str, str]
    status: Literal["applied", "skipped", "failed"]
    message: str
    error: str | None = None


class SimilaritySearchResultResponse(_ResponseModel):
    track: TrackSummaryResponse
    score: float
    score_breakdown: dict[str, float] | None = None
