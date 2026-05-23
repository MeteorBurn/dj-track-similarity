import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3


CURRENT_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class OptimizationSummary:
    db_path: Path
    backup_path: Path
    size_before: int
    size_after: int
    integrity_before: str
    integrity_after: str


def optimize_database(db_path: str | Path) -> OptimizationSummary:
    path = Path(db_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise FileNotFoundError(path)

    size_before = path.stat().st_size
    integrity_before = _integrity_check(path)
    if integrity_before.lower() != "ok":
        raise RuntimeError(f"Integrity check failed before optimization: {integrity_before}")

    backup_path = _backup_database(path)

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        _validate_expected_schema(connection)
        _drop_removed_tables(connection)
        connection.execute("DELETE FROM embeddings WHERE embedding_key = 'fake'")
        _create_settings_table(connection)
        _create_indexes_and_triggers(connection)
        connection.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")
        connection.commit()

        connection.execute("VACUUM")
        connection.execute("ANALYZE")
        connection.execute("PRAGMA optimize")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    integrity_after = _integrity_check(path)
    if integrity_after.lower() != "ok":
        raise RuntimeError(f"Integrity check failed after optimization: {integrity_after}")

    return OptimizationSummary(
        db_path=path,
        backup_path=backup_path,
        size_before=size_before,
        size_after=path.stat().st_size,
        integrity_before=integrity_before,
        integrity_after=integrity_after,
    )


def _backup_database(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak-{timestamp}")
    suffix = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.bak-{timestamp}-{suffix}")
        suffix += 1
    with sqlite3.connect(path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    return backup_path


def _integrity_check(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def _validate_expected_schema(connection: sqlite3.Connection) -> None:
    tables = _user_tables(connection)
    if not {"tracks", "embeddings"}.issubset(tables):
        raise RuntimeError("Database must contain current tracks and embeddings tables before optimization")
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
    if not required_track_columns.issubset(track_columns):
        missing = ", ".join(sorted(required_track_columns - track_columns))
        raise RuntimeError(f"tracks table is missing required columns: {missing}")
    if not required_embedding_columns.issubset(embedding_columns):
        missing = ", ".join(sorted(required_embedding_columns - embedding_columns))
        raise RuntimeError(f"embeddings table is missing required columns: {missing}")


def _drop_removed_tables(connection: sqlite3.Connection) -> None:
    connection.execute("DROP TABLE IF EXISTS playlist_tracks")
    connection.execute("DROP TABLE IF EXISTS playlists")


def _create_settings_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS library_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _create_indexes_and_triggers(connection: sqlite3.Connection) -> None:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize a dj-track-similarity SQLite database.")
    parser.add_argument("--db", required=True, type=Path, help="Path to the SQLite database file")
    args = parser.parse_args()

    summary = optimize_database(args.db)
    print(f"database={summary.db_path}")
    print(f"backup={summary.backup_path}")
    print(f"integrity_before={summary.integrity_before}")
    print(f"integrity_after={summary.integrity_after}")
    print(f"size_before={summary.size_before}")
    print(f"size_after={summary.size_after}")
    print(f"user_version={CURRENT_SCHEMA_VERSION}")


if __name__ == "__main__":
    main()
