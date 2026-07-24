from __future__ import annotations

import json
from pathlib import Path

import pytest

import dj_track_similarity.scanner as scanner
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_tracks import canonical_file_path
from dj_track_similarity.scanner import read_audio_metadata, scan_library


def _scanned_state(database: LibraryDatabase, path: Path):
    state = database.get_track_file_state(path)
    assert state is not None
    return state


def _mert_output():
    return current_embedding_analysis_output("mert")


def test_scan_library_indexes_supported_audio_files_and_skips_unchanged(
    tmp_path: Path,
) -> None:
    music_root = tmp_path / "music"
    music_root.mkdir()
    first = music_root / "Artist - Track.mp3"
    second = music_root / "ambient.wav"
    ignored = music_root / "notes.txt"
    first.write_bytes(b"not really mp3")
    second.write_bytes(b"RIFF0000WAVE")
    ignored.write_text("skip me", encoding="utf-8")

    database = LibraryDatabase(tmp_path / "library.sqlite")

    first_scan = scan_library(database, music_root)
    second_scan = scan_library(database, music_root)

    assert first_scan.added == 2
    assert first_scan.updated == 0
    assert first_scan.unchanged == 0
    assert second_scan.added == 0
    assert second_scan.updated == 0
    assert second_scan.unchanged == 2
    states = database.list_track_paths()
    assert {item.file_path for item in states} == {
        canonical_file_path(first),
        canonical_file_path(second),
    }
    assert all(Path(item.file_path).stat().st_size > 0 for item in states)


def test_scan_library_skips_appledouble_resource_fork_audio_names(
    tmp_path: Path,
) -> None:
    music_root = tmp_path / "music"
    music_root.mkdir()
    audio = music_root / "01. Lampetee.aiff"
    resource_fork = music_root / "._01. Lampetee.aiff"
    audio.write_bytes(b"FORM\x00\x00\x00\x04AIFF")
    resource_fork.write_bytes(b"not an audio stream")
    database = LibraryDatabase(tmp_path / "library.sqlite")

    stats = scan_library(database, music_root)

    assert stats.added == 1
    assert [item.file_path for item in database.list_track_paths()] == [
        canonical_file_path(audio)
    ]


def test_read_audio_metadata_skips_tag_keys_that_mutagen_rejects(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class RejectingTags(dict):
        def __contains__(self, key: object) -> bool:
            if key == "\xa9ART":
                raise ValueError("invalid Vorbis key")
            return super().__contains__(key)

    class FakeAudio:
        info = None
        tags = RejectingTags({"title": ["Warm Pad"]})

    monkeypatch.setattr(scanner, "MutagenFile", lambda path: FakeAudio())

    metadata = read_audio_metadata(tmp_path / "track.flac")

    assert metadata["title"] == "Warm Pad"
    assert "artist" not in metadata


def test_read_audio_metadata_uses_fixed_tag_whitelist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeInfo:
        length = 123.4
        codec = "FLAC"

    class FakeAudio:
        info = FakeInfo()
        mime = ["audio/flac"]
        tags = {
            "title": ["Warm Pad"],
            "artist": ["Artist"],
            "genre": ["Deep Techno"],
            "year": ["2024"],
            "country": ["DE"],
            "publisher": ["Small Label"],
            "CATALOGNUMBER": ["CAT-001"],
            "isrc": ["US-ABC-24-00001"],
            "random_plugin_blob": ["ignore me"],
        }

    monkeypatch.setattr(scanner, "MutagenFile", lambda path: FakeAudio())

    metadata = read_audio_metadata(tmp_path / "track.flac")

    assert metadata == {
        "artist": "Artist",
        "audio_codec": "FLAC",
        "audio_format": "FLAC",
        "catalog_number": "CAT-001",
        "duration": 123.4,
        "genre": "Deep Techno",
        "isrc": "US-ABC-24-00001",
        "country": "DE",
        "label": "Small Label",
        "title": "Warm Pad",
        "year": "2024",
    }


def test_read_audio_metadata_converts_mutagen_objects_to_json_safe_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeTimestamp:
        def __str__(self) -> str:
            return "2025-04-01"

    class FakeFrame:
        text = [FakeTimestamp()]

    class FakeAudio:
        info = None
        tags = {
            "TDRC": FakeFrame(),
            "trkn": [(2, 4)],
        }

    monkeypatch.setattr(scanner, "MutagenFile", lambda path: FakeAudio())

    metadata = read_audio_metadata(tmp_path / "track.mp3")

    assert metadata["year"] == "2025-04-01"
    assert metadata["track_number"] == "2/4"
    assert json.dumps(metadata)


def test_analysis_candidates_are_path_ordered_limited_and_skip_missing_tracks(
    tmp_path: Path,
) -> None:
    music_root = tmp_path / "music"
    first = music_root / "Zeta.wav"
    second = music_root / "alpha.wav"
    first.parent.mkdir()
    first.write_bytes(b"zeta")
    second.write_bytes(b"alpha")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    assert scan_library(database, music_root).added == 2

    output = _mert_output()
    database.register_analysis_outputs((output,))

    limited = database.list_analysis_candidates((output,), limit=1)
    assert [candidate.file_path for candidate in limited] == [
        canonical_file_path(second)
    ]

    alpha_state = _scanned_state(database, second)
    assert database.mark_missing(alpha_state.track_id)
    candidates = database.list_analysis_candidates((output,))
    assert [candidate.file_path for candidate in candidates] == [
        canonical_file_path(first)
    ]
    assert candidates[0].missing_outputs == (output,)


def test_relocate_library_dry_run_preserves_track_and_reports_missing_file(
    tmp_path: Path,
) -> None:
    old_root = tmp_path / "ssd_music"
    new_root = tmp_path / "archive_music"
    old_file = old_root / "Artist" / "track.wav"
    old_file.parent.mkdir(parents=True)
    new_root.mkdir()
    old_file.write_bytes(b"audio")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    assert scan_library(database, old_root).added == 1
    before = _scanned_state(database, old_file)
    assert database.set_library_root(old_root) == canonical_file_path(old_root)

    result = database.relocate_library(old_root, new_root, apply=False)

    assert result["dry_run"] is True
    assert result["tracks_matched"] == 1
    assert result["tracks_updated"] == 0
    assert result["missing_files"] == [
        {
            "track_id": before.track_id,
            "path": canonical_file_path(new_root / "Artist" / "track.wav"),
        }
    ]
    assert _scanned_state(database, old_file) == before
    assert database.get_library_root() == canonical_file_path(old_root)


def test_relocate_library_apply_updates_only_database_paths_and_identity(
    tmp_path: Path,
) -> None:
    old_root = tmp_path / "ssd_music"
    new_root = tmp_path / "archive_music"
    old_file = old_root / "Artist" / "track.wav"
    new_file = new_root / "Artist" / "track.wav"
    old_file.parent.mkdir(parents=True)
    new_file.parent.mkdir(parents=True)
    old_file.write_bytes(b"old audio")
    new_file.write_bytes(b"new audio")
    old_bytes = old_file.read_bytes()
    new_bytes = new_file.read_bytes()
    database = LibraryDatabase(tmp_path / "library.sqlite")
    assert scan_library(database, old_root).added == 1
    before = _scanned_state(database, old_file)
    database.set_library_root(old_root)

    result = database.relocate_library(old_root, new_root, apply=True)

    assert result["dry_run"] is False
    assert result["tracks_matched"] == 1
    assert result["tracks_updated"] == 1
    assert result["missing_files"] == []
    assert database.get_track_file_state(old_file) is None
    after = _scanned_state(database, new_file)
    assert (after.track_id, after.track_uuid, after.content_generation) == (
        before.track_id,
        before.track_uuid,
        before.content_generation,
    )
    assert database.get_library_root() == canonical_file_path(new_root)
    assert old_file.read_bytes() == old_bytes
    assert new_file.read_bytes() == new_bytes


def test_relocate_library_conflict_is_rejected_without_partial_updates(
    tmp_path: Path,
) -> None:
    old_root = tmp_path / "ssd_music"
    new_root = tmp_path / "archive_music"
    movable_old = old_root / "movable.wav"
    movable_new = new_root / "movable.wav"
    conflicting_old = old_root / "conflict.wav"
    conflicting_new = new_root / "conflict.wav"
    old_root.mkdir()
    new_root.mkdir()
    movable_old.write_bytes(b"old movable")
    movable_new.write_bytes(b"new movable")
    conflicting_old.write_bytes(b"old conflict")
    conflicting_new.write_bytes(b"new conflict")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    assert scan_library(database, old_root).added == 2
    assert scan_library(database, new_root).added == 2
    before = {
        path: _scanned_state(database, path)
        for path in (movable_old, conflicting_old, conflicting_new)
    }

    preview = database.relocate_library(old_root, new_root, apply=False)
    assert preview["tracks_matched"] == 2
    assert {
        (
            item["old_path"],
            item["new_path"],
            item["existing_track_id"],
        )
        for item in preview["conflicts"]
    } == {
        (
            canonical_file_path(conflicting_old),
            canonical_file_path(conflicting_new),
            before[conflicting_new].track_id,
        ),
        (
            canonical_file_path(movable_old),
            canonical_file_path(movable_new),
            _scanned_state(database, movable_new).track_id,
        ),
    }
    with pytest.raises(ValueError, match="conflict"):
        database.relocate_library(old_root, new_root, apply=True)

    for path, state in before.items():
        assert _scanned_state(database, path) == state
