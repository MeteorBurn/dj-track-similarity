"""Single-threaded lifecycle for explicit database optimization.

The job runs ``db_optimize.optimize_database`` on the selected library: a
verified backup, FTS merge, ``VACUUM``, ``ANALYZE``, checkpoint, and a second
verification. It holds the per-database write lock for the whole run so the
process's own writers wait instead of colliding with ``VACUUM``; the API layer
refuses to start it while any other job is active.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .db_connection import write_lock_for_path
from .db_optimize import OptimizationError, OptimizationSummary, optimize_database
from .job_runtime import JobStore
from .logging_config import event_log_level

LOGGER = logging.getLogger(__name__)

# Phases the optimizer reports as ``info`` events, in order, so the UI can draw
# a step progress bar for a run that has no row count to measure.
OPTIMIZATION_PHASES = (
    "inspect",
    "backup",
    "optimize",
    "verify",
)


@dataclass(frozen=True)
class DatabaseOptimizationEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None


@dataclass(frozen=True)
class OptimizedFileSummary:
    role: str
    path: str
    backup_path: str
    journal_mode: str
    size_before: int
    size_after: int
    checkpoint: str | None


@dataclass
class DatabaseOptimizationJobStatus:
    job_id: str
    state: str
    phase: str | None = None
    phase_index: int = 0
    phase_count: int = len(OPTIMIZATION_PHASES)
    database_kind: str | None = None
    size_before: int | None = None
    size_after: int | None = None
    files: list[OptimizedFileSummary] = field(default_factory=list)
    error: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    events: list[DatabaseOptimizationEvent] = field(default_factory=list)


class DatabaseOptimizationJobManager:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self._store = JobStore(self._copy, unknown_label="database optimization job")
        self._start_lock = threading.Lock()

    def start(self) -> DatabaseOptimizationJobStatus:
        job_id = self._queue_job()
        threading.Thread(target=self.run_job, args=(job_id,), daemon=True).start()
        return self.get(job_id)

    def run_sync(self) -> DatabaseOptimizationJobStatus:
        job_id = self._queue_job()
        return self.run_job(job_id)

    def _queue_job(self) -> str:
        with self._start_lock:
            latest = self.latest()
            if latest is not None and latest.state in {"queued", "running"}:
                raise RuntimeError("Database optimization is already running")
            job_id = str(uuid.uuid4())
            self._store.add(job_id, DatabaseOptimizationJobStatus(job_id, "queued"))
            return job_id

    def run_job(self, job_id: str) -> DatabaseOptimizationJobStatus:
        self._store.update(job_id, state="running", started_at=time.time(), phase="inspect")
        LOGGER.info("Database optimization started job_id=%s path=%s", job_id, self.database_path)

        def emit(level: str, message: str, path: str | None) -> None:
            LOGGER.log(
                event_log_level(level),
                "%s job_id=%s path=%s",
                message,
                job_id,
                path,
            )
            phase = _phase_of(message)
            if phase is not None:
                self._store.update(
                    job_id,
                    phase=phase,
                    phase_index=OPTIMIZATION_PHASES.index(phase),
                )
            self._store.append_event(
                job_id, DatabaseOptimizationEvent(time.time(), level, message, path)
            )

        try:
            with write_lock_for_path(self.database_path):
                summary = optimize_database(self.database_path, on_event=emit)
        except (OptimizationError, sqlite3.Error, OSError, ValueError) as error:
            self._store.update(
                job_id, state="failed", error=str(error), finished_at=time.time()
            )
            emit("error", f"Database optimization failed: {error}", str(self.database_path))
            return self.get(job_id)
        self._finish(job_id, summary)
        return self.get(job_id)

    def _finish(self, job_id: str, summary: OptimizationSummary) -> None:
        self._store.update(
            job_id,
            state="completed",
            phase=None,
            phase_index=len(OPTIMIZATION_PHASES),
            database_kind=summary.database_kind,
            size_before=summary.size_before,
            size_after=summary.size_after,
            files=[
                OptimizedFileSummary(
                    role=item.role,
                    path=str(item.path),
                    backup_path=str(item.backup_path),
                    journal_mode=item.journal_mode,
                    size_before=item.size_before,
                    size_after=item.size_after,
                    checkpoint=item.checkpoint,
                )
                for item in summary.files
            ],
            finished_at=time.time(),
        )
        LOGGER.info(
            "Database optimization completed job_id=%s size_before=%s size_after=%s backups=%s",
            job_id,
            summary.size_before,
            summary.size_after,
            ", ".join(str(path) for path in summary.backup_paths),
        )

    def get(self, job_id: str) -> DatabaseOptimizationJobStatus:
        return self._store.get(job_id)

    def latest(self) -> DatabaseOptimizationJobStatus | None:
        return self._store.latest()

    @staticmethod
    def _copy(value: DatabaseOptimizationJobStatus) -> DatabaseOptimizationJobStatus:
        return DatabaseOptimizationJobStatus(
            **{
                **value.__dict__,
                "files": list(value.files),
                "events": list(value.events),
            }
        )


def _phase_of(message: str) -> str | None:
    """Map an optimizer event to its phase by the verb the event starts with."""

    if message.startswith("Verified ") and "after optimization" in message:
        return "verify"
    if message.startswith("Backing up ") or message.startswith("Backup of "):
        return "backup"
    if message.startswith("Optimizing ") or message.startswith("Checkpoint "):
        return "optimize"
    if message.startswith("Verified ") or message.startswith("Free space "):
        return "inspect"
    return None
