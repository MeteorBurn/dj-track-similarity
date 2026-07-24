"""Native SONARA batch orchestration for the typed v7 repository."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from .analysis_contracts import utc_timestamp
from .analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
    AnalysisWriteResult,
    SonaraWrite,
)
from .sonara_contract import (
    SONARA_ANALYSIS_MODE,
    SONARA_BPM_MAX,
    SONARA_BPM_MIN,
    SONARA_SAMPLE_RATE,
    SONARA_VOCALNESS_MODEL_SELECTOR,
    normalize_sonara_outputs,
    sonara_requested_features,
    sonara_runtime_contracts,
)
from .sonara_storage import prepare_sonara_write


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


def analysis_outputs_for_sonara_runtime(
    sonara_module: Any | None = None,
) -> tuple[AnalysisOutput, ...]:
    """Return all four active outputs for the actual loaded SONARA runtime."""

    contracts = sonara_runtime_contracts(sonara_module)
    return tuple(AnalysisOutput(identity) for identity in contracts.identities)


def analyze_and_store_sonara_batch(
    repository: SonaraAnalysisRepository,
    candidates: Sequence[AnalysisCandidate],
    *,
    sonara_module: Any | None = None,
    outputs: Sequence[str] | None = None,
    progress: Callable[[int, int], None] | None = None,
    metrics: Callable[[SonaraBatchMetrics], None] | None = None,
) -> list[SonaraBatchTrackResult]:
    """Analyze one native batch and persist successful results in input order.

    Analyzer failures, conversion failures, and repository write failures are
    retained per candidate.  Fatal runtime identity, initialization, or batch
    cardinality failures raise immediately.
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
    contracts = sonara_runtime_contracts(sonara)
    selected_outputs = normalize_sonara_outputs(outputs)
    active_outputs = tuple(
        AnalysisOutput(identity) for identity in contracts.identities
    )
    repository.register_analysis_outputs(active_outputs)

    analyze_started = time.perf_counter()
    raw_results = sonara.analyze_batch(
        [candidate.file_path for candidate in selected_candidates],
        sr=SONARA_SAMPLE_RATE,
        mode=SONARA_ANALYSIS_MODE,
        bpm_min=SONARA_BPM_MIN,
        bpm_max=SONARA_BPM_MAX,
        features=list(
            sonara_requested_features(
                runtime=contracts.runtime,
            )
        ),
        vocalness_model=SONARA_VOCALNESS_MODEL_SELECTOR,
        progress=progress,
    )
    analyze_seconds = time.perf_counter() - analyze_started
    if len(raw_results) != len(selected_candidates):
        raise RuntimeError("SONARA batch result count does not match candidate count")

    prepare_started = time.perf_counter()
    prepared: list[SonaraWrite | Exception] = []
    for candidate, raw_result in zip(selected_candidates, raw_results):
        try:
            analysis = _analysis_mapping(raw_result)
            prepared.append(
                prepare_sonara_write(
                    candidate,
                    analysis,
                    contracts=contracts,
                    outputs=selected_outputs,
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
                )
            )
            continue
        write_result = next(write_results_iter)
        error = (
            None
            if write_result.error is None
            else RuntimeError(f"SONARA storage failure: {write_result.error}")
        )
        stored.append(SonaraBatchTrackResult(candidate=candidate, error=error))

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
