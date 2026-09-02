"""Single-threaded lifecycle for explicit database validation."""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

from .database_validation import DatabaseValidator, ValidationFinding, format_validation_finding
from .job_runtime import JobStore
from .logging_config import event_log_level

LOGGER = logging.getLogger(__name__)

# The event log is a recency tail that a clean library fills with `ok` rows, so
# findings keep their own list. It is bounded because one missing library row
# makes every track, embedding and feature row a finding at once, and the whole
# status is polled once per second.
MAX_VALIDATION_FAILURES = 500


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
    checked: int = 0
    warnings: int = 0
    errors: int = 0
    current_entity: str | None = None
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
        self._store.update(job_id, state="running", started_at=time.time())
        LOGGER.info("Database validation started job_id=%s", job_id)

        def emit(f: ValidationFinding) -> None:
            message = format_validation_finding(f)
            if f.level != "ok":
                LOGGER.log(event_log_level(f.level), "%s", message)
            # Counters and the failure list move under one lock; append_event
            # takes the same lock and must therefore stay outside this block.
            with self._store.locked(job_id) as status:
                status.checked += 1
                status.warnings += f.level == "warning"
                status.errors += f.level == "error"
                status.current_entity = f.entity
                if f.level != "ok":
                    if len(status.failures) < MAX_VALIDATION_FAILURES:
                        status.failures.append(
                            DatabaseValidationFailure(f.level, f.code, f.message, f.table, f.track_id, f.path)
                        )
                    else:
                        status.failures_omitted += 1
            self._store.append_event(job_id, DatabaseValidationEvent(time.time(), f.level, message, f.table, f.track_id, f.path))

        def cancel_requested() -> bool:
            with self._store.locked(job_id) as status:
                return status.cancel_requested

        try:
            report = DatabaseValidator(self.database_path).run(emit, cancel_requested)
            state = "cancelled" if report.cancelled else "completed"
            self._store.update(job_id, state=state, finished_at=time.time())
            LOGGER.info("Database validation %s job_id=%s checked=%s warnings=%s errors=%s", state, job_id, report.checked, report.warning_count, report.error_count)
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
