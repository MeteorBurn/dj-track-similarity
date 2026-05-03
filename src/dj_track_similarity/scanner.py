from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Iterable

from mutagen import File as MutagenFile

from .database import LibraryDatabase
from .models import ScanStats


SUPPORTED_AUDIO_EXTENSIONS = {
    ".aif",
    ".aiff",
    ".alac",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wave",
}


def scan_library(db: LibraryDatabase, root: str | Path) -> ScanStats:
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(root_path)
    if not root_path.is_dir():
        raise NotADirectoryError(root_path)

    stats = ScanStats()
    for path in _iter_audio_files(root_path):
        existing = db.get_track_by_path(path)
        size = path.stat().st_size
        mtime = path.stat().st_mtime
        if existing and existing.size == size and abs(existing.mtime - mtime) < 0.0001:
            stats = replace(stats, unchanged=stats.unchanged + 1)
            continue

        metadata = read_audio_metadata(path)
        db.upsert_track(
            path=path,
            size=size,
            mtime=mtime,
            metadata=metadata,
            bpm=_as_float(metadata.get("bpm")),
            musical_key=_as_string(metadata.get("key") or metadata.get("initialkey")),
            duration=_as_float(metadata.get("duration")),
        )
        if existing:
            stats = replace(stats, updated=stats.updated + 1)
        else:
            stats = replace(stats, added=stats.added + 1)
    return stats


def _iter_audio_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
            yield path


def read_audio_metadata(path: str | Path) -> dict[str, object]:
    audio_path = Path(path)
    metadata: dict[str, object] = {"title": audio_path.stem}
    try:
        audio = MutagenFile(audio_path)
    except Exception:
        return metadata
    if audio is None:
        return metadata

    if getattr(audio, "info", None) and getattr(audio.info, "length", None):
        metadata["duration"] = float(audio.info.length)

    tags = getattr(audio, "tags", None)
    if not tags:
        return metadata

    lookup = {
        "artist": ["artist", "TPE1", "\xa9ART"],
        "title": ["title", "TIT2", "\xa9nam"],
        "album": ["album", "TALB", "\xa9alb"],
        "bpm": ["bpm", "TBPM"],
        "key": ["initialkey", "key", "TKEY"],
    }
    for target, candidates in lookup.items():
        for candidate in candidates:
            if _has_tag(tags, candidate):
                metadata[target] = _tag_value(tags[candidate])
                break
    return metadata


def _has_tag(tags: object, candidate: str) -> bool:
    try:
        return candidate in tags
    except (KeyError, TypeError, ValueError):
        return False


def _tag_value(value: object) -> object:
    text = getattr(value, "text", None)
    if isinstance(text, list) and text:
        return text[0]
    if isinstance(value, list) and value:
        return value[0]
    return value


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
