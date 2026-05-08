from pathlib import Path
import wave

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity import tags
from dj_track_similarity.tags import apply_genre_tags, build_genre_tag_preview, build_tag_preview
from mutagen import File as MutagenFile
from mutagen.id3 import ID3, TALB, TCON, TIT2, TPE1


def test_tag_preview_reports_custom_tags_without_touching_audio_file(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"fake audio")
    before = audio_path.read_bytes()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=audio_path,
        size=len(before),
        mtime=audio_path.stat().st_mtime,
        metadata={"artist": "A", "title": "T"},
        bpm=128,
        musical_key="8A",
        energy=0.73,
    )

    preview = build_tag_preview(db, [track_id])

    assert audio_path.read_bytes() == before
    assert preview[0].track_id == track_id
    assert preview[0].path == audio_path.as_posix()
    assert preview[0].tags == {
        "DJ_SIM_BPM": "128.0",
        "DJ_SIM_KEY": "8A",
        "DJ_SIM_ENERGY": "0.730",
    }


def test_genre_tag_preview_uses_maest_genres_without_touching_audio_file(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"fake audio")
    before = audio_path.read_bytes()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=audio_path,
        size=len(before),
        mtime=audio_path.stat().st_mtime,
        metadata={"title": "T"},
    )
    db.save_genres(track_id, [{"label": "Deep_Techno", "score": 0.9}, {"label": "Minimal", "score": 0.8}], model_name="maest")

    preview = build_genre_tag_preview(db, [track_id])

    assert audio_path.read_bytes() == before
    assert preview[0].tags == {"GENRE": "Deep Techno; Minimal"}


def test_genre_tag_preview_removes_maest_category_prefix(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"fake audio")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=audio_path,
        size=audio_path.stat().st_size,
        mtime=audio_path.stat().st_mtime,
        metadata={"title": "T"},
    )
    db.save_genres(
        track_id,
        [{"label": "Electronic---Tech House", "score": 0.9}, {"label": "Electronic---Minimal_Techno", "score": 0.8}],
        model_name="maest",
    )

    preview = build_genre_tag_preview(db, [track_id])

    assert preview[0].tags == {"GENRE": "Tech House; Minimal Techno"}


def test_apply_genre_tags_overwrites_standard_genre_tag(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"fake audio")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=audio_path,
        size=audio_path.stat().st_size,
        mtime=audio_path.stat().st_mtime,
        metadata={"title": "T"},
    )
    db.save_genres(track_id, [{"label": "House", "score": 0.9}], model_name="maest")
    written: list[tuple[Path, str]] = []
    monkeypatch.setattr(tags, "_write_genre_tag", lambda path, genre: written.append((path, genre)))

    result = apply_genre_tags(db, [track_id])

    assert result[0].tags == {"GENRE": "House"}
    assert written == [(audio_path, "House")]


def test_write_genre_tag_replaces_common_audio_genre_field(monkeypatch, tmp_path: Path) -> None:
    class FakeAudio:
        def __init__(self) -> None:
            self.tags = {"GENRE": ["Old"]}
            self.saved = False

        def __setitem__(self, key: str, value: str) -> None:
            self.tags[key] = value

        def save(self) -> None:
            self.saved = True

    fake_audio = FakeAudio()
    monkeypatch.setattr(tags, "MutagenFile", lambda path: fake_audio)

    tags._write_genre_tag(tmp_path / "track.flac", "House; Techno")

    assert fake_audio.tags["Genre"] == "House; Techno"
    assert fake_audio.saved


def test_write_genre_tag_handles_id3_tags_inside_wave(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.wav"
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)

    tags._write_genre_tag(audio_path, "Tech House; Minimal")

    saved = MutagenFile(audio_path)
    assert saved.tags["TCON"].text == ["Tech House; Minimal"]
    with wave.open(str(audio_path), "rb") as handle:
        assert handle.getnframes() == 44_100


def test_write_genre_tag_uses_wave_loader_when_generic_mutagen_detects_no_tags(monkeypatch, tmp_path: Path) -> None:
    class FakeWave:
        def __init__(self, path: Path) -> None:
            self.path = path
            self.tags = None
            self.saved = False

        def add_tags(self) -> None:
            self.tags = ID3()

        def save(self) -> None:
            self.saved = True

    audio_path = tmp_path / "track.wav"
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)
    fake_wave = FakeWave(audio_path)
    monkeypatch.setattr(tags, "MutagenFile", lambda path: None)
    monkeypatch.setattr(tags, "WAVE", lambda path: fake_wave)

    tags._write_genre_tag(audio_path, "Minimal")

    assert fake_wave.saved
    assert fake_wave.tags["TCON"].text == ["Minimal"]


def test_write_genre_tag_persists_to_wave_and_preserves_existing_id3_tags(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.wav"
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)
    audio = MutagenFile(audio_path)
    audio.add_tags()
    audio.tags.add(TPE1(encoding=3, text=["Existing Artist"]))
    audio.tags.add(TIT2(encoding=3, text=["Existing Title"]))
    audio.save()

    tags._write_genre_tag(audio_path, "Tech House; Minimal; Techno")

    saved = MutagenFile(audio_path)
    assert saved.tags["TCON"].text == ["Tech House; Minimal; Techno"]
    assert saved.tags["TPE1"].text == ["Existing Artist"]
    assert saved.tags["TIT2"].text == ["Existing Title"]
    with wave.open(str(audio_path), "rb") as handle:
        assert handle.getnframes() == 44_100


def test_write_genre_tag_refuses_malformed_wave_without_rewriting(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.wav"
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)
    data = bytearray(audio_path.read_bytes())
    data[36:40] = b"\x00dat"
    audio_path.write_bytes(data)
    before = audio_path.read_bytes()

    with pytest.raises(ValueError, match="readable data chunk"):
        tags._write_genre_tag(audio_path, "Tech House; Minimal; Techno")

    assert audio_path.read_bytes() == before


def test_apply_genre_tags_skips_malformed_wave_and_continues(tmp_path: Path, caplog) -> None:
    malformed_path = tmp_path / "malformed.wav"
    with wave.open(str(malformed_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)
    data = bytearray(malformed_path.read_bytes())
    data[36:40] = b"\x00dat"
    malformed_path.write_bytes(data)
    malformed_before = malformed_path.read_bytes()

    valid_path = tmp_path / "valid.wav"
    with wave.open(str(valid_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)

    db = LibraryDatabase(tmp_path / "library.sqlite")
    malformed_id = db.upsert_track(
        path=malformed_path,
        size=malformed_path.stat().st_size,
        mtime=malformed_path.stat().st_mtime,
        metadata={"title": "Malformed"},
    )
    valid_id = db.upsert_track(
        path=valid_path,
        size=valid_path.stat().st_size,
        mtime=valid_path.stat().st_mtime,
        metadata={"title": "Valid"},
    )
    db.save_genres(malformed_id, [{"label": "Tech House", "score": 0.9}], model_name="maest")
    db.save_genres(valid_id, [{"label": "Minimal", "score": 0.8}], model_name="maest")

    with caplog.at_level("WARNING", logger="dj_track_similarity.tags"):
        previews = apply_genre_tags(db, [malformed_id, valid_id])

    assert malformed_path.read_bytes() == malformed_before
    assert MutagenFile(valid_path).tags["TCON"].text == ["Minimal"]
    assert [preview.track_id for preview in previews] == [malformed_id, valid_id]
    assert "Skipping genre tag write for unsupported WAV container" in caplog.text


def test_apply_genre_tags_repairs_oversized_wave_data_chunk_before_writing(tmp_path: Path) -> None:
    audio_path = tmp_path / "oversized-data.wav"
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)
    data = bytearray(audio_path.read_bytes())
    data_offset = data.index(b"data")
    actual_size = len(data) - data_offset - 8
    data[data_offset + 4 : data_offset + 8] = (actual_size + 4096).to_bytes(4, "little")
    audio_path.write_bytes(data)

    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=audio_path,
        size=audio_path.stat().st_size,
        mtime=audio_path.stat().st_mtime,
        metadata={"title": "Oversized"},
    )
    db.save_genres(track_id, [{"label": "Minimal", "score": 0.8}], model_name="maest")

    apply_genre_tags(db, [track_id])

    saved = MutagenFile(audio_path)
    track = db.get_track(track_id)
    assert saved.tags["TCON"].text == ["Minimal"]
    assert track.metadata["genre"] == "Minimal"
    repaired = audio_path.read_bytes()
    assert int.from_bytes(repaired[data_offset + 4 : data_offset + 8], "little") == actual_size


def test_write_genre_tag_persists_to_mp3_id3_and_preserves_existing_tags(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.mp3"
    id3 = ID3()
    id3.add(TPE1(encoding=3, text=["Existing Artist"]))
    id3.add(TIT2(encoding=3, text=["Existing Title"]))
    id3.add(TALB(encoding=3, text=["Existing Album"]))
    id3.add(TCON(encoding=3, text=["Old Genre"]))
    id3.save(audio_path)

    tags._write_genre_tag(audio_path, "Tech House; Minimal; Techno")

    saved = ID3(audio_path)
    assert saved["TCON"].text == ["Tech House; Minimal; Techno"]
    assert saved["TPE1"].text == ["Existing Artist"]
    assert saved["TIT2"].text == ["Existing Title"]
    assert saved["TALB"].text == ["Existing Album"]


def test_apply_genre_tags_refreshes_database_metadata_and_preserves_existing_file_tags(tmp_path: Path) -> None:
    audio_path = tmp_path / "track.wav"
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)
    audio = MutagenFile(audio_path)
    audio.add_tags()
    audio.tags.add(TPE1(encoding=3, text=["Existing Artist"]))
    audio.tags.add(TIT2(encoding=3, text=["Existing Title"]))
    audio.tags.add(TALB(encoding=3, text=["Existing Album"]))
    audio.tags.add(TCON(encoding=3, text=["Old Genre"]))
    audio.save()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=audio_path,
        size=audio_path.stat().st_size,
        mtime=audio_path.stat().st_mtime,
        metadata={"artist": "Existing Artist", "title": "Existing Title", "album": "Existing Album", "genre": "Old Genre"},
    )
    db.save_genres(track_id, [{"label": "Electronic---Tech House", "score": 0.9}], model_name="maest")

    apply_genre_tags(db, [track_id])

    saved = MutagenFile(audio_path)
    track = db.get_track(track_id)
    assert saved["TCON"].text == ["Tech House"]
    assert saved["TPE1"].text == ["Existing Artist"]
    assert saved["TIT2"].text == ["Existing Title"]
    assert saved["TALB"].text == ["Existing Album"]
    assert track.metadata["artist"] == "Existing Artist"
    assert track.metadata["title"] == "Existing Title"
    assert track.metadata["album"] == "Existing Album"
    assert track.metadata["genre"] == "Tech House"
    assert track.genres == ["Electronic---Tech House"]
