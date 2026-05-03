from __future__ import annotations

from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.id3 import ID3, TXXX

from .database import LibraryDatabase
from .models import TagPreview, Track


CUSTOM_TAG_PREFIX = "DJ_SIM"


def build_tag_preview(db: LibraryDatabase, track_ids: list[int]) -> list[TagPreview]:
    return [TagPreview(track_id=track.id, path=track.path, tags=_custom_tags_for_track(track)) for track in _tracks(db, track_ids)]


def apply_custom_tags(db: LibraryDatabase, track_ids: list[int]) -> list[TagPreview]:
    previews = build_tag_preview(db, track_ids)
    for preview in previews:
        _write_tags(Path(preview.path), preview.tags)
    return previews


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
