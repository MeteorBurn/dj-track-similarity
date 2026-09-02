from __future__ import annotations

from concurrent.futures import Future, ProcessPoolExecutor
import threading
import wave
from pathlib import Path

from mutagen.id3 import ID3, TIT2

import dj_track_similarity.scan_jobs as scan_jobs_module
from dj_track_similarity import scanner
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_tracks import canonical_file_path
from dj_track_similarity.scan_jobs import ScanJobManager, ScanJobPayload
from dj_track_similarity.track_models import FileTags, ScannedFile


def _audio(root: Path, name: str, *, seconds: float = 0.01) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * round(44_100 * seconds))
    return path


def _mislabeled_mp3(root: Path, name: str) -> Path:
    """An MP3 saved under a foreign extension, which the default open rejects."""
    path = root / name
    frame = b"\xff\xfb\x90\x00" + b"\x00" * 413  # MPEG-1 Layer III, 128 kbps, 44.1 kHz
    path.write_bytes(frame * 24)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=["Murmure"]))
    tags.save(path)
    return path


def test_scan_job_records_progress_and_events(tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "a.wav")
    _audio(music, "b.wav")
    _mislabeled_mp3(music, "c.flac")
    (music / "ignore.txt").write_text("skip", encoding="utf-8")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)

    status = manager.run_sync(music)

    assert status.state == "completed"
    assert status.total == 3
    assert status.processed == 3
    assert status.added == 3
    assert status.updated == 0
    assert status.unchanged == 0
    assert status.avg_seconds_per_track is not None
    assert status.events[0].message == "Scan queued · workers 1 · limit all"
    assert any(event.level == "ok" and event.path.endswith("a.wav") for event in status.events)
    # The reader note crosses the worker process and lands in the job log.
    assert any(event.level == "warn" and event.path.endswith("c.flac") for event in status.events)
    assert status.events[-1].message == "Scan completed"
    with database.connect() as connection:
        row = connection.execute(
            "SELECT t.audio_format, g.title FROM tracks t JOIN tags g USING(track_id) "
            "WHERE t.file_path LIKE '%c.flac'"
        ).fetchone()
    assert tuple(row) == ("MP3", "Murmure")


def test_scan_job_records_requested_worker_count(tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "a.wav")
    _audio(music, "b.wav")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)

    status = manager.run_sync(music, workers=2)

    assert status.workers == 2
    assert status.events[0].message == "Scan queued · workers 2 · limit all"
    assert status.state == "completed"
    assert status.processed == 2


def test_scan_job_creation_collects_paths_for_existing_workers(
    tmp_path: Path,
) -> None:
    music = tmp_path / "music"
    music.mkdir()
    audio_path = _audio(music, "track.wav")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)

    job_id = manager.create_job(music, workers=8)
    payload = manager._store.payload(job_id)

    assert manager.get(job_id).state == "queued"
    assert manager.get(job_id).total == 1
    assert isinstance(payload, ScanJobPayload)
    assert payload.paths == [audio_path]


def test_parallel_scan_uses_process_workers_and_writes_on_calling_thread(
    monkeypatch,
    tmp_path: Path,
) -> None:
    music = tmp_path / "music"
    music.mkdir()
    for index in range(4):
        _audio(music, f"track-{index}.wav")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)
    original_upsert = database.upsert_scanned_track
    created_worker_counts: list[int] = []
    writer_thread_ids: list[int] = []

    class RecordingProcessPoolExecutor:
        def __init__(self, *, max_workers: int) -> None:
            created_worker_counts.append(max_workers)
            self._executor = ProcessPoolExecutor(max_workers=max_workers)

        def __enter__(self):
            self._executor.__enter__()
            return self

        def __exit__(self, *args) -> None:
            self._executor.__exit__(*args)

        def submit(self, *args, **kwargs):
            return self._executor.submit(*args, **kwargs)

    def record_writer_thread(*, file: ScannedFile, tags: FileTags):
        writer_thread_ids.append(threading.get_ident())
        return original_upsert(file=file, tags=tags)

    monkeypatch.setattr(
        scan_jobs_module,
        "ProcessPoolExecutor",
        RecordingProcessPoolExecutor,
        raising=False,
    )
    monkeypatch.setattr(database, "upsert_scanned_track", record_writer_thread)

    status = manager.run_sync(music, workers=4)

    assert status.added == 4
    assert created_worker_counts == [4]
    assert len(set(writer_thread_ids)) == 1
    assert writer_thread_ids[0] == threading.get_ident()


def test_parallel_scan_writes_ready_batches_before_all_paths_are_prepared(
    monkeypatch,
    tmp_path: Path,
) -> None:
    music = tmp_path / "music"
    music.mkdir()
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)
    job_id = manager.create_job(music, workers=2)
    paths = [music / f"track-{index}.wav" for index in range(10)]
    events: list[tuple[str, tuple[Path, ...]]] = []

    class RecordingFuture(Future[list[str]]):
        def __init__(self, path_group: list[str]) -> None:
            super().__init__()
            self.path_group = path_group
            self.set_result(path_group)

        def result(self, timeout=None):
            events.append(
                ("prepared", tuple(Path(path) for path in self.path_group))
            )
            return super().result(timeout)

    class ImmediateProcessPoolExecutor:
        def __init__(self, *, max_workers: int) -> None:
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def submit(self, _function, path_group, **_kwargs):
            return RecordingFuture(path_group)

    def collect_prepared_group(_job_id: str, results: list[str]):
        return [(Path(path), object()) for path in results], 0

    def record_write(_job_id: str, batch) -> None:
        events.append(("write", tuple(path for path, _prepared in batch)))

    monkeypatch.setattr(scan_jobs_module, "_SCAN_PREPARE_BATCH_SIZE", 2, raising=False)
    monkeypatch.setattr(
        scan_jobs_module,
        "ProcessPoolExecutor",
        ImmediateProcessPoolExecutor,
    )
    monkeypatch.setattr(manager, "_collect_prepared_scan_group", collect_prepared_group)
    monkeypatch.setattr(manager, "_write_prepared_scan_batch", record_write)

    manager._run_parallel_scan(job_id, paths, workers=2)

    event_kinds = [kind for kind, _paths in events]
    assert event_kinds.index("write") < max(
        index for index, kind in enumerate(event_kinds) if kind == "prepared"
    )
    assert event_kinds[-1] == "write"
    assert all(
        len(batch_paths) <= 2
        for kind, batch_paths in events
        if kind == "write"
    )
    assert {
        path
        for kind, batch_paths in events
        if kind == "write"
        for path in batch_paths
    } == set(paths)


def test_scan_writer_rejects_metadata_if_source_changes_after_read(
    tmp_path: Path,
) -> None:
    music = tmp_path / "music"
    music.mkdir()
    audio_path = _audio(music, "track.wav")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)
    prepared = scanner.prepare_audio_file(database, audio_path)
    assert prepared is not None
    job_id = manager.create_job(music)

    with audio_path.open("ab") as handle:
        handle.write(b"changed")

    manager._write_prepared_scan_one(job_id, audio_path, prepared)

    status = manager.get(job_id)
    assert status.added == 0
    assert status.failed == 1
    assert database.list_track_paths() == []


def test_limited_scan_does_not_mark_unseen_tracks_missing(tmp_path: Path) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "a.wav")
    _audio(music, "b.wav")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)
    assert manager.run_sync(music).added == 2

    status = manager.run_sync(music, limit=1)

    assert status.limit == 1
    assert status.total == 0
    assert status.added == 0
    assert status.unchanged == 0
    assert status.events[0].message == "Scan queued · workers 1 · limit 1"
    with database.connect() as connection:
        missing_count = connection.execute(
            "SELECT COUNT(*) FROM tracks WHERE missing_since IS NOT NULL"
        ).fetchone()[0]
    assert missing_count == 0


def test_scan_job_filters_extensions_and_duration_without_marking_others_missing(
    tmp_path: Path,
) -> None:
    music = tmp_path / "music"
    music.mkdir()
    accepted = _audio(music, "accepted.wav", seconds=2)
    _audio(music, "short.wav", seconds=0.5)
    _audio(music, "long.wav", seconds=4)
    (music / "ignored.flac").write_bytes(b"not audio")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)

    status = manager.run_sync(
        music,
        extensions={".wav"},
        min_duration_seconds=1,
        max_duration_seconds=3,
    )

    assert status.state == "completed"
    assert status.total == 1
    assert status.processed == 1
    assert status.added == 1
    assert status.skipped == 3
    assert [item.file_path for item in database.list_track_paths()] == [accepted.resolve().as_posix()]


def test_prepare_audio_path_group_reads_duration_once(
    monkeypatch,
    tmp_path: Path,
) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "accepted.wav", seconds=2)
    original_reader = scanner.read_audio_metadata
    reads: list[Path] = []

    def record_metadata_read(path: str | Path) -> dict[str, object]:
        reads.append(Path(path))
        return original_reader(path)

    monkeypatch.setattr(scanner, "read_audio_metadata", record_metadata_read)

    results = scanner.prepare_audio_path_group(
        [str(music / "accepted.wav")],
        min_duration_seconds=1,
        max_duration_seconds=3,
    )

    assert results[0].prepared is not None
    assert reads == [music / "accepted.wav"]


def test_duration_filtered_scan_limit_counts_only_eligible_tracks(
    tmp_path: Path,
) -> None:
    music = tmp_path / "music"
    music.mkdir()
    _audio(music, "short.wav", seconds=0.5)
    _audio(music, "first.wav", seconds=2)
    _audio(music, "second.wav", seconds=2)
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)

    status = manager.run_sync(
        music,
        workers=2,
        limit=1,
        min_duration_seconds=1,
        max_duration_seconds=3,
    )

    assert status.added == 1
    assert len(database.list_track_paths()) == 1


def test_scan_stops_once_the_limit_of_added_tracks_is_reached(
    tmp_path: Path,
) -> None:
    music = tmp_path / "music"
    music.mkdir()
    stored = _audio(music, "a-stored.wav")
    for index in range(6):
        _audio(music, f"b-new-{index}.wav")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)
    assert scanner.scan_audio_file(database, stored).action == "added"

    status = manager.run_sync(music, limit=2)
    resumed = manager.run_sync(music, limit=2)

    # Stored paths never consume the limit, and the walk ends with the limit.
    assert status.added == 2
    assert status.processed == 2
    assert status.total == 2
    assert status.unchanged == 0
    assert status.events[-2].message == "Scan limit 2 reached, scanning stopped"
    # The next run excludes what is stored and continues with new paths only.
    assert resumed.added == 2
    assert resumed.processed == 2
    assert resumed.unchanged == 0
    assert [item.file_path for item in database.list_track_paths()] == [
        path.resolve().as_posix()
        for path in [
            stored,
            music / "b-new-0.wav",
            music / "b-new-1.wav",
            music / "b-new-2.wav",
            music / "b-new-3.wav",
        ]
    ]


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
    assert current.missing_since is None
