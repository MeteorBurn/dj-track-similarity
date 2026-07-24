"""V7-only SQLite connection and two-file bootstrap."""

from __future__ import annotations

import errno
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .db_artifacts import (
    ARTIFACTS_SCHEMA_VERSION,
    create_artifacts_sidecar_schema,
    validate_artifacts_sidecar_schema,
)
from .db_schema import (
    CURRENT_SCHEMA_VERSION,
    SQLITE_BUSY_TIMEOUT_SECONDS,
    insert_library_catalog,
    validate_core_schema,
)
from .db_schema_v7 import create_v7_schema
from .db_storage import StorageDatabasePaths, storage_database_paths


_write_locks: dict[Path, threading.RLock] = {}
_write_locks_guard = threading.Lock()
_BOOTSTRAP_RECEIPT_VERSION = 1
_BOOTSTRAP_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class _FileIdentity:
    device: int
    inode: int
    stable_fallback: int


@dataclass(frozen=True)
class _FileMarker:
    identity: _FileIdentity
    size: int
    modified_ns: int


@dataclass(frozen=True)
class _ValidationSnapshot:
    role: str
    path: Path
    file_marker: _FileMarker
    user_version: int
    schema_cookie: int
    catalog_uuid: str
    storage_schema_version: int | None

    @property
    def file_identity(self) -> _FileIdentity:
        return self.file_marker.identity


class BundleValidationState:
    """Process-local cache of one fully validated Core/Artifacts pair."""

    def __init__(self, core_path: Path, artifacts_path: Path) -> None:
        self.core_path = core_path.resolve(strict=False)
        self.artifacts_path = artifacts_path.resolve(strict=False)
        self._lock = threading.RLock()
        self._snapshots: dict[str, _ValidationSnapshot] = {}

    def _expected_path(self, role: str) -> Path:
        if role == "core":
            return self.core_path
        if role == "artifacts":
            return self.artifacts_path
        raise ValueError(f"unsupported validation role: {role!r}")

    def snapshot(self, role: str, path: Path) -> _ValidationSnapshot | None:
        resolved = path.resolve(strict=False)
        if resolved != self._expected_path(role):
            raise ValueError(
                f"{role} validation path mismatch: "
                f"expected {self._expected_path(role)}, got {resolved}"
            )
        with self._lock:
            return self._snapshots.get(role)

    def record(self, snapshot: _ValidationSnapshot) -> None:
        expected_path = self._expected_path(snapshot.role)
        if snapshot.path != expected_path:
            raise ValueError(
                f"{snapshot.role} validation path mismatch: "
                f"expected {expected_path}, got {snapshot.path}"
            )
        with self._lock:
            self._snapshots[snapshot.role] = snapshot


class _ProjectSQLiteConnection(sqlite3.Connection):
    _dj_opened_file_identity: _FileIdentity
    _dj_validation_role: str
    _dj_validated_catalog_uuid: str
    _dj_validated_schema_cookie: int
    _dj_validated_user_version: int
    _dj_validated_storage_schema_version: int | None


def _file_marker(path: Path) -> _FileMarker:
    stat_result = path.stat()
    inode = int(stat_result.st_ino)
    birth_time = int(getattr(stat_result, "st_birthtime_ns", 0) or 0)
    fallback = (
        birth_time
        if birth_time
        else int(stat_result.st_ctime_ns)
        if os.name == "nt" or inode == 0
        else 0
    )
    return _FileMarker(
        identity=_FileIdentity(
            device=int(stat_result.st_dev),
            inode=inode,
            stable_fallback=fallback,
        ),
        size=int(stat_result.st_size),
        modified_ns=int(stat_result.st_mtime_ns),
    )


def _file_identity(path: Path) -> _FileIdentity:
    return _file_marker(path).identity


def resolve_database_path(path: str | Path) -> Path:
    raw = str(path).strip()
    if not raw:
        raise ValueError("Database path is required")
    if raw == ":memory:" or raw.lower().startswith("file::memory:"):
        raise ValueError(
            "LibraryDatabase requires a filesystem path because the v7 "
            "Artifacts database is mandatory"
        )
    return Path(path).expanduser().resolve(strict=False)


def write_lock_for_path(path: str | Path) -> threading.RLock:
    resolved = resolve_database_path(path)
    with _write_locks_guard:
        lock = _write_locks.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _write_locks[resolved] = lock
        return lock


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


def _open_existing(path: Path) -> sqlite3.Connection:
    for attempt in range(2):
        if not path.is_file():
            raise FileNotFoundError(path)
        identity_before = _file_identity(path)
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=rw",
            timeout=SQLITE_BUSY_TIMEOUT_SECONDS,
            uri=True,
            factory=_ProjectSQLiteConnection,
        )
        try:
            _configure_connection(connection)
        except BaseException:
            connection.close()
            raise
        try:
            identity_after = _file_identity(path)
        except FileNotFoundError:
            connection.close()
            if attempt == 0:
                continue
            raise
        if identity_before != identity_after:
            connection.close()
            if attempt == 0:
                continue
            raise RuntimeError(
                f"SQLite database was replaced while it was being opened: {path}"
            )
        connection._dj_opened_file_identity = identity_after
        return connection
    raise RuntimeError(f"Could not open a stable SQLite database file: {path}")


def _pragma_int(connection: sqlite3.Connection, pragma: str) -> int:
    row = connection.execute(f"PRAGMA {pragma}").fetchone()
    if row is None:
        raise RuntimeError(f"SQLite PRAGMA {pragma} returned no value")
    return int(row[0])


def _require_user_version(
    connection: sqlite3.Connection,
    *,
    role: str,
    expected_version: int,
) -> int:
    version = _pragma_int(connection, "user_version")
    if version != expected_version:
        raise RuntimeError(
            f"SQLite {role} schema version {version} is not supported; "
            f"expected {expected_version}"
        )
    return version


def _preflight_existing_core_version_read_only(path: Path) -> None:
    """Reject a non-v7 Core without changing it or creating lock files."""

    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=ro&immutable=1",
        timeout=SQLITE_BUSY_TIMEOUT_SECONDS,
        uri=True,
    )
    try:
        connection.execute("PRAGMA query_only = ON")
        _require_user_version(
            connection,
            role="Core",
            expected_version=CURRENT_SCHEMA_VERSION,
        )
    finally:
        connection.close()


def _capture_validation_snapshot(
    connection: sqlite3.Connection,
    *,
    role: str,
    path: Path,
) -> _ValidationSnapshot:
    resolved = path.resolve(strict=False)
    opened_identity = getattr(connection, "_dj_opened_file_identity", None)
    marker_before = _file_marker(resolved)
    if opened_identity is None or opened_identity != marker_before.identity:
        raise RuntimeError(
            f"SQLite {role} database was replaced during validation: {resolved}"
        )

    user_version = _pragma_int(connection, "user_version")
    schema_cookie = _pragma_int(connection, "schema_version")
    storage_schema_version: int | None = None
    if role == "core":
        rows = connection.execute(
            "SELECT singleton_id, catalog_uuid FROM library_catalog"
        ).fetchall()
        expected_version = CURRENT_SCHEMA_VERSION
        singleton_name = "library_catalog"
    elif role == "artifacts":
        rows = connection.execute(
            "SELECT singleton_id, catalog_uuid, schema_version FROM storage_metadata"
        ).fetchall()
        expected_version = ARTIFACTS_SCHEMA_VERSION
        singleton_name = "storage_metadata"
        if len(rows) == 1:
            storage_schema_version = int(rows[0][2])
    else:
        raise ValueError(f"unsupported validation role: {role!r}")

    if user_version != expected_version:
        raise RuntimeError(
            f"SQLite {role} schema version {user_version} is not supported; "
            f"expected {expected_version}"
        )
    if len(rows) != 1 or int(rows[0][0]) != 1:
        raise RuntimeError(f"{singleton_name} must contain exactly singleton_id=1")
    catalog_uuid = str(rows[0][1]).strip()
    if not catalog_uuid:
        raise RuntimeError(f"{singleton_name}.catalog_uuid must be non-empty")
    if role == "artifacts" and storage_schema_version != ARTIFACTS_SCHEMA_VERSION:
        raise RuntimeError(
            "storage_metadata.schema_version does not match PRAGMA user_version"
        )
    user_version_after = _pragma_int(connection, "user_version")
    schema_cookie_after = _pragma_int(connection, "schema_version")
    if user_version_after != user_version or schema_cookie_after != schema_cookie:
        raise RuntimeError(
            f"SQLite {role} schema changed during validation: {resolved}"
        )
    marker_after = _file_marker(resolved)
    if marker_after.identity != marker_before.identity:
        raise RuntimeError(
            f"SQLite {role} database was replaced during validation: {resolved}"
        )
    return _ValidationSnapshot(
        role=role,
        path=resolved,
        file_marker=marker_after,
        user_version=user_version_after,
        schema_cookie=schema_cookie_after,
        catalog_uuid=catalog_uuid,
        storage_schema_version=storage_schema_version,
    )


def _mark_validated_connection(
    connection: sqlite3.Connection,
    snapshot: _ValidationSnapshot,
) -> None:
    connection._dj_validation_role = snapshot.role
    connection._dj_validated_catalog_uuid = snapshot.catalog_uuid
    connection._dj_validated_schema_cookie = snapshot.schema_cookie
    connection._dj_validated_user_version = snapshot.user_version
    connection._dj_validated_storage_schema_version = snapshot.storage_schema_version


def _snapshot_matches(
    current: _ValidationSnapshot,
    cached: _ValidationSnapshot | None,
    *,
    expected_catalog_uuid: str | None,
) -> bool:
    return (
        cached is not None
        and current == cached
        and (
            expected_catalog_uuid is None
            or current.catalog_uuid == expected_catalog_uuid
        )
    )


def _validate_core_connection(
    connection: sqlite3.Connection,
    *,
    path: Path,
    expected_catalog_uuid: str | None,
    validation_state: BundleValidationState | None,
) -> _ValidationSnapshot:
    _require_user_version(
        connection,
        role="Core",
        expected_version=CURRENT_SCHEMA_VERSION,
    )
    cached = (
        None if validation_state is None else validation_state.snapshot("core", path)
    )
    current: _ValidationSnapshot | None = None
    if cached is not None:
        try:
            current = _capture_validation_snapshot(
                connection,
                role="core",
                path=path,
            )
        except (sqlite3.Error, RuntimeError, TypeError, ValueError):
            current = None
    if current is not None and _snapshot_matches(
        current,
        cached,
        expected_catalog_uuid=expected_catalog_uuid,
    ):
        _enforce_wal(connection)
        _mark_validated_connection(connection, current)
        return current

    schema_cookie_before = _pragma_int(connection, "schema_version")
    file_identity_before = _file_identity(path)
    catalog_uuid = validate_core_schema(
        connection,
        expected_catalog_uuid=expected_catalog_uuid,
    )
    _enforce_wal(connection)
    current = _capture_validation_snapshot(
        connection,
        role="core",
        path=path,
    )
    if (
        current.schema_cookie != schema_cookie_before
        or current.file_identity != file_identity_before
    ):
        raise RuntimeError("Core schema or file identity changed during validation")
    if current.catalog_uuid != catalog_uuid:
        raise RuntimeError("Core catalog identity changed during validation")
    if validation_state is not None:
        validation_state.record(current)
    _mark_validated_connection(connection, current)
    return current


def _validate_artifacts_connection(
    connection: sqlite3.Connection,
    *,
    path: Path,
    expected_catalog_uuid: str,
    validation_state: BundleValidationState | None,
) -> _ValidationSnapshot:
    _require_user_version(
        connection,
        role="Artifacts",
        expected_version=ARTIFACTS_SCHEMA_VERSION,
    )
    cached = (
        None
        if validation_state is None
        else validation_state.snapshot("artifacts", path)
    )
    current: _ValidationSnapshot | None = None
    if cached is not None:
        try:
            current = _capture_validation_snapshot(
                connection,
                role="artifacts",
                path=path,
            )
        except (sqlite3.Error, RuntimeError, TypeError, ValueError):
            current = None
    if current is not None and _snapshot_matches(
        current,
        cached,
        expected_catalog_uuid=expected_catalog_uuid,
    ):
        _enforce_wal(connection)
        _mark_validated_connection(connection, current)
        return current

    schema_cookie_before = _pragma_int(connection, "schema_version")
    file_identity_before = _file_identity(path)
    catalog_uuid = validate_artifacts_sidecar_schema(
        connection,
        expected_catalog_uuid=expected_catalog_uuid,
    )
    _enforce_wal(connection)
    current = _capture_validation_snapshot(
        connection,
        role="artifacts",
        path=path,
    )
    if (
        current.schema_cookie != schema_cookie_before
        or current.file_identity != file_identity_before
    ):
        raise RuntimeError(
            "Artifacts schema or file identity changed during validation"
        )
    if current.catalog_uuid != catalog_uuid:
        raise RuntimeError("Artifacts catalog identity changed during validation")
    if validation_state is not None:
        validation_state.record(current)
    _mark_validated_connection(connection, current)
    return current


def _validate_required_artifacts_peer(
    *,
    expected_catalog_uuid: str,
    validation_state: BundleValidationState | None,
) -> None:
    if validation_state is None:
        return

    path = validation_state.artifacts_path
    cached = validation_state.snapshot("artifacts", path)
    try:
        current_marker = _file_marker(path)
    except (FileNotFoundError, NotADirectoryError) as error:
        raise RuntimeError(f"Required Artifacts database is missing: {path}") from error

    if (
        cached is not None
        and current_marker == cached.file_marker
        and cached.catalog_uuid == expected_catalog_uuid
    ):
        return

    try:
        _validate_artifacts_file(
            path,
            expected_catalog_uuid,
            validation_state=validation_state,
        )
    except (FileNotFoundError, NotADirectoryError) as error:
        raise RuntimeError(f"Required Artifacts database is missing: {path}") from error


def connect_database(
    path: str | Path,
    *,
    expected_catalog_uuid: str | None = None,
    validation_state: BundleValidationState | None = None,
) -> sqlite3.Connection:
    resolved = resolve_database_path(path)
    connection = _open_existing(resolved)
    try:
        core_snapshot = _validate_core_connection(
            connection,
            path=resolved,
            expected_catalog_uuid=expected_catalog_uuid,
            validation_state=validation_state,
        )
        _validate_required_artifacts_peer(
            expected_catalog_uuid=core_snapshot.catalog_uuid,
            validation_state=validation_state,
        )
    except BaseException:
        connection.close()
        raise
    return connection


def connect_artifacts_database(
    path: str | Path,
    *,
    expected_catalog_uuid: str,
    validation_state: BundleValidationState | None = None,
) -> sqlite3.Connection:
    resolved = Path(path).expanduser().resolve(strict=False)
    connection = _open_existing(resolved)
    try:
        _validate_artifacts_connection(
            connection,
            path=resolved,
            expected_catalog_uuid=expected_catalog_uuid,
            validation_state=validation_state,
        )
    except BaseException:
        connection.close()
        raise
    return connection


def _bootstrap_lock_path(core_path: Path) -> Path:
    return core_path.with_name(f".{core_path.name}.bootstrap.lock")


def _bootstrap_receipt_path(core_path: Path) -> Path:
    return core_path.with_name(f".{core_path.name}.bootstrap.json")


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
    """Hold one crash-releasing cross-process operating-system file lock.

    The small lock file is deliberately persistent and reusable.  Process
    termination releases the operating-system byte/file lock automatically.
    """

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


@contextmanager
def _bootstrap_file_lock(core_path: Path) -> Iterator[None]:
    """Hold the reusable cross-process bootstrap lock for one Core path."""

    with _exclusive_file_lock(
        _bootstrap_lock_path(core_path),
        description="database bootstrap lock",
    ):
        yield


def _sqlite_companion_paths(path: Path) -> tuple[Path, Path, Path]:
    return path, Path(f"{path}-wal"), Path(f"{path}-shm")


def _cleanup_staged_sqlite(path: Path) -> None:
    for candidate in _sqlite_companion_paths(path):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _cleanup_sqlite_companions(path: Path) -> None:
    for candidate in _sqlite_companion_paths(path)[1:]:
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _fsync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDWR)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class _BootstrapReceipt:
    token: str
    catalog_uuid: str
    core_name: str
    artifacts_name: str

    def staged_core_path(self, core_path: Path) -> Path:
        return core_path.with_name(f".{core_path.name}.{self.token}.core.tmp")

    def staged_artifacts_path(self, core_path: Path) -> Path:
        return core_path.with_name(f".{core_path.name}.{self.token}.artifacts.tmp")


def _write_bootstrap_receipt(
    core_path: Path,
    receipt: _BootstrapReceipt,
) -> None:
    receipt_path = _bootstrap_receipt_path(core_path)
    if os.path.lexists(receipt_path):
        raise RuntimeError(f"Bootstrap receipt already exists: {receipt_path}")
    temporary_path = receipt_path.with_name(f"{receipt_path.name}.{receipt.token}.tmp")
    payload = (
        json.dumps(
            {
                "manifest_version": _BOOTSTRAP_RECEIPT_VERSION,
                "stage": "ready",
                "token": receipt.token,
                "catalog_uuid": receipt.catalog_uuid,
                "core_name": receipt.core_name,
                "artifacts_name": receipt.artifacts_name,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    try:
        with temporary_path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, receipt_path)
        _fsync_directory(core_path.parent)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _read_bootstrap_receipt(core_path: Path) -> _BootstrapReceipt | None:
    receipt_path = _bootstrap_receipt_path(core_path)
    if not os.path.lexists(receipt_path):
        return None
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise RuntimeError(f"Bootstrap receipt is not a regular file: {receipt_path}")
    if receipt_path.stat().st_size > 16_384:
        raise RuntimeError(f"Bootstrap receipt is unexpectedly large: {receipt_path}")
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Bootstrap receipt is invalid: {receipt_path}") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"Bootstrap receipt is not a JSON object: {receipt_path}")
    expected_keys = {
        "manifest_version",
        "stage",
        "token",
        "catalog_uuid",
        "core_name",
        "artifacts_name",
    }
    if set(payload) != expected_keys:
        raise RuntimeError(f"Bootstrap receipt fields are invalid: {receipt_path}")
    manifest_version = payload["manifest_version"]
    if (
        isinstance(manifest_version, bool)
        or not isinstance(manifest_version, int)
        or manifest_version != _BOOTSTRAP_RECEIPT_VERSION
        or payload["stage"] != "ready"
    ):
        raise RuntimeError(
            f"Bootstrap receipt version/stage is invalid: {receipt_path}"
        )

    token = payload["token"]
    catalog_uuid = payload["catalog_uuid"]
    core_name = payload["core_name"]
    artifacts_name = payload["artifacts_name"]
    if not isinstance(token, str) or _BOOTSTRAP_TOKEN_PATTERN.fullmatch(token) is None:
        raise RuntimeError(f"Bootstrap receipt token is invalid: {receipt_path}")
    if not isinstance(catalog_uuid, str):
        raise RuntimeError(f"Bootstrap receipt catalog UUID is invalid: {receipt_path}")
    try:
        parsed_catalog_uuid = uuid.UUID(catalog_uuid)
    except ValueError as error:
        raise RuntimeError(
            f"Bootstrap receipt catalog UUID is invalid: {receipt_path}"
        ) from error
    if str(parsed_catalog_uuid) != catalog_uuid:
        raise RuntimeError(
            f"Bootstrap receipt catalog UUID is not canonical: {receipt_path}"
        )
    paths = storage_database_paths(core_path)
    if core_name != core_path.name or artifacts_name != paths.artifacts.name:
        raise RuntimeError(
            f"Bootstrap receipt target names are invalid: {receipt_path}"
        )
    return _BootstrapReceipt(
        token=token,
        catalog_uuid=catalog_uuid,
        core_name=core_name,
        artifacts_name=artifacts_name,
    )


def _validate_core_file(
    path: Path,
    expected_catalog_uuid: str | None = None,
    *,
    validation_state: BundleValidationState | None = None,
) -> str:
    with closing(_open_existing(path)) as connection:
        snapshot = _validate_core_connection(
            connection,
            path=path,
            expected_catalog_uuid=expected_catalog_uuid,
            validation_state=validation_state,
        )
        return snapshot.catalog_uuid


def _validate_artifacts_file(
    path: Path,
    expected_catalog_uuid: str,
    *,
    validation_state: BundleValidationState | None = None,
) -> str:
    with closing(_open_existing(path)) as connection:
        snapshot = _validate_artifacts_connection(
            connection,
            path=path,
            expected_catalog_uuid=expected_catalog_uuid,
            validation_state=validation_state,
        )
        return snapshot.catalog_uuid


def _prepare_staged_file(path: Path, *, core: bool, catalog_uuid: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"Staged SQLite database is not a regular file: {path}")
    with closing(_open_existing(path)) as connection:
        if core:
            validate_core_schema(
                connection,
                expected_catalog_uuid=catalog_uuid,
            )
        else:
            validate_artifacts_sidecar_schema(
                connection,
                expected_catalog_uuid=catalog_uuid,
            )
        _enforce_wal(connection)
        checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint is not None and int(checkpoint[0]) != 0:
            raise RuntimeError(f"Could not checkpoint staged SQLite database: {path}")
    _cleanup_sqlite_companions(path)
    _fsync_file(path)


def _validate_bound_pair(
    core_path: Path,
    artifacts_path: Path,
    *,
    expected_catalog_uuid: str,
    validation_state: BundleValidationState | None = None,
) -> str:
    _validate_core_file(
        core_path,
        expected_catalog_uuid,
        validation_state=validation_state,
    )
    _validate_artifacts_file(
        artifacts_path,
        expected_catalog_uuid,
        validation_state=validation_state,
    )
    return expected_catalog_uuid


def _cleanup_receipt_state(
    core_path: Path,
    receipt: _BootstrapReceipt,
) -> None:
    _cleanup_staged_sqlite(receipt.staged_core_path(core_path))
    _cleanup_staged_sqlite(receipt.staged_artifacts_path(core_path))
    temporary_receipt = _bootstrap_receipt_path(core_path).with_name(
        f"{_bootstrap_receipt_path(core_path).name}.{receipt.token}.tmp"
    )
    try:
        temporary_receipt.unlink()
    except FileNotFoundError:
        pass
    try:
        _bootstrap_receipt_path(core_path).unlink()
    except FileNotFoundError:
        pass
    _fsync_directory(core_path.parent)


def _cleanup_orphan_bootstrap_files(core_path: Path) -> None:
    stage_pattern = re.compile(
        rf"^{re.escape(f'.{core_path.name}.')}"
        r"[0-9a-f]{32}\.(?:core|artifacts)\.tmp(?:-(?:wal|shm))?$"
    )
    receipt_pattern = re.compile(
        rf"^{re.escape(_bootstrap_receipt_path(core_path).name)}"
        r"\.[0-9a-f]{32}\.tmp$"
    )
    removed = False
    for candidate in core_path.parent.iterdir():
        if not (
            stage_pattern.fullmatch(candidate.name)
            or receipt_pattern.fullmatch(candidate.name)
        ):
            continue
        if candidate.is_dir() and not candidate.is_symlink():
            continue
        try:
            candidate.unlink()
            removed = True
        except FileNotFoundError:
            pass
    if removed:
        _fsync_directory(core_path.parent)


def _publish_bootstrap_receipt(
    core_path: Path,
    paths: StorageDatabasePaths,
    receipt: _BootstrapReceipt,
    *,
    validation_state: BundleValidationState | None = None,
) -> str:
    staged_core = receipt.staged_core_path(core_path)
    staged_artifacts = receipt.staged_artifacts_path(core_path)
    if os.path.lexists(core_path) or os.path.lexists(paths.artifacts):
        raise RuntimeError("Database storage set appeared during bootstrap")

    _prepare_staged_file(
        staged_core,
        core=True,
        catalog_uuid=receipt.catalog_uuid,
    )
    _prepare_staged_file(
        staged_artifacts,
        core=False,
        catalog_uuid=receipt.catalog_uuid,
    )

    if os.path.lexists(paths.artifacts):
        raise RuntimeError(
            f"Artifacts target appeared during bootstrap: {paths.artifacts}"
        )
    os.replace(staged_artifacts, paths.artifacts)
    _fsync_directory(core_path.parent)

    if os.path.lexists(core_path):
        raise RuntimeError(f"Core target appeared during bootstrap: {core_path}")
    os.replace(staged_core, core_path)
    _fsync_directory(core_path.parent)

    catalog_uuid = _validate_bound_pair(
        core_path,
        paths.artifacts,
        expected_catalog_uuid=receipt.catalog_uuid,
        validation_state=validation_state,
    )
    _cleanup_receipt_state(core_path, receipt)
    return catalog_uuid


def _recover_bootstrap(
    core_path: Path,
    paths: StorageDatabasePaths,
    *,
    validation_state: BundleValidationState | None = None,
) -> str | None:
    receipt = _read_bootstrap_receipt(core_path)
    if receipt is None:
        _cleanup_orphan_bootstrap_files(core_path)
        return None

    staged_core = receipt.staged_core_path(core_path)
    staged_artifacts = receipt.staged_artifacts_path(core_path)
    core_exists = os.path.lexists(core_path)
    artifacts_exists = os.path.lexists(paths.artifacts)

    if core_exists:
        if not artifacts_exists:
            _validate_core_file(core_path, receipt.catalog_uuid)
            raise RuntimeError(
                "Bootstrap receipt found a published Core without its Artifacts database"
            )
        catalog_uuid = _validate_bound_pair(
            core_path,
            paths.artifacts,
            expected_catalog_uuid=receipt.catalog_uuid,
            validation_state=validation_state,
        )
        _cleanup_receipt_state(core_path, receipt)
        return catalog_uuid

    if artifacts_exists:
        _validate_artifacts_file(paths.artifacts, receipt.catalog_uuid)
        if staged_core.is_symlink() or not staged_core.is_file():
            raise RuntimeError(
                "Bootstrap receipt cannot finish because staged Core is missing"
            )
        _prepare_staged_file(
            staged_core,
            core=True,
            catalog_uuid=receipt.catalog_uuid,
        )
        if os.path.lexists(core_path):
            raise RuntimeError(f"Core target appeared during recovery: {core_path}")
        os.replace(staged_core, core_path)
        _fsync_directory(core_path.parent)
        catalog_uuid = _validate_bound_pair(
            core_path,
            paths.artifacts,
            expected_catalog_uuid=receipt.catalog_uuid,
            validation_state=validation_state,
        )
        _cleanup_receipt_state(core_path, receipt)
        return catalog_uuid

    if (
        staged_core.is_symlink()
        or staged_artifacts.is_symlink()
        or not staged_core.is_file()
        or not staged_artifacts.is_file()
    ):
        _cleanup_receipt_state(core_path, receipt)
        return None
    try:
        return _publish_bootstrap_receipt(
            core_path,
            paths,
            receipt,
            validation_state=validation_state,
        )
    except (OSError, sqlite3.Error, RuntimeError):
        if not os.path.lexists(core_path) and not os.path.lexists(paths.artifacts):
            _cleanup_receipt_state(core_path, receipt)
            return None
        raise


def _create_fresh_storage_set(
    core_path: Path,
    paths: StorageDatabasePaths,
    *,
    validation_state: BundleValidationState | None = None,
) -> str:
    token = uuid.uuid4().hex
    catalog_uuid = str(uuid.uuid4())
    receipt = _BootstrapReceipt(
        token=token,
        catalog_uuid=catalog_uuid,
        core_name=core_path.name,
        artifacts_name=paths.artifacts.name,
    )
    staged_core = receipt.staged_core_path(core_path)
    staged_artifacts = receipt.staged_artifacts_path(core_path)
    receipt_written = False
    try:
        if os.path.lexists(core_path) or os.path.lexists(paths.artifacts):
            raise RuntimeError("Database storage set appeared during bootstrap")
        create_v7_schema(str(staged_core))
        with closing(_open_existing(staged_core)) as core_connection:
            insert_library_catalog(core_connection, catalog_uuid)
            core_connection.commit()

        create_artifacts_sidecar_schema(
            str(staged_artifacts),
            catalog_uuid=catalog_uuid,
        )
        _prepare_staged_file(
            staged_core,
            core=True,
            catalog_uuid=catalog_uuid,
        )
        _prepare_staged_file(
            staged_artifacts,
            core=False,
            catalog_uuid=catalog_uuid,
        )
        if os.path.lexists(core_path) or os.path.lexists(paths.artifacts):
            raise RuntimeError("Database storage set appeared during bootstrap")
        _write_bootstrap_receipt(core_path, receipt)
        receipt_written = True
        return _publish_bootstrap_receipt(
            core_path,
            paths,
            receipt,
            validation_state=validation_state,
        )
    finally:
        if not receipt_written:
            _cleanup_staged_sqlite(staged_core)
            _cleanup_staged_sqlite(staged_artifacts)


def ensure_database_schema(
    path: str | Path,
    write_lock: threading.RLock | None = None,
    *,
    validation_state: BundleValidationState | None = None,
) -> str:
    """Create or exactly validate one v7 Core + required Artifacts pair."""

    resolved = resolve_database_path(path)
    if os.path.lexists(resolved):
        _preflight_existing_core_version_read_only(resolved)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    paths = storage_database_paths(resolved)
    lock = write_lock or write_lock_for_path(resolved)

    with lock, _bootstrap_file_lock(resolved):
        recovered_catalog_uuid = _recover_bootstrap(
            resolved,
            paths,
            validation_state=validation_state,
        )
        if recovered_catalog_uuid is not None:
            return recovered_catalog_uuid

        core_exists = os.path.lexists(resolved)
        artifacts_exists = os.path.lexists(paths.artifacts)

        if not core_exists and not artifacts_exists:
            return _create_fresh_storage_set(
                resolved,
                paths,
                validation_state=validation_state,
            )
        elif not core_exists:
            raise RuntimeError(
                f"Artifacts database exists without its Core database: {paths.artifacts}"
            )
        else:
            if not artifacts_exists:
                _validate_core_file(resolved)
                raise RuntimeError(
                    f"Required Artifacts database is missing: {paths.artifacts}"
                )

        catalog_uuid = _validate_core_file(
            resolved,
            validation_state=validation_state,
        )
        _validate_artifacts_file(
            paths.artifacts,
            catalog_uuid,
            validation_state=validation_state,
        )
        return catalog_uuid
