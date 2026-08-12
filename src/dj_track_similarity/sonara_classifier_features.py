"""Resolve SONARA feature names stored in promoted classifier manifests."""

from __future__ import annotations

from dataclasses import fields
from types import MappingProxyType

from .db_ddl import SonaraRow


SONARA_CLASSIFIER_VECTOR_DIMS = MappingProxyType(
    {
        "mfcc_mean_blob": 13,
        "chroma_mean_blob": 12,
        "spectral_contrast_mean_blob": 7,
    }
)
SONARA_CLASSIFIER_VECTOR_ALIASES = MappingProxyType(
    {
        "mfcc_mean": "mfcc_mean_blob",
        "chroma_mean": "chroma_mean_blob",
        "spectral_contrast_mean": "spectral_contrast_mean_blob",
    }
)
SONARA_CLASSIFIER_SCALAR_ALIASES = MappingProxyType(
    {
        "bpm": "detected_bpm",
        "onset_density": "onset_density_per_second",
        "n_beats": "beat_count",
        "loudness_lufs": "integrated_loudness_lufs",
        "spectral_centroid_mean": "spectral_centroid_hz",
        "duration_sec": "analyzed_duration_seconds",
        "energy": "energy_score",
        "danceability": "danceability_score",
        "valence": "valence_score",
        "acousticness": "acousticness_score",
        "chord_change_rate": "chord_changes_per_second",
        "dissonance": "dissonance_score",
        "spectral_bandwidth_mean": "spectral_bandwidth_hz",
        "spectral_rolloff_mean": "spectral_rolloff_hz",
        "spectral_flatness_mean": "spectral_flatness",
        "bpm_raw": "raw_bpm",
        "intro_end_sec": "intro_end_seconds",
        "outro_start_sec": "outro_start_seconds",
        "true_peak_db": "true_peak_dbtp",
        "replaygain_db": "replay_gain_db",
        "loudness_momentary_max_db": "max_momentary_loudness_lufs",
        "grid_offset_sec": "beat_grid_offset_seconds",
        "grid_stability": "beat_grid_stability",
        "leading_silence_sec": "leading_silence_seconds",
        "trailing_silence_sec": "trailing_silence_seconds",
        "mood_happy": "mood_happy_score",
        "mood_aggressive": "mood_aggressive_score",
        "mood_relaxed": "mood_relaxed_score",
        "mood_sad": "mood_sad_score",
    }
)
_NON_NUMERIC_SONARA_FIELDS = frozenset(
    {
        "track_id",
        "bpm_candidates_json",
        "detected_key_name",
        "detected_key_camelot",
        "predominant_chord",
        "key_candidates_json",
        "analyzed_at",
        *SONARA_CLASSIFIER_VECTOR_DIMS,
    }
)
_STORED_SONARA_SCALAR_FIELDS = frozenset(
    field.name for field in fields(SonaraRow)
) - _NON_NUMERIC_SONARA_FIELDS


def resolve_sonara_classifier_feature(
    key: str,
) -> tuple[str, int | None] | None:
    """Return the stored SONARA field and optional vector index for a key.

    Rhythm Lab writes concise names such as ``bpm`` and ``mfcc_mean:0`` into a
    model manifest.  Scoring reads the database's explicit column names, so the
    aliases must be resolved before validating or reading a promoted artifact.
    Direct database field names remain supported for non-Rhythm-Lab artifacts.
    """

    field_name, separator, index_text = key.rpartition(":")
    if separator:
        if not index_text.isdigit():
            return None
        stored_name = SONARA_CLASSIFIER_VECTOR_ALIASES.get(field_name, field_name)
        dimension = SONARA_CLASSIFIER_VECTOR_DIMS.get(stored_name)
        index = int(index_text)
        if dimension is None or not 0 <= index < dimension:
            return None
        return stored_name, index

    stored_name = SONARA_CLASSIFIER_SCALAR_ALIASES.get(key, key)
    if stored_name not in _STORED_SONARA_SCALAR_FIELDS:
        return None
    return stored_name, None
