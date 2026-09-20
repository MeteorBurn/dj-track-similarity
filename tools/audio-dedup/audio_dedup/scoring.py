from __future__ import annotations

from typing import Iterable, Mapping

from . import config as config_module
from . import models as models_module
from . import progress as progress_module
from . import values as values_module


def groups_from_fingerprint_pairs(
    tracks: list[models_module.TrackRecord],
    fingerprint_scores: Mapping[tuple[int, int], float],
    *,
    limit_groups: int | None = None,
    progress_callback: models_module.ProgressCallback | None = None,
    should_cancel: models_module.CancelCheck | None = None,
) -> list[models_module.DuplicateGroup]:
    """Group the LSH-retrieved pairs that native matching confirmed."""

    by_id = {track.track_id: track for track in tracks}
    edges: list[models_module.PairEvidence] = []
    pair_total = len(fingerprint_scores)
    for index, ((left_id, right_id), score) in enumerate(sorted(fingerprint_scores.items()), start=1):
        progress_module._raise_if_cancelled(should_cancel)
        if score >= config_module.FINGERPRINT_REVIEW_MIN_SIMILARITY:
            left = by_id.get(left_id)
            right = by_id.get(right_id)
            if left is not None and right is not None:
                edges.append(_pair_evidence(left, right, score, ("fingerprint_lsh",)))
        if index == pair_total or index % 50 == 0:
            progress_module._report_progress(progress_callback, index, pair_total, "Searching duplicate pairs")
    if not edges:
        progress_module._report_progress(progress_callback, 1, 1, "No fingerprint duplicates")
        return []
    groups: list[models_module.DuplicateGroup] = []
    for edge_group in _connected_components(edges):
        track_ids = tuple(sorted({edge.left_id for edge in edge_group} | {edge.right_id for edge in edge_group}))
        if len(track_ids) < 2:
            continue
        groups.append(
            models_module.DuplicateGroup(
                len(groups) + 1,
                track_ids,
                tuple(sorted(edge_group, key=_pair_order)),
            )
        )
        if limit_groups is not None and len(groups) >= max(0, limit_groups):
            break
    return groups


def groups_from_fingerprint_clusters(
    clusters: Iterable[object],
    tracks: list[models_module.TrackRecord],
    *,
    limit_groups: int | None = None,
    progress_callback: models_module.ProgressCallback | None = None,
    should_cancel: models_module.CancelCheck | None = None,
) -> list[models_module.DuplicateGroup]:
    """Turn upstream-scan clusters into report groups without re-deciding membership."""
    by_id = {track.track_id: track for track in tracks}
    selected_clusters = [
        cluster
        for cluster in clusters
        if all(track_id in by_id for track_id in cluster.member_ids)
    ]
    cluster_total = len(selected_clusters)
    if cluster_total == 0:
        progress_module._report_progress(progress_callback, 1, 1, "No fingerprint duplicates")
        return []
    groups: list[models_module.DuplicateGroup] = []
    for index, cluster in enumerate(selected_clusters, start=1):
        progress_module._raise_if_cancelled(should_cancel)
        evidence = [
            _pair_evidence(by_id[left_id], by_id[right_id], score, ("fingerprint_scan",))
            for (left_id, right_id), score in sorted(cluster.pair_scores.items())
        ]
        if not evidence:
            continue
        groups.append(
            models_module.DuplicateGroup(
                len(groups) + 1,
                tuple(sorted(cluster.member_ids)),
                tuple(sorted(evidence, key=_pair_order)),
            )
        )
        progress_module._report_progress(progress_callback, index, cluster_total, "Building duplicate groups")
        if limit_groups is not None and len(groups) >= max(0, limit_groups):
            break
    return groups


def _pair_evidence(
    left: models_module.TrackRecord,
    right: models_module.TrackRecord,
    fingerprint_similarity: float,
    candidate_sources: tuple[str, ...],
) -> models_module.PairEvidence:
    duration_diff, duration_ratio = values_module._duration_distance(left, right)
    return models_module.PairEvidence(
        left_id=left.track_id,
        right_id=right.track_id,
        fingerprint_similarity=max(0.0, min(1.0, float(fingerprint_similarity))),
        duration_diff_seconds=duration_diff,
        duration_diff_ratio=duration_ratio,
        candidate_sources=candidate_sources,
    )


def _pair_order(pair: models_module.PairEvidence) -> tuple[float, int, int]:
    return (-pair.fingerprint_similarity, pair.left_id, pair.right_id)


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
