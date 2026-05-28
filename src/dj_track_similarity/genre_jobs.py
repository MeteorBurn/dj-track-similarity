from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol, cast

import numpy as np

from .database import MAEST_EMBEDDING_KEY, LibraryDatabase
from .genres import MaestGenreAdapter, genre_adapter_factories as default_genre_adapter_factories
from .job_runtime import JobStore, chunks
from .logging_config import analysis_diagnostics_enabled, exception_summary, log_failure, log_job_event
from .models import Track


class GenreAdapter(Protocol):
    model_name: str
    device: str | None

    def predict(self, path: str) -> list[dict[str, object]]:
        ...

    def predict_batch(self, paths: list[str]) -> list[list[dict[str, object]]]:
        ...


GenreAdapterFactory = Callable[..., GenreAdapter]
LOGGER = logging.getLogger(__name__)


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
    embedding_key: str = MAEST_EMBEDDING_KEY
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
        self._store = JobStore(self._copy_status, unknown_label="MAEST genre job")

    def create_job(self, *, limit: int | None = None, device: str = "auto", top_k: int = 3, batch_size: int = 4) -> str:
        tracks = self.db.list_tracks_missing_maest(limit=limit)
        job_id = str(uuid.uuid4())
        effective_batch_size = max(1, int(batch_size))
        status = GenreJobStatus(
            job_id=job_id,
            state="queued",
            total=len(tracks),
            device_requested=device,
            top_k=max(1, int(top_k)),
            batch_size=effective_batch_size,
            workers=effective_batch_size,
        )
        self._store.add(job_id, status, payload=tracks)
        self._append_event(job_id, "info", "MAEST genre analysis queued")
        return job_id

    def start(self, *, limit: int | None = None, device: str = "auto", top_k: int = 3, batch_size: int = 4) -> GenreJobStatus:
        job_id = self.create_job(limit=limit, device=device, top_k=top_k, batch_size=batch_size)
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(self, *, limit: int | None = None, device: str = "auto", top_k: int = 3, batch_size: int = 4) -> GenreJobStatus:
        job_id = self.create_job(limit=limit, device=device, top_k=top_k, batch_size=batch_size)
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> GenreJobStatus:
        status = self.get(job_id)
        tracks = cast(list[Track], self._store.payload(job_id) or [])
        if status.cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "MAEST genre analysis cancelled")
            return self.get(job_id)

        try:
            adapter = self._create_adapter(device=status.device_requested, top_k=status.top_k)
        except Exception as error:
            error_text = exception_summary(error)
            self._update(job_id, state="failed", finished_at=time.time(), current_path=None)
            self._append_event(job_id, "error", error_text)
            return self.get(job_id)
        started = time.time()
        self._update(
            job_id,
            state="running",
            model_name=getattr(adapter, "model_name", "maest"),
            device=getattr(adapter, "device", None),
            started_at=started,
        )
        self._append_event(job_id, "info", "MAEST genre analysis started")
        for batch in chunks(tracks, max(1, status.batch_size)):
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None)
                self._append_event(job_id, "warn", "MAEST genre analysis cancelled")
                return self.get(job_id)
            self._update(job_id, current_path=batch[0].path if batch else None)
            self._process_batch(job_id, adapter, batch)
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
        return self._store.get(job_id)

    def latest(self) -> GenreJobStatus | None:
        return self._store.latest()

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

    def _process_batch(self, job_id: str, adapter: GenreAdapter, batch: list[Track]) -> None:
        batch_started = time.perf_counter()
        save_seconds = 0.0
        if hasattr(adapter, "predict_batch"):
            try:
                genre_batches = adapter.predict_batch([track.path for track in batch])  # type: ignore[attr-defined]
                if len(genre_batches) != len(batch):
                    raise ValueError("MAEST batch result count does not match track count")
                for track, genres in zip(batch, genre_batches):
                    save_started = time.perf_counter()
                    self._save_success(job_id, adapter, track, genres)
                    save_seconds += time.perf_counter() - save_started
                self._log_batch_timing(job_id, adapter, batch, batch_started=batch_started, save_seconds=save_seconds)
            except Exception as error:
                if len(batch) <= 1:
                    self._save_failure(job_id, batch[0], error)
                    return
                LOGGER.warning(
                    "MAEST genre batch failed; retrying tracks individually job_id=%s batch_size=%s error=%s",
                    job_id,
                    len(batch),
                    exception_summary(error),
                )
                self._append_event(job_id, "warn", "MAEST batch failed; retrying tracks individually")
                for track in batch:
                    try:
                        genres = adapter.predict_batch([track.path])[0]  # type: ignore[attr-defined]
                        self._save_success(job_id, adapter, track, genres)
                    except Exception as track_error:
                        self._save_failure(job_id, track, track_error)
            return

        for track in batch:
            try:
                genres = adapter.predict(track.path)
                save_started = time.perf_counter()
                self._save_success(job_id, adapter, track, genres)
                save_seconds += time.perf_counter() - save_started
                self._log_batch_timing(job_id, adapter, [track], batch_started=batch_started, save_seconds=save_seconds)
            except Exception as error:
                self._save_failure(job_id, track, error)

    def _log_batch_timing(
        self,
        job_id: str,
        adapter: GenreAdapter,
        batch: list[Track],
        *,
        batch_started: float,
        save_seconds: float,
    ) -> None:
        if not analysis_diagnostics_enabled():
            return
        total_seconds = time.perf_counter() - batch_started
        tracks = len(batch)
        timing = getattr(adapter, "last_batch_timing", {}) or {}
        tracks_per_second = tracks / total_seconds if total_seconds > 0 else 0.0
        LOGGER.info(
            "MAEST batch timing job_id=%s adapter=maest embedding_key=%s tracks=%s windows=%s "
            "prepare_seconds=%.3f decode_seconds=%.3f inference_seconds=%.3f save_seconds=%.3f "
            "total_seconds=%.3f tracks_per_second=%.3f",
            job_id,
            getattr(adapter, "embedding_key", MAEST_EMBEDDING_KEY),
            tracks,
            int(timing.get("windows", 0) or 0),
            float(timing.get("prepare_seconds", 0.0) or 0.0),
            float(timing.get("decode_seconds", 0.0) or 0.0),
            float(timing.get("inference_seconds", 0.0) or 0.0),
            save_seconds,
            total_seconds,
            tracks_per_second,
        )

    def _save_success(self, job_id: str, adapter: GenreAdapter, track: Track, genres: list[dict[str, object]]) -> None:
        embedding = _embedding_for_path(adapter, track.path)
        self.db.save_genres(track.id, genres, model_name=adapter.model_name)
        if embedding is not None:
            embedding_key = str(getattr(adapter, "embedding_key", MAEST_EMBEDDING_KEY))
            self.db.save_embedding(
                track.id,
                embedding,
                adapter.model_name,
                getattr(adapter, "dim", None),
                embedding_key=embedding_key,
            )
        self._update_progress(job_id, track.path, analyzed_delta=1)
        self._append_event(job_id, "ok", "Genres analyzed", path=track.path, track_id=track.id)

    def _save_failure(self, job_id: str, track: Track, error: Exception) -> None:
        error_text = exception_summary(error)
        log_failure(
            LOGGER,
            "MAEST genre track failed job_id=%s track_id=%s path=%s error=%s",
            job_id,
            track.id,
            track.path,
            error_text,
        )
        status = self.get(job_id)
        errors = list(status.errors)
        errors.append(GenreTrackError(track_id=track.id, path=track.path, error=error_text))
        self._update_progress(job_id, track.path, failed_delta=1, errors=errors)
        self._append_event(job_id, "error", f"Track failed: {error_text}", path=track.path, track_id=track.id)

    def _update_progress(
        self,
        job_id: str,
        current_path: str,
        *,
        analyzed_delta: int = 0,
        failed_delta: int = 0,
        errors: list[GenreTrackError] | None = None,
    ) -> None:
        with self._store.locked(job_id) as status:
            status.current_path = current_path
            status.processed += 1
            status.analyzed += analyzed_delta
            status.failed += failed_delta
            if errors is not None:
                status.errors = errors
            if status.started_at and status.processed:
                status.avg_seconds_per_track = (time.time() - status.started_at) / status.processed

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
            track_event=level == "ok",
        )
        self._store.append_event(job_id, GenreLogEvent(time.time(), level, message, path, track_id))

    @staticmethod
    def _copy_status(status: GenreJobStatus) -> GenreJobStatus:
        copy = GenreJobStatus(
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
            top_k=status.top_k,
            batch_size=status.batch_size,
            workers=status.workers,
        )
        return copy


def _embedding_for_path(adapter: GenreAdapter, path: str) -> np.ndarray | None:
    getter = getattr(adapter, "embedding_for_path", None)
    if not callable(getter):
        return None
    vector = getter(path)
    if vector is None:
        return None
    return np.asarray(vector, dtype=np.float32)
