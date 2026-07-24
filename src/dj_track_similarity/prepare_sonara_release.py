"""Crash-recoverable activation of one strict SONARA release.

This module owns orchestration only.  The selected :class:`LibraryDatabase`
owns all live database mutations through ``activate_sonara_release``.  The
orchestrator derives the exact four runtime contracts, creates and verifies a
Core + Artifacts backup pair, and records progress in a durable receipt outside
the databases so an interrupted activation can resume without mixing releases.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import threading
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from .analysis_models import AnalysisOutput, AnalysisResetResult
from .db_artifacts import validate_artifacts_sidecar_schema
from .db_schema import validate_core_schema
from .sonara_contract import SONARA_OUTPUT_KINDS, sonara_runtime_contracts


CONFIRM_STRING = "PREPARE SONARA RELEASE"
RECEIPT_VERSION = 1

_RECEIPT_STAGES = ("started", "backed_up", "activated", "completed")
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_RECEIPT_MAX_BYTES = 64 * 1024
_LOCKED_PATHS: set[Path] = set()
_LOCKED_PATHS_GUARD = threading.Lock()


class PrepareSonaraReleaseError(RuntimeError):
    """Raised when strict SONARA release activation cannot proceed safely."""


class LockHeldError(PrepareSonaraReleaseError):
    """Raised when another release activation holds the same catalog lock."""


class SonaraReleaseDatabase(Protocol):
    """The narrow ``LibraryDatabase`` surface used by this orchestrator."""

    path: Path
    artifacts_path: Path
    catalog_uuid: str

    def connect(self) -> sqlite3.Connection:
        """Open the selected Core database."""

    def connect_artifacts(self) -> sqlite3.Connection:
        """Open the selected catalog's required Artifacts database."""

    def activate_sonara_release(
        self,
        outputs: Sequence[AnalysisOutput],
        *,
        preparation_proof: object,
    ) -> AnalysisResetResult:
        """Activate one exact four-output SONARA release."""


def prepare_sonara_release(
    database: SonaraReleaseDatabase,
    *,
    backup_dir: Path,
    confirm: str,
    sonara_module: Any | None = None,
) -> dict[str, object]:
    """Back up and activate the loaded strict SONARA runtime.

    ``database`` must be the already-selected ``LibraryDatabase`` instance.
    Callers cannot supply a release hash or choose a subset of outputs: both are
    derived from :func:`sonara_runtime_contracts`.  A completed call is
    deterministic and idempotent.  An interrupted call resumes from the
    external receipt for the same catalog, backup directory, and runtime.
    """

    validate_confirm(confirm)
    resolved_backup_dir = validate_backup_dir(backup_dir)
    core_path, artifacts_path, catalog_uuid = _database_identity(database)

    contract_set = sonara_runtime_contracts(sonara_module)
    outputs = tuple(AnalysisOutput(identity) for identity in contract_set.identities)
    _validate_exact_outputs(outputs)

    contract_hashes = {
        output.contract.output_kind: output.contract_hash for output in outputs
    }
    operation_id = _operation_id(
        catalog_uuid=catalog_uuid,
        core_path=core_path,
        artifacts_path=artifacts_path,
        backup_dir=resolved_backup_dir,
        release_hash=contract_set.release_hash,
        contract_hashes=contract_hashes,
    )
    receipt_path = _receipt_path(core_path)

    with _release_file_lock(core_path):
        receipt = _read_receipt(receipt_path)
        if receipt is not None:
            _validate_receipt(receipt)
            if receipt["operation_id"] != operation_id:
                if receipt["stage"] != "completed":
                    raise PrepareSonaraReleaseError(
                        "A different SONARA release activation is incomplete; "
                        f"resume it before starting another one: {receipt_path}"
                    )
                receipt = None

        if receipt is None:
            now = _now_iso()
            receipt = {
                "receipt_version": RECEIPT_VERSION,
                "operation_id": operation_id,
                "stage": "started",
                "catalog_uuid": catalog_uuid,
                "core_path": str(core_path),
                "artifacts_path": str(artifacts_path),
                "backup_dir": str(resolved_backup_dir),
                "release_hash": contract_set.release_hash,
                "contract_hashes": contract_hashes,
                "backups": None,
                "activation_result": None,
                "started_at": now,
                "updated_at": now,
                "completed_at": None,
            }
            _atomic_write_json(receipt_path, receipt)
            _stage_checkpoint("started")
        else:
            _require_matching_operation(
                receipt,
                operation_id=operation_id,
                catalog_uuid=catalog_uuid,
                core_path=core_path,
                artifacts_path=artifacts_path,
                backup_dir=resolved_backup_dir,
                release_hash=contract_set.release_hash,
                contract_hashes=contract_hashes,
            )

        stage = str(receipt["stage"])
        if stage == "completed":
            _verify_recorded_backups(receipt, catalog_uuid=catalog_uuid)
            _ensure_completed_receipt_archive(receipt)
            return _json_copy(receipt)

        if stage == "started":
            backup_records = _create_verified_backups(
                database,
                backup_dir=resolved_backup_dir,
                operation_id=operation_id,
                catalog_uuid=catalog_uuid,
            )
            receipt = _advance_receipt(
                receipt,
                stage="backed_up",
                backups=backup_records,
            )
            _atomic_write_json(receipt_path, receipt)
            _stage_checkpoint("backed_up")
        else:
            _verify_recorded_backups(receipt, catalog_uuid=catalog_uuid)

        if receipt["stage"] in {"backed_up", "activated"}:
            preparation_proof = _mint_sonara_release_activation_proof(
                database,
                outputs,
                receipt,
                confirm=confirm,
            )
            result = database.activate_sonara_release(
                outputs,
                preparation_proof=preparation_proof,
            )
            if not isinstance(result, AnalysisResetResult):
                raise PrepareSonaraReleaseError(
                    "LibraryDatabase.activate_sonara_release returned an "
                    "unexpected result"
                )
            _stage_checkpoint("gateway_committed")
            receipt = _advance_receipt(
                receipt,
                stage="activated",
                activation_result=_reset_result_payload(result),
            )
            _atomic_write_json(receipt_path, receipt)
            _stage_checkpoint("activated")

        receipt = _advance_receipt(
            receipt,
            stage="completed",
            completed_at=_now_iso(),
        )
        _write_completed_receipt_archive(receipt)
        _atomic_write_json(receipt_path, receipt)
        _stage_checkpoint("completed")
        return _json_copy(receipt)


def validate_confirm(confirm: str) -> None:
    """Require the destructive-operation confirmation text verbatim."""

    if confirm != CONFIRM_STRING:
        raise ValueError(
            f'Confirmation string must be exactly "{CONFIRM_STRING}"; '
            f'got "{confirm}"'
        )


def validate_backup_dir(backup_dir: Path) -> Path:
    """Return a canonical existing writable backup directory."""

    resolved = Path(backup_dir).expanduser().resolve(strict=False)
    if not resolved.exists():
        raise ValueError(f"--backup-dir does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"--backup-dir is not a directory: {resolved}")
    try:
        with tempfile.NamedTemporaryFile(dir=resolved, prefix=".sonara-write-", delete=True):
            pass
    except OSError as error:
        raise ValueError(f"--backup-dir is not writable: {resolved}: {error}") from error
    return resolved


def _database_identity(
    database: SonaraReleaseDatabase,
) -> tuple[Path, Path, str]:
    core_path = Path(database.path).expanduser().resolve(strict=True)
    artifacts_path = Path(database.artifacts_path).expanduser().resolve(strict=True)
    if core_path == artifacts_path:
        raise PrepareSonaraReleaseError(
            "Core and Artifacts databases must be distinct files"
        )
    if core_path.is_symlink() or not core_path.is_file():
        raise PrepareSonaraReleaseError(
            f"Core database is not a regular file: {core_path}"
        )
    if artifacts_path.is_symlink() or not artifacts_path.is_file():
        raise PrepareSonaraReleaseError(
            f"Artifacts database is not a regular file: {artifacts_path}"
        )
    catalog_uuid = str(database.catalog_uuid).strip()
    try:
        parsed_catalog_uuid = uuid.UUID(catalog_uuid)
    except ValueError as error:
        raise PrepareSonaraReleaseError(
            "LibraryDatabase catalog_uuid is not a canonical UUID"
        ) from error
    if str(parsed_catalog_uuid) != catalog_uuid:
        raise PrepareSonaraReleaseError(
            "LibraryDatabase catalog_uuid is not a canonical UUID"
        )
    return core_path, artifacts_path, catalog_uuid


def _validate_exact_outputs(outputs: Sequence[AnalysisOutput]) -> None:
    if tuple(output.contract.output_kind for output in outputs) != SONARA_OUTPUT_KINDS:
        raise PrepareSonaraReleaseError(
            "SONARA activation requires exactly core, timeline, embedding, "
            "and fingerprint contracts"
        )
    releases = {output.contract.release_hash for output in outputs}
    if len(releases) != 1:
        raise PrepareSonaraReleaseError(
            "All SONARA output contracts must share one release hash"
        )
    release_hash = next(iter(releases))
    if release_hash is None or _SHA256_PATTERN.fullmatch(release_hash) is None:
        raise PrepareSonaraReleaseError(
            "SONARA runtime release hash must be sha256:<64 lowercase hex>"
        )
    for output in outputs:
        if output.contract.analysis_family != "sonara":
            raise PrepareSonaraReleaseError(
                "SONARA activation received a non-SONARA contract"
            )
        if _SHA256_PATTERN.fullmatch(output.contract_hash) is None:
            raise PrepareSonaraReleaseError(
                "SONARA contract hash must be sha256:<64 lowercase hex>"
            )


def _operation_id(
    *,
    catalog_uuid: str,
    core_path: Path,
    artifacts_path: Path,
    backup_dir: Path,
    release_hash: str,
    contract_hashes: Mapping[str, str],
) -> str:
    payload = {
        "receipt_version": RECEIPT_VERSION,
        "catalog_uuid": catalog_uuid,
        "core_path": str(core_path),
        "artifacts_path": str(artifacts_path),
        "backup_dir": str(backup_dir),
        "release_hash": release_hash,
        "contract_hashes": dict(sorted(contract_hashes.items())),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _receipt_path(core_path: Path) -> Path:
    return core_path.with_name(f".{core_path.name}.prepare-sonara-release.json")


def _lock_path(core_path: Path) -> Path:
    return core_path.with_name(f".{core_path.name}.prepare-sonara-release.lock")


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
def _release_file_lock(core_path: Path) -> Iterator[None]:
    lock_path = _lock_path(core_path)
    if lock_path.is_symlink():
        raise PrepareSonaraReleaseError(
            f"SONARA release lock path is a symbolic link: {lock_path}"
        )

    with _LOCKED_PATHS_GUARD:
        if core_path in _LOCKED_PATHS:
            raise LockHeldError(
                f"SONARA release activation is already running for {core_path}"
            )
        _LOCKED_PATHS.add(core_path)

    descriptor: int | None = None
    acquired = False
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        if os.fstat(descriptor).st_size < 1:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        acquired = _try_acquire_os_lock(descriptor)
        if not acquired:
            raise LockHeldError(
                f"SONARA release activation lock is held for {core_path}"
            )
        yield
    finally:
        try:
            if descriptor is not None and acquired:
                _release_os_lock(descriptor)
        finally:
            if descriptor is not None:
                os.close(descriptor)
            with _LOCKED_PATHS_GUARD:
                _LOCKED_PATHS.discard(core_path)


def _backup_paths(
    *,
    core_path: Path,
    artifacts_path: Path,
    backup_dir: Path,
    operation_id: str,
) -> tuple[Path, Path]:
    token = operation_id.removeprefix("sha256:")
    core_backup = backup_dir / (
        f"{core_path.stem}.pre-sonara-{token}.core.sqlite"
    )
    artifacts_backup = backup_dir / (
        f"{artifacts_path.stem}.pre-sonara-{token}.artifacts.sqlite"
    )
    return core_backup, artifacts_backup


def _create_verified_backups(
    database: SonaraReleaseDatabase,
    *,
    backup_dir: Path,
    operation_id: str,
    catalog_uuid: str,
) -> dict[str, object]:
    core_path = Path(database.path).resolve(strict=True)
    artifacts_path = Path(database.artifacts_path).resolve(strict=True)
    core_backup, artifacts_backup = _backup_paths(
        core_path=core_path,
        artifacts_path=artifacts_path,
        backup_dir=backup_dir,
        operation_id=operation_id,
    )
    staged_core = backup_dir / f".{core_backup.name}.tmp"
    staged_artifacts = backup_dir / f".{artifacts_backup.name}.tmp"

    core_lock: sqlite3.Connection | None = None
    artifacts_lock: sqlite3.Connection | None = None
    try:
        core_lock = database.connect()
        core_lock.execute("BEGIN IMMEDIATE")
        artifacts_lock = database.connect_artifacts()
        artifacts_lock.execute("BEGIN IMMEDIATE")

        _backup_connection(database.connect, staged_core)
        _backup_connection(database.connect_artifacts, staged_artifacts)
        _validate_sqlite_backup(
            staged_core,
            kind="core",
            catalog_uuid=catalog_uuid,
        )
        _validate_sqlite_backup(
            staged_artifacts,
            kind="artifacts",
            catalog_uuid=catalog_uuid,
        )

        os.replace(staged_core, core_backup)
        _fsync_file(core_backup)
        os.replace(staged_artifacts, artifacts_backup)
        _fsync_file(artifacts_backup)
        _fsync_directory(backup_dir)
    except BaseException:
        raise
    finally:
        if artifacts_lock is not None:
            if artifacts_lock.in_transaction:
                artifacts_lock.rollback()
            artifacts_lock.close()
        if core_lock is not None:
            if core_lock.in_transaction:
                core_lock.rollback()
            core_lock.close()
        _unlink_if_exists(staged_core)
        _unlink_if_exists(staged_artifacts)
        _unlink_if_exists(Path(f"{staged_core}-wal"))
        _unlink_if_exists(Path(f"{staged_core}-shm"))
        _unlink_if_exists(Path(f"{staged_artifacts}-wal"))
        _unlink_if_exists(Path(f"{staged_artifacts}-shm"))

    records: dict[str, object] = {
        "core": _backup_record(core_backup),
        "artifacts": _backup_record(artifacts_backup),
    }
    _verify_backup_records(records, catalog_uuid=catalog_uuid)
    return records


def _backup_connection(
    source_factory: Callable[[], sqlite3.Connection],
    target_path: Path,
) -> None:
    _cleanup_sqlite_path(target_path)
    with closing(source_factory()) as source, closing(
        sqlite3.connect(str(target_path))
    ) as target:
        source.backup(target)
        target.commit()
        checkpoint = target.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint is not None and int(checkpoint[0]) != 0:
            raise PrepareSonaraReleaseError(
                f"Could not checkpoint SQLite backup: {target_path}"
            )
        journal_mode = target.execute("PRAGMA journal_mode = DELETE").fetchone()
        if journal_mode is None or str(journal_mode[0]).lower() != "delete":
            raise PrepareSonaraReleaseError(
                f"Could not make SQLite backup self-contained: {target_path}"
            )


def _backup_record(path: Path) -> dict[str, object]:
    stat = path.stat()
    if stat.st_size <= 0:
        raise PrepareSonaraReleaseError(f"SQLite backup is empty: {path}")
    return {
        "path": str(path.resolve(strict=True)),
        "sha256": _sha256_file(path),
        "size_bytes": stat.st_size,
    }


def _validate_sqlite_backup(
    path: Path,
    *,
    kind: str,
    catalog_uuid: str,
) -> None:
    if path.is_symlink() or not path.is_file():
        raise PrepareSonaraReleaseError(
            f"{kind.title()} backup is not a regular file: {path}"
        )
    try:
        with closing(
            sqlite3.connect(f"{path.resolve(strict=True).as_uri()}?mode=ro", uri=True)
        ) as connection:
            connection.execute("PRAGMA query_only = ON")
            quick_check = tuple(
                str(row[0]) for row in connection.execute("PRAGMA quick_check")
            )
            if quick_check != ("ok",):
                raise PrepareSonaraReleaseError(
                    f"{kind.title()} backup failed PRAGMA quick_check: "
                    f"{quick_check}"
                )
            if kind == "core":
                actual_catalog_uuid = validate_core_schema(
                    connection,
                    expected_catalog_uuid=catalog_uuid,
                )
            elif kind == "artifacts":
                actual_catalog_uuid = validate_artifacts_sidecar_schema(
                    connection,
                    expected_catalog_uuid=catalog_uuid,
                )
            else:
                raise AssertionError(f"unsupported backup kind: {kind}")
            if actual_catalog_uuid != catalog_uuid:
                raise PrepareSonaraReleaseError(
                    f"{kind.title()} backup catalog binding mismatch"
                )
    except PrepareSonaraReleaseError:
        raise
    except (sqlite3.Error, RuntimeError) as error:
        raise PrepareSonaraReleaseError(
            f"{kind.title()} backup validation failed: {error}"
        ) from error


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _verify_recorded_backups(
    receipt: Mapping[str, object],
    *,
    catalog_uuid: str,
) -> None:
    backups = receipt.get("backups")
    if not isinstance(backups, Mapping):
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt does not contain its backup pair"
        )
    _verify_backup_records(backups, catalog_uuid=catalog_uuid)


def _verify_backup_records(
    records: Mapping[str, object],
    *,
    catalog_uuid: str,
) -> None:
    if set(records) != {"core", "artifacts"}:
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt must reference Core and Artifacts backups"
        )
    for kind in ("core", "artifacts"):
        raw_record = records[kind]
        if not isinstance(raw_record, Mapping):
            raise PrepareSonaraReleaseError(f"{kind} backup record is invalid")
        path = Path(str(raw_record["path"])).resolve(strict=False)
        if path.is_symlink() or not path.is_file():
            raise PrepareSonaraReleaseError(
                f"Recorded {kind} backup is missing: {path}"
            )
        stat = path.stat()
        expected_size = raw_record["size_bytes"]
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or stat.st_size != expected_size
        ):
            raise PrepareSonaraReleaseError(
                f"Recorded {kind} backup size does not match: {path}"
            )
        expected_hash = raw_record["sha256"]
        actual_hash = _sha256_file(path)
        if actual_hash != expected_hash:
            raise PrepareSonaraReleaseError(
                f"Recorded {kind} backup hash does not match: {path}"
            )
        _validate_sqlite_backup(
            path,
            kind=kind,
            catalog_uuid=catalog_uuid,
        )


def _read_receipt(path: Path) -> dict[str, object] | None:
    if not os.path.lexists(path):
        return None
    if path.is_symlink() or not path.is_file():
        raise PrepareSonaraReleaseError(
            f"SONARA activation receipt is not a regular file: {path}"
        )
    if path.stat().st_size > _RECEIPT_MAX_BYTES:
        raise PrepareSonaraReleaseError(
            f"SONARA activation receipt is unexpectedly large: {path}"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PrepareSonaraReleaseError(
            f"SONARA activation receipt is invalid JSON: {path}"
        ) from error
    if not isinstance(payload, dict):
        raise PrepareSonaraReleaseError(
            f"SONARA activation receipt is not a JSON object: {path}"
        )
    return payload


def _validate_receipt(receipt: Mapping[str, object]) -> None:
    expected_keys = {
        "receipt_version",
        "operation_id",
        "stage",
        "catalog_uuid",
        "core_path",
        "artifacts_path",
        "backup_dir",
        "release_hash",
        "contract_hashes",
        "backups",
        "activation_result",
        "started_at",
        "updated_at",
        "completed_at",
    }
    if set(receipt) != expected_keys:
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt fields are invalid"
        )
    if receipt["receipt_version"] != RECEIPT_VERSION or isinstance(
        receipt["receipt_version"], bool
    ):
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt version is invalid"
        )

    stage = receipt["stage"]
    if not isinstance(stage, str) or stage not in _RECEIPT_STAGES:
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt stage is invalid"
        )
    for key in (
        "operation_id",
        "catalog_uuid",
        "core_path",
        "artifacts_path",
        "backup_dir",
        "release_hash",
        "started_at",
        "updated_at",
    ):
        if not isinstance(receipt[key], str) or not str(receipt[key]).strip():
            raise PrepareSonaraReleaseError(
                f"SONARA activation receipt {key} is invalid"
            )
    for key in ("operation_id", "release_hash"):
        if _SHA256_PATTERN.fullmatch(str(receipt[key])) is None:
            raise PrepareSonaraReleaseError(
                f"SONARA activation receipt {key} is not a full SHA-256 hash"
            )
    for key in ("core_path", "artifacts_path", "backup_dir"):
        if not Path(str(receipt[key])).is_absolute():
            raise PrepareSonaraReleaseError(
                f"SONARA activation receipt {key} is not absolute"
            )
    try:
        parsed_catalog_uuid = uuid.UUID(str(receipt["catalog_uuid"]))
    except ValueError as error:
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt catalog UUID is invalid"
        ) from error
    if str(parsed_catalog_uuid) != receipt["catalog_uuid"]:
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt catalog UUID is not canonical"
        )

    contract_hashes = receipt["contract_hashes"]
    if not isinstance(contract_hashes, Mapping) or set(contract_hashes) != set(
        SONARA_OUTPUT_KINDS
    ):
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt contract hashes are invalid"
        )
    if any(
        not isinstance(value, str)
        or _SHA256_PATTERN.fullmatch(value) is None
        for value in contract_hashes.values()
    ):
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt has an invalid contract hash"
        )
    _validate_timestamp(str(receipt["started_at"]), "started_at")
    _validate_timestamp(str(receipt["updated_at"]), "updated_at")

    backups = receipt["backups"]
    activation_result = receipt["activation_result"]
    completed_at = receipt["completed_at"]
    if stage == "started":
        if backups is not None or activation_result is not None or completed_at is not None:
            raise PrepareSonaraReleaseError(
                "Started SONARA activation receipt has completed-stage data"
            )
        return

    _validate_backup_record_shape(backups)
    if stage == "backed_up":
        if activation_result is not None or completed_at is not None:
            raise PrepareSonaraReleaseError(
                "Backed-up SONARA activation receipt has invalid stage data"
            )
        return

    _validate_activation_result(activation_result)
    if stage == "activated":
        if completed_at is not None:
            raise PrepareSonaraReleaseError(
                "Activated SONARA receipt already has completed_at"
            )
        return

    if not isinstance(completed_at, str) or not completed_at.strip():
        raise PrepareSonaraReleaseError(
            "Completed SONARA activation receipt lacks completed_at"
        )
    _validate_timestamp(completed_at, "completed_at")


def _validate_backup_record_shape(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) != {"core", "artifacts"}:
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt backup records are invalid"
        )
    for kind in ("core", "artifacts"):
        record = value[kind]
        if not isinstance(record, Mapping) or set(record) != {
            "path",
            "sha256",
            "size_bytes",
        }:
            raise PrepareSonaraReleaseError(
                f"SONARA activation receipt {kind} backup record is invalid"
            )
        if (
            not isinstance(record["path"], str)
            or not Path(record["path"]).is_absolute()
            or not isinstance(record["sha256"], str)
            or _SHA256_PATTERN.fullmatch(record["sha256"]) is None
            or isinstance(record["size_bytes"], bool)
            or not isinstance(record["size_bytes"], int)
            or record["size_bytes"] <= 0
        ):
            raise PrepareSonaraReleaseError(
                f"SONARA activation receipt {kind} backup values are invalid"
            )


def _validate_activation_result(value: object) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "core_rows_deleted",
        "artifact_rows_deleted",
        "classifier_rows_deleted",
    }:
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt result is invalid"
        )
    for count in value.values():
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise PrepareSonaraReleaseError(
                "SONARA activation receipt deletion count is invalid"
            )


def _validate_timestamp(value: str, field_name: str) -> None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise PrepareSonaraReleaseError(
            f"SONARA activation receipt {field_name} is invalid"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PrepareSonaraReleaseError(
            f"SONARA activation receipt {field_name} must be timezone-aware"
        )


def _require_matching_operation(
    receipt: Mapping[str, object],
    *,
    operation_id: str,
    catalog_uuid: str,
    core_path: Path,
    artifacts_path: Path,
    backup_dir: Path,
    release_hash: str,
    contract_hashes: Mapping[str, str],
) -> None:
    expected = {
        "operation_id": operation_id,
        "catalog_uuid": catalog_uuid,
        "core_path": str(core_path),
        "artifacts_path": str(artifacts_path),
        "backup_dir": str(backup_dir),
        "release_hash": release_hash,
        "contract_hashes": dict(contract_hashes),
    }
    mismatches = [
        key for key, value in expected.items() if receipt.get(key) != value
    ]
    if mismatches:
        raise PrepareSonaraReleaseError(
            "SONARA activation receipt does not match the selected database "
            f"and runtime: {', '.join(mismatches)}"
        )


def _activation_proof_seam():
    """Create the private one-shot proof seam used by the database gateway."""

    nonce = object()

    class _ActivationProof:
        __slots__ = (
            "_contract_hashes",
            "_database",
            "_nonce",
            "_operation_id",
            "_receipt_path",
            "_release_hash",
            "_used",
        )

        def __init__(self) -> None:
            raise TypeError(
                "SONARA activation proofs are created by prepare_sonara_release()"
            )

    def _receipt_context(
        database: SonaraReleaseDatabase,
        outputs: Sequence[AnalysisOutput],
        receipt: Mapping[str, object],
    ) -> tuple[Path, str, str, dict[str, str]]:
        _validate_exact_outputs(outputs)
        core_path, artifacts_path, catalog_uuid = _database_identity(database)
        _validate_receipt(receipt)
        if receipt["stage"] not in {"backed_up", "activated"}:
            raise PrepareSonaraReleaseError(
                "SONARA activation requires a backed-up preparation receipt"
            )
        backup_dir = Path(str(receipt["backup_dir"])).resolve(strict=True)
        contract_hashes = {
            output.contract.output_kind: output.contract_hash
            for output in outputs
        }
        release_hash = str(outputs[0].contract.release_hash)
        operation_id = _operation_id(
            catalog_uuid=catalog_uuid,
            core_path=core_path,
            artifacts_path=artifacts_path,
            backup_dir=backup_dir,
            release_hash=release_hash,
            contract_hashes=contract_hashes,
        )
        _require_matching_operation(
            receipt,
            operation_id=operation_id,
            catalog_uuid=catalog_uuid,
            core_path=core_path,
            artifacts_path=artifacts_path,
            backup_dir=backup_dir,
            release_hash=release_hash,
            contract_hashes=contract_hashes,
        )
        _verify_recorded_backups(receipt, catalog_uuid=catalog_uuid)
        return (
            _receipt_path(core_path),
            operation_id,
            release_hash,
            contract_hashes,
        )

    def mint(
        database: SonaraReleaseDatabase,
        outputs: Sequence[AnalysisOutput],
        receipt: Mapping[str, object],
        *,
        confirm: str,
    ) -> object:
        validate_confirm(confirm)
        receipt_path, operation_id, release_hash, contract_hashes = (
            _receipt_context(database, outputs, receipt)
        )
        persisted = _read_receipt(receipt_path)
        if persisted is None or persisted != dict(receipt):
            raise PrepareSonaraReleaseError(
                "SONARA activation receipt is not durably recorded"
            )
        proof = object.__new__(_ActivationProof)
        object.__setattr__(proof, "_nonce", nonce)
        object.__setattr__(proof, "_database", database)
        object.__setattr__(proof, "_receipt_path", receipt_path)
        object.__setattr__(proof, "_operation_id", operation_id)
        object.__setattr__(proof, "_release_hash", release_hash)
        object.__setattr__(proof, "_contract_hashes", contract_hashes)
        object.__setattr__(proof, "_used", False)
        return proof

    def require(
        proof: object,
        database: SonaraReleaseDatabase,
        outputs: Sequence[AnalysisOutput],
    ) -> None:
        if (
            not isinstance(proof, _ActivationProof)
            or proof._nonce is not nonce
            or proof._database is not database
            or proof._used
        ):
            raise RuntimeError(
                "SONARA release activation requires a validated "
                "prepare-sonara-release receipt"
            )
        persisted = _read_receipt(proof._receipt_path)
        if persisted is None:
            raise PrepareSonaraReleaseError(
                "SONARA activation receipt disappeared before the database gateway"
            )
        receipt_path, operation_id, release_hash, contract_hashes = (
            _receipt_context(database, outputs, persisted)
        )
        if (
            receipt_path != proof._receipt_path
            or operation_id != proof._operation_id
            or release_hash != proof._release_hash
            or contract_hashes != proof._contract_hashes
        ):
            raise PrepareSonaraReleaseError(
                "SONARA activation proof does not match the selected database "
                "and runtime"
            )
        object.__setattr__(proof, "_used", True)

    return mint, require


(
    _mint_sonara_release_activation_proof,
    _require_sonara_release_activation_proof,
) = _activation_proof_seam()
del _activation_proof_seam


def _advance_receipt(
    receipt: Mapping[str, object],
    *,
    stage: str,
    backups: Mapping[str, object] | None = None,
    activation_result: Mapping[str, int] | None = None,
    completed_at: str | None = None,
) -> dict[str, object]:
    current_stage = str(receipt["stage"])
    if _RECEIPT_STAGES.index(stage) < _RECEIPT_STAGES.index(current_stage):
        raise PrepareSonaraReleaseError(
            f"Cannot move SONARA receipt backward from {current_stage} to {stage}"
        )
    updated = dict(receipt)
    updated["stage"] = stage
    updated["updated_at"] = _now_iso()
    if backups is not None:
        updated["backups"] = dict(backups)
    if activation_result is not None:
        updated["activation_result"] = dict(activation_result)
    if completed_at is not None:
        updated["completed_at"] = completed_at
    _validate_receipt(updated)
    return updated


def _reset_result_payload(result: AnalysisResetResult) -> dict[str, int]:
    return {
        "core_rows_deleted": result.core_rows_deleted,
        "artifact_rows_deleted": result.artifact_rows_deleted,
        "classifier_rows_deleted": result.classifier_rows_deleted,
    }


def _completed_receipt_archive_path(
    receipt: Mapping[str, object],
) -> Path:
    backup_dir = Path(str(receipt["backup_dir"]))
    core_stem = Path(str(receipt["core_path"])).stem
    token = str(receipt["operation_id"]).removeprefix("sha256:")
    return backup_dir / f"{core_stem}.pre-sonara-{token}.receipt.json"


def _write_completed_receipt_archive(
    receipt: Mapping[str, object],
) -> None:
    _atomic_write_json(_completed_receipt_archive_path(receipt), receipt)


def _ensure_completed_receipt_archive(
    receipt: Mapping[str, object],
) -> None:
    archive_path = _completed_receipt_archive_path(receipt)
    archived = _read_receipt(archive_path)
    if archived is None:
        _atomic_write_json(archive_path, receipt)
        return
    _validate_receipt(archived)
    if archived != receipt:
        raise PrepareSonaraReleaseError(
            f"Completed SONARA receipt archive does not match: {archive_path}"
        )


def _atomic_write_json(
    path: Path,
    payload: Mapping[str, object],
) -> None:
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    if len(encoded) > _RECEIPT_MAX_BYTES:
        raise PrepareSonaraReleaseError(
            f"SONARA activation receipt is unexpectedly large: {path}"
        )
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        _unlink_if_exists(temporary_path)
        with temporary_path.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        _unlink_if_exists(temporary_path)


def _json_copy(value: Mapping[str, object]) -> dict[str, object]:
    copied = json.loads(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    if not isinstance(copied, dict):
        raise AssertionError("receipt JSON copy is not an object")
    return copied


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


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _cleanup_sqlite_path(path: Path) -> None:
    _unlink_if_exists(path)
    _unlink_if_exists(Path(f"{path}-wal"))
    _unlink_if_exists(Path(f"{path}-shm"))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stage_checkpoint(stage: str) -> None:
    """No-op crash-injection boundary used by focused subprocess tests."""

    del stage
