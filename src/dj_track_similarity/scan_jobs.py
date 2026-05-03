from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path

from .database import LibraryDatabase
from .scanner import SUPPORTED_AUDIO_EXTENSIONS, read_audio_metadata


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


class ScanJobManager:
    def __init__(self, db: LibraryDatabase) -> None:
        self.db = db
        self._jobs: dict[str, ScanJobStatus] = {}
        self._lock = threading.Lock()

    def create_job(self, root: str | Path, *, workers: int = 1) -> str:
        root_path = Path(root)
        if not root_path.exists():
            raise FileNotFoundError(root_path)
        if not root_path.is_dir():
            raise NotADirectoryError(root_path)
        paths = list(_iter_audio_files(root_path))
        job_id = str(uuid.uuid4())
        status = ScanJobStatus(job_id=job_id, state="queued", root=str(root_path), total=len(paths), workers=max(1, workers))
        status._paths = paths  # type: ignore[attr-defined]
        with self._lock:
            self._jobs[job_id] = status
        self._append_event(job_id, "info", "Scan queued", path=str(root_path))
        return job_id

    def start(self, root: str | Path, *, workers: int = 1) -> ScanJobStatus:
        job_id = self.create_job(root, workers=workers)
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(self, root: str | Path, *, workers: int = 1) -> ScanJobStatus:
        job_id = self.create_job(root, workers=workers)
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> ScanJobStatus:
        status = self.get(job_id)
        paths: list[Path] = getattr(status, "_paths", [])
        if status.cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "Scan cancelled")
            return self.get(job_id)

        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(job_id, "info", "Scan started", path=status.root)
        if status.workers <= 1:
            for path in paths:
                if self.get(job_id).cancel_requested:
                    self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None)
                    self._append_event(job_id, "warn", "Scan cancelled")
                    return self.get(job_id)
                self._scan_one(job_id, path)
        else:
            self._run_parallel(job_id, paths, status.workers)
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None)
                self._append_event(job_id, "warn", "Scan cancelled")
                return self.get(job_id)

        final = self.get(job_id)
        finished = time.time()
        processed = max(1, final.processed)
        self._update(
            job_id,
            state="completed",
            finished_at=finished,
            current_path=None,
            avg_seconds_per_track=(finished - (final.started_at or started)) / processed,
        )
        self._append_event(job_id, "info", "Scan completed")
        return self.get(job_id)

    def _run_parallel(self, job_id: str, paths: list[Path], workers: int) -> None:
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
                    futures[executor.submit(self._scan_one, job_id, path)] = path
                if not futures:
                    return
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    futures.pop(future, None)
                    future.result()

    def _run_sequential(self, job_id: str, paths: list[Path]) -> None:
        for path in paths:
            if self.get(job_id).cancel_requested:
                return
            self._scan_one(job_id, path)

    def get(self, job_id: str) -> ScanJobStatus:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown scan job: {job_id}")
            return self._copy_status(self._jobs[job_id])

    def latest(self) -> ScanJobStatus | None:
        with self._lock:
            if not self._jobs:
                return None
            return self._copy_status(next(reversed(self._jobs.values())))

    def cancel(self, job_id: str) -> ScanJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _scan_one(self, job_id: str, path: Path) -> None:
        self._update(job_id, current_path=str(path))
        try:
            existing = self.db.get_track_by_path(path)
            size = path.stat().st_size
            mtime = path.stat().st_mtime
            if existing and existing.size == size and abs(existing.mtime - mtime) < 0.0001:
                self._increment(job_id, unchanged=1, message="Track unchanged", level="info", path=str(path))
                return
            metadata = read_audio_metadata(path)
            self.db.upsert_track(
                path=path,
                size=size,
                mtime=mtime,
                metadata=metadata,
                bpm=_as_float(metadata.get("bpm")),
                musical_key=_as_string(metadata.get("key") or metadata.get("initialkey")),
                duration=_as_float(metadata.get("duration")),
            )
            if existing:
                self._increment(job_id, updated=1, message="Track updated", level="ok", path=str(path))
            else:
                self._increment(job_id, added=1, message="Track added", level="ok", path=str(path))
        except Exception as error:
            self._increment(job_id, failed=1, message=f"Track failed: {error}", level="error", path=str(path))

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
        with self._lock:
            status = self._jobs[job_id]
            status.processed += 1
            status.added += added
            status.updated += updated
            status.unchanged += unchanged
            status.skipped += skipped
            status.failed += failed
            if status.started_at and status.processed:
                status.avg_seconds_per_track = (time.time() - status.started_at) / status.processed
        self._append_event(job_id, level, message, path=path)

    def _update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            status = self._jobs[job_id]
            for key, value in changes.items():
                setattr(status, key, value)

    def _append_event(self, job_id: str, level: str, message: str, *, path: str | None = None) -> None:
        with self._lock:
            status = self._jobs[job_id]
            status.events.append(ScanLogEvent(timestamp=time.time(), level=level, message=message, path=path))
            if len(status.events) > 200:
                status.events = status.events[-200:]

    @staticmethod
    def _copy_status(status: ScanJobStatus) -> ScanJobStatus:
        copy = ScanJobStatus(
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
        if hasattr(status, "_paths"):
            copy._paths = getattr(status, "_paths")  # type: ignore[attr-defined]
        return copy


def _iter_audio_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
            yield path


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
