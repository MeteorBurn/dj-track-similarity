from __future__ import annotations

import sqlite3


SQLITE_BUSY_TIMEOUT_SECONDS = 30

TRACK_SELECT_FIELDS = """
t.*, e.model_name AS embedding_model, e.dim AS embedding_dim,
    (
        SELECT json_group_array(embedding_key)
        FROM embeddings
        WHERE track_id = t.id
    ) AS embedding_keys_json
"""
TRACK_SELECT_FIELDS_WITH_VECTOR = """
t.*, e.model_name AS embedding_model, e.dim AS embedding_dim, e.vector,
    (
        SELECT json_group_array(embedding_key)
        FROM embeddings
        WHERE track_id = t.id
    ) AS embedding_keys_json
"""


def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tracks (
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
            metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            track_id INTEGER NOT NULL,
            embedding_key TEXT NOT NULL DEFAULT 'mert',
            model_name TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(track_id, embedding_key),
            FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );
        """
    )
    migrate_embedding_schema(connection)
    purge_legacy_fake_embeddings(connection)
    drop_legacy_playlist_schema(connection)
    ensure_track_metadata_json_guards(connection)


def migrate_embedding_schema(connection: sqlite3.Connection) -> None:
    columns = connection.execute("PRAGMA table_info(embeddings)").fetchall()
    if any(str(column["name"]) == "embedding_key" for column in columns):
        return
    connection.executescript(
        """
        ALTER TABLE embeddings RENAME TO embeddings_legacy;

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

        INSERT INTO embeddings (track_id, embedding_key, model_name, dim, vector, updated_at)
        SELECT track_id, 'mert', model_name, dim, vector, updated_at
        FROM embeddings_legacy;

        DROP TABLE embeddings_legacy;
        """
    )


def purge_legacy_fake_embeddings(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM embeddings WHERE embedding_key = 'fake'")


def drop_legacy_playlist_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        DROP TABLE IF EXISTS playlist_tracks;
        DROP TABLE IF EXISTS playlists;
        """
    )


def ensure_track_metadata_json_guards(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
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
