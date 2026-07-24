from __future__ import annotations

import wave
from pathlib import Path

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_tracks import canonical_file_path
from dj_track_similarity.scan_jobs import ScanJobManager, ScanJobPayload
from dj_track_similarity.track_models import FileTags, ScannedFile


def _audio(root: Path, name: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 441)
    return path


def test_scan_job_records_progress_and_events(tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "a.wav")
    _audio(music, "b.wav")
    (music / "ignore.txt").write_text("skip", encoding="utf-8")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)

    status = manager.run_sync(music)

    assert status.state == "completed"
    assert status.total == 2
    assert status.processed == 2
    assert status.added == 2
    assert status.updated == 0
    assert status.unchanged == 0
    assert status.avg_seconds_per_track is not None
    assert status.events[0].message == "Scan queued · workers 1"
    assert any(event.level == "ok" and event.path.endswith("a.wav") for event in status.events)
    assert status.events[-1].message == "Scan completed"


def test_scan_job_records_requested_worker_count(tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "a.wav")
    _audio(music, "b.wav")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)

    status = manager.run_sync(music, workers=2)

    assert status.workers == 2
    assert status.events[0].message == "Scan queued · workers 2"
    assert status.state == "completed"
    assert status.processed == 2


def test_scan_job_can_be_cancelled_then_rerun(
    tmp_path: Path,
) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "a.wav")
    _audio(music, "b.wav")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)
    job_id = manager.create_job(music)

    manager.cancel(job_id)
    cancelled = manager.run_job(job_id)
    resumed = manager.run_sync(music)

    assert cancelled.state == "cancelled"
    assert cancelled.processed == 0
    assert resumed.state == "completed"
    assert resumed.added == 2
    assert len(database.list_track_paths()) == 2


def test_tag_refresh_job_snapshots_exact_track_file_states(
    monkeypatch,
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = _audio(tmp_path, "stored.wav")
    manager = ScanJobManager(database)
    assert manager.run_sync(tmp_path).added == 1
    track_paths = database.list_track_paths()
    calls = 0

    def list_track_paths():
        nonlocal calls
        calls += 1
        return track_paths

    monkeypatch.setattr(database, "list_track_paths", list_track_paths)

    job_id = manager.create_tag_refresh_job()
    payload = manager._store.payload(job_id)

    assert calls == 1
    assert isinstance(payload, ScanJobPayload)
    assert payload.paths == [audio_path.resolve()]
    expected = database.get_track_file_state(audio_path)
    assert expected is not None
    assert payload.track_states == {
        canonical_file_path(audio_path): expected,
    }


def test_tag_refresh_job_rejects_stale_missing_snapshot_as_file_failure(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = _audio(tmp_path, "removed.wav")
    manager = ScanJobManager(database)
    assert manager.run_sync(tmp_path).added == 1
    expected = database.get_track_file_state(audio_path)
    assert expected is not None
    job_id = manager.create_tag_refresh_job()

    audio_path.unlink()
    mutation = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(audio_path),
            file_size_bytes=expected.file_size_bytes + 1,
            file_modified_ns=expected.file_modified_ns + 1,
            audio_format="wav",
        ),
        tags=FileTags(title="Generation 2"),
    )
    assert mutation.action == "updated"

    status = manager.run_tag_refresh_job(job_id)

    assert status.state == "completed"
    assert status.processed == 1
    assert status.failed == 1
    assert status.skipped == 0
    current = database.get_track_file_state(audio_path)
    assert current is not None
    assert current.content_generation == 2
    assert current.missing_since is None
