"""Current Core database DDL and typed Python domain models.

This module is standalone — it does NOT import from any other dj_track_similarity
module so it can be used as a migration target without circular dependencies.

Tables (emission order matches FK dependency order):
  1.  library_catalog        — singleton, catalog UUID binding
  2.  library_settings       — key-value settings store
  3.  tracks                 — identity + file facts (file_modified_ns INTEGER)
  4.  file_tags              — Mutagen tags per track
  5.  sonara                 — SONARA Core scalars + three short BLOB vectors
  6.  maest_scores           — MAEST genre predictions + syncopated_rhythm flag
  7.  classifier_scores      — Rhythm Lab classifier scores (predicted_class + score_bucket)
  8.  likes                  — user like per track
  9.  pair_feedback          — candidate pair ratings with reason_tags_json
  10. transition_feedback    — transition ratings with risk_tags_json
  11. track_search_fts       — FTS5 virtual table (human text only)

"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# DDL strings — one per table, in FK-safe emission order
# ---------------------------------------------------------------------------

_DDL_LIBRARY_CATALOG = """
CREATE TABLE library_catalog (
    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
    catalog_uuid TEXT    NOT NULL UNIQUE,
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);
CREATE TRIGGER library_catalog_immutable_insert
BEFORE INSERT ON library_catalog
WHEN EXISTS (SELECT 1 FROM library_catalog)
BEGIN
    SELECT RAISE(ABORT, 'library_catalog is immutable')
    WHERE NOT EXISTS (
        SELECT 1
        FROM library_catalog
        WHERE singleton_id IS NEW.singleton_id
          AND catalog_uuid IS NEW.catalog_uuid
          AND created_at IS NEW.created_at
          AND updated_at IS NEW.updated_at
    );
    SELECT RAISE(IGNORE);
END;
CREATE TRIGGER library_catalog_immutable_update
BEFORE UPDATE ON library_catalog
BEGIN
    SELECT RAISE(ABORT, 'library_catalog is immutable');
END;
CREATE TRIGGER library_catalog_immutable_delete
BEFORE DELETE ON library_catalog
BEGIN
    SELECT RAISE(ABORT, 'library_catalog is immutable');
END;
"""

_DDL_LIBRARY_SETTINGS = """
CREATE TABLE library_settings (
    setting_key   TEXT NOT NULL PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""

_DDL_TRACKS = """
CREATE TABLE tracks (
    track_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    track_uuid              TEXT    NOT NULL UNIQUE,
    file_path               TEXT    NOT NULL UNIQUE,
    file_size_bytes         INTEGER NOT NULL CHECK(file_size_bytes >= 0),
    file_modified_ns        INTEGER NOT NULL CHECK(file_modified_ns >= 0),
    audio_format            TEXT,
    audio_codec             TEXT,
    sample_rate_hz          INTEGER CHECK(sample_rate_hz IS NULL OR sample_rate_hz > 0),
    channel_count           INTEGER CHECK(channel_count   IS NULL OR channel_count   > 0),
    bit_rate_bps            INTEGER CHECK(bit_rate_bps    IS NULL OR bit_rate_bps    > 0),
    audio_duration_seconds  REAL    CHECK(
        audio_duration_seconds IS NULL
        OR (
            audio_duration_seconds > 0
            AND audio_duration_seconds = round(audio_duration_seconds, 2)
        )
    ),
    content_generation      INTEGER NOT NULL CHECK(content_generation >= 1),
    last_scanned_at         TEXT    NOT NULL,
    missing_since           TEXT,
    created_at              TEXT    NOT NULL,
    updated_at              TEXT    NOT NULL
);
CREATE INDEX idx_tracks_missing ON tracks(missing_since, track_id) WHERE missing_since IS NOT NULL;
"""

_DDL_FILE_TAGS = """
CREATE TABLE file_tags (
    track_id       INTEGER PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    title          TEXT,
    artist         TEXT,
    album          TEXT,
    tag_bpm        REAL    CHECK(tag_bpm IS NULL OR tag_bpm > 0),
    tag_key        TEXT,
    comment        TEXT,
    year           INTEGER CHECK(year IS NULL OR (year BETWEEN 1 AND 9999)),
    label          TEXT,
    country        TEXT,
    track_number   TEXT,
    genres_json    TEXT    NOT NULL DEFAULT '[]' CHECK(json_valid(genres_json) AND json_type(genres_json)='array'),
    tags_read_at   TEXT    NOT NULL
);
CREATE INDEX idx_file_tags_sort ON file_tags(COALESCE(artist,''), COALESCE(title,''), track_id);
"""

_DDL_SONARA = """
CREATE TABLE sonara (
    track_id                       INTEGER PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    content_generation             INTEGER NOT NULL,
    -- Rhythm
    detected_bpm                   REAL    CHECK(detected_bpm IS NULL OR detected_bpm > 0),
    raw_bpm                        REAL    CHECK(raw_bpm      IS NULL OR raw_bpm      > 0),
    bpm_confidence                 REAL    CHECK(bpm_confidence IS NULL OR (bpm_confidence BETWEEN 0 AND 1)),
    onset_density_per_second       REAL    CHECK(onset_density_per_second IS NULL OR onset_density_per_second >= 0),
    beat_count                     INTEGER CHECK(beat_count IS NULL OR beat_count >= 0),
    tempo_variability              REAL    CHECK(tempo_variability IS NULL OR tempo_variability >= 0),
    beat_grid_offset_seconds       REAL    CHECK(beat_grid_offset_seconds IS NULL OR beat_grid_offset_seconds >= 0),
    beat_grid_stability            REAL    CHECK(beat_grid_stability IS NULL OR (beat_grid_stability BETWEEN 0 AND 1)),
    bpm_candidates_json            TEXT    CHECK(bpm_candidates_json IS NULL OR (json_valid(bpm_candidates_json) AND json_type(bpm_candidates_json)='array')),
    -- Tonal
    detected_key_name              TEXT,
    detected_key_camelot           TEXT,
    key_confidence                 REAL    CHECK(key_confidence IS NULL OR (key_confidence BETWEEN 0 AND 1)),
    predominant_chord              TEXT,
    chord_changes_per_second       REAL    CHECK(chord_changes_per_second IS NULL OR chord_changes_per_second >= 0),
    key_candidates_json            TEXT    CHECK(key_candidates_json IS NULL OR (json_valid(key_candidates_json) AND json_type(key_candidates_json)='array')),
    -- Perceptual
    energy_score                   REAL    CHECK(energy_score        IS NULL OR (energy_score BETWEEN 0 AND 1)),
    energy_level                   INTEGER CHECK(energy_level        IS NULL OR (energy_level BETWEEN 1 AND 10)),
    danceability_score             REAL    CHECK(danceability_score  IS NULL OR (danceability_score BETWEEN 0 AND 1)),
    valence_score                  REAL    CHECK(valence_score       IS NULL OR (valence_score BETWEEN 0 AND 1)),
    acousticness_score             REAL    CHECK(acousticness_score  IS NULL OR (acousticness_score BETWEEN 0 AND 1)),
    dissonance_score               REAL    CHECK(dissonance_score    IS NULL OR (dissonance_score BETWEEN 0 AND 1)),
    -- Spectral
    spectral_centroid_hz           REAL    CHECK(spectral_centroid_hz   IS NULL OR spectral_centroid_hz   >= 0),
    spectral_bandwidth_hz          REAL    CHECK(spectral_bandwidth_hz  IS NULL OR spectral_bandwidth_hz  >= 0),
    spectral_rolloff_hz            REAL    CHECK(spectral_rolloff_hz    IS NULL OR spectral_rolloff_hz    >= 0),
    spectral_flatness              REAL    CHECK(spectral_flatness      IS NULL OR (spectral_flatness BETWEEN 0 AND 1)),
    zero_crossing_rate             REAL    CHECK(zero_crossing_rate     IS NULL OR (zero_crossing_rate BETWEEN 0 AND 1)),
    -- Loudness
    rms_mean                       REAL    CHECK(rms_mean                    IS NULL OR rms_mean                    >= 0),
    rms_max                        REAL    CHECK(rms_max                     IS NULL OR rms_max                     >= 0),
    integrated_loudness_lufs       REAL,
    dynamic_range_db               REAL    CHECK(dynamic_range_db            IS NULL OR dynamic_range_db            >= 0),
    true_peak_dbtp                 REAL,
    replay_gain_db                 REAL,
    max_momentary_loudness_lufs    REAL,
    loudness_range_lu              REAL    CHECK(loudness_range_lu           IS NULL OR loudness_range_lu           >= 0),
    -- Structure
    analyzed_duration_seconds      REAL    CHECK(analyzed_duration_seconds   IS NULL OR analyzed_duration_seconds   >= 0),
    intro_end_seconds              REAL    CHECK(intro_end_seconds           IS NULL OR intro_end_seconds           >= 0),
    outro_start_seconds            REAL    CHECK(outro_start_seconds         IS NULL OR outro_start_seconds         >= 0),
    leading_silence_seconds        REAL    CHECK(leading_silence_seconds     IS NULL OR leading_silence_seconds     >= 0),
    trailing_silence_seconds       REAL    CHECK(trailing_silence_seconds    IS NULL OR trailing_silence_seconds    >= 0),
    -- Energy curve summary
    energy_curve_hop_seconds       REAL    CHECK(energy_curve_hop_seconds    IS NULL OR energy_curve_hop_seconds    >= 0),
    energy_curve_sample_count      INTEGER CHECK(energy_curve_sample_count   IS NULL OR energy_curve_sample_count   >= 0),
    energy_curve_min               REAL    CHECK(energy_curve_min IS NULL OR (energy_curve_min BETWEEN 0 AND 1)),
    energy_curve_max               REAL    CHECK(energy_curve_max IS NULL OR (energy_curve_max BETWEEN 0 AND 1)),
    energy_curve_mean              REAL    CHECK(energy_curve_mean IS NULL OR (energy_curve_mean BETWEEN 0 AND 1)),
    energy_curve_stddev            REAL    CHECK(energy_curve_stddev IS NULL OR energy_curve_stddev >= 0),
    -- Voice / Mood
    vocal_probability              REAL    CHECK(vocal_probability   IS NULL OR (vocal_probability BETWEEN 0 AND 1)),
    mood_happy_score               REAL    CHECK(mood_happy_score    IS NULL OR (mood_happy_score BETWEEN 0 AND 1)),
    mood_aggressive_score          REAL    CHECK(mood_aggressive_score IS NULL OR (mood_aggressive_score BETWEEN 0 AND 1)),
    mood_relaxed_score             REAL    CHECK(mood_relaxed_score  IS NULL OR (mood_relaxed_score BETWEEN 0 AND 1)),
    mood_sad_score                 REAL    CHECK(mood_sad_score      IS NULL OR (mood_sad_score BETWEEN 0 AND 1)),
    -- Aggression
    aggression_score               REAL    CHECK(aggression_score        IS NULL OR (aggression_score BETWEEN 0 AND 1)),
    aggression_confidence          REAL    CHECK(aggression_confidence   IS NULL OR (aggression_confidence BETWEEN 0 AND 1)),
    aggression_forcefulness        REAL    CHECK(aggression_forcefulness IS NULL OR (aggression_forcefulness BETWEEN 0 AND 1)),
    aggression_harshness           REAL    CHECK(aggression_harshness    IS NULL OR (aggression_harshness BETWEEN 0 AND 1)),
    aggression_tension             REAL    CHECK(aggression_tension      IS NULL OR (aggression_tension BETWEEN 0 AND 1)),
    aggression_rhythm              REAL    CHECK(aggression_rhythm       IS NULL OR (aggression_rhythm BETWEEN 0 AND 1)),
    -- Timbre (short vectors, float32 little-endian)
    mfcc_mean_blob                 BLOB    NOT NULL CHECK(length(mfcc_mean_blob) = 13*4),
    chroma_mean_blob               BLOB    NOT NULL CHECK(length(chroma_mean_blob) = 12*4),
    spectral_contrast_mean_blob    BLOB    NOT NULL CHECK(length(spectral_contrast_mean_blob) = 7*4),
    -- Provenance
    analyzed_at                    TEXT    NOT NULL,
    -- Ordering constraint
    CHECK(energy_curve_min IS NULL OR energy_curve_mean IS NULL OR energy_curve_max IS NULL OR (energy_curve_min <= energy_curve_mean AND energy_curve_mean <= energy_curve_max))
);
CREATE INDEX idx_sonara_generation ON sonara(content_generation, track_id);
"""

_DDL_MAEST_SCORES = """
CREATE TABLE maest_scores (
    track_id           INTEGER PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    content_generation INTEGER NOT NULL,
    syncopated_rhythm  INTEGER CHECK(syncopated_rhythm IS NULL OR syncopated_rhythm IN (0,1)),
    genres_json        TEXT    NOT NULL CHECK(json_valid(genres_json) AND json_type(genres_json)='array'),
    analyzed_at        TEXT    NOT NULL
);
CREATE INDEX idx_maest_scores_generation ON maest_scores(content_generation, track_id);
"""

_DDL_CLASSIFIER_SCORES = """
CREATE TABLE classifier_scores (
    track_id               INTEGER NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    track_uuid             TEXT    NOT NULL,
    classifier_key         TEXT    NOT NULL,
    content_generation     INTEGER NOT NULL,
    feature_set            TEXT    NOT NULL,
    feature_names_json     TEXT    NOT NULL CHECK(json_valid(feature_names_json) AND json_type(feature_names_json)='array'),
    positive_label         TEXT    NOT NULL,
    predicted_class        TEXT    NOT NULL,
    score_bucket           TEXT    NOT NULL CHECK(score_bucket IN ('low','medium','high')),
    score                  REAL    NOT NULL CHECK(score      BETWEEN 0 AND 1),
    confidence             REAL    NOT NULL CHECK(confidence BETWEEN 0 AND 1),
    probabilities_json     TEXT    NOT NULL CHECK(json_valid(probabilities_json) AND json_type(probabilities_json)='object'),
    analyzed_at            TEXT    NOT NULL,
    PRIMARY KEY(track_id, classifier_key)
);
CREATE INDEX idx_classifier_scores_lookup ON classifier_scores(classifier_key, score DESC, track_id);
"""

_DDL_LIKES = """
CREATE TABLE likes (
    track_id  INTEGER PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    liked_at  TEXT    NOT NULL
);
CREATE INDEX idx_likes_liked_at ON likes(liked_at, track_id);
"""

_DDL_PAIR_FEEDBACK = """
CREATE TABLE pair_feedback (
    feedback_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    seed_track_id       INTEGER NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    candidate_track_id  INTEGER NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    rating              INTEGER NOT NULL CHECK(rating BETWEEN 0 AND 3),
    reason_tags_json    TEXT    NOT NULL DEFAULT '[]' CHECK(json_valid(reason_tags_json) AND json_type(reason_tags_json)='array'),
    notes               TEXT,
    source              TEXT    NOT NULL,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL,
    UNIQUE(seed_track_id, candidate_track_id, source)
);
CREATE INDEX idx_pair_feedback_seed_rating ON pair_feedback(seed_track_id, rating DESC, candidate_track_id);
CREATE INDEX idx_pair_feedback_candidate   ON pair_feedback(candidate_track_id, seed_track_id);
"""

_DDL_TRANSITION_FEEDBACK = """
CREATE TABLE transition_feedback (
    transition_feedback_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    outgoing_track_id       INTEGER NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    incoming_track_id       INTEGER NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    rating                  INTEGER NOT NULL CHECK(rating BETWEEN 0 AND 3),
    risk_tags_json          TEXT    NOT NULL DEFAULT '[]' CHECK(json_valid(risk_tags_json) AND json_type(risk_tags_json)='array'),
    notes                   TEXT,
    source                  TEXT    NOT NULL DEFAULT 'manual',
    created_at              TEXT    NOT NULL
);
CREATE INDEX idx_transition_feedback_outgoing ON transition_feedback(outgoing_track_id, created_at DESC, incoming_track_id);
CREATE INDEX idx_transition_feedback_incoming ON transition_feedback(incoming_track_id, outgoing_track_id);
"""

_DDL_TRACK_SEARCH_FTS = """
CREATE VIRTUAL TABLE track_search_fts USING fts5(
    track_id       UNINDEXED,
    file_path,
    title,
    artist,
    album,
    comment,
    label,
    country,
    year,
    track_number,
    file_genres,
    maest_genres,
    tokenize='unicode61'
);
"""

# Ordered list of all DDL blocks to execute
_ALL_DDL: list[str] = [
    _DDL_LIBRARY_CATALOG,
    _DDL_LIBRARY_SETTINGS,
    _DDL_TRACKS,
    _DDL_FILE_TAGS,
    _DDL_SONARA,
    _DDL_MAEST_SCORES,
    _DDL_CLASSIFIER_SCORES,
    _DDL_LIKES,
    _DDL_PAIR_FEEDBACK,
    _DDL_TRANSITION_FEEDBACK,
    _DDL_TRACK_SEARCH_FTS,
]

# ---------------------------------------------------------------------------
# Schema creation function
# ---------------------------------------------------------------------------


def create_core_schema(db: "sqlite3.Connection | str") -> None:
    """Create the current Core schema in *db*.

    Args:
        db: An open :class:`sqlite3.Connection` or a path string (including
            ``':memory:'``).  When a path string is given a new connection is
            opened, the schema is created, and the connection is closed.
    """
    if isinstance(db, str):
        conn = sqlite3.connect(db)
        try:
            _apply_schema(conn)
        finally:
            conn.close()
    else:
        _apply_schema(db)


def _apply_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    script = "\n".join(
        (
            "BEGIN IMMEDIATE;",
            *_ALL_DDL,
            "COMMIT;",
        )
    )
    try:
        conn.executescript(script)
    except BaseException:
        if conn.in_transaction:
            conn.rollback()
        raise


# ---------------------------------------------------------------------------
# Python domain models (frozen dataclasses, no Pydantic)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SonaraRow:
    """SONARA Core row from the ``sonara`` table.

    The three timbre BLOBs are ``bytes`` objects:
    - ``mfcc_mean_blob``: 13 × float32-le = 52 bytes
    - ``chroma_mean_blob``: 12 × float32-le = 48 bytes
    - ``spectral_contrast_mean_blob``: 7 × float32-le = 28 bytes
    """

    track_id: int
    content_generation: int
    # Rhythm
    detected_bpm: Optional[float]
    raw_bpm: Optional[float]
    bpm_confidence: Optional[float]
    onset_density_per_second: Optional[float]
    beat_count: Optional[int]
    tempo_variability: Optional[float]
    beat_grid_offset_seconds: Optional[float]
    beat_grid_stability: Optional[float]
    bpm_candidates_json: Optional[str]
    # Tonal
    detected_key_name: Optional[str]
    detected_key_camelot: Optional[str]
    key_confidence: Optional[float]
    predominant_chord: Optional[str]
    chord_changes_per_second: Optional[float]
    key_candidates_json: Optional[str]
    # Perceptual
    energy_score: Optional[float]
    energy_level: Optional[int]
    danceability_score: Optional[float]
    valence_score: Optional[float]
    acousticness_score: Optional[float]
    dissonance_score: Optional[float]
    # Spectral
    spectral_centroid_hz: Optional[float]
    spectral_bandwidth_hz: Optional[float]
    spectral_rolloff_hz: Optional[float]
    spectral_flatness: Optional[float]
    zero_crossing_rate: Optional[float]
    # Loudness
    rms_mean: Optional[float]
    rms_max: Optional[float]
    integrated_loudness_lufs: Optional[float]
    dynamic_range_db: Optional[float]
    true_peak_dbtp: Optional[float]
    replay_gain_db: Optional[float]
    max_momentary_loudness_lufs: Optional[float]
    loudness_range_lu: Optional[float]
    # Structure
    analyzed_duration_seconds: Optional[float]
    intro_end_seconds: Optional[float]
    outro_start_seconds: Optional[float]
    leading_silence_seconds: Optional[float]
    trailing_silence_seconds: Optional[float]
    # Energy curve summary
    energy_curve_hop_seconds: Optional[float]
    energy_curve_sample_count: Optional[int]
    energy_curve_min: Optional[float]
    energy_curve_max: Optional[float]
    energy_curve_mean: Optional[float]
    energy_curve_stddev: Optional[float]
    # Voice / Mood
    vocal_probability: Optional[float]
    mood_happy_score: Optional[float]
    mood_aggressive_score: Optional[float]
    mood_relaxed_score: Optional[float]
    mood_sad_score: Optional[float]
    # Aggression
    aggression_score: Optional[float]
    aggression_confidence: Optional[float]
    aggression_forcefulness: Optional[float]
    aggression_harshness: Optional[float]
    aggression_tension: Optional[float]
    aggression_rhythm: Optional[float]
    # Timbre BLOBs (float32-le, NOT NULL in DB)
    mfcc_mean_blob: bytes  # 13 * 4 = 52 bytes
    chroma_mean_blob: bytes  # 12 * 4 = 48 bytes
    spectral_contrast_mean_blob: bytes  # 7 * 4 = 28 bytes
    # Provenance
    analyzed_at: str


@dataclass(frozen=True)
class ClassifierScoreRecord:
    """Classifier score row from the ``classifier_scores`` table."""

    track_id: int
    track_uuid: str
    classifier_key: str
    content_generation: int
    feature_set: str
    feature_names_json: str
    positive_label: str
    predicted_class: str
    score_bucket: str  # 'low' | 'medium' | 'high'
    score: float
    confidence: float
    probabilities_json: str  # JSON object string
    analyzed_at: str
