"""V7-only Core schema bootstrap and validation."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache

from .db_schema_v7 import SCHEMA_VERSION, create_v7_schema


CURRENT_SCHEMA_VERSION = SCHEMA_VERSION
SQLITE_BUSY_TIMEOUT_SECONDS = 30
SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY = "sonara.active_release_hash"


_CORE_COLUMNS: dict[str, tuple[str, ...]] = {
    "library_catalog": ("singleton_id", "catalog_uuid", "created_at", "updated_at"),
    "library_settings": ("setting_key", "setting_value", "updated_at"),
    "contracts": (
        "contract_hash",
        "analysis_family",
        "output_kind",
        "model_name",
        "model_version",
        "release_hash",
        "canonical_payload_json",
        "created_at",
    ),
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
        "contract_hash",
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
        "contract_hash",
        "syncopated_rhythm",
        "genres_json",
        "analyzed_at",
    ),
    "classifier_scores": (
        "track_id",
        "classifier_key",
        "content_generation",
        "model_id",
        "feature_set",
        "feature_manifest_hash",
        "required_outputs_hash",
        "uses_sonara",
        "sonara_release_hash",
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
    "idx_contracts_family_output",
    "idx_contracts_release",
    "idx_file_tags_sort",
    "idx_likes_liked_at",
    "idx_maest_scores_contract_generation",
    "idx_pair_feedback_candidate",
    "idx_pair_feedback_seed_rating",
    "idx_sonara_contract_generation",
    "idx_tracks_missing",
    "idx_transition_feedback_incoming",
    "idx_transition_feedback_outgoing",
}
_CORE_TRIGGERS = {
    "library_catalog_immutable_insert",
    "library_catalog_immutable_update",
    "library_catalog_immutable_delete",
    "contracts_append_only_insert",
    "contracts_append_only_update",
    "contracts_append_only_delete",
}


def _normalized_schema_definitions(
    connection: sqlite3.Connection,
) -> tuple[tuple[str, str, str, str], ...]:
    rows = connection.execute(
        """
        SELECT type, name, tbl_name, sql
        FROM sqlite_master
        WHERE type IN ('table', 'index', 'trigger', 'view')
          AND name NOT LIKE 'sqlite_%'
          AND sql IS NOT NULL
        ORDER BY type, name
        """
    ).fetchall()
    return tuple(
        (
            str(object_type),
            str(name),
            str(table_name),
            " ".join(str(sql).split()),
        )
        for object_type, name, table_name, sql in rows
    )


def _schema_definition_fingerprint(
    definitions: tuple[tuple[str, str, str, str], ...],
) -> str:
    payload = json.dumps(
        definitions,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@lru_cache(maxsize=1)
def _expected_core_schema_definitions() -> tuple[tuple[str, str, str, str], ...]:
    connection = sqlite3.connect(":memory:")
    try:
        create_v7_schema(connection)
        return _normalized_schema_definitions(connection)
    finally:
        connection.close()


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
) -> str:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"SQLite Core schema version {version} is not supported; "
            f"expected clean v{CURRENT_SCHEMA_VERSION}"
        )

    actual_views = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='view'"
        )
    }
    if actual_views:
        raise RuntimeError(
            f"SQLite Core contains unexpected views: {sorted(actual_views)}"
        )

    actual_tables = _user_tables(connection)
    expected_tables = set(_CORE_COLUMNS) | _FTS_SHADOW_TABLES
    if actual_tables != expected_tables:
        missing = sorted(expected_tables - actual_tables)
        extra = sorted(actual_tables - expected_tables)
        raise RuntimeError(
            f"SQLite Core table set mismatch; missing={missing}, extra={extra}"
        )

    for table, expected_columns in _CORE_COLUMNS.items():
        actual_columns = tuple(
            str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
        )
        if actual_columns != expected_columns:
            raise RuntimeError(
                f"SQLite Core columns mismatch for {table}; "
                f"expected={list(expected_columns)}, actual={list(actual_columns)}"
            )

    actual_indexes = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    if actual_indexes != _CORE_INDEXES:
        raise RuntimeError(
            "SQLite Core index set mismatch; "
            f"missing={sorted(_CORE_INDEXES - actual_indexes)}, "
            f"extra={sorted(actual_indexes - _CORE_INDEXES)}"
        )

    actual_triggers = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        )
    }
    if actual_triggers != _CORE_TRIGGERS:
        raise RuntimeError(
            "SQLite Core trigger set mismatch; "
            f"missing={sorted(_CORE_TRIGGERS - actual_triggers)}, "
            f"extra={sorted(actual_triggers - _CORE_TRIGGERS)}"
        )

    actual_definitions = _normalized_schema_definitions(connection)
    expected_definitions = _expected_core_schema_definitions()
    if actual_definitions != expected_definitions:
        raise RuntimeError(
            "SQLite Core schema definition fingerprint mismatch; "
            f"expected={_schema_definition_fingerprint(expected_definitions)}, "
            f"actual={_schema_definition_fingerprint(actual_definitions)}"
        )

    rows = connection.execute(
        "SELECT singleton_id, catalog_uuid FROM library_catalog"
    ).fetchall()
    if len(rows) != 1 or int(rows[0][0]) != 1:
        raise RuntimeError("library_catalog must contain exactly singleton_id=1")
    catalog_uuid = str(rows[0][1]).strip()
    if not catalog_uuid:
        raise RuntimeError("library_catalog.catalog_uuid must be non-empty")
    if expected_catalog_uuid is not None and catalog_uuid != expected_catalog_uuid:
        raise RuntimeError("Core database belongs to another library catalog")

    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise RuntimeError(
            f"SQLite Core foreign-key violations: {foreign_key_errors[:5]}"
        )
    return catalog_uuid


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row[0]) for row in rows}
