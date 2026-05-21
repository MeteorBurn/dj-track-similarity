from __future__ import annotations

from pathlib import Path

from mutagen.id3 import TCON
from mutagen.wave import WAVE


def write_wave_genre_tag(path: Path, genre_text: str) -> None:
    audio = WAVE(path)
    info = getattr(audio, "info", None)
    length = getattr(info, "length", None)
    if length is not None and length <= 0:
        raise ValueError(f"Unsupported WAV file without readable audio data: {path}")
    set_audio_id3_genre(audio, genre_text)
    audio.save()
    verify_wave_genre_tag(path, genre_text)


def set_audio_id3_genre(audio: object, genre_text: str) -> None:
    if not hasattr(audio, "tags") or audio.tags is None:
        audio.add_tags()
    if audio.tags is None:
        raise RuntimeError("Unable to create or access ID3 tags")
    if "TCON" in audio.tags:
        del audio.tags["TCON"]
    audio.tags.add(TCON(encoding=3, text=[genre_text]))


def verify_wave_genre_tag(path: Path, genre_text: str) -> None:
    audio = WAVE(path)
    if audio.tags is None or "TCON" not in audio.tags:
        raise RuntimeError(f"Genre tag was not readable after WAV save: {path}")
    if list(audio.tags["TCON"].text) != [genre_text]:
        raise RuntimeError(f"Genre tag readback mismatch after WAV save: {path}")
