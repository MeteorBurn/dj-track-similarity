import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3


CURRENT_VERSION = 3
SOURCE_VERSION = 2
LIBRARY_MARKER_TABLES = {"tracks", "embeddings"}
ANALYSIS_FLAG_COLUMNS = (
    "has_sonara_analysis",
    "has_maest_embedding",
    "has_mert_embedding",
    "has_clap_embedding",
)


@dataclass(frozen=True)
class MigrationSummary:
    db_path: Path
    dry_run: bool
    version_before: int
    version_after: int
    backup_path: Path | None
    tracks: int
    sonara: int
    maest: int
    mert: int
    clap: int
    fts_rows: int
    integrity_before: str
    integrity_after: str | None


def migrate_database_v3(db_path: str | Path, *, apply: bool = False) -> MigrationSummary:
    path = Path(db_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise FileNotFoundError(path)

    integrity_before = _integrity_check(path)
    if integrity_before.lower() != "ok":
        raise RuntimeError(f"Integrity check failed before migration: {integrity_before}")

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        _require_fts5(connection)
        _detect_library_database(connection)
        version_before = _schema_version(connection)
        if version_before == CURRENT_VERSION:
            counts = _analysis_counts(connection)
            needs_fts = not _has_fts_table(connection)
            if not needs_fts:
                return MigrationSummary(
                    db_path=path,
                    dry_run=not apply,
                    version_before=version_before,
                    version_after=version_before,
                    backup_path=None,
                    integrity_before=integrity_before,
                    integrity_after=integrity_before,
                    **counts,
                )
        else:
            if version_before != SOURCE_VERSION:
                raise RuntimeError(f"Expected library schema version {SOURCE_VERSION}, found {version_before}")
            counts = _source_analysis_counts(connection)
            needs_fts = True

    if not apply:
        return MigrationSummary(
            db_path=path,
            dry_run=True,
            version_before=version_before,
            version_after=version_before,
            backup_path=None,
            integrity_before=integrity_before,
            integrity_after=None,
            **counts,
        )

    backup_path = _backup_database(path)
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        if version_before == SOURCE_VERSION:
            _apply_v3_schema(connection)
        elif needs_fts:
            _apply_fts_schema(connection)
        connection.commit()

    integrity_after = _integrity_check(path)
    if integrity_after.lower() != "ok":
        raise RuntimeError(f"Integrity check failed after migration: {integrity_after}")

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        version_after = _schema_version(connection)
        counts_after = _analysis_counts(connection)

    return MigrationSummary(
        db_path=path,
        dry_run=False,
        version_before=version_before,
        version_after=version_after,
        backup_path=backup_path,
        integrity_before=integrity_before,
        integrity_after=integrity_after,
        **counts_after,
    )


def _apply_v3_schema(connection: sqlite3.Connection) -> None:
    existing_columns = _columns(connection, "tracks")
    for column in ANALYSIS_FLAG_COLUMNS:
        if column not in existing_columns:
            connection.execute(f"ALTER TABLE tracks ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")

    connection.execute(
        """
        UPDATE tracks
        SET has_sonara_analysis =
            CASE WHEN json_type(metadata_json, '$.sonara_features') IS NOT NULL THEN 1 ELSE 0 END
        """
    )
    for embedding_key, column in (
        ("maest", "has_maest_embedding"),
        ("mert", "has_mert_embedding"),
        ("clap", "has_clap_embedding"),
    ):
        connection.execute(
            f"""
            UPDATE tracks
            SET {column} =
                CASE WHEN EXISTS (
                    SELECT 1
                    FROM embeddings e
                    WHERE e.track_id = tracks.id
                      AND e.embedding_key = ?
                ) THEN 1 ELSE 0 END
            """,
            (embedding_key,),
        )

    connection.executescript(
        f"""
        DROP INDEX IF EXISTS idx_tracks_sonara_present;
        DROP INDEX IF EXISTS idx_tracks_maest_present;
        DROP INDEX IF EXISTS idx_tracks_sonara_missing_sort;
        DROP INDEX IF EXISTS idx_tracks_maest_missing_sort;

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

        CREATE INDEX IF NOT EXISTS idx_tracks_present_clap_embedding_flag
        ON tracks(id)
        WHERE has_clap_embedding = 1;

        CREATE INDEX IF NOT EXISTS idx_embeddings_key_track
        ON embeddings(embedding_key, track_id);

        CREATE INDEX IF NOT EXISTS idx_classifier_scores_lookup
        ON track_classifier_scores(classifier, score DESC, track_id);

        PRAGMA user_version = {CURRENT_VERSION};
        """
    )
    _apply_fts_schema(connection)


def _apply_fts_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS track_search_fts USING fts5(
            track_id UNINDEXED,
            search_text,
            tokenize = 'unicode61'
        );

        DELETE FROM track_search_fts;

        INSERT INTO track_search_fts(rowid, track_id, search_text)
        SELECT
            t.id,
            t.id,
            COALESCE(t.artist, '') || ' ' ||
            COALESCE(t.title, '') || ' ' ||
            COALESCE(t.album, '') || ' ' ||
            t.path || ' ' ||
            t.metadata_json
        FROM tracks t
        ORDER BY t.id;
        """
    )


def _source_analysis_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "tracks": int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]),
        "sonara": int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM tracks
                WHERE json_type(metadata_json, '$.sonara_features') IS NOT NULL
                """
            ).fetchone()[0]
        ),
        "maest": _embedding_count(connection, "maest"),
        "mert": _embedding_count(connection, "mert"),
        "clap": _embedding_count(connection, "clap"),
        "fts_rows": 0,
    }


def _analysis_counts(connection: sqlite3.Connection) -> dict[str, int]:
    return {
        "tracks": int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]),
        "sonara": int(connection.execute("SELECT COUNT(*) FROM tracks WHERE has_sonara_analysis = 1").fetchone()[0]),
        "maest": int(connection.execute("SELECT COUNT(*) FROM tracks WHERE has_maest_embedding = 1").fetchone()[0]),
        "mert": int(connection.execute("SELECT COUNT(*) FROM tracks WHERE has_mert_embedding = 1").fetchone()[0]),
        "clap": int(connection.execute("SELECT COUNT(*) FROM tracks WHERE has_clap_embedding = 1").fetchone()[0]),
        "fts_rows": int(connection.execute("SELECT COUNT(*) FROM track_search_fts").fetchone()[0])
        if _has_fts_table(connection)
        else 0,
    }


def _embedding_count(connection: sqlite3.Connection, embedding_key: str) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(DISTINCT track_id) FROM embeddings WHERE embedding_key = ?",
            (embedding_key,),
        ).fetchone()[0]
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


def _detect_library_database(connection: sqlite3.Connection) -> None:
    tables = _user_tables(connection)
    if not LIBRARY_MARKER_TABLES.issubset(tables):
        actual = ", ".join(sorted(tables)) or "none"
        raise RuntimeError(f"Unsupported SQLite database: found tables [{actual}], expected main library database")


def _require_fts5(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("CREATE VIRTUAL TABLE temp._fts5_check USING fts5(value)")
        connection.execute("DROP TABLE temp._fts5_check")
    except sqlite3.DatabaseError as error:
        raise RuntimeError("SQLite FTS5 is required for schema v3 search indexing") from error


def _has_fts_table(connection: sqlite3.Connection) -> bool:
    return "track_search_fts" in _user_tables(connection)


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


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row["name"]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}


def _schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate a dj-track-similarity library SQLite database to schema v3.")
    parser.add_argument("--db", required=True, type=Path, help="Path to the SQLite database file")
    parser.add_argument("--apply", action="store_true", help="Apply the migration. Without this flag the script is read-only.")
    args = parser.parse_args()

    summary = migrate_database_v3(args.db, apply=args.apply)
    print(f"database={summary.db_path}")
    print(f"mode={'apply' if args.apply else 'dry-run'}")
    print(f"version_before={summary.version_before}")
    print(f"version_after={summary.version_after}")
    print(f"backup={summary.backup_path or ''}")
    print(f"tracks={summary.tracks}")
    print(f"sonara={summary.sonara}")
    print(f"maest={summary.maest}")
    print(f"mert={summary.mert}")
    print(f"clap={summary.clap}")
    print(f"fts_rows={summary.fts_rows}")
    print(f"integrity_before={summary.integrity_before}")
    print(f"integrity_after={summary.integrity_after or ''}")
    if not args.apply and (summary.version_before == SOURCE_VERSION or summary.fts_rows == 0):
        print("dry_run=true")
        print("apply_hint=rerun with --apply after closing the app")


if __name__ == "__main__":
    main()
