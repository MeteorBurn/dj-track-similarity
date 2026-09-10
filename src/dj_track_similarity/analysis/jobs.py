from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from contextlib import ExitStack
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from .maest_export import MaestMelExport

from . import model_runners as model_runner_module
from .config import (
    ANALYSIS_MODEL_ORDER,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    DEFAULT_SONARA_BATCH_SIZE,
    AnalysisJobConfig,
    build_analysis_job_config,
)
from .job_batch import (
    AnalysisBatchItem,
    DecodeAudio,
    decode_analysis_batch,
)
from .job_state import (
    AnalysisJobStatus,
    AnalysisLogEvent,
    AnalysisModelProgress,
    AnalysisTrackError,
    AnalysisTrackOutcome,
    DecodeMethod,
    copy_analysis_status,
    initial_model_progress,
    initial_track_outcomes,
    mark_track_processed as apply_track_processed,
    record_model_failure as apply_model_failure,
    record_model_success as apply_model_success,
    record_track_model_result as apply_track_model_result,
)
from .model_runners import (
    AnalysisModelRunner,
    AnalysisWriteRepository,
    EmbeddingModelRunner,
    MaestModelRunner,
    RunnerFactory,
    SonaraModelRunner,
)
from .sonara_runtime import DEFAULT_SONARA_BPM_MAX, DEFAULT_SONARA_BPM_MIN
from .sonara_staging import SonaraStagingConfig, StagedSonaraResult
from .ml_staging import MLStagingConfig, MLStagedResult, analyze_and_store_staged_ml
from .._shutdown import defer_keyboard_interrupt
from ..analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
)
from .queue import AnalysisStageQueue
from ..audio.loader import load_decoded_audio
from ..embedding.contracts import EmbeddingCancelledError
from ..job_runtime import JobStore, chunks
from ..logging_config import (
    exception_summary,
    log_failure,
    log_job_event,
)
from .sonara_features import (
    SonaraBatchMetrics,
    analysis_outputs_for_sonara_runtime,
)


LOGGER = logging.getLogger(__name__)


@dataclass
class _AnalysisPayload:
    config: AnalysisJobConfig
    candidates: list[AnalysisCandidate] = field(default_factory=list)
    targets_by_track: dict[int, tuple[str, ...]] = field(default_factory=dict)
    track_outcomes: dict[int, AnalysisTrackOutcome] = field(default_factory=dict)


@dataclass
class _RunnerLifecycle:
    runners: dict[str, AnalysisModelRunner] = field(default_factory=dict)
    handles: dict[str, _RunnerHandle] = field(default_factory=dict)


@dataclass(frozen=True)
class _RunnerRuntimeKey:
    model: str
    device_requested: str
    inference_batch_size: int
    top_k: int


@dataclass
class _RunnerHandle:
    runner: AnalysisModelRunner
    lock: threading.RLock = field(default_factory=threading.RLock)
    preflight_complete: bool = False


class _RunnerInitializationError(RuntimeError):
    def __init__(self, model: str, error: Exception) -> None:
        super().__init__(f"{model} initialization failed: {exception_summary(error)}")
        self.model = model


class _RunnerPreflightError(RuntimeError):
    def __init__(self, model: str, error: Exception) -> None:
        super().__init__(f"{model} preflight failed: {exception_summary(error)}")
        self.model = model


@dataclass(frozen=True)
class SonaraOutputStatus:
    output_kind: Literal["core", "embedding", "fingerprint"]
    present_count: int
    missing_count: int


@dataclass(frozen=True)
class SonaraStatus:
    catalog_uuid: str
    total_tracks: int
    outputs: tuple[SonaraOutputStatus, ...]


class AnalysisJobManager:
    def __init__(
        self,
        db: AnalysisWriteRepository,
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
        self._provided_runner_handles = (
            {
                model: _RunnerHandle(runner)
                for model, runner in self._model_runners.items()
            }
            if self._model_runners is not None
            else None
        )
        self._runtime_runners: dict[_RunnerRuntimeKey, _RunnerHandle] = {}
        self._runtime_runners_lock = threading.RLock()
        self._runner_factory = (
            runner_factory or model_runner_module.default_model_runners
        )
        self._decode_audio = decode_audio
        self.track_batch_size = max(1, int(track_batch_size))
        self.inference_batch_size = max(1, int(inference_batch_size))
        self.sonara_batch_size = max(1, int(sonara_batch_size))
        self._stage_queue = stage_queue
        self._lifecycle = threading.Condition(threading.RLock())
        self._closing = False
        self._closed = False
        self._closing_thread: int | None = None
        self._active_work = 0
        self._executing_threads: dict[int, int] = {}
        self._executing_jobs: dict[str, int] = {}
        self._store: JobStore[AnalysisJobStatus] = JobStore(
            self._copy_status,
            unknown_label="analysis job",
        )

    def resolve_sonara_range(
        self,
        requested_min: float | None,
        requested_max: float | None,
    ) -> dict[str, float]:
        """Bind the run to the one BPM range this library analyses with.

        The first job to reach here claims the range; every later run reuses it
        so one library stays internally comparable. Releasing it means resetting
        the stored SONARA analysis or clearing the library.
        """
        library_min, library_max = self.db.claim_sonara_analysis_range(
            DEFAULT_SONARA_BPM_MIN if requested_min is None else requested_min,
            DEFAULT_SONARA_BPM_MAX if requested_max is None else requested_max,
        )
        requested = (
            requested_min if requested_min is not None else library_min,
            requested_max if requested_max is not None else library_max,
        )
        if requested != (library_min, library_max):
            raise ValueError(
                f"This library is analysed with the BPM range {library_min:g}-{library_max:g}. "
                f"Reset SONARA analysis before switching to {requested[0]:g}-{requested[1]:g}."
            )
        return {"sonara_bpm_min": library_min, "sonara_bpm_max": library_max}

    def create_job(
        self,
        *,
        models: Sequence[str] | None = None,
        limit: int | None = None,
        track_batch_size: int | None = None,
        inference_batch_size: int | None = None,
        sonara_batch_size: int | None = None,
        sonara_mode: str = "direct",
        sonara_bpm_min: float | None = None,
        sonara_bpm_max: float | None = None,
        sonara_staging_config: SonaraStagingConfig | None = None,
        ml_staging_config: MLStagingConfig | None = None,
        device: str = "auto",
        top_k: int = 3,
    ) -> str:
        with self._lifecycle:
            self._require_open()
        config = build_analysis_job_config(
            models=models,
            limit=limit,
            device=device,
            top_k=top_k,
            track_batch_size=(
                self.track_batch_size if track_batch_size is None else track_batch_size
            ),
            inference_batch_size=(
                self.inference_batch_size
                if inference_batch_size is None
                else inference_batch_size
            ),
            sonara_batch_size=(
                self.sonara_batch_size
                if sonara_batch_size is None
                else sonara_batch_size
            ),
            sonara_mode=sonara_mode,
            **self.resolve_sonara_range(sonara_bpm_min, sonara_bpm_max),
            sonara_staging_config=sonara_staging_config,
            ml_staging_config=ml_staging_config,
        )
        if config.require_current_sonara and self.current_sonara_track_count() < 1:
            raise ValueError(
                "ML analysis requires at least one track with current "
                "SONARA analysis"
            )
        job_id = str(uuid.uuid4())
        status = AnalysisJobStatus(
            job_id=job_id,
            state="queued",
            models=list(config.models),
            model_progress={model: AnalysisModelProgress() for model in config.models},
            total=0,
            device_requested=config.device,
            workers=(
                config.sonara_batch_size
                if config.models == ("sonara",)
                else config.track_batch_size
            ),
            track_batch_size=config.track_batch_size,
            inference_batch_size=config.inference_batch_size,
            sonara_batch_size=config.sonara_batch_size,
            sonara_mode=config.sonara_mode,
            sonara_bpm_min=config.sonara_bpm_min,
            sonara_bpm_max=config.sonara_bpm_max,
            top_k=config.top_k,
        )
        self._store.add(
            job_id,
            status,
            payload=_AnalysisPayload(config=config),
        )
        if config.models == ("sonara",):
            if config.sonara_mode == "staged":
                staging = config.sonara_staging_config
                assert staging is not None
                settings_message = (
                    "SONARA queued · outputs Core + embedding · Staged Mode · "
                    f"folder {staging.root} · processes {staging.processes} · "
                    f"threads {staging.rayon_threads} · "
                    f"batch {staging.max_native_batch_size} · "
                    f"stage {staging.stage_size}"
                )
            else:
                settings_message = (
                    "SONARA queued · outputs Core + embedding · Direct Mode · "
                    f"batch {config.sonara_batch_size}"
                )
        else:
            model_names = ", ".join(model.upper() for model in config.models)
            if config.ml_staging_config:
                staging = config.ml_staging_config
                settings_message = (
                    f"ML queued · models {model_names} · Staged Mode · "
                    f"folder {staging.root} · "
                    f"copy workers {staging.copy_workers} · "
                    f"decode workers {staging.decode_workers} · "
                    f"stage size {staging.stage_size} · "
                    f"inference batch {staging.inference_batch_size} · "
                    f"Device {config.device.upper()}"
                )
            else:
                settings_message = (
                    f"ML queued · models {model_names} · Direct Mode · "
                    f"Device {config.device.upper()} · "
                    f"Track batch {config.track_batch_size} · "
                    f"Inference batch {config.inference_batch_size}"
                )
        self._append_event(job_id, "info", settings_message)
        return job_id

    def current_sonara_track_count(self) -> int:
        return self.db.current_sonara_track_count()

    def sonara_status(self) -> SonaraStatus:
        """Return SONARA output coverage for the current catalog."""

        repository = self.db
        outputs = analysis_outputs_for_sonara_runtime()
        total_tracks = int(repository.library_summary().tracks)
        missing_counts = {output.key: 0 for output in outputs}
        for candidate in repository.list_analysis_candidates(outputs):
            for output in candidate.missing_outputs:
                if output.key in missing_counts:
                    missing_counts[output.key] += 1

        statuses = tuple(
            SonaraOutputStatus(
                output_kind=output.output_kind,
                present_count=total_tracks - missing_counts[output.key],
                missing_count=missing_counts[output.key],
            )
            for output in outputs
        )
        return SonaraStatus(
            catalog_uuid=str(repository.catalog_uuid),
            total_tracks=total_tracks,
            outputs=statuses,
        )

    def start(self, **kwargs: object) -> AnalysisJobStatus:
        job_id = self._create_admitted_job(**kwargs)
        try:
            if self._stage_queue is not None:
                self._stage_queue.submit(lambda: self._run_admitted_job(job_id))
            else:
                threading.Thread(
                    target=self._run_admitted_job,
                    args=(job_id,),
                    daemon=True,
                ).start()
        except BaseException as error:
            try:
                self._fail_stage(job_id, f"Analysis dispatch failed: {type(error).__name__}: {error}")
            finally:
                self._release_work()
            raise
        return self.get(job_id)

    def run_sync(self, **kwargs: object) -> AnalysisJobStatus:
        return self._run_admitted_job(self._create_admitted_job(**kwargs))

    def run_job(self, job_id: str) -> AnalysisJobStatus:
        with self._lifecycle:
            self._require_open()
            self._active_work += 1
        return self._run_admitted_job(job_id)

    def _create_admitted_job(self, **kwargs: object) -> str:
        with self._lifecycle:
            self._require_open()
            job_id = self.create_job(**kwargs)
            # Reserve before dispatch: the callback/thread may not have started
            # when another owner asks us to close.
            self._active_work += 1
            return job_id

    def _require_open(self) -> None:
        if self._closing:
            raise RuntimeError("Analysis manager is closed")

    def export_maest_mel(
        self, target: AnalysisTarget | int, *, device: str = "auto", top_k: int = 3,
    ) -> MaestMelExport:
        """Run a synchronous export under the same runner and shutdown ownership as analysis."""
        from .maest_export import build_maest_mel_export

        config = build_analysis_job_config(models=["maest"], device=device, top_k=top_k)
        thread_id = threading.get_ident()
        with self._lifecycle:
            self._require_open()
            self._active_work += 1
            self._executing_threads[thread_id] = self._executing_threads.get(thread_id, 0) + 1
        try:
            key = _RunnerRuntimeKey("maest", config.device, self.inference_batch_size, config.top_k)
            handle = self._cached_ml_runner(key)
            with handle.lock:
                if not isinstance(handle.runner, MaestModelRunner):
                    raise RuntimeError("MAEST export requires a MAEST analysis runner")
                return build_maest_mel_export(self.db, target, handle.runner.adapter)
        finally:
            with self._lifecycle:
                self._executing_threads[thread_id] -= 1
                if not self._executing_threads[thread_id]:
                    del self._executing_threads[thread_id]
                self._release_work()

    def _release_work(self) -> None:
        with self._lifecycle:
            self._active_work -= 1
            self._lifecycle.notify_all()

    def _run_admitted_job(self, job_id: str) -> AnalysisJobStatus:
        thread_id = threading.get_ident()
        payload: _AnalysisPayload | None = None
        with self._lifecycle:
            self._executing_threads[thread_id] = self._executing_threads.get(thread_id, 0) + 1
            self._executing_jobs[job_id] = self._executing_jobs.get(job_id, 0) + 1
        try:
            payload = self._payload(job_id)
            return self._execute_job(job_id)
        except EmbeddingCancelledError:
            return self._finish_cancelled(job_id)
        except BaseException as error:
            if self.get(job_id).state in {"queued", "running"}:
                self._fail_stage(
                    job_id,
                    f"Analysis execution failed: {type(error).__name__}: {error}",
                )
            if not isinstance(error, Exception):
                raise
            return self.get(job_id)
        finally:
            working_data = None
            with self._lifecycle:
                remaining_jobs = self._executing_jobs[job_id] - 1
                if remaining_jobs:
                    self._executing_jobs[job_id] = remaining_jobs
                else:
                    del self._executing_jobs[job_id]
                    if payload is not None:
                        working_data = (
                            payload.candidates, payload.targets_by_track, payload.track_outcomes,
                        )
                        payload.candidates = []
                        payload.targets_by_track = {}
                        payload.track_outcomes = {}
            try:
                # Keep configuration for run_job replay; release library-sized
                # data only after the final consumer exits, outside owner locks.
                if working_data is not None:
                    for collection in working_data:
                        collection.clear()
            finally:
                with self._lifecycle:
                    remaining = self._executing_threads[thread_id] - 1
                    if remaining:
                        self._executing_threads[thread_id] = remaining
                    else:
                        del self._executing_threads[thread_id]
                    self._release_work()

    def close(self) -> None:
        """Release runners after work unwinds; owners must first drain the shared queue."""
        with defer_keyboard_interrupt() as finish:
            with self._lifecycle:
                self.check_close_allowed()
                while self._closing_thread is not None:
                    if self._closing_thread == threading.get_ident():
                        return
                    finish(lambda: self._lifecycle.wait_for(lambda: self._closing_thread is None))
                if self._closed:
                    return
                self._closing = True
                self._closing_thread = threading.get_ident()
            try:
                with self._lifecycle:
                    finish(lambda: self._lifecycle.wait_for(lambda: self._active_work == 0))
                    runners = (
                        self._runtime_runners,
                        self._provided_runner_handles,
                        self._model_runners,
                    )
                    self._runtime_runners = {}
                    self._provided_runner_handles = None
                    self._model_runners = None
                # Finalizers may need application/runner locks. Drop the last
                # owned references only after leaving the lifecycle lock.
                del runners
                with self._lifecycle:
                    self._closed = True
            finally:
                with self._lifecycle:
                    self._closing_thread = None
                    self._lifecycle.notify_all()

    def check_close_allowed(self) -> None:
        """Reject waits on this thread before an owner detaches the manager."""
        with self._lifecycle:
            if threading.get_ident() in self._executing_threads:
                raise RuntimeError("Analysis manager cannot close from an executing job")
        if self._stage_queue is not None:
            self._stage_queue.check_close_allowed()

    def _execute_job(self, job_id: str) -> AnalysisJobStatus:
        status = self.get(job_id)
        if status.cancel_requested:
            return self._finish_cancelled(job_id)
        started = time.time()
        self._update(job_id, state="running", started_at=started)
        self._append_event(job_id, "info", "Analysis started")

        lifecycle = _RunnerLifecycle()
        try:
            self._prepare_job(job_id, lifecycle)
        except (_RunnerInitializationError, _RunnerPreflightError) as error:
            self._fail_stage(job_id, str(error), model=error.model)
            return self.get(job_id)
        except Exception as error:
            self._fail_stage(
                job_id,
                f"Analysis preparation failed: {exception_summary(error)}",
            )
            return self.get(job_id)

        if self.get(job_id).cancel_requested:
            return self._finish_cancelled(job_id)

        payload = self._payload(job_id)
        status = self.get(job_id)
        if status.models == ["sonara"]:
            batches = (
                (payload.candidates,)
                if payload.config.sonara_mode == "staged"
                else chunks(
                    payload.candidates,
                    max(1, payload.config.sonara_batch_size),
                )
            )
        else:
            # ML models: use single batch for staged mode, chunks for direct mode
            batches = (
                (payload.candidates,)
                if payload.config.ml_staging_config is not None
                else chunks(payload.candidates, max(1, status.track_batch_size))
            )
        for batch in batches:
            if self.get(job_id).cancel_requested:
                return self._finish_cancelled(job_id)
            if not self._process_batch(
                job_id,
                lifecycle,
                batch,
                payload.targets_by_track,
            ):
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
            avg_seconds_per_track=(
                None
                if final.processed == 0
                else (finished - (final.started_at or started)) / final.processed
            ),
        )
        self._append_event(job_id, "info", "Analysis completed")
        return self.get(job_id)

    def _prepare_job(
        self,
        job_id: str,
        lifecycle: _RunnerLifecycle,
    ) -> None:
        payload = self._payload(job_id)
        config = payload.config
        for model in config.models:
            try:
                handle = self._runner_for_model(
                    model,
                    self.get(job_id),
                    sonara_staging_config=config.sonara_staging_config,
                )
                runner = handle.runner
                _validate_runner(model, runner)
            except Exception as error:
                raise _RunnerInitializationError(model, error) from error
            if isinstance(runner, SonaraModelRunner):
                runner.bpm_min = config.sonara_bpm_min
                runner.bpm_max = config.sonara_bpm_max
                runner.progress = lambda done, total: self._sonara_progress(
                    job_id,
                    done,
                    total,
                )
                runner.cancelled = lambda: self.get(job_id).cancel_requested
                runner.track_result = lambda result: self._record_staged_sonara_result(
                    job_id,
                    result,
                )
            lifecycle.runners[model] = runner
            lifecycle.handles[model] = handle

        self._warm_up_models(job_id, config.models, lifecycle)

        active_outputs = tuple(
            output
            for model in config.models
            for output in lifecycle.runners[model].active_outputs
        )
        candidate_outputs = tuple(
            output
            for model in config.models
            for output in lifecycle.runners[model].candidate_outputs
        )
        _validate_output_set(active_outputs, label="active")
        _validate_output_set(candidate_outputs, label="candidate")
        active_keys = {output.key for output in active_outputs}
        if any(output.key not in active_keys for output in candidate_outputs):
            raise RuntimeError("candidate outputs must be a subset of active outputs")

        registered = self.db.register_analysis_outputs(active_outputs)
        registered_keys = {
            f"{family}/{output_kind}" for family, output_kind in active_keys
        }
        if set(registered) != registered_keys or len(registered) != len(active_outputs):
            raise RuntimeError(
                "analysis repository did not activate every runner output"
            )
        candidates = self.db.list_analysis_candidates(
            candidate_outputs,
            limit=config.limit,
            require_current_sonara=config.require_current_sonara,
        )
        if any(
            not isinstance(candidate, AnalysisCandidate) for candidate in candidates
        ):
            raise TypeError("analysis repository must return AnalysisCandidate values")

        model_keys = {
            model: {output.key for output in lifecycle.runners[model].candidate_outputs}
            for model in config.models
        }
        targets_by_track: dict[int, tuple[str, ...]] = {}
        requested_keys = {output.key for output in candidate_outputs}
        for candidate in candidates:
            for missing in candidate.missing_outputs:
                if missing.key not in requested_keys:
                    raise RuntimeError(
                        "candidate contains an unrequested analysis output"
                    )
            targets = tuple(
                model
                for model in config.models
                if any(
                    missing.key in model_keys[model]
                    for missing in candidate.missing_outputs
                )
            )
            if not targets:
                raise RuntimeError("candidate does not map to an initialized runner")
            track_id = candidate.target.track_id
            if track_id in targets_by_track:
                raise RuntimeError(
                    f"analysis repository returned duplicate track_id {track_id}"
                )
            targets_by_track[track_id] = targets

        payload.candidates = list(candidates)
        payload.targets_by_track = targets_by_track
        payload.track_outcomes = initial_track_outcomes(
            candidates,
            targets_by_track,
        )
        with self._store.locked(job_id) as status:
            status.total = len(candidates)
            status.model_progress = initial_model_progress(
                config.models,
                targets_by_track,
            )
        self._append_event(
            job_id,
            "info",
            f"Analysis candidates ready: {len(candidates)}",
        )

    def _warm_up_models(
        self,
        job_id: str,
        models: Sequence[str],
        lifecycle: _RunnerLifecycle,
    ) -> None:
        """Load every selected model before any track is decoded."""

        warm_up_started = time.time()
        self._update(job_id, phase="warmup")
        self._append_event(
            job_id,
            "info",
            f"Model warm-up started: {', '.join(models)}",
        )
        for position, model in enumerate(models, start=1):
            handle = lifecycle.handles[model]
            runner = lifecycle.runners[model]
            self._update(job_id, current_model=model, model_name=runner.model_name)
            model_started = time.time()
            try:
                with handle.lock:
                    if handle.preflight_complete:
                        loaded = False
                    else:
                        self._append_event(
                            job_id,
                            "info",
                            f"Warming up {model} ({position}/{len(models)})",
                            model=model,
                        )
                        handle.runner.preflight()
                        handle.preflight_complete = True
                        loaded = True
            except Exception as error:
                raise _RunnerPreflightError(model, error) from error
            self._update(job_id, device=runner.device)
            self._append_event(
                job_id,
                "info",
                (
                    f"{model} ready on {runner.device} "
                    f"in {time.time() - model_started:.1f}s"
                    if loaded
                    else f"{model} already resident on {runner.device}"
                ),
                model=model,
            )
        self._update(job_id, phase="analyzing", current_model=None)
        self._append_event(
            job_id,
            "info",
            f"Model warm-up completed in {time.time() - warm_up_started:.1f}s",
        )

    def _process_batch(
        self,
        job_id: str,
        lifecycle: _RunnerLifecycle,
        batch: list[AnalysisCandidate],
        targets_by_track: Mapping[int, tuple[str, ...]],
    ) -> bool:
        payload = self._payload(job_id)
        status = self.get(job_id)
        
        # SONARA-only path
        if status.models == ["sonara"]:
            items = [
                AnalysisBatchItem(
                    candidate=candidate,
                    decoded=None,
                    models=targets_by_track.get(
                        candidate.target.track_id,
                        (),
                    ),
                )
                for candidate in batch
                if targets_by_track.get(candidate.target.track_id)
            ]
        # ML Staged Mode path
        elif payload.config.ml_staging_config is not None:
            # ML staged processes ALL candidates in one pipeline run
            config = payload.config.ml_staging_config
            self._append_event(
                job_id,
                "info",
                f"ML staged pipeline starting: {len(batch)} tracks",
            )
            
            with ExitStack() as runner_locks:
                for model in ANALYSIS_MODEL_ORDER:
                    handle = lifecycle.handles.get(model)
                    if handle is None:
                        continue
                    runner_locks.enter_context(handle.lock)
                    runner = handle.runner
                    if isinstance(runner, EmbeddingModelRunner) and model in {"mert", "clap"}:
                        runner.cancelled = lambda: self.get(job_id).cancel_requested
                results = analyze_and_store_staged_ml(
                    repository=self.db,
                    candidates=batch,
                    model_runners=lifecycle.runners,
                    targets_by_track=targets_by_track,
                    config=config,
                    decode_audio=self._decode_audio,
                    cancelled=lambda: self.get(job_id).cancel_requested,
                    track_result_callback=lambda result: self._record_staged_ml_result(
                        job_id, result
                    ),
                    progress_callback=lambda phase, done, total: self._ml_staged_progress(
                        job_id, phase, done, total
                    ),
                    set_current_path=lambda path: self._update(
                        job_id, current_path=path
                    ),
                    mark_track_processed=lambda candidate: self._mark_track_processed(
                        job_id, candidate
                    ),
                )

            self._append_event(
                job_id,
                "info",
                f"ML staged pipeline completed: {len(results)} tracks processed",
            )

            # ML staged handles its own track processing
            return True

        # ML Direct Mode path (current)
        else:
            items = decode_analysis_batch(
                batch,
                targets_by_track,
                self._decode_audio,
                set_current_path=lambda path: self._update(
                    job_id,
                    current_path=path,
                ),
                mark_track_processed=lambda candidate: self._mark_track_processed(
                    job_id, candidate
                ),
            )

        # Run models on decoded items (SONARA or ML direct mode)
        for model in ANALYSIS_MODEL_ORDER:
            model_items = [item for item in items if model in item.models]
            if not model_items:
                continue
            if self.get(job_id).cancel_requested:
                return True
            runner = lifecycle.runners[model]
            self._update(
                job_id,
                current_model=model,
                model_name=runner.model_name,
                device=runner.device,
            )
            with lifecycle.handles[model].lock:
                if isinstance(runner, EmbeddingModelRunner) and model in {"mert", "clap"}:
                    runner.cancelled = lambda: self.get(job_id).cancel_requested
                if not self._run_model_batch(
                    job_id,
                    model,
                    runner,
                    model_items,
                ):
                    return False
            if self.get(job_id).cancel_requested:
                return True

        sonara_runner = lifecycle.runners.get("sonara")
        if (
            status.models == ["sonara"]
            and sonara_runner is not None
            and bool(getattr(sonara_runner, "incremental_results_emitted", False))
        ):
            return True

        for item in items:
            self._mark_track_processed(job_id, item.candidate)
        return True

    def _sonara_progress(
        self,
        job_id: str,
        done: int,
        total: int,
    ) -> None:
        if done == total or done == 1 or done % 10 == 0:
            self._append_event(
                job_id,
                "info",
                f"SONARA native batch progress {done}/{total}",
                model="sonara",
            )

    def _runner_for_model(
        self,
        model: str,
        status: AnalysisJobStatus,
        *,
        sonara_staging_config: SonaraStagingConfig | None = None,
    ) -> _RunnerHandle:
        if self._model_runners is not None:
            try:
                assert self._provided_runner_handles is not None
                return self._provided_runner_handles[model]
            except KeyError as error:
                raise ValueError(
                    f"No analysis runner configured for: {model}"
                ) from error
        if model == "sonara":
            runner = self._runner_factory(
                model,
                status.device_requested,
                status.inference_batch_size,
                status.top_k,
            )
            if isinstance(runner, SonaraModelRunner):
                runner.staging_config = sonara_staging_config
            return _RunnerHandle(runner)

        key = _RunnerRuntimeKey(
            model=model,
            device_requested=status.device_requested,
            inference_batch_size=status.inference_batch_size,
            top_k=status.top_k,
        )
        return self._cached_ml_runner(key)

    def _cached_ml_runner(self, key: _RunnerRuntimeKey) -> _RunnerHandle:
        if self._provided_runner_handles is not None:
            try:
                return self._provided_runner_handles[key.model]
            except KeyError as error:
                raise ValueError(f"No analysis runner configured for: {key.model}") from error
        with self._runtime_runners_lock:
            cached = self._runtime_runners.get(key)
            if cached is None:
                cached = _RunnerHandle(
                    self._runner_factory(
                        key.model,
                        key.device_requested,
                        key.inference_batch_size,
                        key.top_k,
                    )
                )
                self._runtime_runners[key] = cached
            return cached

    def _run_model_batch(
        self,
        job_id: str,
        model: str,
        runner: AnalysisModelRunner,
        items: list[AnalysisBatchItem],
    ) -> bool:
        try:
            results = _validated_runner_results(
                runner.analyze_batch(self.db, items),
                items,
            )
        except EmbeddingCancelledError:
            raise
        except Exception as error:
            if model == "sonara":
                self._fail_stage(
                    job_id,
                    f"SONARA native batch failed: {exception_summary(error)}",
                    model=model,
                )
                return False
            if len(items) <= 1:
                self._record_model_failure(
                    job_id,
                    model,
                    items[0].candidate,
                    error,
                )
                return True
            LOGGER.warning(
                "Analysis model batch failed; retrying tracks individually "
                "job_id=%s model=%s batch_size=%s error=%s",
                job_id,
                model,
                len(items),
                exception_summary(error),
            )
            self._append_event(
                job_id,
                "warn",
                f"{model} batch failed; retrying tracks individually",
                model=model,
            )
            for item in items:
                if model in {"mert", "clap"} and self.get(job_id).cancel_requested:
                    raise EmbeddingCancelledError(f"{model.upper()} analysis cancelled")
                try:
                    item_results = _validated_runner_results(
                        runner.analyze_batch(self.db, [item]),
                        [item],
                    )
                    item_error = item_results[0]
                except EmbeddingCancelledError:
                    raise
                except Exception as item_exception:
                    item_error = item_exception
                if item_error is None:
                    self._record_model_success(
                        job_id,
                        model,
                        item.candidate,
                        decode_method=self._runner_decode_method(
                            model,
                            runner,
                            item.candidate,
                        ),
                    )
                else:
                    self._record_model_failure(
                        job_id,
                        model,
                        item.candidate,
                        item_error,
                    )
            return True

        if model == "sonara":
            self._record_sonara_metrics(job_id, runner)
            if bool(getattr(runner, "incremental_results_emitted", False)):
                return True
        for item, error in zip(items, results):
            if error is None:
                self._record_model_success(
                    job_id,
                    model,
                    item.candidate,
                    decode_method=self._runner_decode_method(
                        model,
                        runner,
                        item.candidate,
                    ),
                )
            else:
                self._record_model_failure(
                    job_id,
                    model,
                    item.candidate,
                    error,
                )
        return True

    def _record_staged_sonara_result(
        self,
        job_id: str,
        result: StagedSonaraResult,
    ) -> None:
        if result.error is None:
            self._record_model_success(
                job_id,
                "sonara",
                result.candidate,
                decode_method="ffmpeg" if result.used_ffmpeg_fallback else None,
            )
        else:
            self._record_model_failure(
                job_id,
                "sonara",
                result.candidate,
                result.error,
            )
        self._mark_track_processed(job_id, result.candidate)

    def _record_staged_ml_result(
        self,
        job_id: str,
        result: MLStagedResult,
    ) -> None:
        """Record each requested model before the pipeline completes the track."""
        models = self._payload(job_id).targets_by_track[result.target.track_id]
        for model in models:
            if model in result.model_errors:
                error = result.model_errors[model]
            elif not result.track_complete:
                continue
            else:
                error = result.error or RuntimeError(f"{model} did not return a staged result")
            if error is None:
                self._record_model_success(job_id, model, result.candidate)
            else:
                self._record_model_failure(job_id, model, result.candidate, error)

    def _ml_staged_progress(
        self,
        job_id: str,
        phase: str,
        done: int,
        total: int,
    ) -> None:
        """Progress callback for ML staged pipeline phases."""
        if done == 1 or done == total or done % 10 == 0:
            phase_label = {
                "copy": "Copy",
                "copy_queued": "Copy queued",
                "decode": "Decode",
            }.get(phase, phase)
            
            # For inference phases (inference:model_name), extract model
            if phase.startswith("inference:"):
                model_name = phase.split(":", 1)[1].upper()
                self._append_event(
                    job_id,
                    "info",
                    f"ML staged · {model_name} inference {done}/{total}",
                    model=phase.split(":", 1)[1],
                )
            else:
                self._append_event(
                    job_id,
                    "info",
                    f"ML staged · {phase_label} {done}/{total}",
                )


    def _record_sonara_metrics(
        self,
        job_id: str,
        runner: AnalysisModelRunner,
    ) -> None:
        metrics = getattr(runner, "last_metrics", None)
        if not isinstance(metrics, SonaraBatchMetrics):
            return
        source_mib = metrics.source_bytes / (1024 * 1024)
        throughput = (
            source_mib / metrics.analyze_seconds if metrics.analyze_seconds > 0 else 0.0
        )
        self._append_event(
            job_id,
            "info",
            f"SONARA batch: {metrics.track_count} tracks · "
            f"staging {metrics.staged_track_count} · "
            f"copy {metrics.copy_seconds:.2f}s · "
            f"analyze {metrics.analyze_seconds:.2f}s "
            f"({throughput:.1f} MiB/s) · "
            f"prepare {metrics.prepare_seconds:.2f}s · "
            f"store {metrics.store_seconds:.2f}s",
            model="sonara",
        )

    def _record_model_success(
        self,
        job_id: str,
        model: str,
        candidate: AnalysisCandidate,
        *,
        decode_method: DecodeMethod | None = None,
    ) -> None:
        apply_track_model_result(
            self._track_outcome(job_id, candidate.target.track_id),
            failed=False,
            decode_method=decode_method,
        )
        with self._store.locked(job_id) as status:
            apply_model_success(status, model)

    def _record_model_failure(
        self,
        job_id: str,
        model: str,
        candidate: AnalysisCandidate,
        error: Exception,
        *,
        emit_event: bool = True,
    ) -> None:
        error_text = exception_summary(error)
        track_id = candidate.target.track_id
        log_failure(
            LOGGER,
            "Analysis model failed job_id=%s model=%s track_id=%s path=%s error=%s",
            job_id,
            model,
            track_id,
            candidate.file_path,
            error_text,
        )
        apply_track_model_result(
            self._track_outcome(job_id, track_id),
            failed=True,
        )
        with self._store.locked(job_id) as status:
            apply_model_failure(
                status,
                model,
                AnalysisTrackError(
                    track_id=track_id,
                    path=candidate.file_path,
                    error=error_text,
                    model=model,
                ),
            )
        if emit_event:
            self._append_event(
                job_id,
                "error",
                f"Track failed: {error_text}",
                path=candidate.file_path,
                track_id=track_id,
                model=model,
                log=False,
            )

    def _mark_track_processed(
        self,
        job_id: str,
        candidate: AnalysisCandidate,
    ) -> None:
        track_id = candidate.target.track_id
        outcome = self._track_outcome(job_id, track_id)
        with self._store.locked(job_id) as status:
            analyzed = apply_track_processed(
                status,
                track_path=candidate.file_path,
                outcome=outcome,
                now=time.time(),
            )
        if analyzed:
            decode_method = outcome.decode_method if outcome is not None else None
            message = (
                f"[{decode_method}] Track analyzed"
                if decode_method is not None
                else "Track analyzed"
            )
            self._append_event(
                job_id,
                "ok",
                message,
                path=candidate.file_path,
                track_id=track_id,
            )

    @staticmethod
    def _runner_decode_method(
        model: str,
        runner: AnalysisModelRunner,
        candidate: AnalysisCandidate,
    ) -> DecodeMethod | None:
        track_id = candidate.target.track_id
        ffmpeg_track_ids = getattr(runner, "last_ffmpeg_fallback_track_ids", ())
        if track_id in ffmpeg_track_ids:
            return "ffmpeg"
        if model != "sonara":
            return "torchcodec"
        return None

    def _fail_stage(
        self,
        job_id: str,
        message: str,
        *,
        model: str | None = None,
    ) -> None:
        self._update(
            job_id,
            state="failed",
            finished_at=time.time(),
            current_path=None,
            current_model=None,
        )
        self._append_event(job_id, "error", message, model=model)

    def _finish_cancelled(self, job_id: str) -> AnalysisJobStatus:
        self._update(
            job_id,
            state="cancelled",
            finished_at=time.time(),
            current_path=None,
            current_model=None,
        )
        self._append_event(job_id, "warn", "Analysis cancelled")
        return self.get(job_id)

    def get(self, job_id: str) -> AnalysisJobStatus:
        return self._store.get(job_id)

    def latest(self) -> AnalysisJobStatus | None:
        return self._store.latest()

    def cancel(self, job_id: str) -> AnalysisJobStatus:
        self._update(job_id, cancel_requested=True)
        return self.get(job_id)

    def _track_outcome(
        self,
        job_id: str,
        track_id: int,
    ) -> AnalysisTrackOutcome | None:
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
        log: bool = True,
    ) -> None:
        """Record one job event for the UI, and by default for the app log too.

        Callers that already wrote a structured record pass ``log=False`` so the
        failure reaches the log once instead of twice.
        """

        if log:
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
        self._store.append_event(
            job_id,
            AnalysisLogEvent(
                time.time(),
                level,
                message,
                path,
                track_id,
                model,
            ),
        )

    @staticmethod
    def _copy_status(status: AnalysisJobStatus) -> AnalysisJobStatus:
        return copy_analysis_status(status)


def _validate_runner(
    model: str,
    runner: AnalysisModelRunner,
) -> None:
    if runner.model != model:
        raise ValueError(
            f"runner model mismatch: expected {model!r}, got {runner.model!r}"
        )
    active = tuple(runner.active_outputs)
    candidates = tuple(runner.candidate_outputs)
    if not active or not candidates:
        raise ValueError(f"{model} runner must declare analysis outputs")
    expected_family = model
    if any(output.analysis_family != expected_family for output in active):
        raise ValueError(
            f"{model} runner declared an output for another analysis family"
        )
    active_keys = {output.key for output in active}
    if any(output.key not in active_keys for output in candidates):
        raise ValueError(f"{model} candidate outputs are not active runner outputs")


def _validate_output_set(
    outputs: Sequence[AnalysisOutput],
    *,
    label: str,
) -> None:
    if not outputs:
        raise ValueError(f"{label} analysis outputs must not be empty")
    if any(not isinstance(output, AnalysisOutput) for output in outputs):
        raise TypeError(f"{label} analysis outputs must contain AnalysisOutput values")
    keys = [output.key for output in outputs]
    if len(set(keys)) != len(keys):
        raise ValueError(
            f"{label} analysis outputs contain duplicate family/output keys"
        )


def _validated_runner_results(
    results: Sequence[Exception | None],
    items: Sequence[AnalysisBatchItem],
) -> tuple[Exception | None, ...]:
    normalized = tuple(results)
    if len(normalized) != len(items):
        raise RuntimeError(
            "analysis runner result count does not match candidate count"
        )
    if any(
        result is not None and not isinstance(result, Exception)
        for result in normalized
    ):
        raise TypeError("analysis runner results must contain only exceptions or None")
    for result in normalized:
        if isinstance(result, EmbeddingCancelledError):
            raise result
    return normalized
