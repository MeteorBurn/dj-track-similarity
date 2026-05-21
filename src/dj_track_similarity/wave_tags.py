from __future__ import annotations

from pathlib import Path

from mutagen.id3 import TCON
from mutagen.wave import WAVE


WAVE_ID3_CHUNK_IDS = {b"id3 ", b"ID3 "}


def should_skip_wave_genre_tag_write(path: Path) -> bool:
    if path.suffix.lower() not in {".wav", ".wave"}:
        return False
    try:
        validate_wave_container(path)
    except ValueError:
        return True
    return False


def write_wave_genre_tag(path: Path, genre_text: str) -> None:
    validate_wave_container(path)
    audio = WAVE(path)
    set_audio_id3_genre(audio, genre_text)
    audio.save()
    validate_wave_container(path)
    verify_wave_genre_tag(path, genre_text)


def set_audio_id3_genre(audio: object, genre_text: str) -> None:
    if not hasattr(audio, "tags") or audio.tags is None:
        audio.add_tags()
    if audio.tags is None:
        raise RuntimeError("Unable to create or access ID3 tags")
    if "TCON" in audio.tags:
        del audio.tags["TCON"]
    audio.tags.add(TCON(encoding=3, text=[genre_text]))


def validate_wave_container(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"Unsupported WAV file: {path}")
    expected_riff_size = len(data) - 8
    declared_riff_size = int.from_bytes(data[4:8], "little")
    if declared_riff_size != expected_riff_size:
        raise ValueError(f"Unsupported WAV file with inconsistent RIFF size: {path}")

    has_data_chunk = False
    id3_chunk_count = 0
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        chunk_size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        payload_end = pos + 8 + chunk_size
        chunk_end = payload_end + (chunk_size % 2)
        if chunk_end <= pos or chunk_end > len(data):
            raise ValueError(f"Unsupported WAV file with invalid chunk bounds: {path}")
        if chunk_id == b"data":
            has_data_chunk = True
        if chunk_id in WAVE_ID3_CHUNK_IDS:
            id3_chunk_count += 1
        pos = chunk_end

    if pos != len(data):
        raise ValueError(f"Unsupported WAV file with trailing partial chunk: {path}")
    if not has_data_chunk:
        raise ValueError(f"Unsupported WAV file without readable data chunk: {path}")
    if id3_chunk_count > 1:
        raise ValueError(f"Unsupported WAV file with duplicate ID3 chunks: {path}")


def verify_wave_genre_tag(path: Path, genre_text: str) -> None:
    audio = WAVE(path)
    if audio.tags is None or "TCON" not in audio.tags:
        raise RuntimeError(f"Genre tag was not readable after WAV save: {path}")
    if list(audio.tags["TCON"].text) != [genre_text]:
        raise RuntimeError(f"Genre tag readback mismatch after WAV save: {path}")

