from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from ..analysis_models import AnalysisCandidate
from ..audio.loader import DecodedAudio


DecodeAudio = Callable[[str | Path], DecodedAudio | object]


@dataclass(frozen=True)
class AnalysisBatchItem:
    candidate: AnalysisCandidate
    decoded: DecodedAudio | object | None
    models: tuple[str, ...]


@dataclass(frozen=True)
class DecodeFailure:
    """A full-track decode error deferred to a model-specific recovery path."""

    error: Exception


def iter_decoded_batches(
    candidates: Sequence[AnalysisCandidate],
    targets_by_track: Mapping[int, tuple[str, ...]],
    decode_audio: DecodeAudio,
    *,
    batch_size: int,
    workers: int,
    set_current_path: Callable[[str], None],
    mark_track_processed: Callable[[AnalysisCandidate], None],
) -> Iterator[list[AnalysisBatchItem]]:
    """Yield Direct Mode batches in library order while the next batch decodes.

    A worker pool decodes up to one batch ahead of the batch being handed to the
    models, so the CPU decodes while the models run and at most two batches of
    decoded audio exist at once. Closing the iterator cancels decodes that have
    not started and waits for running ones, so no worker outlives the job's use.
    """

    size = max(1, batch_size)
    pending = iter(candidates)
    queued: deque[tuple[AnalysisCandidate, tuple[str, ...], Future[object] | None]] = deque()
    pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="ml-direct-decode")

    def refill() -> None:
        while len(queued) < size:
            candidate = next(pending, None)
            if candidate is None:
                return
            targets = targets_by_track.get(candidate.target.track_id, ())
            future = pool.submit(_decode_or_defer, decode_audio, candidate.file_path) if targets else None
            queued.append((candidate, targets, future))

    try:
        refill()
        while queued:
            items: list[AnalysisBatchItem] = []
            for _ in range(min(size, len(queued))):
                candidate, targets, future = queued.popleft()
                # Each consumed track frees a slot for the next batch's decode.
                refill()
                if future is None:
                    mark_track_processed(candidate)
                    continue
                set_current_path(candidate.file_path)
                items.append(
                    AnalysisBatchItem(candidate=candidate, decoded=future.result(), models=targets)
                )
            yield items
    finally:
        queued.clear()
        pool.shutdown(wait=True, cancel_futures=True)


def _decode_or_defer(decode_audio: DecodeAudio, path: str) -> DecodedAudio | object:
    try:
        return decode_audio(path)
    except Exception as error:
        return DecodeFailure(error)
