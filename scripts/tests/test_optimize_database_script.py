from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path


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


def test_optimize_database_dry_run_reports_without_writing(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "other.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_table(value) VALUES ('kept')")
    before = db_path.read_bytes()

    assert module.main(["--db", str(db_path), "--dry-run"]) == 0

    assert _backup_files(tmp_path) == []
    assert db_path.read_bytes() == before


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
