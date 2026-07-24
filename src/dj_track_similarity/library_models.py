"""Typed domain models for the v7 library read path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping


JsonObject = Mapping[str, object]
ScoreBucket = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class AnalysisCoverage:
    sonara_core: bool = False
    timeline: bool = False
    sonara_embedding: bool = False
    fingerprint: bool = False
    maest_analysis: bool = False
    maest_embedding: bool = False
    mert: bool = False
    muq: bool = False
    clap: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "sonara_core": self.sonara_core,
            "timeline": self.timeline,
            "sonara_embedding": self.sonara_embedding,
            "fingerprint": self.fingerprint,
            "maest_analysis": self.maest_analysis,
            "maest_embedding": self.maest_embedding,
            "mert": self.mert,
            "muq": self.muq,
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
    feature_manifest_hash: str
    required_outputs_hash: str
    model_id: str
    uses_sonara: bool
    sonara_release_hash: str | None
    positive_label: str
    analyzed_at: str


@dataclass(frozen=True)
class FileTechnical:
    file_size_bytes: int
    file_modified_ns: int
    audio_format: str | None
    audio_codec: str | None
    sample_rate_hz: int | None
    channel_count: int | None
    bit_rate_bps: int | None
    audio_duration_seconds: float | None
    last_scanned_at: str
    missing_since: str | None


@dataclass(frozen=True)
class FileTags:
    title: str | None
    artist: str | None
    album: str | None
    tag_bpm: float | None
    tag_key: str | None
    comment: str | None
    year: int | None
    label: str | None
    catalog_number: str | None
    country: str | None
    isrc: str | None
    track_number: str | None
    disc_number: str | None
    genres: tuple[str, ...]
    tags_read_at: str


@dataclass(frozen=True)
class VectorSummary:
    vector_type: str
    dim: int


@dataclass(frozen=True)
class SonaraCore:
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
    model_name: str
    model_version: str | None
    dim: int
    normalization: str
    analyzed_at: str


@dataclass(frozen=True)
class OptionalOutputs:
    timeline_fields: tuple[str, ...]
    sonara_embedding_available: bool
    audio_fingerprint_available: bool


@dataclass(frozen=True)
class TrackSummary:
    track_id: int
    catalog_uuid: str
    track_uuid: str
    content_generation: int
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
    optional_outputs: OptionalOutputs


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
    content_generation: int
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
    clap: int
    liked: int
    classifiers: int

    def as_dict(self) -> dict[str, int]:
        return {
            "tracks": self.tracks,
            "sonara": self.sonara,
            "maest_analysis": self.maest_analysis,
            "maest_embedding": self.maest_embedding,
            "mert": self.mert,
            "muq": self.muq,
            "clap": self.clap,
            "liked": self.liked,
            "classifiers": self.classifiers,
        }
