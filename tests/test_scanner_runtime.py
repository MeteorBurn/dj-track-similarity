from __future__ import annotations

import json
import os
import re
import wave
from pathlib import Path

import dj_track_similarity.scan_jobs as scan_jobs_module
import dj_track_similarity.scanner as scanner_module
import pytest
from mutagen.id3 import TALB, TBPM, TCON, TIT2, TKEY, TPE1
from mutagen.wave import WAVE

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_tracks import (
    canonical_file_path,
    ordinal_path_key,
)
from dj_track_similarity.scan_jobs import ScanJobManager
from dj_track_similarity.scanner import scan_library


_TIMESTAMP_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z"
)


def _make_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 441)


def _make_tagged_wav(
    path: Path,
    *,
    artist: str,
    title: str,
    album: str,
    bpm: float,
    key: str,
    genre: str,
) -> None:
    _make_wav(path)
    audio = WAVE(path)
    audio.add_tags()
    assert audio.tags is not None
    audio.tags.add(TPE1(encoding=3, text=[artist]))
    audio.tags.add(TIT2(encoding=3, text=[title]))
    audio.tags.add(TALB(encoding=3, text=[album]))
    audio.tags.add(TBPM(encoding=3, text=[str(bpm)]))
    audio.tags.add(TKEY(encoding=3, text=[key]))
    audio.tags.add(TCON(encoding=3, text=[genre]))
    audio.save()


def test_scan_library_uses_canonical_absolute_path_and_marks_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    music_root = tmp_path / "Music"
    audio_path = music_root / "Straße Track.wav"
    _make_wav(audio_path)
    database = LibraryDatabase(tmp_path / "library.sqlite")

    monkeypatch.chdir(tmp_path)
    first = scan_library(database, Path("Music"))
    second = scan_library(database, music_root / ".")

    assert first.added == 1
    assert second.unchanged == 1
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT
                file_path,
                file_size_bytes,
                file_modified_ns,
                content_generation,
                last_scanned_at,
                missing_since
            FROM tracks
            """
        ).fetchone()
        assert connection.execute(
            "SELECT COUNT(*) FROM file_tags"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM track_search_fts"
        ).fetchone()[0] == 1
    assert row["file_path"] == canonical_file_path(audio_path)
    assert Path(row["file_path"]).is_absolute()
    assert int(row["file_size_bytes"]) == audio_path.stat().st_size
    assert int(row["file_modified_ns"]) == audio_path.stat().st_mtime_ns
    assert int(row["content_generation"]) == 1
    assert _TIMESTAMP_PATTERN.fullmatch(str(row["last_scanned_at"]))
    assert row["missing_since"] is None

    audio_path.unlink()
    missing_scan = scan_library(database, music_root)
    assert missing_scan == type(missing_scan)()
    with database.connect() as connection:
        missing_since = connection.execute(
            "SELECT missing_since FROM tracks"
        ).fetchone()[0]
    assert _TIMESTAMP_PATTERN.fullmatch(str(missing_since))


def test_scan_library_reads_typed_file_tags_through_runtime_repository(
    tmp_path: Path,
) -> None:
    music_root = tmp_path / "tagged"
    audio_path = music_root / "typed-track.wav"
    _make_tagged_wav(
        audio_path,
        artist="Runtime Artist",
        title="Runtime Title",
        album="Runtime Album",
        bpm=132.0,
        key="5A",
        genre="Melodic Techno",
    )
    database = LibraryDatabase(tmp_path / "library.sqlite")

    result = scan_library(database, music_root)

    assert result.added == 1
    assert result.updated == 0
    assert result.unchanged == 0
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT
                t.content_generation,
                ft.title,
                ft.artist,
                ft.album,
                ft.tag_bpm,
                ft.tag_key,
                ft.genres_json
            FROM tracks AS t
            JOIN file_tags AS ft ON ft.track_id = t.track_id
            """
        ).fetchone()
    assert int(row["content_generation"]) == 1
    assert row["title"] == "Runtime Title"
    assert row["artist"] == "Runtime Artist"
    assert row["album"] == "Runtime Album"
    assert float(row["tag_bpm"]) == 132.0
    assert row["tag_key"] == "5A"
    assert json.loads(row["genres_json"]) == ["Melodic Techno"]


def test_scan_library_content_change_increments_generation(
    tmp_path: Path,
) -> None:
    music_root = tmp_path / "changed"
    audio_path = music_root / "evolving.wav"
    _make_wav(audio_path)
    database = LibraryDatabase(tmp_path / "library.sqlite")

    assert scan_library(database, music_root).added == 1
    with database.connect() as connection:
        before = connection.execute(
            """
            SELECT track_id, track_uuid, content_generation
            FROM tracks
            """
        ).fetchone()

    with audio_path.open("ab") as stream:
        stream.write(b"\x00" * 16)

    changed = scan_library(database, music_root)
    with database.connect() as connection:
        after = connection.execute(
            """
            SELECT track_id, track_uuid, content_generation
            FROM tracks
            """
        ).fetchone()

    assert changed.updated == 1
    assert changed.added == 0
    assert changed.unchanged == 0
    assert int(after["track_id"]) == int(before["track_id"])
    assert after["track_uuid"] == before["track_uuid"]
    assert int(before["content_generation"]) == 1
    assert int(after["content_generation"]) == 2


def test_scan_audio_file_retries_until_metadata_and_file_facts_are_stable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio_path = tmp_path / "stable-retry.wav"
    audio_path.write_bytes(b"version-a")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    calls = 0

    def racing_reader(path: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            path.write_bytes(b"version-b-with-different-size")
            return {"title": "Stale Version A"}
        return {"title": "Stable Version B"}

    monkeypatch.setattr(scanner_module, "read_audio_metadata", racing_reader)

    mutation = scanner_module.scan_audio_file(database, audio_path)

    assert mutation.action == "added"
    assert calls == 2
    final_stat = audio_path.stat()
    with database.connect() as connection:
        row = connection.execute(
            """
            SELECT t.file_size_bytes, t.file_modified_ns, ft.title
            FROM tracks AS t
            JOIN file_tags AS ft ON ft.track_id = t.track_id
            """
        ).fetchone()
    assert int(row["file_size_bytes"]) == final_stat.st_size
    assert int(row["file_modified_ns"]) == final_stat.st_mtime_ns
    assert row["title"] == "Stable Version B"


def test_scan_audio_file_never_persists_mixed_metadata_after_bounded_churn(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio_path = tmp_path / "unstable.wav"
    audio_path.write_bytes(b"version")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    calls = 0

    def always_changing_reader(path: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        with path.open("ab") as stream:
            stream.write(b"x")
        return {"title": f"Unstable {calls}"}

    monkeypatch.setattr(
        scanner_module,
        "read_audio_metadata",
        always_changing_reader,
    )

    with pytest.raises(OSError, match="changed while metadata was being read"):
        scanner_module.scan_audio_file(database, audio_path)

    assert calls == scanner_module.METADATA_STABILITY_ATTEMPTS
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 0


def test_windows_path_identity_uses_lower_not_unicode_casefold() -> None:
    assert ordinal_path_key(
        r"C:\Music\Folder\TRACK.WAV",
        windows=True,
    ) == ordinal_path_key(
        "c:/music/folder/track.wav",
        windows=True,
    )
    assert ordinal_path_key(
        r"C:\Music\Straße.wav",
        windows=True,
    ) != ordinal_path_key(
        r"C:\Music\Strasse.wav",
        windows=True,
    )


def test_scan_job_manager_parallel_workers_share_thread_safe_repository(
    tmp_path: Path,
) -> None:
    music_root = tmp_path / "parallel"
    for index in range(12):
        _make_wav(music_root / f"track-{index:02d}.wav")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)

    first = manager.run_sync(music_root, workers=4)
    second = manager.run_sync(music_root, workers=4)

    assert first.state == "completed"
    assert first.processed == 12
    assert first.added == 12
    assert first.failed == 0
    assert second.state == "completed"
    assert second.processed == 12
    assert second.unchanged == 12
    assert second.failed == 0
    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM tracks"
        ).fetchone()[0] == 12
        assert connection.execute(
            "SELECT COUNT(*) FROM file_tags"
        ).fetchone()[0] == 12
        assert connection.execute(
            "SELECT COUNT(*) FROM track_search_fts"
        ).fetchone()[0] == 12
        facts = connection.execute(
            """
            SELECT file_path, file_size_bytes, file_modified_ns
            FROM tracks
            ORDER BY file_path
            """
        ).fetchall()
    assert [row["file_path"] for row in facts] == sorted(
        canonical_file_path(path)
        for path in music_root.glob("*.wav")
    )
    for row in facts:
        stat = Path(row["file_path"]).stat()
        assert int(row["file_size_bytes"]) == stat.st_size
        assert int(row["file_modified_ns"]) == stat.st_mtime_ns


def test_parallel_tag_refresh_updates_tags_and_fts_without_generation_change(
    tmp_path: Path,
    monkeypatch,
) -> None:
    music_root = tmp_path / "refresh"
    for index in range(4):
        _make_wav(music_root / f"track-{index}.wav")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    manager = ScanJobManager(database)
    assert manager.run_sync(music_root, workers=2).added == 4
    with database.connect() as connection:
        before = {
            int(row["track_id"]): (
                int(row["content_generation"]),
                int(row["file_size_bytes"]),
                int(row["file_modified_ns"]),
            )
            for row in connection.execute(
                """
                SELECT
                    track_id,
                    content_generation,
                    file_size_bytes,
                    file_modified_ns
                FROM tracks
                """
            )
        }

    monkeypatch.setattr(
        scan_jobs_module,
        "read_audio_metadata",
        lambda path: {
            "title": f"Refreshed {Path(path).stem}",
            "artist": "Refresh Artist",
        },
    )
    job_id = manager.create_tag_refresh_job(workers=3)
    final = manager.run_tag_refresh_job(job_id)

    assert final.state == "completed"
    assert final.updated == 4
    assert final.failed == 0
    with database.connect() as connection:
        after = {
            int(row["track_id"]): (
                int(row["content_generation"]),
                int(row["file_size_bytes"]),
                int(row["file_modified_ns"]),
            )
            for row in connection.execute(
                """
                SELECT
                    track_id,
                    content_generation,
                    file_size_bytes,
                    file_modified_ns
                FROM tracks
                """
            )
        }
        refreshed_titles = [
            str(row[0])
            for row in connection.execute(
                "SELECT title FROM file_tags ORDER BY track_id"
            )
        ]
        fts_matches = connection.execute(
            """
            SELECT COUNT(*)
            FROM track_search_fts
            WHERE track_search_fts MATCH '"Refresh"'
            """
        ).fetchone()[0]
    assert after == before
    assert all(title.startswith("Refreshed track-") for title in refreshed_titles)
    assert int(fts_matches) == 4


def test_windows_runtime_path_variants_do_not_duplicate_track(
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        return
    music_root = tmp_path / "CaseMusic"
    audio_path = music_root / "Case Track.wav"
    _make_wav(audio_path)
    database = LibraryDatabase(tmp_path / "library.sqlite")

    assert scan_library(database, music_root).added == 1
    variant = str(music_root).upper().replace("/", "\\")
    assert scan_library(database, variant).unchanged == 1
    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM tracks"
        ).fetchone()[0] == 1
