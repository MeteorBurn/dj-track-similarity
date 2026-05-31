from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence, cast

import numpy as np

from .audio_loader import DecodedAudio, load_decoded_audio
from .database import LibraryDatabase
from .embedding import ClapEmbeddingAdapter, MertEmbeddingAdapter
from .genres import MaestGenreAdapter
from .job_runtime import JobStore, chunks
from .logging_config import exception_summary, log_failure, log_job_event
from .models import Track
from .sonara_features import analyze_and_store_sonara_features_from_audio


ANALYSIS_MODEL_ORDER = ("sonara", "maest", "mert", "clap")
DEFAULT_ANALYSIS_TRACK_BATCH_SIZE = 6
DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE = 24
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisBatchItem:
    track: Track
    decoded: DecodedAudio | object
    models: tuple[str, ...]


class AnalysisModelRunner(Protocol):
    model: str
    model_name: str
    device: str | None

    def analyze_batch(self, db: LibraryDatabase, items: Sequence[AnalysisBatchItem]) -> None:
        ...


@dataclass(frozen=True)
class AnalysisTrackError:
    track_id: int
    path: str
    error: str
    model: str


@dataclass(frozen=True)
class AnalysisLogEvent:
    timestamp: float
    level: str
    message: str
    path: str | None = None
    track_id: int | None = None
    model: str | None = None


@dataclass
class AnalysisModelProgress:
    total: int = 0
    processed: int = 0
    analyzed: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass
class AnalysisTrackOutcome:
    target_count: int
    successes: int = 0
    failures: int = 0


@dataclass
class AnalysisJobStatus:
    job_id: str
    state: str
    adapter_name: str = "multi"
    embedding_key: str = "multi"
    models: list[str] = field(default_factory=lambda: list(ANALYSIS_MODEL_ORDER))
    current_model: str | None = None
    model_progress: dict[str, AnalysisModelProgress] = field(default_factory=dict)
    model_name: str | None = None
    device: str | None = None
    device_requested: str = "auto"
    total: int = 0
    processed: int = 0
    analyzed: int = 0
    failed: int = 0
    skipped: int = 0
    current_path: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    avg_seconds_per_track: float | None = None
    errors: list[AnalysisTrackError] = field(default_factory=list)
    events: list[AnalysisLogEvent] = field(default_factory=list)
    cancel_requested: bool = False
    workers: int = DEFAULT_ANALYSIS_TRACK_BATCH_SIZE
    batch_size: int = DEFAULT_ANALYSIS_TRACK_BATCH_SIZE
    track_batch_size: int = DEFAULT_ANALYSIS_TRACK_BATCH_SIZE
    inference_batch_size: int = DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE
    top_k: int = 3


RunnerFactory = Callable[[str, str, int, int], AnalysisModelRunner]
DecodeAudio = Callable[[str | Path], DecodedAudio | object]


class AnalysisJobManager:
    def __init__(
        self,
        db: LibraryDatabase,
        model_runners: Mapping[str, AnalysisModelRunner] | None = None,
        *,
        decode_audio: DecodeAudio = load_decoded_audio,
        runner_factory: RunnerFactory | None = None,
        track_batch_size: int = DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
        inference_batch_size: int = DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    ) -> None:
        self.db = db
        self._model_runners = dict(model_runners) if model_runners is not None else None
        self._runner_factory = runner_factory or _default_model_runners
        self._decode_audio = decode_audio
        self.track_batch_size = max(1, int(track_batch_size))
        self.inference_batch_size = max(1, int(inference_batch_size))
        self._store = JobStore(self._copy_status, unknown_label="analysis job")

    def create_job(
        self,
        *,
        models: Sequence[str] | None = None,
        limit: int | None = None,
        track_batch_size: int | None = None,
        inference_batch_size: int | None = None,
        device: str = "auto",
        top_k: int = 3,
    ) -> str:
        selected = _normalize_models(models)
        tracks = self.db.list_tracks_missing_any_analysis(selected, limit=limit)
        targets_by_track = {track.id: _missing_models(track, selected) for track in tracks}
        tracks = [track for track in tracks if targets_by_track[track.id]]
        progress = {model: AnalysisModelProgress() for model in selected}
        for targets in targets_by_track.values():
            for model in targets:
                progress[model].total += 1
        track_outcomes = {
            track.id: AnalysisTrackOutcome(target_count=len(targets_by_track[track.id]))
            for track in tracks
        }
        job_id = str(uuid.uuid4())
        effective_track_batch_size = max(1, int(track_batch_size if track_batch_size is not None else self.track_batch_size))
        effective_inference_batch_size = max(
            1,
            int(inference_batch_size if inference_batch_size is not None else self.inference_batch_size),
        )
        status = AnalysisJobStatus(
            job_id=job_id,
            state="queued",
            models=list(selected),
            model_progress=progress,
            total=len(tracks),
            device_requested=device,
            workers=effective_track_batch_size,
            batch_size=effective_track_batch_size,
            track_batch_size=effective_track_batch_size,
            inference_batch_size=effective_inference_batch_size,
            top_k=max(1, int(top_k)),
        )
        self._store.add(
            job_id,
            status,
            payload={"tracks": tracks, "targets_by_track": targets_by_track, "track_outcomes": track_outcomes},
        )
        self._append_event(job_id, "info", "Analysis queued")
        return job_id

    def start(
        self,
        *,
        models: Sequence[str] | None = None,
        limit: int | None = None,
        track_batch_size: int | None = None,
        inference_batch_size: int | None = None,
        device: str = "auto",
        top_k: int = 3,
    ) -> AnalysisJobStatus:
        job_id = self.create_job(
            models=models,
            limit=limit,
            track_batch_size=track_batch_size,
            inference_batch_size=inference_batch_size,
            device=device,
            top_k=top_k,
        )
        thread = threading.Thread(target=self.run_job, args=(job_id,), daemon=True)
        thread.start()
        return self.get(job_id)

    def run_sync(
        self,
        *,
        models: Sequence[str] | None = None,
        limit: int | None = None,
        track_batch_size: int | None = None,
        inference_batch_size: int | None = None,
        device: str = "auto",
        top_k: int = 3,
    ) -> AnalysisJobStatus:
        job_id = self.create_job(
            models=models,
            limit=limit,
            track_batch_size=track_batch_size,
            inference_batch_size=inference_batch_size,
            device=device,
            top_k=top_k,
        )
        return self.run_job(job_id)

    def run_job(self, job_id: str) -> AnalysisJobStatus:
        status = self.get(job_id)
        payload = cast(dict[str, object], self._store.payload(job_id) or {})
        tracks = cast(list[Track], payload.get("tracks") or [])
        targets_by_track = cast(dict[int, tuple[str, ...]], payload.get("targets_by_track") or {})
        if status.cancel_requested:
            self._update(job_id, state="cancelled", finished_at=time.time())
            self._append_event(job_id, "warn", "Analysis cancelled")
            return self.get(job_id)

        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(job_id, "info", "Analysis started")
        runners: dict[str, AnalysisModelRunner] = {}
        failed_model_inits: dict[str, str] = {}

        for batch in chunks(tracks, max(1, status.track_batch_size)):
            if self.get(job_id).cancel_requested:
                self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None, current_model=None)
                self._append_event(job_id, "warn", "Analysis cancelled")
                return self.get(job_id)
            self._process_batch(job_id, runners, failed_model_inits, batch, targets_by_track)

        finished = time.time()
        final = self.get(job_id)
        processed = max(1, final.processed)
        self._update(
            job_id,
            state="completed",
            finished_at=finished,
            current_path=None,
            current_model=None,
            avg_seconds_per_track=(finished - (final.started_at or started)) / processed,
        )
        self._append_event(job_id, "info", "Analysis completed")
        return self.get(job_id)

    def get(self, job_id: str) -> AnalysisJobStatus:
        return self._store.get(job_id)

    def latest(self) -> AnalysisJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> AnalysisJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _process_batch(
        self,
        job_id: str,
        runners: dict[str, AnalysisModelRunner],
        failed_model_inits: dict[str, str],
        batch: list[Track],
        targets_by_track: Mapping[int, tuple[str, ...]],
    ) -> None:
        decoded_items: list[AnalysisBatchItem] = []
        for track in batch:
            targets = targets_by_track.get(track.id, ())
            if not targets:
                self._mark_track_processed(job_id, track)
                continue
            self._update(job_id, current_path=track.path)
            try:
                decoded = self._decode_audio(track.path)
            except Exception as error:
                for model in targets:
                    self._record_model_failure(job_id, model, track, error)
                self._mark_track_processed(job_id, track)
                continue
            decoded_items.append(AnalysisBatchItem(track=track, decoded=decoded, models=targets))

        for model in ANALYSIS_MODEL_ORDER:
            model_items = [item for item in decoded_items if model in item.models]
            if not model_items:
                continue
            if self.get(job_id).cancel_requested:
                return
            if model in failed_model_inits:
                for item in model_items:
                    self._record_model_failure(job_id, model, item.track, RuntimeError(failed_model_inits[model]))
                continue
            try:
                runner = runners.get(model)
                if runner is None:
                    runner = self._runner_for_model(model, self.get(job_id))
                    runners[model] = runner
            except Exception as error:
                error_text = exception_summary(error)
                failed_model_inits[model] = error_text
                self._append_event(job_id, "error", f"{model} initialization failed: {error_text}", model=model)
                for item in model_items:
                    self._record_model_failure(job_id, model, item.track, RuntimeError(error_text))
                continue
            self._update(job_id, current_model=model, model_name=getattr(runner, "model_name", model), device=getattr(runner, "device", None))
            self._run_model_batch(job_id, model, runner, model_items)

        for item in decoded_items:
            self._mark_track_processed(job_id, item.track)

    def _runner_for_model(self, model: str, status: AnalysisJobStatus) -> AnalysisModelRunner:
        if self._model_runners is not None:
            try:
                return self._model_runners[model]
            except KeyError as error:
                raise ValueError(f"No analysis runner configured for: {model}") from error
        return self._runner_factory(model, status.device_requested, status.inference_batch_size, status.top_k)

    def _run_model_batch(
        self,
        job_id: str,
        model: str,
        runner: AnalysisModelRunner,
        items: list[AnalysisBatchItem],
    ) -> None:
        try:
            runner.analyze_batch(self.db, items)
            for item in items:
                self._record_model_success(job_id, model, item.track)
            return
        except Exception as error:
            if len(items) <= 1:
                self._record_model_failure(job_id, model, items[0].track, error)
                return
            LOGGER.warning(
                "Analysis model batch failed; retrying tracks individually job_id=%s model=%s batch_size=%s error=%s",
                job_id,
                model,
                len(items),
                exception_summary(error),
            )
            self._append_event(job_id, "warn", f"{model} batch failed; retrying tracks individually", model=model)

        for item in items:
            try:
                runner.analyze_batch(self.db, [item])
                self._record_model_success(job_id, model, item.track)
            except Exception as error:
                self._record_model_failure(job_id, model, item.track, error)

    def _record_model_success(self, job_id: str, model: str, track: Track) -> None:
        self._record_track_model_result(job_id, track.id, failed=False)
        with self._store.locked(job_id) as status:
            progress = status.model_progress[model]
            progress.processed += 1
            progress.analyzed += 1

    def _record_model_failure(self, job_id: str, model: str, track: Track, error: Exception) -> None:
        error_text = exception_summary(error)
        log_failure(
            LOGGER,
            "Analysis model failed job_id=%s model=%s track_id=%s path=%s error=%s",
            job_id,
            model,
            track.id,
            track.path,
            error_text,
        )
        self._record_track_model_result(job_id, track.id, failed=True)
        with self._store.locked(job_id) as status:
            progress = status.model_progress[model]
            progress.processed += 1
            progress.failed += 1
            status.errors.append(AnalysisTrackError(track_id=track.id, path=track.path, error=error_text, model=model))
        self._append_event(job_id, "error", f"Track failed: {error_text}", path=track.path, track_id=track.id, model=model)

    def _mark_track_processed(self, job_id: str, track: Track) -> None:
        outcome = self._track_outcome(job_id, track.id)
        analyzed = False
        with self._store.locked(job_id) as status:
            status.current_path = track.path
            status.processed += 1
            if outcome is None or outcome.target_count <= 0:
                status.skipped += 1
            elif outcome.failures:
                status.failed += 1
            elif outcome.successes >= outcome.target_count:
                status.analyzed += 1
                analyzed = True
            else:
                status.skipped += 1
            if status.started_at and status.processed:
                status.avg_seconds_per_track = (time.time() - status.started_at) / status.processed
        if analyzed:
            self._append_event(job_id, "ok", "Track analyzed", path=track.path, track_id=track.id)

    def _record_track_model_result(self, job_id: str, track_id: int, *, failed: bool) -> None:
        outcome = self._track_outcome(job_id, track_id)
        if outcome is None:
            return
        if failed:
            outcome.failures += 1
        else:
            outcome.successes += 1

    def _track_outcome(self, job_id: str, track_id: int) -> AnalysisTrackOutcome | None:
        payload = cast(dict[str, object], self._store.payload(job_id) or {})
        outcomes = cast(dict[int, AnalysisTrackOutcome], payload.get("track_outcomes") or {})
        return outcomes.get(track_id)

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
        model: str | None = None,
    ) -> None:
        log_job_event(
            LOGGER,
            level,
            "%s job_id=%s model=%s track_id=%s path=%s",
            message,
            job_id,
            model,
            track_id,
            path,
            track_event=level == "ok",
        )
        self._store.append_event(job_id, AnalysisLogEvent(time.time(), level, message, path, track_id, model))

    @staticmethod
    def _copy_status(status: AnalysisJobStatus) -> AnalysisJobStatus:
        return AnalysisJobStatus(
            job_id=status.job_id,
            state=status.state,
            adapter_name=status.adapter_name,
            embedding_key=status.embedding_key,
            models=list(status.models),
            current_model=status.current_model,
            model_progress={
                model: AnalysisModelProgress(
                    total=progress.total,
                    processed=progress.processed,
                    analyzed=progress.analyzed,
                    failed=progress.failed,
                    skipped=progress.skipped,
                )
                for model, progress in status.model_progress.items()
            },
            model_name=status.model_name,
            device=status.device,
            device_requested=status.device_requested,
            total=status.total,
            processed=status.processed,
            analyzed=status.analyzed,
            failed=status.failed,
            skipped=status.skipped,
            current_path=status.current_path,
            started_at=status.started_at,
            finished_at=status.finished_at,
            avg_seconds_per_track=status.avg_seconds_per_track,
            errors=list(status.errors),
            events=list(status.events),
            cancel_requested=status.cancel_requested,
            workers=status.workers,
            batch_size=status.batch_size,
            track_batch_size=status.track_batch_size,
            inference_batch_size=status.inference_batch_size,
            top_k=status.top_k,
        )


class SonaraModelRunner:
    model = "sonara"
    model_name = "sonara-playlist-lab"
    device = "cpu"

    def analyze_batch(self, db: LibraryDatabase, items: Sequence[AnalysisBatchItem]) -> None:
        for item in items:
            analyze_and_store_sonara_features_from_audio(db, item.track, cast(DecodedAudio, item.decoded))


class MaestModelRunner:
    model = "maest"

    def __init__(self, *, device: str, top_k: int, inference_batch_size: int) -> None:
        self.adapter = MaestGenreAdapter(device=device, top_k=top_k, inference_batch_size=inference_batch_size)

    @property
    def model_name(self) -> str:
        return self.adapter.model_name

    @property
    def device(self) -> str | None:
        return self.adapter.device

    def analyze_batch(self, db: LibraryDatabase, items: Sequence[AnalysisBatchItem]) -> None:
        tracks = [item.track for item in items]
        decoded_items = [cast(DecodedAudio, item.decoded) for item in items]
        genres_by_track = self.adapter.predict_decoded_batch(decoded_items)
        if len(genres_by_track) != len(tracks):
            raise ValueError("MAEST batch result count does not match track count")
        for track, decoded, genres in zip(tracks, decoded_items, genres_by_track):
            db.save_genres(track.id, genres, model_name=self.adapter.model_name)
            embedding = _embedding_for_path(self.adapter, decoded.path)
            if embedding is not None:
                db.save_embedding(track.id, embedding, self.adapter.model_name, getattr(self.adapter, "dim", None), embedding_key="maest")


class EmbeddingModelRunner:
    def __init__(self, model: str, *, device: str, inference_batch_size: int) -> None:
        self.model = model
        adapter_class = MertEmbeddingAdapter if model == "mert" else ClapEmbeddingAdapter
        self.adapter = adapter_class(device=device, inference_batch_size=inference_batch_size)

    @property
    def model_name(self) -> str:
        return self.adapter.model_name

    @property
    def device(self) -> str | None:
        return self.adapter.device

    def analyze_batch(self, db: LibraryDatabase, items: Sequence[AnalysisBatchItem]) -> None:
        tracks = [item.track for item in items]
        vectors = self.adapter.embed_decoded_batch([cast(DecodedAudio, item.decoded) for item in items])
        if len(vectors) != len(tracks):
            raise ValueError(f"{self.model.upper()} batch result count does not match track count")
        for track, vector in zip(tracks, vectors):
            db.save_embedding(track.id, vector, self.adapter.model_name, getattr(self.adapter, "dim", None), embedding_key=self.model)


def _default_model_runners(model: str, device: str, inference_batch_size: int, top_k: int) -> AnalysisModelRunner:
    if model == "sonara":
        return SonaraModelRunner()
    if model == "maest":
        return MaestModelRunner(device=device, top_k=top_k, inference_batch_size=inference_batch_size)
    if model in {"mert", "clap"}:
        return EmbeddingModelRunner(model, device=device, inference_batch_size=inference_batch_size)
    raise ValueError(f"No analysis runner configured for: {model}")


def _normalize_models(models: Sequence[str] | None) -> tuple[str, ...]:
    requested = models or ANALYSIS_MODEL_ORDER
    selected: list[str] = []
    for model in requested:
        text = str(model).strip().lower()
        if text not in ANALYSIS_MODEL_ORDER:
            raise ValueError(f"Unknown analysis model: {model}")
        if text not in selected:
            selected.append(text)
    if not selected:
        raise ValueError("At least one analysis model must be selected")
    return tuple(model for model in ANALYSIS_MODEL_ORDER if model in selected)


def _missing_models(track: Track, selected: Sequence[str]) -> tuple[str, ...]:
    existing = set(track.analyses or [])
    return tuple(model for model in selected if model not in existing)


def _embedding_for_path(adapter: object, path: str) -> np.ndarray | None:
    getter = getattr(adapter, "embedding_for_path", None)
    if not callable(getter):
        return None
    vector = getter(path)
    if vector is None:
        return None
    return np.asarray(vector, dtype=np.float32)
