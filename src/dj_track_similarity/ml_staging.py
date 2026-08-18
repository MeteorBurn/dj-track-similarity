"""Ephemeral SSD staging for ML model analysis with parallel decode pipeline."""

from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .analysis_job_batch import AnalysisBatchItem, DecodeFailure
from .analysis_models import AnalysisCandidate
from .audio_loader import DecodedAudio, load_decoded_audio, load_decoded_audio_with_ffmpeg


LOGGER = logging.getLogger(__name__)
_DEFERRED_STAGING_CLEANUP_WINERRORS = frozenset({32, 64})


@dataclass(frozen=True)
class MLStagingConfig:
    """Location and bounded-window settings for ML staged analysis.

    KEY DIFFERENCES FROM SONARA:
    1. copy_workers: Optimized for HDD sequential reads (not process count)
    2. decode_workers: Parallel TorchCodec decoders (GPU bottleneck relief)
    3. No rayon_threads: ML models use torch/CUDA parallelism
    4. No max_native_batch_size: Each model has its own inference_batch_size
    5. preflight_copy: Copy during model loading (ML-specific optimization)
    """

    root: Path
    stage_size: int = 64  # Higher than SONARA (16) - we have more VRAM
    copy_workers: int = 4  # HDD sequential optimization (lower than SONARA's 8)
    decode_workers: int = 8  # NEW: Parallel TorchCodec decoders
    inference_batch_size: int = 16  # Per-model GPU batch size

    # ML-specific: preflight overlap optimization
    preflight_copy_enabled: bool = True
    preflight_copy_count: int = 64  # Copy this many during model loading

    def __post_init__(self) -> None:
        root = Path(self.root)
        if not str(root):
            raise ValueError("ML staging root must not be empty")
        for name, value in (
            ("stage_size", self.stage_size),
            ("copy_workers", self.copy_workers),
            ("decode_workers", self.decode_workers),
            ("inference_batch_size", self.inference_batch_size),
            ("preflight_copy_count", self.preflight_copy_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        object.__setattr__(self, "root", root)


@dataclass(frozen=True)
class MLStagedCandidate:
    """A candidate with its staged copy location.

    DIFFERENCE FROM SONARA: No decode yet - decode happens in separate phase.
    """
    candidate: AnalysisCandidate
    source_path: Path
    staged_path: Path
    copy_seconds: float = 0.0


@dataclass(frozen=True)
class MLStagedResult:
    """One completed ML staged analysis result.

    KEY DIFFERENCES FROM SONARA:
    1. Per-model timing breakdown (not single analyze_seconds)
    2. Shared decode across models (decode_seconds separate)
    3. Multiple model results in single structure
    """

    candidate: AnalysisCandidate
    decoded: DecodedAudio | DecodeFailure | None = None
    error: Exception | None = None

    # Timing breakdown (more granular than SONARA)
    copy_seconds: float = 0.0
    decode_seconds: float = 0.0
    inference_seconds: float = 0.0  # Sum across all models
    store_seconds: float = 0.0

    # Per-model timing for metrics
    model_timings: dict[str, float] = field(default_factory=dict)

    # Recovery tracking
    used_ffmpeg_fallback: bool = False

    @property
    def target(self):
        return self.candidate.target


class MLStagingSession:
    """Manage staged copies for one ML analysis job.

    DIFFERENCES FROM SONARA:
    1. No ProcessPool integration (models run in main process)
    2. Decode tracking separate from copy tracking
    3. Preflight copy support for model loading overlap
    """

    def __init__(self, config: MLStagingConfig) -> None:
        self.config = config
        self.path = config.root / f"ml-stage-{uuid.uuid4().hex}"
        self._created = False

    def __enter__(self) -> MLStagingSession:
        cleanup_orphaned_ml_staging(self.config.root)
        self.path.mkdir(parents=True, exist_ok=False)
        (self.path / ".owner").write_text(str(os.getpid()), encoding="ascii")
        self._created = True
        LOGGER.info("ML staging session created: %s", self.path)
        return self

    def __exit__(self, *_: object) -> None:
        self.cleanup()

    def stage_file(self, candidate: AnalysisCandidate) -> MLStagedCandidate:
        """Copy source file to staging directory.

        OPTIMIZATION: Uses same copy strategy as SONARA (pre-allocation, large buffers).
        """
        if not self._created:
            raise RuntimeError("ML staging session is not active")
        source_path = Path(candidate.file_path)
        destination = self.path / f"{candidate.target.track_id}-{source_path.name}"
        started = time.perf_counter()
        try:
            self._copy(source_path, destination)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        return MLStagedCandidate(
            candidate=candidate,
            source_path=source_path,
            staged_path=destination,
            copy_seconds=time.perf_counter() - started,
        )

    @staticmethod
    def _copy(source_path: Path, destination: Path) -> None:
        """Optimized file copy - identical to SONARA strategy."""
        stat = source_path.stat()
        buffer_size = 1024 * 1024  # 1MB chunks for HDD sequential read

        # Pre-allocate destination (reduce fragmentation)
        with open(destination, 'wb') as dst:
            try:
                dst.truncate(stat.st_size)
            except (OSError, IOError):
                pass

        # Buffered copy with large chunks
        with open(source_path, 'rb', buffering=buffer_size) as src, \
             open(destination, 'r+b', buffering=buffer_size) as dst:
            while True:
                chunk = src.read(buffer_size)
                if not chunk:
                    break
                dst.write(chunk)

    def release(self, staged: MLStagedCandidate) -> None:
        """Delete staged copy after processing."""
        if not staged.staged_path.is_relative_to(self.path):
            raise ValueError("staged path is not owned by this ML session")
        try:
            staged.staged_path.unlink(missing_ok=True)
        except OSError as error:
            if getattr(error, "winerror", None) not in _DEFERRED_STAGING_CLEANUP_WINERRORS:
                raise
            LOGGER.warning(
                "ML staged copy cleanup deferred path=%s error=%s",
                staged.staged_path,
                error,
            )

    def cleanup(self) -> None:
        """Remove staging directory."""
        if self._created:
            try:
                shutil.rmtree(self.path, ignore_errors=True)
                LOGGER.info("ML staging session cleaned up: %s", self.path)
            except Exception as error:
                LOGGER.warning("ML staging cleanup error: %s", error)
            self._created = False


def cleanup_orphaned_ml_staging(root: Path) -> None:
    """Remove ML staging directories whose owner process is gone."""
    if not root.exists():
        return
    for path in root.glob("ml-stage-*"):
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
        LOGGER.info("Removing orphaned ML staging directory: %s (owner PID %d)", path, owner)
        shutil.rmtree(path, ignore_errors=True)


def _process_exists(pid: int) -> bool:
    """Check if process is running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def analyze_and_store_staged_ml(
    repository: Any,
    candidates: Sequence[AnalysisCandidate],
    model_runners: Mapping[str, Any],
    targets_by_track: Mapping[int, tuple[str, ...]],
    *,
    config: MLStagingConfig,
    decode_audio: Callable[[Path], DecodedAudio],
    cancelled: Callable[[], bool] | None = None,
    track_result_callback: Callable[[MLStagedResult], None] | None = None,
    progress_callback: Callable[[str, int, int], None] | None = None,
    set_current_path: Callable[[str], None] | None = None,
    mark_track_processed: Callable[[AnalysisCandidate], None] | None = None,
) -> list[MLStagedResult]:
    """Run bounded ML staged pipeline with copy → decode → inference phases.

    KEY ARCHITECTURE DIFFERENCES FROM SONARA:

    1. THREE-PHASE PIPELINE (vs SONARA's two-phase):
       - Copy: HDD → SSD staging (sequential, HDD-optimized)
       - Decode: SSD → VRAM tensors (parallel TorchCodec)
       - Inference: VRAM → models → results (GPU batched)

    2. SHARED DECODE ACROSS MODELS:
       - SONARA: Each process decodes independently
       - ML: Decode once, all 5 models use same DecodedAudio

    3. NO PROCESS POOL:
       - SONARA: ProcessPool for native library
       - ML: Models live in main process (torch/CUDA)

    4. PER-MODEL BATCHING:
       - Each model takes inference_batch_size from ready_decoded
       - Models run sequentially (same GPU)

    5. MEMORY MANAGEMENT:
       - Release DecodedAudio after ALL models finish
       - Delete staged file after track complete

    6. INTEGRATION WITH EXISTING RUNNERS:
       - Runners expect AnalysisBatchItem with decoded field
       - We build items and call runner.analyze_batch() directly
       - No custom prepare/store - runners handle everything

    Pipeline flow:
    ```
    Copy Pool (4 workers)     → staged_ready queue
    Decode Pool (8 workers)   → ready_decoded queue
    Model Inference (sequential, calls runner.analyze_batch) → results
    ```
    """

    pending = iter(candidates)
    staged_ready: deque[MLStagedCandidate] = deque()  # Copied, waiting decode
    ready_decoded: deque[tuple[MLStagedCandidate, DecodedAudio | DecodeFailure, float]] = deque()  # Decoded, waiting inference
    outcomes: list[MLStagedResult] = []

    copy_futures: dict[Future[MLStagedCandidate], AnalysisCandidate] = {}
    decode_futures: dict[Future[tuple[MLStagedCandidate, DecodedAudio | DecodeFailure, float]], MLStagedCandidate] = {}

    active_limit = config.stage_size
    exhausted = False

    def complete(result: MLStagedResult) -> None:
        """Record completed result."""
        outcomes.append(result)
        if track_result_callback is not None:
            track_result_callback(result)

    def fill_copy_window() -> None:
        """Fill copy window up to stage_size."""
        nonlocal exhausted
        while not exhausted and (
            len(copy_futures)
            + len(staged_ready)
            + len(decode_futures)
            + len(ready_decoded)
            < active_limit
        ):
            try:
                candidate = next(pending)
            except StopIteration:
                exhausted = True
                return
            copy_futures[copier.submit(session.stage_file, candidate)] = candidate
            if progress_callback:
                progress_callback("copy_queued", len(copy_futures), len(candidates))

    with MLStagingSession(config) as session, \
         ThreadPoolExecutor(
             max_workers=config.copy_workers,
             thread_name_prefix="ml-stage-copy"
         ) as copier, \
         ThreadPoolExecutor(
             max_workers=config.decode_workers,
             thread_name_prefix="ml-stage-decode"
         ) as decoder:

        fill_copy_window()

        while (
            not exhausted
            or copy_futures
            or staged_ready
            or decode_futures
            or ready_decoded
        ):
            if cancelled is not None and cancelled():
                raise RuntimeError("ML staging cancelled")

            # Start decode jobs from staged_ready
            while staged_ready and len(decode_futures) < config.decode_workers:
                staged = staged_ready.popleft()
                decode_futures[decoder.submit(_decode_staged, staged, decode_audio)] = staged

            # Wait for any copy or decode to complete
            all_futures = tuple(copy_futures) + tuple(decode_futures)
            if not all_futures:
                # No pending I/O, process ready_decoded batch
                if ready_decoded:
                    batch_size = min(config.inference_batch_size, len(ready_decoded))
                    batch = [ready_decoded.popleft() for _ in range(batch_size)]
                    _process_inference_batch(
                        batch,
                        model_runners,
                        targets_by_track,
                        repository,
                        session,
                        complete,
                        progress_callback,
                        mark_track_processed,
                    )
                fill_copy_window()
                continue

            done, _ = wait(all_futures, return_when=FIRST_COMPLETED, timeout=0.1)

            for future in done:
                if future in copy_futures:
                    # Copy completed
                    candidate = copy_futures.pop(future)
                    try:
                        staged = future.result()
                        staged_ready.append(staged)
                        if progress_callback:
                            progress_callback("copy", len(outcomes), len(candidates))
                    except Exception as error:
                        # Copy failed - record error immediately
                        complete(MLStagedResult(
                            candidate=candidate,
                            error=error,
                        ))
                elif future in decode_futures:
                    # Decode completed
                    staged = decode_futures.pop(future)
                    try:
                        staged, decoded, decode_seconds = future.result()
                        ready_decoded.append((staged, decoded, decode_seconds))
                        if progress_callback:
                            progress_callback("decode", len(ready_decoded), len(candidates))
                    except Exception as error:
                        # Decode failed - record error immediately
                        session.release(staged)
                        complete(MLStagedResult(
                            candidate=staged.candidate,
                            error=error,
                            copy_seconds=staged.copy_seconds,
                        ))

            fill_copy_window()

        # Process remaining decoded tracks
        while ready_decoded:
            batch_size = min(config.inference_batch_size, len(ready_decoded))
            batch = [ready_decoded.popleft() for _ in range(batch_size)]
            _process_inference_batch(
                batch,
                model_runners,
                targets_by_track,
                repository,
                session,
                complete,
                progress_callback,
                mark_track_processed,
            )

    return outcomes


def _decode_staged(
    staged: MLStagedCandidate,
    decode_audio: Callable[[Path], DecodedAudio],
) -> tuple[MLStagedCandidate, DecodedAudio | DecodeFailure, float]:
    """Decode audio from staged path with fallback chain.

    OPTIMIZATION: Reads from SSD staging (fast random access).

    Fallback chain (same as direct mode):
    1. TorchCodec AudioDecoder (primary, uses internal FFmpeg libraries)
    2. Shared FFmpeg via PyAV (fallback, uses project-pinned FFmpeg 8.1.1 + PyAV)
       - load_decoded_audio_with_ffmpeg → load_tolerant_mono_audio
       - Tolerant decode: discards corrupt packets, returns valid frames
    3. DecodeFailure if both fail

    NOTE: The decode_audio callback handles TorchCodec.
    We add shared FFmpeg/PyAV fallback here.
    """
    started = time.perf_counter()

    # Try primary decoder (TorchCodec via callback)
    try:
        decoded = decode_audio(staged.staged_path)
        return staged, decoded, time.perf_counter() - started
    except Exception as primary_error:
        # Try shared FFmpeg fallback
        try:
            decoded = load_decoded_audio_with_ffmpeg(staged.staged_path)
            LOGGER.debug(
                "ML staged: TorchCodec failed, FFmpeg fallback succeeded for %s",
                staged.candidate.file_path,
            )
            return staged, decoded, time.perf_counter() - started
        except Exception as ffmpeg_error:
            # Both failed - return DecodeFailure
            combined_error = RuntimeError(
                f"TorchCodec decode failed: {primary_error}; "
                f"FFmpeg fallback failed: {ffmpeg_error}"
            )
            LOGGER.warning(
                "ML staged: All decode attempts failed for %s: %s",
                staged.candidate.file_path,
                combined_error,
            )
            return staged, DecodeFailure(combined_error), time.perf_counter() - started


def _process_inference_batch(
    batch: list[tuple[MLStagedCandidate, DecodedAudio | DecodeFailure, float]],
    model_runners: Mapping[str, Any],
    targets_by_track: Mapping[int, tuple[str, ...]],
    repository: Any,
    session: MLStagingSession,
    complete: Callable[[MLStagedResult], None],
    progress_callback: Callable[[str, int, int], None] | None,
    mark_track_processed: Callable[[AnalysisCandidate], None] | None,
) -> None:
    """Process inference batch through all models.

    KEY DIFFERENCES FROM SONARA AND DIRECT MODE:
    - Multiple models run sequentially on same batch
    - Each model gets AnalysisBatchItem with shared DecodedAudio
    - DecodeFailure items already tried FFmpeg in _decode_staged
    - Runners handle their own FFmpeg fallback internally (for consistency)
    - Track result only completed after ALL models finish
    - Runners handle their own storage (no custom prepare/store)

    NOTE: DecodeFailure in ML staged means BOTH TorchCodec AND shared FFmpeg
    failed during decode phase. Runners may still attempt their own FFmpeg
    fallback for consistency with direct mode behavior.
    """

    # Build AnalysisBatchItem for each track
    items = []
    decode_timings = {}
    ffmpeg_used_in_decode = {}

    for staged, decoded, decode_seconds in batch:
        track_id = staged.candidate.target.track_id
        models = targets_by_track.get(track_id, ())
        decode_timings[track_id] = decode_seconds

        # Track if FFmpeg was used during decode phase
        # DecodeFailure means both TorchCodec AND FFmpeg failed
        ffmpeg_used_in_decode[track_id] = False  # Will be updated by runner fallback

        items.append(AnalysisBatchItem(
            candidate=staged.candidate,
            decoded=decoded,
            models=models,
        ))

    # Track model timing per track
    model_timings: dict[int, dict[str, float]] = {
        item.candidate.target.track_id: {} for item in items
    }
    model_errors: dict[int, Exception | None] = {
        item.candidate.target.track_id: None for item in items
    }

    # Run each model sequentially (they share GPU)
    from .analysis_config import ANALYSIS_MODEL_ORDER

    for model_name in ANALYSIS_MODEL_ORDER:
        runner = model_runners.get(model_name)
        if not runner:
            continue

        model_items = [item for item in items if model_name in item.models]
        if not model_items:
            continue

        started = time.perf_counter()
        try:
            # Runners handle their own analyze_batch + storage
            # They may do internal FFmpeg fallback for DecodeFailure items
            errors = runner.analyze_batch(repository, model_items)
            elapsed = time.perf_counter() - started

            # Record timing and check for errors
            for item, error in zip(model_items, errors):
                track_id = item.candidate.target.track_id
                model_timings[track_id][model_name] = elapsed / len(model_items)
                if error and model_errors[track_id] is None:
                    model_errors[track_id] = error

            # Check if runner used FFmpeg fallback (from runner.last_ffmpeg_fallback_track_ids)
            if hasattr(runner, 'last_ffmpeg_fallback_track_ids'):
                for track_id in runner.last_ffmpeg_fallback_track_ids:
                    if track_id in ffmpeg_used_in_decode:
                        ffmpeg_used_in_decode[track_id] = True

            if progress_callback:
                progress_callback(f"inference:{model_name}", len(model_items), len(items))
        except Exception as error:
            LOGGER.exception("Model %s batch inference failed", model_name)
            for item in model_items:
                track_id = item.candidate.target.track_id
                if model_errors[track_id] is None:
                    model_errors[track_id] = error

    # Complete each track and mark as processed
    for staged, decoded, decode_seconds in batch:
        track_id = staged.candidate.target.track_id

        result = MLStagedResult(
            candidate=staged.candidate,
            decoded=decoded if not isinstance(decoded, DecodeFailure) else None,
            error=model_errors.get(track_id),
            copy_seconds=staged.copy_seconds,
            decode_seconds=decode_seconds,
            inference_seconds=sum(model_timings.get(track_id, {}).values()),
            model_timings=model_timings.get(track_id, {}),
            # FFmpeg fallback used if either decode phase or runner used it
            used_ffmpeg_fallback=ffmpeg_used_in_decode.get(track_id, False),
        )

        # Release staged copy
        session.release(staged)

        # Mark track as processed
        if mark_track_processed:
            mark_track_processed(staged.candidate)

        # Complete result
        complete(result)
