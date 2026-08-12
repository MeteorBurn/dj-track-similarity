"""Back up and optimize one SQLite database without imposing a schema contract."""

from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3

from dj_track_similarity.db_schema import validate_library_schema
from dj_track_similarity.db_storage import storage_database_paths


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
        return (
            "ok"
            if all(item.integrity_before.lower() == "ok" for item in self.files)
            else "failed"
        )

    @property
    def integrity_after(self) -> str:
        return (
            "ok"
            if all(item.integrity_after.lower() == "ok" for item in self.files)
            else "failed"
        )


def optimize_database(db_path: str | Path) -> OptimizationSummary:
    """Back up, vacuum, analyze, and verify a SQLite database set.

    A database with a valid ``library`` singleton is optimized together with
    its optional Evaluation sidecar. Other SQLite files are optimized as a
    single generic file. This tool deliberately does not enforce a fixed list
    of application tables, columns, or indexes.
    """

    path = Path(db_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise FileNotFoundError(path)

    database_kind = _detect_database_kind(path)
    database_files = _database_files(path, database_kind)
    before: list[tuple[str, Path, int, str]] = []
    for role, selected_path in database_files:
        integrity = _integrity_check(selected_path)
        if integrity.lower() != "ok":
            raise RuntimeError(
                f"Integrity check failed before optimization for {role}: {integrity}"
            )
        before.append((role, selected_path, selected_path.stat().st_size, integrity))

    backups = {
        role: _backup_database(selected_path)
        for role, selected_path, _size, _integrity in before
    }
    for _role, selected_path, _size, _integrity in before:
        _optimize_one_database(selected_path)

    files: list[OptimizedDatabaseFile] = []
    for role, selected_path, size_before, integrity_before in before:
        integrity_after = _integrity_check(selected_path)
        if integrity_after.lower() != "ok":
            raise RuntimeError(
                f"Integrity check failed after optimization for {role}: {integrity_after}"
            )
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


def _detect_database_kind(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        try:
            validate_library_schema(connection, database_path=str(path))
        except RuntimeError:
            return "sqlite"
    return "library"


def _database_files(path: Path, database_kind: str) -> tuple[tuple[str, Path], ...]:
    if database_kind != "library":
        return (("sqlite", path),)

    selected: list[tuple[str, Path]] = [("library", path)]
    evaluation_path = storage_database_paths(path).evaluation
    if evaluation_path.exists():
        if not evaluation_path.is_file():
            raise ValueError(
                f"Evaluation database path must be a file: {evaluation_path}"
            )
        selected.append(("evaluation", evaluation_path))
    return tuple(selected)


def _optimize_one_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("VACUUM")
        connection.execute("ANALYZE")
        connection.execute("PRAGMA optimize")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.commit()


def _backup_database(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak-{timestamp}")
    suffix = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.bak-{timestamp}-{suffix}")
        suffix += 1
    with (
        closing(sqlite3.connect(path)) as source,
        closing(sqlite3.connect(backup_path)) as target,
    ):
        source.backup(target)
        target.commit()
    return backup_path


def _integrity_check(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Back up and optimize a dj-track-similarity SQLite database."
    )
    parser.add_argument(
        "--db", required=True, type=Path, help="Path to the SQLite database file"
    )
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
