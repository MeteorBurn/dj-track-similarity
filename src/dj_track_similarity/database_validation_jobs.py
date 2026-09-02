"""Single-threaded lifecycle for explicit database validation."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

from .database_validation import (
    DatabaseValidator,
    TrackValidation,
    ValidationFinding,
    describe_validation_finding,
    format_validation_finding,
)
from .job_runtime import JobStore
from .logging_config import event_log_level

LOGGER = logging.getLogger(__name__)

# The event log is a recency tail that a clean library fills with `ok` rows, so
# findings keep their own list. It is bounded because one missing library row
# makes every track, embedding and feature row a finding at once, and the whole
# status is polled once per second.
MAX_VALIDATION_FAILURES = 500


def _ui_level(level: str) -> str:
    """Map a finding level onto the levels the log panel styles."""
    return "warn" if level == "warning" else level


@dataclass(frozen=True)
class DatabaseValidationEvent:
    timestamp: float
    level: str
    message: str
    table: str | None = None
    track_id: int | None = None
    path: str | None = None


@dataclass(frozen=True)
class DatabaseValidationFailure:
    level: str
    code: str
    message: str
    table: str | None = None
    track_id: int | None = None
    path: str | None = None


@dataclass
class DatabaseValidationJobStatus:
    job_id: str
    state: str
    total: int = 0
    processed: int = 0
    valid: int = 0
    warned: int = 0
    failed: int = 0
    checked: int = 0
    warnings: int = 0
    errors: int = 0
    current_entity: str | None = None
    current_path: str | None = None
    avg_seconds_per_track: float | None = None
    started_at: float | None = None
    finished_at: float | None = None
    events: list[DatabaseValidationEvent] = field(default_factory=list)
    failures: list[DatabaseValidationFailure] = field(default_factory=list)
    failures_omitted: int = 0
    cancel_requested: bool = False


class DatabaseValidationJobManager:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        self._store = JobStore(self._copy, unknown_label="database validation job")
        self._start_lock = threading.Lock()

    def start(self) -> DatabaseValidationJobStatus:
        job_id = self._queue_job()
        threading.Thread(target=self.run_job, args=(job_id,), daemon=True).start()
        return self.get(job_id)

    def run_sync(self) -> DatabaseValidationJobStatus:
        job_id = self._queue_job()
        return self.run_job(job_id)

    def _queue_job(self) -> str:
        with self._start_lock:
            latest = self.latest()
            if latest is not None and latest.state in {"queued", "running"}:
                raise RuntimeError("Database validation is already running")
            job_id = str(uuid.uuid4())
            self._store.add(job_id, DatabaseValidationJobStatus(job_id, "queued"))
            return job_id

    def run_job(self, job_id: str) -> DatabaseValidationJobStatus:
        started_at = time.time()
        self._store.update(job_id, state="running", started_at=started_at)
        LOGGER.info("Database validation started job_id=%s", job_id)
        validator = DatabaseValidator(self.database_path)

        def count(f: ValidationFinding, status: DatabaseValidationJobStatus) -> None:
            """Update the row-level counters. The caller already holds the lock."""
            status.checked += 1
            status.warnings += f.level == "warning"
            status.errors += f.level == "error"
            # `ok` rows and the closing `info` coverage line are not failures.
            if f.level not in {"warning", "error"}:
                return
            if len(status.failures) < MAX_VALIDATION_FAILURES:
                status.failures.append(
                    DatabaseValidationFailure(f.level, f.code, f.message, f.table, f.track_id, f.path)
                )
            else:
                status.failures_omitted += 1

        def emit(f: ValidationFinding) -> None:
            """Log one finding that belongs to no track: database, library, orphan."""
            if f.level != "ok":
                LOGGER.log(event_log_level(f.level), "%s", format_validation_finding(f))
            # Counters and the failure list move under one lock; append_event
            # takes the same lock and must therefore stay outside this block.
            with self._store.locked(job_id) as status:
                count(f, status)
                status.current_entity = f.entity
            self._store.append_event(job_id, DatabaseValidationEvent(time.time(), _ui_level(f.level), describe_validation_finding(f), f.table, f.track_id, f.path))

        def emit_track(track: TrackValidation) -> None:
            """Log one line per validated track, the way the analysis job does."""
            level = track.level
            message = track.message
            if level != "ok":
                LOGGER.log(
                    event_log_level(level),
                    "%s job_id=%s track_id=%s path=%s",
                    message,
                    job_id,
                    track.track_id,
                    track.path,
                )
            with self._store.locked(job_id) as status:
                for finding in track.findings:
                    count(finding, status)
                status.processed += 1
                status.valid += level == "ok"
                status.warned += level == "warning"
                status.failed += level == "error"
                status.current_entity = "track"
                status.current_path = track.path
                status.avg_seconds_per_track = (time.time() - started_at) / status.processed
            self._store.append_event(job_id, DatabaseValidationEvent(time.time(), _ui_level(level), message, "tracks", track.track_id, track.path))

        def cancel_requested() -> bool:
            with self._store.locked(job_id) as status:
                return status.cancel_requested

        try:
            self._store.update(job_id, total=validator.track_count())
            report = validator.run(emit, cancel_requested, emit_track)
            state = "cancelled" if report.cancelled else "completed"
            self._store.update(job_id, state=state, finished_at=time.time())
            LOGGER.info(
                "Database validation %s job_id=%s tracks=%s checked=%s warnings=%s errors=%s",
                state,
                job_id,
                report.tracks_checked,
                report.checked,
                report.warning_count,
                report.error_count,
            )
        except Exception as error:
            self._store.update(job_id, state="failed", finished_at=time.time())
            emit(ValidationFinding("error", "validation_failed", "database", str(error)))
        return self.get(job_id)

    def get(self, job_id: str) -> DatabaseValidationJobStatus:
        return self._store.get(job_id)

    def latest(self) -> DatabaseValidationJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> DatabaseValidationJobStatus:
        self._store.update(job_id, cancel_requested=True)
        return self.get(job_id)

    @staticmethod
    def _copy(value: DatabaseValidationJobStatus) -> DatabaseValidationJobStatus:
        return DatabaseValidationJobStatus(
            **{
                **value.__dict__,
                "events": list(value.events),
                "failures": list(value.failures),
            }
        )
