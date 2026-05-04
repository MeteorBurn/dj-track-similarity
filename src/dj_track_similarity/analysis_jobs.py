from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .database import LibraryDatabase
from .embedding import EmbeddingAdapter, FakeEmbeddingAdapter, MertEmbeddingAdapter
from .models import Track


AdapterFactory = Callable[[], EmbeddingAdapter]


@dataclass(frozen=True)
class AnalysisTrackError:
    track_id: int
    path: str
    error: str


@dataclass(frozen=True)
class AnalysisLogEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None
    track_id: int | None = None


@dataclass
class AnalysisJobStatus:
    job_id: str
    state: str
    adapter_name: str
    model_name: str | None = None
    device: str | None = None
    device_requested: str = "auto"
    total: int = 0
    processed: int = 0
    analyzed: int = 0
    failed: int = 0
    current_path: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    avg_seconds_per_track: float | None = None
    errors: list[AnalysisTrackError] = field(default_factory=list)
    events: list[AnalysisLogEvent] = field(default_factory=list)
    cancel_requested: bool = False
    workers: int = 1
    batch_size: int = 1


class AnalysisJobManager:
    def __init__(
        self,
        db: LibraryDatabase,
        adapter_factories: dict[str, AdapterFactory] | None = None,
        *,
        batch_size: int = 4,
    ) -> None:
        self.db = db
        self.adapter_factories = adapter_factories or {
            "mert": MertEmbeddingAdapter,
            "fake": FakeEmbeddingAdapter,
        }
        self.batch_size = max(1, batch_size)
        self._jobs: dict[str, AnalysisJobStatus] = {}
        self._lock = threading.Lock()

    def create_job(
        self,
        *,
        adapter_name: str,
        limit: int | None = None,
        workers: int | None = None,
        batch_size: int | None = None,
        device: str = "auto",
    ) -> str:
        if adapter_name not in self.adapter_factories:
            raise ValueError(f"Unknown analysis adapter: {adapter_name}")
        tracks = self.db.list_tracks(with_embeddings=False)
        if limit is not None:
            tracks = tracks[:limit]
        job_id = str(uuid.uuid4())
        effective_batch_size = max(1, int(batch_size or workers or self.batch_size))
        status = AnalysisJobStatus(
            job_id=job_id,
            state="queued",
            adapter_name=adapter_name,
            total=len(tracks),
            device_requested=device,
            workers=effective_batch_size,
            batch_size=effective_batch_size,
        )
        status._tracks = tracks  # type: ignore[attr-defined]
        with self._lock:
            self._jobs[job_id] = status
        self._append_event(job_id, "info", "Analysis queued")
        return job_id

    def start(
        self,
        *,
        adapter_name: str,
        limit: int | None = None,
        workers: int | None = None,
        batch_size: int | None = None,
        device: str = "auto",
    ) -> AnalysisJobStatus:
        job_id = self.create_job(
            adapter_name=adapter_name,
            limit=limit,
            workers=workers,
            batch_size=batch_size,
            device=device,
        )
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(
        self,
        *,
        adapter_name: str,
        limit: int | None = None,
        workers: int | None = None,
        batch_size: int | None = None,
        device: str = "auto",
    ) -> AnalysisJobStatus:
        job_id = self.create_job(
            adapter_name=adapter_name,
            limit=limit,
            workers=workers,
            batch_size=batch_size,
            device=device,
        )
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> AnalysisJobStatus:
        status = self.get(job_id)
        tracks: list[Track] = getattr(status, "_tracks", [])
        if status.cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "Analysis cancelled")
            return self.get(job_id)

        adapter = self._create_adapter(status.adapter_name, device=status.device_requested, batch_size=status.batch_size)
        model_name = getattr(adapter, "model_name", status.adapter_name)
        device = getattr(adapter, "device", None) or getattr(adapter, "device_name", None)
        if device is None and hasattr(adapter, "_device"):
            try:
                device = adapter._device()  # type: ignore[attr-defined]
            except Exception:
                device = None
        started = time.time()
        self._update(job_id, state="running", model_name=model_name, device=device, started_at=started)
        self._append_event(job_id, "info", "Analysis started")

        for batch in _chunks(tracks, max(1, status.batch_size)):
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None)
                self._append_event(job_id, "warn", "Analysis cancelled")
                return self.get(job_id)
            self._update(job_id, current_path=batch[0].path if batch else None)
            self._process_batch(job_id, adapter, batch)
            self._refresh_adapter_runtime_metadata(job_id, adapter)

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
        self._append_event(job_id, "info", "Analysis completed")
        return self.get(job_id)

    def get(self, job_id: str) -> AnalysisJobStatus:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown analysis job: {job_id}")
            return self._copy_status(self._jobs[job_id])

    def latest(self) -> AnalysisJobStatus | None:
        with self._lock:
            if not self._jobs:
                return None
            return self._copy_status(next(reversed(self._jobs.values())))

    def cancel(self, job_id: str) -> AnalysisJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _create_adapter(self, adapter_name: str, *, device: str, batch_size: int) -> EmbeddingAdapter:
        factory = self.adapter_factories[adapter_name]
        try:
            return factory(device=device, inference_batch_size=batch_size)  # type: ignore[misc,call-arg]
        except TypeError:
            return factory()

    def _process_batch(self, job_id: str, adapter: EmbeddingAdapter, batch: list[Track]) -> None:
        paths = [track.path for track in batch]
        try:
            if hasattr(adapter, "embed_batch"):
                vectors = adapter.embed_batch(paths)  # type: ignore[attr-defined]
            else:
                vectors = [adapter.embed(path) for path in paths]
            for track, vector in zip(batch, vectors):
                self._save_success(job_id, adapter, track, vector)
        except Exception:
            for track in batch:
                try:
                    vector = adapter.embed(track.path)
                    self._save_success(job_id, adapter, track, vector)
                except Exception as error:
                    self._save_failure(job_id, track, error)

    def _refresh_adapter_runtime_metadata(self, job_id: str, adapter: EmbeddingAdapter) -> None:
        device = getattr(adapter, "device", None) or getattr(adapter, "device_name", None)
        model_name = getattr(adapter, "model_name", None)
        changes = {}
        if device:
            changes["device"] = device
        if model_name:
            changes["model_name"] = model_name
        if changes:
            self._update(job_id, **changes)

    def _save_success(self, job_id: str, adapter: EmbeddingAdapter, track: Track, vector: np.ndarray) -> None:
        self.db.save_embedding(track.id, vector, adapter.model_name, getattr(adapter, "dim", None))
        self._update_progress(job_id, track.path, analyzed_delta=1)
        self._append_event(job_id, "ok", "Track analyzed", path=track.path, track_id=track.id)

    def _save_failure(self, job_id: str, track: Track, error: Exception) -> None:
        status = self.get(job_id)
        errors = list(status.errors)
        errors.append(AnalysisTrackError(track_id=track.id, path=track.path, error=str(error)))
        self._update_progress(job_id, track.path, failed_delta=1, errors=errors)
        self._append_event(job_id, "error", f"Track failed: {error}", path=track.path, track_id=track.id)

    def _update_progress(
        self,
        job_id: str,
        current_path: str,
        *,
        analyzed_delta: int = 0,
        failed_delta: int = 0,
        errors: list[AnalysisTrackError] | None = None,
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
        with self._lock:
            status = self._jobs[job_id]
            status.events.append(
                AnalysisLogEvent(
                    timestamp=time.time(),
                    level=level,
                    message=message,
                    path=path,
                    track_id=track_id,
                )
            )
            if len(status.events) > 200:
                status.events = status.events[-200:]

    @staticmethod
    def _copy_status(status: AnalysisJobStatus) -> AnalysisJobStatus:
        copy = AnalysisJobStatus(
            job_id=status.job_id,
            state=status.state,
            adapter_name=status.adapter_name,
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


def _chunks(tracks: list[Track], size: int):
    for index in range(0, len(tracks), size):
        yield tracks[index : index + size]
