"""Explicit backup-first migration for the Core and Artifacts SQLite pair.

Normal application startup never imports this module and never migrates data.
The public functions here are used only by the ``migrate-database`` CLI
command.  Evaluation is outside the two-file replacement boundary: it is
inspected read-only so the plan can report legacy recorded-session identity
keys, but this migration never rewrites it.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Literal, Mapping, Sequence

from .db_artifacts import (
    ArtifactTrackIdentity,
    create_artifacts_sidecar_schema,
    validate_artifacts_sidecar_schema,
    validate_embedding_row_payload,
)
from .db_connection import write_lock_for_path
from .db_ddl import create_core_schema
from .db_schema import validate_core_schema
from .db_search_fts import rebuild_track_search_fts
from .db_storage import migration_recovery_path, storage_database_paths
from .db_structure import inspect_database_structure
from .sonara_core_validation import validate_sonara_core_row


CONFIRMATION_PHRASE = "MIGRATE DATABASE"
_BUSY_TIMEOUT_SECONDS = 30.0
_COPY_BATCH_SIZE = 500

_CORE_COPY_ORDER = (
    "library_settings",
    "tracks",
    "file_tags",
    "sonara",
    "maest_scores",
    "classifier_scores",
    "likes",
    "pair_feedback",
    "transition_feedback",
)
_ARTIFACT_COPY_ORDER = (
    "maest_embeddings",
    "mert_embeddings",
    "muq_embeddings",
    "clap_embeddings",
)
_ARTIFACT_FAMILY = {
    "maest_embeddings": "maest",
    "mert_embeddings": "mert",
    "muq_embeddings": "muq",
    "clap_embeddings": "clap",
}
_CORE_DERIVED_FAMILY = {
    "sonara": "sonara",
    "maest_scores": "maest",
    "classifier_scores": "classifiers",
}
_LEGACY_JSON_IDENTITY_KEYS = frozenset(
    {
        "active_contract_hash",
        "active_release_hash",
        "contract_hash",
        "contract_hashes",
        "expected_contract_hash",
        "expected_release_hash",
        "feature_manifest_hash",
        "manifest_version",
        "model_version",
        "release_hash",
        "required_outputs_hash",
        "schema_version",
        "sonara_release_hash",
        "source_contract_hashes",
    }
)
_LEGACY_SETTING_KEY_FRAGMENTS = (
    "active_contract",
    "active_release",
    "contract_hash",
    "contract_version",
    "expected_contract",
    "expected_release",
    "feature_manifest_hash",
    "manifest_version",
    "model_version",
    "release_hash",
    "required_outputs_hash",
    "schema_version",
    "sonara_release",
    "source_contract",
)


class DatabaseMigrationError(RuntimeError):
    """Raised when an explicit migration cannot complete safely."""


@dataclass(frozen=True, slots=True)
class TableMigration:
    database: Literal["core", "artifacts"]
    table: str
    action: Literal["create", "rebuild", "exclude", "drop"]
    row_count: int
    detail: str


@dataclass(frozen=True, slots=True)
class _SourceFingerprint:
    role: Literal["core", "artifacts"]
    path: Path
    size_bytes: int
    modified_ns: int
    sha256: str
    wal_size_bytes: int
    wal_sha256: str | None


@dataclass(frozen=True, slots=True)
class MigrationPlan:
    core_path: Path
    artifacts_path: Path
    core_changes: tuple[TableMigration, ...]
    artifacts_changes: tuple[TableMigration, ...]
    analysis_families_needing_reanalysis: tuple[str, ...]
    warnings: tuple[str, ...]
    catalog_uuid: str
    source_fingerprints: tuple[_SourceFingerprint, ...]

    @property
    def has_changes(self) -> bool:
        return bool(self.core_changes or self.artifacts_changes)


@dataclass(frozen=True, slots=True)
class MigrationReceipt:
    core_backup: Path
    artifacts_backup: Path
    integrity_check: str
    foreign_key_violations: int
    orphan_count: int
    excluded_rows: tuple[tuple[str, str, int], ...]
    analysis_families_needing_reanalysis: tuple[str, ...]
    recovery_receipt: Path


@dataclass(frozen=True, slots=True)
class _BundleValidation:
    integrity_check: str
    foreign_key_violations: int
    orphan_count: int


def plan_database_migration(core_path: Path) -> MigrationPlan:
    """Inspect a Core/Artifacts pair without writing either database."""

    requested_core = Path(core_path).expanduser().resolve(strict=False)
    _refuse_pending_recovery(requested_core)
    resolved_core = _required_existing_database(requested_core, "Core")
    artifacts_path = storage_database_paths(resolved_core).artifacts
    resolved_artifacts = _required_existing_database(artifacts_path, "Artifacts")
    _require_checkpointed_database(resolved_core, "Core")
    _require_checkpointed_database(resolved_artifacts, "Artifacts")

    with _read_only_connection(resolved_core) as core_connection:
        catalog_uuid = _catalog_uuid(
            core_connection,
            table="library_catalog",
            label="Core",
        )
        core_changes, core_reanalysis = _plan_role(
            core_connection,
            role="core",
        )
    with _read_only_connection(resolved_artifacts) as artifacts_connection:
        artifacts_catalog_uuid = _catalog_uuid(
            artifacts_connection,
            table="storage_metadata",
            label="Artifacts",
        )
        if artifacts_catalog_uuid != catalog_uuid:
            raise DatabaseMigrationError(
                "Core and Artifacts belong to different library catalogs"
            )
        artifacts_changes, artifact_reanalysis = _plan_role(
            artifacts_connection,
            role="artifacts",
        )

    warnings = _evaluation_warnings(resolved_core)
    fingerprints = (
        _source_fingerprint(resolved_core, "core"),
        _source_fingerprint(resolved_artifacts, "artifacts"),
    )
    return MigrationPlan(
        core_path=resolved_core,
        artifacts_path=resolved_artifacts,
        core_changes=core_changes,
        artifacts_changes=artifacts_changes,
        analysis_families_needing_reanalysis=tuple(
            sorted(core_reanalysis | artifact_reanalysis)
        ),
        warnings=warnings,
        catalog_uuid=catalog_uuid,
        source_fingerprints=fingerprints,
    )


def apply_database_migration(
    plan: MigrationPlan,
    backup_dir: Path,
    confirm: str,
) -> MigrationReceipt:
    """Back up, rebuild, validate, and transactionally publish the database pair."""

    if confirm != CONFIRMATION_PHRASE:
        raise ValueError(
            f"Database migration requires the exact confirmation "
            f"{CONFIRMATION_PHRASE!r}"
        )
    if not plan.has_changes:
        raise ValueError("Database structure is already current; nothing to migrate")

    core_path = _required_existing_database(plan.core_path, "Core")
    artifacts_path = _required_existing_database(plan.artifacts_path, "Artifacts")
    backup_root = Path(backup_dir).expanduser().resolve(strict=False)
    replacement_token = uuid.uuid4().hex
    staged_core = core_path.with_name(
        f".{core_path.name}.{replacement_token}.migration.tmp"
    )
    staged_artifacts = artifacts_path.with_name(
        f".{artifacts_path.name}.{replacement_token}.migration.tmp"
    )
    recovery_state = migration_recovery_path(core_path)
    excluded_rows: dict[tuple[str, str], int] = {}
    reanalysis = set(plan.analysis_families_needing_reanalysis)
    backups_ready = False
    artifacts_committed = False
    core_committed = False
    core_backup: Path | None = None
    artifacts_backup: Path | None = None

    try:
        with _project_path_write_locks((core_path, artifacts_path)):
            try:
                with _reserve_sources(
                    (core_path, artifacts_path)
                ) as publication_connections:
                    core_publication, artifacts_publication = (
                        publication_connections
                    )
                    _require_unchanged_sources(plan)
                    core_backup, artifacts_backup = _prepare_backup_paths(
                        backup_root,
                        core_path,
                        artifacts_path,
                    )
                    _backup_sqlite(core_publication, core_backup)
                    _stage_checkpoint("after_core_backup")
                    _backup_sqlite(artifacts_publication, artifacts_backup)
                    _stage_checkpoint("after_artifacts_backup")
                    _validate_backup(
                        core_backup,
                        role="core",
                        expected_catalog_uuid=plan.catalog_uuid,
                    )
                    _validate_backup(
                        artifacts_backup,
                        role="artifacts",
                        expected_catalog_uuid=plan.catalog_uuid,
                    )
                    backups_ready = True
                    _stage_checkpoint("after_backup_validation")

                    _build_core_replacement(
                        core_backup,
                        staged_core,
                        catalog_uuid=plan.catalog_uuid,
                        excluded_rows=excluded_rows,
                        reanalysis=reanalysis,
                    )
                    core_identities = _core_track_identities(staged_core)
                    _build_artifacts_replacement(
                        artifacts_backup,
                        staged_artifacts,
                        catalog_uuid=plan.catalog_uuid,
                        core_identities=core_identities,
                        excluded_rows=excluded_rows,
                        reanalysis=reanalysis,
                    )
                    validation = _validate_current_pair(
                        staged_core,
                        staged_artifacts,
                        expected_catalog_uuid=plan.catalog_uuid,
                    )
                    _require_clean_validation(validation, "replacement pair")
                    _stage_checkpoint("after_replacement_validation")

                    assert (
                        core_backup is not None
                        and artifacts_backup is not None
                    )
                    _write_recovery_state(
                        recovery_state,
                        status="ready",
                        core_path=core_path,
                        artifacts_path=artifacts_path,
                        core_backup=core_backup,
                        artifacts_backup=artifacts_backup,
                    )
                    core_publication.execute("BEGIN IMMEDIATE")
                    artifacts_publication.execute("BEGIN IMMEDIATE")
                    _require_unchanged_sources(plan)
                    _publish_replacement_in_transaction(
                        artifacts_publication,
                        staged_artifacts,
                        role="artifacts",
                    )
                    _publish_replacement_in_transaction(
                        core_publication,
                        staged_core,
                        role="core",
                    )
                    validation = _validate_current_connections(
                        core_publication,
                        artifacts_publication,
                        expected_catalog_uuid=plan.catalog_uuid,
                        core_path=core_path,
                        artifacts_path=artifacts_path,
                    )
                    _require_clean_validation(
                        validation,
                        "transactional replacement pair",
                    )

                    artifacts_committed = True
                    artifacts_publication.commit()
                    _stage_checkpoint("after_first_replace")
                    core_committed = True
                    core_publication.commit()

                validation = _validate_current_pair(
                    core_path,
                    artifacts_path,
                    expected_catalog_uuid=plan.catalog_uuid,
                )
                _require_clean_validation(validation, "opened migrated pair")
                receipt_path = backup_root / "migration-receipt.json"
                receipt = MigrationReceipt(
                    core_backup=core_backup,
                    artifacts_backup=artifacts_backup,
                    integrity_check=validation.integrity_check,
                    foreign_key_violations=validation.foreign_key_violations,
                    orphan_count=validation.orphan_count,
                    excluded_rows=tuple(
                        (role, table, count)
                        for (role, table), count in sorted(
                            excluded_rows.items()
                        )
                        if count
                    ),
                    analysis_families_needing_reanalysis=tuple(
                        sorted(reanalysis)
                    ),
                    recovery_receipt=receipt_path,
                )
                _write_completed_receipt(receipt)
                _unlink_if_exists(recovery_state)
                return receipt
            except BaseException as error:
                if (artifacts_committed or core_committed) and backups_ready:
                    assert (
                        core_backup is not None
                        and artifacts_backup is not None
                    )
                    try:
                        _restore_backup_pair(
                            core_backup=core_backup,
                            artifacts_backup=artifacts_backup,
                            core_path=core_path,
                            artifacts_path=artifacts_path,
                            expected_catalog_uuid=plan.catalog_uuid,
                            restore_core_file=core_committed,
                            restore_artifacts_file=artifacts_committed,
                        )
                        _write_failure_receipt(
                            backup_root,
                            core_backup=core_backup,
                            artifacts_backup=artifacts_backup,
                            error=error,
                        )
                        _unlink_if_exists(recovery_state)
                    except BaseException as recovery_error:
                        raise DatabaseMigrationError(
                            "Database migration failed after pair publication "
                            "began and automatic restoration also failed. Keep "
                            f"the verified backups and recovery state at "
                            f"{recovery_state}: {recovery_error}"
                        ) from error
                elif os.path.lexists(recovery_state):
                    _unlink_if_exists(recovery_state)
                raise
    finally:
        _cleanup_sqlite_path(staged_core)
        _cleanup_sqlite_path(staged_artifacts)


def render_migration_plan(plan: MigrationPlan) -> str:
    lines = [
        "Database migration plan",
        f"Core: {plan.core_path}",
        f"Artifacts: {plan.artifacts_path}",
        f"Changes required: {'yes' if plan.has_changes else 'no'}",
    ]
    for change in (*plan.core_changes, *plan.artifacts_changes):
        lines.append(
            f"- {change.database}.{change.table}: {change.action}; "
            f"rows={change.row_count}; {change.detail}"
        )
    if plan.analysis_families_needing_reanalysis:
        lines.append(
            "Reanalysis after migration (separate command): "
            + ", ".join(plan.analysis_families_needing_reanalysis)
        )
    for warning in plan.warnings:
        lines.append(f"Warning: {warning}")
    if plan.has_changes:
        lines.append(
            f"Apply only with the exact confirmation: {CONFIRMATION_PHRASE}"
        )
    return "\n".join(lines)


def render_migration_receipt(receipt: MigrationReceipt) -> str:
    lines = [
        "Database migration completed",
        f"core_backup={receipt.core_backup}",
        f"artifacts_backup={receipt.artifacts_backup}",
        f"integrity_check={receipt.integrity_check}",
        f"foreign_key_violations={receipt.foreign_key_violations}",
        f"orphan_count={receipt.orphan_count}",
        f"recovery_receipt={receipt.recovery_receipt}",
    ]
    if receipt.excluded_rows:
        lines.append(
            "excluded_rows="
            + ", ".join(
                f"{role}.{table}:{count}"
                for role, table, count in receipt.excluded_rows
            )
        )
    if receipt.analysis_families_needing_reanalysis:
        lines.append(
            "reanalysis_required="
            + ",".join(receipt.analysis_families_needing_reanalysis)
        )
    return "\n".join(lines)


def default_backup_dir(core_path: Path) -> Path:
    resolved = Path(core_path).expanduser().resolve(strict=False)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return resolved.parent / f"{resolved.stem}.migration-backup-{timestamp}"


def _plan_role(
    connection: sqlite3.Connection,
    *,
    role: Literal["core", "artifacts"],
) -> tuple[tuple[TableMigration, ...], set[str]]:
    report = inspect_database_structure(connection, role)
    if report.is_current:
        return (), set()

    expected_columns, expected_additional = _expected_tables(role)
    actual_tables = _user_tables(connection)
    changes: list[TableMigration] = []
    reanalysis: set[str] = set()
    for table, target_columns in expected_columns.items():
        if table in {"library_catalog", "storage_metadata"}:
            row_count = _row_count(connection, table)
            changes.append(
                TableMigration(
                    database=role,
                    table=table,
                    action="rebuild",
                    row_count=row_count,
                    detail="recreate catalog binding without layout identity fields",
                )
            )
            continue
        if role == "core" and table == "track_search_fts":
            changes.append(
                TableMigration(
                    database=role,
                    table=table,
                    action="rebuild",
                    row_count=_row_count(connection, table),
                    detail="rebuild searchable text from migrated Core rows",
                )
            )
            continue
        if table not in actual_tables:
            changes.append(
                TableMigration(
                    database=role,
                    table=table,
                    action="create",
                    row_count=0,
                    detail="table is absent and will be created empty",
                )
            )
            continue
        source_columns = _table_columns(connection, table)
        row_count = _row_count(connection, table)
        missing_required = _required_target_columns(role, table) - set(
            source_columns
        )
        family = _derived_family(role, table)
        if missing_required and row_count and family is not None:
            changes.append(
                TableMigration(
                    database=role,
                    table=table,
                    action="exclude",
                    row_count=row_count,
                    detail=(
                        "derived rows lack required structural fields "
                        + ", ".join(sorted(missing_required))
                    ),
                )
            )
            reanalysis.add(family)
            continue
        if missing_required and row_count:
            changes.append(
                TableMigration(
                    database=role,
                    table=table,
                    action="exclude",
                    row_count=row_count,
                    detail=(
                        "non-derived rows cannot be transferred because fields "
                        "are missing: "
                        + ", ".join(sorted(missing_required))
                    ),
                )
            )
            continue
        removed_columns = sorted(set(source_columns) - set(target_columns))
        added_columns = sorted(set(target_columns) - set(source_columns))
        details: list[str] = []
        if removed_columns:
            details.append("remove columns " + ", ".join(removed_columns))
        if added_columns:
            details.append("add columns " + ", ".join(added_columns))
        if not details:
            details.append("recreate current table definition")
        changes.append(
            TableMigration(
                database=role,
                table=table,
                action="rebuild",
                row_count=row_count,
                detail="; ".join(details),
            )
        )

    expected_names = set(expected_columns) | expected_additional
    for table in sorted(actual_tables - expected_names):
        changes.append(
            TableMigration(
                database=role,
                table=table,
                action="drop",
                row_count=_row_count(connection, table),
                detail="legacy identity or unsupported table is not in current storage",
            )
        )
    return tuple(changes), reanalysis


def _expected_tables(
    role: Literal["core", "artifacts"],
) -> tuple[Mapping[str, tuple[str, ...]], set[str]]:
    if role == "core":
        from .db_schema import _CORE_COLUMNS, _FTS_SHADOW_TABLES

        return _CORE_COLUMNS, set(_FTS_SHADOW_TABLES)
    from .db_artifacts import _ARTIFACT_COLUMNS

    return _ARTIFACT_COLUMNS, set()


@lru_cache(maxsize=2)
def _target_table_info(
    role: Literal["core", "artifacts"],
) -> dict[str, tuple[tuple[str, int, object, int], ...]]:
    connection = sqlite3.connect(":memory:")
    try:
        if role == "core":
            create_core_schema(connection)
        else:
            create_artifacts_sidecar_schema(
                connection,
                catalog_uuid="migration-expected-catalog",
            )
        expected_columns, _ = _expected_tables(role)
        return {
            table: tuple(
                (str(row[1]), int(row[3]), row[4], int(row[5]))
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            )
            for table in expected_columns
        }
    finally:
        connection.close()


def _required_target_columns(
    role: Literal["core", "artifacts"],
    table: str,
) -> set[str]:
    required: set[str] = set()
    for name, not_null, default_value, primary_key in _target_table_info(role)[
        table
    ]:
        if primary_key or (not_null and default_value is None):
            required.add(name)
    return required


def _derived_family(
    role: Literal["core", "artifacts"],
    table: str,
) -> str | None:
    if role == "core":
        return _CORE_DERIVED_FAMILY.get(table)
    return _ARTIFACT_FAMILY.get(table)


def _evaluation_warnings(core_path: Path) -> tuple[str, ...]:
    evaluation_path = storage_database_paths(core_path).evaluation
    if not evaluation_path.is_file():
        return ()
    try:
        _require_checkpointed_database(evaluation_path, "Evaluation")
        with _read_only_connection(evaluation_path) as connection:
            count = _legacy_json_row_count(connection)
    except (OSError, sqlite3.Error, DatabaseMigrationError) as error:
        return (
            "Evaluation is outside this Core/Artifacts migration and could not "
            f"be inspected read-only: {error}",
        )
    if count == 0:
        return ()
    return (
        f"Evaluation contains {count} recorded row(s) with legacy identity "
        "keys. This Core/Artifacts command will not rewrite that sidecar; "
        "current runtime rejects those rows until they are handled separately.",
    )


def _legacy_json_row_count(connection: sqlite3.Connection) -> int:
    tables = _user_tables(connection)
    count = 0
    for table in sorted(tables):
        json_columns = [
            column
            for column in _table_columns(connection, table)
            if column.endswith("_json")
        ]
        for column in json_columns:
            cursor = connection.execute(
                f'SELECT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
            )
            for (raw_value,) in cursor:
                if _json_contains_legacy_identity(raw_value):
                    count += 1
    return count


def _json_contains_legacy_identity(raw_value: object) -> bool:
    if not isinstance(raw_value, str):
        return False
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        return False
    stack = [payload]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            if _LEGACY_JSON_IDENTITY_KEYS.intersection(value):
                return True
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return False


def _prepare_backup_paths(
    backup_dir: Path,
    core_path: Path,
    artifacts_path: Path,
) -> tuple[Path, Path]:
    if os.path.lexists(backup_dir):
        if backup_dir.is_symlink() or not backup_dir.is_dir():
            raise DatabaseMigrationError(
                f"Backup target is not a regular directory: {backup_dir}"
            )
    else:
        backup_dir.mkdir(parents=True)
    core_backup = backup_dir / core_path.name
    artifacts_backup = backup_dir / artifacts_path.name
    for source, target in (
        (core_path, core_backup),
        (artifacts_path, artifacts_backup),
    ):
        if source == target:
            raise DatabaseMigrationError(
                "Backup directory must not resolve to the database directory"
            )
        if os.path.lexists(target):
            raise DatabaseMigrationError(f"Backup target already exists: {target}")
    return core_backup, artifacts_backup


def _backup_sqlite(
    source: sqlite3.Connection,
    target_path: Path,
) -> None:
    with closing(sqlite3.connect(target_path)) as target:
        source.backup(target)
        target.commit()
        checkpoint = target.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if checkpoint is not None and int(checkpoint[0]) != 0:
            raise DatabaseMigrationError(
                f"Could not checkpoint SQLite backup: {target_path}"
            )
        mode = target.execute("PRAGMA journal_mode = DELETE").fetchone()
        if mode is None or str(mode[0]).lower() != "delete":
            raise DatabaseMigrationError(
                f"Could not make SQLite backup self-contained: {target_path}"
            )
    _fsync_file(target_path)
    _fsync_directory(target_path.parent)


def _validate_backup(
    path: Path,
    *,
    role: Literal["core", "artifacts"],
    expected_catalog_uuid: str,
) -> None:
    with _read_only_connection(path) as connection:
        integrity = _integrity_result(connection)
        if integrity != "ok":
            raise DatabaseMigrationError(
                f"{role.title()} backup failed integrity_check: {integrity}"
            )
        table = "library_catalog" if role == "core" else "storage_metadata"
        catalog_uuid = _catalog_uuid(
            connection,
            table=table,
            label=f"{role.title()} backup",
        )
        if catalog_uuid != expected_catalog_uuid:
            raise DatabaseMigrationError(
                f"{role.title()} backup catalog binding mismatch"
            )


def _build_core_replacement(
    source_path: Path,
    target_path: Path,
    *,
    catalog_uuid: str,
    excluded_rows: dict[tuple[str, str], int],
    reanalysis: set[str],
) -> None:
    _cleanup_sqlite_path(target_path)
    target = sqlite3.connect(target_path)
    target.row_factory = sqlite3.Row
    try:
        create_core_schema(target)
        with _read_only_connection(source_path) as source:
            catalog_row = source.execute(
                """
                SELECT created_at, updated_at
                FROM library_catalog
                WHERE singleton_id = 1
                """
            ).fetchone()
            created_at = (
                str(catalog_row["created_at"])
                if catalog_row is not None
                else _utc_timestamp()
            )
            updated_at = (
                str(catalog_row["updated_at"])
                if catalog_row is not None
                else created_at
            )
            target.execute(
                """
                INSERT INTO library_catalog(
                    singleton_id,
                    catalog_uuid,
                    created_at,
                    updated_at
                )
                VALUES (1, ?, ?, ?)
                """,
                (catalog_uuid, created_at, updated_at),
            )
            target.commit()
            for table in _CORE_COPY_ORDER:
                _copy_table(
                    source,
                    target,
                    role="core",
                    table=table,
                    catalog_uuid=catalog_uuid,
                    core_identities=None,
                    excluded_rows=excluded_rows,
                    reanalysis=reanalysis,
                )
            rebuild_track_search_fts(target)
            target.commit()
        _make_self_contained(target, target_path)
    finally:
        target.close()
    _fsync_file(target_path)


def _build_artifacts_replacement(
    source_path: Path,
    target_path: Path,
    *,
    catalog_uuid: str,
    core_identities: Mapping[int, tuple[str, int]],
    excluded_rows: dict[tuple[str, str], int],
    reanalysis: set[str],
) -> None:
    _cleanup_sqlite_path(target_path)
    target = sqlite3.connect(target_path)
    target.row_factory = sqlite3.Row
    try:
        create_artifacts_sidecar_schema(target, catalog_uuid=catalog_uuid)
        with _read_only_connection(source_path) as source:
            for table in _ARTIFACT_COPY_ORDER:
                _copy_table(
                    source,
                    target,
                    role="artifacts",
                    table=table,
                    catalog_uuid=catalog_uuid,
                    core_identities=core_identities,
                    excluded_rows=excluded_rows,
                    reanalysis=reanalysis,
                )
            target.commit()
        _make_self_contained(target, target_path)
    finally:
        target.close()
    _fsync_file(target_path)


def _copy_table(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    *,
    role: Literal["core", "artifacts"],
    table: str,
    catalog_uuid: str,
    core_identities: Mapping[int, tuple[str, int]] | None,
    excluded_rows: dict[tuple[str, str], int],
    reanalysis: set[str],
) -> None:
    if table not in _user_tables(source):
        return
    source_columns = _table_columns(source, table)
    target_columns = tuple(
        str(row[1]) for row in target.execute(f'PRAGMA table_info("{table}")')
    )
    missing_required = _required_target_columns(role, table) - set(source_columns)
    row_count = _row_count(source, table)
    family = _derived_family(role, table)
    if missing_required:
        if row_count == 0:
            return
        if family is None:
            raise DatabaseMigrationError(
                f"{role}.{table} cannot be transferred; required fields are "
                f"missing: {sorted(missing_required)}"
            )
        excluded_rows[(role, table)] = (
            excluded_rows.get((role, table), 0) + row_count
        )
        reanalysis.add(family)
        return

    copied_columns = tuple(
        column for column in target_columns if column in set(source_columns)
    )
    quoted_columns = ", ".join(f'"{column}"' for column in copied_columns)
    placeholders = ", ".join("?" for _ in copied_columns)
    select_cursor = source.execute(
        f'SELECT {quoted_columns} FROM "{table}" ORDER BY rowid'
    )
    insert_sql = (
        f'INSERT INTO "{table}" ({quoted_columns}) VALUES ({placeholders})'
    )
    while rows := select_cursor.fetchmany(_COPY_BATCH_SIZE):
        for row in rows:
            values = {
                column: row[column]
                for column in copied_columns
            }
            if (
                role == "core"
                and table == "library_settings"
                and _legacy_identity_setting(values)
            ):
                continue
            if _exclude_derived_row(
                role=role,
                table=table,
                values=values,
                target=target,
                catalog_uuid=catalog_uuid,
                core_identities=core_identities,
            ):
                excluded_rows[(role, table)] = (
                    excluded_rows.get((role, table), 0) + 1
                )
                if family is not None:
                    reanalysis.add(family)
                continue
            try:
                target.execute(
                    insert_sql,
                    tuple(values[column] for column in copied_columns),
                )
            except sqlite3.IntegrityError:
                if family is None:
                    raise
                excluded_rows[(role, table)] = (
                    excluded_rows.get((role, table), 0) + 1
                )
                reanalysis.add(family)
    target.commit()


def _exclude_derived_row(
    *,
    role: Literal["core", "artifacts"],
    table: str,
    values: Mapping[str, object],
    target: sqlite3.Connection,
    catalog_uuid: str,
    core_identities: Mapping[int, tuple[str, int]] | None,
) -> bool:
    family = _derived_family(role, table)
    if family is None:
        return False
    track_id = _positive_int(values.get("track_id"))
    generation = _positive_int(values.get("content_generation"))
    if track_id is None or generation is None:
        return True
    if role == "core":
        current_track = target.execute(
            """
            SELECT track_uuid, content_generation
            FROM tracks
            WHERE track_id = ?
            """,
            (track_id,),
        ).fetchone()
        if current_track is None or int(current_track[1]) != generation:
            return True
        if (
            table == "classifier_scores"
            and values.get("track_uuid") != str(current_track[0])
        ):
            return True
        if table == "sonara":
            valid, _ = validate_sonara_core_row(
                values,
                expected_track_id=track_id,
                expected_content_generation=generation,
            )
            return not valid
        return False

    assert core_identities is not None
    identity = core_identities.get(track_id)
    if identity is None:
        return True
    track_uuid, current_generation = identity
    if generation != current_generation or values.get("track_uuid") != track_uuid:
        return True
    expected_track = ArtifactTrackIdentity(
        catalog_uuid=catalog_uuid,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=current_generation,
    )
    valid, _ = validate_embedding_row_payload(
        family=_ARTIFACT_FAMILY[table],
        row=values,
        expected_track=expected_track,
    )
    return not valid


def _legacy_identity_setting(values: Mapping[str, object]) -> bool:
    raw_key = values.get("setting_key")
    if not isinstance(raw_key, str):
        return True
    normalized_key = "".join(
        character if character.isalnum() else "_"
        for character in raw_key.casefold()
    )
    if any(
        fragment in normalized_key
        for fragment in _LEGACY_SETTING_KEY_FRAGMENTS
    ):
        return True
    return _json_contains_legacy_identity(values.get("setting_value"))


def _core_track_identities(path: Path) -> dict[int, tuple[str, int]]:
    with _read_only_connection(path) as connection:
        return {
            int(row[0]): (str(row[1]), int(row[2]))
            for row in connection.execute(
                """
                SELECT track_id, track_uuid, content_generation
                FROM tracks
                """
            )
        }


def _publish_replacement_in_transaction(
    destination: sqlite3.Connection,
    replacement_path: Path,
    *,
    role: Literal["core", "artifacts"],
) -> None:
    """Replace one database's logical contents inside its held write transaction."""

    expected_columns, _ = _expected_tables(role)
    with _read_only_connection(replacement_path) as source:
        _drop_user_objects(destination)
        source_table_sql = {
            str(row[0]): str(row[1])
            for row in source.execute(
                """
                SELECT name, sql
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                  AND sql IS NOT NULL
                """
            )
        }
        for table in expected_columns:
            sql = source_table_sql.get(table)
            if sql is None:
                raise DatabaseMigrationError(
                    f"Replacement {role} table definition is missing: {table}"
                )
            destination.execute(sql)

        for table, columns in expected_columns.items():
            if table == "track_search_fts":
                selected = ("rowid", *columns)
            else:
                selected = columns
            quoted = ", ".join(_quote_identifier(column) for column in selected)
            cursor = source.execute(
                f"SELECT {quoted} FROM {_quote_identifier(table)}"
            )
            insert_sql = (
                f"INSERT INTO {_quote_identifier(table)} ({quoted}) "
                f"VALUES ({', '.join('?' for _ in selected)})"
            )
            while rows := cursor.fetchmany(_COPY_BATCH_SIZE):
                destination.executemany(
                    insert_sql,
                    (tuple(row[column] for column in selected) for row in rows),
                )

        for object_type in ("index", "trigger"):
            for _, sql in source.execute(
                """
                SELECT name, sql
                FROM sqlite_master
                WHERE type = ?
                  AND name NOT LIKE 'sqlite_%'
                  AND sql IS NOT NULL
                ORDER BY name
                """,
                (object_type,),
            ):
                destination.execute(str(sql))


def _drop_user_objects(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT type, name, sql
        FROM sqlite_master
        WHERE name NOT LIKE 'sqlite_%'
          AND type IN ('table', 'trigger', 'view')
        ORDER BY type, name
        """
    ).fetchall()
    for object_type, name, _ in rows:
        if str(object_type) in {"trigger", "view"}:
            connection.execute(
                f"DROP {str(object_type).upper()} "
                f"{_quote_identifier(str(name))}"
            )
    table_rows = [
        (str(name), "" if sql is None else str(sql))
        for object_type, name, sql in rows
        if str(object_type) == "table"
    ]
    virtual_tables = [
        name
        for name, sql in table_rows
        if sql.lstrip().upper().startswith("CREATE VIRTUAL TABLE")
    ]
    shadow_prefixes = tuple(f"{name}_" for name in virtual_tables)
    for name in virtual_tables:
        connection.execute(f"DROP TABLE {_quote_identifier(name)}")
    for name, _ in reversed(table_rows):
        if name in virtual_tables or name.startswith(shadow_prefixes):
            continue
        connection.execute(f"DROP TABLE {_quote_identifier(name)}")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _validate_current_pair(
    core_path: Path,
    artifacts_path: Path,
    *,
    expected_catalog_uuid: str,
) -> _BundleValidation:
    with closing(_read_connection(core_path)) as core, closing(
        _read_connection(artifacts_path)
    ) as artifacts:
        return _validate_current_connections(
            core,
            artifacts,
            expected_catalog_uuid=expected_catalog_uuid,
            core_path=core_path,
            artifacts_path=artifacts_path,
        )


def _validate_current_connections(
    core: sqlite3.Connection,
    artifacts: sqlite3.Connection,
    *,
    expected_catalog_uuid: str,
    core_path: Path,
    artifacts_path: Path,
) -> _BundleValidation:
    core_catalog = validate_core_schema(
        core,
        expected_catalog_uuid=expected_catalog_uuid,
        database_path=str(core_path),
    )
    artifacts_catalog = validate_artifacts_sidecar_schema(
        artifacts,
        expected_catalog_uuid=expected_catalog_uuid,
        database_path=str(artifacts_path),
    )
    if core_catalog != artifacts_catalog:
        raise DatabaseMigrationError(
            "Migrated Core and Artifacts catalog binding mismatch"
        )
    integrity_results = (
        _integrity_result(core),
        _integrity_result(artifacts),
    )
    integrity = (
        "ok"
        if integrity_results == ("ok", "ok")
        else "; ".join(integrity_results)
    )
    foreign_key_violations = len(
        core.execute("PRAGMA foreign_key_check").fetchall()
    ) + len(artifacts.execute("PRAGMA foreign_key_check").fetchall())
    identities = {
        int(row[0]): (str(row[1]), int(row[2]))
        for row in core.execute(
            "SELECT track_id, track_uuid, content_generation FROM tracks"
        )
    }
    orphan_count = 0
    for table in ("sonara", "maest_scores"):
        orphan_count += int(
            core.execute(
                f"""
                SELECT COUNT(*)
                FROM {_quote_identifier(table)} AS derived
                LEFT JOIN tracks AS track
                  ON track.track_id = derived.track_id
                WHERE track.track_id IS NULL
                   OR track.content_generation <> derived.content_generation
                """
            ).fetchone()[0]
        )
    orphan_count += int(
        core.execute(
            """
            SELECT COUNT(*)
            FROM classifier_scores AS derived
            LEFT JOIN tracks AS track
              ON track.track_id = derived.track_id
            WHERE track.track_id IS NULL
               OR track.track_uuid <> derived.track_uuid
               OR track.content_generation <> derived.content_generation
            """
        ).fetchone()[0]
    )
    for table in _ARTIFACT_COPY_ORDER:
        for track_id, track_uuid, content_generation in artifacts.execute(
            f"""
            SELECT track_id, track_uuid, content_generation
            FROM {_quote_identifier(table)}
            """
        ):
            if identities.get(int(track_id)) != (
                str(track_uuid),
                int(content_generation),
            ):
                orphan_count += 1
    return _BundleValidation(
        integrity_check=integrity,
        foreign_key_violations=foreign_key_violations,
        orphan_count=orphan_count,
    )


def _require_clean_validation(
    validation: _BundleValidation,
    label: str,
) -> None:
    if (
        validation.integrity_check != "ok"
        or validation.foreign_key_violations
        or validation.orphan_count
    ):
        raise DatabaseMigrationError(
            f"{label} failed validation: "
            f"integrity_check={validation.integrity_check}, "
            f"foreign_key_violations={validation.foreign_key_violations}, "
            f"orphan_count={validation.orphan_count}"
        )


def _restore_backup_pair(
    *,
    core_backup: Path,
    artifacts_backup: Path,
    core_path: Path,
    artifacts_path: Path,
    expected_catalog_uuid: str,
    restore_core_file: bool,
    restore_artifacts_file: bool,
) -> None:
    if restore_artifacts_file:
        _restore_sqlite_backup(artifacts_backup, artifacts_path)
    if restore_core_file:
        _restore_sqlite_backup(core_backup, core_path)
    _validate_backup(
        core_path,
        role="core",
        expected_catalog_uuid=expected_catalog_uuid,
    )
    _validate_backup(
        artifacts_path,
        role="artifacts",
        expected_catalog_uuid=expected_catalog_uuid,
    )


def _restore_sqlite_backup(source_path: Path, target_path: Path) -> None:
    with closing(_read_connection(source_path)) as source, closing(
        sqlite3.connect(target_path, timeout=_BUSY_TIMEOUT_SECONDS)
    ) as target:
        target.execute(
            f"PRAGMA busy_timeout = {int(_BUSY_TIMEOUT_SECONDS * 1000)}"
        )
        source.backup(target)
        target.commit()
        checkpoint = target.execute(
            "PRAGMA wal_checkpoint(TRUNCATE)"
        ).fetchone()
        if checkpoint is not None and int(checkpoint[0]) != 0:
            raise DatabaseMigrationError(
                f"Could not checkpoint restored database: {target_path}"
            )
    _fsync_file(target_path)


def _write_recovery_state(
    path: Path,
    *,
    status: str,
    core_path: Path,
    artifacts_path: Path,
    core_backup: Path,
    artifacts_backup: Path,
) -> None:
    _atomic_write_json(
        path,
        {
            "status": status,
            "core_path": str(core_path),
            "artifacts_path": str(artifacts_path),
            "core_backup": str(core_backup),
            "artifacts_backup": str(artifacts_backup),
            "updated_at": _utc_timestamp(),
        },
    )


def _write_completed_receipt(receipt: MigrationReceipt) -> None:
    _atomic_write_json(
        receipt.recovery_receipt,
        {
            "status": "completed",
            "core_backup": str(receipt.core_backup),
            "artifacts_backup": str(receipt.artifacts_backup),
            "integrity_check": receipt.integrity_check,
            "foreign_key_violations": receipt.foreign_key_violations,
            "orphan_count": receipt.orphan_count,
            "excluded_rows": [
                {"database": role, "table": table, "row_count": count}
                for role, table, count in receipt.excluded_rows
            ],
            "analysis_families_needing_reanalysis": list(
                receipt.analysis_families_needing_reanalysis
            ),
            "completed_at": _utc_timestamp(),
        },
    )


def _write_failure_receipt(
    backup_dir: Path,
    *,
    core_backup: Path,
    artifacts_backup: Path,
    error: BaseException,
) -> None:
    _atomic_write_json(
        backup_dir / "migration-recovery.json",
        {
            "status": "restored",
            "core_backup": str(core_backup),
            "artifacts_backup": str(artifacts_backup),
            "error": f"{type(error).__name__}: {error}",
            "restored_at": _utc_timestamp(),
        },
    )


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    encoded = (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        _unlink_if_exists(temporary)


@contextmanager
def _project_path_write_locks(paths: Sequence[Path]) -> Iterator[None]:
    locks = [
        write_lock_for_path(path)
        for path in sorted(
            {path.resolve(strict=False) for path in paths},
            key=lambda value: str(value).casefold(),
        )
    ]
    for lock in locks:
        lock.acquire()
    try:
        yield
    finally:
        for lock in reversed(locks):
            lock.release()


@contextmanager
def _reserve_sources(
    paths: Sequence[Path],
) -> Iterator[tuple[sqlite3.Connection, ...]]:
    connections: list[sqlite3.Connection] = []
    try:
        for path in paths:
            try:
                connection = sqlite3.connect(
                    f"{path.as_uri()}?mode=rw",
                    uri=True,
                    timeout=_BUSY_TIMEOUT_SECONDS,
                )
                connections.append(connection)
                connection.execute(
                    f"PRAGMA busy_timeout = {int(_BUSY_TIMEOUT_SECONDS * 1000)}"
                )
                connection.execute("PRAGMA foreign_keys = OFF")
                locking_mode = connection.execute(
                    "PRAGMA locking_mode = EXCLUSIVE"
                ).fetchone()
                if (
                    locking_mode is None
                    or str(locking_mode[0]).casefold() != "exclusive"
                ):
                    raise DatabaseMigrationError(
                        f"Could not reserve exclusive SQLite access: {path}"
                    )
                checkpoint = connection.execute(
                    "PRAGMA wal_checkpoint(TRUNCATE)"
                ).fetchone()
                if checkpoint is not None and int(checkpoint[0]) != 0:
                    raise DatabaseMigrationError(
                        "Could not obtain a checkpointed database snapshot; stop "
                        f"the server and all database writers, then retry: {path}"
                    )
                # Force acquisition of the exclusive file lock now. In
                # EXCLUSIVE locking mode SQLite retains it across transaction
                # boundaries until this connection closes.
                connection.execute("BEGIN EXCLUSIVE")
                connection.commit()
            except sqlite3.OperationalError as error:
                raise DatabaseMigrationError(
                    "Could not obtain exclusive SQLite access; stop the server "
                    f"and all database writers, then retry: {path}: {error}"
                ) from error
        yield tuple(connections)
    finally:
        for connection in reversed(connections):
            if connection.in_transaction:
                connection.rollback()
            connection.close()


def _refuse_pending_recovery(core_path: Path) -> None:
    marker = migration_recovery_path(core_path)
    if not os.path.lexists(marker):
        return
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatabaseMigrationError(
            "Pending database migration recovery marker cannot be read at "
            f"{marker}: {error}. Keep the database pair unchanged."
        ) from error
    core_backup = payload.get("core_backup")
    artifacts_backup = payload.get("artifacts_backup")
    raise DatabaseMigrationError(
        "Pending database migration recovery at "
        f"{marker}. Refusing another migration until the verified backup pair "
        "is restored together. Recorded Core backup: "
        f"{core_backup}. Recorded Artifacts backup: {artifacts_backup}. "
        "Keep both current databases and both backups unchanged."
    )


def _require_unchanged_sources(plan: MigrationPlan) -> None:
    actual = (
        _source_fingerprint(plan.core_path, "core"),
        _source_fingerprint(plan.artifacts_path, "artifacts"),
    )
    if actual != plan.source_fingerprints:
        raise DatabaseMigrationError(
            "Database pair changed since migration preview. Stop the server and "
            "all database writers, then rerun migrate-database --dry-run before "
            "applying."
        )


def _source_fingerprint(
    path: Path,
    role: Literal["core", "artifacts"],
) -> _SourceFingerprint:
    stat = path.stat()
    digest = _sha256_file(path)
    wal_path = Path(f"{path}-wal")
    wal_size = wal_path.stat().st_size if wal_path.is_file() else 0
    wal_digest = _sha256_file(wal_path) if wal_size else None
    return _SourceFingerprint(
        role=role,
        path=path,
        size_bytes=stat.st_size,
        modified_ns=stat.st_mtime_ns,
        sha256=digest,
        wal_size_bytes=wal_size,
        wal_sha256=wal_digest,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=ro",
        uri=True,
        timeout=_BUSY_TIMEOUT_SECONDS,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


@contextmanager
def _read_only_connection(path: Path) -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(
        f"{path.as_uri()}?mode=ro&immutable=1",
        uri=True,
        timeout=_BUSY_TIMEOUT_SECONDS,
    )
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        yield connection
    finally:
        connection.close()


def _required_existing_database(path: Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve(strict=False)
    if resolved.is_symlink() or not resolved.is_file():
        raise DatabaseMigrationError(
            f"{label} database is not an existing regular file: {resolved}"
        )
    return resolved


def _require_checkpointed_database(path: Path, label: str) -> None:
    wal_path = Path(f"{path}-wal")
    if wal_path.is_file() and wal_path.stat().st_size:
        raise DatabaseMigrationError(
            f"{label} database has a non-empty WAL file. Stop applications using "
            f"the database and checkpoint it before migration: {wal_path}"
        )


def _catalog_uuid(
    connection: sqlite3.Connection,
    *,
    table: str,
    label: str,
) -> str:
    if table not in _user_tables(connection):
        raise DatabaseMigrationError(f"{label} catalog table is missing: {table}")
    columns = set(_table_columns(connection, table))
    if not {"singleton_id", "catalog_uuid"} <= columns:
        raise DatabaseMigrationError(
            f"{label} catalog binding columns are missing from {table}"
        )
    rows = connection.execute(
        f'SELECT singleton_id, catalog_uuid FROM "{table}"'
    ).fetchall()
    if len(rows) != 1 or int(rows[0][0]) != 1:
        raise DatabaseMigrationError(
            f"{label} catalog binding must contain exactly singleton_id=1"
        )
    catalog_uuid = str(rows[0][1]).strip()
    if not catalog_uuid:
        raise DatabaseMigrationError(f"{label} catalog UUID is empty")
    return catalog_uuid


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }


def _table_columns(
    connection: sqlite3.Connection,
    table: str,
) -> tuple[str, ...]:
    return tuple(
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table}")')
    )


def _row_count(connection: sqlite3.Connection, table: str) -> int:
    if table not in _user_tables(connection):
        return 0
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _integrity_result(connection: sqlite3.Connection) -> str:
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    values = tuple(str(row[0]) for row in rows)
    return "ok" if values == ("ok",) else "; ".join(values)


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _make_self_contained(
    connection: sqlite3.Connection,
    path: Path,
) -> None:
    connection.commit()
    checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if checkpoint is not None and int(checkpoint[0]) != 0:
        raise DatabaseMigrationError(
            f"Could not checkpoint replacement database: {path}"
        )
    mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
    if mode is None or str(mode[0]).lower() != "delete":
        raise DatabaseMigrationError(
            f"Could not make replacement database self-contained: {path}"
        )


def _cleanup_sqlite_companions(path: Path) -> None:
    for candidate in (Path(f"{path}-wal"), Path(f"{path}-shm")):
        _unlink_if_exists(candidate)


def _cleanup_sqlite_path(path: Path) -> None:
    _unlink_if_exists(path)
    _cleanup_sqlite_companions(path)


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink()
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


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _stage_checkpoint(stage: str) -> None:
    """No-op failure-injection boundary for focused migration tests."""

    del stage
