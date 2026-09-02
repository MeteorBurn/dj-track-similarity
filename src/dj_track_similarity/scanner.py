"""Audio-file discovery and the canonical scan path."""

from __future__ import annotations

import io
import logging
import math
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Collection, Iterator

from mutagen import File as MutagenFile
from mutagen.aac import AAC
from mutagen.aiff import AIFFFile, AIFFInfo
from mutagen.asf import ASF
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.monkeysaudio import MonkeysAudio
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Chapters
from mutagen.oggflac import OggFLAC
from mutagen.oggopus import OggOpus
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE
from mutagen.wavpack import WavPack

from .db_tracks import (
    TrackRepository,
    ordinal_path_key,
    resolved_file_path,
)
from .ffmpeg_runtime import load_project_pyav
from .track_models import (
    FileTags,
    ScannedFile,
    ScanStats,
    TrackMutation,
)


SUPPORTED_AUDIO_EXTENSIONS = {
    ".aac",
    ".aif",
    ".aiff",
    ".alac",
    ".ape",
    ".flac",
    ".m4a",
    ".mp3",
    ".ogg",
    ".opus",
    ".wav",
    ".wave",
    ".wma",
    ".wv",
}
METADATA_STABILITY_ATTEMPTS = 3
DISPLAY_AUDIO_FORMATS = {
    ".aac": "AAC",
    ".aif": "AIFF",
    ".aiff": "AIFF",
    ".alac": "ALAC",
    ".ape": "APE",
    ".flac": "FLAC",
    ".m4a": "M4A",
    ".mp3": "MP3",
    ".ogg": "Ogg",
    ".opus": "Opus",
    ".wav": "Wave",
    ".wave": "Wave",
    ".wma": "WMA",
    ".wv": "WavPack",
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
    "track_number": ["tracknumber", "TRCK", "trkn"],
    "bpm": ["bpm", "TBPM"],
    "key": ["initialkey", "key", "TKEY"],
    "comment": ["comment", "description", "COMM", "\xa9cmt"],
}
LOGGER = logging.getLogger(__name__)
# read_audio_metadata stores a one-line note under this key whenever a file was
# served by anything but the default mutagen open, so a caller in another
# process can surface it where the reader's own log line cannot reach.
READER_NOTE_KEY = "reader_note"


@dataclass(frozen=True)
class PreparedScan:
    """Stable metadata ready for the scan coordinator to write."""

    file: ScannedFile
    tags: FileTags


@dataclass(frozen=True)
class PreparedScanResult:
    """One process-worker result for a source path."""

    path: str
    prepared: PreparedScan | None = None
    error_message: str | None = None
    note: str | None = None
    """Reader note for the coordinator to log; set even when the file was skipped."""


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
    """Scan one root through the sole TrackRepository write path."""

    root_path = _resolved_directory(root)
    repository.record_library_root(root_path)
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
    *,
    min_duration_seconds: int | None = None,
    max_duration_seconds: int | None = None,
    claim_scan_slot: Callable[[], bool] | None = None,
) -> TrackMutation | None:
    """Reconcile one audio file using exact nanosecond filesystem facts.

    An unchanged size/mtime pair intentionally skips tag decoding. Tag-only
    edits with unchanged file facts must use the explicit Refresh Tags path.
    """

    prepared = prepare_audio_file(
        repository,
        path,
        min_duration_seconds=min_duration_seconds,
        max_duration_seconds=max_duration_seconds,
        claim_scan_slot=claim_scan_slot,
    )
    if prepared is None:
        return None
    return repository.upsert_scanned_track(
        file=prepared.file,
        tags=prepared.tags,
    )


def prepare_audio_file(
    repository: TrackRepository,
    path: str | Path,
    *,
    min_duration_seconds: int | None = None,
    max_duration_seconds: int | None = None,
    claim_scan_slot: Callable[[], bool] | None = None,
) -> PreparedScan | None:
    """Read one stable scan record without writing it to the library."""

    audio_path = Path(path).expanduser().resolve(strict=False)
    initial_stat = audio_path.stat()
    existing = repository.get_track_file_state(audio_path)
    duration_filter_active = (
        min_duration_seconds is not None
        or max_duration_seconds is not None
    )
    if (
        existing is not None
        and existing.file_size_bytes == initial_stat.st_size
        and existing.file_modified_ns == initial_stat.st_mtime_ns
        and not duration_filter_active
    ):
        return PreparedScan(
            file=ScannedFile(
                file_path=resolved_file_path(audio_path),
                file_size_bytes=initial_stat.st_size,
                file_modified_ns=initial_stat.st_mtime_ns,
            ),
            tags=FileTags(),
        )

    prepared, note = _prepare_audio_file_metadata_with_note(
        audio_path,
        initial_stat=initial_stat,
        min_duration_seconds=min_duration_seconds,
        max_duration_seconds=max_duration_seconds,
        claim_scan_slot=claim_scan_slot,
    )
    if note is not None:
        # In-process callers such as the CLI scan have no job log; the
        # application log file is where their notes go.
        LOGGER.warning("%s path=%s", note, audio_path)
    return prepared


def prepare_audio_path_group(
    paths: list[str],
    *,
    min_duration_seconds: int | None = None,
    max_duration_seconds: int | None = None,
) -> list[PreparedScanResult]:
    """Read metadata for raw path strings without opening the library database."""

    results: list[PreparedScanResult] = []
    for path in paths:
        try:
            prepared, note = _prepare_audio_file_metadata_with_note(
                Path(path).expanduser().resolve(strict=False),
                min_duration_seconds=min_duration_seconds,
                max_duration_seconds=max_duration_seconds,
            )
        except Exception as error:
            results.append(
                PreparedScanResult(
                    path=path,
                    error_message=f"{type(error).__name__}: {error}",
                )
            )
            continue
        results.append(PreparedScanResult(path=path, prepared=prepared, note=note))
    return results


def _prepare_audio_file_metadata_with_note(
    audio_path: Path,
    *,
    initial_stat: os.stat_result | None = None,
    min_duration_seconds: int | None = None,
    max_duration_seconds: int | None = None,
    claim_scan_slot: Callable[[], bool] | None = None,
) -> tuple[PreparedScan | None, str | None]:
    """Prepare one file and return the reader note separately.

    The note survives a duration-filter skip on purpose: a file no reader could
    open has no duration either, and the coordinator should still say why.
    """

    initial_stat = initial_stat or audio_path.stat()
    metadata, final_stat = read_audio_metadata_stable(
        audio_path,
        initial_stat=initial_stat,
    )
    note = _string_or_none(metadata.pop(READER_NOTE_KEY, None))
    duration_filter_active = (
        min_duration_seconds is not None
        or max_duration_seconds is not None
    )
    if duration_filter_active:
        duration = _positive_float_or_none(metadata.get("duration"))
        if duration is None:
            duration = read_ffmpeg_audio_duration_seconds(audio_path)
            if duration is not None:
                metadata["duration"] = duration
        if duration is None or (
            min_duration_seconds is not None and duration < min_duration_seconds
        ) or (
            max_duration_seconds is not None and duration > max_duration_seconds
        ):
            return None, note
    if claim_scan_slot is not None and not claim_scan_slot():
        return None, note
    prepared = PreparedScan(
        file=scanned_file_from_metadata(
            audio_path,
            metadata,
            file_size_bytes=final_stat.st_size,
            file_modified_ns=final_stat.st_mtime_ns,
        ),
        tags=file_tags_from_metadata(audio_path, metadata),
    )
    return prepared, note


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


def iter_audio_files(
    root: Path,
    *,
    extensions: Collection[str] | None = None,
) -> Iterator[Path]:
    """Stream deterministic absolute audio paths, deduplicated after resolve.

    Directories are walked depth-first in name order and every path is yielded
    as soon as it is found, so a limited scan can abandon the walk early instead
    of paying for the whole tree first.
    """

    root_path = _resolved_directory(root)
    selected_extensions = (
        SUPPORTED_AUDIO_EXTENSIONS
        if extensions is None
        else {
            extension.lower()
            for extension in extensions
            if extension.lower() in SUPPORTED_AUDIO_EXTENSIONS
        }
    )
    seen_identities: set[str] = set()

    def scan_directory(directory: Path) -> Iterator[Path]:
        try:
            with os.scandir(directory) as entries:
                sorted_entries = sorted(
                    entries,
                    key=lambda entry: (entry.name.lower(), entry.name),
                )
        except OSError:
            return
        for entry in sorted_entries:
            try:
                if entry.is_file() and (
                    Path(entry.name).suffix.lower() in selected_extensions
                ) and not entry.name.startswith("._"):
                    resolved = Path(entry.path).resolve(strict=False)
                    # resolve() already ran, so the key is built without a
                    # second resolve per discovered file.
                    identity = ordinal_path_key(resolved.as_posix())
                    if identity in seen_identities:
                        continue
                    seen_identities.add(identity)
                elif entry.is_dir(follow_symlinks=False):
                    yield from scan_directory(Path(entry.path))
                    continue
                else:
                    continue
            except OSError:
                continue
            yield resolved

    yield from scan_directory(root_path)


def read_ffmpeg_audio_duration_seconds(path: str | Path) -> float | None:
    """Read a container duration through PyAV without decoding audio frames."""

    try:
        av = load_project_pyav()
        with av.open(str(path), mode="r", metadata_errors="replace") as container:
            return _positive_float_or_none(
                float(container.duration) / float(av.time_base)
            )
    except Exception:
        return None


def read_audio_metadata(path: str | Path) -> dict[str, object]:
    """Read stream fields and tags with mutagen, retrying by content on refusal.

    The default mutagen open comes first and unchanged, so a healthy file takes
    exactly the path it always did. Only when that open raises or finds no
    reader is the file opened by content instead of by extension. Both passes
    fill the same keys; the second one also leaves a note under
    ``READER_NOTE_KEY`` so the caller can log what happened.
    """

    audio_path = Path(path)
    metadata: dict[str, object] = {"title": audio_path.stem}
    try:
        audio = MutagenFile(audio_path)
    except Exception:
        audio = None
    if audio is not None:
        return _metadata_from_mutagen(
            audio, metadata, _audio_format(audio, audio_path)
        )

    audio = _open_audio_by_content(audio_path)
    if audio is None:
        metadata[READER_NOTE_KEY] = "No reader could open the file: only its name is known"
        return metadata
    audio_format = _audio_format_from_reader(audio)
    metadata[READER_NOTE_KEY] = (
        f"Tags read by content as {audio_format or type(audio).__name__}: "
        "the default mutagen open rejected the file"
    )
    return _metadata_from_mutagen(audio, metadata, audio_format)


def _metadata_from_mutagen(
    audio: object,
    metadata: dict[str, object],
    audio_format: str | None,
) -> dict[str, object]:
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
    bit_depth = _positive_int_or_none(
        getattr(info, "bits_per_sample", None)
        or getattr(info, "sample_size", None)
    )
    if bit_depth is not None:
        metadata["bit_depth"] = bit_depth

    if audio_format:
        metadata["audio_format"] = audio_format

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
        file_path=resolved_file_path(path),
        file_size_bytes=int(file_size_bytes),
        file_modified_ns=int(file_modified_ns),
        audio_format=_string_or_none(metadata.get("audio_format")),
        sample_rate_hz=_positive_int_or_none(metadata.get("sample_rate_hz")),
        channel_count=_positive_int_or_none(metadata.get("channel_count")),
        bit_rate_bps=_positive_int_or_none(metadata.get("bit_rate_bps")),
        bit_depth=_positive_int_or_none(metadata.get("bit_depth")),
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
        track_number=_string_or_none(metadata.get("track_number")),
        label=_string_or_none(metadata.get("label")),
        country=_string_or_none(metadata.get("country")),
        year=_year_or_none(metadata.get("year")),
        tag_key=_string_or_none(
            metadata.get("key") or metadata.get("initialkey")
        ),
        tag_bpm=_positive_float_or_none(metadata.get("bpm")),
        comment=_string_or_none(metadata.get("comment")),
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


# --- Second-chance readers -------------------------------------------------
#
# Everything below runs only for a file the default mutagen open could not
# parse. A healthy file never reaches it, so it costs the scan nothing.


class _LenientMP4Chapters(MP4Chapters):
    """Chapter list that survives a malformed ``chpl`` atom.

    Some tag writers shrink the metadata and leave a stale ``chpl`` header over
    unrelated bytes. mutagen reads a chapter count out of that garbage and runs
    off the end of the atom (quodlibet/mutagen issue 564, open since 2022). The
    tags and the stream info parse fine, so an empty chapter list is the right
    answer.
    """

    def __init__(self, atoms, fileobj):
        try:
            super().__init__(atoms, fileobj)
        except Exception:
            self._chapters = []


class _LenientMP4(MP4):
    MP4Chapters = _LenientMP4Chapters


class _AIFFByChunks:
    """AIFF stream info plus the last well-formed ``ID3`` chunk.

    mutagen's ``AIFF`` binds the first chunk named ``ID3``, so a writer that
    leaves empty ``ID3`` chunks in front of the real one makes it read an ID3
    header out of the next chunk and refuse the file. Stream info never depends
    on tags, so read it directly, then take the last non-empty tag chunk. A
    tag cut by truncation is padded to its declared size: ``ID3`` treats the
    zeros as padding and keeps every frame that survived.
    """

    def __init__(self, fileobj) -> None:
        self.info = AIFFInfo(fileobj)
        fileobj.seek(0)
        chunks = [
            chunk
            for chunk in AIFFFile(fileobj).root.subchunks()
            if chunk.id == "ID3" and chunk.data_size > 0
        ]
        self.tags = None
        if chunks:
            chunk = chunks[-1]
            body = chunk.read()
            body += b"\x00" * (chunk.data_size - len(body))
            try:
                self.tags = ID3(io.BytesIO(body))
            except Exception:
                self.tags = None


# Readers for the second, content-only mutagen pass: every format the scan
# accepts, with the tolerant MP4 in place of the stock one. AIFF is handled
# by _AIFFByChunks before this list is consulted.
_CONTENT_READERS = (
    MP3,
    FLAC,
    OggVorbis,
    OggOpus,
    OggFLAC,
    _LenientMP4,
    AAC,
    WAVE,
    ASF,
    WavPack,
    MonkeysAudio,
)

# In the content pass the extension is known to be wrong or absent, so the
# display format comes from the reader that parsed the file.
_READER_FORMAT_SUFFIXES: tuple[tuple[type, str], ...] = (
    (MP3, ".mp3"),
    (FLAC, ".flac"),
    (OggOpus, ".opus"),
    (OggVorbis, ".ogg"),
    (OggFLAC, ".ogg"),
    (MP4, ".m4a"),
    (AAC, ".aac"),
    (WAVE, ".wav"),
    (ASF, ".wma"),
    (WavPack, ".wv"),
    (MonkeysAudio, ".ape"),
    (_AIFFByChunks, ".aiff"),
)


def _open_audio_by_content(path: Path) -> object | None:
    """Open a file mutagen rejected, choosing the reader by its header.

    ``mutagen.File`` scores readers by header and by file extension, and the
    extension weighs enough to send an MP3 named ``.flac`` to the FLAC parser.
    Passing the stem as the name removes the extension from the score, so only
    the content decides. Returns ``None`` when no reader recognises the file.
    """

    try:
        with path.open("rb") as fileobj:
            header = fileobj.read(12)
            fileobj.seek(0)
            if header[:4] == b"FORM" and header[8:12] in (b"AIFF", b"AIFC"):
                return _AIFFByChunks(fileobj)
            return MutagenFile(fileobj, filename=path.stem, options=_CONTENT_READERS)
    except Exception:
        return None


def _audio_format_from_reader(audio: object) -> str | None:
    for kind, suffix in _READER_FORMAT_SUFFIXES:
        if isinstance(audio, kind):
            return DISPLAY_AUDIO_FORMATS[suffix]
    return None
