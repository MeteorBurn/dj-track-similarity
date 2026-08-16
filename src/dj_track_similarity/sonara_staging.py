"""Ephemeral SSD staging ownership for SONARA source files."""

from __future__ import annotations

import shutil
import uuid
import os
import time
from collections import deque
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .analysis_models import AnalysisCandidate
from .sonara_runtime import (
    SONARA_ANALYSIS_MODE,
    SONARA_BPM_MAX,
    SONARA_BPM_MIN,
    SONARA_SAMPLE_RATE,
    SONARA_VOCALNESS_MODEL_SELECTOR,
    sonara_requested_features,
)


@dataclass(frozen=True)
class SonaraStagingConfig:
    """Location and bounded-window settings for one SONARA staging run."""

    root: Path
    stage_size: int = 32
    copy_workers: int = 16
    processes: int = 4
    rayon_threads: int = 4
    max_native_batch_size: int = 4

    def __post_init__(self) -> None:
        root = Path(self.root)
        if not str(root):
            raise ValueError("SONARA staging root must not be empty")
        for name, value in (
            ("stage_size", self.stage_size),
            ("copy_workers", self.copy_workers),
            ("processes", self.processes),
            ("rayon_threads", self.rayon_threads),
            ("max_native_batch_size", self.max_native_batch_size),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        object.__setattr__(self, "root", root)


@dataclass(frozen=True)
class StagedSonaraCandidate:
    candidate: AnalysisCandidate
    source_path: Path
    path: Path
    copy_seconds: float = 0.0


@dataclass(frozen=True)
class StagedSonaraResult:
    """One completed staged analysis, keyed by the original candidate."""

    item: StagedSonaraCandidate
    analysis: dict[str, object] | None = None
    error: Exception | None = None
    used_ffmpeg_fallback: bool = False
    copy_seconds: float = 0.0
    analyze_seconds: float = 0.0
    store_seconds: float = 0.0

    @property
    def candidate(self) -> AnalysisCandidate:
        return self.item.candidate

    @property
    def target(self):
        return self.candidate.target


class SonaraStagingSession:
    """Own staged copies for one job and remove them deterministically."""

    def __init__(self, config: SonaraStagingConfig) -> None:
        self.config = config
        self.path = config.root / f"sonara-stage-{uuid.uuid4().hex}"
        self._created = False

    def __enter__(self) -> SonaraStagingSession:
        cleanup_orphaned_sonara_staging(self.config.root)
        self.path.mkdir(parents=True, exist_ok=False)
        (self.path / ".owner").write_text(str(os.getpid()), encoding="ascii")
        self._created = True
        return self

    def __exit__(self, *_: object) -> None:
        self.cleanup()

    def stage(self, candidate: AnalysisCandidate) -> StagedSonaraCandidate:
        if not self._created:
            raise RuntimeError("SONARA staging session is not active")
        source_path = Path(candidate.file_path)
        destination = self.path / f"{candidate.target.track_id}-{source_path.name}"
        started = time.perf_counter()
        try:
            self._copy(source_path, destination)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return StagedSonaraCandidate(
            candidate=candidate,
            source_path=source_path,
            path=destination,
            copy_seconds=time.perf_counter() - started,
        )

    @staticmethod
    def _copy(source_path: Path, destination: Path) -> None:
        shutil.copyfile(source_path, destination)

    def release(self, staged: StagedSonaraCandidate) -> None:
        if not staged.path.is_relative_to(self.path):
            raise ValueError("staged path is not owned by this SONARA session")
        staged.path.unlink(missing_ok=True)

    def cleanup(self) -> None:
        if self._created:
            shutil.rmtree(self.path, ignore_errors=True)
            self._created = False


def cleanup_orphaned_sonara_staging(root: Path) -> None:
    """Remove only job directories whose recorded owner process is gone."""

    if not root.exists():
        return
    for path in root.glob("sonara-stage-*"):
        if not path.is_dir():
            continue
        try:
            owner = int((path / ".owner").read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            try:
                path.rmdir()
            except OSError:
                pass
            continue
        if _process_exists(owner):
            continue
        shutil.rmtree(path, ignore_errors=True)


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def analyze_and_store_staged_sonara(
    repository: Any,
    candidates: Sequence[AnalysisCandidate],
    *,
    config: SonaraStagingConfig,
    analyze_group: Callable[[Sequence[StagedSonaraCandidate]], Iterable[StagedSonaraResult]],
    prepare_write: Callable[[AnalysisCandidate, dict[str, object]], Any],
    store_write: Callable[[Any, Any], Any],
    cancelled: Callable[[], bool] | None = None,
    executor_factory: Callable[[], Any] | None = None,
    result_callback: Callable[[StagedSonaraResult], None] | None = None,
) -> list[StagedSonaraResult]:
    """Run a bounded, barrier-free staged queue and persist completed tracks.

    The caller owns the model worker implementation. This boundary keeps source
    identity in the parent process and releases every staged path after its
    result is handled.
    """

    pending = iter(candidates)
    ready: deque[StagedSonaraCandidate] = deque()
    outcomes: list[StagedSonaraResult] = []
    copy_futures: dict[Future[StagedSonaraCandidate], AnalysisCandidate] = {}
    analysis_futures: dict[Future[tuple[StagedSonaraResult, ...]], tuple[StagedSonaraCandidate, ...]] = {}
    active_limit = config.stage_size

    def complete(result: StagedSonaraResult) -> None:
        outcomes.append(result)
        if result_callback is not None:
            result_callback(result)

    with SonaraStagingSession(config) as session, ThreadPoolExecutor(
        max_workers=config.copy_workers,
        thread_name_prefix="sonara-stage-copy",
    ) as copier, (executor_factory() if executor_factory is not None else ThreadPoolExecutor(max_workers=config.processes)) as analyzer:
        exhausted = False

        def fill_window() -> None:
            nonlocal exhausted
            while not exhausted and (
                len(copy_futures)
                + len(ready)
                + sum(len(group) for group in analysis_futures.values())
                < active_limit
            ):
                try:
                    candidate = next(pending)
                except StopIteration:
                    exhausted = True
                    return
                copy_futures[copier.submit(session.stage, candidate)] = candidate

        fill_window()
        while copy_futures or ready or analysis_futures:
            if cancelled is not None and cancelled():
                raise RuntimeError("SONARA staging cancelled")
            while ready and len(analysis_futures) < config.processes:
                group = tuple(
                    ready.popleft()
                    for _ in range(min(config.max_native_batch_size, len(ready)))
                )
                analysis_futures[analyzer.submit(_run_group, analyze_group, group)] = group

            futures = tuple(copy_futures) + tuple(analysis_futures)
            if not futures:
                continue
            done, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                if future in copy_futures:
                    candidate = copy_futures.pop(future)
                    try:
                        ready.append(future.result())
                    except Exception as error:
                        complete(
                            StagedSonaraResult(
                                item=StagedSonaraCandidate(
                                    candidate=candidate,
                                    source_path=Path(candidate.file_path),
                                    path=session.path / "copy-failed",
                                ),
                                error=error,
                            )
                        )
                    continue
                group = analysis_futures.pop(future)
                try:
                    results = future.result()
                    if len(results) != len(group):
                        raise RuntimeError("SONARA staged worker result count mismatch")
                except Exception as error:
                    results = tuple(StagedSonaraResult(item=item, error=error) for item in group)
                for result in results:
                    store_started = time.perf_counter()
                    try:
                        if result.error is None:
                            if result.analysis is None:
                                raise RuntimeError("SONARA staged worker returned no analysis")
                            write = prepare_write(result.candidate, result.analysis)
                            store_write(repository, write)
                    except Exception as error:
                        result = StagedSonaraResult(
                            item=result.item,
                            error=error,
                            used_ffmpeg_fallback=result.used_ffmpeg_fallback,
                            copy_seconds=result.copy_seconds,
                            analyze_seconds=result.analyze_seconds,
                        )
                    finally:
                        result = replace(
                            result,
                            store_seconds=time.perf_counter() - store_started,
                        )
                        session.release(result.item)
                    complete(result)
            fill_window()
    return outcomes


def _run_group(
    analyze_group: Callable[[Sequence[StagedSonaraCandidate]], Iterable[StagedSonaraResult]],
    group: tuple[StagedSonaraCandidate, ...],
) -> tuple[StagedSonaraResult, ...]:
    return tuple(analyze_group(group))


def sonara_process_executor(config: SonaraStagingConfig) -> ProcessPoolExecutor:
    """Create persistent SONARA workers with the benchmarked Rayon setting."""

    return ProcessPoolExecutor(
        max_workers=config.processes,
        initializer=_initialize_sonara_process,
        initargs=(config.rayon_threads,),
    )


def analyze_staged_sonara_group(
    staged: Sequence[StagedSonaraCandidate],
) -> tuple[StagedSonaraResult, ...]:
    """Analyze one mini-batch inside a persistent child process."""

    from .sonara_features import _analysis_mapping_with_ffmpeg_fallback, _import_sonara

    started = time.perf_counter()
    sonara = _import_sonara()
    raw_results = sonara.analyze_batch(
        [str(item.path) for item in staged],
        sr=SONARA_SAMPLE_RATE,
        mode=SONARA_ANALYSIS_MODE,
        bpm_min=SONARA_BPM_MIN,
        bpm_max=SONARA_BPM_MAX,
        features=list(sonara_requested_features()),
        vocalness_model=SONARA_VOCALNESS_MODEL_SELECTOR,
    )
    if len(raw_results) != len(staged):
        raise RuntimeError("SONARA staged worker result count mismatch")
    elapsed = time.perf_counter() - started
    results: list[StagedSonaraResult] = []
    for item, raw_result in zip(staged, raw_results):
        try:
            analysis, used_ffmpeg_fallback = _analysis_mapping_with_ffmpeg_fallback(
                sonara,
                item.candidate,
                raw_result,
                decode_path=str(item.path),
            )
            results.append(
                StagedSonaraResult(
                    item=item,
                    analysis=analysis,
                    used_ffmpeg_fallback=used_ffmpeg_fallback,
                    copy_seconds=item.copy_seconds,
                    analyze_seconds=elapsed / len(staged),
                )
            )
        except Exception as error:
            results.append(StagedSonaraResult(item=item, error=error, copy_seconds=item.copy_seconds, analyze_seconds=elapsed / len(staged)))
    return tuple(results)


def _initialize_sonara_process(rayon_threads: int) -> None:
    os.environ["RAYON_NUM_THREADS"] = str(rayon_threads)
