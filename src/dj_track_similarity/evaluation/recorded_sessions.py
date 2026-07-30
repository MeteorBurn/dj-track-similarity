"""Current-only read view over recorded evaluation search sessions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from ..track_models import TrackIdentity

if TYPE_CHECKING:
    from ..database import LibraryDatabase


_LEGACY_VERSION_IDENTITY_KEYS = frozenset(
    {
        "active_contract_hash",
        "active_release_hash",
        "contract_hash",
        "contract_hashes",
        "expected_contract_hash",
        "expected_release_hash",
        "feature_manifest_hash",
        "manifest_version",
        "release_hash",
        "schema_version",
        "sonara_release_hash",
        "source_contract_hashes",
    }
)


def load_current_evaluation_sessions(
    db: LibraryDatabase,
) -> list[dict[str, Any]]:
    """Return only sessions proven current by catalog and track identity.

    A session is discarded when any seed snapshot is missing or stale, or when
    its seed snapshot is missing or stale. Individual result events are
    discarded when their track snapshot is stale. The repository's deterministic
    ordering is normalized explicitly.
    """

    raw_sessions = db.list_search_sessions_with_events()
    track_ids = _recorded_track_ids(raw_sessions)
    identities = db.get_track_identities(track_ids)
    _validate_identity_catalog(db, identities)
    current_sessions: list[dict[str, Any]] = []
    for session in raw_sessions:
        current = _current_session(
            db,
            session,
            identities=identities,
        )
        if current is not None:
            current_sessions.append(current)
    return sorted(
        current_sessions,
        key=lambda session: (
            str(session.get("created_at") or ""),
            int(session["id"]),
        ),
    )


def _current_session(
    db: LibraryDatabase,
    session: Mapping[str, Any],
    *,
    identities: Mapping[int, TrackIdentity],
) -> dict[str, Any] | None:
    request = session.get("request")
    if not isinstance(request, Mapping):
        return None
    if _contains_legacy_version_identity(request):
        return None
    if request.get("catalog_uuid") != db.catalog_uuid:
        return None
    raw_seeds = _mapping_sequence(session.get("seeds"))
    if not raw_seeds:
        return None
    expected_seeds = _mapping_sequence(request.get("seed_identities"))
    if not _recorded_seed_snapshots_match(
        expected_seeds,
        raw_seeds,
        catalog_uuid=db.catalog_uuid,
    ):
        return None
    seeds = sorted(
        (
            dict(seed)
            for seed in raw_seeds
            if _snapshot_matches(seed, identities)
        ),
        key=lambda seed: (
            _positive_int_or_none(seed.get("position")) or 0,
            _positive_int_or_none(seed.get("track_id")) or 0,
        ),
    )
    if len(seeds) != len(raw_seeds):
        return None

    events = sorted(
        (
            dict(event)
            for event in _mapping_sequence(session.get("events"))
            if _snapshot_matches(event, identities)
            and _event_provenance_matches(event, catalog_uuid=db.catalog_uuid)
        ),
        key=lambda event: (
            _positive_int_or_none(event.get("rank")) or 0,
            _positive_int_or_none(event.get("id")) or 0,
        ),
    )
    result = dict(session)
    result["request"] = dict(request)
    result["seeds"] = seeds
    result["seed_track_ids"] = [int(seed["track_id"]) for seed in seeds]
    result["events"] = events
    return result


def _event_provenance_matches(
    event: Mapping[str, Any],
    *,
    catalog_uuid: str,
) -> bool:
    if _contains_legacy_version_identity(event):
        return False
    score_breakdown = event.get("score_breakdown")
    if not isinstance(score_breakdown, Mapping):
        return False
    candidate_identity = score_breakdown.get("candidate_identity")
    if (
        not isinstance(candidate_identity, Mapping)
        or not _persisted_snapshot_matches(
            candidate_identity,
            event,
            catalog_uuid=catalog_uuid,
        )
    ):
        return False
    return True


def _recorded_seed_snapshots_match(
    expected: Sequence[Mapping[str, Any]],
    persisted: Sequence[Mapping[str, Any]],
    *,
    catalog_uuid: str,
) -> bool:
    if len(expected) != len(persisted) or not expected:
        return False
    expected_by_id = {
        _positive_int_or_none(snapshot.get("track_id")): snapshot
        for snapshot in expected
    }
    if None in expected_by_id or len(expected_by_id) != len(expected):
        return False
    return all(
        (
            expected_snapshot := expected_by_id.get(
                _positive_int_or_none(snapshot.get("track_id"))
            )
        )
        is not None
        and _persisted_snapshot_matches(
            expected_snapshot,
            snapshot,
            catalog_uuid=catalog_uuid,
        )
        for snapshot in persisted
    )


def _persisted_snapshot_matches(
    expected: Mapping[str, Any],
    persisted: Mapping[str, Any],
    *,
    catalog_uuid: str,
) -> bool:
    return (
        expected.get("catalog_uuid") == catalog_uuid
        and _positive_int_or_none(expected.get("track_id"))
        == _positive_int_or_none(persisted.get("track_id"))
        and _required_text_or_none(expected.get("track_uuid"))
        == _required_text_or_none(persisted.get("track_uuid"))
        and _positive_int_or_none(expected.get("content_generation"))
        == _positive_int_or_none(persisted.get("content_generation"))
    )


def _snapshot_matches(
    snapshot: Mapping[str, Any],
    identities: Mapping[int, TrackIdentity],
) -> bool:
    track_id = _positive_int_or_none(snapshot.get("track_id"))
    content_generation = _positive_int_or_none(
        snapshot.get("content_generation")
    )
    track_uuid = _required_text_or_none(snapshot.get("track_uuid"))
    if (
        track_id is None
        or content_generation is None
        or track_uuid is None
    ):
        return False
    identity = identities.get(track_id)
    return (
        identity is not None
        and identity.track_uuid == track_uuid
        and identity.content_generation == content_generation
    )


def _recorded_track_ids(
    sessions: Sequence[Mapping[str, Any]],
) -> tuple[int, ...]:
    track_ids: list[int] = []
    for session in sessions:
        for row in (
            *_mapping_sequence(session.get("seeds")),
            *_mapping_sequence(session.get("events")),
        ):
            track_id = _positive_int_or_none(row.get("track_id"))
            if track_id is not None:
                track_ids.append(track_id)
    return tuple(dict.fromkeys(track_ids))


def _validate_identity_catalog(
    db: LibraryDatabase,
    identities: Mapping[int, TrackIdentity],
) -> None:
    if any(
        identity.catalog_uuid != db.catalog_uuid
        for identity in identities.values()
    ):
        raise RuntimeError(
            "Track identity repository returned another catalog"
        )


def _mapping_sequence(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _positive_int_or_none(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _required_text_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _contains_legacy_version_identity(value: object) -> bool:
    if isinstance(value, Mapping):
        return bool(
            _LEGACY_VERSION_IDENTITY_KEYS.intersection(
                str(key) for key in value
            )
        ) or any(
            _contains_legacy_version_identity(item)
            for item in value.values()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_legacy_version_identity(item) for item in value)
    return False
