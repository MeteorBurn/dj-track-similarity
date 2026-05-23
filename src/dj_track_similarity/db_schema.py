from __future__ import annotations

import sqlite3


CURRENT_SCHEMA_VERSION = 2
SQLITE_BUSY_TIMEOUT_SECONDS = 30

TRACK_BASE_FIELDS = """
t.id, t.path, t.size, t.mtime, t.artist, t.title, t.album, t.bpm, t.musical_key, t.energy, t.duration
"""
TRACK_ANALYSIS_FLAG_FIELDS = """
json_type(t.metadata_json, '$.sonara_features') IS NOT NULL AS has_sonara,
(
    json_type(t.metadata_json, '$.maest_genres') = 'array'
    AND json_array_length(json_extract(t.metadata_json, '$.maest_genres')) > 0
) AS has_maest
"""
TRACK_EMBEDDING_KEY_FIELD = """
(
    SELECT json_group_array(embedding_key)
    FROM embeddings
    WHERE track_id = t.id
) AS embedding_keys_json
"""
TRACK_SELECT_FIELDS = f"""
{TRACK_BASE_FIELDS}, t.metadata_json, e.model_name AS embedding_model, e.dim AS embedding_dim,
{TRACK_EMBEDDING_KEY_FIELD}
"""
TRACK_SLIM_SELECT_FIELDS = f"""
{TRACK_BASE_FIELDS}, e.model_name AS embedding_model, e.dim AS embedding_dim,
{TRACK_ANALYSIS_FLAG_FIELDS},
{TRACK_EMBEDDING_KEY_FIELD}
"""
TRACK_SELECT_FIELDS_WITH_VECTOR = f"""
{TRACK_BASE_FIELDS}, t.metadata_json, e.model_name AS embedding_model, e.dim AS embedding_dim, e.vector,
{TRACK_EMBEDDING_KEY_FIELD}
"""
TRACK_SLIM_SELECT_FIELDS_WITH_VECTOR = f"""
{TRACK_BASE_FIELDS}, e.model_name AS embedding_model, e.dim AS embedding_dim, e.vector,
{TRACK_ANALYSIS_FLAG_FIELDS},
{TRACK_EMBEDDING_KEY_FIELD}
"""

MAEST_HAS_GENRES_SQL = """
(
    json_type(metadata_json, '$.maest_genres') = 'array'
    AND json_array_length(json_extract(metadata_json, '$.maest_genres')) > 0
)
"""
MAEST_MISSING_GENRES_SQL = """
(
    json_type(metadata_json, '$.maest_genres') IS NULL
    OR json_type(metadata_json, '$.maest_genres') != 'array'
    OR json_array_length(json_extract(metadata_json, '$.maest_genres')) = 0
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

        PRAGMA user_version = {CURRENT_SCHEMA_VERSION};
        """
    )
    _create_current_indexes_and_triggers(connection)


def _create_current_indexes_and_triggers(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_tracks_sort_artist_title_path
        ON tracks (COALESCE(artist, ''), COALESCE(title, ''), path);

        CREATE INDEX IF NOT EXISTS idx_tracks_sonara_present
        ON tracks(id)
        WHERE json_type(metadata_json, '$.sonara_features') IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_tracks_maest_present
        ON tracks(id)
        WHERE json_type(metadata_json, '$.maest_genres') IS NOT NULL;

        CREATE INDEX IF NOT EXISTS idx_tracks_syncopated_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE json_extract(metadata_json, '$.maest_syncopated_rhythm') = 1;

        CREATE INDEX IF NOT EXISTS idx_tracks_sonara_missing_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE json_type(metadata_json, '$.sonara_features') IS NULL;

        CREATE INDEX IF NOT EXISTS idx_tracks_maest_missing_sort
        ON tracks(COALESCE(artist, ''), COALESCE(title, ''), path)
        WHERE (
            json_type(metadata_json, '$.maest_genres') IS NULL
            OR json_type(metadata_json, '$.maest_genres') != 'array'
            OR json_array_length(json_extract(metadata_json, '$.maest_genres')) = 0
        );

        CREATE INDEX IF NOT EXISTS idx_embeddings_key_track
        ON embeddings(embedding_key, track_id);

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
        "metadata_json",
        "created_at",
        "updated_at",
    }
    required_embedding_columns = {"track_id", "embedding_key", "model_name", "dim", "vector", "updated_at"}
    settings_columns = _columns(connection, "library_settings")
    required_settings_columns = {"key", "value", "updated_at"}
    if not required_track_columns.issubset(track_columns):
        raise RuntimeError(_migration_required_message())
    if not required_embedding_columns.issubset(embedding_columns):
        raise RuntimeError(_migration_required_message())
    if not required_settings_columns.issubset(settings_columns):
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
        "SQLite database schema is not current. Stop the app and run "
        ".\\.venv\\Scripts\\python.exe scripts/optimize_database.py --db <path-to-database>."
    )
