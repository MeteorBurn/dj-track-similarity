import argparse
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3


CORE_SCHEMA_VERSION = 7
SIDECAR_SCHEMA_VERSION = 1
LIBRARY_DATABASE_MARKERS = {
    "library_catalog",
    "contracts",
    "tracks",
    "file_tags",
    "sonara",
    "maest_scores",
    "classifier_scores",
    "likes",
}
ARTIFACTS_DATABASE_MARKERS = {
    "storage_metadata",
    "mert_embeddings",
    "maest_embeddings",
    "muq_embeddings",
    "clap_embeddings",
    "sonara_similarity_embeddings",
    "sonara_timeline",
    "sonara_fingerprints",
}
EVALUATION_DATABASE_MARKERS = {
    "storage_metadata",
    "search_sessions",
    "search_session_seeds",
    "search_result_events",
    "calibration_runs",
    "evaluation_settings",
}
RHYTHM_LAB_DATABASE_MARKERS = {
    "classifier_profiles",
    "classifier_profile_labels",
    "classifier_labels",
    "classifier_predictions",
    "classifier_training_checkpoints",
}
RHYTHM_LAB_IDENTITY_COLUMNS = {
    "catalog_uuid",
    "track_uuid",
    "content_generation",
}


@dataclass(frozen=True)
class OptimizedDatabaseFile:
    role: str
    path: Path
    backup_path: Path
    size_before: int
    size_after: int
    integrity_before: str
    integrity_after: str


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
        return "ok" if all(item.integrity_before.lower() == "ok" for item in self.files) else "failed"

    @property
    def integrity_after(self) -> str:
        return "ok" if all(item.integrity_after.lower() == "ok" for item in self.files) else "failed"


def optimize_database(db_path: str | Path) -> OptimizationSummary:
    path = Path(db_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise FileNotFoundError(path)

    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        database_kind = _detect_supported_database(connection)

    database_files = _database_files(path, database_kind)
    before = []
    for role, selected_path in database_files:
        integrity = _integrity_check(selected_path)
        if integrity.lower() != "ok":
            raise RuntimeError(f"Integrity check failed before optimization for {role}: {integrity}")
        before.append((role, selected_path, selected_path.stat().st_size, integrity))

    backups = {
        role: _backup_database(selected_path)
        for role, selected_path, _size, _integrity in before
    }
    for _role, selected_path, _size, _integrity in before:
        _optimize_one_database(selected_path)

    files = []
    for role, selected_path, size_before, integrity_before in before:
        integrity_after = _integrity_check(selected_path)
        if integrity_after.lower() != "ok":
            raise RuntimeError(f"Integrity check failed after optimization for {role}: {integrity_after}")
        files.append(
            OptimizedDatabaseFile(
                role=role,
                path=selected_path,
                backup_path=backups[role],
                size_before=size_before,
                size_after=selected_path.stat().st_size,
                integrity_before=integrity_before,
                integrity_after=integrity_after,
            )
        )

    return OptimizationSummary(
        db_path=path,
        database_kind=database_kind,
        files=tuple(files),
    )


def _database_files(path: Path, database_kind: str) -> tuple[tuple[str, Path], ...]:
    if database_kind != "library":
        return ((database_kind, path),)

    artifacts_path, evaluation_path = _sidecar_database_paths(path)
    if not artifacts_path.is_file():
        raise FileNotFoundError(f"Artifacts database does not exist: {artifacts_path}")

    _require_schema(
        path,
        LIBRARY_DATABASE_MARKERS,
        "Core",
        expected_version=CORE_SCHEMA_VERSION,
    )
    _require_schema(
        artifacts_path,
        ARTIFACTS_DATABASE_MARKERS,
        "Artifacts",
        expected_version=SIDECAR_SCHEMA_VERSION,
    )
    selected = [("core", path), ("artifacts", artifacts_path)]
    if evaluation_path.is_file():
        _require_schema(
            evaluation_path,
            EVALUATION_DATABASE_MARKERS,
            "Evaluation",
            expected_version=SIDECAR_SCHEMA_VERSION,
        )
        selected.append(("evaluation", evaluation_path))
    _validate_catalog_uuids(path, *(selected_path for _role, selected_path in selected[1:]))
    return tuple(selected)


def _sidecar_database_paths(path: Path) -> tuple[Path, Path]:
    stem = path.stem if path.suffix else path.name
    return (
        path.with_name(f"{stem}.artifacts.sqlite"),
        path.with_name(f"{stem}.evaluation.sqlite"),
    )


def _require_schema(
    path: Path,
    required: set[str],
    label: str,
    *,
    expected_version: int,
) -> None:
    with closing(sqlite3.connect(path)) as connection:
        tables = _user_tables(connection)
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if not required.issubset(tables):
        actual = ", ".join(sorted(tables)) or "none"
        expected = ", ".join(sorted(required))
        raise RuntimeError(f"{label} database has tables [{actual}], expected [{expected}]")
    if version != expected_version:
        raise RuntimeError(
            f"{label} database schema version {version} is not supported; "
            f"expected {expected_version}"
        )
    if foreign_key_errors:
        raise RuntimeError(
            f"{label} database has foreign-key violations: {foreign_key_errors[:5]}"
        )


def _validate_catalog_uuids(core: Path, *sidecars: Path) -> None:
    catalog_uuids = {"Core": _catalog_uuid(core, table="library_catalog")}
    for sidecar in sidecars:
        catalog_uuids[sidecar.name] = _catalog_uuid(sidecar, table="storage_metadata")
    if any(value is None for value in catalog_uuids.values()) or len(set(catalog_uuids.values())) != 1:
        details = ", ".join(
            f"{label}={value or 'missing'}"
            for label, value in catalog_uuids.items()
        )
        raise RuntimeError(f"SQLite bundle catalog UUIDs do not match: {details}")


def _catalog_uuid(path: Path, *, table: str) -> str | None:
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute(
            f"SELECT catalog_uuid FROM {table} WHERE singleton_id = 1",
        ).fetchone()
    if row is None:
        return None
    value = str(row[0]).strip()
    return value or None


def _optimize_one_database(path: Path) -> None:
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute("VACUUM")
        connection.execute("ANALYZE")
        connection.execute("PRAGMA optimize")
        connection.commit()
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.commit()


def _backup_database(path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.bak-{timestamp}")
    suffix = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.bak-{timestamp}-{suffix}")
        suffix += 1
    with (
        closing(sqlite3.connect(path)) as source,
        closing(sqlite3.connect(backup_path)) as target,
    ):
        source.backup(target)
        target.commit()
    return backup_path


def _integrity_check(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def _detect_supported_database(connection: sqlite3.Connection) -> str:
    tables = _user_tables(connection)
    version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if LIBRARY_DATABASE_MARKERS.issubset(tables) and version == CORE_SCHEMA_VERSION:
        return "library"
    if RHYTHM_LAB_DATABASE_MARKERS.issubset(tables):
        label_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(classifier_labels)")
        }
        if RHYTHM_LAB_IDENTITY_COLUMNS.issubset(label_columns):
            return "rhythm_lab"
    markers = (
        f"library v{CORE_SCHEMA_VERSION}: "
        f"{', '.join(sorted(LIBRARY_DATABASE_MARKERS))}; "
        "rhythm_lab v7 identity tables: "
        f"{', '.join(sorted(RHYTHM_LAB_DATABASE_MARKERS))}"
    )
    actual = ", ".join(sorted(tables)) or "none"
    raise RuntimeError(f"Unsupported SQLite database: found tables [{actual}], expected markers [{markers}]")


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()
    return {str(row[0]) for row in rows}


def main() -> None:
    parser = argparse.ArgumentParser(description="Optimize a dj-track-similarity SQLite database.")
    parser.add_argument("--db", required=True, type=Path, help="Path to the SQLite database file")
    args = parser.parse_args()

    summary = optimize_database(args.db)
    print(f"database={summary.db_path}")
    print(f"database_kind={summary.database_kind}")
    print(f"integrity_before={summary.integrity_before}")
    print(f"integrity_after={summary.integrity_after}")
    print(f"size_before={summary.size_before}")
    print(f"size_after={summary.size_after}")
    for item in summary.files:
        print(f"{item.role}.database={item.path}")
        print(f"{item.role}.backup={item.backup_path}")


if __name__ == "__main__":
    main()
