"""Background and synchronous jobs for the sole v7 scan repository path."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, cast

from .db_tracks import TrackRepository, canonical_file_path
from .job_runtime import JobStore
from .logging_config import exception_summary, log_failure, log_job_event
from .scanner import (
    file_tags_from_metadata,
    iter_audio_files,
    read_audio_metadata,
    read_audio_metadata_stable,
    scan_audio_file,
)
from .track_models import TrackFileState


LOGGER = logging.getLogger(__name__)


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


@dataclass(frozen=True)
class ScanJobPayload:
    paths: list[Path]
    track_states: dict[str, TrackFileState] = field(default_factory=dict)


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
    ) -> str:
        root_path = Path(root).expanduser().resolve(strict=False)
        paths = list(iter_audio_files(root_path))
        job_id = str(uuid.uuid4())
        status = ScanJobStatus(
            job_id=job_id,
            state="queued",
            root=str(root_path),
            total=len(paths),
            workers=max(1, workers),
        )
        self._store.add(
            job_id,
            status,
            payload=ScanJobPayload(paths=paths),
        )
        self._append_event(
            job_id,
            "info",
            f"Scan queued · workers {status.workers}",
            path=str(root_path),
        )
        return job_id

    def start(
        self,
        root: str | Path,
        *,
        workers: int = 1,
    ) -> ScanJobStatus:
        job_id = self.create_job(root, workers=workers)
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
    ) -> ScanJobStatus:
        job_id = self.create_job(root, workers=workers)
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
        if status.workers <= 1:
            for path in payload.paths:
                if self.get(job_id).cancel_requested:
                    return self._finish_cancelled(
                        job_id,
                        "Scan cancelled",
                    )
                self._scan_one(job_id, path)
        else:
            self._run_parallel(
                job_id,
                payload.paths,
                status.workers,
                self._scan_one,
            )
            if self.get(job_id).cancel_requested:
                return self._finish_cancelled(
                    job_id,
                    "Scan cancelled",
                )

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
        paths: list[Path],
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

    def get(self, job_id: str) -> ScanJobStatus:
        return self._store.get(job_id)

    def latest(self) -> ScanJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> ScanJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _scan_one(self, job_id: str, path: Path) -> None:
        self._update(job_id, current_path=str(path))
        try:
            mutation = scan_audio_file(self.repository, path)
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
        except Exception as error:
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
            )
            self._increment(
                job_id,
                updated=1,
                message="Tags refreshed",
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
    ) -> None:
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
        )
