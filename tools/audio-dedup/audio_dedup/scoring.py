from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np

from . import candidates as candidates_module
from . import config as config_module
from . import models as models_module
from . import progress as progress_module
from . import values as values_module

SONARA_FIELDS = (
    "bpm",
    "danceability",
    "energy",
    "valence",
    "acousticness",
    "spectral_centroid_mean",
    "onset_density",
    "dynamic_range_db",
    "loudness_lufs",
)


def find_duplicate_groups(
    tracks: list[models_module.TrackRecord],
    config: models_module.PresetConfig,
    *,
    limit_groups: int | None,
    source_config: models_module.SourceConfig | None = None,
    candidate_sources: Mapping[tuple[int, int], tuple[str, ...]] | None = None,
    fingerprint_scores: Mapping[tuple[int, int], float] | None = None,
    progress_callback: models_module.ProgressCallback | None = None,
    should_cancel: models_module.CancelCheck | None = None,
) -> list[models_module.DuplicateGroup]:
    selected_sources = source_config or config_module.resolve_source_config()
    if len(tracks) < 2:
        progress_module._report_progress(progress_callback, 1, 1, "Not enough scoped tracks")
        return []
    by_id = {track.track_id: track for track in tracks}
    progress_module._report_progress(progress_callback, 0, 0, "Building candidate pairs")
    selected_candidate_sources = dict(
        candidate_sources
        if candidate_sources is not None
        else candidates_module._candidate_pair_sources(tracks, config, selected_sources)
    )
    pair_total = len(selected_candidate_sources)
    if pair_total == 0:
        progress_module._report_progress(progress_callback, 1, 1, "No candidate pairs")
        return []
    edges: list[models_module.PairEvidence] = []
    selected_fingerprint_scores = fingerprint_scores or {}
    for index, ((left_id, right_id), sources_for_pair) in enumerate(
        sorted(selected_candidate_sources.items()),
        start=1,
    ):
        progress_module._raise_if_cancelled(should_cancel)
        left = by_id[left_id]
        right = by_id[right_id]
        fingerprint_similarity = selected_fingerprint_scores.get((left_id, right_id))
        if (
            "fingerprint_lsh" not in sources_for_pair
            and not candidates_module._candidate_duration_compatible(left, right, config)
        ):
            if index == pair_total or index % 50 == 0:
                progress_module._report_progress(progress_callback, index, pair_total, "Searching duplicate pairs")
            continue
        evidence = score_pair(
            left,
            right,
            config,
            source_config=selected_sources,
            fingerprint_similarity=fingerprint_similarity,
            candidate_sources=sources_for_pair,
        )
        conventional_match = (
            candidates_module._candidate_duration_compatible(left, right, config)
            and evidence.score >= config.min_score
            and _passes_content_similarity(evidence, config)
        )
        fingerprint_match = (
            fingerprint_similarity is not None
            and fingerprint_similarity >= config_module.FINGERPRINT_REVIEW_MIN_SIMILARITY
        )
        if conventional_match or fingerprint_match:
            edges.append(evidence)
        if index == pair_total or index % 50 == 0:
            progress_module._report_progress(progress_callback, index, pair_total, "Searching duplicate pairs")
    grouped_edges = _connected_components(edges)
    groups: list[models_module.DuplicateGroup] = []
    for edge_group in grouped_edges:
        track_ids = tuple(sorted({edge.left_id for edge in edge_group} | {edge.right_id for edge in edge_group}))
        if len(track_ids) < 2 or not all(track_id in by_id for track_id in track_ids):
            continue
        groups.append(models_module.DuplicateGroup(len(groups) + 1, track_ids, tuple(sorted(edge_group, key=lambda item: (-item.score, item.left_id, item.right_id)))))
        if limit_groups is not None and len(groups) >= max(0, limit_groups):
            break
    return groups


def score_pair(
    left: models_module.TrackRecord,
    right: models_module.TrackRecord,
    config: models_module.PresetConfig,
    *,
    source_config: models_module.SourceConfig | None = None,
    fingerprint_similarity: float | None = None,
    candidate_sources: Iterable[str] = (),
) -> models_module.PairEvidence:
    selected_sources = source_config or config_module.resolve_source_config()
    similarities = {
        source: (
            _embedding_similarity(left, right, source)
            if source in selected_sources.sources
            else None
        )
        for source in config_module.SUPPORTED_EMBEDDINGS
    }
    mert = similarities["mert"]
    maest = similarities["maest"]
    muq = similarities["muq"]
    clap = similarities["clap"]
    content_similarity = _content_similarity(
        similarities,
        selected_sources,
    )
    sonara = _sonara_similarity(left, right)
    duration_diff, duration_ratio = values_module._duration_distance(left, right)
    blocked: list[str] = []
    weighted = 0.0
    total = 0.0
    for source in ("mert", "maest"):
        if source not in selected_sources.sources:
            continue
        value = similarities[source]
        if value is None:
            continue
        weight = selected_sources.weights[source]
        weighted += value * weight
        total += weight
    if sonara is not None:
        weighted += sonara * 0.14
        total += 0.14
    for source in ("muq", "clap"):
        if source not in selected_sources.sources:
            continue
        value = similarities[source]
        if value is None:
            continue
        weight = selected_sources.weights[source]
        weighted += value * weight
        total += weight
    if duration_ratio is not None:
        duration_score = max(0.0, 1.0 - min(duration_ratio / max(config.duration_ratio, 0.0001), 1.0))
        weighted += duration_score * 0.05
        total += 0.05
        if duration_diff is not None and duration_diff > max(config.duration_seconds, (min(left.duration or 0, right.duration or 0) * config.duration_ratio)):
            blocked.append("duration mismatch")
    else:
        blocked.append("missing duration")
    for required_source in config_module.DELETE_SAFETY_EMBEDDINGS:
        if required_source not in selected_sources.sources:
            blocked.append(f"{required_source.upper()} source disabled")
            continue
        required_similarity = similarities[required_source]
        if required_similarity is None:
            blocked.append(
                f"missing {required_source.upper()} embedding"
            )
    if not config_module._uses_legacy_delete_safety_config(selected_sources):
        corroboration_weighted = 0.0
        corroboration_total = 0.0
        corroboration_available = True
        for required_source in config_module.DELETE_SAFETY_EMBEDDINGS:
            if required_source not in selected_sources.sources:
                corroboration_available = False
                continue
            required_weight = selected_sources.weights[required_source]
            if required_weight <= 0:
                blocked.append(
                    f"{required_source.upper()} weight is not positive"
                )
                corroboration_available = False
                continue
            required_similarity = similarities[required_source]
            if required_similarity is None:
                corroboration_available = False
                continue
            corroboration_weighted += (
                required_similarity * required_weight
            )
            corroboration_total += required_weight
        if corroboration_available and corroboration_total > 0:
            corroboration = max(
                0.0,
                min(
                    1.0,
                    corroboration_weighted / corroboration_total,
                ),
            )
            if corroboration < config.min_similarity:
                blocked.append(
                    "MERT+MAEST corroboration below delete safety "
                    f"threshold ({corroboration:.6f} < "
                    f"{config.min_similarity:.6f})"
                )
    if content_similarity is None:
        blocked.append("missing content similarity")
    elif content_similarity < config.min_similarity:
        blocked.append("content similarity below threshold")
    score = (weighted / total) if total else 0.0
    return models_module.PairEvidence(
        left_id=left.track_id,
        right_id=right.track_id,
        score=max(0.0, min(1.0, score)),
        content_similarity=content_similarity,
        mert_similarity=mert,
        maest_similarity=maest,
        muq_similarity=muq,
        clap_similarity=clap,
        sonara_similarity=sonara,
        duration_diff_seconds=duration_diff,
        duration_diff_ratio=duration_ratio,
        blocked_reasons=tuple(blocked),
        fingerprint_similarity=fingerprint_similarity,
        candidate_sources=tuple(sorted(set(candidate_sources))),
    )


def _embedding_similarity(left: models_module.TrackRecord, right: models_module.TrackRecord, key: str) -> float | None:
    left_vector = left.embeddings.get(key)
    right_vector = right.embeddings.get(key)
    if left_vector is None or right_vector is None or left_vector.shape != right_vector.shape:
        return None
    return max(-1.0, min(1.0, float(left_vector @ right_vector)))


def _content_similarity(
    similarities: Mapping[str, float | None],
    source_config: models_module.SourceConfig,
) -> float | None:
    weighted = 0.0
    total = 0.0
    for source in config_module.SUPPORTED_EMBEDDINGS:
        if source not in source_config.sources:
            continue
        value = similarities.get(source)
        if value is None:
            continue
        weight = source_config.weights[source]
        weighted += value * weight
        total += weight
    if total == 0.0:
        return None
    return max(0.0, min(1.0, weighted / total))


def _passes_content_similarity(pair: models_module.PairEvidence, config: models_module.PresetConfig) -> bool:
    return pair.content_similarity is not None and pair.content_similarity >= config.min_similarity


def _sonara_similarity(left: models_module.TrackRecord, right: models_module.TrackRecord) -> float | None:
    left_features = _sonara_features(left)
    right_features = _sonara_features(right)
    if not left_features or not right_features:
        return None
    diffs: list[float] = []
    for field in SONARA_FIELDS:
        left_value = values_module._float_or_none(left_features.get(field))
        right_value = values_module._float_or_none(right_features.get(field))
        if left_value is None or right_value is None:
            continue
        if field == "bpm":
            diff = min(_bpm_distance(left_value, right_value) or 0.0, 8.0) / 8.0
        elif field == "loudness_lufs":
            diff = min(abs(left_value - right_value), 24.0) / 24.0
        elif field == "dynamic_range_db":
            diff = min(abs(left_value - right_value), 20.0) / 20.0
        else:
            diff = min(abs(left_value - right_value), 1.0)
        diffs.append(diff)
    if not diffs:
        return None
    return max(0.0, min(1.0, 1.0 - float(np.mean(diffs))))


def _sonara_features(track: models_module.TrackRecord) -> dict[str, object] | None:
    features = track.metadata.get("sonara_features")
    return features if isinstance(features, dict) else None


def _bpm_distance(left: float | None, right: float | None) -> float | None:
    if left is None or right is None or left <= 0 or right <= 0:
        return None
    variants_left = (left / 2.0, left, left * 2.0)
    variants_right = (right / 2.0, right, right * 2.0)
    return min(abs(a - b) for a in variants_left for b in variants_right)


def _connected_components(edges: list[models_module.PairEvidence]) -> list[list[models_module.PairEvidence]]:
    neighbors: dict[int, set[int]] = {}
    edge_by_node: dict[int, list[models_module.PairEvidence]] = {}
    for edge in edges:
        neighbors.setdefault(edge.left_id, set()).add(edge.right_id)
        neighbors.setdefault(edge.right_id, set()).add(edge.left_id)
        edge_by_node.setdefault(edge.left_id, []).append(edge)
        edge_by_node.setdefault(edge.right_id, []).append(edge)
    seen: set[int] = set()
    components: list[list[models_module.PairEvidence]] = []
    for start in sorted(neighbors):
        if start in seen:
            continue
        stack = [start]
        nodes: set[int] = set()
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            nodes.add(node)
            stack.extend(sorted(neighbors.get(node, ()), reverse=True))
        component_edges = {
            edge
            for node in nodes
            for edge in edge_by_node.get(node, [])
            if edge.left_id in nodes and edge.right_id in nodes
        }
        components.append(sorted(component_edges, key=lambda item: (item.left_id, item.right_id)))
    return components
