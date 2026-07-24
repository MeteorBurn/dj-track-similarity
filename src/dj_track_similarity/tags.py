from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

from mutagen import File as MutagenFile
from mutagen.aiff import AIFF
from mutagen.flac import FLAC
from mutagen.id3 import ID3, ID3NoHeaderError, TCON
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

from .job_runtime import JobStore
from .library_models import GenreTagCandidate
from .logging_config import exception_summary, log_failure, log_job_event
from .scanner import file_tags_from_metadata, read_audio_metadata
from .track_models import FileTags, TrackFileState, TrackIdentity
from .wave_tags import set_audio_id3_genre, write_wave_genre_tag


LOGGER = logging.getLogger(__name__)


class _GenreTagRepository(Protocol):
    def list_genre_tag_candidates(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[GenreTagCandidate, ...]: ...

    def apply_self_tag_write(
        self,
        expected: TrackFileState,
        *,
        write_source: Callable[[Path], None],
        read_source_tags: Callable[[Path], FileTags],
        validate_readback: Callable[[FileTags], None],
        tags_read_at: str | None = None,
    ) -> TrackIdentity: ...


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


@dataclass(frozen=True)
class GenreTagApplyResult:
    track_id: int
    path: str
    tags: dict[str, str]
    status: str
    message: str
    error: str | None = None


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
    def __init__(self, repository: _GenreTagRepository) -> None:
        self.repository = repository
        self._store = JobStore(self._copy_status, unknown_label="genre tag job")

    def create_job(self) -> str:
        candidates = self.repository.list_genre_tag_candidates()
        job_id = str(uuid.uuid4())
        status = GenreTagJobStatus(
            job_id=job_id,
            state="queued",
            total=len(candidates),
        )
        self._store.add(job_id, status, payload=candidates)
        self._append_event(job_id, "info", "Genre tag apply queued")
        return job_id

    def start(self) -> GenreTagJobStatus:
        job_id = self.create_job()
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(self) -> GenreTagJobStatus:
        job_id = self.create_job()
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> GenreTagJobStatus:
        status = self.get(job_id)
        candidates = cast(
            tuple[GenreTagCandidate, ...],
            self._store.payload(job_id) or (),
        )
        if status.cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "Genre tag apply cancelled")
            return self.get(job_id)

        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(job_id, "info", "Genre tag apply started")
        for candidate in candidates:
            if self.get(job_id).cancel_requested:
                self._update(
                    job_id,
                    state="cancelled",
                    finished_at=time.time(),
                    current_path=None,
                )
                self._append_event(job_id, "warn", "Genre tag apply cancelled")
                return self.get(job_id)
            result = _apply_genre_tag_to_candidate(
                self.repository,
                candidate,
            )
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
                status.errors.append(
                    GenreTagError(
                        track_id=result.track_id,
                        path=result.path,
                        error=result.error or result.message,
                    )
                )
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
        log_job_event(
            LOGGER,
            level,
            "%s job_id=%s track_id=%s path=%s",
            message,
            job_id,
            track_id,
            path,
            track_event=path is not None,
        )
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
        return copy


def apply_genre_tags_to_tracks(
    repository: _GenreTagRepository,
    candidates: Sequence[GenreTagCandidate],
) -> list[GenreTagApplyResult]:
    results: list[GenreTagApplyResult] = []
    LOGGER.info("Genre tag apply started tracks=%s", len(candidates))
    for candidate in candidates:
        results.append(
            _apply_genre_tag_to_candidate(repository, candidate)
        )
    LOGGER.info("Genre tag apply finished %s", genre_tag_apply_summary(results))
    return results


def _apply_genre_tag_to_candidate(
    repository: _GenreTagRepository,
    candidate: GenreTagCandidate,
) -> GenreTagApplyResult:
    genre_tags = _genre_tags_for_candidate(candidate)
    if not genre_tags:
        result = GenreTagApplyResult(
            track_id=candidate.track_id,
            path=candidate.file_path,
            tags=genre_tags,
            status="skipped",
            message="No MAEST genres to write",
        )
        log_job_event(
            LOGGER,
            "info",
            "Genre tag write skipped track_id=%s path=%s reason=%s",
            candidate.track_id,
            candidate.file_path,
            result.message,
            track_event=True,
        )
        return result

    path = Path(candidate.file_path)
    try:
        genre_text = genre_tags["GENRE"]
        expected = TrackFileState(
            catalog_uuid=candidate.catalog_uuid,
            track_id=candidate.track_id,
            track_uuid=candidate.track_uuid,
            file_path=candidate.file_path,
            file_size_bytes=candidate.expected_file_size_bytes,
            file_modified_ns=candidate.expected_file_modified_ns,
            content_generation=candidate.content_generation,
            missing_since=None,
        )
        repository.apply_self_tag_write(
            expected,
            write_source=lambda source_path: _write_genre_tag(
                source_path,
                genre_text,
            ),
            read_source_tags=_read_file_tags,
            validate_readback=lambda refreshed_tags: _verify_genre_readback(
                path,
                expected_genre=genre_text,
                refreshed_tags=refreshed_tags,
            ),
        )
        result = GenreTagApplyResult(
            track_id=candidate.track_id,
            path=candidate.file_path,
            tags=genre_tags,
            status="applied",
            message="Genre tag written",
        )
        log_job_event(
            LOGGER,
            "ok",
            "Genre tags applied track_id=%s path=%s tags=%s",
            candidate.track_id,
            candidate.file_path,
            genre_tags,
            track_event=True,
        )
        return result
    except Exception as error:
        summary = exception_summary(error)
        result = GenreTagApplyResult(
            track_id=candidate.track_id,
            path=candidate.file_path,
            tags=genre_tags,
            status="failed",
            message="Genre tag write failed",
            error=summary,
        )
        log_failure(
            LOGGER,
            "Genre tag apply failed track_id=%s path=%s error=%s",
            candidate.track_id,
            candidate.file_path,
            summary,
        )
        return result


def genre_tag_apply_summary(results: list[GenreTagApplyResult]) -> str:
    applied = sum(1 for result in results if result.status == "applied")
    skipped = sum(1 for result in results if result.status == "skipped")
    failed = sum(1 for result in results if result.status == "failed")
    return f"applied={applied} skipped={skipped} failed={failed} total={len(results)}"


def _genre_tags_for_candidate(
    candidate: GenreTagCandidate,
) -> dict[str, str]:
    if not candidate.genres:
        return {}
    genres = [_clean_genre_label(genre) for genre in candidate.genres]
    genres = [genre for genre in genres if genre]
    return {"GENRE": "; ".join(genres)} if genres else {}


def _read_file_tags(path: Path) -> FileTags:
    return file_tags_from_metadata(path, read_audio_metadata(path))


def _verify_genre_readback(
    path: Path,
    *,
    expected_genre: str,
    refreshed_tags: FileTags,
) -> None:
    expected_values = _split_genre_values((expected_genre,))
    actual_values = _split_genre_values(refreshed_tags.genres)
    if actual_values != expected_values:
        raise RuntimeError(
            f"Genre tag readback mismatch after save: {path}"
        )


def _split_genre_values(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        cleaned
        for value in values
        for cleaned in (part.strip() for part in value.split(";"))
        if cleaned
    )


def _clean_genre_label(genre: str) -> str:
    text = str(genre).replace("_", " ").strip()
    if "---" in text:
        text = text.rsplit("---", 1)[-1].strip()
    return text


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
        write_wave_genre_tag(path, genre_text)
        return

    audio = MutagenFile(path)
    if audio is None:
        raise ValueError(f"Unsupported audio tag format: {path}")
    if isinstance(audio, MP4) or suffix in {".m4a", ".mp4", ".alac"}:
        audio["\xa9gen"] = [genre_text]
    elif isinstance(audio, FLAC):
        audio["GENRE"] = genre_text
    elif isinstance(audio, (WAVE, AIFF)) or suffix in {".aif", ".aiff", ".dsf", ".dff"}:
        set_audio_id3_genre(audio, genre_text)
    else:
        if not hasattr(audio, "tags") or audio.tags is None:
            audio.add_tags()
        if hasattr(audio.tags, "add"):
            set_audio_id3_genre(audio, genre_text)
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
