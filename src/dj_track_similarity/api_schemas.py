from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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


class SetBuilderClassifierCurve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: float = Field(default=0.5, ge=0.0, le=1.0)
    end: float = Field(default=0.5, ge=0.0, le=1.0)


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
    classifier_targets: dict[str, float] = Field(default_factory=dict)
    classifier_avoid: dict[str, float] = Field(default_factory=dict)
    classifier_curves: dict[str, SetBuilderClassifierCurve] = Field(default_factory=dict)
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
