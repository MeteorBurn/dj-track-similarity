from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .analysis_config import (
    ANALYSIS_MODEL_ORDER,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
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
    models: list[str] = Field(default_factory=lambda: list(ANALYSIS_MODEL_ORDER), min_length=1)
    device: str = Field(default="auto", pattern="^(auto|cpu|cuda)$")
    top_k: int = Field(default=3, ge=1, le=10)
    track_batch_size: int = Field(default=DEFAULT_ANALYSIS_TRACK_BATCH_SIZE, ge=1, le=64)
    inference_batch_size: int = Field(default=DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE, ge=1, le=128)


class ClassifierAnalyzeRequest(BaseModel):
    limit: int | None = None


class ClassifierResetRequest(BaseModel):
    classifiers: list[str] = Field(default_factory=list)


class AnalysisResetRequest(BaseModel):
    adapter: str = Field(pattern="^(sonara|maest|mert|clap)$")


class SearchRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    seed_track_ids: list[int]
    lookback_track_ids: list[int] = Field(default_factory=list)
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
    seed_track_ids: list[int]
    lookback_track_ids: list[int] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=500)
    mode: str = Field(default="balanced", pattern="^(balanced|vibe|sound|dj_transition|custom)$")
    min_similarity: float | None = Field(default=None, ge=0.0, le=1.0)
    mixer_weights: SonaraMixerWeights | None = None
    modifiers: SonaraModifiers | None = None


class TextSearchRequest(BaseModel):
    query: str
    limit: int = Field(default=10, ge=1, le=500)
    min_similarity: float | None = None
    device: str = Field(default="auto", pattern="^(auto|cpu|cuda)$")


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
