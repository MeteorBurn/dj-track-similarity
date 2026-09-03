"""Request-argument validation shared by the embedding and SONARA searchers."""

from __future__ import annotations

from collections.abc import Sequence

from .analysis_models import AnalysisTarget


def validate_targets(
    targets: Sequence[AnalysisTarget],
    *,
    catalog_uuid: str,
    field_name: str,
    require_nonempty: bool,
) -> tuple[AnalysisTarget, ...]:
    selected = tuple(targets)
    if require_nonempty and not selected:
        raise ValueError(
            f"{field_name} must contain at least one target"
        )
    if any(
        not isinstance(target, AnalysisTarget)
        for target in selected
    ):
        raise TypeError(
            f"{field_name} must contain only AnalysisTarget values"
        )
    if any(
        target.catalog_uuid != catalog_uuid
        for target in selected
    ):
        raise ValueError(
            f"{field_name} contains a target from another catalog"
        )
    if len(set(selected)) != len(selected):
        raise ValueError(
            f"{field_name} must not contain duplicate identities"
        )
    track_ids = [target.track_id for target in selected]
    if len(set(track_ids)) != len(track_ids):
        raise ValueError(
            f"{field_name} contains conflicting identities "
            "for one track ID"
        )
    return selected


def optional_targets(
    targets: Sequence[AnalysisTarget] | None,
    *,
    catalog_uuid: str,
) -> tuple[AnalysisTarget, ...] | None:
    if targets is None:
        return None
    return validate_targets(
        targets,
        catalog_uuid=catalog_uuid,
        field_name="candidate_targets",
        require_nonempty=False,
    )


def merge_targets(
    first: Sequence[AnalysisTarget],
    second: Sequence[AnalysisTarget],
) -> tuple[AnalysisTarget, ...]:
    merged: list[AnalysisTarget] = []
    seen: set[AnalysisTarget] = set()
    for target in (*first, *second):
        if target in seen:
            continue
        seen.add(target)
        merged.append(target)
    return tuple(merged)


def requested_track_ids(
    track_ids: Sequence[int],
) -> tuple[int, ...]:
    requested = tuple(track_ids)
    if not requested:
        raise ValueError("At least one track ID is required")
    if any(
        isinstance(track_id, bool)
        or not isinstance(track_id, int)
        or track_id <= 0
        for track_id in requested
    ):
        raise ValueError("Track IDs must be positive integers")
    if len(set(requested)) != len(requested):
        raise ValueError("Track IDs must not contain duplicates")
    return requested


def optional_track_ids(track_ids: Sequence[int]) -> frozenset[int]:
    requested = tuple(track_ids)
    if any(
        isinstance(track_id, bool)
        or not isinstance(track_id, int)
        or track_id <= 0
        for track_id in requested
    ):
        raise ValueError("Track IDs must be positive integers")
    if len(set(requested)) != len(requested):
        raise ValueError("Track IDs must not contain duplicates")
    return frozenset(requested)


def result_limit(limit: int, *, subject: str = "Search") -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError(
            f"{subject} result limit must be a non-negative integer"
        )
    return limit
