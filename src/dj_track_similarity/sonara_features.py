"""Native SONARA batch orchestration for the analysis repository."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .audio_loader import load_audio_mono_with_ffmpeg
from .analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
    AnalysisWriteResult,
    SonaraWrite,
)
from .timestamps import utc_timestamp
from .sonara_runtime import (
    SONARA_ANALYSIS_MODE,
    SONARA_BPM_MAX,
    SONARA_BPM_MIN,
    SONARA_SAMPLE_RATE,
    SONARA_VOCALNESS_MODEL_SELECTOR,
    sonara_requested_features,
)
from .sonara_storage import prepare_sonara_write


LOGGER = logging.getLogger(__name__)


class SonaraAnalysisRepository(Protocol):
    """Repository boundary required by the SONARA batch orchestrator."""

    def register_analysis_outputs(
        self,
        outputs: Sequence[AnalysisOutput],
    ) -> tuple[str, ...]: ...

    def save_sonara_results(
        self,
        writes: Sequence[SonaraWrite],
    ) -> tuple[AnalysisWriteResult, ...]: ...


@dataclass(frozen=True)
class SonaraBatchTrackResult:
    candidate: AnalysisCandidate
    error: Exception | None = None
    used_ffmpeg_fallback: bool = False

    @property
    def target(self) -> AnalysisTarget:
        return self.candidate.target


@dataclass(frozen=True)
class SonaraBatchMetrics:
    track_count: int
    source_bytes: int
    analyze_seconds: float
    prepare_seconds: float
    store_seconds: float
    copy_seconds: float = 0.0
    staged_track_count: int = 0
    ffmpeg_fallback_count: int = 0


def analysis_outputs_for_sonara_runtime(
    sonara_module: Any | None = None,
) -> tuple[AnalysisOutput, ...]:
    """Return the current SONARA Core and embedding outputs."""

    del sonara_module
    return (
        AnalysisOutput("sonara", "core"),
        AnalysisOutput("sonara", "embedding"),
    )


def analyze_and_store_sonara_batch(
    repository: SonaraAnalysisRepository,
    candidates: Sequence[AnalysisCandidate],
    *,
    sonara_module: Any | None = None,
    progress: Callable[[int, int], None] | None = None,
    metrics: Callable[[SonaraBatchMetrics], None] | None = None,
) -> list[SonaraBatchTrackResult]:
    """Analyze one native batch and persist successful results in input order.

    Analyzer failures, conversion failures, and repository write failures are
    retained per candidate. Fatal initialization or batch cardinality failures
    raise immediately.
    """

    selected_candidates = tuple(candidates)
    if not selected_candidates:
        return []
    if any(
        not isinstance(candidate, AnalysisCandidate)
        for candidate in selected_candidates
    ):
        raise TypeError("candidates must contain only AnalysisCandidate values")

    sonara = sonara_module or _import_sonara()
    active_outputs = analysis_outputs_for_sonara_runtime()
    repository.register_analysis_outputs(active_outputs)

    analyze_started = time.perf_counter()
    raw_results = sonara.analyze_batch(
        [candidate.file_path for candidate in selected_candidates],
        sr=SONARA_SAMPLE_RATE,
        mode=SONARA_ANALYSIS_MODE,
        bpm_min=SONARA_BPM_MIN,
        bpm_max=SONARA_BPM_MAX,
        features=list(sonara_requested_features()),
        vocalness_model=SONARA_VOCALNESS_MODEL_SELECTOR,
        progress=progress,
    )
    analyze_seconds = time.perf_counter() - analyze_started
    if len(raw_results) != len(selected_candidates):
        raise RuntimeError("SONARA batch result count does not match candidate count")

    prepare_started = time.perf_counter()
    prepared: list[SonaraWrite | Exception] = []
    fallback_track_ids: set[int] = set()
    for candidate, raw_result in zip(selected_candidates, raw_results):
        try:
            analysis, used_ffmpeg_fallback = _analysis_mapping_with_ffmpeg_fallback(
                sonara,
                candidate,
                raw_result,
            )
            if used_ffmpeg_fallback:
                fallback_track_ids.add(candidate.target.track_id)
            prepared.append(
                prepare_sonara_write(
                    candidate,
                    analysis,
                    analyzed_at=utc_timestamp(),
                )
            )
        except Exception as error:
            prepared.append(error)
    prepare_seconds = time.perf_counter() - prepare_started

    pending_writes = tuple(item for item in prepared if isinstance(item, SonaraWrite))
    store_started = time.perf_counter()
    write_results = tuple(repository.save_sonara_results(pending_writes))
    store_seconds = time.perf_counter() - store_started
    _validate_write_results(pending_writes, write_results)
    write_results_iter = iter(write_results)

    stored: list[SonaraBatchTrackResult] = []
    for candidate, prepared_result in zip(selected_candidates, prepared):
        if isinstance(prepared_result, Exception):
            stored.append(
                SonaraBatchTrackResult(
                    candidate=candidate,
                    error=prepared_result,
                    used_ffmpeg_fallback=(
                        candidate.target.track_id in fallback_track_ids
                    ),
                )
            )
            continue
        write_result = next(write_results_iter)
        error = (
            None
            if write_result.error is None
            else RuntimeError(f"SONARA storage failure: {write_result.error}")
        )
        stored.append(
            SonaraBatchTrackResult(
                candidate=candidate,
                error=error,
                used_ffmpeg_fallback=(candidate.target.track_id in fallback_track_ids),
            )
        )

    if metrics is not None:
        metrics(
            SonaraBatchMetrics(
                track_count=len(selected_candidates),
                source_bytes=sum(
                    candidate.file_size_bytes for candidate in selected_candidates
                ),
                analyze_seconds=analyze_seconds,
                prepare_seconds=prepare_seconds,
                store_seconds=store_seconds,
            )
        )
    return stored


def _analysis_mapping_with_ffmpeg_fallback(
    sonara: Any,
    candidate: AnalysisCandidate,
    raw_result: object,
    *,
    decode_path: str | None = None,
) -> tuple[dict[str, object], bool]:
    native_error: RuntimeError
    try:
        return _analysis_mapping(raw_result), False
    except RuntimeError as error:
        message = str(error).lower()
        if not (
            message.startswith("sonara decode failure:")
            or "codec" in message
        ):
            raise
        native_error = error

    try:
        audio, source_sample_rate, decode_detail = load_audio_mono_with_ffmpeg(
            decode_path or candidate.file_path
        )
        if source_sample_rate != SONARA_SAMPLE_RATE:
            audio = sonara.resample(
                audio,
                orig_sr=source_sample_rate,
                target_sr=SONARA_SAMPLE_RATE,
            )
        analysis = _analysis_mapping(
            sonara.analyze_signal(
                audio,
                sr=SONARA_SAMPLE_RATE,
                mode=SONARA_ANALYSIS_MODE,
                bpm_min=SONARA_BPM_MIN,
                bpm_max=SONARA_BPM_MAX,
                features=list(sonara_requested_features()),
                vocalness_model=SONARA_VOCALNESS_MODEL_SELECTOR,
            )
        )
    except Exception as fallback_error:
        LOGGER.warning(
            "SONARA native analysis and FFmpeg PCM fallback failed path=%s "
            "native_error=%s fallback_error=%s",
            candidate.file_path,
            native_error,
            fallback_error,
        )
        raise RuntimeError(
            "SONARA native analysis failed and FFmpeg PCM fallback failed: "
            f"native={native_error}; fallback={fallback_error}"
        ) from fallback_error

    LOGGER.warning(
        "SONARA analysis recovered through FFmpeg PCM fallback path=%s "
        "source_sample_rate=%s target_sample_rate=%s pcm_samples=%s "
        "decode_detail=%s native_error=%s",
        candidate.file_path,
        source_sample_rate,
        SONARA_SAMPLE_RATE,
        audio.size,
        decode_detail,
        native_error,
    )
    return analysis, True


def _analysis_mapping(raw_result: object) -> dict[str, object]:
    if bool(getattr(raw_result, "failed", False)):
        try:
            failed = dict(raw_result)
        except (TypeError, ValueError) as error:
            raise RuntimeError("SONARA analysis failure") from error
        kind = str(failed.get("error_kind") or "analysis")
        message = str(failed.get("error") or "unknown error")
        raise RuntimeError(f"SONARA {kind} failure: {message}")
    try:
        analysis = dict(raw_result)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise TypeError("SONARA batch result must be mapping-compatible") from error
    if analysis.get("error") is not None:
        kind = str(analysis.get("error_kind") or "analysis")
        raise RuntimeError(f"SONARA {kind} failure: {analysis.get('error')}")
    return analysis


def _validate_write_results(
    writes: tuple[SonaraWrite, ...],
    results: tuple[AnalysisWriteResult, ...],
) -> None:
    if len(results) != len(writes):
        raise RuntimeError(
            "SONARA repository result count does not match prepared write count"
        )
    for write, result in zip(writes, results):
        if not isinstance(result, AnalysisWriteResult):
            raise TypeError(
                "save_sonara_results must return AnalysisWriteResult values"
            )
        if result.target != write.target:
            raise RuntimeError(
                "SONARA repository returned a result for the wrong target"
            )


def _import_sonara() -> Any:
    try:
        import sonara
    except ImportError as error:
        raise RuntimeError(
            'sonara is not installed. Install it with: python -m pip install -e ".[sonara,dev]"'
        ) from error
    return sonara
