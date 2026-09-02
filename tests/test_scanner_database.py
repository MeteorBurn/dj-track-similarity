from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from mutagen.id3 import ID3, TCON, TIT2, TPE1

import dj_track_similarity.scanner as scanner
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.scanner import read_audio_metadata, scan_library


def _scanned_state(database: LibraryDatabase, path: Path):
    state = database.get_track_file_state(path)
    assert state is not None
    return state


def _library_roots(database: LibraryDatabase) -> tuple[str, ...]:
    with database.connect() as connection:
        row = connection.execute(
            "SELECT roots_json FROM library WHERE singleton_id = 1"
        ).fetchone()
    assert row is not None
    return tuple(json.loads(str(row[0])))


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
        first.resolve().as_posix(),
        second.resolve().as_posix(),
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
        audio.resolve().as_posix()
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
        bits_per_sample = 24

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
        "audio_format": "FLAC",
        "bit_depth": 24,
        "duration": 123.4,
        "genre": "Deep Techno",
        "country": "DE",
        "label": "Small Label",
        "title": "Warm Pad",
        "year": "2024",
    }


def test_read_audio_duration_uses_ffmpeg_when_mutagen_has_no_duration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "recoverable.mp3"
    monkeypatch.setattr(scanner, "read_audio_metadata", lambda path: {})
    monkeypatch.setattr(
        scanner,
        "read_ffmpeg_audio_duration_seconds",
        lambda path: 245.5,
        raising=False,
    )

    assert scanner.read_ffmpeg_audio_duration_seconds(audio_path) == 245.5


def test_ffmpeg_duration_reads_container_header_without_decoding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    class FakeContainer:
        duration = 245_500_000

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            return None

    class FakeAv:
        time_base = 1_000_000

        @staticmethod
        def open(path: str, mode: str, **options):
            assert path.endswith("recoverable.mp3")
            assert mode == "r"
            return FakeContainer()

    monkeypatch.setattr(scanner, "load_project_pyav", lambda: FakeAv(), raising=False)

    assert scanner.read_ffmpeg_audio_duration_seconds(tmp_path / "recoverable.mp3") == 245.5


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
        second.resolve().as_posix()
    ]

    alpha_state = _scanned_state(database, second)
    assert database.mark_missing(alpha_state.track_id)
    candidates = database.list_analysis_candidates((output,))
    assert [candidate.file_path for candidate in candidates] == [
        first.resolve().as_posix()
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
    assert database.record_library_root(old_root) == (
        old_root.resolve().as_posix(),
    )

    result = database.relocate_library(old_root, new_root, apply=False)

    assert result["dry_run"] is True
    assert result["tracks_matched"] == 1
    assert result["tracks_updated"] == 0
    assert result["missing_files"] == [
        {
            "track_id": before.track_id,
            "path": (new_root / "Artist" / "track.wav").resolve().as_posix(),
        }
    ]
    assert _scanned_state(database, old_file) == before
    assert _library_roots(database) == (old_root.resolve().as_posix(),)


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
    database.record_library_root(old_root)

    result = database.relocate_library(old_root, new_root, apply=True)

    assert result["dry_run"] is False
    assert result["tracks_matched"] == 1
    assert result["tracks_updated"] == 1
    assert result["missing_files"] == []
    assert database.get_track_file_state(old_file) is None
    after = _scanned_state(database, new_file)
    assert (after.track_id, after.track_uuid) == (
        before.track_id,
        before.track_uuid,
    )
    assert _library_roots(database) == (new_root.resolve().as_posix(),)
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
            conflicting_old.resolve().as_posix(),
            conflicting_new.resolve().as_posix(),
            before[conflicting_new].track_id,
        ),
        (
            movable_old.resolve().as_posix(),
            movable_new.resolve().as_posix(),
            _scanned_state(database, movable_new).track_id,
        ),
    }
    with pytest.raises(ValueError, match="conflict"):
        database.relocate_library(old_root, new_root, apply=True)

    for path, state in before.items():
        assert _scanned_state(database, path) == state


# --- Second-chance tag readers: mutagen by content, tolerant readers, FFmpeg ---


def _id3_tag_bytes(tmp_path: Path, **frames: str) -> bytes:
    """Serialize an ID3v2 tag with 512 bytes of padding after the frames."""
    tag_path = tmp_path / "tag.bin"
    tag_path.write_bytes(b"")
    tags = ID3()
    for frame_id, text in frames.items():
        tags.add({"TIT2": TIT2, "TPE1": TPE1, "TCON": TCON}[frame_id](encoding=3, text=[text]))
    tags.save(tag_path, padding=lambda info: 512)
    return tag_path.read_bytes()


def _iff_chunk(chunk_id: bytes, payload: bytes) -> bytes:
    return chunk_id + struct.pack(">L", len(payload)) + payload + (b"\x00" if len(payload) % 2 else b"")


def _aiff_bytes(*trailing_chunks: bytes) -> bytes:
    """A 4-frame 16-bit stereo 44.1 kHz AIFF followed by the given chunks."""
    comm = struct.pack(">hLh", 2, 4, 16) + b"\x40\x0e\xac\x44\x00\x00\x00\x00\x00\x00"
    ssnd = struct.pack(">LL", 0, 0) + b"\x00" * 16
    body = _iff_chunk(b"COMM", comm) + _iff_chunk(b"SSND", ssnd) + b"".join(trailing_chunks)
    return b"FORM" + struct.pack(">L", 4 + len(body)) + b"AIFF" + body


def _mp4_atom(name: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + name + payload


def _mp4_text_item(name: bytes, text: str) -> bytes:
    return _mp4_atom(name, _mp4_atom(b"data", b"\x00\x00\x00\x01\x00\x00\x00\x00" + text.encode()))


def test_read_audio_metadata_reads_a_mislabeled_container_by_content(
    tmp_path: Path,
) -> None:
    # An MP3 named .flac: the extension sends mutagen to the FLAC parser first.
    frame = b"\xff\xfb\x90\x00" + b"\x00" * 413  # MPEG-1 Layer III, 128 kbps, 44.1 kHz
    audio_path = tmp_path / "Murmure.flac"
    audio_path.write_bytes(frame * 24)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=["Murmure"]))
    tags.add(TPE1(encoding=3, text=["Petit Batou"]))
    tags.save(audio_path)

    metadata = read_audio_metadata(audio_path)

    assert metadata["audio_format"] == "MP3"
    assert metadata["sample_rate_hz"] == 44100
    assert metadata["channel_count"] == 2
    assert metadata["duration"] > 0
    assert metadata["title"] == "Murmure"
    assert metadata["artist"] == "Petit Batou"


def test_read_audio_metadata_takes_aiff_tags_behind_empty_and_truncated_chunks(
    tmp_path: Path,
) -> None:
    tag = _id3_tag_bytes(tmp_path, TIT2="Mount Royal", TPE1="Paolo Rocco", TCON="Minimal")
    junk_path = tmp_path / "junk chunks.aiff"
    junk_path.write_bytes(
        _aiff_bytes(_iff_chunk(b"ID3 ", b""), _iff_chunk(b"ID3 ", b""), _iff_chunk(b"ID3 ", tag))
    )
    cut_path = tmp_path / "truncated tag.aiff"
    cut_path.write_bytes(_aiff_bytes(_iff_chunk(b"ID3 ", tag))[:-256])

    for audio_path in (junk_path, cut_path):
        metadata = read_audio_metadata(audio_path)

        assert metadata["audio_format"] == "AIFF"
        assert metadata["sample_rate_hz"] == 44100
        assert metadata["channel_count"] == 2
        assert metadata["bit_depth"] == 16
        assert metadata["title"] == "Mount Royal"
        assert metadata["artist"] == "Paolo Rocco"
        assert metadata["genre"] == "Minimal"


def test_read_audio_metadata_ignores_a_malformed_mp4_chapter_atom(
    tmp_path: Path,
) -> None:
    mvhd = _mp4_atom(
        b"mvhd",
        b"\x00" * 4 + struct.pack(">IIII", 0, 0, 44100, 88200)
        + struct.pack(">IH", 0x00010000, 0x0100) + b"\x00" * 70 + struct.pack(">I", 2),
    )
    hdlr = _mp4_atom(b"hdlr", b"\x00" * 8 + b"mdir" + b"appl" + b"\x00" * 9)
    ilst = _mp4_atom(b"ilst", _mp4_text_item(b"\xa9nam", "Slatoinia") + _mp4_text_item(b"\xa9ART", "STOi"))
    meta = _mp4_atom(b"meta", b"\x00" * 4 + hdlr + ilst)
    # A stale chpl header over unrelated bytes: 114 "chapters" in 18 bytes.
    chpl = _mp4_atom(b"chpl", b"\x00" * 8 + bytes([114]) + b"ee" + b"\x00" * 16)
    audio_path = tmp_path / "stale chapters.m4a"
    audio_path.write_bytes(
        _mp4_atom(b"ftyp", b"M4A \x00\x00\x02\x00M4A mp42isom")
        + _mp4_atom(b"moov", mvhd + _mp4_atom(b"udta", meta + chpl))
        + _mp4_atom(b"mdat", b"\x00" * 16)
    )

    metadata = read_audio_metadata(audio_path)

    assert metadata["audio_format"] == "M4A"
    assert metadata["title"] == "Slatoinia"
    assert metadata["artist"] == "STOi"


def test_read_audio_metadata_keeps_only_the_name_when_no_reader_fits(
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "opaque.mp3"
    audio_path.write_bytes(b"not an audio container at all")

    metadata = read_audio_metadata(audio_path)

    assert metadata.pop(scanner.READER_NOTE_KEY)
    assert metadata == {"title": "opaque"}
