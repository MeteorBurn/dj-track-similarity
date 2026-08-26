"""Typed domain models for the library read path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping


JsonObject = Mapping[str, object]
ScoreBucket = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class AnalysisCoverage:
    sonara_core: bool = False
    maest_analysis: bool = False
    maest_embedding: bool = False
    mert: bool = False
    muq: bool = False
    mulan: bool = False
    clap: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "sonara_core": self.sonara_core,
            "maest_analysis": self.maest_analysis,
            "maest_embedding": self.maest_embedding,
            "mert": self.mert,
            "muq": self.muq,
            "mulan": self.mulan,
            "clap": self.clap,
        }


@dataclass(frozen=True)
class ClassifierScoreSummary:
    classifier_key: str
    score: float
    predicted_class: str
    score_bucket: ScoreBucket
    confidence: float


@dataclass(frozen=True)
class ClassifierScoreDetail(ClassifierScoreSummary):
    probabilities: Mapping[str, float]
    feature_set: str
    feature_names: tuple[str, ...]
    positive_label: str
    analyzed_at: str


@dataclass(frozen=True)
class FileTechnical:
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


@dataclass(frozen=True)
class FileTags:
    title: str | None
    artist: str | None
    album: str | None
    track_number: str | None
    label: str | None
    country: str | None
    year: int | None
    tag_key: str | None
    tag_bpm: float | None
    comment: str | None
    genres: tuple[str, ...]
    tags_read_at: str


@dataclass(frozen=True)
class VectorSummary:
    vector_type: str
    dim: int


@dataclass(frozen=True)
class SonaraCore:
    analysis_schema_version: int
    bpm_min: float
    bpm_max: float
    detected_bpm: float | None
    raw_bpm: float | None
    bpm_confidence: float | None
    onset_density_per_second: float | None
    beat_count: int | None
    tempo_variability: float | None
    beat_grid_offset_seconds: float | None
    beat_grid_stability: float | None
    bpm_candidates: tuple[JsonObject, ...]
    detected_key_name: str | None
    detected_key_camelot: str | None
    key_confidence: float | None
    predominant_chord: str | None
    chord_changes_per_second: float | None
    key_candidates: tuple[JsonObject, ...]
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
    vector_summaries: tuple[VectorSummary, ...]
    analyzed_at: str


@dataclass(frozen=True)
class MaestGenre:
    rank: int
    genre_name: str
    score: float


@dataclass(frozen=True)
class MaestAnalysis:
    syncopated_rhythm: bool | None
    genres: tuple[MaestGenre, ...]
    analyzed_at: str


@dataclass(frozen=True)
class EmbeddingSummary:
    analysis_family: str
    dim: int
    normalization: str
    analyzed_at: str


@dataclass(frozen=True)
class TrackSummary:
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
    analysis_coverage: AnalysisCoverage
    classifier_scores: tuple[ClassifierScoreSummary, ...]


@dataclass(frozen=True)
class TrackDetail(TrackSummary):
    file: FileTechnical
    file_tags: FileTags | None
    sonara_core: SonaraCore | None
    maest: MaestAnalysis | None
    embeddings: tuple[EmbeddingSummary, ...]
    classifier_scores_detail: tuple[ClassifierScoreDetail, ...]


@dataclass(frozen=True)
class TrackPage:
    items: tuple[TrackSummary, ...]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class ExportTrackRow:
    track_id: int
    file_path: str
    artist: str | None
    title: str | None
    album: str | None
    tag_bpm: float | None
    tag_key: str | None
    sonara_bpm: float | None
    sonara_key: str | None
    sonara_energy: float | None

    @property
    def display_name(self) -> str:
        if self.artist and self.title:
            return f"{self.artist} - {self.title}"
        return self.title or Path(self.file_path).stem


@dataclass(frozen=True)
class GenreTagCandidate:
    catalog_uuid: str
    track_id: int
    track_uuid: str
    file_path: str
    expected_file_size_bytes: int
    expected_file_modified_ns: int
    genres: tuple[str, ...]
    maest_analyzed_at: str


@dataclass(frozen=True)
class LibrarySummary:
    tracks: int
    sonara: int
    maest_analysis: int
    maest_embedding: int
    mert: int
    muq: int
    mulan: int
    clap: int
    liked: int
    classifiers: int
    # The BPM range stored SONARA rows were analysed with, or None when the
    # library has no SONARA analysis yet or was analysed with mixed settings.
    sonara_bpm_min: float | None = None
    sonara_bpm_max: float | None = None

    def as_dict(self) -> dict[str, float | int | None]:
        return {
            "tracks": self.tracks,
            "sonara": self.sonara,
            "maest_analysis": self.maest_analysis,
            "maest_embedding": self.maest_embedding,
            "mert": self.mert,
            "muq": self.muq,
            "mulan": self.mulan,
            "clap": self.clap,
            "liked": self.liked,
            "classifiers": self.classifiers,
            "sonara_bpm_min": self.sonara_bpm_min,
            "sonara_bpm_max": self.sonara_bpm_max,
        }
