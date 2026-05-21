from collections.abc import Callable
from pathlib import Path
import hashlib
import shutil
import subprocess
import wave

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity import tags
from dj_track_similarity.api import create_app
from dj_track_similarity.tags import GenreTagJobManager, apply_genre_tags, build_genre_tag_preview, build_tag_preview, genre_tag_apply_summary
from fastapi.testclient import TestClient
from mutagen import File as MutagenFile
from mutagen.id3 import ID3, TALB, TCON, TIT2, TPE1


def _wave_chunk_payload(path: Path, chunk_id: bytes = b"data") -> bytes:
    data = path.read_bytes()
    pos = 12
    while pos + 8 <= len(data):
        current_id = data[pos : pos + 4]
        chunk_size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        payload_start = pos + 8
        payload_end = payload_start + chunk_size
        if current_id == chunk_id:
            return bytes(data[payload_start:payload_end])
        chunk_end = payload_end + (chunk_size % 2)
        if chunk_end <= pos or chunk_end > len(data) + 1:
            break
        pos = chunk_end
    raise AssertionError(f"Missing WAV chunk: {chunk_id!r}")


def _riff_size_delta(path: Path) -> int:
    data = path.read_bytes()
    return len(data) - (int.from_bytes(data[4:8], "little") + 8)


def _wave_chunk_spans(path: Path, chunk_id: bytes) -> list[tuple[int, int]]:
    data = path.read_bytes()
    spans: list[tuple[int, int]] = []
    pos = 12
    while pos + 8 <= len(data):
        current_id = data[pos : pos + 4]
        chunk_size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        payload_end = pos + 8 + chunk_size
        chunk_end = payload_end + (chunk_size % 2)
        if current_id == chunk_id:
            spans.append((pos, chunk_end))
        if chunk_end <= pos or chunk_end > len(data) + 1:
            break
        pos = chunk_end
    return spans


def _require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg is required for real audio container tag tests")
    return ffmpeg


def _make_tone(path: Path, codec_args: list[str]) -> None:
    subprocess.run(
        [
            _require_ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.5:sample_rate=44100",
            *codec_args,
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _decoded_audio_md5(path: Path) -> str:
    result = subprocess.run(
        [
            _require_ffmpeg(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-",
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return hashlib.md5(result.stdout).hexdigest()


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
    assert result[0].status == "applied"
    assert result[0].message == "Genre tag written"
    assert written == [(audio_path, "House")]


def test_apply_genre_tags_reports_failures_and_continues(monkeypatch, tmp_path: Path, caplog) -> None:
    first_path = tmp_path / "first.flac"
    second_path = tmp_path / "second.flac"
    first_path.write_bytes(b"fake audio")
    second_path.write_bytes(b"fake audio")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first_id = db.upsert_track(path=first_path, size=first_path.stat().st_size, mtime=1, metadata={"title": "First"})
    second_id = db.upsert_track(path=second_path, size=second_path.stat().st_size, mtime=1, metadata={"title": "Second"})
    db.save_genres(first_id, [{"label": "House", "score": 0.9}], model_name="maest")
    db.save_genres(second_id, [{"label": "Minimal", "score": 0.8}], model_name="maest")
    written: list[Path] = []

    def fake_write(path: Path, genre: str) -> None:
        if path == first_path:
            raise RuntimeError("permission denied")
        written.append(path)

    monkeypatch.setattr(tags, "_write_genre_tag", fake_write)

    with caplog.at_level("INFO", logger="dj_track_similarity.tags"):
        result = apply_genre_tags(db, [first_id, second_id])

    assert [item.status for item in result] == ["failed", "applied"]
    assert result[0].error == "permission denied"
    assert written == [second_path]
    assert genre_tag_apply_summary(result) == "applied=1 skipped=0 failed=1 total=2"
    assert "Genre tag apply failed" in caplog.text
    assert "Genre tag apply finished applied=1 skipped=0 failed=1 total=2" in caplog.text


def test_genre_tags_apply_api_returns_per_track_status(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"fake audio")
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})
    db.save_genres(track_id, [{"label": "House", "score": 0.9}], model_name="maest")
    monkeypatch.setattr(tags, "_write_genre_tag", lambda path, genre: None)

    response = TestClient(create_app(db_path)).post("/api/tags/genres/apply", json={"track_ids": [track_id]})

    assert response.status_code == 200
    payload = response.json()
    assert payload == [
        {
            "track_id": track_id,
            "path": audio_path.as_posix(),
            "tags": {"GENRE": "House"},
            "status": "applied",
            "message": "Genre tag written",
            "error": None,
        }
    ]


def test_genre_tags_apply_api_can_apply_all_maest_tracks(monkeypatch, tmp_path: Path) -> None:
    first_path = tmp_path / "first.flac"
    second_path = tmp_path / "second.flac"
    third_path = tmp_path / "third.flac"
    for path in (first_path, second_path, third_path):
        path.write_bytes(b"fake audio")
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    first_id = db.upsert_track(path=first_path, size=first_path.stat().st_size, mtime=1, metadata={"title": "First"})
    second_id = db.upsert_track(path=second_path, size=second_path.stat().st_size, mtime=1, metadata={"title": "Second"})
    db.upsert_track(path=third_path, size=third_path.stat().st_size, mtime=1, metadata={"title": "Third"})
    db.save_genres(first_id, [{"label": "House", "score": 0.9}], model_name="maest")
    db.save_genres(second_id, [{"label": "Techno", "score": 0.8}], model_name="maest")
    written: list[Path] = []
    monkeypatch.setattr(tags, "_write_genre_tag", lambda path, genre: written.append(path))

    response = TestClient(create_app(db_path)).post("/api/tags/genres/apply", json={})

    assert response.status_code == 200
    payload = response.json()
    assert [item["track_id"] for item in payload] == [first_id, second_id]
    assert [item["status"] for item in payload] == ["applied", "applied"]
    assert written == [first_path, second_path]


def test_genre_tag_job_processes_all_maest_tracks_without_page_ids(monkeypatch, tmp_path: Path) -> None:
    first_path = tmp_path / "first.flac"
    second_path = tmp_path / "second.flac"
    third_path = tmp_path / "third.flac"
    for path in (first_path, second_path, third_path):
        path.write_bytes(b"fake audio")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first_id = db.upsert_track(path=first_path, size=first_path.stat().st_size, mtime=1, metadata={"title": "First"})
    second_id = db.upsert_track(path=second_path, size=second_path.stat().st_size, mtime=1, metadata={"title": "Second"})
    db.upsert_track(path=third_path, size=third_path.stat().st_size, mtime=1, metadata={"title": "Third"})
    db.save_genres(first_id, [{"label": "House", "score": 0.9}], model_name="maest")
    db.save_genres(second_id, [{"label": "Techno", "score": 0.8}], model_name="maest")
    written: list[Path] = []
    monkeypatch.setattr(tags, "_write_genre_tag", lambda path, genre: written.append(path))

    result = GenreTagJobManager(db).run_sync()

    assert result.state == "completed"
    assert result.total == 2
    assert result.processed == 2
    assert result.applied == 2
    assert result.skipped == 0
    assert result.failed == 0
    assert written == [first_path, second_path]
    assert [event.message for event in result.events] == [
        "Genre tag apply queued",
        "Genre tag apply started",
        "Genre tag written",
        "Genre tag written",
        "Genre tag apply completed",
    ]


def test_genre_tag_job_api_returns_job_status(monkeypatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"fake audio")
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})
    db.save_genres(track_id, [{"label": "House", "score": 0.9}], model_name="maest")
    monkeypatch.setattr(tags, "_write_genre_tag", lambda path, genre: None)

    client = TestClient(create_app(db_path))
    response = client.post("/api/tags/genres/jobs", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"]
    assert payload["total"] == 1
    assert payload["state"] in {"queued", "running", "completed"}


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
    audio_payload_before = _wave_chunk_payload(audio_path)

    tags._write_genre_tag(audio_path, "Tech House; Minimal")
    size_after_first_write = audio_path.stat().st_size
    tags._write_genre_tag(audio_path, "Tech House; Minimal")

    saved = MutagenFile(audio_path)
    assert saved.tags["TCON"].text == ["Tech House; Minimal"]
    assert audio_path.stat().st_size == size_after_first_write
    assert _riff_size_delta(audio_path) == 0
    assert _wave_chunk_payload(audio_path) == audio_payload_before
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
    audio_payload_before = _wave_chunk_payload(audio_path)

    tags._write_genre_tag(audio_path, "Tech House; Minimal; Techno")

    saved = MutagenFile(audio_path)
    assert saved.tags["TCON"].text == ["Tech House; Minimal; Techno"]
    assert saved.tags["TPE1"].text == ["Existing Artist"]
    assert saved.tags["TIT2"].text == ["Existing Title"]
    assert _riff_size_delta(audio_path) == 0
    assert _wave_chunk_payload(audio_path) == audio_payload_before
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
    assert [preview.status for preview in previews] == ["skipped", "applied"]
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
    audio_payload_before = bytes(data[data_offset + 8 :])
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
    assert _riff_size_delta(audio_path) == 0
    assert _wave_chunk_payload(audio_path) == audio_payload_before


def test_apply_genre_tags_repairs_wave_with_data_chunk_two_bytes_too_long(tmp_path: Path) -> None:
    audio_path = tmp_path / "shifted-id3.wav"
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)
    audio = MutagenFile(audio_path)
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=["Existing Title"]))
    audio.save()
    audio_payload_before = _wave_chunk_payload(audio_path)

    data = bytearray(audio_path.read_bytes())
    data_offset = data.index(b"data")
    data_size_offset = data_offset + 4
    riff_size_offset = 4
    data[data_size_offset : data_size_offset + 4] = (int.from_bytes(data[data_size_offset : data_size_offset + 4], "little") + 2).to_bytes(4, "little")
    data[riff_size_offset : riff_size_offset + 4] = (int.from_bytes(data[riff_size_offset : riff_size_offset + 4], "little") + 2).to_bytes(4, "little")
    audio_path.write_bytes(data)

    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=audio_path,
        size=audio_path.stat().st_size,
        mtime=audio_path.stat().st_mtime,
        metadata={"title": "Existing Title"},
    )
    db.save_genres(track_id, [{"label": "Electronic---Minimal Techno", "score": 0.8}], model_name="maest")

    apply_genre_tags(db, [track_id])

    saved = MutagenFile(audio_path)
    track = db.get_track(track_id)
    repaired = audio_path.read_bytes()
    assert int.from_bytes(repaired[4:8], "little") == len(repaired) - 8
    assert _riff_size_delta(audio_path) == 0
    assert _wave_chunk_payload(audio_path) == audio_payload_before
    assert saved.tags["TCON"].text == ["Minimal Techno"]
    assert saved.tags["TIT2"].text == ["Existing Title"]
    assert track.metadata["genre"] == "Minimal Techno"


def test_write_genre_tag_removes_duplicate_wave_id3_chunks_without_touching_audio(tmp_path: Path) -> None:
    audio_path = tmp_path / "duplicate-id3.wav"
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)
    audio = MutagenFile(audio_path)
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=["Existing Title"]))
    audio.tags.add(TCON(encoding=3, text=["Old Genre"]))
    audio.save()
    audio_payload_before = _wave_chunk_payload(audio_path)

    before_duplicate = audio_path.read_bytes()
    id3_start, id3_end = _wave_chunk_spans(audio_path, b"id3 ")[-1]
    duplicate = before_duplicate[id3_start:id3_end]
    data = bytearray(before_duplicate)
    data.extend(duplicate)
    data[4:8] = (len(data) - 8).to_bytes(4, "little")
    audio_path.write_bytes(data)
    assert len(_wave_chunk_spans(audio_path, b"id3 ")) == 2
    assert audio_path.read_bytes().count(b"TCON") == 2

    tags._write_genre_tag(audio_path, "Tech House; Minimal")

    saved = MutagenFile(audio_path)
    repaired = audio_path.read_bytes()
    assert _riff_size_delta(audio_path) == 0
    assert _wave_chunk_payload(audio_path) == audio_payload_before
    assert len(_wave_chunk_spans(audio_path, b"id3 ")) == 1
    assert repaired.count(b"TCON") == 1
    assert saved.tags["TCON"].text == ["Tech House; Minimal"]
    assert saved.tags["TIT2"].text == ["Existing Title"]


@pytest.mark.parametrize("old_genres", [[], ["Old Genre"], ["One", "Two", "Three", "Four", "Five"]])
def test_write_genre_tag_upserts_wave_genre_field_without_touching_audio(tmp_path: Path, old_genres: list[str]) -> None:
    audio_path = tmp_path / "track.wav"
    with wave.open(str(audio_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(44_100)
        handle.writeframes(b"\x00\x00" * 44_100)
    audio = MutagenFile(audio_path)
    if old_genres:
        audio.add_tags()
        audio.tags.add(TIT2(encoding=3, text=["Existing Title"]))
        audio.tags.add(TCON(encoding=3, text=old_genres))
        audio.save()
    audio_payload_before = _wave_chunk_payload(audio_path)

    tags._write_genre_tag(audio_path, "Tech House; Minimal")
    size_after_first_write = audio_path.stat().st_size
    tags._write_genre_tag(audio_path, "Tech House; Minimal")

    saved = MutagenFile(audio_path)
    assert saved.tags["TCON"].text == ["Tech House; Minimal"]
    assert audio_path.stat().st_size == size_after_first_write
    assert _riff_size_delta(audio_path) == 0
    assert _wave_chunk_payload(audio_path) == audio_payload_before
    assert len(_wave_chunk_spans(audio_path, b"id3 ")) == 1
    assert audio_path.read_bytes().count(b"TCON") == 1


@pytest.mark.parametrize("old_genres", [[], ["One", "Two", "Three", "Four", "Five"]])
def test_write_genre_tag_upserts_mp3_genre_field_without_touching_audio(tmp_path: Path, old_genres: list[str]) -> None:
    audio_path = tmp_path / "track.mp3"
    _make_tone(audio_path, ["-codec:a", "libmp3lame", "-q:a", "4"])
    old_tags = ID3(audio_path)
    old_tags.add(TIT2(encoding=3, text=["Existing Title"]))
    if old_genres:
        old_tags.add(TCON(encoding=3, text=old_genres))
    old_tags.save(audio_path)
    audio_md5_before = _decoded_audio_md5(audio_path)

    tags._write_genre_tag(audio_path, "Tech House; Minimal")
    size_after_first_write = audio_path.stat().st_size
    tags._write_genre_tag(audio_path, "Tech House; Minimal")

    saved = ID3(audio_path)
    assert saved["TCON"].text == ["Tech House; Minimal"]
    assert saved["TIT2"].text == ["Existing Title"]
    assert audio_path.stat().st_size == size_after_first_write
    assert _decoded_audio_md5(audio_path) == audio_md5_before


@pytest.mark.parametrize(
    ("suffix", "codec_args", "old_key", "expected_getter"),
    [
        (".flac", ["-codec:a", "flac"], "GENRE", lambda audio: audio.get("GENRE")),
        (".m4a", ["-codec:a", "aac", "-b:a", "128k"], "\xa9gen", lambda audio: audio.get("\xa9gen")),
    ],
)
@pytest.mark.parametrize("old_genres", [[], ["One", "Two", "Three", "Four", "Five"]])
def test_write_genre_tag_upserts_vorbis_and_mp4_genre_fields_without_touching_audio(
    tmp_path: Path,
    suffix: str,
    codec_args: list[str],
    old_key: str,
    expected_getter: Callable[[object], list[str] | None],
    old_genres: list[str],
) -> None:
    audio_path = tmp_path / f"track{suffix}"
    _make_tone(audio_path, codec_args)
    audio = MutagenFile(audio_path)
    if old_genres:
        audio[old_key] = old_genres
    audio.save()
    audio_md5_before = _decoded_audio_md5(audio_path)

    tags._write_genre_tag(audio_path, "Tech House; Minimal")
    size_after_first_write = audio_path.stat().st_size
    tags._write_genre_tag(audio_path, "Tech House; Minimal")

    saved = MutagenFile(audio_path)
    assert expected_getter(saved) == ["Tech House; Minimal"]
    assert audio_path.stat().st_size == size_after_first_write
    assert _decoded_audio_md5(audio_path) == audio_md5_before


@pytest.mark.parametrize("old_genres", [[], ["One", "Two", "Three", "Four", "Five"]])
def test_write_genre_tag_upserts_aiff_genre_field_without_touching_audio(tmp_path: Path, old_genres: list[str]) -> None:
    audio_path = tmp_path / "track.aiff"
    _make_tone(audio_path, ["-codec:a", "pcm_s16be"])
    audio = MutagenFile(audio_path)
    audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=["Existing Title"]))
    if old_genres:
        audio.tags.add(TCON(encoding=3, text=old_genres))
    audio.save()
    audio_md5_before = _decoded_audio_md5(audio_path)

    tags._write_genre_tag(audio_path, "Tech House; Minimal")
    size_after_first_write = audio_path.stat().st_size
    tags._write_genre_tag(audio_path, "Tech House; Minimal")

    saved = MutagenFile(audio_path)
    assert saved.tags["TCON"].text == ["Tech House; Minimal"]
    assert saved.tags["TIT2"].text == ["Existing Title"]
    assert audio_path.stat().st_size == size_after_first_write
    assert _decoded_audio_md5(audio_path) == audio_md5_before


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
    assert track.genres == ["Tech House"]
