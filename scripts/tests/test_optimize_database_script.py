from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_storage import storage_database_paths
from dj_track_similarity.track_models import FileTags, ScannedFile


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "optimize_database.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("optimize_database", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _backup_files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.bak-*"))


def test_optimize_database_backs_up_library_and_existing_evaluation_sidecar(
    tmp_path: Path,
) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    mutation = db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / "track.wav"),
            file_size_bytes=10,
            file_modified_ns=1,
            audio_format="wav",
        ),
        tags=FileTags(title="Track", artist="Artist", genres=("Breakbeat",)),
    )
    evaluation = db.connect_evaluation(create=True)
    assert evaluation is not None
    evaluation.close()
    evaluation_path = storage_database_paths(db_path).evaluation

    summary = module.optimize_database(db_path)

    assert [item.role for item in summary.files] == ["library", "evaluation"]
    assert all(path.exists() for path in summary.backup_paths)
    assert summary.database_kind == "library"
    assert summary.integrity_before == "ok"
    assert summary.integrity_after == "ok"
    library_file = summary.files[0]
    assert library_file.journal_mode == "wal"
    assert library_file.checkpoint == "complete"
    assert not Path(f"{db_path}-wal").exists()
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM library").fetchone()[0] == 1
        assert connection.execute(
            "SELECT track_uuid FROM tracks WHERE track_id = ?",
            (mutation.identity.track_id,),
        ).fetchone() == (
            mutation.identity.track_uuid,
        )
        assert connection.execute(
            "SELECT track_id FROM track_search_fts WHERE track_search_fts MATCH 'Track'"
        ).fetchall() == [(mutation.identity.track_id,)]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    with sqlite3.connect(evaluation_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM evaluation_profiles"
        ).fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_optimize_database_does_not_reject_future_library_tables(
    tmp_path: Path,
) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE future_feature_values (value TEXT NOT NULL)")
        connection.execute("INSERT INTO future_feature_values(value) VALUES ('kept')")

    summary = module.optimize_database(db_path)

    assert summary.database_kind == "library"
    assert [item.role for item in summary.files] == ["library"]
    with sqlite3.connect(db_path) as connection:
        assert connection.execute(
            "SELECT value FROM future_feature_values"
        ).fetchone()[0] == "kept"


def test_optimize_database_keeps_generic_sqlite_file_and_its_journal_mode(
    tmp_path: Path,
) -> None:
    module = _load_script()
    db_path = tmp_path / "other.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_table(value) VALUES ('kept')")
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"

    assert module.main(["--db", str(db_path), "--dry-run"]) == 0
    assert _backup_files(tmp_path) == []

    summary = module.optimize_database(db_path)

    assert summary.database_kind == "sqlite"
    assert [item.role for item in summary.files] == ["sqlite"]
    assert summary.backup_path.exists()
    assert summary.files[0].journal_mode == "delete"
    assert summary.files[0].checkpoint is None
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert connection.execute("SELECT value FROM values_table").fetchone()[0] == "kept"
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_optimize_database_refuses_a_database_that_fails_verification(
    tmp_path: Path,
) -> None:
    module = _load_script()
    db_path = tmp_path / "broken.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE values_table (value INTEGER CHECK(value > 0))")
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute("INSERT INTO values_table(value) VALUES (-1)")
    size_before = db_path.stat().st_size

    assert module.main(["--db", str(db_path)]) == 1

    assert _backup_files(tmp_path) == []
    assert db_path.stat().st_size == size_before
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT value FROM values_table").fetchone()[0] == -1
