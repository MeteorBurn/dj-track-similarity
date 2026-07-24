from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, cast

from . import analysis_model_runners as model_runner_module
from .analysis_config import (
    ANALYSIS_MODEL_ORDER,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    DEFAULT_SONARA_BATCH_SIZE,
    AnalysisJobConfig,
    build_analysis_job_config,
)
from .analysis_job_batch import (
    AnalysisBatchItem,
    DecodeAudio,
    decode_analysis_batch,
)
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
    AnalysisWriteRepository,
    EmbeddingModelRunner,
    MaestModelRunner,
    RunnerFactory,
    SonaraModelRunner,
)
from .analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    InactiveAnalysisOutputError,
)
from .analysis_queue import AnalysisStageQueue
from .audio_loader import load_decoded_audio
from .job_runtime import JobStore, chunks
from .logging_config import (
    exception_summary,
    log_failure,
    log_job_event,
)
from .sonara_contract import SONARA_OUTPUT_KINDS
from .sonara_features import (
    SonaraBatchMetrics,
    analysis_outputs_for_sonara_runtime,
)


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


@dataclass
class _AnalysisPayload:
    config: AnalysisJobConfig
    candidates: list[AnalysisCandidate] = field(default_factory=list)
    targets_by_track: dict[int, tuple[str, ...]] = field(default_factory=dict)
    track_outcomes: dict[int, AnalysisTrackOutcome] = field(default_factory=dict)


@dataclass
class _RunnerLifecycle:
    runners: dict[str, AnalysisModelRunner] = field(default_factory=dict)


class _RunnerInitializationError(RuntimeError):
    def __init__(self, model: str, error: Exception) -> None:
        super().__init__(f"{model} initialization failed: {exception_summary(error)}")
        self.model = model


class _RunnerPreflightError(RuntimeError):
    def __init__(self, model: str, error: Exception) -> None:
        super().__init__(f"{model} preflight failed: {exception_summary(error)}")
        self.model = model


class _SonaraPreflightRepository(AnalysisWriteRepository, Protocol):
    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None: ...


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
        self._runner_factory = (
            runner_factory or model_runner_module.default_model_runners
        )
        self._decode_audio = decode_audio
        self.track_batch_size = max(1, int(track_batch_size))
        self.inference_batch_size = max(1, int(inference_batch_size))
        self.sonara_batch_size = max(1, int(sonara_batch_size))
        self._stage_queue = stage_queue
        self._store: JobStore[AnalysisJobStatus] = JobStore(
            self._copy_status,
            unknown_label="analysis job",
        )

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
            sonara_outputs=sonara_outputs,
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
            top_k=config.top_k,
            sonara_outputs=list(config.sonara_outputs),
        )
        self._store.add(
            job_id,
            status,
            payload=_AnalysisPayload(config=config),
        )
        if config.models == ("sonara",):
            output_names = ", ".join(output.title() for output in config.sonara_outputs)
            settings_message = (
                f"SONARA queued · outputs {output_names} · "
                f"batch {config.sonara_batch_size}"
            )
        else:
            model_names = ", ".join(model.upper() for model in config.models)
            settings_message = (
                f"ML queued · models {model_names} · "
                f"Device {config.device.upper()} · "
                f"Track batch {config.track_batch_size} · "
                f"Inference batch {config.inference_batch_size}"
            )
        self._append_event(job_id, "info", settings_message)
        return job_id

    def validate_sonara_preflight(self) -> None:
        """Require the loaded runtime's exact four-output SONARA release.

        The caller supplies no release identity.  All four contracts are
        derived from the loaded SONARA runtime, compared with the repository's
        active outputs, and then checked through the normal v7 candidate
        boundary before a job may be queued.
        """

        expected_outputs = analysis_outputs_for_sonara_runtime()
        expected_kinds = tuple(
            output.contract.output_kind for output in expected_outputs
        )
        if expected_kinds != SONARA_OUTPUT_KINDS or any(
            output.contract.analysis_family != "sonara" for output in expected_outputs
        ):
            raise RuntimeError(
                "Loaded SONARA runtime did not derive the exact core, timeline, "
                "embedding, and fingerprint outputs"
            )

        releases = {output.contract.release_hash for output in expected_outputs}
        if len(releases) != 1 or None in releases:
            raise RuntimeError("Loaded SONARA runtime outputs do not share one release")

        repository = cast(_SonaraPreflightRepository, self.db)
        try:
            active_outputs = tuple(
                repository.active_analysis_output(*expected.key)
                for expected in expected_outputs
            )
        except InactiveAnalysisOutputError as error:
            raise _sonara_release_preparation_required(
                "the active SONARA release settings are inconsistent"
            ) from error

        for expected, active in zip(expected_outputs, active_outputs):
            if active is None:
                raise _sonara_release_preparation_required(
                    f"the {expected.contract.output_kind} output is not active"
                )
            if (
                active.contract_hash != expected.contract_hash
                or active.contract.canonical_payload_json
                != expected.contract.canonical_payload_json
            ):
                raise _sonara_release_preparation_required(
                    f"the active {expected.contract.output_kind} output does "
                    "not match the loaded runtime"
                )

        try:
            repository.list_analysis_candidates(
                expected_outputs,
                limit=0,
            )
        except InactiveAnalysisOutputError as error:
            raise _sonara_release_preparation_required(
                "the exact runtime outputs are not ready for analysis"
            ) from error

    def start(self, **kwargs: object) -> AnalysisJobStatus:
        job_id = self.create_job(**kwargs)
        if self._stage_queue is not None:
            self._stage_queue.submit(lambda: self.run_job(job_id))
        else:
            threading.Thread(
                target=self.run_job,
                args=(job_id,),
                daemon=True,
            ).start()
        return self.get(job_id)

    def run_sync(self, **kwargs: object) -> AnalysisJobStatus:
        return self.run_job(self.create_job(**kwargs))

    def run_job(self, job_id: str) -> AnalysisJobStatus:
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
        batch_size = (
            status.sonara_batch_size
            if status.models == ["sonara"]
            else status.track_batch_size
        )
        for batch in chunks(payload.candidates, max(1, batch_size)):
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
                runner = self._runner_for_model(model, self.get(job_id))
                _validate_runner(model, runner)
            except Exception as error:
                raise _RunnerInitializationError(model, error) from error
            if isinstance(runner, SonaraModelRunner):
                runner.progress = lambda done, total: self._sonara_progress(
                    job_id,
                    done,
                    total,
                )
            lifecycle.runners[model] = runner

        for model in config.models:
            try:
                lifecycle.runners[model].preflight()
            except Exception as error:
                raise _RunnerPreflightError(model, error) from error

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
        active_hashes = {output.contract_hash for output in active_outputs}
        if any(
            output.contract_hash not in active_hashes for output in candidate_outputs
        ):
            raise RuntimeError("candidate outputs must be a subset of active outputs")

        registered = self.db.register_analysis_outputs(active_outputs)
        if set(registered) != active_hashes or len(registered) != len(active_outputs):
            raise RuntimeError(
                "analysis repository did not activate every runner output"
            )
        candidates = self.db.list_analysis_candidates(
            candidate_outputs,
            limit=config.limit,
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
        requested_by_key = {
            output.key: output.contract_hash for output in candidate_outputs
        }
        for candidate in candidates:
            for missing in candidate.missing_outputs:
                expected_hash = requested_by_key.get(missing.key)
                if expected_hash != missing.contract_hash:
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

    def _process_batch(
        self,
        job_id: str,
        lifecycle: _RunnerLifecycle,
        batch: list[AnalysisCandidate],
        targets_by_track: Mapping[int, tuple[str, ...]],
    ) -> bool:
        status = self.get(job_id)
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
        else:
            items = decode_analysis_batch(
                batch,
                targets_by_track,
                self._decode_audio,
                set_current_path=lambda path: self._update(
                    job_id,
                    current_path=path,
                ),
                record_decode_failure=lambda candidate, targets, error: (
                    self._record_decode_failure(
                        job_id,
                        candidate,
                        targets,
                        error,
                    )
                ),
                mark_track_processed=lambda candidate: self._mark_track_processed(
                    job_id, candidate
                ),
            )

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
            if not self._run_model_batch(
                job_id,
                model,
                runner,
                model_items,
            ):
                return False

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
    ) -> AnalysisModelRunner:
        if self._model_runners is not None:
            try:
                return self._model_runners[model]
            except KeyError as error:
                raise ValueError(
                    f"No analysis runner configured for: {model}"
                ) from error
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
            results = _validated_runner_results(
                runner.analyze_batch(self.db, items),
                items,
            )
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
                try:
                    item_results = _validated_runner_results(
                        runner.analyze_batch(self.db, [item]),
                        [item],
                    )
                    item_error = item_results[0]
                except Exception as item_exception:
                    item_error = item_exception
                if item_error is None:
                    self._record_model_success(
                        job_id,
                        model,
                        item.candidate,
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
        for item, error in zip(items, results):
            if error is None:
                self._record_model_success(
                    job_id,
                    model,
                    item.candidate,
                )
            else:
                self._record_model_failure(
                    job_id,
                    model,
                    item.candidate,
                    error,
                )
        return True

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
            f"analyze {metrics.analyze_seconds:.2f}s "
            f"({throughput:.1f} MiB/s) · "
            f"prepare {metrics.prepare_seconds:.2f}s · "
            f"store {metrics.store_seconds:.2f}s",
            model="sonara",
        )

    def _record_decode_failure(
        self,
        job_id: str,
        candidate: AnalysisCandidate,
        targets: tuple[str, ...],
        error: Exception,
    ) -> None:
        for model in targets:
            self._record_model_failure(
                job_id,
                model,
                candidate,
                error,
                emit_event=False,
            )
        self._append_event(
            job_id,
            "error",
            f"Track decode failed: {exception_summary(error)}",
            path=candidate.file_path,
            track_id=candidate.target.track_id,
        )

    def _record_model_success(
        self,
        job_id: str,
        model: str,
        candidate: AnalysisCandidate,
    ) -> None:
        apply_track_model_result(
            self._track_outcome(job_id, candidate.target.track_id),
            failed=False,
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
            self._append_event(
                job_id,
                "ok",
                "Track analyzed",
                path=candidate.file_path,
                track_id=track_id,
            )

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
    if any(output.contract.analysis_family != expected_family for output in active):
        raise ValueError(
            f"{model} runner declared an output for another analysis family"
        )
    active_hashes = {output.contract_hash for output in active}
    if any(output.contract_hash not in active_hashes for output in candidates):
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
    return normalized


def _sonara_release_preparation_required(reason: str) -> RuntimeError:
    return RuntimeError(
        "SONARA_RELEASE_PREPARATION_REQUIRED: "
        f"{reason}. Back up the selected Core and Artifacts databases, then "
        "run prepare-sonara-release for the loaded runtime before analysis."
    )
