"""SQLite connection management for one library database."""

from __future__ import annotations

import errno
import os
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator

from .db_ddl import create_library_schema
from .db_schema import SQLITE_BUSY_TIMEOUT_SECONDS, insert_library, validate_library_schema


_write_locks: dict[Path, threading.RLock] = {}
_write_locks_guard = threading.Lock()


def resolve_database_path(path: str | Path) -> Path:
    raw = str(path).strip()
    if not raw:
        raise ValueError("Database path is required")
    if raw == ":memory:" or raw.lower().startswith("file::memory:"):
        raise ValueError("LibraryDatabase requires a filesystem path")
    return Path(path).expanduser().resolve(strict=False)


def write_lock_for_path(path: str | Path) -> threading.RLock:
    resolved = resolve_database_path(path)
    with _write_locks_guard:
        lock = _write_locks.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _write_locks[resolved] = lock
        return lock


def connect_database(
    path: str | Path,
    *,
    expected_catalog_uuid: str | None = None,
) -> sqlite3.Connection:
    """Open one existing library and validate only its identity row."""

    resolved = resolve_database_path(path)
    connection = _open_existing(resolved)
    try:
        validate_library_schema(
            connection,
            expected_catalog_uuid=expected_catalog_uuid,
            database_path=str(resolved),
        )
        _enforce_wal(connection)
        return connection
    except BaseException:
        connection.close()
        raise


def ensure_database_schema(
    path: str | Path,
    write_lock: threading.RLock | None = None,
) -> str:
    """Create a fresh library or validate an already current one.

    This function never changes an existing database structure.  A former
    legacy split database has no ``library`` row and therefore fails with a
    clear error until the separate, explicit migration is run.
    """

    resolved = resolve_database_path(path)
    if resolved.exists():
        if not resolved.is_file():
            raise ValueError(f"Database path must be a file: {resolved}")
        with closing(_open_existing(resolved)) as connection:
            return validate_library_schema(connection, database_path=str(resolved))

    resolved.parent.mkdir(parents=True, exist_ok=True)
    lock = write_lock or write_lock_for_path(resolved)
    with lock, _bootstrap_file_lock(resolved):
        if resolved.exists():
            if not resolved.is_file():
                raise ValueError(f"Database path must be a file: {resolved}")
            with closing(_open_existing(resolved)) as connection:
                return validate_library_schema(
                    connection,
                    database_path=str(resolved),
                )
        return _create_fresh_library(resolved)


def _create_fresh_library(path: Path) -> str:
    staged = path.with_name(f".{path.name}.{uuid.uuid4().hex}.create.tmp")
    try:
        with closing(sqlite3.connect(staged)) as connection:
            _configure_connection(connection)
            create_library_schema(connection)
            catalog_uuid = insert_library(connection, str(uuid.uuid4()))
            connection.commit()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or str(integrity[0]).lower() != "ok":
                raise RuntimeError(
                    f"Fresh library integrity check failed: {integrity!r}"
                )
        os.replace(staged, path)
        with closing(_open_existing(path)) as connection:
            return validate_library_schema(
                connection,
                expected_catalog_uuid=catalog_uuid,
                database_path=str(path),
            )
    except BaseException:
        _cleanup_staged_sqlite(staged)
        raise


def _open_existing(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=rw",
        timeout=SQLITE_BUSY_TIMEOUT_SECONDS,
        uri=True,
    )
    try:
        _configure_connection(connection)
        return connection
    except BaseException:
        connection.close()
        raise


def _configure_connection(connection: sqlite3.Connection) -> None:
    connection.row_factory = sqlite3.Row
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_SECONDS * 1000}")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA cache_size = -32768")


def _enforce_wal(connection: sqlite3.Connection) -> None:
    journal_mode_row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
    journal_mode = "" if journal_mode_row is None else str(journal_mode_row[0]).lower()
    if journal_mode != "wal":
        raise RuntimeError(
            f"SQLite database could not enter WAL journal mode; got {journal_mode!r}"
        )


def _bootstrap_lock_path(path: Path) -> Path:
    return path.with_name(f".{path.name}.create.lock")


@contextmanager
def _bootstrap_file_lock(path: Path) -> Iterator[None]:
    with _exclusive_file_lock(
        _bootstrap_lock_path(path),
        description="library creation lock",
    ):
        yield


def _try_acquire_os_lock(descriptor: int) -> bool:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                return False
            raise
        return True

    import fcntl

    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in {errno.EACCES, errno.EAGAIN}:
            return False
        raise
    return True


def _release_os_lock(descriptor: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(descriptor, fcntl.LOCK_UN)


@contextmanager
def _exclusive_file_lock(
    lock_path: Path,
    *,
    description: str,
) -> Iterator[None]:
    """Hold one crash-releasing cross-process operating-system file lock."""

    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        if os.fstat(descriptor).st_size < 1:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        deadline = time.monotonic() + SQLITE_BUSY_TIMEOUT_SECONDS
        while not acquired:
            acquired = _try_acquire_os_lock(descriptor)
            if acquired:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out waiting for {description}: {lock_path}")
            time.sleep(0.05)
        yield
    finally:
        try:
            if acquired:
                _release_os_lock(descriptor)
        finally:
            os.close(descriptor)


def _cleanup_staged_sqlite(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass
