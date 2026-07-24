from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .analysis_models import AnalysisCandidate
from .audio_loader import DecodedAudio


DecodeAudio = Callable[[str | Path], DecodedAudio | object]


@dataclass(frozen=True)
class AnalysisBatchItem:
    candidate: AnalysisCandidate
    decoded: DecodedAudio | object | None
    models: tuple[str, ...]


def decode_analysis_batch(
    batch: Sequence[AnalysisCandidate],
    targets_by_track: Mapping[int, tuple[str, ...]],
    decode_audio: DecodeAudio,
    *,
    set_current_path: Callable[[str], None],
    record_decode_failure: Callable[
        [AnalysisCandidate, tuple[str, ...], Exception],
        None,
    ],
    mark_track_processed: Callable[[AnalysisCandidate], None],
) -> list[AnalysisBatchItem]:
    decoded_items: list[AnalysisBatchItem] = []
    for candidate in batch:
        track_id = candidate.target.track_id
        targets = targets_by_track.get(track_id, ())
        if not targets:
            mark_track_processed(candidate)
            continue
        set_current_path(candidate.file_path)
        try:
            decoded = decode_audio(candidate.file_path)
        except Exception as error:
            record_decode_failure(candidate, targets, error)
            mark_track_processed(candidate)
            continue
        decoded_items.append(
            AnalysisBatchItem(
                candidate=candidate,
                decoded=decoded,
                models=targets,
            )
        )
    return decoded_items
