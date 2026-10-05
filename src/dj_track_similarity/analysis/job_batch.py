from __future__ import annotations

from collections import deque
from collections.abc import Callable, Collection, Iterator, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

from ..analysis_models import AnalysisCandidate
from ..audio.loader import DecodedAudio
from ..embedding.audio import resample_decoded


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


@dataclass(frozen=True)
class ModelAudio:
    """One decoded track at each sample rate its models read.

    ``None`` keeps the decode unchanged for a runner that declares no rate.
    """

    by_rate: Mapping[int | None, DecodedAudio]


def model_sample_rate(runner: object) -> int | None:
    """The rate a runner's model reads, or ``None`` when it takes a decode as is."""

    return getattr(runner, "input_sample_rate", None)


def prepare_model_audio(
    decoded: DecodedAudio | object,
    sample_rates: Collection[int | None],
) -> ModelAudio | object:
    """Resample a decode once per rate its models read, off the models' thread."""

    if not isinstance(decoded, DecodedAudio):
        return decoded
    by_rate: dict[int | None, DecodedAudio] = {}
    for rate in sample_rates:
        try:
            by_rate[rate] = decoded if rate is None else resample_decoded(decoded, rate)
        except Exception:
            # Hand the decode over unchanged: the model's own resampling then
            # rejects it with the error it has always reported.
            by_rate[rate] = decoded
    return ModelAudio(by_rate)


def select_model_items(
    items: Sequence[AnalysisBatchItem],
    model: str,
    sample_rate: int | None,
) -> list[AnalysisBatchItem]:
    """One model's items, each carrying its track at the rate that model reads."""

    return [
        replace(item, decoded=item.decoded.by_rate[sample_rate])
        if isinstance(item.decoded, ModelAudio)
        else item
        for item in items
        if model in item.models
    ]


def iter_decoded_batches(
    candidates: Sequence[AnalysisCandidate],
    targets_by_track: Mapping[int, tuple[str, ...]],
    decode_audio: DecodeAudio,
    *,
    sample_rates: Mapping[str, int | None],
    batch_size: int,
    workers: int,
    set_current_path: Callable[[str], None],
    mark_track_processed: Callable[[AnalysisCandidate], None],
) -> Iterator[list[AnalysisBatchItem]]:
    """Yield Direct Mode batches in library order while the next batch decodes.

    A worker pool decodes and resamples up to one batch ahead of the batch being
    handed to the models, so the CPU prepares audio while the models run and at
    most two batches of prepared audio exist at once. Closing the iterator
    cancels work that has not started and waits for running work, so no worker
    outlives the job's use.
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
            future = (
                pool.submit(
                    _decode_for_models,
                    decode_audio,
                    candidate.file_path,
                    {sample_rates.get(model) for model in targets},
                )
                if targets
                else None
            )
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


def _decode_for_models(
    decode_audio: DecodeAudio,
    path: str,
    sample_rates: Collection[int | None],
) -> ModelAudio | object:
    try:
        decoded = decode_audio(path)
    except Exception as error:
        return DecodeFailure(error)
    return prepare_model_audio(decoded, sample_rates)
