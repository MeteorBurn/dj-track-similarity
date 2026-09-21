"""Move single-vector MuQ and MAEST tables to per-layer storage (one-off).

Every stored vector becomes the default layer (13) of the per-layer table and
keeps its track_uuid and analyzed_at, so it stays readable, searchable and
analysis-ready at the default layer; resetting the family refills all layers.
Every per-layer table, MERT-v2 included, also gets its partial default-layer
index when it lacks one.

Dry run by default: it reports each table and exactly what would change.
``--apply`` refuses on any row that fails the embedding validator, backs the
database up with the SQLite backup API and checks that copy, then changes all
tables in one transaction that commits only after the integrity, foreign-key,
row-count, shape and index checks pass. Stop the server before ``--apply``.

Delete this script, as AGENTS.md requires, once the owner's databases are
migrated.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from dj_track_similarity.analysis_models import EMBEDDING_LAYERS
from dj_track_similarity.db.connection import connect_database, connect_database_read_only
from dj_track_similarity.db.ddl import (
    LAYERED_EMBEDDINGS_DDL,
    LAYERED_EMBEDDINGS_DEFAULT_INDEX_DDL,
)
from dj_track_similarity.db.embedding_layers import embedding_layers_capability
from dj_track_similarity.db.embeddings import (
    EmbeddingTrackIdentity,
    validate_embedding_row_payload,
)
from dj_track_similarity.db.schema import validate_library_schema

# Only these tables ever had the single-vector shape this script reshapes.
RESHAPED_FAMILIES = ("muq", "maest")
_SINGLE_VECTOR_COLUMNS = (
    "track_id", "track_uuid", "dim", "normalization", "embedding_blob", "analyzed_at",
)
_OFFENDER_SAMPLE = 20


def _default_index(family: str) -> str:
    return f"idx_{family}_embeddings_default"


def _has_index(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'index' AND name = ?", (name,)
    ).fetchone() is not None


def _inspect(connection: sqlite3.Connection, family: str, catalog_uuid: str) -> dict:
    table = f"{family}_embeddings"
    state = embedding_layers_capability(connection, family)
    report: dict = {"family": family, "table": table, "state": state, "add_index": False}
    if state == "absent":
        return report
    report["rows"] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    report["specs"] = [
        (row[0], row[1], int(row[2]))
        for row in connection.execute(
            f"SELECT dim, normalization, COUNT(*) FROM {table} "
            "GROUP BY dim, normalization ORDER BY dim, normalization"
        )
    ]
    if state == "ready":
        report["add_index"] = not _has_index(connection, _default_index(family))
        return report
    columns = [
        (str(row["name"]), int(row["pk"]))
        for row in connection.execute(f"PRAGMA table_info({table})")
    ]
    if (
        family not in RESHAPED_FAMILIES
        or tuple(name for name, _pk in columns) != _SINGLE_VECTOR_COLUMNS
        or [name for name, pk in columns if pk] != ["track_id"]
    ):
        report["state"] = "unknown shape"
        report["columns"] = columns
        return report
    report["state"] = "single-vector"
    report["offenders"] = _offenders(connection, family, catalog_uuid)
    report["add_index"] = True
    return report


def _offenders(
    connection: sqlite3.Connection,
    family: str,
    catalog_uuid: str,
) -> list[tuple[object, str]]:
    """Check every row with the validator the readers use, against its track."""

    offenders: list[tuple[object, str]] = []
    rows = connection.execute(
        f"""
        SELECT stored.track_id, stored.track_uuid, stored.dim, stored.normalization,
               stored.embedding_blob, tracks.track_uuid AS current_track_uuid
        FROM {family}_embeddings AS stored
        LEFT JOIN tracks ON tracks.track_id = stored.track_id
        ORDER BY stored.track_id
        """
    )
    for row in rows:
        if row["current_track_uuid"] is None:
            offenders.append((row["track_id"], "no track with this track_id"))
            continue
        valid, reason = validate_embedding_row_payload(
            family=family,
            row=row,
            expected_track=EmbeddingTrackIdentity(
                catalog_uuid=catalog_uuid,
                track_id=int(row["track_id"]),
                track_uuid=str(row["current_track_uuid"]),
            ),
        )
        if not valid:
            offenders.append((row["track_id"], str(reason)))
    return offenders


def _print_report(report: dict) -> None:
    line = f"{report['table']}: {report['state']}"
    if "rows" in report:
        specs = ", ".join(f"dim {dim} {norm} x{count}" for dim, norm, count in report["specs"])
        line += f"; {report['rows']} rows ({specs or 'empty'})"
    print(line)
    layer = EMBEDDING_LAYERS[report["family"]].default
    if report["state"] == "absent":
        print("  absent: left alone, not created")
    elif report["state"] == "ready":
        print("  already per-layer: table left alone")
    elif report["state"] == "unknown shape":
        print(f"  neither per-layer nor single-vector: {report['columns']}")
    else:
        offenders = report["offenders"]
        if offenders:
            print(f"  {len(offenders)} rows fail validation; first {_OFFENDER_SAMPLE}:")
            for track_id, reason in offenders[:_OFFENDER_SAMPLE]:
                print(f"    track_id {track_id}: {reason}")
        else:
            print(
                f"  would move {report['rows']} rows to layer {layer} of the "
                "per-layer table, keeping track_uuid and analyzed_at"
            )
    if report["add_index"]:
        print(f"  would add index {_default_index(report['family'])} (layer {layer})")
    elif report["state"] == "ready":
        print(f"  has index {_default_index(report['family'])}")


def _blocking(reports: list[dict]) -> list[dict]:
    return [
        report for report in reports
        if report["state"] == "unknown shape" or report.get("offenders")
    ]


def _pending(reports: list[dict]) -> list[dict]:
    return [
        report for report in reports
        if report["state"] == "single-vector" or report["add_index"]
    ]


def _backup(database: Path, backup_dir: Path | None, catalog_uuid: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = (backup_dir or database.parent).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{database.stem}.pre-layers-{stamp}.sqlite"
    if target.exists():
        raise FileExistsError(f"Backup target already exists: {target}")
    with closing(connect_database_read_only(database)) as source:
        with closing(sqlite3.connect(target)) as destination:
            source.backup(destination)
    with closing(connect_database_read_only(target)) as check:
        if validate_library_schema(check, database_path=str(target)) != catalog_uuid:
            raise RuntimeError(f"Backup holds another library catalog: {target}")
        integrity = [str(row[0]) for row in check.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        raise RuntimeError(f"Backup integrity check failed: {integrity[:5]}")
    return target


def _migrate_table(connection: sqlite3.Connection, family: str) -> None:
    # The layer guard compares the stored CREATE TABLE text, and SQLite would
    # store a quoted name for a table renamed into place. So the old table
    # moves aside and the final table is created under its own name.
    table = f"{family}_embeddings"
    aside = f"{table}_single_vector"
    connection.execute(f"ALTER TABLE {table} RENAME TO {aside}")
    connection.execute(LAYERED_EMBEDDINGS_DDL[family])
    connection.execute(
        f"""
        INSERT INTO {table}(
            track_id, layer, track_uuid, dim, normalization, embedding_blob, analyzed_at
        )
        SELECT track_id, ?, track_uuid, dim, normalization, embedding_blob, analyzed_at
        FROM {aside}
        ORDER BY track_id
        """,
        (EMBEDDING_LAYERS[family].default,),
    )
    connection.execute(f"DROP TABLE {aside}")
    connection.execute(f"CREATE INDEX idx_{table}_track_uuid ON {table}(track_uuid)")


def _check_migrated(connection: sqlite3.Connection, pending: list[dict]) -> list[str]:
    problems: list[str] = []
    integrity = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
    if integrity != ["ok"]:
        problems.append(f"integrity_check: {integrity[:5]}")
    for report in pending:
        family, table, rows = report["family"], report["table"], report["rows"]
        if not _has_index(connection, _default_index(family)):
            problems.append(f"{table}: index {_default_index(family)} is missing")
        if report["state"] != "single-vector":
            continue
        orphans = connection.execute(f"PRAGMA foreign_key_check({table})").fetchall()
        if orphans:
            problems.append(f"{table}: {len(orphans)} rows fail foreign_key_check")
        total, at_default, tracks = connection.execute(
            f"SELECT COUNT(*), COALESCE(SUM(layer = ?), 0), COUNT(DISTINCT track_id) FROM {table}",
            (EMBEDDING_LAYERS[family].default,),
        ).fetchone()
        if (int(total), int(at_default), int(tracks)) != (rows, rows, rows):
            problems.append(
                f"{table}: {rows} rows before, {total} after "
                f"({at_default} at the default layer, {tracks} tracks)"
            )
        state = embedding_layers_capability(connection, family)
        if state != "ready":
            problems.append(f"{table}: layer guard reports {state}")
    return problems


def _file_sizes(database: Path) -> str:
    parts = []
    for suffix in ("", "-wal"):
        path = Path(f"{database}{suffix}")
        if path.exists():
            parts.append(f"{path.name} {path.stat().st_size:,} B")
    return ", ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", required=True, type=Path, help="library database to migrate")
    parser.add_argument("--apply", action="store_true", help="perform the migration")
    parser.add_argument("--backup-dir", type=Path, help="backup folder (default: next to --db)")
    args = parser.parse_args(argv)
    database = args.db.expanduser().resolve()
    if not database.is_file():
        parser.error(f"--db is not an existing file: {database}")
    print(f"Database: {database} ({_file_sizes(database)})")

    started = time.perf_counter()
    with closing(connect_database_read_only(database)) as connection:
        catalog_uuid = validate_library_schema(connection, database_path=str(database))
        reports = [_inspect(connection, family, catalog_uuid) for family in EMBEDDING_LAYERS]
    print(f"Checked every row in {time.perf_counter() - started:.1f} s")
    for report in reports:
        _print_report(report)
    if _blocking(reports):
        print("Refused: nothing changed.")
        return 1
    if not _pending(reports):
        print("Nothing to migrate.")
        return 0
    if not args.apply:
        print("Dry run: nothing changed. Stop the server, then run again with --apply.")
        return 0

    started = time.perf_counter()
    backup = _backup(database, args.backup_dir, catalog_uuid)
    print(
        f"Backup: {backup} ({backup.stat().st_size:,} B), integrity ok, "
        f"{time.perf_counter() - started:.1f} s"
    )

    started = time.perf_counter()
    with closing(connect_database(database, expected_catalog_uuid=catalog_uuid)) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            # Check again under the write lock: rows may have changed since.
            reports = [_inspect(connection, family, catalog_uuid) for family in EMBEDDING_LAYERS]
            pending = _pending(reports)
            if _blocking(reports) or not pending:
                connection.rollback()
                for report in reports:
                    _print_report(report)
                print("Refused: the database changed since the dry check; nothing changed.")
                return 1
            generation = int(connection.execute("PRAGMA user_version").fetchone()[0])
            for report in pending:
                if report["state"] == "single-vector":
                    _migrate_table(connection, report["family"])
                connection.execute(LAYERED_EMBEDDINGS_DEFAULT_INDEX_DDL[report["family"]])
            # user_version dates cached vector loads; move it on, never reset it.
            connection.execute(f"PRAGMA user_version = {generation + 1}")
            problems = _check_migrated(connection, pending)
            if problems:
                connection.rollback()
                print("Checks failed; rolled back, nothing changed:")
                for problem in problems:
                    print(f"  {problem}")
                return 1
            connection.commit()
        except BaseException:
            if connection.in_transaction:
                connection.rollback()
            raise
    elapsed = time.perf_counter() - started
    for report in pending:
        moved = (
            f"{report['rows']} rows moved to layer {EMBEDDING_LAYERS[report['family']].default}, "
            if report["state"] == "single-vector" else ""
        )
        print(f"{report['table']}: {moved}index {_default_index(report['family'])} added")
    print(
        f"Migrated in {elapsed:.1f} s: integrity_check ok, foreign_key_check clean, "
        f"row counts equal, layer guard ready, indexes present; "
        f"user_version {generation} -> {generation + 1}"
    )
    print(f"Database now: {_file_sizes(database)}")
    print(
        f"Undo: stop the server, delete any {database.name}-wal and {database.name}-shm, "
        f"then copy {backup} over {database}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
