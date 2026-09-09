from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np

from .fingerprints import (
    FingerprintSketch,
    fingerprint_candidate_pairs,
)

from . import models as models_module
from . import values as values_module




def _candidate_pair_sources(
    tracks: list[models_module.TrackRecord],
    config: models_module.PresetConfig,
    source_config: models_module.SourceConfig,
    *,
    fingerprint_sketches: Iterable[FingerprintSketch] = (),
    fingerprint_only: bool = False,
) -> dict[tuple[int, int], tuple[str, ...]]:
    sources_by_pair: dict[tuple[int, int], set[str]] = {}
    if not fingerprint_only:
        signature_sources = _signature_candidate_pair_sources(
            tracks,
            config,
            source_config,
        )
        for pair, sources in signature_sources.items():
            sources_by_pair.setdefault(pair, set()).update(sources)
        if not signature_sources:
            for pair in _duration_window_candidate_pairs(tracks, config):
                sources_by_pair.setdefault(pair, set()).add("duration_window")
    for pair in fingerprint_candidate_pairs(list(fingerprint_sketches)):
        sources_by_pair.setdefault(pair, set()).add("fingerprint_lsh")
    return {
        pair: tuple(sorted(sources))
        for pair, sources in sources_by_pair.items()
    }


def _fingerprint_exact_candidate_pairs(
    candidate_sources: Mapping[tuple[int, int], tuple[str, ...]],
) -> set[tuple[int, int]]:
    return {
        pair
        for pair, sources_for_pair in candidate_sources.items()
        if "fingerprint_lsh" in sources_for_pair
        or any(source in {"mert_lsh", "maest_lsh"} for source in sources_for_pair)
    }


def _duration_window_candidate_pairs(tracks: list[models_module.TrackRecord], config: models_module.PresetConfig) -> list[tuple[int, int]]:
    sortable = [track for track in tracks if track.duration is not None and track.duration > 0]
    missing_duration = [track for track in tracks if track.duration is None or track.duration <= 0]
    sortable.sort(key=lambda track: (float(track.duration or 0.0), track.track_id))
    pairs: set[tuple[int, int]] = set()
    end = 0
    for start, left in enumerate(sortable):
        if end < start + 1:
            end = start + 1
        tolerance = max(config.duration_seconds, float(left.duration or 0.0) * config.duration_ratio)
        while end < len(sortable) and float(sortable[end].duration or 0.0) - float(left.duration or 0.0) <= tolerance:
            end += 1
        for right in sortable[start + 1 : end]:
            pairs.add(_ordered_pair(left.track_id, right.track_id))
    if len(missing_duration) <= 200:
        for index, left in enumerate(missing_duration):
            for right in missing_duration[index + 1 :]:
                pairs.add(_ordered_pair(left.track_id, right.track_id))
    return sorted(pairs)


def _signature_candidate_pairs(
    tracks: list[models_module.TrackRecord],
    config: models_module.PresetConfig,
    source_config: models_module.SourceConfig,
) -> set[tuple[int, int]]:
    return set(_signature_candidate_pair_sources(tracks, config, source_config))


def _signature_candidate_pair_sources(
    tracks: list[models_module.TrackRecord],
    config: models_module.PresetConfig,
    source_config: models_module.SourceConfig,
) -> dict[tuple[int, int], set[str]]:
    sources_by_pair: dict[tuple[int, int], set[str]] = {}
    for embedding_key in ("mert", "maest"):
        if embedding_key not in source_config.sources:
            continue
        embedding_tracks = [track for track in tracks if embedding_key in track.embeddings]
        if not embedding_tracks:
            continue
        dim = min(int(track.embeddings[embedding_key].shape[0]) for track in embedding_tracks)
        if dim < 96:
            continue
        projection_count = 96
        rng = np.random.default_rng(_projection_seed(embedding_key, dim))
        projection = rng.standard_normal((dim, projection_count), dtype=np.float32)
        matrix = np.vstack([track.embeddings[embedding_key][:dim] for track in embedding_tracks]).astype(np.float32)
        matrix = matrix - matrix.mean(axis=0, keepdims=True)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms
        signatures = (matrix @ projection) >= 0
        buckets: dict[tuple[int, int], list[int]] = {}
        for row_index, track in enumerate(embedding_tracks):
            for band_index in range(8):
                start = band_index * 12
                value = _bits_to_int(signatures[row_index, start : start + 12])
                buckets.setdefault((band_index, value), []).append(track.track_id)
        by_id = {track.track_id: track for track in embedding_tracks}
        for ids in buckets.values():
            if len(ids) < 2:
                continue
            for pair in _duration_window_candidate_pairs(
                [by_id[track_id] for track_id in ids],
                config,
            ):
                sources_by_pair.setdefault(pair, set()).add(f"{embedding_key}_lsh")
    return sources_by_pair


def _candidate_duration_compatible(left: models_module.TrackRecord, right: models_module.TrackRecord, config: models_module.PresetConfig) -> bool:
    diff, ratio = values_module._duration_distance(left, right)
    if diff is None or ratio is None:
        return True
    shorter = min(float(left.duration or 0.0), float(right.duration or 0.0))
    return diff <= max(config.duration_seconds, shorter * config.duration_ratio)


def _ordered_pair(left_id: int, right_id: int) -> tuple[int, int]:
    return (left_id, right_id) if left_id < right_id else (right_id, left_id)


def _bits_to_int(bits: np.ndarray) -> int:
    value = 0
    for bit in bits.tolist():
        value = (value << 1) | int(bool(bit))
    return value


def _projection_seed(embedding_key: str, dim: int) -> int:
    base = 17_311 if embedding_key == "mert" else 29_327
    return base + int(dim)
