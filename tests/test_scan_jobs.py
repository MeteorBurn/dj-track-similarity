from pathlib import Path

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.scan_jobs import ScanJobManager


def _audio(root: Path, name: str) -> Path:
    path = root / name
    path.write_bytes(b"RIFF0000WAVE")
    return path


def test_scan_job_records_progress_and_events(tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "a.wav")
    _audio(music, "b.flac")
    (music / "ignore.txt").write_text("skip", encoding="utf-8")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(db)

    status = manager.run_sync(music)

    assert status.state == "completed"
    assert status.total == 2
    assert status.processed == 2
    assert status.added == 2
    assert status.updated == 0
    assert status.unchanged == 0
    assert status.avg_seconds_per_track is not None
    assert status.events[0].message == "Scan queued"
    assert any(event.level == "ok" and event.path.endswith("a.wav") for event in status.events)
    assert status.events[-1].message == "Scan completed"


def test_scan_job_records_requested_worker_count(tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "a.wav")
    _audio(music, "b.wav")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(db)

    status = manager.run_sync(music, workers=2)

    assert status.workers == 2
    assert status.state == "completed"
    assert status.processed == 2


def test_scan_job_can_be_cancelled_and_rerun_continues_with_unchanged_tracks(tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "a.wav")
    _audio(music, "b.wav")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(db)
    job_id = manager.create_job(music)

    manager.cancel(job_id)
    cancelled = manager.run_job(job_id)
    resumed = manager.run_sync(music)

    assert cancelled.state == "cancelled"
    assert cancelled.processed == 0
    assert resumed.state == "completed"
    assert resumed.added == 2
    assert len(db.list_tracks()) == 2


def test_tag_refresh_job_uses_lightweight_track_paths(monkeypatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = _audio(tmp_path, "stored.wav")
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Stored"})
    manager = ScanJobManager(db)

    def fail_if_full_track_scan(**_kwargs):
        raise AssertionError("tag refresh job creation must use lightweight path selection")

    monkeypatch.setattr(db, "list_tracks", fail_if_full_track_scan)

    job_id = manager.create_tag_refresh_job()
    payload = manager._store.payload(job_id)

    assert payload.paths == [audio_path]
    assert payload.track_ids == {audio_path.as_posix(): track_id}
