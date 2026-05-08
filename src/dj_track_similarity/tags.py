from __future__ import annotations

import logging
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TCON, TXXX
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

from .database import LibraryDatabase
from .logging_config import exception_summary
from .models import TagPreview, Track
from .scanner import MUTAGEN_METADATA_KEYS, read_audio_metadata


CUSTOM_TAG_PREFIX = "DJ_SIM"
LOGGER = logging.getLogger(__name__)


def build_tag_preview(db: LibraryDatabase, track_ids: list[int]) -> list[TagPreview]:
    return [TagPreview(track_id=track.id, path=track.path, tags=_custom_tags_for_track(track)) for track in _tracks(db, track_ids)]


def apply_custom_tags(db: LibraryDatabase, track_ids: list[int]) -> list[TagPreview]:
    previews = build_tag_preview(db, track_ids)
    for preview in previews:
        try:
            _write_tags(Path(preview.path), preview.tags)
            LOGGER.info("Custom tags applied track_id=%s path=%s keys=%s", preview.track_id, preview.path, sorted(preview.tags))
        except Exception as error:
            LOGGER.exception(
                "Custom tag apply failed track_id=%s path=%s error=%s",
                preview.track_id,
                preview.path,
                exception_summary(error),
            )
            raise
    return previews


def build_genre_tag_preview(db: LibraryDatabase, track_ids: list[int]) -> list[TagPreview]:
    return [TagPreview(track_id=track.id, path=track.path, tags=_genre_tags_for_track(track)) for track in _tracks(db, track_ids)]


def apply_genre_tags(db: LibraryDatabase, track_ids: list[int]) -> list[TagPreview]:
    previews = build_genre_tag_preview(db, track_ids)
    for preview in previews:
        if preview.tags:
            path = Path(preview.path)
            if _should_skip_genre_tag_write(path):
                LOGGER.warning(
                    "Skipping genre tag write for unsupported WAV container track_id=%s path=%s",
                    preview.track_id,
                    preview.path,
                )
                continue
            try:
                _write_genre_tag(path, list(preview.tags.values())[0])
                db.refresh_track_file_metadata(
                    preview.track_id,
                    size=path.stat().st_size,
                    mtime=path.stat().st_mtime,
                    metadata=read_audio_metadata(path),
                    replace_metadata_keys=MUTAGEN_METADATA_KEYS,
                )
                LOGGER.info("Genre tags applied track_id=%s path=%s tags=%s", preview.track_id, preview.path, preview.tags)
            except Exception as error:
                LOGGER.exception(
                    "Genre tag apply failed track_id=%s path=%s error=%s",
                    preview.track_id,
                    preview.path,
                    exception_summary(error),
                )
                raise
    return previews


def _should_skip_genre_tag_write(path: Path) -> bool:
    if path.suffix.lower() not in {".wav", ".wave"}:
        return False
    try:
        _validate_wave_container(path)
    except ValueError:
        return True
    return False


def _tracks(db: LibraryDatabase, track_ids: list[int]) -> list[Track]:
    return [db.get_track(track_id) for track_id in track_ids]


def _custom_tags_for_track(track: Track) -> dict[str, str]:
    tags: dict[str, str] = {}
    if track.bpm is not None:
        tags[f"{CUSTOM_TAG_PREFIX}_BPM"] = f"{track.bpm:.1f}"
    if track.musical_key:
        tags[f"{CUSTOM_TAG_PREFIX}_KEY"] = track.musical_key
    if track.energy is not None:
        tags[f"{CUSTOM_TAG_PREFIX}_ENERGY"] = f"{track.energy:.3f}"
    if track.embedding_model:
        tags[f"{CUSTOM_TAG_PREFIX}_EMBEDDING_MODEL"] = track.embedding_model
    return tags


def _genre_tags_for_track(track: Track) -> dict[str, str]:
    if not track.genres:
        return {}
    genres = [_clean_genre_label(genre) for genre in track.genres]
    genres = [genre for genre in genres if genre]
    return {"GENRE": "; ".join(genres)} if genres else {}


def _clean_genre_label(genre: str) -> str:
    text = str(genre).replace("_", " ").strip()
    if "---" in text:
        text = text.rsplit("---", 1)[-1].strip()
    return text


def _write_tags(path: Path, tags: dict[str, str]) -> None:
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        id3 = ID3(path) if path.exists() else ID3()
        for key, value in tags.items():
            id3.delall(f"TXXX:{key}")
            id3.add(TXXX(encoding=3, desc=key, text=value))
        id3.save(path)
        return

    audio = MutagenFile(path)
    if audio is None:
        raise ValueError(f"Unsupported audio tag format: {path}")
    if audio.tags is None:
        audio.add_tags()
    for key, value in tags.items():
        audio.tags[key] = [value]
    audio.save()


def _write_genre_tag(path: Path, genre: str) -> None:
    values = [part.strip() for part in genre.split(";") if part.strip()]
    if not values:
        return
    genre_text = "; ".join(values)
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        id3 = _load_id3(path)
        _set_id3_genre(id3, genre_text)
        id3.save(path, v2_version=3)
        return

    if suffix in {".wav", ".wave"}:
        _validate_wave_container(path)
        _repair_oversized_wave_data_chunk(path)
        audio = WAVE(path)
        _set_audio_id3_genre(audio, genre_text)
        audio.save()
        _validate_wave_container(path)
        return

    audio = MutagenFile(path)
    if audio is None:
        raise ValueError(f"Unsupported audio tag format: {path}")
    if isinstance(audio, MP4) or suffix in {".m4a", ".mp4", ".alac"}:
        audio["\xa9gen"] = [genre_text]
    elif isinstance(audio, FLAC):
        audio["GENRE"] = genre_text
    elif isinstance(audio, (WAVE, AIFF)) or suffix in {".aif", ".aiff", ".dsf", ".dff"}:
        _set_audio_id3_genre(audio, genre_text)
    else:
        if not hasattr(audio, "tags") or audio.tags is None:
            audio.add_tags()
        if hasattr(audio.tags, "add"):
            _set_audio_id3_genre(audio, genre_text)
        else:
            audio["Genre"] = genre_text
    audio.save()


def _set_id3_genre(tags: object, genre_text: str) -> None:
    tags.delall("TCON")
    tags.add(TCON(encoding=3, text=[genre_text]))


def _load_id3(path: Path) -> ID3:
    try:
        return ID3(path)
    except ID3NoHeaderError:
        return ID3()


def _set_audio_id3_genre(audio: object, genre_text: str) -> None:
    if not hasattr(audio, "tags") or audio.tags is None:
        audio.add_tags()
    if audio.tags is None:
        raise RuntimeError("Unable to create or access ID3 tags")
    if "TCON" in audio.tags:
        del audio.tags["TCON"]
    audio.tags.add(TCON(encoding=3, text=[genre_text]))


def _validate_wave_container(path: Path) -> None:
    data = path.read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"Unsupported WAV file: {path}")
    if _find_wave_data_chunk_start(data) is None:
        raise ValueError(f"Unsupported WAV file without readable data chunk: {path}")


def _repair_oversized_wave_data_chunk(path: Path) -> None:
    data = bytearray(path.read_bytes())
    bounds = _find_wave_data_chunk_bounds(data)
    if bounds is None:
        return
    data_start, declared_size = bounds
    actual_size = len(data) - data_start
    if declared_size <= actual_size:
        return
    chunk_size_offset = data_start - 4
    data[chunk_size_offset : chunk_size_offset + 4] = actual_size.to_bytes(4, "little")
    data[4:8] = (len(data) - 8).to_bytes(4, "little")
    path.write_bytes(data)
    LOGGER.warning("Repaired oversized WAV data chunk before tag write path=%s", path)


def _find_wave_data_chunk_bounds(data: bytes) -> tuple[int, int] | None:
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        chunk_size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        if chunk_id == b"data":
            return pos + 8, chunk_size
        chunk_end = pos + 8 + chunk_size + (chunk_size % 2)
        if chunk_end <= pos or chunk_end > len(data):
            return None
        pos = chunk_end
    return None


def _find_wave_data_chunk_start(data: bytes) -> int | None:
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        chunk_size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        if chunk_id == b"data":
            return pos
        chunk_end = pos + 8 + chunk_size + (chunk_size % 2)
        if chunk_end <= pos or chunk_end > len(data):
            return None
        pos = chunk_end
    return None
