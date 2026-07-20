import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3


SUPPORTED_DATABASE_MARKERS = {
    "library": {"tracks", "embeddings", "library_settings"},
    "rhythm_lab": {
        "classifier_profiles",
        "classifier_labels",
        "classifier_predictions",
        "classifier_training_checkpoints",
    },
}
TIMELINE_DATABASE_MARKERS = {"storage_metadata", "sonara_timeline"}
REPRESENTATIONS_DATABASE_MARKERS = {"storage_metadata", "embeddings", "fingerprints"}
STORAGE_CATALOG_SETTING_KEY = "storage.catalog_id"


@dataclass(frozen=True)
class OptimizedDatabaseFile:
    role: str
    path: Path
    backup_path: Path
    size_before: int
    size_after: int
    integrity_before: str
    integrity_after: str


@dataclass(frozen=True)
class OptimizationSummary:
    db_path: Path
    database_kind: str
    files: tuple[OptimizedDatabaseFile, ...]

    @property
    def backup_path(self) -> Path:
        return self.files[0].backup_path

    @property
    def backup_paths(self) -> tuple[Path, ...]:
        return tuple(item.backup_path for item in self.files)

    @property
    def size_before(self) -> int:
        return sum(item.size_before for item in self.files)

    @property
    def size_after(self) -> int:
        return sum(item.size_after for item in self.files)

    @property
    def integrity_before(self) -> str:
        return "ok" if all(item.integrity_before.lower() == "ok" for item in self.files) else "failed"

    @property
    def integrity_after(self) -> str:
        return "ok" if all(item.integrity_after.lower() == "ok" for item in self.files) else "failed"


def optimize_database(db_path: str | Path) -> OptimizationSummary:
    path = Path(db_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise FileNotFoundError(path)

    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        database_kind = _detect_supported_database(connection)

    database_files = _database_files(path, database_kind)
    before = []
    for role, selected_path in database_files:
        integrity = _integrity_check(selected_path)
        if integrity.lower() != "ok":
            raise RuntimeError(f"Integrity check failed before optimization for {role}: {integrity}")
        before.append((role, selected_path, selected_path.stat().st_size, integrity))

    backups = {
        role: _backup_database(selected_path)
        for role, selected_path, _size, _integrity in before
    }
    for _role, selected_path, _size, _integrity in before:
        _optimize_one_database(selected_path)

    files = []
    for role, selected_path, size_before, integrity_before in before:
        integrity_after = _integrity_check(selected_path)
        if integrity_after.lower() != "ok":
            raise RuntimeError(f"Integrity check failed after optimization for {role}: {integrity_after}")
        files.append(
            OptimizedDatabaseFile(
                role=role,
                path=selected_path,
                backup_path=backups[role],
                size_before=size_before,
                size_after=selected_path.stat().st_size,
                integrity_before=integrity_before,
                integrity_after=integrity_after,
            )
        )

    return OptimizationSummary(
        db_path=path,
        database_kind=database_kind,
        files=tuple(files),
    )


def _database_files(path: Path, database_kind: str) -> tuple[tuple[str, Path], ...]:
    if database_kind != "library":
        return ((database_kind, path),)

    timeline_path, representations_path = _sidecar_database_paths(path)
    for label, selected_path in (
        ("Timeline", timeline_path),
        ("Representations", representations_path),
    ):
        if not selected_path.is_file():
            raise FileNotFoundError(f"{label} database does not exist: {selected_path}")

    _require_tables(timeline_path, TIMELINE_DATABASE_MARKERS, "Timeline")
    _require_tables(representations_path, REPRESENTATIONS_DATABASE_MARKERS, "Representations")
    _validate_catalog_ids(path, timeline_path, representations_path)
    return (
        ("core", path),
        ("timeline", timeline_path),
        ("representations", representations_path),
    )


def _sidecar_database_paths(path: Path) -> tuple[Path, Path]:
    suffix = path.suffix or ".sqlite"
    stem = path.stem if path.suffix else path.name
    return (
        path.with_name(f"{stem}.timeline{suffix}"),
        path.with_name(f"{stem}.representations{suffix}"),
    )


def _require_tables(path: Path, required: set[str], label: str) -> None:
    with sqlite3.connect(path) as connection:
        tables = _user_tables(connection)
    if not required.issubset(tables):
        actual = ", ".join(sorted(tables)) or "none"
        expected = ", ".join(sorted(required))
        raise RuntimeError(f"{label} database has tables [{actual}], expected [{expected}]")


def _validate_catalog_ids(core: Path, timeline: Path, representations: Path) -> None:
    catalog_ids = {
        "Core": _setting_value(core, "library_settings"),
        "Timeline": _setting_value(timeline, "storage_metadata"),
        "Representations": _setting_value(representations, "storage_metadata"),
    }
    if any(value is None for value in catalog_ids.values()) or len(set(catalog_ids.values())) != 1:
        details = ", ".join(f"{label}={value or 'missing'}" for label, value in catalog_ids.items())
        raise RuntimeError(f"Core, Timeline, and Representations catalog IDs do not match: {details}")


def _setting_value(path: Path, table: str) -> str | None:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            f"SELECT value FROM {table} WHERE key = ?",
            (STORAGE_CATALOG_SETTING_KEY,),
        ).fetchone()
    return str(row[0]) if row is not None else None


def _optimize_one_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("VACUUM")
        connection.execute("ANALYZE")
        connection.execute("PRAGMA optimize")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


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
    return {str(row[0]) for row in rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize a dj-track-similarity SQLite database.")
    parser.add_argument("--db", required=True, type=Path, help="Path to the SQLite database file")
    args = parser.parse_args()

    summary = optimize_database(args.db)
    print(f"database={summary.db_path}")
    print(f"database_kind={summary.database_kind}")
    print(f"integrity_before={summary.integrity_before}")
    print(f"integrity_after={summary.integrity_after}")
    print(f"size_before={summary.size_before}")
    print(f"size_after={summary.size_after}")
    for item in summary.files:
        print(f"{item.role}.database={item.path}")
        print(f"{item.role}.backup={item.backup_path}")


if __name__ == "__main__":
    main()
