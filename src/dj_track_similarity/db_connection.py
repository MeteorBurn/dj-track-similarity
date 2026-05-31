from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .db_schema import SQLITE_BUSY_TIMEOUT_SECONDS, ensure_schema


_write_locks: dict[Path, threading.RLock] = {}
_write_locks_guard = threading.Lock()


def resolve_database_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def write_lock_for_path(path: str | Path) -> threading.RLock:
    resolved = resolve_database_path(path)
    with _write_locks_guard:
        lock = _write_locks.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _write_locks[resolved] = lock
        return lock


def connect_database(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(resolve_database_path(path), timeout=SQLITE_BUSY_TIMEOUT_SECONDS)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_SECONDS * 1000}")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.execute("PRAGMA cache_size = -32768")
    return connection


def ensure_database_schema(path: str | Path, write_lock: threading.RLock | None = None) -> None:
    resolved = resolve_database_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    lock = write_lock or write_lock_for_path(resolved)
    with lock, connect_database(resolved) as connection:
        ensure_schema(connection)
