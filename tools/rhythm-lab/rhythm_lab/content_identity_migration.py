"""Explicit, recoverable migration of a Rhythm Lab database to content identity.

Converts the pre-content-identity layout, whose per-track rows are keyed by
``(catalog_uuid, track_uuid, selected_path)``, into the ``content_key`` layout
that :mod:`rhythm_lab.lab_db` creates. Only classifier profiles, their label
vocabularies and the manual labels carry over; predictions, the label queue and
training checkpoints start empty and are rebuilt by the next refresh or
training run. Review collections carry over only when they hold rows.

The dry run is the default and touches nothing. ``apply`` copies the database
and its WAL/SHM companions into a sibling backup directory, rewrites the
database in one transaction, checks foreign keys and vacuums. Any error rolls
the transaction back and leaves the backup in place. Both layouts are
recognised by table shape alone.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sqlite3
import time
from typing import Any

from dj_track_similarity.rhythm_lab_collections import sonara_content_key

from .lab_db import (
    TRAINING_MIN_LABELS_COLUMN_SQL,
    create_lab_schema,
    require_fingerprint_table,
    upsert_track_sightings,
)
from .source_db import SourceDatabase


class MigrationError(RuntimeError):
    """The database, the libraries or the rows cannot be migrated as requested."""


# The pre-content-identity layout this module converts; frozen on purpose so a
# future layout change cannot make an old database look migratable.
V1_TABLE_COLUMNS: dict[str, frozenset[str]] = {
    "classifier_labels": frozenset(
        {
            "classifier_key",
            "catalog_uuid",
            "track_uuid",
            "selected_path",
            "file_size_bytes",
            "file_modified_ns",
            "label",
            "note",
            "updated_at",
        }
    ),
    "classifier_label_queue": frozenset(
        {
            "id",
            "classifier_key",
            "catalog_uuid",
            "track_uuid",
            "selected_path",
            "mode",
            "score",
            "priority",
            "reason_json",
            "state",
            "created_at",
            "updated_at",
        }
    ),
    "classifier_predictions": frozenset(
        {
            "classifier_key",
            "catalog_uuid",
            "track_uuid",
            "selected_path",
            "artist",
            "title",
            "feature_set",
            "model_artifact",
            "label",
            "confidence",
            "probabilities_json",
            "updated_at",
        }
    ),
    "review_collection_tracks": frozenset(
        {
            "collection_id",
            "catalog_uuid",
            "track_uuid",
            "selected_path",
            "position",
            "score",
            "note",
            "added_at",
        }
    ),
}
_COUNTED_TABLES = (
    "classifier_profiles",
    "classifier_profile_labels",
    "classifier_labels",
    "classifier_predictions",
    "classifier_label_queue",
    "classifier_training_checkpoints",
    "review_collections",
    "review_collection_tracks",
    "track_sightings",
)
_DROPPED_TABLES = (
    "classifier_labels",
    "classifier_predictions",
    "classifier_label_queue",
    "review_collection_tracks",
    "review_collections",
)


def migrate_content_identity(
    lab_db: str | Path,
    library_dbs: list[str | Path] | tuple[str | Path, ...],
    *,
    apply: bool = False,
    skip_unresolved: bool = False,
    rekey: bool = False,
) -> dict[str, Any]:
    """Plan, and with ``apply`` perform, the migration; return the JSON report."""

    if rekey:
        raise MigrationError("--rekey is not implemented yet")
    started = time.perf_counter()
    lab_path = Path(lab_db).expanduser().resolve(strict=False)
    if not lab_path.is_file():
        raise FileNotFoundError(f"Rhythm Lab database does not exist: {lab_path}")
    libraries = _open_libraries(library_dbs)
    # Autocommit: staging into temp tables must not open an implicit
    # transaction, so the rewrite below can own one explicit BEGIN IMMEDIATE.
    connection = sqlite3.connect(lab_path.as_uri(), uri=True, timeout=30, isolation_level=None)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.create_function(
            "rhythm_lab_content_key",
            2,
            sonara_content_key,
            deterministic=True,
        )
        _require_v1_layout(connection)
        aliases: dict[str, str] = {}
        for index, library in enumerate(libraries):
            alias = f"lib{index}"
            connection.execute(
                f"ATTACH DATABASE ? AS {alias}",
                (f"{library.path.as_uri()}?mode=ro",),
            )
            require_fingerprint_table(connection, alias)
            aliases[library.catalog_uuid] = alias
        try:
            report: dict[str, Any] = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "mode": "apply" if apply else "dry-run",
                "lab_db": str(lab_path),
                "libraries": [
                    {"path": str(library.path), "catalog_uuid": library.catalog_uuid}
                    for library in libraries
                ],
                "skip_unresolved": skip_unresolved,
                "before": _table_counts(connection),
            }
            _stage_labels(connection, aliases)
            collections_present = _stage_collections(connection, aliases)
            report["labels"] = _label_report(connection)
            report["collections"] = _collection_report(connection, collections_present)
            report["catalogs"] = _catalog_report(connection, aliases)
            unresolved_total = len(report["labels"]["unresolved"]) + len(
                report["collections"]["unresolved"]
            )
            if unresolved_total and not skip_unresolved:
                raise MigrationError(
                    f"{unresolved_total} rows cannot be resolved to a fingerprinted track "
                    "(see the report); pass --skip-unresolved to drop them"
                )
            report["after"] = _projected_counts(report["before"], report, aliases, connection)
            if apply:
                report["backup"] = _backup_lab_database(connection, lab_path)
                report["integrity"] = _apply(connection, aliases, collections_present)
                report["after"] = _table_counts(connection)
        finally:
            for alias in aliases.values():
                connection.execute(f"DETACH DATABASE {alias}")
    finally:
        connection.close()
    report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    return report


def write_migration_report(
    report: dict[str, Any],
    output_path: str | Path,
    *,
    force: bool = False,
) -> Path:
    target = Path(output_path).expanduser().resolve(strict=False)
    if target.exists() and not force:
        raise MigrationError(f"Report already exists; pass --force to overwrite: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def _open_libraries(library_dbs: list[str | Path] | tuple[str | Path, ...]) -> list[SourceDatabase]:
    if not library_dbs:
        raise MigrationError("At least one --library-db is required")
    libraries: list[SourceDatabase] = []
    seen: dict[str, Path] = {}
    for candidate in library_dbs:
        library = SourceDatabase(candidate)
        previous = seen.get(library.catalog_uuid)
        if previous is not None:
            raise MigrationError(
                f"Libraries {previous} and {library.path} share catalog {library.catalog_uuid}"
            )
        seen[library.catalog_uuid] = library.path
        libraries.append(library)
    return libraries


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str] | None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if exists is None:
        return None
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _require_v1_layout(connection: sqlite3.Connection) -> None:
    if _table_columns(connection, "track_sightings") is not None:
        raise MigrationError("Rhythm Lab database already uses content identity; nothing to migrate")
    if _table_columns(connection, "classifier_profiles") is None:
        raise MigrationError("Rhythm Lab database has no classifier_profiles table; nothing to migrate")
    for table, expected in V1_TABLE_COLUMNS.items():
        columns = _table_columns(connection, table)
        if columns is None:
            continue
        if "content_key" in columns:
            raise MigrationError(
                f"Rhythm Lab table {table!r} already uses content identity; nothing to migrate"
            )
        if columns != expected:
            raise MigrationError(
                f"Rhythm Lab table {table!r} is not the pre-content-identity layout; "
                "this migration cannot convert it"
            )


def _table_counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in _COUNTED_TABLES:
        if _table_columns(connection, table) is None:
            counts[table] = 0
            continue
        counts[table] = int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return counts


def _resolution_sql(alias: str | None, *, source_table: str, columns: str) -> str:
    """SELECT resolving one catalog's rows of ``source_table`` against a library alias."""

    if alias is None:
        return f"""
            SELECT {columns}, NULL AS content_key, 'unresolved' AS status, NULL AS current_path
            FROM main.{source_table} AS l
            WHERE l.catalog_uuid = ?
        """
    return f"""
        SELECT {columns},
               CASE WHEN fp.track_id IS NULL THEN NULL
                    ELSE rhythm_lab_content_key(fp.fingerprint_version, fp.fingerprint_base64)
               END AS content_key,
               CASE WHEN t.track_id IS NULL THEN 'unresolved'
                    WHEN fp.track_id IS NULL THEN 'no_fingerprint'
                    WHEN t.file_path != l.selected_path THEN 'path_drift'
                    ELSE 'resolved'
               END AS status,
               t.file_path AS current_path
        FROM main.{source_table} AS l
        LEFT JOIN {alias}.tracks AS t ON t.track_uuid = l.track_uuid
        LEFT JOIN {alias}.sonara_fingerprints AS fp
          ON fp.track_id = t.track_id AND fp.track_uuid = t.track_uuid
        WHERE l.catalog_uuid = ?
    """


def _catalogs_in(connection: sqlite3.Connection, table: str) -> list[str]:
    if _table_columns(connection, table) is None:
        return []
    return [
        str(row[0])
        for row in connection.execute(
            f"SELECT DISTINCT catalog_uuid FROM main.{table} ORDER BY catalog_uuid"
        )
    ]


def _stage_labels(connection: sqlite3.Connection, aliases: dict[str, str]) -> None:
    connection.execute("DROP TABLE IF EXISTS temp.label_rows")
    connection.execute("DROP TABLE IF EXISTS temp.label_groups")
    connection.execute(
        """
        CREATE TEMP TABLE label_rows(
            classifier_key TEXT NOT NULL,
            catalog_uuid TEXT NOT NULL,
            track_uuid TEXT NOT NULL,
            selected_path TEXT NOT NULL,
            label TEXT NOT NULL,
            note TEXT,
            updated_at TEXT NOT NULL,
            content_key TEXT,
            status TEXT NOT NULL,
            current_path TEXT
        )
        """
    )
    columns = (
        "l.classifier_key, l.catalog_uuid, l.track_uuid, l.selected_path, "
        "l.label, l.note, l.updated_at"
    )
    for catalog_uuid in _catalogs_in(connection, "classifier_labels"):
        connection.execute(
            "INSERT INTO temp.label_rows "
            + _resolution_sql(
                aliases.get(catalog_uuid),
                source_table="classifier_labels",
                columns=columns,
            ),
            (catalog_uuid,),
        )
    # One row per (profile, content): the newest label wins a disagreement; an
    # agreeing group keeps the latest timestamp and the newest non-empty note.
    connection.execute(
        """
        CREATE TEMP TABLE label_groups AS
        SELECT classifier_key, catalog_uuid, track_uuid, selected_path, label, note,
               updated_at, content_key, status, current_path,
               ROW_NUMBER() OVER newest AS rank,
               COUNT(*) OVER grp AS members,
               MIN(label) OVER grp != MAX(label) OVER grp AS disagree,
               MAX(updated_at) OVER grp AS max_updated_at,
               FIRST_VALUE(note) OVER (
                   PARTITION BY classifier_key, content_key
                   ORDER BY (note IS NULL OR note = ''), updated_at DESC,
                            catalog_uuid, track_uuid
               ) AS newest_note
        FROM temp.label_rows
        WHERE content_key IS NOT NULL
        WINDOW grp AS (PARTITION BY classifier_key, content_key),
               newest AS (
                   PARTITION BY classifier_key, content_key
                   ORDER BY updated_at DESC, catalog_uuid, track_uuid
               )
        """
    )


def _stage_collections(connection: sqlite3.Connection, aliases: dict[str, str]) -> bool:
    """Stage review collections when they hold rows; return whether any exist."""

    connection.execute("DROP TABLE IF EXISTS temp.collection_headers")
    connection.execute("DROP TABLE IF EXISTS temp.collection_rows")
    connection.execute("DROP TABLE IF EXISTS temp.collection_groups")
    if _table_columns(connection, "review_collections") is None:
        return False
    header_count = int(connection.execute("SELECT COUNT(*) FROM main.review_collections").fetchone()[0])
    if header_count == 0:
        return False
    connection.execute(
        """
        CREATE TEMP TABLE collection_headers AS
        SELECT id, catalog_uuid, name, source, note, created_at, updated_at
        FROM main.review_collections
        """
    )
    connection.execute(
        """
        CREATE TEMP TABLE collection_rows(
            collection_id INTEGER NOT NULL,
            catalog_uuid TEXT NOT NULL,
            track_uuid TEXT NOT NULL,
            selected_path TEXT NOT NULL,
            position INTEGER NOT NULL,
            score REAL,
            note TEXT,
            added_at TEXT NOT NULL,
            content_key TEXT,
            status TEXT NOT NULL,
            current_path TEXT
        )
        """
    )
    columns = (
        "l.collection_id, l.catalog_uuid, l.track_uuid, l.selected_path, "
        "l.position, l.score, l.note, l.added_at"
    )
    for catalog_uuid in _catalogs_in(connection, "review_collection_tracks"):
        connection.execute(
            "INSERT INTO temp.collection_rows "
            + _resolution_sql(
                aliases.get(catalog_uuid),
                source_table="review_collection_tracks",
                columns=columns,
            ),
            (catalog_uuid,),
        )
    # Duplicate content inside one collection keeps its earliest position; the
    # survivors are renumbered densely from 1 in their original order.
    connection.execute(
        """
        CREATE TEMP TABLE collection_groups AS
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY collection_id
                   ORDER BY position, catalog_uuid, track_uuid
               ) AS new_position
        FROM (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY collection_id, content_key
                       ORDER BY position, catalog_uuid, track_uuid
                   ) AS rank
            FROM temp.collection_rows
            WHERE content_key IS NOT NULL
        )
        WHERE rank = 1
        """
    )
    return True


def _label_report(connection: sqlite3.Connection) -> dict[str, Any]:
    before = int(connection.execute("SELECT COUNT(*) FROM temp.label_rows").fetchone()[0])
    after = int(
        connection.execute("SELECT COUNT(*) FROM temp.label_groups WHERE rank = 1").fetchone()[0]
    )
    merged = connection.execute(
        """
        SELECT COUNT(*) AS groups, COALESCE(SUM(members - 1), 0) AS rows_merged
        FROM temp.label_groups
        WHERE rank = 1 AND members > 1
        """
    ).fetchone()
    conflicts: dict[tuple[str, str], dict[str, Any]] = {}
    for row in connection.execute(
        """
        SELECT classifier_key, content_key, rank, catalog_uuid, track_uuid,
               selected_path, label, note, updated_at
        FROM temp.label_groups
        WHERE disagree
        ORDER BY classifier_key, content_key, rank
        """
    ):
        group = conflicts.setdefault(
            (str(row["classifier_key"]), str(row["content_key"])),
            {
                "classifier_key": str(row["classifier_key"]),
                "content_key": str(row["content_key"]),
                "winner": None,
                "losers": [],
            },
        )
        entry = {
            "catalog_uuid": str(row["catalog_uuid"]),
            "track_uuid": str(row["track_uuid"]),
            "selected_path": str(row["selected_path"]),
            "label": str(row["label"]),
            "note": row["note"],
            "updated_at": str(row["updated_at"]),
        }
        if int(row["rank"]) == 1:
            group["winner"] = entry
        else:
            group["losers"].append(entry)
    unresolved = [
        {
            "classifier_key": str(row["classifier_key"]),
            "catalog_uuid": str(row["catalog_uuid"]),
            "track_uuid": str(row["track_uuid"]),
            "selected_path": str(row["selected_path"]),
            "label": str(row["label"]),
            "status": str(row["status"]),
        }
        for row in connection.execute(
            """
            SELECT classifier_key, catalog_uuid, track_uuid, selected_path, label, status
            FROM temp.label_rows
            WHERE content_key IS NULL
            ORDER BY classifier_key, catalog_uuid, track_uuid
            """
        )
    ]
    return {
        "before": before,
        "after": after,
        "merged_groups": int(merged["groups"]),
        "merged_rows": int(merged["rows_merged"]),
        "conflicts": list(conflicts.values()),
        "unresolved": unresolved,
    }


def _collection_report(connection: sqlite3.Connection, present: bool) -> dict[str, Any]:
    if not present:
        return {"migrated": False, "before": 0, "after": 0, "unresolved": []}
    before = int(connection.execute("SELECT COUNT(*) FROM temp.collection_rows").fetchone()[0])
    after = int(connection.execute("SELECT COUNT(*) FROM temp.collection_groups").fetchone()[0])
    unresolved = [
        {
            "collection_id": int(row["collection_id"]),
            "catalog_uuid": str(row["catalog_uuid"]),
            "track_uuid": str(row["track_uuid"]),
            "selected_path": str(row["selected_path"]),
            "position": int(row["position"]),
            "status": str(row["status"]),
        }
        for row in connection.execute(
            """
            SELECT collection_id, catalog_uuid, track_uuid, selected_path, position, status
            FROM temp.collection_rows
            WHERE content_key IS NULL
            ORDER BY collection_id, position
            """
        )
    ]
    return {"migrated": True, "before": before, "after": after, "unresolved": unresolved}


def _catalog_report(connection: sqlite3.Connection, aliases: dict[str, str]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for row in connection.execute(
        """
        SELECT catalog_uuid, status, COUNT(*) AS count
        FROM temp.label_rows
        GROUP BY catalog_uuid, status
        ORDER BY catalog_uuid, status
        """
    ):
        catalog = report.setdefault(
            str(row["catalog_uuid"]),
            {"library": row["catalog_uuid"] in aliases, "labels": {}},
        )
        catalog["labels"][str(row["status"])] = int(row["count"])
    return report


def _projected_counts(
    before: dict[str, int],
    report: dict[str, Any],
    aliases: dict[str, str],
    connection: sqlite3.Connection,
) -> dict[str, int]:
    sightings = 0
    for alias in aliases.values():
        sightings += int(
            connection.execute(
                f"""
                SELECT COUNT(*)
                FROM {alias}.tracks AS t
                JOIN {alias}.sonara_fingerprints AS fp
                  ON fp.track_id = t.track_id AND fp.track_uuid = t.track_uuid
                WHERE t.missing_since IS NULL
                """
            ).fetchone()[0]
        )
    collections = report["collections"]
    return {
        **before,
        "classifier_labels": int(report["labels"]["after"]),
        "classifier_predictions": 0,
        "classifier_label_queue": 0,
        "classifier_training_checkpoints": 0,
        "review_collections": before["review_collections"] if collections["migrated"] else 0,
        "review_collection_tracks": int(collections["after"]),
        "track_sightings": sightings,
    }


def _backup_lab_database(connection: sqlite3.Connection, lab_path: Path) -> dict[str, Any]:
    """Copy the database and its WAL/SHM companions next to it before rewriting."""

    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    companions = [lab_path, Path(f"{lab_path}-wal"), Path(f"{lab_path}-shm")]
    existing = [path for path in companions if path.exists()]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    backup_dir = lab_path.parent / f"{lab_path.name}.content-identity-backup-{timestamp}"
    backup_dir.mkdir()
    copied: list[dict[str, str]] = []
    for source in existing:
        destination = backup_dir / source.name
        shutil.copy2(source, destination)
        copied.append({"backup": str(destination), "source": str(source)})
    return {"directory": str(backup_dir), "files": copied}


def _apply(
    connection: sqlite3.Connection,
    aliases: dict[str, str],
    collections_present: bool,
) -> dict[str, Any]:
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("BEGIN IMMEDIATE")
    try:
        for table in _DROPPED_TABLES:
            connection.execute(f"DROP TABLE IF EXISTS main.{table}")
        connection.execute("DELETE FROM main.classifier_training_checkpoints")
        # Profiles carry over in place; bring the legacy table up to the current DDL.
        if "training_min_labels" not in (_table_columns(connection, "classifier_profiles") or set()):
            connection.execute(
                f"ALTER TABLE classifier_profiles ADD COLUMN {TRAINING_MIN_LABELS_COLUMN_SQL}"
            )
        create_lab_schema(connection)
        connection.execute(
            """
            INSERT INTO main.classifier_labels(
                classifier_key, content_key, label, note, updated_at,
                last_catalog_uuid, last_track_uuid, last_selected_path
            )
            SELECT classifier_key, content_key, label,
                   CASE WHEN disagree THEN note ELSE newest_note END,
                   CASE WHEN disagree THEN updated_at ELSE max_updated_at END,
                   catalog_uuid, track_uuid, COALESCE(current_path, selected_path)
            FROM temp.label_groups
            WHERE rank = 1
            """
        )
        if collections_present:
            connection.execute(
                """
                INSERT INTO main.review_collections(
                    id, catalog_uuid, name, source, note, created_at, updated_at
                )
                SELECT id, catalog_uuid, name, source, note, created_at, updated_at
                FROM temp.collection_headers
                """
            )
            connection.execute(
                """
                INSERT INTO main.review_collection_tracks(
                    collection_id, content_key, catalog_uuid, track_uuid,
                    selected_path, position, score, note, added_at
                )
                SELECT collection_id, content_key, catalog_uuid, track_uuid,
                       COALESCE(current_path, selected_path), new_position,
                       score, note, added_at
                FROM temp.collection_groups
                """
            )
        for catalog_uuid, alias in aliases.items():
            upsert_track_sightings(connection, alias=alias, catalog_uuid=catalog_uuid)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise MigrationError(
                f"foreign_key_check reported {len(violations)} violations; rolled back"
            )
        connection.execute("COMMIT")
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    connection.execute("VACUUM")
    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    return {"foreign_key_check": [], "integrity_check": integrity}
