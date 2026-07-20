from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path


TIMELINE_DATABASE_ALIAS = "timeline"
REPRESENTATIONS_DATABASE_ALIAS = "representations"
TIMELINE_SCHEMA_VERSION = 1
REPRESENTATIONS_SCHEMA_VERSION = 1
STORAGE_CATALOG_SETTING_KEY = "storage.catalog_id"


@dataclass(frozen=True)
class SidecarDatabasePaths:
    timeline: Path
    representations: Path


def sidecar_database_paths(main_path: str | Path) -> SidecarDatabasePaths:
    resolved = Path(main_path).expanduser().resolve(strict=False)
    suffix = resolved.suffix or ".sqlite"
    stem = resolved.stem if resolved.suffix else resolved.name
    return SidecarDatabasePaths(
        timeline=resolved.with_name(f"{stem}.timeline{suffix}"),
        representations=resolved.with_name(f"{stem}.representations{suffix}"),
    )


def attach_sidecar_databases(connection: sqlite3.Connection, main_path: str | Path) -> SidecarDatabasePaths:
    paths = sidecar_database_paths(main_path)
    connection.execute(f"ATTACH DATABASE ? AS {TIMELINE_DATABASE_ALIAS}", (str(paths.timeline),))
    connection.execute(
        f"ATTACH DATABASE ? AS {REPRESENTATIONS_DATABASE_ALIAS}",
        (str(paths.representations),),
    )
    connection.execute(f"PRAGMA {TIMELINE_DATABASE_ALIAS}.journal_mode = WAL")
    connection.execute(f"PRAGMA {REPRESENTATIONS_DATABASE_ALIAS}.journal_mode = WAL")
    connection.execute(f"PRAGMA {TIMELINE_DATABASE_ALIAS}.synchronous = NORMAL")
    connection.execute(f"PRAGMA {REPRESENTATIONS_DATABASE_ALIAS}.synchronous = NORMAL")
    return paths


def ensure_sidecar_schemas(connection: sqlite3.Connection) -> None:
    _ensure_timeline_schema(connection)
    _ensure_representations_schema(connection)
    _ensure_shared_catalog_id(connection)


def validate_attached_storage_catalog(
    connection: sqlite3.Connection,
    aliases: tuple[str, ...] = (TIMELINE_DATABASE_ALIAS, REPRESENTATIONS_DATABASE_ALIAS),
) -> str:
    row = connection.execute(
        "SELECT value FROM library_settings WHERE key = ?",
        (STORAGE_CATALOG_SETTING_KEY,),
    ).fetchone()
    if row is None:
        raise RuntimeError("Core database is missing its storage catalog ID")
    catalog_id = str(row[0])
    for alias in aliases:
        if alias not in {TIMELINE_DATABASE_ALIAS, REPRESENTATIONS_DATABASE_ALIAS}:
            raise ValueError(f"Unsupported storage database alias: {alias}")
        sidecar_row = connection.execute(
            f"SELECT value FROM {alias}.storage_metadata WHERE key = ?",
            (STORAGE_CATALOG_SETTING_KEY,),
        ).fetchone()
        if sidecar_row is None or str(sidecar_row[0]) != catalog_id:
            raise RuntimeError(
                f"{alias.capitalize()} database belongs to another library catalog. "
                "Choose the matching set of Core, Timeline, and Representations databases."
            )
    return catalog_id


def _ensure_timeline_schema(connection: sqlite3.Connection) -> None:
    tables = _user_tables(connection, TIMELINE_DATABASE_ALIAS)
    version = _schema_version(connection, TIMELINE_DATABASE_ALIAS)
    if tables and version != TIMELINE_SCHEMA_VERSION:
        raise RuntimeError(_sidecar_migration_required_message("Timeline"))
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {TIMELINE_DATABASE_ALIAS}.storage_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS {TIMELINE_DATABASE_ALIAS}.sonara_timeline (
            track_id INTEGER PRIMARY KEY,
            fields_json TEXT NOT NULL CHECK(json_valid(fields_json)),
            payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
            analysis_signature_id TEXT NOT NULL,
            analysis_signature_json TEXT NOT NULL CHECK(json_valid(analysis_signature_json)),
            provenance_json TEXT NOT NULL DEFAULT '{{}}' CHECK(json_valid(provenance_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS {TIMELINE_DATABASE_ALIAS}.idx_sonara_timeline_signature
        ON sonara_timeline(analysis_signature_id, track_id);

        PRAGMA {TIMELINE_DATABASE_ALIAS}.user_version = {TIMELINE_SCHEMA_VERSION};
        """
    )
    required = {"storage_metadata", "sonara_timeline"}
    if not required.issubset(_user_tables(connection, TIMELINE_DATABASE_ALIAS)):
        raise RuntimeError(_sidecar_migration_required_message("Timeline"))


def _ensure_representations_schema(connection: sqlite3.Connection) -> None:
    tables = _user_tables(connection, REPRESENTATIONS_DATABASE_ALIAS)
    version = _schema_version(connection, REPRESENTATIONS_DATABASE_ALIAS)
    if tables and version != REPRESENTATIONS_SCHEMA_VERSION:
        raise RuntimeError(_sidecar_migration_required_message("Representations"))
    connection.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS {REPRESENTATIONS_DATABASE_ALIAS}.storage_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS {REPRESENTATIONS_DATABASE_ALIAS}.embeddings (
            track_id INTEGER NOT NULL,
            embedding_key TEXT NOT NULL DEFAULT 'sonara' CHECK(embedding_key = 'sonara'),
            model_name TEXT NOT NULL,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL,
            normalization TEXT NOT NULL DEFAULT 'l2',
            analysis_signature_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{{}}' CHECK(json_valid(metadata_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(track_id, embedding_key)
        );

        CREATE TABLE IF NOT EXISTS {REPRESENTATIONS_DATABASE_ALIAS}.fingerprints (
            track_id INTEGER NOT NULL,
            fingerprint_key TEXT NOT NULL DEFAULT 'fingerprint' CHECK(fingerprint_key = 'fingerprint'),
            model_name TEXT NOT NULL,
            version TEXT,
            payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
            analysis_signature_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{{}}' CHECK(json_valid(metadata_json)),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(track_id, fingerprint_key)
        );

        CREATE INDEX IF NOT EXISTS {REPRESENTATIONS_DATABASE_ALIAS}.idx_embeddings_key_track
        ON embeddings(embedding_key, track_id);

        CREATE INDEX IF NOT EXISTS {REPRESENTATIONS_DATABASE_ALIAS}.idx_fingerprints_key_track
        ON fingerprints(fingerprint_key, track_id);

        PRAGMA {REPRESENTATIONS_DATABASE_ALIAS}.user_version = {REPRESENTATIONS_SCHEMA_VERSION};
        """
    )
    required = {"storage_metadata", "embeddings", "fingerprints"}
    if not required.issubset(_user_tables(connection, REPRESENTATIONS_DATABASE_ALIAS)):
        raise RuntimeError(_sidecar_migration_required_message("Representations"))
    if connection.execute(
        f"SELECT 1 FROM {REPRESENTATIONS_DATABASE_ALIAS}.embeddings WHERE embedding_key != 'sonara' LIMIT 1"
    ).fetchone() is not None:
        raise RuntimeError("Representations database may contain only the optional SONARA embedding")
    if connection.execute(
        f"SELECT 1 FROM {REPRESENTATIONS_DATABASE_ALIAS}.fingerprints WHERE fingerprint_key != 'fingerprint' LIMIT 1"
    ).fetchone() is not None:
        raise RuntimeError("Representations database may contain only the optional SONARA fingerprint")


def _ensure_shared_catalog_id(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT value FROM library_settings WHERE key = ?",
        (STORAGE_CATALOG_SETTING_KEY,),
    ).fetchone()
    catalog_id = str(row["value"]) if row is not None else str(uuid.uuid4())
    if row is None:
        connection.execute(
            "INSERT INTO library_settings (key, value) VALUES (?, ?)",
            (STORAGE_CATALOG_SETTING_KEY, catalog_id),
        )

    for alias in (TIMELINE_DATABASE_ALIAS, REPRESENTATIONS_DATABASE_ALIAS):
        sidecar_row = connection.execute(
            f"SELECT value FROM {alias}.storage_metadata WHERE key = ?",
            (STORAGE_CATALOG_SETTING_KEY,),
        ).fetchone()
        if sidecar_row is not None and str(sidecar_row["value"]) != catalog_id:
            raise RuntimeError(
                f"{alias.capitalize()} database belongs to another library catalog. "
                "Choose the matching set of Core, Timeline, and Representations databases."
            )
        connection.execute(
            f"""
            INSERT INTO {alias}.storage_metadata (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            """,
            (STORAGE_CATALOG_SETTING_KEY, catalog_id),
        )


def _schema_version(connection: sqlite3.Connection, alias: str) -> int:
    return int(connection.execute(f"PRAGMA {alias}.user_version").fetchone()[0])


def _user_tables(connection: sqlite3.Connection, alias: str) -> set[str]:
    rows = connection.execute(
        f"""
        SELECT name
        FROM {alias}.sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _sidecar_migration_required_message(label: str) -> str:
    return (
        f"{label} SQLite database schema is not current. Move the sidecar database out of the way "
        "and run a fresh analysis with the current application version."
    )
