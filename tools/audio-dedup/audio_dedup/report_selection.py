from __future__ import annotations

from typing import Collection, Iterable

from dj_track_similarity.track_models import TrackIdentity


def _safe_candidate_count(payload: dict[str, object]) -> int:
    stats = payload.get("statistics", {})
    if isinstance(stats, dict):
        return int(stats.get("safe_candidate_count", 0) or 0)
    return len(safe_delete_candidates(payload))


def safe_delete_candidates(payload: dict[str, object]) -> list[dict[str, object]]:
    candidates: list[dict[str, object]] = []
    for group in payload.get("groups", []):
        if not isinstance(group, dict):
            continue
        for candidate in group.get("candidate_deletes", []):
            if not isinstance(candidate, dict):
                continue
            if candidate.get("decision") == "delete_candidate" and candidate.get("safe_to_delete") == "true_candidate":
                candidates.append(candidate)
    return candidates


def selected_delete_candidates(
    payload: dict[str, object],
    selected_track_ids: Collection[int],
) -> list[dict[str, object]]:
    """Report entries a reviewer explicitly chose to delete.

    Fingerprint mode never marks a candidate safe to delete, so manual review is
    the only path to deletion there. The selection therefore replaces the
    safe-delete filter instead of narrowing it, and any group member can be
    chosen, including the suggested keeper.
    """
    selected = set()
    for track_id in selected_track_ids:
        try:
            selected.add(int(track_id))
        except (TypeError, ValueError):
            continue
    candidates: list[dict[str, object]] = []
    seen: set[int] = set()
    for group in _payload_groups(payload):
        for entry in _group_member_entries(group):
            track_id = _candidate_track_id(entry)
            if track_id < 0 or track_id not in selected or track_id in seen:
                continue
            seen.add(track_id)
            candidates.append(entry)
    return candidates


def _payload_groups(payload: dict[str, object]) -> list[dict[str, object]]:
    groups = payload.get("groups", [])
    if not isinstance(groups, list):
        return []
    return [group for group in groups if isinstance(group, dict)]


def _entry_list(group: dict[str, object], field_name: str) -> list[dict[str, object]]:
    entries = group.get(field_name, [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _group_member_entries(group: dict[str, object]) -> list[dict[str, object]]:
    """Every file of one duplicate group, keeper included.

    The ``tracks`` rows carry the identity and file facts the apply gate
    rechecks, so one uniform list covers keeper and candidates alike.
    """
    members = _entry_list(group, "tracks")
    if members:
        return members
    keeper = group.get("suggested_keeper")
    fallback = [keeper] if isinstance(keeper, dict) else []
    return fallback + _entry_list(group, "candidate_deletes")


def _candidate_track_id(candidate: dict[str, object]) -> int:
    try:
        return int(candidate["track_id"])
    except (KeyError, TypeError, ValueError):
        return -1


def _candidate_identity(candidate: dict[str, object]) -> TrackIdentity:
    return TrackIdentity(
        catalog_uuid=_candidate_text(candidate, "catalog_uuid"),
        track_id=int(candidate["track_id"]),
        track_uuid=_candidate_text(candidate, "track_uuid"),
    )


def _candidate_text(
    candidate: dict[str, object],
    field_name: str,
) -> str:
    value = candidate[field_name]
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _unique_identities(
    identities: Iterable[TrackIdentity],
) -> tuple[TrackIdentity, ...]:
    return tuple(
        sorted(
            set(identities),
            key=lambda identity: (
                identity.catalog_uuid,
                identity.track_uuid,
                identity.track_id,
            ),
        )
    )
