from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .database import LibraryDatabase
from .genres import MaestGenreAdapter, genre_adapter_factories as default_genre_adapter_factories
from .models import Track


class GenreAdapter(Protocol):
    model_name: str
    device: str | None

    def predict(self, path: str) -> list[dict[str, object]]:
        ...


GenreAdapterFactory = Callable[..., GenreAdapter]


@dataclass(frozen=True)
class GenreTrackError:
    track_id: int
    path: str
    error: str


@dataclass(frozen=True)
class GenreLogEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None
    track_id: int | None = None


@dataclass
class GenreJobStatus:
    job_id: str
    state: str
    adapter_name: str = "maest"
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
    errors: list[GenreTrackError] = field(default_factory=list)
    events: list[GenreLogEvent] = field(default_factory=list)
    cancel_requested: bool = False
    top_k: int = 3
    batch_size: int = 1
    workers: int = 1


class GenreAnalysisJobManager:
    def __init__(
        self,
        db: LibraryDatabase,
        adapter_factories: dict[str, GenreAdapterFactory] | None = None,
    ) -> None:
        self.db = db
        self.adapter_factories = adapter_factories or default_genre_adapter_factories()
        self._jobs: dict[str, GenreJobStatus] = {}
        self._lock = threading.Lock()

    def create_job(self, *, limit: int | None = None, device: str = "auto", top_k: int = 3) -> str:
        tracks = [track for track in self.db.list_tracks() if not track.genres]
        if limit is not None:
            tracks = tracks[:limit]
        job_id = str(uuid.uuid4())
        status = GenreJobStatus(
            job_id=job_id,
            state="queued",
            total=len(tracks),
            device_requested=device,
            top_k=max(1, int(top_k)),
        )
        status._tracks = tracks  # type: ignore[attr-defined]
        with self._lock:
            self._jobs[job_id] = status
        self._append_event(job_id, "info", "MAEST genre analysis queued")
        return job_id

    def start(self, *, limit: int | None = None, device: str = "auto", top_k: int = 3) -> GenreJobStatus:
        job_id = self.create_job(limit=limit, device=device, top_k=top_k)
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(self, *, limit: int | None = None, device: str = "auto", top_k: int = 3) -> GenreJobStatus:
        job_id = self.create_job(limit=limit, device=device, top_k=top_k)
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> GenreJobStatus:
        status = self.get(job_id)
        tracks: list[Track] = getattr(status, "_tracks", [])
        if status.cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "MAEST genre analysis cancelled")
            return self.get(job_id)

        adapter = self._create_adapter(device=status.device_requested, top_k=status.top_k)
        started = time.time()
        self._update(
            job_id,
            state="running",
            model_name=getattr(adapter, "model_name", "maest"),
            device=getattr(adapter, "device", None),
            started_at=started,
        )
        self._append_event(job_id, "info", "MAEST genre analysis started")
        for track in tracks:
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None)
                self._append_event(job_id, "warn", "MAEST genre analysis cancelled")
                return self.get(job_id)
            self._update(job_id, current_path=track.path)
            try:
                genres = adapter.predict(track.path)
                self.db.save_genres(track.id, genres, model_name=adapter.model_name)
                self._update_progress(job_id, track.path, analyzed_delta=1)
                self._append_event(job_id, "ok", "Genres analyzed", path=track.path, track_id=track.id)
            except Exception as error:
                self._save_failure(job_id, track, error)
            device = getattr(adapter, "device", None)
            if device:
                self._update(job_id, device=device)

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
        self._append_event(job_id, "info", "MAEST genre analysis completed")
        return self.get(job_id)

    def get(self, job_id: str) -> GenreJobStatus:
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(f"Unknown MAEST genre job: {job_id}")
            return self._copy_status(self._jobs[job_id])

    def latest(self) -> GenreJobStatus | None:
        with self._lock:
            if not self._jobs:
                return None
            return self._copy_status(next(reversed(self._jobs.values())))

    def cancel(self, job_id: str) -> GenreJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _create_adapter(self, *, device: str, top_k: int) -> GenreAdapter:
        factory = self.adapter_factories["maest"]
        try:
            return factory(device=device, top_k=top_k)  # type: ignore[misc,call-arg]
        except TypeError:
            if factory is MaestGenreAdapter:
                raise
            return factory()

    def _save_failure(self, job_id: str, track: Track, error: Exception) -> None:
        status = self.get(job_id)
        errors = list(status.errors)
        errors.append(GenreTrackError(track_id=track.id, path=track.path, error=str(error)))
        self._update_progress(job_id, track.path, failed_delta=1, errors=errors)
        self._append_event(job_id, "error", f"Track failed: {error}", path=track.path, track_id=track.id)

    def _update_progress(
        self,
        job_id: str,
        current_path: str,
        *,
        analyzed_delta: int = 0,
        failed_delta: int = 0,
        errors: list[GenreTrackError] | None = None,
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
            status.events.append(GenreLogEvent(time.time(), level, message, path, track_id))
            if len(status.events) > 200:
                status.events = status.events[-200:]

    @staticmethod
    def _copy_status(status: GenreJobStatus) -> GenreJobStatus:
        copy = GenreJobStatus(
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
            top_k=status.top_k,
            batch_size=status.batch_size,
            workers=status.workers,
        )
        if hasattr(status, "_tracks"):
            copy._tracks = getattr(status, "_tracks")  # type: ignore[attr-defined]
        return copy
