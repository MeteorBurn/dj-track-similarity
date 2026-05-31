from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Mapping, Sequence, cast

from .analysis_job_batch import AnalysisBatchItem, DecodeAudio, decode_analysis_batch
from .analysis_job_state import (
    AnalysisJobStatus,
    AnalysisLogEvent,
    AnalysisModelProgress,
    AnalysisTrackError,
    AnalysisTrackOutcome,
    copy_analysis_status,
    initial_model_progress,
    initial_track_outcomes,
    mark_track_processed as apply_track_processed,
    record_model_failure as apply_model_failure,
    record_model_success as apply_model_success,
    record_track_model_result as apply_track_model_result,
)
from .analysis_model_runners import (
    AnalysisModelRunner,
    EmbeddingModelRunner,
    MaestModelRunner,
    RunnerFactory,
    SonaraModelRunner,
    _default_model_runners,
)
from .audio_loader import load_decoded_audio
from .analysis_config import (
    ANALYSIS_MODEL_ORDER,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    normalize_analysis_models,
)
from .database import LibraryDatabase
from .job_runtime import JobStore, chunks
from .logging_config import exception_summary, log_failure, log_job_event
from .models import Track


LOGGER = logging.getLogger(__name__)


__all__ = [
    "AnalysisBatchItem",
    "AnalysisJobManager",
    "AnalysisJobStatus",
    "AnalysisLogEvent",
    "AnalysisModelProgress",
    "AnalysisModelRunner",
    "AnalysisTrackError",
    "AnalysisTrackOutcome",
    "DecodeAudio",
    "EmbeddingModelRunner",
    "MaestModelRunner",
    "RunnerFactory",
    "SonaraModelRunner",
]


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
        selected = normalize_analysis_models(models)
        candidates = self.db.list_analysis_candidates(selected, limit=limit)
        tracks = [candidate.to_track() for candidate in candidates]
        targets_by_track = {candidate.id: candidate.missing_models for candidate in candidates}
        progress = initial_model_progress(selected, targets_by_track)
        track_outcomes = initial_track_outcomes(tracks, targets_by_track)
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
        decoded_items = decode_analysis_batch(
            batch,
            targets_by_track,
            self._decode_audio,
            set_current_path=lambda path: self._update(job_id, current_path=path),
            record_decode_failure=lambda track, targets, error: self._record_decode_failure(job_id, track, targets, error),
            mark_track_processed=lambda track: self._mark_track_processed(job_id, track),
        )

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

    def _record_decode_failure(self, job_id: str, track: Track, targets: tuple[str, ...], error: Exception) -> None:
        for model in targets:
            self._record_model_failure(job_id, model, track, error, emit_event=False)
        self._append_event(
            job_id,
            "error",
            f"Track decode failed: {exception_summary(error)}",
            path=track.path,
            track_id=track.id,
        )

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
            apply_model_success(status, model)

    def _record_model_failure(self, job_id: str, model: str, track: Track, error: Exception, *, emit_event: bool = True) -> None:
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
            apply_model_failure(
                status,
                model,
                AnalysisTrackError(track_id=track.id, path=track.path, error=error_text, model=model),
            )
        if emit_event:
            self._append_event(job_id, "error", f"Track failed: {error_text}", path=track.path, track_id=track.id, model=model)

    def _mark_track_processed(self, job_id: str, track: Track) -> None:
        outcome = self._track_outcome(job_id, track.id)
        analyzed = False
        with self._store.locked(job_id) as status:
            analyzed = apply_track_processed(status, track_path=track.path, outcome=outcome, now=time.time())
        if analyzed:
            self._append_event(job_id, "ok", "Track analyzed", path=track.path, track_id=track.id)

    def _record_track_model_result(self, job_id: str, track_id: int, *, failed: bool) -> None:
        apply_track_model_result(self._track_outcome(job_id, track_id), failed=failed)

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
        return copy_analysis_status(status)
