import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3


CURRENT_SCHEMA_VERSION = 2

EXPECTED_USER_TABLES = {
    "embeddings",
    "library_settings",
    "track_classifier_scores",
    "tracks",
}

EXPECTED_COLUMNS = {
    "tracks": (
        ("id", "INTEGER", 0, None, 1),
        ("path", "TEXT", 1, None, 0),
        ("size", "INTEGER", 1, None, 0),
        ("mtime", "REAL", 1, None, 0),
        ("artist", "TEXT", 0, None, 0),
        ("title", "TEXT", 0, None, 0),
        ("album", "TEXT", 0, None, 0),
        ("bpm", "REAL", 0, None, 0),
        ("musical_key", "TEXT", 0, None, 0),
        ("energy", "REAL", 0, None, 0),
        ("duration", "REAL", 0, None, 0),
        ("metadata_json", "TEXT", 1, "'{}'", 0),
        ("created_at", "TEXT", 1, "CURRENT_TIMESTAMP", 0),
        ("updated_at", "TEXT", 1, "CURRENT_TIMESTAMP", 0),
    ),
    "embeddings": (
        ("track_id", "INTEGER", 1, None, 1),
        ("embedding_key", "TEXT", 1, "'mert'", 2),
        ("model_name", "TEXT", 1, None, 0),
        ("dim", "INTEGER", 1, None, 0),
        ("vector", "BLOB", 1, None, 0),
        ("updated_at", "TEXT", 1, "CURRENT_TIMESTAMP", 0),
    ),
    "library_settings": (
        ("key", "TEXT", 0, None, 1),
        ("value", "TEXT", 1, None, 0),
        ("updated_at", "TEXT", 1, "CURRENT_TIMESTAMP", 0),
    ),
    "track_classifier_scores": (
        ("track_id", "INTEGER", 1, None, 1),
        ("classifier", "TEXT", 1, None, 2),
        ("score", "REAL", 1, None, 0),
        ("label", "TEXT", 1, None, 0),
        ("confidence", "REAL", 1, None, 0),
        ("probabilities_json", "TEXT", 1, None, 0),
        ("feature_set", "TEXT", 1, None, 0),
        ("model_id", "TEXT", 1, None, 0),
        ("analyzed_at", "TEXT", 1, "CURRENT_TIMESTAMP", 0),
    ),
}

EXPECTED_INDEXES = {
    "idx_classifier_scores_lookup": "track_classifier_scores",
    "idx_embeddings_key_track": "embeddings",
    "idx_tracks_maest_missing_sort": "tracks",
    "idx_tracks_maest_present": "tracks",
    "idx_tracks_sonara_missing_sort": "tracks",
    "idx_tracks_sonara_present": "tracks",
    "idx_tracks_sort_artist_title_path": "tracks",
    "idx_tracks_syncopated_sort": "tracks",
}

EXPECTED_TRIGGERS = {
    "tracks_metadata_json_insert_valid": "tracks",
    "tracks_metadata_json_update_valid": "tracks",
}

EXPECTED_FOREIGN_KEYS = {
    "embeddings": (("tracks", "track_id", "id", "CASCADE"),),
    "track_classifier_scores": (("tracks", "track_id", "id", "CASCADE"),),
}


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

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        _validate_current_schema(connection)

    backup_path = _backup_database(path)

    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
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


def _validate_current_schema(connection: sqlite3.Connection) -> None:
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if version != CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema is not current: user_version is {version}, expected {CURRENT_SCHEMA_VERSION}"
        )

    tables = _user_tables(connection)
    if tables != EXPECTED_USER_TABLES:
        missing = ", ".join(sorted(EXPECTED_USER_TABLES - tables)) or "none"
        unexpected = ", ".join(sorted(tables - EXPECTED_USER_TABLES)) or "none"
        raise RuntimeError(f"Database schema is not current: missing tables [{missing}], unexpected tables [{unexpected}]")

    for table, expected_columns in EXPECTED_COLUMNS.items():
        actual_columns = _columns(connection, table)
        if actual_columns != expected_columns:
            raise RuntimeError(f"Database schema is not current: {table} columns do not match current contract")

    indexes = _objects_by_name(connection, "index")
    expected_index_names = set(EXPECTED_INDEXES)
    actual_index_names = {name for name in indexes if not name.startswith("sqlite_")}
    if actual_index_names != expected_index_names:
        missing = ", ".join(sorted(expected_index_names - actual_index_names)) or "none"
        unexpected = ", ".join(sorted(actual_index_names - expected_index_names)) or "none"
        raise RuntimeError(f"Database schema is not current: missing indexes [{missing}], unexpected indexes [{unexpected}]")
    for name, table in EXPECTED_INDEXES.items():
        if indexes[name] != table:
            raise RuntimeError(f"Database schema is not current: index {name} is on {indexes[name]}, expected {table}")

    triggers = _objects_by_name(connection, "trigger")
    if triggers != EXPECTED_TRIGGERS:
        missing = ", ".join(sorted(set(EXPECTED_TRIGGERS) - set(triggers))) or "none"
        unexpected = ", ".join(sorted(set(triggers) - set(EXPECTED_TRIGGERS))) or "none"
        raise RuntimeError(
            f"Database schema is not current: missing triggers [{missing}], unexpected triggers [{unexpected}]"
        )

    for table, expected_foreign_keys in EXPECTED_FOREIGN_KEYS.items():
        actual_foreign_keys = _foreign_keys(connection, table)
        if actual_foreign_keys != expected_foreign_keys:
            raise RuntimeError(f"Database schema is not current: {table} foreign keys do not match current contract")


def _columns(connection: sqlite3.Connection, table: str) -> tuple[tuple[str, str, int, str | None, int], ...]:
    return tuple(
        (str(row["name"]), str(row["type"]), int(row["notnull"]), row["dflt_value"], int(row["pk"]))
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    )


def _foreign_keys(connection: sqlite3.Connection, table: str) -> tuple[tuple[str, str, str, str], ...]:
    return tuple(
        (str(row["table"]), str(row["from"]), str(row["to"]), str(row["on_delete"]))
        for row in connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    )


def _objects_by_name(connection: sqlite3.Connection, object_type: str) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT name, tbl_name
        FROM sqlite_master
        WHERE type = ?
        """,
        (object_type,),
    ).fetchall()
    return {str(row["name"]): str(row["tbl_name"]) for row in rows}


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
