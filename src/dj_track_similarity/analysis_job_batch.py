from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .audio_loader import DecodedAudio
from .models import Track


DecodeAudio = Callable[[str | Path], DecodedAudio | object]


@dataclass(frozen=True)
class AnalysisBatchItem:
    track: Track
    decoded: DecodedAudio | object | None
    models: tuple[str, ...]


def decode_analysis_batch(
    batch: Sequence[Track],
    targets_by_track: Mapping[int, tuple[str, ...]],
    decode_audio: DecodeAudio,
    *,
    set_current_path: Callable[[str], None],
    record_decode_failure: Callable[[Track, tuple[str, ...], Exception], None],
    mark_track_processed: Callable[[Track], None],
    should_defer_processed: Callable[[Track], bool] | None = None,
) -> list[AnalysisBatchItem]:
    decoded_items: list[AnalysisBatchItem] = []
    for track in batch:
        targets = targets_by_track.get(track.id, ())
        if not targets:
            if should_defer_processed is None or not should_defer_processed(track):
                mark_track_processed(track)
            continue
        set_current_path(track.path)
        try:
            decoded = decode_audio(track.path)
        except Exception as error:
            record_decode_failure(track, targets, error)
            if should_defer_processed is None or not should_defer_processed(track):
                mark_track_processed(track)
            continue
        decoded_items.append(AnalysisBatchItem(track=track, decoded=decoded, models=targets))
    return decoded_items
