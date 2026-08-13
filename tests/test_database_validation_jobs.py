from __future__ import annotations

import logging
from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.database_validation_jobs import DatabaseValidationJobManager
from dj_track_similarity.track_models import FileTags, ScannedFile


def test_job_keeps_ok_events_for_ui_without_writing_them_to_file_log(tmp_path: Path, caplog) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    track_path = tmp_path / "present.wav"
    track_path.write_bytes(b"audio")
    stat = track_path.stat()
    database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(track_path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
        ),
        tags=FileTags(title="Validation fixture"),
    )

    with caplog.at_level(logging.INFO, logger="dj_track_similarity.database_validation_jobs"):
        status = DatabaseValidationJobManager(str(database.path)).run_sync()

    assert status.state == "completed"
    assert any(event.level == "ok" for event in status.events)
    assert not any("track identity and path are valid" in record.message for record in caplog.records)
    assert any("Database validation completed" in record.message for record in caplog.records)


def test_manager_allows_only_one_queued_or_running_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = DatabaseValidationJobManager(str(database.path))
    monkeypatch.setattr("threading.Thread.start", lambda _thread: None)

    manager.start()

    with pytest.raises(RuntimeError, match="already running"):
        manager.start()
