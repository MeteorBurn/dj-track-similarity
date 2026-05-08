from __future__ import annotations

from contextlib import contextmanager
import threading
from typing import Callable, Generic, Iterator, TypeVar


JobStatus = TypeVar("JobStatus")
Item = TypeVar("Item")

MAX_JOB_EVENTS = 200


class JobStore(Generic[JobStatus]):
    def __init__(self, copy_status: Callable[[JobStatus], JobStatus], *, unknown_label: str) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self._lock = threading.Lock()
        self._copy_status = copy_status
        self._unknown_label = unknown_label

    def add(self, job_id: str, status: JobStatus) -> None:
        with self._lock:
            self._jobs[job_id] = status

    def get(self, job_id: str) -> JobStatus:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown {self._unknown_label}: {job_id}")
            return self._copy_status(self._jobs[job_id])

    def latest(self) -> JobStatus | None:
        with self._lock:
            if not self._jobs:
                return None
            return self._copy_status(next(reversed(self._jobs.values())))

    def update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            status = self._jobs[job_id]
            for key, value in changes.items():
                setattr(status, key, value)

    @contextmanager
    def locked(self, job_id: str) -> Iterator[JobStatus]:
        with self._lock:
            yield self._jobs[job_id]

    def append_event(self, job_id: str, event: object, *, limit: int = MAX_JOB_EVENTS) -> None:
        with self._lock:
            status = self._jobs[job_id]
            events = getattr(status, "events")
            events.append(event)
            if len(events) > limit:
                setattr(status, "events", events[-limit:])


def chunks(items: list[Item], size: int):
    for index in range(0, len(items), size):
        yield items[index : index + size]
