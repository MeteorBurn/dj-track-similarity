from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from .analysis_config import (
    ANALYSIS_MODEL_ORDER,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    DEFAULT_SONARA_BATCH_SIZE,
)
from .analysis_models import AnalysisCandidate
from .sonara_runtime import DEFAULT_SONARA_BPM_MAX, DEFAULT_SONARA_BPM_MIN


DecodeMethod = Literal["torchcodec", "ffmpeg"]

_DECODE_METHOD_PRIORITY: dict[DecodeMethod, int] = {
    "torchcodec": 1,
    "ffmpeg": 2,
}


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
    decode_method: DecodeMethod | None = None


@dataclass
class AnalysisJobStatus:
    job_id: str
    state: str
    adapter_name: str = "multi"
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
    track_batch_size: int = DEFAULT_ANALYSIS_TRACK_BATCH_SIZE
    inference_batch_size: int = DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE
    sonara_batch_size: int = DEFAULT_SONARA_BATCH_SIZE
    sonara_mode: str = "direct"
    sonara_bpm_min: float = DEFAULT_SONARA_BPM_MIN
    sonara_bpm_max: float = DEFAULT_SONARA_BPM_MAX
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
    candidates: Sequence[AnalysisCandidate],
    targets_by_track: Mapping[int, tuple[str, ...]],
) -> dict[int, AnalysisTrackOutcome]:
    return {
        candidate.target.track_id: AnalysisTrackOutcome(
            target_count=len(targets_by_track[candidate.target.track_id])
        )
        for candidate in candidates
    }


def record_track_model_result(
    outcome: AnalysisTrackOutcome | None,
    *,
    failed: bool,
    decode_method: DecodeMethod | None = None,
) -> None:
    if outcome is None:
        return
    if failed:
        outcome.failures += 1
    else:
        outcome.successes += 1
        if decode_method is not None and (
            outcome.decode_method is None
            or _DECODE_METHOD_PRIORITY[decode_method]
            > _DECODE_METHOD_PRIORITY[outcome.decode_method]
        ):
            outcome.decode_method = decode_method


def record_model_success(status: AnalysisJobStatus, model: str) -> None:
    progress = status.model_progress[model]
    progress.processed += 1
    progress.analyzed += 1


def record_model_failure(
    status: AnalysisJobStatus, model: str, error: AnalysisTrackError
) -> None:
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
        track_batch_size=status.track_batch_size,
        inference_batch_size=status.inference_batch_size,
        sonara_batch_size=status.sonara_batch_size,
        sonara_mode=status.sonara_mode,
        sonara_bpm_min=status.sonara_bpm_min,
        sonara_bpm_max=status.sonara_bpm_max,
        top_k=status.top_k,
    )
