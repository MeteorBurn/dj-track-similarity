from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import cast

from .analysis_config import DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE, DEFAULT_ANALYSIS_TRACK_BATCH_SIZE
from .analysis_jobs import AnalysisJobManager
from .analysis_queue import AnalysisStageQueue
from .classifier_jobs import ClassifierJobManager
from .job_runtime import JobStore


PIPELINE_STAGE_ORDER = ("sonara", "ml", "classifiers")


@dataclass
class PipelineStageStatus:
    name: str
    state: str = "pending"
    child_job_id: str | None = None
    error: str | None = None


@dataclass
class AnalysisPipelineStatus:
    job_id: str
    state: str
    order: list[str]
    stages: dict[str, PipelineStageStatus]
    current_stage: str | None = None
    started_at: float | None = None
    finished_at: float | None = None
    cancel_requested: bool = False


@dataclass(frozen=True)
class _PipelinePayload:
    limit: int | None
    sonara: dict[str, object]
    ml: dict[str, object]
    classifiers: dict[str, object]


class AnalysisPipelineManager:
    def __init__(
        self,
        analysis_jobs: AnalysisJobManager,
        classifier_jobs: ClassifierJobManager,
        stage_queue: AnalysisStageQueue,
    ) -> None:
        self.analysis_jobs = analysis_jobs
        self.classifier_jobs = classifier_jobs
        self.stage_queue = stage_queue
        self._store = JobStore(self._copy_status, unknown_label="analysis pipeline")

    def create_job(
        self,
        *,
        stages: list[str],
        limit: int | None,
        sonara: dict[str, object] | None = None,
        ml: dict[str, object] | None = None,
        classifiers: dict[str, object] | None = None,
    ) -> str:
        selected = [stage for stage in PIPELINE_STAGE_ORDER if stage in stages]
        unknown = sorted(set(stages) - set(PIPELINE_STAGE_ORDER))
        if unknown:
            raise ValueError(f"Unknown pipeline stages: {', '.join(unknown)}")
        if not selected:
            raise ValueError("At least one pipeline stage must be selected")
        if "sonara" in selected:
            self.analysis_jobs.validate_sonara_preflight()
        job_id = str(uuid.uuid4())
        status = AnalysisPipelineStatus(
            job_id=job_id,
            state="queued",
            order=selected,
            stages={stage: PipelineStageStatus(name=stage) for stage in selected},
        )
        self._store.add(
            job_id,
            status,
            payload=_PipelinePayload(
                limit=limit,
                sonara=dict(sonara or {}),
                ml=dict(ml or {}),
                classifiers=dict(classifiers or {}),
            ),
        )
        return job_id

    def start(self, **kwargs: object) -> AnalysisPipelineStatus:
        job_id = self.create_job(**kwargs)
        self.stage_queue.submit(lambda: self.run_job(job_id))
        return self.get(job_id)

    def run_job(self, job_id: str) -> AnalysisPipelineStatus:
        status = self.get(job_id)
        payload = cast(_PipelinePayload, self._store.payload(job_id))
        if status.cancel_requested:
            return self._finish_cancelled(job_id)
        self._update(job_id, state="running", started_at=time.time())
        for stage in status.order:
            if self.get(job_id).cancel_requested:
                return self._finish_cancelled(job_id)
            self._set_stage(job_id, stage, state="running")
            try:
                child_id, child_state = self._run_stage(job_id, stage, payload)
            except Exception as error:
                self._set_stage(job_id, stage, state="failed", error=str(error))
                self._update(job_id, state="failed", finished_at=time.time(), current_stage=None)
                return self.get(job_id)
            self._set_stage(job_id, stage, state=child_state, child_job_id=child_id)
            if child_state == "cancelled":
                return self._finish_cancelled(job_id)
            if child_state == "failed":
                self._update(job_id, state="failed", finished_at=time.time(), current_stage=None)
                return self.get(job_id)
        self._update(job_id, state="completed", finished_at=time.time(), current_stage=None)
        return self.get(job_id)

    def _run_stage(self, parent_job_id: str, stage: str, payload: _PipelinePayload) -> tuple[str, str]:
        if stage == "sonara":
            job_id = self.analysis_jobs.create_job(
                models=["sonara"],
                limit=payload.limit,
                sonara_outputs=cast(list[str] | None, payload.sonara.get("outputs")),
                sonara_batch_size=cast(int | None, payload.sonara.get("batch_size")),
            )
            self._set_stage(parent_job_id, stage, state="running", child_job_id=job_id)
            if self.get(parent_job_id).cancel_requested:
                self.analysis_jobs.cancel(job_id)
                return job_id, "cancelled"
            return job_id, self.analysis_jobs.run_job(job_id).state
        if stage == "ml":
            job_id = self.analysis_jobs.create_job(
                models=cast(list[str], payload.ml.get("models")),
                limit=payload.limit,
                device=str(payload.ml.get("device") or "auto"),
                top_k=int(payload.ml.get("top_k") or 3),
                track_batch_size=int(payload.ml.get("track_batch_size") or DEFAULT_ANALYSIS_TRACK_BATCH_SIZE),
                inference_batch_size=int(payload.ml.get("inference_batch_size") or DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE),
            )
            self._set_stage(parent_job_id, stage, state="running", child_job_id=job_id)
            if self.get(parent_job_id).cancel_requested:
                self.analysis_jobs.cancel(job_id)
                return job_id, "cancelled"
            return job_id, self.analysis_jobs.run_job(job_id).state
        job_id = self.classifier_jobs.create_job(
            classifiers=cast(list[str], payload.classifiers.get("classifier_keys")),
            limit=payload.limit,
        )
        self._set_stage(parent_job_id, stage, state="running", child_job_id=job_id)
        if self.get(parent_job_id).cancel_requested:
            self.classifier_jobs.cancel(job_id)
            return job_id, "cancelled"
        return job_id, self.classifier_jobs.run_job(job_id).state

    def cancel(self, job_id: str) -> AnalysisPipelineStatus:
        with self._store.locked(job_id) as status:
            if status.state not in {"queued", "running"}:
                return self._copy_status(status)
            status.cancel_requested = True
            for stage in status.stages.values():
                if stage.state == "pending":
                    stage.state = "cancelled"
            if status.state == "queued":
                status.state = "cancelled"
                status.finished_at = time.time()
            current_stage = status.current_stage
            child_id = status.stages[current_stage].child_job_id if current_stage else None
        if current_stage and child_id:
            if current_stage == "classifiers":
                self.classifier_jobs.cancel(child_id)
            else:
                self.analysis_jobs.cancel(child_id)
        return self.get(job_id)

    def get(self, job_id: str) -> AnalysisPipelineStatus:
        return self._store.get(job_id)

    def latest(self) -> AnalysisPipelineStatus | None:
        return self._store.latest()

    def _finish_cancelled(self, job_id: str) -> AnalysisPipelineStatus:
        with self._store.locked(job_id) as status:
            for stage in status.stages.values():
                if stage.state == "pending":
                    stage.state = "cancelled"
            status.state = "cancelled"
            status.current_stage = None
            status.finished_at = time.time()
        return self.get(job_id)

    def _set_stage(self, job_id: str, stage: str, **changes: object) -> None:
        with self._store.locked(job_id) as status:
            status.current_stage = stage
            stage_status = status.stages[stage]
            for key, value in changes.items():
                setattr(stage_status, key, value)

    def _update(self, job_id: str, **changes: object) -> None:
        self._store.update(job_id, **changes)

    @staticmethod
    def _copy_status(status: AnalysisPipelineStatus) -> AnalysisPipelineStatus:
        return AnalysisPipelineStatus(
            job_id=status.job_id,
            state=status.state,
            order=list(status.order),
            stages={
                key: PipelineStageStatus(
                    name=value.name,
                    state=value.state,
                    child_job_id=value.child_job_id,
                    error=value.error,
                )
                for key, value in status.stages.items()
            },
            current_stage=status.current_stage,
            started_at=status.started_at,
            finished_at=status.finished_at,
            cancel_requested=status.cancel_requested,
        )
