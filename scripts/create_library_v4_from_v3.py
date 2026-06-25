import argparse
from dataclasses import dataclass
from pathlib import Path
import sqlite3


SOURCE_VERSION = 3
DESTINATION_VERSION = 4
REQUIRED_SOURCE_TABLES = {
    "tracks",
    "embeddings",
    "library_settings",
    "track_classifier_scores",
    "track_likes",
    "track_search_fts",
}
EVALUATION_TABLES = {
    "search_sessions",
    "search_result_events",
    "track_pair_feedback",
    "transition_feedback",
    "calibration_runs",
}


@dataclass(frozen=True)
class CreateLibraryV4Summary:
    source_path: Path
    dest_path: Path
    dry_run: bool
    force: bool
    source_version: int
    dest_version: int
    source_tracks: int
    source_integrity: str
    dest_integrity: str | None
    dest_existed: bool
    evaluation_tables: tuple[str, ...]


def create_library_v4_from_v3(
    source_path: str | Path,
    dest_path: str | Path,
    *,
    apply: bool = False,
    force: bool = False,
) -> CreateLibraryV4Summary:
    source = Path(source_path).expanduser().resolve(strict=False)
    dest = Path(dest_path).expanduser().resolve(strict=False)
    if source == dest:
        raise ValueError("Source and destination must be different database files")
    if not source.is_file():
        raise FileNotFoundError(source)

    dest_existed = dest.exists()
    source_integrity, source_tracks = _validate_source(source)

    if not apply:
        return CreateLibraryV4Summary(
            source_path=source,
            dest_path=dest,
            dry_run=True,
            force=force,
            source_version=SOURCE_VERSION,
            dest_version=DESTINATION_VERSION,
            source_tracks=source_tracks,
            source_integrity=source_integrity,
            dest_integrity=None,
            dest_existed=dest_existed,
            evaluation_tables=tuple(sorted(EVALUATION_TABLES)),
        )

    if dest_existed and not force:
        raise FileExistsError(f"Destination already exists: {dest}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest_existed:
        _remove_destination_files(dest)

    with _connect_readonly(source) as source_connection, sqlite3.connect(dest) as dest_connection:
        source_connection.backup(dest_connection)

    with sqlite3.connect(dest) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        _apply_evaluation_schema(connection)
        connection.execute(f"PRAGMA user_version = {DESTINATION_VERSION}")
        connection.commit()

    dest_integrity = _integrity_check(dest)
    if dest_integrity.lower() != "ok":
        raise RuntimeError(f"Destination integrity check failed: {dest_integrity}")

    dest_version, evaluation_tables = _validate_destination(dest)
    return CreateLibraryV4Summary(
        source_path=source,
        dest_path=dest,
        dry_run=False,
        force=force,
        source_version=SOURCE_VERSION,
        dest_version=dest_version,
        source_tracks=source_tracks,
        source_integrity=source_integrity,
        dest_integrity=dest_integrity,
        dest_existed=dest_existed,
        evaluation_tables=tuple(sorted(evaluation_tables)),
    )


def _validate_source(path: Path) -> tuple[str, int]:
    source_integrity = _integrity_check(path)
    if source_integrity.lower() != "ok":
        raise RuntimeError(f"Source integrity check failed: {source_integrity}")

    with _connect_readonly(path) as connection:
        connection.row_factory = sqlite3.Row
        tables = _user_tables(connection)
        missing_tables = sorted(REQUIRED_SOURCE_TABLES - tables)
        if missing_tables:
            raise RuntimeError(f"Source is not a complete schema v3 library database; missing {missing_tables}")
        version = _schema_version(connection)
        if version != SOURCE_VERSION:
            raise RuntimeError(f"Expected source schema version {SOURCE_VERSION}, found {version}")
        tracks = int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
    return source_integrity, tracks


def _validate_destination(path: Path) -> tuple[int, set[str]]:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        version = _schema_version(connection)
        if version != DESTINATION_VERSION:
            raise RuntimeError(f"Expected destination schema version {DESTINATION_VERSION}, found {version}")
        tables = _user_tables(connection)
        missing_tables = sorted(EVALUATION_TABLES - tables)
        if missing_tables:
            raise RuntimeError(f"Destination is missing evaluation tables: {missing_tables}")
    return version, EVALUATION_TABLES


def _apply_evaluation_schema(connection: sqlite3.Connection) -> None:
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


def _connect_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _remove_destination_files(path: Path) -> None:
    for candidate in (path, path.with_name(f"{path.name}-wal"), path.with_name(f"{path.name}-shm")):
        if candidate.exists():
            candidate.unlink()


def _integrity_check(path: Path) -> str:
    with _connect_readonly(path) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def _schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


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
    parser = argparse.ArgumentParser(
        description="Create a schema v4 copy of a dj-track-similarity schema v3 library database."
    )
    parser.add_argument("--source", required=True, type=Path, help="Read-only source schema v3 SQLite database")
    parser.add_argument("--dest", required=True, type=Path, help="Destination schema v4 SQLite database to create")
    parser.add_argument("--apply", action="store_true", help="Create the destination copy. Without this flag, dry-run only.")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing destination database during --apply.")
    args = parser.parse_args()

    summary = create_library_v4_from_v3(args.source, args.dest, apply=args.apply, force=args.force)
    print(f"source={summary.source_path}")
    print(f"dest={summary.dest_path}")
    print(f"mode={'apply' if args.apply else 'dry-run'}")
    print(f"force={summary.force}")
    print(f"source_version={summary.source_version}")
    print(f"dest_version={summary.dest_version}")
    print(f"source_tracks={summary.source_tracks}")
    print(f"source_integrity={summary.source_integrity}")
    print(f"dest_integrity={summary.dest_integrity or ''}")
    print(f"dest_exists={summary.dest_existed}")
    print(f"evaluation_tables={','.join(summary.evaluation_tables)}")
    if not args.apply:
        print("dry_run=true")
        print("apply_hint=rerun with --apply after choosing a new destination path")


if __name__ == "__main__":
    main()
