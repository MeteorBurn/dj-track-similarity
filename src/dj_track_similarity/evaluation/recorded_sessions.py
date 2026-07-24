"""Current-only read view over recorded evaluation search sessions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from ..track_models import TrackIdentity

if TYPE_CHECKING:
    from ..database import LibraryDatabase


_SOURCE_OUTPUT_KEYS = {
    "maest": ("maest", "embedding"),
    "mert": ("mert", "embedding"),
    "clap": ("clap", "embedding"),
    "sonara": ("sonara", "core"),
}


def load_current_evaluation_sessions(
    db: LibraryDatabase,
) -> list[dict[str, Any]]:
    """Return only sessions proven current by identity and active contracts.

    A session is discarded when any seed snapshot is missing or stale, or when
    its source contracts are no longer active. Individual result events are
    discarded when their track snapshot or per-event contract provenance is
    stale. The repository's deterministic ordering is normalized explicitly.
    """

    raw_sessions = db.list_search_sessions_with_events()
    track_ids = _recorded_track_ids(raw_sessions)
    identities = db.get_track_identities(track_ids)
    _validate_identity_catalog(db, identities)
    active_contract_hashes: dict[str, str | None] = {}
    current_sessions: list[dict[str, Any]] = []
    for session in raw_sessions:
        current = _current_session(
            db,
            session,
            identities=identities,
            active_contract_hashes=active_contract_hashes,
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
    active_contract_hashes: dict[str, str | None],
) -> dict[str, Any] | None:
    request = session.get("request")
    if not isinstance(request, Mapping):
        return None
    if request.get("catalog_uuid") != db.catalog_uuid:
        return None
    session_contracts = _source_contract_hashes(
        request.get("source_contract_hashes")
    )
    if not session_contracts or not _contracts_are_current(
        db,
        session_contracts,
        active_contract_hashes=active_contract_hashes,
    ):
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
            and _event_provenance_matches(
                event,
                session_contracts,
                catalog_uuid=db.catalog_uuid,
            )
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


def _contracts_are_current(
    db: LibraryDatabase,
    source_contracts: Mapping[str, str],
    *,
    active_contract_hashes: dict[str, str | None],
) -> bool:
    for source, recorded_hash in source_contracts.items():
        output_key = _SOURCE_OUTPUT_KEYS.get(source)
        if output_key is None:
            return False
        if source not in active_contract_hashes:
            output = db.active_analysis_output(*output_key)
            active_contract_hashes[source] = (
                None if output is None else output.contract_hash
            )
        if active_contract_hashes[source] != recorded_hash:
            return False
    return True


def _event_provenance_matches(
    event: Mapping[str, Any],
    session_contracts: Mapping[str, str],
    *,
    catalog_uuid: str,
) -> bool:
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
    direct = _source_contract_hashes(
        score_breakdown.get("source_contract_hashes")
    )
    if direct:
        event_contracts = direct
    else:
        event_contracts = _source_contracts_from_contributions(
            score_breakdown.get("sources")
        )
    return bool(event_contracts) and all(
        session_contracts.get(source) == contract_hash
        for source, contract_hash in event_contracts.items()
    )


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


def _source_contracts_from_contributions(
    value: object,
) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        return {}
    result: dict[str, str] = {}
    for source, contribution in value.items():
        source_name = str(source).strip().lower()
        if not source_name or not isinstance(contribution, Mapping):
            return {}
        contract_hash = _required_text_or_none(
            contribution.get("contract_hash")
        )
        if contract_hash is None:
            return {}
        result[source_name] = contract_hash
    return dict(sorted(result.items()))


def _source_contract_hashes(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        return {}
    result: dict[str, str] = {}
    for source, contract_hash in value.items():
        source_name = str(source).strip().lower()
        clean_hash = _required_text_or_none(contract_hash)
        if not source_name or clean_hash is None:
            return {}
        result[source_name] = clean_hash
    return dict(sorted(result.items()))


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
