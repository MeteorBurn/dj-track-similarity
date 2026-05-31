from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .analysis_config import ANALYSIS_MODEL_ORDER, DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE, DEFAULT_ANALYSIS_TRACK_BATCH_SIZE
from .models import Track


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


def initial_model_progress(
    models: Sequence[str],
    targets_by_track: Mapping[int, tuple[str, ...]],
) -> dict[str, AnalysisModelProgress]:
    progress = {model: AnalysisModelProgress() for model in models}
    for targets in targets_by_track.values():
        for model in targets:
            progress[model].total += 1
    return progress


def initial_track_outcomes(
    tracks: Sequence[Track],
    targets_by_track: Mapping[int, tuple[str, ...]],
) -> dict[int, AnalysisTrackOutcome]:
    return {track.id: AnalysisTrackOutcome(target_count=len(targets_by_track[track.id])) for track in tracks}


def record_track_model_result(outcome: AnalysisTrackOutcome | None, *, failed: bool) -> None:
    if outcome is None:
        return
    if failed:
        outcome.failures += 1
    else:
        outcome.successes += 1


def record_model_success(status: AnalysisJobStatus, model: str) -> None:
    progress = status.model_progress[model]
    progress.processed += 1
    progress.analyzed += 1


def record_model_failure(status: AnalysisJobStatus, model: str, error: AnalysisTrackError) -> None:
    progress = status.model_progress[model]
    progress.processed += 1
    progress.failed += 1
    status.errors.append(error)


def mark_track_processed(
    status: AnalysisJobStatus,
    *,
    track_path: str,
    outcome: AnalysisTrackOutcome | None,
    now: float,
) -> bool:
    status.current_path = track_path
    status.processed += 1
    if outcome is None or outcome.target_count <= 0:
        status.skipped += 1
        analyzed = False
    elif outcome.failures:
        status.failed += 1
        analyzed = False
    elif outcome.successes >= outcome.target_count:
        status.analyzed += 1
        analyzed = True
    else:
        status.skipped += 1
        analyzed = False
    if status.started_at and status.processed:
        status.avg_seconds_per_track = (now - status.started_at) / status.processed
    return analyzed


def copy_analysis_status(status: AnalysisJobStatus) -> AnalysisJobStatus:
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
