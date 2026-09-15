from collections.abc import Callable
from pathlib import Path
import hashlib
import shutil
import subprocess
import wave

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.analysis.model_runners import MaestModelRunner
from dj_track_similarity.analysis_models import (
    AnalysisTarget,
    MaestGenreScore,
    MaestWrite,
)
from dj_track_similarity import tags
from dj_track_similarity.api.application import create_app
from dj_track_similarity.tags import (
    GenreTagJobManager,
    apply_genre_tags_to_tracks,
)
from fastapi.testclient import TestClient
from mutagen import File as MutagenFile
from mutagen.id3 import ID3, TCON, TIT2, TPE1
from dj_track_similarity.track_models import FileTags, ScannedFile, TrackIdentity


_ANALYZED_AT = "2026-07-24T00:00:00.000000Z"


def _scan_track(
    database: LibraryDatabase,
    path: Path,
    *,
    title: str,
    artist: str | None = None,
    album: str | None = None,
    tag_bpm: float | None = None,
    tag_key: str | None = None,
    genres: tuple[str, ...] = (),
) -> TrackIdentity:
    stat = path.stat()
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format=path.suffix.lstrip(".") or None,
        ),
        tags=FileTags(
            title=title,
            artist=artist,
            album=album,
            tag_bpm=tag_bpm,
            tag_key=tag_key,
            genres=genres,
        ),
        scanned_at=_ANALYZED_AT,
    ).identity


def _save_maest_genres(
    database: LibraryDatabase,
    identity: TrackIdentity,
    *labels: str,
) -> None:
    output = MaestModelRunner(
        device="cpu",
        top_k=5,
        inference_batch_size=1,
    ).active_outputs[0]
    database.register_analysis_outputs((output,))
    target = AnalysisTarget(
        catalog_uuid=identity.catalog_uuid,
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
    )
    result = database.save_maest_results(
        (
            MaestWrite(
                target=target,
                genres=tuple(
                    MaestGenreScore(label=label, score=0.9) for label in labels
                ),
                syncopated_rhythm=None,
                analyzed_at=_ANALYZED_AT,
            ),
        )
    )[0]
    assert result.ok, result.error


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


def test_genre_tags_apply_api_rejects_specific_track_ids(
    monkeypatch, tmp_path: Path
) -> None:
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"fake audio")
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    identity = _scan_track(db, audio_path, title="Track")
    _save_maest_genres(db, identity, "House")
    written: list[Path] = []
    monkeypatch.setattr(
        tags, "_write_genre_tag", lambda path, genre: written.append(path)
    )

    response = TestClient(create_app(db_path)).post(
        "/api/tags/genres/apply", json={"track_ids": [identity.track_id]}
    )

    assert response.status_code == 422
    assert written == []


def test_genre_tag_job_api_rejects_specific_track_ids(
    monkeypatch, tmp_path: Path
) -> None:
    audio_path = tmp_path / "track.flac"
    audio_path.write_bytes(b"fake audio")
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    identity = _scan_track(db, audio_path, title="Track")
    _save_maest_genres(db, identity, "House")
    written: list[Path] = []
    monkeypatch.setattr(
        tags, "_write_genre_tag", lambda path, genre: written.append(path)
    )

    response = TestClient(create_app(db_path)).post(
        "/api/tags/genres/jobs", json={"track_ids": [identity.track_id]}
    )

    assert response.status_code == 422
    assert written == []


def test_genre_tags_apply_api_can_apply_all_maest_tracks(
    monkeypatch, tmp_path: Path
) -> None:
    first_path = tmp_path / "first.flac"
    second_path = tmp_path / "second.flac"
    third_path = tmp_path / "third.flac"
    for path in (first_path, second_path, third_path):
        path.write_bytes(b"fake audio")
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    first = _scan_track(db, first_path, title="First")
    second = _scan_track(db, second_path, title="Second")
    _scan_track(db, third_path, title="Third")
    _save_maest_genres(db, first, "House")
    _save_maest_genres(db, second, "Techno")
    written: list[Path] = []
    monkeypatch.setattr(
        tags, "_write_genre_tag", lambda path, genre: written.append(path)
    )
    monkeypatch.setattr(
        tags,
        "_read_file_tags",
        lambda path: FileTags(
            genres=("Techno",) if path == second_path else ("House",)
        ),
    )

    response = TestClient(create_app(db_path)).post("/api/tags/genres/apply", json={})

    assert response.status_code == 200
    payload = response.json()
    assert [item["track_id"] for item in payload] == [first.track_id, second.track_id]
    assert [item["status"] for item in payload] == ["applied", "applied"]
    assert written == [first_path, second_path]


def test_genre_tag_job_processes_all_maest_tracks_without_page_ids(
    monkeypatch, tmp_path: Path
) -> None:
    first_path = tmp_path / "first.flac"
    second_path = tmp_path / "second.flac"
    third_path = tmp_path / "third.flac"
    for path in (first_path, second_path, third_path):
        path.write_bytes(b"fake audio")
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first = _scan_track(db, first_path, title="First")
    second = _scan_track(db, second_path, title="Second")
    _scan_track(db, third_path, title="Third")
    _save_maest_genres(db, first, "House")
    _save_maest_genres(db, second, "Techno")
    written: list[Path] = []
    monkeypatch.setattr(
        tags, "_write_genre_tag", lambda path, genre: written.append(path)
    )
    monkeypatch.setattr(
        tags,
        "_read_file_tags",
        lambda path: FileTags(
            genres=("Techno",) if path == second_path else ("House",)
        ),
    )

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
    identity = _scan_track(db, audio_path, title="Track")
    _save_maest_genres(db, identity, "House")
    monkeypatch.setattr(tags, "_write_genre_tag", lambda path, genre: None)
    monkeypatch.setattr(
        tags, "_read_file_tags", lambda _path: FileTags(genres=("House",))
    )

    client = TestClient(create_app(db_path))
    response = client.post("/api/tags/genres/jobs", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"]
    assert payload["total"] == 1
    assert payload["state"] in {"queued", "running", "completed"}


def test_write_genre_tag_persists_to_wave_and_preserves_existing_id3_tags(
    tmp_path: Path,
) -> None:
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


def test_write_genre_tag_allows_mutagen_readable_wave_with_trailing_padding(
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "padded.wav"
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
    data.extend(b"\x00")
    data[4:8] = (len(data) - 8).to_bytes(4, "little")
    audio_path.write_bytes(data)
    assert MutagenFile(audio_path) is not None

    tags._write_genre_tag(audio_path, "Tech House; Minimal")

    saved = MutagenFile(audio_path)
    assert saved.tags["TCON"].text == ["Tech House; Minimal"]
    assert _wave_chunk_payload(audio_path) == audio_payload_before


def test_write_genre_tag_fails_invalid_wave_without_rewriting(tmp_path: Path) -> None:
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

    with pytest.raises(Exception):
        tags._write_genre_tag(audio_path, "Tech House; Minimal; Techno")

    assert audio_path.read_bytes() == before


def test_apply_genre_tags_reports_failed_invalid_wave_and_continues(
    tmp_path: Path, caplog
) -> None:
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
    malformed = _scan_track(db, malformed_path, title="Malformed")
    valid = _scan_track(db, valid_path, title="Valid")
    _save_maest_genres(db, malformed, "Tech House")
    _save_maest_genres(db, valid, "Minimal")

    with caplog.at_level("ERROR", logger="dj_track_similarity.tags"):
        previews = apply_genre_tags_to_tracks(
            db,
            db.list_genre_tag_candidates(),
        )

    assert malformed_path.read_bytes() == malformed_before
    assert MutagenFile(valid_path).tags["TCON"].text == ["Minimal"]
    assert [preview.track_id for preview in previews] == [
        malformed.track_id,
        valid.track_id,
    ]
    assert [preview.status for preview in previews] == ["failed", "applied"]
    assert previews[0].message == "Genre tag write failed"
    assert previews[0].error
    assert "Genre tag apply failed" in caplog.text


@pytest.mark.parametrize(
    "old_genres", [[], ["Old Genre"], ["One", "Two", "Three", "Four", "Five"]]
)
def test_write_genre_tag_upserts_wave_genre_field_without_touching_audio(
    tmp_path: Path, old_genres: list[str]
) -> None:
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
def test_write_genre_tag_upserts_mp3_genre_field_without_touching_audio(
    tmp_path: Path, old_genres: list[str]
) -> None:
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
        (
            ".m4a",
            ["-codec:a", "aac", "-b:a", "128k"],
            "\xa9gen",
            lambda audio: audio.get("\xa9gen"),
        ),
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
def test_write_genre_tag_upserts_aiff_genre_field_without_touching_audio(
    tmp_path: Path, old_genres: list[str]
) -> None:
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
