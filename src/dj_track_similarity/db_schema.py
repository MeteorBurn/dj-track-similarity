from __future__ import annotations

import sqlite3

from .db_search_fts import create_track_search_fts


CURRENT_SCHEMA_VERSION = 5
SQLITE_BUSY_TIMEOUT_SECONDS = 30

TRACK_BASE_FIELDS = """
t.id, t.path, t.size, t.mtime, t.artist, t.title, t.album, t.bpm, t.musical_key, t.energy, t.duration,
EXISTS(SELECT 1 FROM track_likes tl WHERE tl.track_id = t.id) AS liked
"""
TRACK_ANALYSIS_FLAG_FIELDS = """
t.has_sonara_analysis = 1 AS has_sonara,
t.has_maest_embedding = 1 AS has_maest
"""
TRACK_EMBEDDING_KEY_FIELD = """
(
    SELECT json_group_array(embedding_key)
    FROM embeddings
    WHERE track_id = t.id
) AS embedding_keys_json
"""
TRACK_CLASSIFIER_SCORES_FIELD = """
(
    SELECT COALESCE(
        json_group_object(
            classifier,
            json_object(
                'score', score,
                'label', label,
                'confidence', confidence,
                'probabilities', json(probabilities_json),
                'feature_set', feature_set,
                'model_id', model_id,
                'analyzed_at', analyzed_at
            )
        ),
        '{}'
    )
    FROM track_classifier_scores
    WHERE track_id = t.id
) AS classifier_scores_json
"""
TRACK_SELECT_FIELDS = f"""
{TRACK_BASE_FIELDS}, t.metadata_json, e.model_name AS embedding_model, e.dim AS embedding_dim,
{TRACK_EMBEDDING_KEY_FIELD},
{TRACK_CLASSIFIER_SCORES_FIELD}
"""
TRACK_SLIM_SELECT_FIELDS = f"""
{TRACK_BASE_FIELDS}, e.model_name AS embedding_model, e.dim AS embedding_dim,
{TRACK_ANALYSIS_FLAG_FIELDS},
{TRACK_EMBEDDING_KEY_FIELD},
{TRACK_CLASSIFIER_SCORES_FIELD}
"""
TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR = f"""
{TRACK_BASE_FIELDS}, e.model_name AS embedding_model, e.dim AS embedding_dim, e.vector,
{TRACK_ANALYSIS_FLAG_FIELDS},
{TRACK_EMBEDDING_KEY_FIELD},
{TRACK_CLASSIFIER_SCORES_FIELD}
"""

MAEST_HAS_GENRES_SQL = """
(
    json_type(metadata_json, '$.maest_genres') = 'array'
    AND json_array_length(json_extract(metadata_json, '$.maest_genres')) > 0
)
"""
def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")

    tables = _user_tables(connection)
    if tables and not {"tracks", "embeddings"}.issubset(tables):
        raise RuntimeError(_migration_required_message())

    if not tables:
        _create_current_schema(connection)
        return

    if _schema_version(connection) != CURRENT_SCHEMA_VERSION:
        raise RuntimeError(_migration_required_message())
    _validate_current_schema(connection)
    _create_current_indexes_and_triggers(connection)


def _create_current_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        f"""
        CREATE TABLE tracks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            size INTEGER NOT NULL,
            mtime REAL NOT NULL,
            artist TEXT,
            title TEXT,
            album TEXT,
            bpm REAL,
            musical_key TEXT,
            energy REAL,
            duration REAL,
            has_sonara_analysis INTEGER NOT NULL DEFAULT 0,
            has_maest_embedding INTEGER NOT NULL DEFAULT 0,
            has_mert_embedding INTEGER NOT NULL DEFAULT 0,
            has_muq_embedding INTEGER NOT NULL DEFAULT 0,
            has_clap_embedding INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{{}}' CHECK (json_valid(metadata_json)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE embeddings (
            track_id INTEGER NOT NULL,
            embedding_key TEXT NOT NULL DEFAULT 'mert',
            model_name TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(track_id, embedding_key),
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE TABLE library_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE track_classifier_scores (
            track_id INTEGER NOT NULL,
            classifier TEXT NOT NULL,
            score REAL NOT NULL,
            label TEXT NOT NULL,
            confidence REAL NOT NULL,
            probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
            feature_set TEXT NOT NULL,
            model_id TEXT NOT NULL,
            analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(track_id, classifier),
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE TABLE track_likes (
            track_id INTEGER PRIMARY KEY,
            liked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE TABLE sonara_curves (
            track_id INTEGER PRIMARY KEY,
            curves_json TEXT NOT NULL CHECK(json_valid(curves_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        PRAGMA user_version = {CURRENT_SCHEMA_VERSION};
        """
    )
    create_track_search_fts(connection)
    _create_current_indexes_and_triggers(connection)


def _create_current_indexes_and_triggers(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_tracks_sort_artist_title_path
        ON tracks (COALESCE(artist, ''), COALESCE(title, ''), path);

        CREATE INDEX IF NOT EXISTS idx_tracks_syncopated_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE json_extract(metadata_json, '$.maest_syncopated_rhythm') = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_missing_sonara_flag_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE has_sonara_analysis = 0;

        CREATE INDEX IF NOT EXISTS idx_tracks_missing_maest_embedding_flag_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE has_maest_embedding = 0;

        CREATE INDEX IF NOT EXISTS idx_tracks_missing_mert_embedding_flag_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE has_mert_embedding = 0;

        CREATE INDEX IF NOT EXISTS idx_tracks_missing_muq_embedding_flag_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE has_muq_embedding = 0;

        CREATE INDEX IF NOT EXISTS idx_tracks_missing_clap_embedding_flag_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE has_clap_embedding = 0;

        CREATE INDEX IF NOT EXISTS idx_tracks_present_sonara_flag
        ON tracks(id)
        WHERE has_sonara_analysis = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_present_maest_embedding_flag
        ON tracks(id)
        WHERE has_maest_embedding = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_present_mert_embedding_flag
        ON tracks(id)
        WHERE has_mert_embedding = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_present_muq_embedding_flag
        ON tracks(id)
        WHERE has_muq_embedding = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_present_clap_embedding_flag
        ON tracks(id)
        WHERE has_clap_embedding = 1;

        CREATE INDEX IF NOT EXISTS idx_embeddings_key_track
        ON embeddings(embedding_key, track_id);

        CREATE TABLE IF NOT EXISTS track_classifier_scores (
            track_id INTEGER NOT NULL,
            classifier TEXT NOT NULL,
            score REAL NOT NULL,
            label TEXT NOT NULL,
            confidence REAL NOT NULL,
            probabilities_json TEXT NOT NULL CHECK(json_valid(probabilities_json)),
            feature_set TEXT NOT NULL,
            model_id TEXT NOT NULL,
            analyzed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(track_id, classifier),
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_classifier_scores_lookup
        ON track_classifier_scores(classifier, score DESC, track_id);

        CREATE TABLE IF NOT EXISTS track_likes (
            track_id INTEGER PRIMARY KEY,
            liked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS sonara_curves (
            track_id INTEGER PRIMARY KEY,
            curves_json TEXT NOT NULL CHECK(json_valid(curves_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        CREATE TRIGGER IF NOT EXISTS tracks_metadata_json_insert_valid
        BEFORE INSERT ON tracks
        FOR EACH ROW
        WHEN NOT json_valid(NEW.metadata_json)
        BEGIN
            SELECT RAISE(ABORT, 'tracks.metadata_json must be valid JSON');
        END;

        CREATE TRIGGER IF NOT EXISTS tracks_metadata_json_update_valid
        BEFORE UPDATE OF metadata_json ON tracks
        FOR EACH ROW
        WHEN NOT json_valid(NEW.metadata_json)
        BEGIN
            SELECT RAISE(ABORT, 'tracks.metadata_json must be valid JSON');
        END;
        """
    )
    _create_evaluation_schema(connection)


def _create_evaluation_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS search_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mode TEXT NOT NULL,
            seed_track_ids_json TEXT NOT NULL CHECK(json_valid(seed_track_ids_json)),
            request_json TEXT NOT NULL CHECK(json_valid(request_json)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS search_result_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL REFERENCES search_sessions(id) ON DELETE CASCADE,
            track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            rank INTEGER NOT NULL,
            total_score REAL NOT NULL,
            score_breakdown_json TEXT NOT NULL CHECK(json_valid(score_breakdown_json)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS track_pair_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seed_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            candidate_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 0 AND 3),
            reason_tags_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(reason_tags_json)),
            notes TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(seed_track_id, candidate_track_id, source)
        );

        CREATE TABLE IF NOT EXISTS transition_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            outgoing_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            incoming_track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 0 AND 3),
            risk_tags_json TEXT NOT NULL DEFAULT '[]' CHECK(json_valid(risk_tags_json)),
            notes TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS calibration_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_name TEXT NOT NULL,
            search_mode TEXT NOT NULL,
            config_json TEXT NOT NULL CHECK(json_valid(config_json)),
            metrics_json TEXT NOT NULL CHECK(json_valid(metrics_json)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_search_sessions_mode_created
        ON search_sessions(mode, created_at);

        CREATE INDEX IF NOT EXISTS idx_search_result_events_session_rank
        ON search_result_events(session_id, rank);

        CREATE INDEX IF NOT EXISTS idx_search_result_events_track
        ON search_result_events(track_id);

        CREATE INDEX IF NOT EXISTS idx_track_pair_feedback_seed_rating
        ON track_pair_feedback(seed_track_id, rating, candidate_track_id);

        CREATE INDEX IF NOT EXISTS idx_track_pair_feedback_candidate
        ON track_pair_feedback(candidate_track_id);

        CREATE INDEX IF NOT EXISTS idx_transition_feedback_outgoing_created
        ON transition_feedback(outgoing_track_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_transition_feedback_incoming
        ON transition_feedback(incoming_track_id);

        CREATE INDEX IF NOT EXISTS idx_calibration_runs_profile_mode_created
        ON calibration_runs(profile_name, search_mode, created_at);
        """
    )


def _validate_current_schema(connection: sqlite3.Connection) -> None:
    track_columns = _columns(connection, "tracks")
    embedding_columns = _columns(connection, "embeddings")
    required_track_columns = {
        "id",
        "path",
        "size",
        "mtime",
        "artist",
        "title",
        "album",
        "bpm",
        "musical_key",
        "energy",
        "duration",
        "has_sonara_analysis",
        "has_maest_embedding",
        "has_mert_embedding",
        "has_muq_embedding",
        "has_clap_embedding",
        "metadata_json",
        "created_at",
        "updated_at",
    }
    required_embedding_columns = {"track_id", "embedding_key", "model_name", "dim", "vector", "updated_at"}
    settings_columns = _columns(connection, "library_settings")
    required_settings_columns = {"key", "value", "updated_at"}
    tables = _user_tables(connection)
    if not required_track_columns.issubset(track_columns):
        raise RuntimeError(_migration_required_message())
    if not required_embedding_columns.issubset(embedding_columns):
        raise RuntimeError(_migration_required_message())
    if not required_settings_columns.issubset(settings_columns):
        raise RuntimeError(_migration_required_message())
    if "track_search_fts" not in tables:
        raise RuntimeError(_migration_required_message())
    _validate_evaluation_schema(connection)


def _validate_evaluation_schema(connection: sqlite3.Connection) -> None:
    required_tables = {
        "search_sessions": {
            "id",
            "mode",
            "seed_track_ids_json",
            "request_json",
            "created_at",
        },
        "search_result_events": {
            "id",
            "session_id",
            "track_id",
            "rank",
            "total_score",
            "score_breakdown_json",
            "created_at",
        },
        "track_pair_feedback": {
            "id",
            "seed_track_id",
            "candidate_track_id",
            "rating",
            "reason_tags_json",
            "notes",
            "source",
            "created_at",
            "updated_at",
        },
        "transition_feedback": {
            "id",
            "outgoing_track_id",
            "incoming_track_id",
            "rating",
            "risk_tags_json",
            "notes",
            "source",
            "created_at",
        },
        "calibration_runs": {
            "id",
            "profile_name",
            "search_mode",
            "config_json",
            "metrics_json",
            "created_at",
        },
    }
    tables = _user_tables(connection)
    if not set(required_tables).issubset(tables):
        raise RuntimeError(_migration_required_message())
    for table, required_columns in required_tables.items():
        if not required_columns.issubset(_columns(connection, table)):
            raise RuntimeError(_migration_required_message())


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def _migration_required_message() -> str:
    return (
        "SQLite database schema is not current. Stop the app and use a database created with the current "
        "application version, or rebuild the library database by scanning the source music library again."
    )
