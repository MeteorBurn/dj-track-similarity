"""Current Core schema bootstrap helpers and structural validation."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from .db_structure import require_current_structure


SQLITE_BUSY_TIMEOUT_SECONDS = 30


_CORE_COLUMNS: dict[str, tuple[str, ...]] = {
    "library_catalog": ("singleton_id", "catalog_uuid", "created_at", "updated_at"),
    "library_settings": ("setting_key", "setting_value", "updated_at"),
    "tracks": (
        "track_id",
        "track_uuid",
        "file_path",
        "file_size_bytes",
        "file_modified_ns",
        "audio_format",
        "audio_codec",
        "sample_rate_hz",
        "channel_count",
        "bit_rate_bps",
        "audio_duration_seconds",
        "content_generation",
        "last_scanned_at",
        "missing_since",
        "created_at",
        "updated_at",
    ),
    "file_tags": (
        "track_id",
        "title",
        "artist",
        "album",
        "tag_bpm",
        "tag_key",
        "comment",
        "year",
        "label",
        "catalog_number",
        "country",
        "isrc",
        "track_number",
        "disc_number",
        "genres_json",
        "tags_read_at",
    ),
    "sonara": (
        "track_id",
        "content_generation",
        "detected_bpm",
        "raw_bpm",
        "bpm_confidence",
        "onset_density_per_second",
        "beat_count",
        "tempo_variability",
        "beat_grid_offset_seconds",
        "beat_grid_stability",
        "bpm_candidates_json",
        "detected_key_name",
        "detected_key_camelot",
        "key_confidence",
        "predominant_chord",
        "chord_changes_per_second",
        "key_candidates_json",
        "energy_score",
        "energy_level",
        "danceability_score",
        "valence_score",
        "acousticness_score",
        "dissonance_score",
        "spectral_centroid_hz",
        "spectral_bandwidth_hz",
        "spectral_rolloff_hz",
        "spectral_flatness",
        "zero_crossing_rate",
        "rms_mean",
        "rms_max",
        "integrated_loudness_lufs",
        "dynamic_range_db",
        "true_peak_dbtp",
        "replay_gain_db",
        "max_momentary_loudness_lufs",
        "loudness_range_lu",
        "analyzed_duration_seconds",
        "intro_end_seconds",
        "outro_start_seconds",
        "leading_silence_seconds",
        "trailing_silence_seconds",
        "energy_curve_hop_seconds",
        "energy_curve_sample_count",
        "energy_curve_min",
        "energy_curve_max",
        "energy_curve_mean",
        "energy_curve_stddev",
        "vocal_probability",
        "mood_happy_score",
        "mood_aggressive_score",
        "mood_relaxed_score",
        "mood_sad_score",
        "mfcc_mean_blob",
        "chroma_mean_blob",
        "spectral_contrast_mean_blob",
        "analyzed_at",
    ),
    "maest_scores": (
        "track_id",
        "content_generation",
        "syncopated_rhythm",
        "genres_json",
        "analyzed_at",
    ),
    "classifier_scores": (
        "track_id",
        "track_uuid",
        "classifier_key",
        "content_generation",
        "feature_set",
        "feature_names_json",
        "positive_label",
        "predicted_class",
        "score_bucket",
        "score",
        "confidence",
        "probabilities_json",
        "analyzed_at",
    ),
    "likes": ("track_id", "liked_at"),
    "pair_feedback": (
        "feedback_id",
        "seed_track_id",
        "candidate_track_id",
        "rating",
        "reason_tags_json",
        "notes",
        "source",
        "created_at",
        "updated_at",
    ),
    "transition_feedback": (
        "transition_feedback_id",
        "outgoing_track_id",
        "incoming_track_id",
        "rating",
        "risk_tags_json",
        "notes",
        "source",
        "created_at",
    ),
    "track_search_fts": (
        "track_id",
        "file_path",
        "title",
        "artist",
        "album",
        "comment",
        "label",
        "catalog_number",
        "country",
        "isrc",
        "year",
        "track_number",
        "disc_number",
        "file_genres",
        "maest_genres",
    ),
}

_FTS_SHADOW_TABLES = {
    "track_search_fts_config",
    "track_search_fts_content",
    "track_search_fts_data",
    "track_search_fts_docsize",
    "track_search_fts_idx",
}
_CORE_INDEXES = {
    "idx_classifier_scores_lookup",
    "idx_file_tags_sort",
    "idx_likes_liked_at",
    "idx_maest_scores_generation",
    "idx_pair_feedback_candidate",
    "idx_pair_feedback_seed_rating",
    "idx_sonara_generation",
    "idx_tracks_missing",
    "idx_transition_feedback_incoming",
    "idx_transition_feedback_outgoing",
}
_CORE_TRIGGERS = {
    "library_catalog_immutable_insert",
    "library_catalog_immutable_update",
    "library_catalog_immutable_delete",
}


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def insert_library_catalog(
    connection: sqlite3.Connection,
    catalog_uuid: str,
    *,
    created_at: str | None = None,
) -> str:
    if not isinstance(catalog_uuid, str):
        raise ValueError("catalog_uuid must be a string")
    clean_uuid = catalog_uuid.strip()
    if not clean_uuid:
        raise ValueError("catalog_uuid must be a non-empty string")
    if connection.execute("SELECT COUNT(*) FROM library_catalog").fetchone()[0] != 0:
        raise RuntimeError("library_catalog is already initialized")
    timestamp = created_at or _utc_timestamp()
    connection.execute(
        """
        INSERT INTO library_catalog(singleton_id, catalog_uuid, created_at, updated_at)
        VALUES (1, ?, ?, ?)
        """,
        (clean_uuid, timestamp, timestamp),
    )
    return clean_uuid


def validate_core_schema(
    connection: sqlite3.Connection,
    *,
    expected_catalog_uuid: str | None = None,
    database_path: str = "<connected Core database>",
) -> str:
    catalog_uuid = require_current_structure(
        connection,
        "core",
        database_path,
    )
    if expected_catalog_uuid is not None and catalog_uuid != expected_catalog_uuid:
        raise RuntimeError("Core database belongs to another library catalog")

    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise RuntimeError(
            f"SQLite Core foreign-key violations: {foreign_key_errors[:5]}"
        )
    return catalog_uuid
