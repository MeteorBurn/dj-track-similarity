"""One explicit, backup-first migration from the former split library pair.

Normal application startup does not import or run this module.  It exists only
for moving a legacy ``library.sqlite`` plus ``library.artifacts.sqlite`` pair
into the current single-library schema.
"""

from __future__ import annotations

import json
import ntpath
import os
import sqlite3
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db_ddl import create_library_schema
from .db_search_fts import rebuild_track_search_fts


MIGRATION_CONFIRMATION = "MIGRATE SINGLE LIBRARY"
_BUSY_TIMEOUT_SECONDS = 30

_COPY_TABLES: tuple[tuple[str, str, str], ...] = (
    ("tracks", "core", "tracks"),
    ("tags", "core", "tags"),
    ("sonara_features", "core", "sonara"),
    ("maest_genres", "core", "maest_genres"),
    ("maest_embeddings", "artifacts", "maest_embeddings"),
    ("mert_embeddings", "artifacts", "mert_embeddings"),
    ("muq_embeddings", "artifacts", "muq_embeddings"),
    ("clap_embeddings", "artifacts", "clap_embeddings"),
    ("classifier_scores", "core", "classifier_scores"),
    ("likes", "core", "likes"),
    ("pair_feedback", "core", "pair_feedback"),
    ("transition_feedback", "core", "transition_feedback"),
)

class LegacyLibraryMigrationError(RuntimeError):
    """The explicit legacy-pair migration could not finish safely."""


@dataclass(frozen=True, slots=True)
class MigrationResult:
    library_path: Path
    backup_dir: Path
    catalog_uuid: str
    roots: tuple[str, ...]
    copied_rows: Mapping[str, int]
    fts_rows: int
    integrity_check: str
    foreign_key_violations: int


def migrate_legacy_library_database(
    library_path: str | Path,
    *,
    confirm: str,
    backup_root: str | Path | None = None,
) -> MigrationResult:
    """Replace one legacy Core/Artifacts pair after copying it into one DB.

    The caller must stop all SQLite users first.  The function keeps the
    original two files in a new timestamped backup directory, then publishes
    the verified staged replacement as ``library_path``.
    """

    if confirm != MIGRATION_CONFIRMATION:
        raise ValueError(
            "Migration requires the exact confirmation "
            f"{MIGRATION_CONFIRMATION!r}"
        )

    core_path = _required_database(library_path, "Core")
    artifacts_path = _required_database(
        _legacy_artifacts_path(core_path),
        "Artifacts",
    )
    root = Path(backup_root) if backup_root is not None else core_path.parent / "backups"
    backup_dir = _create_backup_directory(root)
    staged_path = core_path.with_name(
        f".{core_path.name}.{uuid.uuid4().hex}.single-library.tmp"
    )
    snapshot_core = backup_dir / f".snapshot-{core_path.name}"
    snapshot_artifacts = backup_dir / f".snapshot-{artifacts_path.name}"

    try:
        with _reserve_legacy_sources((core_path, artifacts_path)) as (core, artifacts):
            core_catalog = _legacy_catalog(core, "library_catalog", "Core")
            artifacts_catalog = _legacy_catalog(
                artifacts,
                "storage_metadata",
                "Artifacts",
            )
            if artifacts_catalog[0] != core_catalog[0]:
                raise LegacyLibraryMigrationError(
                    "Core and Artifacts belong to different library catalogs"
                )
            _require_clean_database(core, "Core")
            _require_clean_database(artifacts, "Artifacts")
            excluded = _require_no_unrepresentable_data(core, artifacts)
            roots = _infer_roots(core)
            source_rows = _source_copy_row_counts(core, artifacts)

            _backup_sqlite(core, snapshot_core)
            _backup_sqlite(artifacts, snapshot_artifacts)
            _require_clean_backup(snapshot_core, core_catalog[0], "Core backup")
            _require_clean_backup(
                snapshot_artifacts,
                artifacts_catalog[0],
                "Artifacts backup",
                metadata_table="storage_metadata",
            )

            copied_rows, fts_rows = _build_staged_library(
                staged_path,
                core_snapshot=snapshot_core,
                artifacts_snapshot=snapshot_artifacts,
                catalog_uuid=core_catalog[0],
                created_at=core_catalog[1],
                updated_at=core_catalog[2],
                roots=roots,
            )
            if copied_rows != source_rows:
                raise LegacyLibraryMigrationError(
                    "Source and staged library row counts differ"
                )
            integrity, foreign_keys = _validate_library(
                staged_path,
                catalog_uuid=core_catalog[0],
                copied_rows=copied_rows,
                fts_rows=fts_rows,
            )

        core_moves: tuple[tuple[Path, Path], ...] = ()
        artifact_moves: tuple[tuple[Path, Path], ...] = ()
        try:
            core_moves = _move_database_with_companions(
                core_path,
                backup_dir / f"legacy-{core_path.name}",
            )
            try:
                os.replace(staged_path, core_path)
            except BaseException:
                _restore_moves(core_moves)
                raise
            try:
                artifact_moves = _move_database_with_companions(
                    artifacts_path,
                    backup_dir / f"legacy-{artifacts_path.name}",
                )
            except BaseException:
                _restore_legacy_pair(
                    core_path,
                    backup_dir / f"failed-{core_path.name}",
                    core_moves,
                    artifact_moves,
                )
                raise
            try:
                integrity, foreign_keys = _validate_library(
                    core_path,
                    catalog_uuid=core_catalog[0],
                    copied_rows=copied_rows,
                    fts_rows=fts_rows,
                )
            except BaseException:
                _restore_legacy_pair(
                    core_path,
                    backup_dir / f"failed-{core_path.name}",
                    core_moves,
                    artifact_moves,
                )
                raise
        except BaseException:
            _cleanup_sqlite(staged_path)
            raise

        _cleanup_sqlite(snapshot_core)
        _cleanup_sqlite(snapshot_artifacts)
        _write_receipt(
            backup_dir,
            catalog_uuid=core_catalog[0],
            roots=roots,
            copied_rows=copied_rows,
            fts_rows=fts_rows,
            integrity_check=integrity,
            foreign_key_violations=foreign_keys,
            excluded=excluded,
        )
        return MigrationResult(
            library_path=core_path,
            backup_dir=backup_dir,
            catalog_uuid=core_catalog[0],
            roots=roots,
            copied_rows=copied_rows,
            fts_rows=fts_rows,
            integrity_check=integrity,
            foreign_key_violations=foreign_keys,
        )
    except BaseException:
        _cleanup_sqlite(staged_path)
        raise


def _legacy_artifacts_path(core_path: Path) -> Path:
    suffix = core_path.suffix
    stem = core_path.stem if suffix else core_path.name
    return core_path.with_name(f"{stem}.artifacts{suffix}")


def _required_database(path: str | Path, label: str) -> Path:
    resolved = Path(path).expanduser().resolve(strict=False)
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} database is not an existing file: {resolved}")
    return resolved


def _create_backup_directory(root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    directory = root.expanduser().resolve(strict=False) / f"{timestamp}-single-library-migration"
    directory.mkdir(parents=True, exist_ok=False)
    return directory


@contextmanager
def _reserve_legacy_sources(paths: Sequence[Path]) -> Iterator[tuple[sqlite3.Connection, ...]]:
    connections: list[sqlite3.Connection] = []
    try:
        for path in paths:
            try:
                connection = sqlite3.connect(
                    f"{path.as_uri()}?mode=rw",
                    uri=True,
                    timeout=_BUSY_TIMEOUT_SECONDS,
                )
                connection.row_factory = sqlite3.Row
                connection.execute(f"PRAGMA busy_timeout = {_BUSY_TIMEOUT_SECONDS * 1000}")
                locking_mode = connection.execute(
                    "PRAGMA locking_mode = EXCLUSIVE"
                ).fetchone()
                if locking_mode is None or str(locking_mode[0]).casefold() != "exclusive":
                    raise LegacyLibraryMigrationError(
                        f"Could not reserve exclusive SQLite access: {path}"
                    )
                connection.execute("BEGIN EXCLUSIVE")
                connection.commit()
            except sqlite3.OperationalError as error:
                raise LegacyLibraryMigrationError(
                    "Could not reserve exclusive SQLite access; stop the server "
                    f"and all database tools, then retry: {path}: {error}"
                ) from error
            connections.append(connection)
        yield tuple(connections)
    finally:
        for connection in reversed(connections):
            if connection.in_transaction:
                connection.rollback()
            connection.close()


def _legacy_catalog(
    connection: sqlite3.Connection,
    table: str,
    label: str,
) -> tuple[str, str, str]:
    try:
        rows = connection.execute(
            f"SELECT singleton_id, catalog_uuid, created_at, updated_at FROM {_quote(table)}"
        ).fetchall()
    except sqlite3.Error as error:
        raise LegacyLibraryMigrationError(
            f"{label} metadata table is unavailable: {table}: {error}"
        ) from error
    if len(rows) != 1 or int(rows[0][0]) != 1:
        raise LegacyLibraryMigrationError(
            f"{label} metadata must contain exactly singleton_id=1"
        )
    catalog_uuid = str(rows[0][1]).strip()
    if not catalog_uuid:
        raise LegacyLibraryMigrationError(f"{label} catalog UUID is empty")
    return catalog_uuid, str(rows[0][2]), str(rows[0][3])


def _require_clean_database(connection: sqlite3.Connection, label: str) -> None:
    integrity = _integrity_check(connection)
    foreign_keys = _foreign_key_violation_count(connection)
    if integrity != "ok" or foreign_keys:
        raise LegacyLibraryMigrationError(
            f"{label} database is not clean: integrity_check={integrity}, "
            f"foreign_key_violations={foreign_keys}"
        )


def _require_clean_backup(
    path: Path,
    catalog_uuid: str,
    label: str,
    *,
    metadata_table: str = "library_catalog",
) -> None:
    with closing(_open_read_only(path)) as connection:
        if _legacy_catalog(connection, metadata_table, label)[0] != catalog_uuid:
            raise LegacyLibraryMigrationError(f"{label} belongs to another catalog")
        _require_clean_database(connection, label)


def _require_no_unrepresentable_data(
    core: sqlite3.Connection,
    artifacts: sqlite3.Connection,
) -> tuple[dict[str, object], ...]:
    allowed_core = {source for _, role, source in _COPY_TABLES if role == "core"}
    allowed_core.update({"library_catalog", "library_settings", "track_search_fts"})
    allowed_artifacts = {
        source for _, role, source in _COPY_TABLES if role == "artifacts"
    }
    allowed_artifacts.add("storage_metadata")

    _reject_nonempty_unknown_tables(core, "core", allowed_core)
    _reject_nonempty_unknown_tables(artifacts, "artifacts", allowed_artifacts)

    settings_count = _row_count(core, "library_settings")
    if not settings_count:
        return ()
    return (
        {
            "database": "core",
            "table": "library_settings",
            "row_count": settings_count,
            "reason": "obsolete derived counters",
        },
    )


def _reject_nonempty_unknown_tables(
    connection: sqlite3.Connection,
    role: str,
    allowed: set[str],
) -> None:
    for table in _user_tables(connection):
        if table in allowed or table.startswith("track_search_fts_"):
            continue
        _reject_nonempty_table(connection, role, table)


def _reject_nonempty_table(
    connection: sqlite3.Connection,
    role: str,
    table: str,
) -> None:
    if table not in _user_tables(connection):
        return
    count = _row_count(connection, table)
    if count:
        raise LegacyLibraryMigrationError(
            "Legacy data has no destination in the current schema: "
            f"{role}.{table} rows={count}"
        )


def _infer_roots(connection: sqlite3.Connection) -> tuple[str, ...]:
    paths = [str(row[0]) for row in connection.execute("SELECT file_path FROM tracks")]
    groups: dict[str, list[str]] = {}
    for path in paths:
        drive, _ = ntpath.splitdrive(path)
        groups.setdefault(drive.casefold(), []).append(path)

    roots: list[str] = []
    for paths_on_drive in groups.values():
        parents = [ntpath.dirname(path) for path in paths_on_drive]
        root = ntpath.commonpath(parents)
        if root:
            roots.append(root.replace("\\", "/"))
    return tuple(sorted(dict.fromkeys(roots), key=str.casefold))


def _source_copy_row_counts(
    core: sqlite3.Connection,
    artifacts: sqlite3.Connection,
) -> dict[str, int]:
    sources = {"core": core, "artifacts": artifacts}
    return {
        target_table: _row_count(sources[source_role], source_table)
        for target_table, source_role, source_table in _COPY_TABLES
    }


def _backup_sqlite(source: sqlite3.Connection, destination: Path) -> None:
    with closing(sqlite3.connect(destination)) as target:
        source.backup(target)
        target.commit()


def _build_staged_library(
    staged_path: Path,
    *,
    core_snapshot: Path,
    artifacts_snapshot: Path,
    catalog_uuid: str,
    created_at: str,
    updated_at: str,
    roots: tuple[str, ...],
) -> tuple[dict[str, int], int]:
    copied_rows: dict[str, int] = {}
    try:
        with closing(sqlite3.connect(staged_path, uri=True)) as target:
            target.row_factory = sqlite3.Row
            target.execute("PRAGMA foreign_keys = ON")
            create_library_schema(target)
            target.execute("ATTACH DATABASE ? AS legacy_core", (_read_only_uri(core_snapshot),))
            target.execute(
                "ATTACH DATABASE ? AS legacy_artifacts",
                (_read_only_uri(artifacts_snapshot),),
            )
            target.execute("BEGIN IMMEDIATE")
            target.execute(
                """
                INSERT INTO library(
                    singleton_id, catalog_uuid, created_at, updated_at, schema_version,
                    roots_json
                ) VALUES (1, ?, ?, ?, 1, ?)
                """,
                (
                    catalog_uuid,
                    created_at,
                    updated_at,
                    json.dumps(roots, ensure_ascii=False, separators=(",", ":")),
                ),
            )
            for target_table, source_role, source_table in _COPY_TABLES:
                source_schema = (
                    "legacy_core" if source_role == "core" else "legacy_artifacts"
                )
                columns = _matching_columns(
                    target,
                    target_table,
                    source_schema,
                    source_table,
                )
                quoted_columns = ", ".join(_quote(column) for column in columns)
                source_count = _attached_row_count(target, source_schema, source_table)
                target.execute(
                    f"INSERT INTO {_quote(target_table)} ({quoted_columns}) "
                    f"SELECT {quoted_columns} FROM {_quote(source_schema)}.{_quote(source_table)}"
                )
                target_count = _row_count(target, target_table)
                if target_count != source_count:
                    raise LegacyLibraryMigrationError(
                        f"Row count changed while copying {source_role}.{source_table}: "
                        f"source={source_count}, target={target_count}"
                    )
                copied_rows[target_table] = target_count
            fts_rows = rebuild_track_search_fts(target)
            target.commit()
            target.execute("DETACH DATABASE legacy_core")
            target.execute("DETACH DATABASE legacy_artifacts")
            _make_self_contained(target, staged_path)
        _cleanup_companions(staged_path)
        return copied_rows, fts_rows
    except BaseException:
        _cleanup_sqlite(staged_path)
        raise


def _matching_columns(
    connection: sqlite3.Connection,
    target_table: str,
    source_schema: str,
    source_table: str,
) -> tuple[str, ...]:
    target_columns = _table_columns(connection, target_table)
    source_columns = _table_columns(connection, source_table, schema=source_schema)
    if set(target_columns) != set(source_columns):
        raise LegacyLibraryMigrationError(
            f"Cannot losslessly copy {source_schema}.{source_table} into "
            f"{target_table}: columns differ"
        )
    return target_columns


def _make_self_contained(connection: sqlite3.Connection, path: Path) -> None:
    checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if checkpoint is not None and int(checkpoint[0]) != 0:
        raise LegacyLibraryMigrationError(
            f"Could not checkpoint staged database: {path}"
        )
    journal_mode = connection.execute("PRAGMA journal_mode = DELETE").fetchone()
    if journal_mode is None or str(journal_mode[0]).casefold() != "delete":
        raise LegacyLibraryMigrationError(
            f"Could not finalize staged database journal mode: {path}"
        )


def _validate_library(
    path: Path,
    *,
    catalog_uuid: str,
    copied_rows: Mapping[str, int],
    fts_rows: int,
) -> tuple[str, int]:
    with closing(_open_read_only(path)) as connection:
        rows = connection.execute("SELECT catalog_uuid FROM library").fetchall()
        if len(rows) != 1 or str(rows[0][0]) != catalog_uuid:
            raise LegacyLibraryMigrationError("Migrated library catalog identity changed")
        for table, expected_count in copied_rows.items():
            actual_count = _row_count(connection, table)
            if actual_count != expected_count:
                raise LegacyLibraryMigrationError(
                    f"Migrated row count differs for {table}: "
                    f"expected={expected_count}, actual={actual_count}"
                )
        actual_fts_rows = _row_count(connection, "track_search_fts")
        if actual_fts_rows != fts_rows:
            raise LegacyLibraryMigrationError(
                "Migrated FTS row count differs: "
                f"expected={fts_rows}, actual={actual_fts_rows}"
            )
        integrity = _integrity_check(connection)
        foreign_keys = _foreign_key_violation_count(connection)
        if integrity != "ok" or foreign_keys:
            raise LegacyLibraryMigrationError(
                "Migrated library is not clean: "
                f"integrity_check={integrity}, foreign_key_violations={foreign_keys}"
            )
        return integrity, foreign_keys


def _move_database_with_companions(
    source: Path,
    destination: Path,
) -> tuple[tuple[Path, Path], ...]:
    moves = tuple(
        (candidate, Path(f"{destination}{suffix}"))
        for candidate, suffix in (
            (source, ""),
            (Path(f"{source}-wal"), "-wal"),
            (Path(f"{source}-shm"), "-shm"),
        )
        if candidate.exists()
    )
    moved: list[tuple[Path, Path]] = []
    try:
        for original, archived in moves:
            os.replace(original, archived)
            moved.append((original, archived))
    except BaseException:
        _restore_moves(tuple(moved))
        raise
    return tuple(moved)


def _restore_legacy_pair(
    current_library: Path,
    failed_library: Path,
    core_moves: Sequence[tuple[Path, Path]],
    artifact_moves: Sequence[tuple[Path, Path]],
) -> None:
    if current_library.exists():
        os.replace(current_library, failed_library)
    _restore_moves(core_moves)
    _restore_moves(artifact_moves)


def _restore_moves(moves: Sequence[tuple[Path, Path]]) -> None:
    for original, archived in reversed(tuple(moves)):
        if archived.exists():
            os.replace(archived, original)


def _write_receipt(
    backup_dir: Path,
    *,
    catalog_uuid: str,
    roots: tuple[str, ...],
    copied_rows: Mapping[str, int],
    fts_rows: int,
    integrity_check: str,
    foreign_key_violations: int,
    excluded: Sequence[dict[str, object]],
) -> None:
    payload = {
        "catalog_uuid": catalog_uuid,
        "copied_rows": dict(copied_rows),
        "excluded": list(excluded),
        "foreign_key_violations": foreign_key_violations,
        "fts_rows": fts_rows,
        "integrity_check": integrity_check,
        "roots": list(roots),
    }
    (backup_dir / "migration-receipt.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _open_read_only(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(_read_only_uri(path), uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _read_only_uri(path: Path) -> str:
    return f"{path.as_uri()}?mode=ro"


def _table_columns(
    connection: sqlite3.Connection,
    table: str,
    *,
    schema: str | None = None,
) -> tuple[str, ...]:
    prefix = f"{_quote(schema)}." if schema is not None else ""
    return tuple(
        str(row[1])
        for row in connection.execute(f"PRAGMA {prefix}table_info({_quote(table)})")
    )


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }


def _attached_row_count(
    connection: sqlite3.Connection,
    schema: str,
    table: str,
) -> int:
    return int(
        connection.execute(
            f"SELECT COUNT(*) FROM {_quote(schema)}.{_quote(table)}"
        ).fetchone()[0]
    )


def _row_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {_quote(table)}").fetchone()[0])


def _integrity_check(connection: sqlite3.Connection) -> str:
    values = tuple(str(row[0]) for row in connection.execute("PRAGMA integrity_check"))
    return "ok" if values == ("ok",) else "; ".join(values)


def _foreign_key_violation_count(connection: sqlite3.Connection) -> int:
    return sum(1 for _ in connection.execute("PRAGMA foreign_key_check"))


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _cleanup_companions(path: Path) -> None:
    for candidate in (Path(f"{path}-wal"), Path(f"{path}-shm")):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def _cleanup_sqlite(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    _cleanup_companions(path)
