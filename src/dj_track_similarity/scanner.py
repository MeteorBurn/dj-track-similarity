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
DISPLAY_AUDIO_FORMATS = {
    ".aif": "AIFF",
    ".aiff": "AIFF",
    ".alac": "ALAC",
    ".flac": "FLAC",
    ".m4a": "M4A",
    ".mp3": "MP3",
    ".ogg": "Ogg",
    ".opus": "Opus",
    ".wav": "Wave",
    ".wave": "Wave",
}


MUTAGEN_TAG_LOOKUP = {
    "artist": ["artist", "albumartist", "TPE1", "TPE2", "\xa9ART", "aART"],
    "title": ["title", "TIT2", "\xa9nam"],
    "album": ["album", "TALB", "\xa9alb"],
    "genre": ["genre", "TCON", "\xa9gen"],
    "year": ["year", "originalyear", "date", "originaldate", "TDRC", "TYER", "\xa9day"],
    "country": ["country", "releasecountry", "MusicBrainz Album Release Country"],
    "label": ["label", "organization", "publisher", "TPUB"],
    "catalog_number": ["catalognumber", "catalog", "catalog_number", "CATALOGNUMBER"],
    "track_number": ["tracknumber", "TRCK", "trkn"],
    "disc_number": ["discnumber", "TPOS", "disk"],
    "bpm": ["bpm", "TBPM"],
    "key": ["initialkey", "key", "TKEY"],
    "comment": ["comment", "description", "COMM", "\xa9cmt"],
    "isrc": ["isrc", "TSRC"],
}
MUTAGEN_METADATA_KEYS = tuple(MUTAGEN_TAG_LOOKUP.keys()) + ("duration", "audio_format", "audio_codec", "date")


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

    info = getattr(audio, "info", None)
    if info and getattr(info, "length", None):
        metadata["duration"] = float(info.length)
    audio_format = _audio_format(audio, audio_path)
    if audio_format:
        metadata["audio_format"] = audio_format
    audio_codec = _audio_codec(audio, info)
    if audio_codec:
        metadata["audio_codec"] = audio_codec

    tags = getattr(audio, "tags", None)
    if not tags:
        return metadata

    for target, candidates in MUTAGEN_TAG_LOOKUP.items():
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
        return _json_safe_tag_value(text[0])
    if isinstance(value, list) and value:
        return _json_safe_tag_value(value[0])
    return _json_safe_tag_value(value)


def _json_safe_tag_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, tuple):
        parts = [str(part).strip() for part in value if part not in (None, "")]
        return "/".join(parts)
    return str(value).strip()


def _audio_format(audio: object, path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in DISPLAY_AUDIO_FORMATS:
        return DISPLAY_AUDIO_FORMATS[suffix]
    mime = getattr(audio, "mime", None)
    if isinstance(mime, list) and mime:
        return _audio_format_from_mime(str(mime[0]))
    if isinstance(mime, str) and mime.strip():
        return _audio_format_from_mime(mime)
    return None


def _audio_format_from_mime(mime: str) -> str | None:
    cleaned = mime.strip().lower()
    if not cleaned:
        return None
    if cleaned.startswith("audio/"):
        cleaned = cleaned.removeprefix("audio/")
    return DISPLAY_AUDIO_FORMATS.get(f".{cleaned}") or cleaned.upper()


def _audio_codec(audio: object, info: object | None) -> str | None:
    for source in (info, audio):
        if source is None:
            continue
        for attribute in ("codec", "codec_name", "encoder_info", "pprint"):
            value = getattr(source, attribute, None)
            if callable(value):
                try:
                    value = value()
                except Exception:
                    continue
            text = _as_string(value)
            if text:
                return text
    return None


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
