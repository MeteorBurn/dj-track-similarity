from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from shutil import copyfile
from threading import Barrier

import pytest

from dj_track_similarity import db_connection as connection_module
from dj_track_similarity.database import LibraryDatabase


CORE_SCHEMA_VERSION = 7
ARTIFACTS_SCHEMA_VERSION = 1

REQUIRED_CORE_TABLES = {
    "library_catalog",
    "library_settings",
    "contracts",
    "tracks",
    "file_tags",
    "sonara",
    "maest_scores",
    "classifier_scores",
    "likes",
    "pair_feedback",
    "transition_feedback",
    "track_search_fts",
}
REQUIRED_ARTIFACT_TABLES = {
    "storage_metadata",
    "maest_embeddings",
    "mert_embeddings",
    "muq_embeddings",
    "clap_embeddings",
    "sonara_similarity_embeddings",
    "sonara_timeline",
    "sonara_fingerprints",
}
FORBIDDEN_LEGACY_TABLES = {
    "embeddings",
    "sonara_features",
    "track_classifier_scores",
    "track_likes",
    "search_sessions",
    "search_result_events",
    "calibration_runs",
}
FORBIDDEN_TRACK_COLUMNS = {
    "metadata_json",
    "has_sonara",
    "has_sonara_analysis",
    "has_maest_embedding",
    "has_mert_embedding",
    "has_muq_embedding",
    "has_clap_embedding",
}

_BOOTSTRAP_CRASH_SCRIPT = r"""
import os
import sys
from pathlib import Path

from dj_track_similarity import db_connection
from dj_track_similarity.database import LibraryDatabase

core_path = Path(sys.argv[1]).resolve()
artifacts_path = core_path.with_suffix(".artifacts.sqlite")
crash_stage = sys.argv[2]
original_replace = os.replace

def crash_replace(source, destination):
    destination_path = Path(destination).resolve()
    if crash_stage == "stages_ready" and destination_path == artifacts_path:
        os._exit(73)
    result = original_replace(source, destination)
    if crash_stage == "artifacts_published" and destination_path == artifacts_path:
        os._exit(74)
    if crash_stage == "core_published" and destination_path == core_path:
        os._exit(75)
    return result

db_connection.os.replace = crash_replace
LibraryDatabase(core_path)
"""

_CONCURRENT_OPEN_SCRIPT = r"""
import sys
import time
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase

core_path = Path(sys.argv[1]).resolve()
barrier_root = Path(sys.argv[2]).resolve()
worker = sys.argv[3]
(barrier_root / f"ready-{worker}").touch(exist_ok=False)
go_path = barrier_root / "go"
deadline = time.monotonic() + 20
while not go_path.exists():
    if time.monotonic() >= deadline:
        raise TimeoutError("timed out waiting for process barrier")
    time.sleep(0.01)
print(LibraryDatabase(core_path).catalog_uuid, flush=True)
"""

_CONCURRENT_EVALUATION_CREATE_SCRIPT = r"""
import sys
import time
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase

core_path = Path(sys.argv[1]).resolve()
barrier_root = Path(sys.argv[2]).resolve()
worker = sys.argv[3]
database = LibraryDatabase(core_path)
(barrier_root / f"evaluation-ready-{worker}").touch(exist_ok=False)
go_path = barrier_root / "evaluation-go"
deadline = time.monotonic() + 20
while not go_path.exists():
    if time.monotonic() >= deadline:
        raise TimeoutError("timed out waiting for Evaluation creation barrier")
    time.sleep(0.01)
connection = database.connect_evaluation(create=True)
if connection is None:
    raise RuntimeError("Evaluation creation returned no connection")
try:
    row = connection.execute(
        "SELECT catalog_uuid FROM storage_metadata WHERE singleton_id = 1"
    ).fetchone()
finally:
    connection.close()
if row is None:
    raise RuntimeError("Evaluation storage metadata is missing")
print(str(row[0]), flush=True)
"""


def _artifacts_path(core_path: Path) -> Path:
    return core_path.with_suffix(".artifacts.sqlite")


def _evaluation_path(core_path: Path) -> Path:
    return core_path.with_suffix(".evaluation.sqlite")


def _bootstrap_receipt_path(core_path: Path) -> Path:
    return core_path.with_name(f".{core_path.name}.bootstrap.json")


def _bootstrap_staging_paths(core_path: Path) -> list[Path]:
    return [
        path
        for path in core_path.parent.iterdir()
        if path.name.startswith(f".{core_path.name}.")
        and (
            ".core.tmp" in path.name
            or ".artifacts.tmp" in path.name
            or ".bootstrap.json." in path.name
        )
    ]


def _run_hard_crash(core_path: Path, stage: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-c",
            _BOOTSTRAP_CRASH_SCRIPT,
            str(core_path),
            stage,
        ],
        cwd=Path(__file__).resolve().parents[1],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            """
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}


def _core_catalog_uuid(core_path: Path) -> str:
    with closing(sqlite3.connect(core_path)) as connection:
        rows = connection.execute(
            "SELECT singleton_id, catalog_uuid FROM library_catalog"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1
    return str(rows[0][1])


def _artifacts_catalog_uuid(artifacts_path: Path) -> str:
    with closing(sqlite3.connect(artifacts_path)) as connection:
        rows = connection.execute(
            "SELECT singleton_id, catalog_uuid FROM storage_metadata"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1
    return str(rows[0][1])


def test_library_database_bootstraps_bound_v7_core_and_required_artifacts(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)

    database = LibraryDatabase(core_path)

    assert database.path == core_path.resolve()
    assert core_path.is_file()
    assert artifacts_path.is_file()
    assert not _evaluation_path(core_path).exists()
    assert not core_path.with_suffix(".timeline.sqlite").exists()
    assert not core_path.with_suffix(".representations.sqlite").exists()

    with closing(database.connect()) as core:
        core_version = int(core.execute("PRAGMA user_version").fetchone()[0])
        core_tables = _tables(core)
        track_columns = _columns(core, "tracks")
        attached_aliases = {
            str(row[1]) for row in core.execute("PRAGMA database_list").fetchall()
        }

    with closing(sqlite3.connect(artifacts_path)) as artifacts:
        artifacts_version = int(artifacts.execute("PRAGMA user_version").fetchone()[0])
        artifact_tables = _tables(artifacts)

    assert core_version == CORE_SCHEMA_VERSION
    assert artifacts_version == ARTIFACTS_SCHEMA_VERSION
    assert REQUIRED_CORE_TABLES <= core_tables
    assert REQUIRED_ARTIFACT_TABLES <= artifact_tables
    assert FORBIDDEN_LEGACY_TABLES.isdisjoint(core_tables)
    assert FORBIDDEN_TRACK_COLUMNS.isdisjoint(track_columns)
    assert {"timeline", "representations"}.isdisjoint(attached_aliases)
    assert _core_catalog_uuid(core_path) == _artifacts_catalog_uuid(artifacts_path)


def test_library_database_reopens_the_same_bound_bundle(tmp_path: Path) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)

    first = LibraryDatabase(core_path)
    first_catalog_uuid = _core_catalog_uuid(core_path)
    first_artifacts_catalog_uuid = _artifacts_catalog_uuid(artifacts_path)

    second = LibraryDatabase(core_path)
    second_catalog_uuid = _core_catalog_uuid(core_path)
    second_artifacts_catalog_uuid = _artifacts_catalog_uuid(artifacts_path)

    assert first.path == second.path == core_path.resolve()
    assert first_catalog_uuid == first_artifacts_catalog_uuid
    assert second_catalog_uuid == second_artifacts_catalog_uuid
    assert second_catalog_uuid == first_catalog_uuid
    assert sorted(path.name for path in tmp_path.glob("*.sqlite")) == [
        "library.artifacts.sqlite",
        "library.sqlite",
    ]


def test_reopen_fully_validates_once_then_connections_use_cached_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core_path = tmp_path / "library.sqlite"
    LibraryDatabase(core_path)
    full_validation_calls = {"core": 0, "artifacts": 0}
    original_core_validator = connection_module.validate_core_schema
    original_artifacts_validator = connection_module.validate_artifacts_sidecar_schema

    def count_core_validation(
        connection: sqlite3.Connection,
        *,
        expected_catalog_uuid: str | None = None,
    ) -> str:
        full_validation_calls["core"] += 1
        return original_core_validator(
            connection,
            expected_catalog_uuid=expected_catalog_uuid,
        )

    def count_artifacts_validation(
        connection: sqlite3.Connection,
        *,
        expected_catalog_uuid: str | None = None,
    ) -> str:
        full_validation_calls["artifacts"] += 1
        return original_artifacts_validator(
            connection,
            expected_catalog_uuid=expected_catalog_uuid,
        )

    monkeypatch.setattr(
        connection_module,
        "validate_core_schema",
        count_core_validation,
    )
    monkeypatch.setattr(
        connection_module,
        "validate_artifacts_sidecar_schema",
        count_artifacts_validation,
    )

    database = LibraryDatabase(core_path)
    assert full_validation_calls == {"core": 1, "artifacts": 1}

    for _ in range(12):
        with closing(database.connect()) as core:
            assert core.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 0
        with closing(database.connect_artifacts()) as artifacts:
            assert (
                artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0]
                == 0
            )

    assert full_validation_calls == {"core": 1, "artifacts": 1}


@pytest.mark.parametrize("target_name", ["core", "artifacts"])
def test_cached_connection_falls_back_to_full_validation_after_external_ddl(
    tmp_path: Path,
    target_name: str,
) -> None:
    core_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(core_path)
    target = core_path if target_name == "core" else _artifacts_path(core_path)
    with closing(sqlite3.connect(target)) as connection:
        connection.execute("CREATE VIEW unexpected_view AS SELECT 1 AS value")
        connection.commit()

    connect = database.connect if target_name == "core" else database.connect_artifacts
    with pytest.raises(RuntimeError, match=r"(?i)unexpected views"):
        connect()


@pytest.mark.parametrize("target_name", ["core", "artifacts"])
def test_cached_connection_fully_revalidates_same_catalog_file_replacement(
    tmp_path: Path,
    target_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(core_path)
    target = core_path if target_name == "core" else _artifacts_path(core_path)
    replacement = tmp_path / f"{target_name}.replacement.sqlite"
    with closing(sqlite3.connect(target)) as connection:
        checkpoint = connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        assert checkpoint is not None
        assert int(checkpoint[0]) == 0
    copyfile(target, replacement)

    calls = 0
    validator_name = (
        "validate_core_schema"
        if target_name == "core"
        else "validate_artifacts_sidecar_schema"
    )
    original_validator = getattr(connection_module, validator_name)

    def count_validation(
        connection: sqlite3.Connection,
        *,
        expected_catalog_uuid: str | None = None,
    ) -> str:
        nonlocal calls
        calls += 1
        return original_validator(
            connection,
            expected_catalog_uuid=expected_catalog_uuid,
        )

    monkeypatch.setattr(connection_module, validator_name, count_validation)
    replacement.replace(target)

    connect = database.connect if target_name == "core" else database.connect_artifacts
    with closing(connect()) as connection:
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) > 0

    assert calls == 1


def test_library_database_rejects_artifacts_from_another_catalog(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)
    LibraryDatabase(core_path)
    original_core_catalog_uuid = _core_catalog_uuid(core_path)

    other_core_path = tmp_path / "other.sqlite"
    other_artifacts_path = _artifacts_path(other_core_path)
    LibraryDatabase(other_core_path)
    other_catalog_uuid = _artifacts_catalog_uuid(other_artifacts_path)
    assert other_catalog_uuid != original_core_catalog_uuid
    copyfile(other_artifacts_path, artifacts_path)

    with pytest.raises(
        (RuntimeError, ValueError),
        match=r"(?i)(catalog|binding|artifacts)",
    ):
        LibraryDatabase(core_path)

    assert _core_catalog_uuid(core_path) == original_core_catalog_uuid
    assert _artifacts_catalog_uuid(artifacts_path) == other_catalog_uuid


def test_library_database_rejects_missing_required_artifacts(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)
    LibraryDatabase(core_path)
    artifacts_path.unlink()

    with pytest.raises(
        (RuntimeError, FileNotFoundError),
        match=r"(?i)(artifacts|sidecar|required|missing)",
    ):
        LibraryDatabase(core_path)

    assert not artifacts_path.exists()


def test_long_lived_core_connect_rejects_unlinked_required_artifacts(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(core_path)
    database.artifacts_path.unlink()

    with pytest.raises(
        RuntimeError,
        match=r"(?i)(artifacts.*missing|required.*artifacts)",
    ):
        database.connect()

    assert core_path.is_file()
    assert not database.artifacts_path.exists()


def test_long_lived_core_connect_rejects_foreign_artifacts_replacement(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(core_path)
    original_catalog_uuid = database.catalog_uuid

    foreign_database = LibraryDatabase(tmp_path / "foreign.sqlite")
    assert foreign_database.catalog_uuid != original_catalog_uuid
    replacement = tmp_path / "foreign-artifacts-replacement.sqlite"
    copyfile(foreign_database.artifacts_path, replacement)
    replacement.replace(database.artifacts_path)

    with pytest.raises(
        (RuntimeError, ValueError),
        match=r"(?i)(catalog|binding|artifacts)",
    ):
        database.connect()

    assert _core_catalog_uuid(core_path) == original_catalog_uuid
    assert _artifacts_catalog_uuid(database.artifacts_path) == (
        foreign_database.catalog_uuid
    )


def test_library_database_rejects_non_artifacts_schema(tmp_path: Path) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)
    LibraryDatabase(core_path)
    artifacts_path.unlink()
    with closing(sqlite3.connect(artifacts_path)) as connection:
        connection.executescript(
            """
            PRAGMA user_version = 0;
            CREATE TABLE sentinel(value TEXT NOT NULL);
            INSERT INTO sentinel(value) VALUES ('preserve-me');
            """
        )
        connection.commit()

    with pytest.raises(
        (RuntimeError, ValueError),
        match=r"(?i)(artifacts|version|schema)",
    ):
        LibraryDatabase(core_path)

    with closing(sqlite3.connect(artifacts_path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == (
            "preserve-me"
        )


def test_library_database_rejects_non_v7_without_creating_sidecars(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "legacy.sqlite"
    with closing(sqlite3.connect(core_path)) as connection:
        connection.executescript(
            """
            PRAGMA user_version = 6;
            CREATE TABLE sentinel(value TEXT NOT NULL);
            INSERT INTO sentinel(value) VALUES ('preserve-me');
            """
        )
        connection.commit()
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"

    original_bytes = core_path.read_bytes()
    original_directory_entries = {path.name for path in tmp_path.iterdir()}

    with pytest.raises(
        (RuntimeError, ValueError),
        match=r"(?i)(v7|version|schema)",
    ):
        LibraryDatabase(core_path)

    assert core_path.read_bytes() == original_bytes
    assert {path.name for path in tmp_path.iterdir()} == original_directory_entries
    assert not core_path.with_name(f".{core_path.name}.bootstrap.lock").exists()
    assert not _artifacts_path(core_path).exists()
    assert not core_path.with_suffix(".timeline.sqlite").exists()
    assert not core_path.with_suffix(".representations.sqlite").exists()
    with closing(sqlite3.connect(core_path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == (
            "preserve-me"
        )


def test_library_database_does_not_create_optional_evaluation_sidecar(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"

    database = LibraryDatabase(core_path)
    with closing(database.connect()) as connection:
        connection.execute("SELECT COUNT(*) FROM tracks").fetchone()

    assert not _evaluation_path(core_path).exists()


def test_library_database_creates_evaluation_sidecar_only_when_requested(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    evaluation_path = _evaluation_path(core_path)
    database = LibraryDatabase(core_path)

    assert database.connect_evaluation(create=False) is None
    assert not evaluation_path.exists()

    created = database.connect_evaluation(create=True)
    assert created is not None
    with closing(created) as connection:
        metadata = connection.execute(
            """
            SELECT singleton_id, catalog_uuid, schema_version
            FROM storage_metadata
            """
        ).fetchone()
    assert metadata is not None
    assert tuple(metadata) == (1, database.catalog_uuid, 1)
    assert evaluation_path.is_file()

    reopened = database.connect_evaluation(create=False)
    assert reopened is not None
    reopened.close()


def test_evaluation_reopen_enforces_wal(tmp_path: Path) -> None:
    core_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(core_path)
    created = database.connect_evaluation(create=True)
    assert created is not None
    created.close()

    with closing(sqlite3.connect(database.evaluation_path)) as connection:
        assert connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0] == (
            "delete"
        )

    reopened = database.connect_evaluation(create=False)
    assert reopened is not None
    with closing(reopened) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_evaluation_reopen_rejects_unexpected_views(tmp_path: Path) -> None:
    core_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(core_path)
    created = database.connect_evaluation(create=True)
    assert created is not None
    created.close()

    with closing(sqlite3.connect(database.evaluation_path)) as connection:
        connection.execute("CREATE VIEW unexpected_view AS SELECT 1 AS value")
        connection.commit()

    with pytest.raises(RuntimeError, match=r"(?i)unexpected views"):
        database.connect_evaluation(create=False)

    with closing(sqlite3.connect(database.evaluation_path)) as connection:
        assert (
            connection.execute("SELECT value FROM unexpected_view").fetchone()[0] == 1
        )


def test_library_database_rejects_ambiguous_memory_path_without_filesystem_writes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(
        (RuntimeError, ValueError),
        match=r"(?i)(memory|persistent|artifacts)",
    ):
        LibraryDatabase(":memory:")

    assert list(tmp_path.iterdir()) == []


def test_concurrent_library_database_opens_publish_one_bound_bundle(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)
    workers = 8
    barrier = Barrier(workers)

    def open_bundle() -> tuple[int, str, str]:
        barrier.wait()
        database = LibraryDatabase(core_path)
        with closing(database.connect()) as core:
            version = int(core.execute("PRAGMA user_version").fetchone()[0])
            core_catalog_uuid = str(
                core.execute(
                    "SELECT catalog_uuid FROM library_catalog WHERE singleton_id = 1"
                ).fetchone()[0]
            )
        artifacts_catalog_uuid = _artifacts_catalog_uuid(artifacts_path)
        return version, core_catalog_uuid, artifacts_catalog_uuid

    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(lambda _: open_bundle(), range(workers)))

    assert len(results) == workers
    assert {version for version, _, _ in results} == {CORE_SCHEMA_VERSION}
    assert len({core_uuid for _, core_uuid, _ in results}) == 1
    assert len({artifacts_uuid for _, _, artifacts_uuid in results}) == 1
    assert all(core_uuid == artifacts_uuid for _, core_uuid, artifacts_uuid in results)
    assert sorted(path.name for path in tmp_path.glob("*.sqlite")) == [
        "library.artifacts.sqlite",
        "library.sqlite",
    ]


@pytest.mark.parametrize(
    ("crash_stage", "exit_code"),
    [
        ("stages_ready", 73),
        ("artifacts_published", 74),
        ("core_published", 75),
    ],
)
def test_bootstrap_recovers_after_hard_crash_at_each_publication_stage(
    tmp_path: Path,
    crash_stage: str,
    exit_code: int,
) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)

    crashed = _run_hard_crash(core_path, crash_stage)

    assert crashed.returncode == exit_code, (crashed.stdout, crashed.stderr)
    assert _bootstrap_receipt_path(core_path).is_file()
    if crash_stage == "stages_ready":
        assert not core_path.exists()
        assert not artifacts_path.exists()
        assert len(_bootstrap_staging_paths(core_path)) == 2
    elif crash_stage == "artifacts_published":
        assert not core_path.exists()
        assert artifacts_path.is_file()
        assert len(_bootstrap_staging_paths(core_path)) == 1
    else:
        assert core_path.is_file()
        assert artifacts_path.is_file()
        assert _bootstrap_staging_paths(core_path) == []

    database = LibraryDatabase(core_path)

    assert database.catalog_uuid == _core_catalog_uuid(core_path)
    assert database.catalog_uuid == _artifacts_catalog_uuid(artifacts_path)
    assert not _bootstrap_receipt_path(core_path).exists()
    assert _bootstrap_staging_paths(core_path) == []


@pytest.mark.parametrize("existing_target", ["core", "artifacts"])
def test_bootstrap_recovery_never_deletes_nonmatching_existing_target(
    tmp_path: Path,
    existing_target: str,
) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)
    crashed = _run_hard_crash(core_path, "stages_ready")
    assert crashed.returncode == 73, (crashed.stdout, crashed.stderr)

    target = core_path if existing_target == "core" else artifacts_path
    with closing(sqlite3.connect(target)) as connection:
        connection.executescript(
            """
            PRAGMA user_version = 0;
            CREATE TABLE sentinel(value TEXT NOT NULL);
            INSERT INTO sentinel(value) VALUES ('preserve-me');
            """
        )
        connection.commit()

    with pytest.raises(
        (RuntimeError, ValueError),
        match=r"(?i)(version|schema|artifacts|core)",
    ):
        LibraryDatabase(core_path)

    assert target.is_file()
    with closing(sqlite3.connect(target)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == (
            "preserve-me"
        )
    assert _bootstrap_receipt_path(core_path).is_file()


def test_bootstrap_rejects_tampered_receipt_without_following_paths(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    victim_path = tmp_path / "victim.sqlite"
    crashed = _run_hard_crash(core_path, "stages_ready")
    assert crashed.returncode == 73, (crashed.stdout, crashed.stderr)
    with closing(sqlite3.connect(victim_path)) as connection:
        connection.execute("CREATE TABLE sentinel(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sentinel(value) VALUES ('preserve-me')")
        connection.commit()

    receipt_path = _bootstrap_receipt_path(core_path)
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["artifacts_name"] = "../victim.sqlite"
    receipt_path.write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match=r"(?i)receipt.*target"):
        LibraryDatabase(core_path)

    with closing(sqlite3.connect(victim_path)) as connection:
        assert connection.execute("SELECT value FROM sentinel").fetchone()[0] == (
            "preserve-me"
        )
    assert receipt_path.is_file()
    assert _bootstrap_staging_paths(core_path)


def test_stale_bootstrap_lock_file_is_harmless_and_reusable(tmp_path: Path) -> None:
    core_path = tmp_path / "library.sqlite"
    lock_path = core_path.with_name(f".{core_path.name}.bootstrap.lock")
    lock_path.write_text("pid=process-that-crashed\n", encoding="ascii")

    first = LibraryDatabase(core_path)
    second = LibraryDatabase(core_path)

    assert first.catalog_uuid == second.catalog_uuid
    assert lock_path.is_file()


def test_reopen_enforces_wal_for_both_storage_files(tmp_path: Path) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)
    LibraryDatabase(core_path)
    for target in (core_path, artifacts_path):
        with closing(sqlite3.connect(target)) as connection:
            assert connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0] == (
                "delete"
            )

    LibraryDatabase(core_path)

    for target in (core_path, artifacts_path):
        with closing(sqlite3.connect(target)) as connection:
            assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


@pytest.mark.parametrize("target_name", ["core", "artifacts"])
def test_reopen_rejects_unexpected_views(
    tmp_path: Path,
    target_name: str,
) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)
    LibraryDatabase(core_path)
    target = core_path if target_name == "core" else artifacts_path
    with closing(sqlite3.connect(target)) as connection:
        connection.execute("CREATE VIEW unexpected_view AS SELECT 1 AS value")
        connection.commit()

    with pytest.raises(RuntimeError, match=r"(?i)unexpected views"):
        LibraryDatabase(core_path)

    with closing(sqlite3.connect(target)) as connection:
        assert (
            connection.execute("SELECT value FROM unexpected_view").fetchone()[0] == 1
        )


def test_eight_process_concurrent_open_publishes_one_bound_bundle(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    artifacts_path = _artifacts_path(core_path)
    workers = 8
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _CONCURRENT_OPEN_SCRIPT,
                str(core_path),
                str(tmp_path),
                str(index),
            ],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(workers)
    ]
    deadline = time.monotonic() + 20
    try:
        while len(list(tmp_path.glob("ready-*"))) != workers:
            if time.monotonic() >= deadline:
                raise TimeoutError("processes did not reach the bootstrap barrier")
            time.sleep(0.01)
        (tmp_path / "go").touch(exist_ok=False)
        results = [process.communicate(timeout=30) for process in processes]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    failures = [
        (process.returncode, stdout, stderr)
        for process, (stdout, stderr) in zip(processes, results)
        if process.returncode != 0
    ]
    assert failures == []
    catalog_uuids = {stdout.strip() for stdout, _stderr in results}
    assert len(catalog_uuids) == 1
    assert catalog_uuids == {_core_catalog_uuid(core_path)}
    assert catalog_uuids == {_artifacts_catalog_uuid(artifacts_path)}
    assert not _bootstrap_receipt_path(core_path).exists()
    assert _bootstrap_staging_paths(core_path) == []


def test_eight_process_concurrent_evaluation_creation_is_idempotent(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(core_path)
    workers = 8
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                _CONCURRENT_EVALUATION_CREATE_SCRIPT,
                str(core_path),
                str(tmp_path),
                str(index),
            ],
            cwd=Path(__file__).resolve().parents[1],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(workers)
    ]
    deadline = time.monotonic() + 20
    try:
        while len(list(tmp_path.glob("evaluation-ready-*"))) != workers:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "processes did not reach the Evaluation creation barrier"
                )
            time.sleep(0.01)
        (tmp_path / "evaluation-go").touch(exist_ok=False)
        results = [process.communicate(timeout=30) for process in processes]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)

    failures = [
        (process.returncode, stdout, stderr)
        for process, (stdout, stderr) in zip(processes, results)
        if process.returncode != 0
    ]
    assert failures == []
    catalog_uuids = {stdout.strip() for stdout, _stderr in results}
    assert catalog_uuids == {database.catalog_uuid}
    assert database.evaluation_path.is_file()

    reopened = database.connect_evaluation(create=False)
    assert reopened is not None
    with closing(reopened) as connection:
        rows = connection.execute(
            """
            SELECT singleton_id, catalog_uuid, schema_version
            FROM storage_metadata
            """
        ).fetchall()
        assert [tuple(row) for row in rows] == [(1, database.catalog_uuid, 1)]
