import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3


SUPPORTED_DATABASE_MARKERS = {
    "library": {"tracks", "embeddings"},
    "rhythm_lab": {
        "classifier_profiles",
        "classifier_labels",
        "classifier_predictions",
        "classifier_training_checkpoints",
    },
}


@dataclass(frozen=True)
class OptimizationSummary:
    db_path: Path
    database_kind: str
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
        database_kind = _detect_supported_database(connection)

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
        database_kind=database_kind,
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


def _detect_supported_database(connection: sqlite3.Connection) -> str:
    tables = _user_tables(connection)
    for database_kind, required_tables in SUPPORTED_DATABASE_MARKERS.items():
        if required_tables.issubset(tables):
            return database_kind
    markers = "; ".join(
        f"{kind}: {', '.join(sorted(required_tables))}"
        for kind, required_tables in SUPPORTED_DATABASE_MARKERS.items()
    )
    actual = ", ".join(sorted(tables)) or "none"
    raise RuntimeError(f"Unsupported SQLite database: found tables [{actual}], expected markers [{markers}]")


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
    print(f"database_kind={summary.database_kind}")
    print(f"backup={summary.backup_path}")
    print(f"integrity_before={summary.integrity_before}")
    print(f"integrity_after={summary.integrity_after}")
    print(f"size_before={summary.size_before}")
    print(f"size_after={summary.size_after}")


if __name__ == "__main__":
    main()
