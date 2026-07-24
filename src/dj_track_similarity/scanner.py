"""Audio-file discovery and the canonical v7 scan path."""

from __future__ import annotations

import math
import os
from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterable

from mutagen import File as MutagenFile

from .db_tracks import TrackRepository, canonical_file_path
from .track_models import (
    FileTags,
    ScannedFile,
    ScanStats,
    TrackMutation,
)


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
METADATA_STABILITY_ATTEMPTS = 3
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
    "year": [
        "year",
        "originalyear",
        "date",
        "originaldate",
        "TDRC",
        "TYER",
        "\xa9day",
    ],
    "country": [
        "country",
        "releasecountry",
        "MusicBrainz Album Release Country",
    ],
    "label": ["label", "organization", "publisher", "TPUB"],
    "catalog_number": [
        "catalognumber",
        "catalog",
        "catalog_number",
        "CATALOGNUMBER",
    ],
    "track_number": ["tracknumber", "TRCK", "trkn"],
    "disc_number": ["discnumber", "TPOS", "disk"],
    "bpm": ["bpm", "TBPM"],
    "key": ["initialkey", "key", "TKEY"],
    "comment": ["comment", "description", "COMM", "\xa9cmt"],
    "isrc": ["isrc", "TSRC"],
}


def _resolved_directory(root: str | Path) -> Path:
    root_path = Path(root).expanduser().resolve(strict=False)
    if not root_path.exists():
        raise FileNotFoundError(root_path)
    if not root_path.is_dir():
        raise NotADirectoryError(root_path)
    return root_path


def scan_library(
    repository: TrackRepository,
    root: str | Path,
) -> ScanStats:
    """Scan one root through the sole v7 TrackRepository write path."""

    root_path = _resolved_directory(root)
    stats = ScanStats()
    seen_paths: list[Path] = []
    for path in iter_audio_files(root_path):
        seen_paths.append(path)
        try:
            mutation = scan_audio_file(repository, path)
        except OSError:
            stats = replace(stats, skipped=stats.skipped + 1)
            continue
        if mutation.action == "added":
            stats = replace(stats, added=stats.added + 1)
        elif mutation.action == "updated":
            stats = replace(stats, updated=stats.updated + 1)
        else:
            stats = replace(stats, unchanged=stats.unchanged + 1)
    repository.mark_unseen_missing(root_path, seen_paths)
    return stats


def scan_audio_file(
    repository: TrackRepository,
    path: str | Path,
) -> TrackMutation:
    """Reconcile one audio file using exact nanosecond filesystem facts.

    An unchanged size/mtime pair intentionally skips tag decoding. Tag-only
    edits with unchanged file facts must use the explicit Refresh Tags path.
    """

    audio_path = Path(path).expanduser().resolve(strict=False)
    initial_stat = audio_path.stat()
    existing = repository.get_track_file_state(audio_path)
    if (
        existing is not None
        and existing.file_size_bytes == initial_stat.st_size
        and existing.file_modified_ns == initial_stat.st_mtime_ns
    ):
        return repository.upsert_scanned_track(
            file=ScannedFile(
                file_path=canonical_file_path(audio_path),
                file_size_bytes=initial_stat.st_size,
                file_modified_ns=initial_stat.st_mtime_ns,
            ),
            tags=FileTags(),
        )

    metadata, final_stat = read_audio_metadata_stable(
        audio_path,
        initial_stat=initial_stat,
    )
    return repository.upsert_scanned_track(
        file=scanned_file_from_metadata(
            audio_path,
            metadata,
            file_size_bytes=final_stat.st_size,
            file_modified_ns=final_stat.st_mtime_ns,
        ),
        tags=file_tags_from_metadata(audio_path, metadata),
    )


def read_audio_metadata_stable(
    path: str | Path,
    *,
    initial_stat: os.stat_result | None = None,
    metadata_reader: Callable[[str | Path], dict[str, object]] | None = None,
    max_attempts: int = METADATA_STABILITY_ATTEMPTS,
) -> tuple[dict[str, object], os.stat_result]:
    """Read metadata only from one stable size/mtime snapshot.

    A writer may replace or retag a source file while Mutagen is decoding it.
    Retry from a fresh snapshot when either file fact changes. No caller may
    persist the returned metadata under facts from another attempt.
    """

    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
        raise TypeError("max_attempts must be an integer")
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")
    audio_path = Path(path).expanduser().resolve(strict=False)
    reader = read_audio_metadata if metadata_reader is None else metadata_reader
    before_stat = initial_stat
    for attempt in range(max_attempts):
        if before_stat is None or attempt > 0:
            before_stat = audio_path.stat()
        metadata = reader(audio_path)
        after_stat = audio_path.stat()
        if (
            before_stat.st_size == after_stat.st_size
            and before_stat.st_mtime_ns == after_stat.st_mtime_ns
        ):
            return metadata, after_stat
        before_stat = None
    raise OSError(
        "Audio file changed while metadata was being read "
        f"after {max_attempts} attempts: {audio_path}"
    )


def iter_audio_files(root: Path) -> Iterable[Path]:
    """Yield deterministic absolute audio paths, deduplicated after resolve."""

    root_path = _resolved_directory(root)
    paths_by_identity: dict[str, Path] = {}
    for candidate in root_path.rglob("*"):
        if (
            candidate.is_file()
            and candidate.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS
            and not candidate.name.startswith("._")
        ):
            resolved = candidate.resolve(strict=False)
            paths_by_identity.setdefault(canonical_file_path(resolved), resolved)
    for identity in sorted(paths_by_identity):
        yield paths_by_identity[identity]


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
    duration = _positive_float_or_none(getattr(info, "length", None))
    if duration is not None:
        metadata["duration"] = duration
    sample_rate = _positive_int_or_none(getattr(info, "sample_rate", None))
    if sample_rate is not None:
        metadata["sample_rate_hz"] = sample_rate
    channel_count = _positive_int_or_none(getattr(info, "channels", None))
    if channel_count is not None:
        metadata["channel_count"] = channel_count
    bit_rate = _positive_int_or_none(getattr(info, "bitrate", None))
    if bit_rate is not None:
        metadata["bit_rate_bps"] = bit_rate

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
            if _contains_tag(tags, candidate):
                metadata[target] = _tag_value(tags[candidate])
                break
    return metadata


def scanned_file_from_metadata(
    path: str | Path,
    metadata: dict[str, object],
    *,
    file_size_bytes: int,
    file_modified_ns: int,
) -> ScannedFile:
    return ScannedFile(
        file_path=canonical_file_path(path),
        file_size_bytes=int(file_size_bytes),
        file_modified_ns=int(file_modified_ns),
        audio_format=_string_or_none(metadata.get("audio_format")),
        audio_codec=_string_or_none(metadata.get("audio_codec")),
        sample_rate_hz=_positive_int_or_none(metadata.get("sample_rate_hz")),
        channel_count=_positive_int_or_none(metadata.get("channel_count")),
        bit_rate_bps=_positive_int_or_none(metadata.get("bit_rate_bps")),
        audio_duration_seconds=_positive_float_or_none(
            metadata.get("duration")
        ),
    )


def file_tags_from_metadata(
    path: str | Path,
    metadata: dict[str, object],
) -> FileTags:
    audio_path = Path(path)
    title = _string_or_none(metadata.get("title")) or audio_path.stem
    return FileTags(
        title=title,
        artist=_string_or_none(metadata.get("artist")),
        album=_string_or_none(metadata.get("album")),
        tag_bpm=_positive_float_or_none(metadata.get("bpm")),
        tag_key=_string_or_none(
            metadata.get("key") or metadata.get("initialkey")
        ),
        comment=_string_or_none(metadata.get("comment")),
        year=_year_or_none(metadata.get("year")),
        label=_string_or_none(metadata.get("label")),
        catalog_number=_string_or_none(metadata.get("catalog_number")),
        country=_string_or_none(metadata.get("country")),
        isrc=_string_or_none(metadata.get("isrc")),
        track_number=_string_or_none(metadata.get("track_number")),
        disc_number=_string_or_none(metadata.get("disc_number")),
        genres=_genres(metadata.get("genre")),
    )


def _contains_tag(tags: object, candidate: str) -> bool:
    try:
        return candidate in tags
    except (KeyError, TypeError, ValueError):
        return False


def _tag_value(value: object) -> object:
    text = getattr(value, "text", None)
    if isinstance(text, list) and text:
        return _safe_tag_value(text[0])
    if isinstance(value, list) and value:
        return _safe_tag_value(value[0])
    return _safe_tag_value(value)


def _safe_tag_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").strip()
    if isinstance(value, tuple):
        parts = [
            str(part).strip()
            for part in value
            if part not in (None, "")
        ]
        return "/".join(parts)
    return str(value).strip()


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_float_or_none(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _positive_int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _year_or_none(value: object) -> int | None:
    text = _string_or_none(value)
    if text is None:
        return None
    try:
        year = int(text[:4])
    except ValueError:
        return None
    return year if 1 <= year <= 9999 else None


def _genres(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = (value,)
    genres: list[str] = []
    for item in items:
        text = _string_or_none(item)
        if text is not None:
            genres.append(text)
    return tuple(genres)


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
            text = _string_or_none(value)
            if text:
                return text
    return None
