from __future__ import annotations

import logging
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.validation_jobs import DatabaseValidationJobManager
from dj_track_similarity.track_models import FileTags, ScannedFile


def test_job_retains_every_finding_while_ok_rows_rotate_out_of_the_event_log(tmp_path: Path, caplog) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    # More broken tracks than the event log can hold, so the capped tail loses
    # the earliest of them. Each file is removed once its track is stored, so
    # each becomes a `track_path_missing` warning.
    for index in range(300):
        missing_path = tmp_path / f"missing-{index}.wav"
        missing_path.write_bytes(b"\0")
        database.upsert_scanned_track(
            file=ScannedFile(
                file_path=str(missing_path),
                file_size_bytes=1,
                file_modified_ns=missing_path.stat().st_mtime_ns,
                audio_format="wav",
            ),
            tags=FileTags(title=f"Missing {index}"),
        )
        missing_path.unlink()
    # Validation walks tracks by id, so the healthy track goes in last and its
    # `ok` finding is the one still inside the tail at the end of the run.
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

    with caplog.at_level(logging.INFO, logger="dj_track_similarity.db.validation_jobs"):
        status = DatabaseValidationJobManager(str(database.path)).run_sync()

    assert status.state == "completed"
    assert any(event.level == "ok" for event in status.events)
    assert not any("track identity and path are valid" in record.message for record in caplog.records)
    assert any("Database validation completed" in record.message for record in caplog.records)
    assert status.warnings == 300
    assert len(status.events) == 200
    assert len(status.failures) == 300
    assert status.failures_omitted == 0
    assert status.failures[0].code == "track_path_missing"
    assert status.failures[0].track_id == 1
