from pathlib import Path

import dj_track_similarity.scanner as scanner
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.scanner import read_audio_metadata, scan_library


def test_scan_library_indexes_supported_audio_files_and_skips_unchanged(tmp_path: Path) -> None:
    music_root = tmp_path / "music"
    music_root.mkdir()
    first = music_root / "Artist - Track.mp3"
    second = music_root / "ambient.wav"
    ignored = music_root / "notes.txt"
    first.write_bytes(b"not really mp3")
    second.write_bytes(b"RIFF0000WAVE")
    ignored.write_text("skip me", encoding="utf-8")

    db = LibraryDatabase(tmp_path / "library.sqlite")

    first_stats = scan_library(db, music_root)
    second_stats = scan_library(db, music_root)

    tracks = db.list_tracks()
    assert first_stats.added == 2
    assert first_stats.updated == 0
    assert first_stats.unchanged == 0
    assert second_stats.added == 0
    assert second_stats.updated == 0
    assert second_stats.unchanged == 2
    assert {Path(track.path).name for track in tracks} == {"Artist - Track.mp3", "ambient.wav"}
    assert all(track.size > 0 for track in tracks)


def test_read_audio_metadata_skips_tag_keys_that_mutagen_rejects(monkeypatch, tmp_path: Path) -> None:
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
