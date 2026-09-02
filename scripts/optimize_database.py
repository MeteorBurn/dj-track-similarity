"""Back up and optimize one SQLite database without imposing a schema contract.

The run, in order:

1. Inspect every file of the set through the project's read-only recipe:
   ``PRAGMA integrity_check`` (CHECK constraints included), ``PRAGMA
   foreign_key_check``, journal mode, page accounting, and FTS5 tables.
   A failure stops the run before any write.
2. Refuse to start when the drive cannot hold what the run needs: a backup
   copy and, in WAL mode, a WAL that grows to the compacted size during
   ``VACUUM``, plus the ``VACUUM`` temporary copy when the SQLite temp
   directory shares the drive.
3. Back up every file through the SQLite backup API, then verify the copy.
   A backup that has not been checked is not a rollback point.
4. Optimize each file: merge FTS5 index segments, ``VACUUM``, ``ANALYZE``,
   and fold the WAL back with ``PRAGMA wal_checkpoint(TRUNCATE)``.
5. Verify every file again and report the sizes.

The script changes storage, never policy: it keeps the journal mode it found,
because every database this project owns enforces WAL itself on open, and a
generic file belongs to whoever created it. ``--dry-run`` stops after step 2.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
import sys
import tempfile
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from dj_track_similarity.db_connection import connect_database_read_only
from dj_track_similarity.db_schema import (
    SQLITE_BUSY_TIMEOUT_SECONDS,
    validate_library_schema,
)
from dj_track_similarity.db_storage import storage_database_paths


_SQLITE_HEADER = b"SQLite format 3\x00"
_FTS5_TABLE_PATTERN = re.compile(r"\bUSING\s+fts5\s*\(", re.IGNORECASE)


class OptimizationError(RuntimeError):
    """A user-facing optimization failure."""


@dataclass(frozen=True)
class InspectedDatabaseFile:
    role: str
    path: Path
    journal_mode: str
    page_size: int
    page_count: int
    freelist_pages: int
    fts5_tables: tuple[str, ...]
    size: int
    """Bytes on disk before the run: the main file plus its WAL."""
    integrity: str

    @property
    def compacted_bytes(self) -> int:
        """Upper estimate of the file size after ``VACUUM``."""
        return max(self.page_count - self.freelist_pages, 0) * self.page_size


@dataclass(frozen=True)
class DatabaseInspection:
    db_path: Path
    database_kind: str
    files: tuple[InspectedDatabaseFile, ...]
    required_free_bytes: int
    free_bytes: int | None
    """Free space on the database drive; ``None`` when it cannot be read."""

    @property
    def size(self) -> int:
        return sum(item.size for item in self.files)

    @property
    def compacted_bytes(self) -> int:
        return sum(item.compacted_bytes for item in self.files)

    @property
    def free_space_ok(self) -> bool:
        return self.free_bytes is None or self.free_bytes >= self.required_free_bytes


@dataclass(frozen=True)
class OptimizedDatabaseFile:
    role: str
    path: Path
    backup_path: Path
    journal_mode: str
    size_before: int
    size_after: int
    integrity_before: str
    integrity_after: str
    checkpoint: str | None
    """``complete`` or ``incomplete`` for a WAL file, ``None`` otherwise."""


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
        return _aggregate_integrity(item.integrity_before for item in self.files)

    @property
    def integrity_after(self) -> str:
        return _aggregate_integrity(item.integrity_after for item in self.files)


def inspect_database(db_path: str | Path) -> DatabaseInspection:
    """Verify a SQLite database set and report what optimization would do.

    Every file is opened through ``connect_database_read_only``; nothing is
    written. A file that fails ``integrity_check`` or ``foreign_key_check``
    raises ``OptimizationError``.
    """

    path = _resolved(db_path)
    _require_sqlite_file(path, "database")
    database_kind = _detect_database_kind(path)
    files = tuple(
        _inspect_file(role, selected_path)
        for role, selected_path in _database_files(path, database_kind)
    )
    return DatabaseInspection(
        db_path=path,
        database_kind=database_kind,
        files=files,
        required_free_bytes=_required_free_bytes(files),
        free_bytes=_free_bytes(path),
    )


def optimize_database(db_path: str | Path) -> OptimizationSummary:
    """Back up, optimize, and verify a SQLite database set.

    A database with a valid ``library`` singleton is optimized together with
    its optional Evaluation sidecar. Other SQLite files are optimized as a
    single generic file. This tool deliberately does not enforce a fixed list
    of application tables, columns, or indexes.
    """

    inspection = inspect_database(db_path)
    _require_free_space(inspection)

    backups = {item.role: _backup_database(item) for item in inspection.files}

    files: list[OptimizedDatabaseFile] = []
    for item in inspection.files:
        checkpoint = _optimize_one_database(item)
        integrity_after = _verify_file(
            item.path,
            item.role,
            backup_path=backups[item.role],
        )
        files.append(
            OptimizedDatabaseFile(
                role=item.role,
                path=item.path,
                backup_path=backups[item.role],
                journal_mode=item.journal_mode,
                size_before=item.size,
                size_after=_on_disk_size(item.path),
                integrity_before=item.integrity,
                integrity_after=integrity_after,
                checkpoint=checkpoint,
            )
        )

    return OptimizationSummary(
        db_path=inspection.db_path,
        database_kind=inspection.database_kind,
        files=tuple(files),
    )


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _require_sqlite_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise OptimizationError(f"{label} not found: {path}")
    with path.open("rb") as handle:
        header = handle.read(len(_SQLITE_HEADER))
    if header != _SQLITE_HEADER:
        raise OptimizationError(f"{label} is not a SQLite database: {path}")


def _detect_database_kind(path: Path) -> str:
    with closing(_open_read_only(path, "database")) as connection:
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
        _require_sqlite_file(evaluation_path, "Evaluation database")
        selected.append(("evaluation", evaluation_path))
    return tuple(selected)


def _inspect_file(role: str, path: Path) -> InspectedDatabaseFile:
    # Measure before opening: closing the last connection of a WAL database
    # checkpoints it and removes the WAL, and the run should report the WAL
    # bytes it found.
    size = _on_disk_size(path)
    with closing(_open_read_only(path, role)) as connection:
        integrity = _integrity_check(connection, role)
        _foreign_key_check(connection, role)
        return InspectedDatabaseFile(
            role=role,
            path=path,
            journal_mode=str(
                connection.execute("PRAGMA journal_mode").fetchone()[0]
            ).lower(),
            page_size=int(connection.execute("PRAGMA page_size").fetchone()[0]),
            page_count=int(connection.execute("PRAGMA page_count").fetchone()[0]),
            freelist_pages=int(
                connection.execute("PRAGMA freelist_count").fetchone()[0]
            ),
            fts5_tables=_fts5_tables(connection),
            size=size,
            integrity=integrity,
        )


def _fts5_tables(connection: sqlite3.Connection) -> tuple[str, ...]:
    rows = connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL"
    ).fetchall()
    return tuple(
        str(row[0]) for row in rows if _FTS5_TABLE_PATTERN.search(str(row[1]))
    )


def _open_read_only(path: Path, label: str) -> sqlite3.Connection:
    """Open one file for verification through the shared read-only recipe.

    ``connect_database_read_only`` keeps ``PRAGMA integrity_check`` honest: a
    ``mode=ro`` handle skips CHECK constraint verification and answers ``ok``
    on a database that violates them.
    """

    try:
        return connect_database_read_only(path)
    except (sqlite3.Error, OSError, ValueError) as error:
        raise OptimizationError(
            f"cannot open {label} database {path}: {error}"
        ) from error


def _open_read_write(path: Path) -> sqlite3.Connection:
    """Open one existing file for the backup source and the maintenance run.

    This deliberately does not reuse the application connection recipe: its
    ``PRAGMA temp_store = MEMORY`` makes ``VACUUM`` build its temporary copy in
    RAM, measured as a peak of roughly the compacted database size on top of
    the process. The maintenance handle keeps SQLite's default ``temp_store``
    and ``synchronous`` and never sets ``journal_mode``.
    """

    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=rw",
        timeout=SQLITE_BUSY_TIMEOUT_SECONDS,
        uri=True,
    )
    try:
        connection.execute(
            f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_SECONDS * 1000}"
        )
        connection.execute("PRAGMA temp_store = FILE")
        return connection
    except BaseException:
        connection.close()
        raise


def _integrity_check(connection: sqlite3.Connection, label: str) -> str:
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    failures = [str(row[0]) for row in rows if str(row[0]).lower() != "ok"]
    if failures or not rows:
        detail = failures[0] if failures else "no result"
        if len(failures) > 1:
            detail = f"{detail} (+{len(failures) - 1} more)"
        raise OptimizationError(f"{label} integrity_check failed: {detail}")
    return "ok"


def _foreign_key_check(connection: sqlite3.Connection, label: str) -> None:
    rows = connection.execute("PRAGMA foreign_key_check").fetchall()
    if rows:
        row = rows[0]
        raise OptimizationError(
            f"{label} foreign-key violation: "
            f"table={row[0]} rowid={row[1]} parent={row[2]} fkid={row[3]}"
        )


def _verify_file(path: Path, label: str, *, backup_path: Path | None = None) -> str:
    try:
        with closing(_open_read_only(path, label)) as connection:
            integrity = _integrity_check(connection, label)
            _foreign_key_check(connection, label)
            return integrity
    except OptimizationError as error:
        if backup_path is None:
            raise
        raise OptimizationError(
            f"{error} after optimization; the verified backup is {backup_path}"
        ) from error


def _on_disk_size(path: Path) -> int:
    size = path.stat().st_size
    wal_path = Path(f"{path}-wal")
    if wal_path.is_file():
        size += wal_path.stat().st_size
    return size


def _drive(path: Path) -> str:
    return os.path.splitdrive(str(_resolved(path)))[0].lower()


def _required_free_bytes(files: tuple[InspectedDatabaseFile, ...]) -> int:
    """Estimate the peak extra bytes the run needs on the database drive.

    The backup copy and the WAL written by ``VACUUM`` each reach about the
    compacted size, and the ``VACUUM`` temporary copy adds the same again when
    the SQLite temp directory lives on the database drive.
    """

    compacted = sum(item.compacted_bytes for item in files)
    same_drive = _drive(files[0].path) == _drive(Path(tempfile.gettempdir()))
    return compacted * (3 if same_drive else 2)


def _free_bytes(path: Path) -> int | None:
    try:
        return shutil.disk_usage(path.parent).free
    except OSError:
        return None


def _require_free_space(inspection: DatabaseInspection) -> None:
    if inspection.free_space_ok:
        return
    drive = _drive(inspection.db_path) or "the database drive"
    raise OptimizationError(
        f"insufficient free space on {drive}: {inspection.free_bytes} bytes free, "
        f"about {inspection.required_free_bytes} bytes needed for the backup, "
        "the VACUUM temporary copy, and WAL growth"
    )


def _backup_database(item: InspectedDatabaseFile) -> Path:
    backup_path = _next_backup_path(item.path)
    try:
        with (
            closing(_open_read_write(item.path)) as source,
            closing(sqlite3.connect(backup_path)) as target,
        ):
            source.backup(target)
        _verify_file(backup_path, f"{item.role} backup")
    except BaseException:
        _remove_sqlite_files(backup_path)
        raise
    return backup_path


def _next_backup_path(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak-{timestamp}")
    suffix = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.bak-{timestamp}-{suffix}")
        suffix += 1
    return backup_path


def _remove_sqlite_files(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _optimize_one_database(item: InspectedDatabaseFile) -> str | None:
    """Run the maintenance statements; return the checkpoint outcome for WAL."""

    with closing(_open_read_write(item.path)) as connection:
        # Merge FTS5 segments first so VACUUM compacts the merged index.
        for table in item.fts5_tables:
            quoted = _quote_identifier(table)
            connection.execute(f"INSERT INTO {quoted}({quoted}) VALUES ('optimize')")
        connection.commit()
        connection.execute("VACUUM")
        connection.execute("ANALYZE")
        if item.journal_mode != "wal":
            return None
        row = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        busy = 1 if row is None else int(row[0])
        return "complete" if busy == 0 else "incomplete"


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _aggregate_integrity(values: Iterable[str]) -> str:
    return "ok" if all(str(value).lower() == "ok" for value in values) else "failed"


def _fail(reason: str) -> int:
    print(f"FAIL: {reason}", flush=True)
    return 1


def _print_inspection(inspection: DatabaseInspection) -> None:
    print(f"database={inspection.db_path}")
    print(f"database_kind={inspection.database_kind}")
    print(f"sqlite_version={sqlite3.sqlite_version}")
    print("dry_run=true")
    print(f"size_before={inspection.size}")
    print(f"compacted_estimate={inspection.compacted_bytes}")
    print(f"required_free_bytes={inspection.required_free_bytes}")
    free = "unknown" if inspection.free_bytes is None else inspection.free_bytes
    print(f"free_bytes={free}")
    for item in inspection.files:
        print(f"{item.role}.database={item.path}")
        print(f"{item.role}.journal_mode={item.journal_mode}")
        print(f"{item.role}.size={item.size}")
        print(f"{item.role}.freelist_pages={item.freelist_pages}")
        print(f"{item.role}.fts5_tables={','.join(item.fts5_tables) or 'none'}")
        print(f"{item.role}.integrity={item.integrity}")


def _print_summary(summary: OptimizationSummary) -> None:
    print(f"database={summary.db_path}")
    print(f"database_kind={summary.database_kind}")
    print(f"sqlite_version={sqlite3.sqlite_version}")
    print(f"integrity_before={summary.integrity_before}")
    print(f"integrity_after={summary.integrity_after}")
    print(f"size_before={summary.size_before}")
    print(f"size_after={summary.size_after}")
    for item in summary.files:
        print(f"{item.role}.database={item.path}")
        print(f"{item.role}.backup={item.backup_path}")
        print(f"{item.role}.journal_mode={item.journal_mode}")
        print(f"{item.role}.size_before={item.size_before}")
        print(f"{item.role}.size_after={item.size_after}")
        if item.checkpoint is not None:
            print(f"{item.role}.checkpoint={item.checkpoint}")
            if item.checkpoint != "complete":
                print(
                    f"{item.role}.note=another connection holds the database; "
                    "the WAL folds back on its next checkpoint"
                )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Back up and optimize a dj-track-similarity SQLite database.",
    )
    parser.add_argument(
        "--db",
        required=True,
        metavar="PATH",
        help="Path to the SQLite database file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Verify the database set and report what the run would do "
            "without writing anything."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.dry_run:
            inspection = inspect_database(Path(args.db))
            _require_free_space(inspection)
            _print_inspection(inspection)
            return 0
        summary = optimize_database(Path(args.db))
    except (OptimizationError, sqlite3.Error, OSError, ValueError) as error:
        return _fail(str(error))
    _print_summary(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
