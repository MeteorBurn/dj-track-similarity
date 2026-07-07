from __future__ import annotations

from pathlib import Path
from typing import Protocol

from mutagen.id3 import Frame, TCON
from mutagen.wave import WAVE


class _Id3Tags(Protocol):
    def __contains__(self, key: str) -> bool: ...

    def __getitem__(self, key: str) -> "_TextFrame": ...

    def __delitem__(self, key: str) -> None: ...

    def add(self, frame: Frame) -> None: ...


class _TextFrame(Protocol):
    text: list[str]


class _AudioWithId3Tags(Protocol):
    @property
    def tags(self) -> _Id3Tags | None: ...

    def add_tags(self) -> None: ...


class _WaveAudio(_AudioWithId3Tags, Protocol):
    def save(self) -> None: ...


def write_wave_genre_tag(path: Path, genre_text: str) -> None:
    audio: _WaveAudio = WAVE(path)
    _require_readable_wave_audio(audio, path)
    set_audio_id3_genre(audio, genre_text)
    _save_wave_audio(audio)
    verify_wave_genre_tag(path, genre_text)


def set_audio_id3_genre(audio: _AudioWithId3Tags, genre_text: str) -> None:
    if not hasattr(audio, "tags") or audio.tags is None:
        audio.add_tags()
    if audio.tags is None:
        raise RuntimeError("Unable to create or access ID3 tags")
    _replace_id3_genre(audio.tags, genre_text)


def _require_readable_wave_audio(audio: object, path: Path) -> None:
    info = getattr(audio, "info", None)
    length = getattr(info, "length", None)
    if length is not None and length <= 0:
        raise ValueError(f"Unsupported WAV file without readable audio data: {path}")


def _replace_id3_genre(tags: _Id3Tags, genre_text: str) -> None:
    if "TCON" in tags:
        del tags["TCON"]
    tags.add(TCON(encoding=3, text=[genre_text]))


def _save_wave_audio(audio: _WaveAudio) -> None:
    audio.save()


def _genre_frame_text(tags: _Id3Tags) -> list[str]:
    return list(tags["TCON"].text)


def verify_wave_genre_tag(path: Path, genre_text: str) -> None:
    audio: _AudioWithId3Tags = WAVE(path)
    tags = audio.tags
    if tags is None or "TCON" not in tags:
        raise RuntimeError(f"Genre tag was not readable after WAV save: {path}")
    if _genre_frame_text(tags) != [genre_text]:
        raise RuntimeError(f"Genre tag readback mismatch after WAV save: {path}")
