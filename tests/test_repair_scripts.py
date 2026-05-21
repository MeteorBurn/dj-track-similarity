from pathlib import Path
import sqlite3
import subprocess
import sys


def test_repair_malformed_metadata_json_script_reports_then_repairs(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    _create_tracks_database_with_malformed_metadata(db_path)
    script_path = Path("scripts/repair_malformed_metadata_json.py")

    dry_run = subprocess.run(
        [sys.executable, str(script_path), "--db", str(db_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert dry_run.returncode == 0
    assert "malformed tracks.metadata_json rows: 2" in dry_run.stdout
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT metadata_json FROM tracks WHERE id = 1").fetchone()[0] == "{"

    applied = subprocess.run(
        [sys.executable, str(script_path), "--db", str(db_path), "--apply", "--no-backup"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert applied.returncode == 0
    assert "repaired rows: 2" in applied.stdout
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT metadata_json FROM tracks WHERE id = 1").fetchone()[0] == "{}"
        assert connection.execute("SELECT metadata_json FROM tracks WHERE id = 2").fetchone()[0] == '{"ok": true}'
        assert connection.execute("SELECT json_valid(metadata_json) FROM tracks WHERE id = 3").fetchone()[0] == 1
        repaired = connection.execute("SELECT metadata_json FROM tracks WHERE id = 3").fetchone()[0]
    assert '"score": null' in repaired
    assert '"title": "NaN score"' in repaired


def _create_tracks_database_with_malformed_metadata(db_path: Path) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                artist TEXT,
                title TEXT,
                album TEXT,
                bpm REAL,
                musical_key TEXT,
                energy REAL,
                duration REAL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO tracks (id, path, size, mtime, title, metadata_json)
            VALUES
                (1, 'C:/music/bad.wav', 10, 1, 'Bad', '{'),
                (2, 'C:/music/good.wav', 10, 1, 'Good', '{"ok": true}'),
                (
                    3,
                    'C:/music/nan.wav',
                    10,
                    1,
                    'NaN score',
                    '{"title": "NaN score", "maest_genres": [{"label": "Breakbeat", "score": NaN}]}'
                );
            """
        )
