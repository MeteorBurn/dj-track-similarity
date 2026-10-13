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
    mert_v2: bool = False
    sheetsage2: bool = False
    muq: bool = False
    mulan: bool = False
    clap: bool = False



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
    file_size_bytes: int
    audio_format: str | None
    sample_rate_hz: int | None
    bit_rate_bps: int | None
    bit_depth: int | None
    title: str | None
    artist: str | None
    album: str | None
    tag_bpm: float | None
    tag_key: str | None
    sonara_bpm: float | None
    sonara_key_camelot: str | None
    maest_genres: tuple[MaestGenre, ...]
    audio_duration_seconds: float | None
    liked: bool
    analysis_coverage: AnalysisCoverage
    classifier_scores: tuple[ClassifierScoreSummary, ...]


@dataclass(frozen=True)
class SheetSage2Interval:
    label: str
    end_s: float


@dataclass(frozen=True)
class SheetSage2Rhythm:
    eighth_position: int
    numerator: int | None
    denominator: int | None


@dataclass(frozen=True)
class SheetSage2Note:
    start_s: float
    end_s: float
    pitch_midi: int
    source_track: Literal["vocal", "instrumental"]


@dataclass(frozen=True)
class SheetSage2Event:
    time_s: float
    rhythm: SheetSage2Rhythm | None
    chord: SheetSage2Interval | None
    key: SheetSage2Interval | None
    structure: SheetSage2Interval | None
    melody: tuple[SheetSage2Note, ...]


@dataclass(frozen=True)
class SheetSage2Timeline:
    catalog_uuid: str
    track_id: int
    track_uuid: str
    analyzed_at: str
    duration_s: float
    events: tuple[SheetSage2Event, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SheetSage2Features:
    """Stored whole-track summaries from one current SheetSage2 analysis."""

    beat_count: int
    downbeat_count: int
    bpm_median: float | None
    bpm_min: float | None
    bpm_max: float | None
    bpm_std: float | None
    dominant_meter: str | None
    meter_change_count: int
    meter_durations_s: dict[str, float]
    chord_segment_count: int
    chord_unique_count: int
    chord_change_count: int
    chord_change_rate_per_minute: float
    dominant_chord: str | None
    chord_durations_s: dict[str, float]
    dominant_key: str | None
    key_change_count: int
    major_fraction: float
    minor_fraction: float
    key_durations_s: dict[str, float]
    section_count: int
    section_counts: dict[str, int]
    section_durations_s: dict[str, float]
    intro_end_s: float | None
    outro_start_s: float | None
    first_chorus_start_s: float | None
    melody_all_event_count: int
    melody_all_pitch_min: float | None
    melody_all_pitch_median: float | None
    melody_all_pitch_max: float | None
    melody_all_pitch_range: float | None
    melody_all_duration_min: float | None
    melody_all_duration_median: float | None
    melody_all_duration_mean: float | None
    melody_all_duration_max: float | None
    melody_all_duration_std: float | None
    melody_all_density_per_second: float
    melody_all_coverage_fraction: float
    melody_all_interval_pair_count: int
    melody_all_interval_abs_mean: float | None
    melody_all_interval_histogram: dict[str, int]
    melody_vocal_event_count: int
    melody_vocal_pitch_min: float | None
    melody_vocal_pitch_median: float | None
    melody_vocal_pitch_max: float | None
    melody_vocal_pitch_range: float | None
    melody_vocal_duration_min: float | None
    melody_vocal_duration_median: float | None
    melody_vocal_duration_mean: float | None
    melody_vocal_duration_max: float | None
    melody_vocal_duration_std: float | None
    melody_vocal_density_per_second: float
    melody_vocal_coverage_fraction: float
    melody_vocal_interval_pair_count: int
    melody_vocal_interval_abs_mean: float | None
    melody_vocal_interval_histogram: dict[str, int]
    melody_instrumental_event_count: int
    melody_instrumental_pitch_min: float | None
    melody_instrumental_pitch_median: float | None
    melody_instrumental_pitch_max: float | None
    melody_instrumental_pitch_range: float | None
    melody_instrumental_duration_min: float | None
    melody_instrumental_duration_median: float | None
    melody_instrumental_duration_mean: float | None
    melody_instrumental_duration_max: float | None
    melody_instrumental_duration_std: float | None
    melody_instrumental_density_per_second: float
    melody_instrumental_coverage_fraction: float
    melody_instrumental_interval_pair_count: int
    melody_instrumental_interval_abs_mean: float | None
    melody_instrumental_interval_histogram: dict[str, int]
    analyzed_at: str


@dataclass(frozen=True)
class TrackDetail(TrackSummary):
    file: FileTechnical
    file_tags: FileTags | None
    sonara_core: SonaraCore | None
    maest: MaestAnalysis | None
    embeddings: tuple[EmbeddingSummary, ...]
    classifier_scores_detail: tuple[ClassifierScoreDetail, ...]
    sheetsage2_features: SheetSage2Features | None = None


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
    mert_v2: int
    sheetsage2: int
    muq: int
    mulan: int
    clap: int
    liked: int
    classifiers: int
    # The BPM range this library analyses SONARA with. Both bounds are None
    # while no analysis job has claimed one, and when the claim is analysis
    # without a range, which sonara_bpm_range_none tells apart.
    sonara_bpm_min: float | None = None
    sonara_bpm_max: float | None = None
    sonara_bpm_range_none: bool = False
