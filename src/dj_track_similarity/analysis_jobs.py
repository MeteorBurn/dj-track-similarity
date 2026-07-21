from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from . import analysis_model_runners as model_runner_module
from .analysis_config import (
    ANALYSIS_MODEL_ORDER,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    DEFAULT_SONARA_BATCH_SIZE,
    DEFAULT_SONARA_OUTPUTS,
    MAX_SONARA_BATCH_SIZE,
    normalize_analysis_models,
    normalize_sonara_outputs,
)
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
)
from .analysis_queue import AnalysisStageQueue
from .audio_loader import load_decoded_audio
from .database import LibraryDatabase
from .job_runtime import JobStore, chunks
from .logging_config import exception_summary, log_failure, log_job_event
from .models import Track
from .sonara_features import sonara_analysis_signatures_for_outputs


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


@dataclass(frozen=True)
class _AnalysisPayload:
    tracks: list[Track]
    targets_by_track: dict[int, tuple[str, ...]]
    track_outcomes: dict[int, AnalysisTrackOutcome]


@dataclass
class _RunnerLifecycle:
    runners: dict[str, AnalysisModelRunner]


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
        sonara_batch_size: int = DEFAULT_SONARA_BATCH_SIZE,
        stage_queue: AnalysisStageQueue | None = None,
    ) -> None:
        self.db = db
        self._model_runners = dict(model_runners) if model_runners is not None else None
        self._runner_factory = runner_factory or model_runner_module.default_model_runners
        self._decode_audio = decode_audio
        self.track_batch_size = max(1, int(track_batch_size))
        self.inference_batch_size = max(1, int(inference_batch_size))
        self.sonara_batch_size = max(1, int(sonara_batch_size))
        self._stage_queue = stage_queue
        self._store: JobStore[AnalysisJobStatus] = JobStore(self._copy_status, unknown_label="analysis job")

    def create_job(
        self,
        *,
        models: Sequence[str] | None = None,
        limit: int | None = None,
        track_batch_size: int | None = None,
        inference_batch_size: int | None = None,
        sonara_batch_size: int | None = None,
        device: str = "auto",
        top_k: int = 3,
        sonara_outputs: Sequence[str] | None = None,
    ) -> str:
        selected = normalize_analysis_models(models)
        if "sonara" not in selected and sonara_outputs:
            raise ValueError("SONARA outputs can only be used with a SONARA-only analysis job")
        outputs = (
            normalize_sonara_outputs(DEFAULT_SONARA_OUTPUTS if sonara_outputs is None else sonara_outputs)
            if selected == ("sonara",)
            else ()
        )
        if selected == ("sonara",):
            self.validate_sonara_preflight()
        expected_signatures = sonara_analysis_signatures_for_outputs(outputs) if outputs else None
        candidates = self.db.list_analysis_candidates(
            selected,
            limit=limit,
            expected_sonara_signatures=expected_signatures,
        )
        tracks = [candidate.to_track() for candidate in candidates]
        targets_by_track = {
            candidate.id: tuple(model for model in selected if model in candidate.missing_models)
            for candidate in candidates
        }
        job_id = str(uuid.uuid4())
        effective_track_batch = max(1, int(track_batch_size or self.track_batch_size))
        effective_inference_batch = max(1, int(inference_batch_size or self.inference_batch_size))
        effective_sonara_batch = int(self.sonara_batch_size if sonara_batch_size is None else sonara_batch_size)
        if effective_sonara_batch < 1 or effective_sonara_batch > MAX_SONARA_BATCH_SIZE:
            raise ValueError(f"sonara_batch_size must be between 1 and {MAX_SONARA_BATCH_SIZE}")
        status = AnalysisJobStatus(
            job_id=job_id,
            state="queued",
            models=list(selected),
            model_progress=initial_model_progress(selected, targets_by_track),
            total=len(tracks),
            device_requested=device,
            workers=effective_sonara_batch if selected == ("sonara",) else effective_track_batch,
            track_batch_size=effective_track_batch,
            inference_batch_size=effective_inference_batch,
            sonara_batch_size=effective_sonara_batch,
            top_k=max(1, int(top_k)),
            sonara_outputs=list(outputs),
        )
        self._store.add(
            job_id,
            status,
            payload=_AnalysisPayload(
                tracks=tracks,
                targets_by_track=targets_by_track,
                track_outcomes=initial_track_outcomes(tracks, targets_by_track),
            ),
        )
        self._append_event(job_id, "info", "Analysis queued")
        return job_id

    def validate_sonara_preflight(self) -> None:
        signatures = sonara_analysis_signatures_for_outputs(("core", "timeline", "representations"))
        blockers = self.db.sonara_migration_blockers(signatures)
        if blockers["total"]:
            raise ValueError(
                "Existing SONARA data uses an older contract "
                f"(Core {blockers['core']}, Timeline {blockers['timeline']}, "
                f"Representations {blockers['representations']}). Back up the database and run the explicit "
                "SONARA reset before native analysis; old and new SONARA results cannot be mixed."
            )

    def start(self, **kwargs: object) -> AnalysisJobStatus:
        job_id = self.create_job(**kwargs)
        if self._stage_queue is not None:
            self._stage_queue.submit(lambda: self.run_job(job_id))
        else:
            threading.Thread(target=self.run_job, args=(job_id,), daemon=True).start()
        return self.get(job_id)

    def run_sync(self, **kwargs: object) -> AnalysisJobStatus:
        return self.run_job(self.create_job(**kwargs))

    def run_job(self, job_id: str) -> AnalysisJobStatus:
        status = self.get(job_id)
        payload = self._payload(job_id)
        if status.cancel_requested:
            return self._finish_cancelled(job_id)
        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(job_id, "info", "Analysis started")
        lifecycle = _RunnerLifecycle(runners={})
        batch_size = status.sonara_batch_size if status.models == ["sonara"] else status.track_batch_size
        for batch in chunks(payload.tracks, max(1, batch_size)):
            if self.get(job_id).cancel_requested:
                return self._finish_cancelled(job_id)
            if not self._process_batch(job_id, lifecycle, batch, payload.targets_by_track):
                return self.get(job_id)
            if self.get(job_id).cancel_requested:
                return self._finish_cancelled(job_id)

        finished = time.time()
        final = self.get(job_id)
        self._update(
            job_id,
            state="completed",
            finished_at=finished,
            current_path=None,
            current_model=None,
            avg_seconds_per_track=(finished - (final.started_at or started)) / max(1, final.processed),
        )
        self._append_event(job_id, "info", "Analysis completed")
        return self.get(job_id)

    def _process_batch(
        self,
        job_id: str,
        lifecycle: _RunnerLifecycle,
        batch: list[Track],
        targets_by_track: Mapping[int, tuple[str, ...]],
    ) -> bool:
        status = self.get(job_id)
        if status.models == ["sonara"]:
            items = [
                AnalysisBatchItem(track=track, decoded=None, models=targets_by_track.get(track.id, ()))
                for track in batch
                if targets_by_track.get(track.id)
            ]
        else:
            items = decode_analysis_batch(
                batch,
                targets_by_track,
                self._decode_audio,
                set_current_path=lambda path: self._update(job_id, current_path=path),
                record_decode_failure=lambda track, targets, error: self._record_decode_failure(job_id, track, targets, error),
                mark_track_processed=lambda track: self._mark_track_processed(job_id, track),
            )

        for model in ANALYSIS_MODEL_ORDER:
            model_items = [item for item in items if model in item.models]
            if not model_items:
                continue
            if self.get(job_id).cancel_requested:
                return True
            try:
                runner = lifecycle.runners.get(model)
                if runner is None:
                    runner = self._runner_for_model(model, self.get(job_id))
                    lifecycle.runners[model] = runner
                    if isinstance(runner, SonaraModelRunner):
                        runner.progress = lambda done, total: self._sonara_progress(job_id, done, total)
            except Exception as error:
                self._fail_stage(job_id, f"{model} initialization failed: {exception_summary(error)}", model=model)
                return False
            self._update(
                job_id,
                current_model=model,
                model_name=getattr(runner, "model_name", model),
                device=getattr(runner, "device", None),
            )
            if not self._run_model_batch(job_id, model, runner, model_items):
                return False

        for item in items:
            self._mark_track_processed(job_id, item.track)
        return True

    def _sonara_progress(self, job_id: str, done: int, total: int) -> None:
        if done == total or done == 1 or done % 10 == 0:
            self._append_event(job_id, "info", f"SONARA native batch progress {done}/{total}", model="sonara")

    def _runner_for_model(self, model: str, status: AnalysisJobStatus) -> AnalysisModelRunner:
        if self._model_runners is not None:
            try:
                return self._model_runners[model]
            except KeyError as error:
                raise ValueError(f"No analysis runner configured for: {model}") from error
        return self._runner_factory(
            model,
            status.device_requested,
            status.inference_batch_size,
            status.top_k,
            tuple(status.sonara_outputs),
        )

    def _run_model_batch(
        self,
        job_id: str,
        model: str,
        runner: AnalysisModelRunner,
        items: list[AnalysisBatchItem],
    ) -> bool:
        try:
            results = runner.analyze_batch(self.db, items)
        except Exception as error:
            if model == "sonara":
                self._fail_stage(job_id, f"SONARA native batch failed: {exception_summary(error)}", model=model)
                return False
            if len(items) <= 1:
                self._record_model_failure(job_id, model, items[0].track, error)
                return True
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
                except Exception as item_error:
                    self._record_model_failure(job_id, model, item.track, item_error)
            return True

        if model == "sonara":
            if results is None or len(results) != len(items):
                self._fail_stage(job_id, "SONARA native batch returned an invalid result count", model=model)
                return False
            for item, error in zip(items, results):
                if error is None:
                    self._record_model_success(job_id, model, item.track)
                else:
                    self._record_model_failure(job_id, model, item.track, error)
            return True

        for item in items:
            self._record_model_success(job_id, model, item.track)
        return True

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

    def _record_model_success(self, job_id: str, model: str, track: Track) -> None:
        apply_track_model_result(self._track_outcome(job_id, track.id), failed=False)
        with self._store.locked(job_id) as status:
            apply_model_success(status, model)

    def _record_model_failure(
        self,
        job_id: str,
        model: str,
        track: Track,
        error: Exception,
        *,
        emit_event: bool = True,
    ) -> None:
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
        apply_track_model_result(self._track_outcome(job_id, track.id), failed=True)
        with self._store.locked(job_id) as status:
            apply_model_failure(
                status,
                model,
                AnalysisTrackError(track_id=track.id, path=track.path, error=error_text, model=model),
            )
        if emit_event:
            self._append_event(
                job_id,
                "error",
                f"Track failed: {error_text}",
                path=track.path,
                track_id=track.id,
                model=model,
            )

    def _mark_track_processed(self, job_id: str, track: Track) -> None:
        analyzed = False
        outcome = self._track_outcome(job_id, track.id)
        with self._store.locked(job_id) as status:
            analyzed = apply_track_processed(
                status,
                track_path=track.path,
                outcome=outcome,
                now=time.time(),
            )
        if analyzed:
            self._append_event(job_id, "ok", "Track analyzed", path=track.path, track_id=track.id)

    def _fail_stage(self, job_id: str, message: str, *, model: str | None = None) -> None:
        self._update(job_id, state="failed", finished_at=time.time(), current_path=None, current_model=None)
        self._append_event(job_id, "error", message, model=model)

    def _finish_cancelled(self, job_id: str) -> AnalysisJobStatus:
        self._update(job_id, state="cancelled", finished_at=time.time(), current_path=None, current_model=None)
        self._append_event(job_id, "warn", "Analysis cancelled")
        return self.get(job_id)

    def get(self, job_id: str) -> AnalysisJobStatus:
        return self._store.get(job_id)

    def latest(self) -> AnalysisJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> AnalysisJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _track_outcome(self, job_id: str, track_id: int) -> AnalysisTrackOutcome | None:
        return self._payload(job_id).track_outcomes.get(track_id)

    def _payload(self, job_id: str) -> _AnalysisPayload:
        return cast(_AnalysisPayload, self._store.payload(job_id))

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
