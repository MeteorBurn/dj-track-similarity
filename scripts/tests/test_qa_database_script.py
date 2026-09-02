from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.track_models import FileTags, ScannedFile


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "qa_database.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("qa_database", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_qa_database_checks_library_and_optional_evaluation(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    evaluation = database.connect_evaluation(create=True)
    assert evaluation is not None
    evaluation.close()

    assert module.run_qa(db_path) == 0

    output = capsys.readouterr().out
    assert "QA PASSED" in output
    assert "Library:" in output
    assert "Evaluation:" in output


def test_qa_database_fails_on_a_violated_check_constraint(
    tmp_path: Path,
    capsys,
) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    track_path = tmp_path / "one.wav"
    track_path.write_bytes(b"audio")
    stat = track_path.stat()
    database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(track_path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
        ),
        tags=FileTags(title="One", artist="Fixture"),
    )
    # A read-only handle answers "ok" here, which is what made the gate hollow.
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute("UPDATE tags SET year = 50000")

    assert module.run_qa(db_path) == 1
    assert "FAIL" in capsys.readouterr().out


def test_qa_database_allows_future_library_tables(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE future_feature_values (value TEXT NOT NULL)")
        connection.execute("INSERT INTO future_feature_values(value) VALUES ('kept')")

    assert module.run_qa(db_path) == 0
