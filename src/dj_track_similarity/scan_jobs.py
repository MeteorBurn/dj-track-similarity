"""Background and synchronous jobs for the sole scan repository path."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import (
    FIRST_COMPLETED,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
)
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from typing import Callable, Collection, Iterable, Iterator, cast

from .db_tracks import TrackRepository, canonical_file_path, ordinal_path_key
from .job_runtime import JobStore
from .logging_config import exception_summary, log_failure, log_job_event
from .scanner import (
    PreparedScan,
    PreparedScanResult,
    READER_NOTE_KEY,
    SUPPORTED_AUDIO_EXTENSIONS,
    file_tags_from_metadata,
    iter_audio_files,
    prepare_audio_path_group,
    read_audio_metadata,
    read_audio_metadata_stable,
    scanned_file_from_metadata,
)
from .track_models import TrackFileState


LOGGER = logging.getLogger(__name__)
_SCAN_PREPARE_BATCH_SIZE = 64
_SCAN_PREPARE_IN_FLIGHT_FACTOR = 2
_SCAN_WRITE_BATCH_SIZE = 64


@dataclass(frozen=True)
class ScanLogEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None


@dataclass
class ScanJobStatus:
    job_id: str
    state: str
    root: str
    total: int = 0
    processed: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    current_path: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    avg_seconds_per_track: float | None = None
    events: list[ScanLogEvent] = field(default_factory=list)
    cancel_requested: bool = False
    workers: int = 1
    limit: int | None = None


@dataclass
class ScanJobPayload:
    paths: Iterable[Path]
    track_states: dict[str, TrackFileState] = field(default_factory=dict)
    reconcile_missing: bool = True
    min_duration_seconds: int | None = None
    max_duration_seconds: int | None = None
    scan_limit: int | None = None
    extension_filtered_count: int = 0
    _accepted_count: int = field(default=0, init=False, repr=False)
    _accepted_lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    def claim_scan_slot(self) -> bool:
        if self.scan_limit is None:
            return True
        with self._accepted_lock:
            if self._accepted_count >= self.scan_limit:
                return False
            self._accepted_count += 1
            return True

    def release_scan_slot(self) -> None:
        """Return a claimed slot when the track never reached the database."""

        if self.scan_limit is None:
            return
        with self._accepted_lock:
            self._accepted_count = max(0, self._accepted_count - 1)

    def next_scan_batch_size(self, batch_size: int) -> int:
        """Pull no more paths than the limit can still take."""

        if self.scan_limit is None:
            return batch_size
        with self._accepted_lock:
            return max(0, min(batch_size, self.scan_limit - self._accepted_count))

    def scan_limit_reached(self) -> bool:
        if self.scan_limit is None:
            return False
        with self._accepted_lock:
            return self._accepted_count >= self.scan_limit


class ScanJobManager:
    """Run parallel discovery work against one thread-safe TrackRepository."""

    def __init__(self, repository: TrackRepository) -> None:
        self.repository = repository
        self._store = JobStore(
            self._copy_status,
            unknown_label="scan job",
        )

    def create_job(
        self,
        root: str | Path,
        *,
        workers: int = 1,
        limit: int | None = None,
        extensions: Collection[str] | None = None,
        min_duration_seconds: int | None = None,
        max_duration_seconds: int | None = None,
    ) -> str:
        root_path = Path(root).expanduser().resolve(strict=False)
        if limit is not None and (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 1
        ):
            raise ValueError("limit must be a positive integer or None")
        if not root_path.exists():
            raise FileNotFoundError(root_path)
        if not root_path.is_dir():
            raise NotADirectoryError(root_path)
        _validate_duration_bounds(min_duration_seconds, max_duration_seconds)
        selected_extensions = _selected_extensions(extensions)
        job_id = str(uuid.uuid4())
        payload = ScanJobPayload(
            paths=[],
            reconcile_missing=(
                limit is None
                and selected_extensions == SUPPORTED_AUDIO_EXTENSIONS
                and min_duration_seconds is None
                and max_duration_seconds is None
            ),
            min_duration_seconds=min_duration_seconds,
            max_duration_seconds=max_duration_seconds,
            scan_limit=limit,
        )
        if limit is None:
            payload.paths = list(
                self._iter_scan_paths(payload, root_path, selected_extensions)
            )
            total = len(payload.paths)
        else:
            # A limited scan adds new tracks only, so paths already stored are
            # dropped before the limit counts them, and discovery stays lazy so
            # the walk can stop as soon as the limit is filled.
            payload.paths = self._iter_scan_paths(
                payload,
                root_path,
                selected_extensions,
                known_path_keys={
                    # Stored paths are already resolved, so no path in the
                    # library is resolved again to build this set.
                    ordinal_path_key(item.file_path)
                    for item in self.repository.list_track_paths(
                        include_missing=True,
                    )
                },
            )
            total = 0
        status = ScanJobStatus(
            job_id=job_id,
            state="queued",
            root=str(root_path),
            total=total,
            workers=max(1, workers),
            limit=limit,
        )
        self._store.add(job_id, status, payload=payload)
        self._append_event(
            job_id,
            "info",
            (
                f"Scan queued · workers {status.workers}"
                f" · limit {status.limit if status.limit is not None else 'all'}"
            ),
            path=str(root_path),
        )
        return job_id

    def start(
        self,
        root: str | Path,
        *,
        workers: int = 1,
        limit: int | None = None,
        extensions: Collection[str] | None = None,
        min_duration_seconds: int | None = None,
        max_duration_seconds: int | None = None,
    ) -> ScanJobStatus:
        job_id = self.create_job(
            root,
            workers=workers,
            limit=limit,
            extensions=extensions,
            min_duration_seconds=min_duration_seconds,
            max_duration_seconds=max_duration_seconds,
        )
        thread = threading.Thread(
            target=self.run_job,
            args=(job_id,),
            daemon=True,
        )
        thread.start()
        return self.get(job_id)

    def run_sync(
        self,
        root: str | Path,
        *,
        workers: int = 1,
        limit: int | None = None,
        extensions: Collection[str] | None = None,
        min_duration_seconds: int | None = None,
        max_duration_seconds: int | None = None,
    ) -> ScanJobStatus:
        job_id = self.create_job(
            root,
            workers=workers,
            limit=limit,
            extensions=extensions,
            min_duration_seconds=min_duration_seconds,
            max_duration_seconds=max_duration_seconds,
        )
        return self.run_job(job_id)

    def create_tag_refresh_job(
        self,
        *,
        workers: int = 1,
    ) -> str:
        track_paths = self.repository.list_track_paths()
        track_states = self.repository.get_track_file_states_by_ids(
            [item.track_id for item in track_paths]
        )
        paths = [Path(item.file_path) for item in track_states]
        states_by_path = {
            canonical_file_path(item.file_path): item
            for item in track_states
        }
        job_id = str(uuid.uuid4())
        status = ScanJobStatus(
            job_id=job_id,
            state="queued",
            root="metadata refresh",
            total=len(paths),
            workers=max(1, workers),
        )
        self._store.add(
            job_id,
            status,
            payload=ScanJobPayload(
                paths=paths,
                track_states=states_by_path,
            ),
        )
        self._append_event(
            job_id,
            "info",
            f"Tag refresh queued · workers {status.workers}",
        )
        return job_id

    def start_tag_refresh(
        self,
        *,
        workers: int = 1,
    ) -> ScanJobStatus:
        job_id = self.create_tag_refresh_job(workers=workers)
        thread = threading.Thread(
            target=self.run_tag_refresh_job,
            args=(job_id,),
            daemon=True,
        )
        thread.start()
        return self.get(job_id)

    def run_tag_refresh_job(self, job_id: str) -> ScanJobStatus:
        status = self.get(job_id)
        payload = cast(ScanJobPayload, self._store.payload(job_id))
        if status.cancel_requested:
            return self._finish_cancelled(job_id, "Tag refresh cancelled")

        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(job_id, "info", "Tag refresh started")
        if status.workers <= 1:
            for path in payload.paths:
                if self.get(job_id).cancel_requested:
                    return self._finish_cancelled(
                        job_id,
                        "Tag refresh cancelled",
                    )
                self._refresh_tags_one(job_id, path)
        else:
            self._run_parallel(
                job_id,
                payload.paths,
                status.workers,
                self._refresh_tags_one,
            )
            if self.get(job_id).cancel_requested:
                return self._finish_cancelled(
                    job_id,
                    "Tag refresh cancelled",
                )

        return self._finish_completed(
            job_id,
            started=started,
            message="Tag refresh completed",
        )

    def run_job(self, job_id: str) -> ScanJobStatus:
        status = self.get(job_id)
        payload = cast(ScanJobPayload, self._store.payload(job_id))
        if status.cancel_requested:
            return self._finish_cancelled(job_id, "Scan cancelled")

        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(
            job_id,
            "info",
            "Scan started",
            path=status.root,
        )
        self._run_parallel_scan(
            job_id,
            payload.paths,
            status.workers,
        )
        if self.get(job_id).cancel_requested:
            return self._finish_cancelled(job_id, "Scan cancelled")

        if payload.scan_limit_reached():
            self._append_event(
                job_id,
                "info",
                f"Scan limit {payload.scan_limit} reached, scanning stopped",
            )

        if payload.reconcile_missing:
            try:
                self.repository.mark_unseen_missing(
                    status.root,
                    payload.paths,
                )
            except Exception as error:
                error_text = exception_summary(error)
                log_failure(
                    LOGGER,
                    "Scan missing reconciliation failed job_id=%s error=%s",
                    job_id,
                    error_text,
                )
                self._update(
                    job_id,
                    state="failed",
                    finished_at=time.time(),
                    current_path=None,
                )
                self._append_event(
                    job_id,
                    "error",
                    f"Scan failed: {error_text}",
                )
                return self.get(job_id)

        return self._finish_completed(
            job_id,
            started=started,
            message="Scan completed",
        )

    def _run_parallel(
        self,
        job_id: str,
        paths: Iterable[Path],
        workers: int,
        action: Callable[[str, Path], None],
    ) -> None:
        pending_paths = iter(paths)
        futures = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            while True:
                if self.get(job_id).cancel_requested:
                    for future in futures:
                        future.cancel()
                    return
                while len(futures) < workers:
                    try:
                        path = next(pending_paths)
                    except StopIteration:
                        break
                    futures[executor.submit(action, job_id, path)] = path
                if not futures:
                    return
                done, _ = wait(
                    futures,
                    return_when=FIRST_COMPLETED,
                )
                for future in done:
                    futures.pop(future, None)
                    future.result()

    @staticmethod
    def _iter_scan_paths(
        payload: ScanJobPayload,
        root_path: Path,
        selected_extensions: set[str],
        *,
        known_path_keys: set[str] | None = None,
    ) -> Iterator[Path]:
        """Stream scannable paths and count what the selection dropped."""

        for path in iter_audio_files(
            root_path,
            extensions=SUPPORTED_AUDIO_EXTENSIONS,
        ):
            if path.suffix.lower() not in selected_extensions:
                payload.extension_filtered_count += 1
                continue
            if (
                known_path_keys is not None
                # iter_audio_files already yields resolved paths.
                and ordinal_path_key(path.as_posix()) in known_path_keys
            ):
                continue
            yield path

    def _run_parallel_scan(
        self,
        job_id: str,
        paths: Iterable[Path],
        workers: int,
    ) -> None:
        """Prepare bounded path batches and write ready results on this thread."""

        payload = cast(ScanJobPayload, self._store.payload(job_id))
        pending_paths = iter(paths)
        max_in_flight = max(1, workers * _SCAN_PREPARE_IN_FLIGHT_FACTOR)
        futures = {}
        input_exhausted = False
        actual_total = 0
        filtered_count_total = 0
        self._update(
            job_id,
            total=actual_total,
            skipped=payload.extension_filtered_count,
        )
        with ProcessPoolExecutor(max_workers=workers) as executor:
            while not input_exhausted or futures:
                if self.get(job_id).cancel_requested:
                    for future in futures:
                        future.cancel()
                    return
                if payload.scan_limit_reached():
                    for future in futures:
                        future.cancel()
                    return

                while not input_exhausted and len(futures) < max_in_flight:
                    batch_size = payload.next_scan_batch_size(
                        _SCAN_PREPARE_BATCH_SIZE,
                    )
                    if batch_size == 0:
                        break
                    path_group = [
                        str(path)
                        for path in islice(pending_paths, batch_size)
                    ]
                    if not path_group:
                        input_exhausted = True
                        break
                    future = executor.submit(
                        prepare_audio_path_group,
                        path_group,
                        min_duration_seconds=payload.min_duration_seconds,
                        max_duration_seconds=payload.max_duration_seconds,
                    )
                    futures[future] = None

                if not futures:
                    return
                done, _ = wait(
                    futures,
                    return_when=FIRST_COMPLETED,
                )
                for future in done:
                    futures.pop(future, None)
                    prepared_group, filtered_count = self._collect_prepared_scan_group(
                        job_id,
                        future.result(),
                    )
                    actual_total += len(prepared_group)
                    filtered_count_total += filtered_count
                    self._update(
                        job_id,
                        total=actual_total,
                        skipped=(
                            payload.extension_filtered_count
                            + filtered_count_total
                        ),
                    )
                    for start in range(
                        0,
                        len(prepared_group),
                        _SCAN_WRITE_BATCH_SIZE,
                    ):
                        if self.get(job_id).cancel_requested:
                            for pending_future in futures:
                                pending_future.cancel()
                            return
                        self._write_prepared_scan_batch(
                            job_id,
                            prepared_group[
                                start : start + _SCAN_WRITE_BATCH_SIZE
                            ],
                        )

    def get(self, job_id: str) -> ScanJobStatus:
        return self._store.get(job_id)

    def latest(self) -> ScanJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> ScanJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _collect_prepared_scan_group(
        self,
        job_id: str,
        results: list[PreparedScanResult],
    ) -> tuple[list[tuple[Path, PreparedScan]], int]:
        """Apply worker results to job state without writing to SQLite."""

        prepared_group: list[tuple[Path, PreparedScan]] = []
        skipped_count = 0
        payload = cast(ScanJobPayload, self._store.payload(job_id))
        for result in results:
            if payload.scan_limit_reached():
                break
            path = Path(result.path)
            self._update(job_id, current_path=str(path))
            if result.error_message is not None:
                self._record_scan_failure(
                    job_id,
                    path,
                    RuntimeError(result.error_message),
                )
                continue
            if result.note is not None:
                # The reader only annotates its result; this is where the note
                # reaches the job log and the log file, like every other event.
                self._append_event(job_id, "warn", result.note, path=str(path))
            if result.prepared is None:
                skipped_count += 1
                self._append_event(
                    job_id,
                    "info",
                    "Track skipped by duration filter or scan limit",
                    path=str(path),
                )
                continue
            if not payload.claim_scan_slot():
                break
            prepared_group.append((path, result.prepared))
        return prepared_group, skipped_count

    def _write_prepared_scan_batch(
        self,
        job_id: str,
        batch: list[tuple[Path, PreparedScan]],
    ) -> None:
        for path, prepared in batch:
            self._write_prepared_scan_one(job_id, path, prepared)

    def _write_prepared_scan_one(
        self,
        job_id: str,
        path: Path,
        prepared: PreparedScan | None,
    ) -> None:
        if prepared is None:
            self._increment(
                job_id,
                skipped=1,
                message="Track skipped by duration filter or scan limit",
                level="info",
                path=str(path),
            )
            return
        payload = cast(ScanJobPayload, self._store.payload(job_id))
        try:
            current_stat = Path(prepared.file.file_path).stat()
            if (
                int(current_stat.st_size) != prepared.file.file_size_bytes
                or int(current_stat.st_mtime_ns) != prepared.file.file_modified_ns
            ):
                raise RuntimeError(
                    "Source file changed after scan metadata was read"
                )
            mutation = self.repository.upsert_scanned_track(
                file=prepared.file,
                tags=prepared.tags,
            )
        except Exception as error:
            payload.release_scan_slot()
            self._record_scan_failure(job_id, path, error)
            return
        if mutation.action != "added":
            payload.release_scan_slot()
        counters = {
            "added": 1 if mutation.action == "added" else 0,
            "updated": 1 if mutation.action == "updated" else 0,
            "unchanged": 1 if mutation.action == "unchanged" else 0,
        }
        self._increment(
            job_id,
            level="info" if mutation.action == "unchanged" else "ok",
            message=f"Track {mutation.action}",
            path=str(path),
            **counters,
        )

    def _record_scan_failure(
        self,
        job_id: str,
        path: Path,
        error: Exception,
    ) -> None:
        error_text = exception_summary(error)
        log_failure(
            LOGGER,
            "Scan track failed job_id=%s path=%s error=%s",
            job_id,
            path,
            error_text,
        )
        self._increment(
            job_id,
            failed=1,
            message=f"Track failed: {error_text}",
            level="error",
            path=str(path),
            log=False,
        )

    def _refresh_tags_one(self, job_id: str, path: Path) -> None:
        self._update(job_id, current_path=str(path))
        payload = cast(ScanJobPayload, self._store.payload(job_id))
        expected = payload.track_states.get(canonical_file_path(path))
        if expected is None:
            self._increment(
                job_id,
                skipped=1,
                message="Track state missing for path",
                level="warn",
                path=str(path),
            )
            return
        try:
            if not path.exists():
                self.repository.mark_missing_if_current(expected)
                self._increment(
                    job_id,
                    skipped=1,
                    message="Track file missing",
                    level="warn",
                    path=str(path),
                )
                return

            metadata, stable_stat = read_audio_metadata_stable(
                path,
                metadata_reader=read_audio_metadata,
            )
            note = metadata.pop(READER_NOTE_KEY, None)
            if note is not None:
                self._append_event(job_id, "warn", str(note), path=str(path))
            if (
                int(stable_stat.st_size) != expected.file_size_bytes
                or int(stable_stat.st_mtime_ns) != expected.file_modified_ns
            ):
                raise RuntimeError(
                    "Source file changed after the tag refresh was queued"
                )
            self.repository.refresh_file_tags(
                expected,
                file_tags_from_metadata(path, metadata),
                technical_file=(
                    scanned_file_from_metadata(
                        path,
                        metadata,
                        file_size_bytes=int(stable_stat.st_size),
                        file_modified_ns=int(stable_stat.st_mtime_ns),
                    )
                    if "audio_format" in metadata
                    else None
                ),
            )
            self._increment(
                job_id,
                updated=1,
                message="Tags and technical metadata refreshed",
                level="ok",
                path=str(path),
            )
        except Exception as error:
            error_text = exception_summary(error)
            log_failure(
                LOGGER,
                "Tag refresh failed job_id=%s path=%s error=%s",
                job_id,
                path,
                error_text,
            )
            self._increment(
                job_id,
                failed=1,
                message=f"Tag refresh failed: {error_text}",
                level="error",
                path=str(path),
            )

    def _finish_cancelled(
        self,
        job_id: str,
        message: str,
    ) -> ScanJobStatus:
        self._update(
            job_id,
            state="cancelled",
            finished_at=time.time(),
            current_path=None,
        )
        self._append_event(job_id, "warn", message)
        return self.get(job_id)

    def _finish_completed(
        self,
        job_id: str,
        *,
        started: float,
        message: str,
    ) -> ScanJobStatus:
        final = self.get(job_id)
        finished = time.time()
        processed = max(1, final.processed)
        self._update(
            job_id,
            state="completed",
            finished_at=finished,
            current_path=None,
            avg_seconds_per_track=(
                finished - (final.started_at or started)
            )
            / processed,
        )
        self._append_event(job_id, "info", message)
        return self.get(job_id)

    def _increment(
        self,
        job_id: str,
        *,
        level: str,
        message: str,
        path: str,
        added: int = 0,
        updated: int = 0,
        unchanged: int = 0,
        skipped: int = 0,
        failed: int = 0,
        log: bool = True,
    ) -> None:
        with self._store.locked(job_id) as status:
            status.processed += 1
            status.added += added
            status.updated += updated
            status.unchanged += unchanged
            status.skipped += skipped
            status.failed += failed
            if status.started_at and status.processed:
                status.avg_seconds_per_track = (
                    time.time() - status.started_at
                ) / status.processed
        self._append_event(
            job_id,
            level,
            message,
            path=path,
            track_event=True,
            log=log,
        )

    def _update(self, job_id: str, **changes: object) -> None:
        self._store.update(job_id, **changes)

    def _append_event(
        self,
        job_id: str,
        level: str,
        message: str,
        *,
        path: str | None = None,
        track_event: bool = False,
        log: bool = True,
    ) -> None:
        if log:
            log_job_event(
                LOGGER,
                level,
                "%s job_id=%s path=%s",
                message,
                job_id,
                path,
                track_event=track_event,
            )
        self._store.append_event(
            job_id,
            ScanLogEvent(
                timestamp=time.time(),
                level=level,
                message=message,
                path=path,
            ),
        )

    @staticmethod
    def _copy_status(status: ScanJobStatus) -> ScanJobStatus:
        return ScanJobStatus(
            job_id=status.job_id,
            state=status.state,
            root=status.root,
            total=status.total,
            processed=status.processed,
            added=status.added,
            updated=status.updated,
            unchanged=status.unchanged,
            skipped=status.skipped,
            failed=status.failed,
            current_path=status.current_path,
            started_at=status.started_at,
            finished_at=status.finished_at,
            avg_seconds_per_track=status.avg_seconds_per_track,
            events=list(status.events),
            cancel_requested=status.cancel_requested,
            workers=status.workers,
            limit=status.limit,
        )


def _selected_extensions(extensions: Collection[str] | None) -> set[str]:
    if extensions is None:
        return set(SUPPORTED_AUDIO_EXTENSIONS)
    selected = {
        extension.lower()
        for extension in extensions
        if extension.lower() in SUPPORTED_AUDIO_EXTENSIONS
    }
    if not selected:
        raise ValueError("at least one supported audio extension is required")
    return selected


def _validate_duration_bounds(
    min_duration_seconds: int | None,
    max_duration_seconds: int | None,
) -> None:
    for label, value in (
        ("min_duration_seconds", min_duration_seconds),
        ("max_duration_seconds", max_duration_seconds),
    ):
        if value is not None and (isinstance(value, bool) or value <= 0):
            raise ValueError(f"{label} must be a positive integer or None")
    if (
        min_duration_seconds is not None
        and max_duration_seconds is not None
        and min_duration_seconds > max_duration_seconds
    ):
        raise ValueError("min_duration_seconds must not exceed max_duration_seconds")
