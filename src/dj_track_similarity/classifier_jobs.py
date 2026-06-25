from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from .classifier_scoring import ClassifierScorer, default_classifier_model_path
from .database import LibraryDatabase
from .job_runtime import JobStore
from .logging_config import exception_summary, log_failure, log_job_event
from .models import Track


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifierTrackError:
    track_id: int
    path: str
    error: str


@dataclass(frozen=True)
class ClassifierLogEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None
    track_id: int | None = None


@dataclass
class ClassifierJobStatus:
    job_id: str
    state: str
    adapter_name: str
    embedding_key: str
    model_name: str | None = None
    device: str | None = "cpu"
    device_requested: str = "cpu"
    total: int = 0
    processed: int = 0
    analyzed: int = 0
    skipped: int = 0
    failed: int = 0
    current_path: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    avg_seconds_per_track: float | None = None
    errors: list[ClassifierTrackError] = field(default_factory=list)
    events: list[ClassifierLogEvent] = field(default_factory=list)
    cancel_requested: bool = False
    workers: int = 1
    batch_size: int = 1


class ClassifierJobManager:
    def __init__(self, db: LibraryDatabase) -> None:
        self.db = db
        self._store = JobStore(self._copy_status, unknown_label="classifier job")

    def create_job(self, *, classifier: str, limit: int | None = None) -> str:
        tracks = self.db.list_tracks_missing_classifier(classifier, limit=limit)
        job_id = str(uuid.uuid4())
        status = ClassifierJobStatus(
            job_id=job_id,
            state="queued",
            adapter_name=classifier,
            embedding_key=classifier,
            total=len(tracks),
        )
        self._store.add(job_id, status, payload=tracks)
        self._append_event(job_id, "info", f"{classifier} classification queued")
        return job_id

    def start(
        self,
        *,
        classifier: str,
        limit: int | None = None,
        model_path: str | Path | None = None,
    ) -> ClassifierJobStatus:
        job_id = self.create_job(classifier=classifier, limit=limit)
        thread = threading.Thread(target=self.run_job, args=(job_id, classifier, model_path), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_job(self, job_id: str, classifier: str, model_path: str | Path | None = None) -> ClassifierJobStatus:
        status = self.get(job_id)
        tracks = cast(list[Track], self._store.payload(job_id) or [])
        if status.cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", f"{classifier} classification cancelled")
            return self.get(job_id)

        started = time.time()
        path = Path(model_path) if model_path is not None else default_classifier_model_path(classifier)
        self._update(job_id, state="running", started_at=started, model_name=str(path))
        self._append_event(job_id, "info", f"{classifier} classification started")

        try:
            scorer = ClassifierScorer(self.db, classifier=classifier, model_path=path)
        except Exception as error:
            error_text = exception_summary(error)
            self._update(job_id, state="failed", finished_at=time.time())
            self._append_event(job_id, "error", error_text)
            raise
        for warning in getattr(scorer, "manifest_warnings", ()):
            self._append_event(job_id, "warn", str(warning))

        for track in tracks:
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None)
                self._append_event(job_id, "warn", f"{classifier} classification cancelled")
                return self.get(job_id)
            self._score_one(job_id, scorer, track)

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
        self._append_event(job_id, "info", f"{classifier} classification completed")
        return self.get(job_id)

    def get(self, job_id: str, *, classifier: str | None = None) -> ClassifierJobStatus:
        status = self._store.get(job_id)
        if classifier is not None and status.adapter_name != classifier:
            raise KeyError(f"Unknown classifier job for {classifier}: {job_id}")
        return status

    def latest(self, *, classifier: str | None = None) -> ClassifierJobStatus | None:
        if classifier is None:
            return self._store.latest()
        return self._store.latest_matching(lambda status: status.adapter_name == classifier)

    def cancel(self, job_id: str, *, classifier: str | None = None) -> ClassifierJobStatus:
        self.get(job_id, classifier=classifier)
        self._update(job_id, cancel_requested=True)
        return self.get(job_id, classifier=classifier)

    def _score_one(self, job_id: str, scorer: ClassifierScorer, track: Track) -> None:
        self._update(job_id, current_path=track.path)
        try:
            result = scorer.score_track(track)
            if result is None:
                self._update_progress(job_id, track.path, skipped_delta=1)
                return
            scorer.save_score(track, result)
            self._update_progress(job_id, track.path, analyzed_delta=1)
        except Exception as error:
            self._save_failure(job_id, track, error)

    def _update_progress(
        self,
        job_id: str,
        current_path: str,
        *,
        analyzed_delta: int = 0,
        skipped_delta: int = 0,
    ) -> None:
        with self._store.locked(job_id) as status:
            status.current_path = current_path
            status.processed += 1
            status.analyzed += analyzed_delta
            status.skipped += skipped_delta
            if status.started_at and status.processed:
                status.avg_seconds_per_track = (time.time() - status.started_at) / status.processed

    def _save_failure(self, job_id: str, track: Track, error: Exception) -> None:
        error_text = exception_summary(error)
        log_failure(
            LOGGER,
            "Classifier track failed job_id=%s track_id=%s path=%s error=%s",
            job_id,
            track.id,
            track.path,
            error_text,
        )
        with self._store.locked(job_id) as status:
            status.current_path = track.path
            status.processed += 1
            status.failed += 1
            status.errors.append(ClassifierTrackError(track_id=track.id, path=track.path, error=error_text))
            if status.started_at and status.processed:
                status.avg_seconds_per_track = (time.time() - status.started_at) / status.processed
        self._append_event(job_id, "error", f"Track failed: {error_text}", path=track.path, track_id=track.id)

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
            track_event=False,
        )
        self._store.append_event(job_id, ClassifierLogEvent(time.time(), level, message, path, track_id))

    @staticmethod
    def _copy_status(status: ClassifierJobStatus) -> ClassifierJobStatus:
        return ClassifierJobStatus(
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
            skipped=status.skipped,
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
