from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
import logging
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TCON, TXXX
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

from .database import LibraryDatabase
from .job_runtime import JobStore
from .logging_config import exception_summary
from .models import GenreTagApplyResult, TagPreview, Track
from .scanner import MUTAGEN_METADATA_KEYS, read_audio_metadata


CUSTOM_TAG_PREFIX = "DJ_SIM"
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenreTagLogEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None
    track_id: int | None = None


@dataclass(frozen=True)
class GenreTagError:
    track_id: int
    path: str
    error: str


@dataclass
class GenreTagJobStatus:
    job_id: str
    state: str
    total: int = 0
    processed: int = 0
    applied: int = 0
    skipped: int = 0
    failed: int = 0
    current_path: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    avg_seconds_per_track: float | None = None
    errors: list[GenreTagError] = field(default_factory=list)
    events: list[GenreTagLogEvent] = field(default_factory=list)
    cancel_requested: bool = False


class GenreTagJobManager:
    def __init__(self, db: LibraryDatabase) -> None:
        self.db = db
        self._store = JobStore(self._copy_status, unknown_label="genre tag job")

    def create_job(self, track_ids: list[int] | None = None) -> str:
        tracks = self.db.list_tracks_with_maest_genres() if track_ids is None else _tracks(db=self.db, track_ids=track_ids)
        job_id = str(uuid.uuid4())
        status = GenreTagJobStatus(job_id=job_id, state="queued", total=len(tracks))
        status._tracks = tracks  # type: ignore[attr-defined]
        self._store.add(job_id, status)
        self._append_event(job_id, "info", "Genre tag apply queued")
        return job_id

    def start(self, track_ids: list[int] | None = None) -> GenreTagJobStatus:
        job_id = self.create_job(track_ids)
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(self, track_ids: list[int] | None = None) -> GenreTagJobStatus:
        job_id = self.create_job(track_ids)
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> GenreTagJobStatus:
        status = self.get(job_id)
        tracks: list[Track] = getattr(status, "_tracks", [])
        if status.cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "Genre tag apply cancelled")
            return self.get(job_id)

        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(job_id, "info", "Genre tag apply started")
        for track in tracks:
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None)
                self._append_event(job_id, "warn", "Genre tag apply cancelled")
                return self.get(job_id)
            result = _apply_genre_tag_to_track(self.db, track)
            self._record_result(job_id, result)

        finished = time.time()
        final = self.get(job_id)
        processed = max(1, final.processed)
        self._update(
            job_id,
            state="completed",
            finished_at=finished,
            current_path=None,
            avg_seconds_per_track=(finished - (final.started_at or started)) / processed,
        )
        self._append_event(job_id, "info", "Genre tag apply completed")
        return self.get(job_id)

    def get(self, job_id: str) -> GenreTagJobStatus:
        return self._store.get(job_id)

    def latest(self) -> GenreTagJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> GenreTagJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _record_result(self, job_id: str, result: GenreTagApplyResult) -> None:
        with self._store.locked(job_id) as status:
            status.current_path = result.path
            status.processed += 1
            if result.status == "applied":
                status.applied += 1
            elif result.status == "skipped":
                status.skipped += 1
            else:
                status.failed += 1
                status.errors.append(GenreTagError(track_id=result.track_id, path=result.path, error=result.error or result.message))
            if status.started_at and status.processed:
                status.avg_seconds_per_track = (time.time() - status.started_at) / status.processed
        level = "ok" if result.status == "applied" else "warn" if result.status == "skipped" else "error"
        self._append_event(job_id, level, result.message, path=result.path, track_id=result.track_id)

    def _update(self, job_id: str, **changes: object) -> None:
        self._store.update(job_id, **changes)

    def _append_event(
        self,
        job_id: str,
        level: str,
        message: str,
        *,
        path: str | None = None,
        track_id: int | None = None,
    ) -> None:
        self._store.append_event(job_id, GenreTagLogEvent(time.time(), level, message, path, track_id))

    @staticmethod
    def _copy_status(status: GenreTagJobStatus) -> GenreTagJobStatus:
        copy = GenreTagJobStatus(
            job_id=status.job_id,
            state=status.state,
            total=status.total,
            processed=status.processed,
            applied=status.applied,
            skipped=status.skipped,
            failed=status.failed,
            current_path=status.current_path,
            started_at=status.started_at,
            finished_at=status.finished_at,
            avg_seconds_per_track=status.avg_seconds_per_track,
            errors=list(status.errors),
            events=list(status.events),
            cancel_requested=status.cancel_requested,
        )
        if hasattr(status, "_tracks"):
            copy._tracks = list(getattr(status, "_tracks"))  # type: ignore[attr-defined]
        return copy


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


def apply_genre_tags(db: LibraryDatabase, track_ids: list[int]) -> list[GenreTagApplyResult]:
    return apply_genre_tags_to_tracks(db, _tracks(db, track_ids))


def apply_genre_tags_to_tracks(db: LibraryDatabase, tracks: list[Track]) -> list[GenreTagApplyResult]:
    results: list[GenreTagApplyResult] = []
    LOGGER.info("Genre tag apply started tracks=%s", len(tracks))
    for track in tracks:
        results.append(_apply_genre_tag_to_track(db, track))
    LOGGER.info("Genre tag apply finished %s", genre_tag_apply_summary(results))
    return results


def _apply_genre_tag_to_track(db: LibraryDatabase, track: Track) -> GenreTagApplyResult:
    preview = TagPreview(track_id=track.id, path=track.path, tags=_genre_tags_for_track(track))
    if not preview.tags:
        result = GenreTagApplyResult(
            track_id=preview.track_id,
            path=preview.path,
            tags=preview.tags,
            status="skipped",
            message="No MAEST genres to write",
        )
        LOGGER.info("Genre tag write skipped track_id=%s path=%s reason=%s", preview.track_id, preview.path, result.message)
        return result

    path = Path(preview.path)
    if _should_skip_genre_tag_write(path):
        result = GenreTagApplyResult(
            track_id=preview.track_id,
            path=preview.path,
            tags=preview.tags,
            status="skipped",
            message="Unsupported WAV container",
        )
        LOGGER.warning(
            "Skipping genre tag write for unsupported WAV container track_id=%s path=%s",
            preview.track_id,
            preview.path,
        )
        return result

    try:
        _write_genre_tag(path, list(preview.tags.values())[0])
        db.refresh_track_file_metadata(
            preview.track_id,
            size=path.stat().st_size,
            mtime=path.stat().st_mtime,
            metadata=read_audio_metadata(path),
            replace_metadata_keys=MUTAGEN_METADATA_KEYS,
        )
        result = GenreTagApplyResult(
            track_id=preview.track_id,
            path=preview.path,
            tags=preview.tags,
            status="applied",
            message="Genre tag written",
        )
        LOGGER.info("Genre tags applied track_id=%s path=%s tags=%s", preview.track_id, preview.path, preview.tags)
        return result
    except Exception as error:
        summary = exception_summary(error)
        result = GenreTagApplyResult(
            track_id=preview.track_id,
            path=preview.path,
            tags=preview.tags,
            status="failed",
            message="Genre tag write failed",
            error=summary,
        )
        LOGGER.exception(
            "Genre tag apply failed track_id=%s path=%s error=%s",
            preview.track_id,
            preview.path,
            summary,
        )
        return result


def genre_tag_apply_summary(results: list[GenreTagApplyResult]) -> str:
    applied = sum(1 for result in results if result.status == "applied")
    skipped = sum(1 for result in results if result.status == "skipped")
    failed = sum(1 for result in results if result.status == "failed")
    return f"applied={applied} skipped={skipped} failed={failed} total={len(results)}"


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
        _repair_shifted_wave_id3_chunk(path)
        _repair_oversized_wave_data_chunk(path)
        _remove_duplicate_wave_id3_chunks(path)
        audio = WAVE(path)
        _set_audio_id3_genre(audio, genre_text)
        audio.save()
        _validate_wave_container(path)
        _remove_duplicate_wave_id3_chunks(path)
        _verify_wave_genre_tag(path, genre_text)
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


def _repair_shifted_wave_id3_chunk(path: Path) -> None:
    data = bytearray(path.read_bytes())
    bounds = _find_wave_data_chunk_bounds(data)
    if bounds is None:
        return
    data_start, declared_size = bounds
    declared_end = data_start + declared_size
    shifted_chunk_start = declared_end - 2
    if shifted_chunk_start < data_start or shifted_chunk_start + 8 > len(data):
        return
    if data[shifted_chunk_start : shifted_chunk_start + 4] != b"id3 ":
        return
    data_size_offset = data_start - 4
    data[data_size_offset : data_size_offset + 4] = (declared_size - 2).to_bytes(4, "little")
    data[4:8] = (len(data) - 8).to_bytes(4, "little")
    path.write_bytes(data)
    LOGGER.warning("Repaired WAV data/id3 chunk boundary before tag write path=%s", path)


def _verify_wave_genre_tag(path: Path, genre_text: str) -> None:
    audio = WAVE(path)
    if audio.tags is None or "TCON" not in audio.tags:
        raise RuntimeError(f"Genre tag was not readable after WAV save: {path}")
    if list(audio.tags["TCON"].text) != [genre_text]:
        raise RuntimeError(f"Genre tag readback mismatch after WAV save: {path}")


def _remove_duplicate_wave_id3_chunks(path: Path) -> None:
    data = path.read_bytes()
    pos = 12
    chunks: list[tuple[int, int, bytes]] = []
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        chunk_size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        chunk_end = pos + 8 + chunk_size + (chunk_size % 2)
        if chunk_end <= pos or chunk_end > len(data) + 1:
            return
        chunks.append((pos, chunk_end, chunk_id))
        pos = chunk_end

    seen_id3 = False
    rebuilt = bytearray(data[:12])
    removed = 0
    for start, end, chunk_id in chunks:
        if chunk_id in {b"id3 ", b"ID3 "}:
            if seen_id3:
                removed += 1
                continue
            seen_id3 = True
        rebuilt.extend(data[start:end])

    if not removed:
        return
    rebuilt[4:8] = (len(rebuilt) - 8).to_bytes(4, "little")
    path.write_bytes(rebuilt)
    LOGGER.warning("Removed duplicate WAV id3 chunks before tag write path=%s count=%s", path, removed)


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
