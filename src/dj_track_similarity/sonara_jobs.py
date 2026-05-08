from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field

from .database import LibraryDatabase
from .logging_config import event_log_level, exception_summary
from .models import Track
from .sonara_features import SONARA_MODEL_NAME, analyze_and_store_sonara_features


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SonaraTrackError:
    track_id: int
    path: str
    error: str


@dataclass(frozen=True)
class SonaraLogEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None
    track_id: int | None = None


@dataclass
class SonaraJobStatus:
    job_id: str
    state: str
    adapter_name: str = "sonara"
    embedding_key: str = "sonara"
    model_name: str | None = SONARA_MODEL_NAME
    device: str | None = "cpu"
    device_requested: str = "cpu"
    total: int = 0
    processed: int = 0
    analyzed: int = 0
    failed: int = 0
    current_path: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    avg_seconds_per_track: float | None = None
    errors: list[SonaraTrackError] = field(default_factory=list)
    events: list[SonaraLogEvent] = field(default_factory=list)
    cancel_requested: bool = False
    workers: int = 1
    batch_size: int = 1


class SonaraFeatureJobManager:
    def __init__(self, db: LibraryDatabase) -> None:
        self.db = db
        self._jobs: dict[str, SonaraJobStatus] = {}
        self._lock = threading.Lock()

    def create_job(self, *, limit: int | None = None) -> str:
        tracks = [track for track in self.db.list_tracks() if "sonara_features" not in track.metadata]
        if limit is not None:
            tracks = tracks[:limit]
        job_id = str(uuid.uuid4())
        status = SonaraJobStatus(job_id=job_id, state="queued", total=len(tracks))
        status._tracks = tracks  # type: ignore[attr-defined]
        with self._lock:
            self._jobs[job_id] = status
        self._append_event(job_id, "info", "Sonara feature analysis queued")
        return job_id

    def start(self, *, limit: int | None = None) -> SonaraJobStatus:
        job_id = self.create_job(limit=limit)
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(self, *, limit: int | None = None) -> SonaraJobStatus:
        job_id = self.create_job(limit=limit)
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> SonaraJobStatus:
        status = self.get(job_id)
        tracks: list[Track] = getattr(status, "_tracks", [])
        if status.cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "Sonara feature analysis cancelled")
            return self.get(job_id)

        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(job_id, "info", "Sonara feature analysis started")
        for track in tracks:
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None)
                self._append_event(job_id, "warn", "Sonara feature analysis cancelled")
                return self.get(job_id)
            self._update(job_id, current_path=track.path)
            try:
                analyze_and_store_sonara_features(self.db, track)
                self._update_progress(job_id, track.path, analyzed_delta=1)
                self._append_event(job_id, "ok", "Sonara features saved to database", path=track.path, track_id=track.id)
            except Exception as error:
                self._save_failure(job_id, track, error)

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
        self._append_event(job_id, "info", "Sonara feature analysis completed")
        return self.get(job_id)

    def get(self, job_id: str) -> SonaraJobStatus:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown sonara job: {job_id}")
            return self._copy_status(self._jobs[job_id])

    def latest(self) -> SonaraJobStatus | None:
        with self._lock:
            if not self._jobs:
                return None
            return self._copy_status(next(reversed(self._jobs.values())))

    def cancel(self, job_id: str) -> SonaraJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _save_failure(self, job_id: str, track: Track, error: Exception) -> None:
        error_text = exception_summary(error)
        LOGGER.exception("Sonara track failed job_id=%s track_id=%s path=%s", job_id, track.id, track.path)
        status = self.get(job_id)
        errors = list(status.errors)
        errors.append(SonaraTrackError(track_id=track.id, path=track.path, error=error_text))
        self._update_progress(job_id, track.path, failed_delta=1, errors=errors)
        self._append_event(job_id, "error", f"Track failed: {error_text}", path=track.path, track_id=track.id)

    def _update_progress(
        self,
        job_id: str,
        current_path: str,
        *,
        analyzed_delta: int = 0,
        failed_delta: int = 0,
        errors: list[SonaraTrackError] | None = None,
    ) -> None:
        with self._lock:
            status = self._jobs[job_id]
            status.current_path = current_path
            status.processed += 1
            status.analyzed += analyzed_delta
            status.failed += failed_delta
            if errors is not None:
                status.errors = errors
            if status.started_at and status.processed:
                status.avg_seconds_per_track = (time.time() - status.started_at) / status.processed

    def _update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            status = self._jobs[job_id]
            for key, value in changes.items():
                setattr(status, key, value)

    def _append_event(
        self,
        job_id: str,
        level: str,
        message: str,
        *,
        path: str | None = None,
        track_id: int | None = None,
    ) -> None:
        LOGGER.log(
            event_log_level(level),
            "%s job_id=%s track_id=%s path=%s",
            message,
            job_id,
            track_id,
            path,
        )
        with self._lock:
            status = self._jobs[job_id]
            status.events.append(SonaraLogEvent(time.time(), level, message, path, track_id))
            if len(status.events) > 200:
                status.events = status.events[-200:]

    @staticmethod
    def _copy_status(status: SonaraJobStatus) -> SonaraJobStatus:
        copy = SonaraJobStatus(
            job_id=status.job_id,
            state=status.state,
            adapter_name=status.adapter_name,
            embedding_key=status.embedding_key,
            model_name=status.model_name,
            device=status.device,
            device_requested=status.device_requested,
            total=status.total,
            processed=status.processed,
            analyzed=status.analyzed,
            failed=status.failed,
            current_path=status.current_path,
            started_at=status.started_at,
            finished_at=status.finished_at,
            avg_seconds_per_track=status.avg_seconds_per_track,
            errors=list(status.errors),
            events=list(status.events),
            cancel_requested=status.cancel_requested,
            workers=status.workers,
            batch_size=status.batch_size,
        )
        if hasattr(status, "_tracks"):
            copy._tracks = getattr(status, "_tracks")  # type: ignore[attr-defined]
        return copy
