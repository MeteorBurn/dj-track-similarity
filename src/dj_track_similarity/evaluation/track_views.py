"""Identity-bound typed track views for evaluation workflows."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..analysis_models import AnalysisTarget, SonaraFeatureRow
from ..track_models import TrackIdentity
from ..transition_diagnostics import TransitionTrack

if TYPE_CHECKING:
    from ..database import LibraryDatabase


def load_all_transition_tracks(
    db: LibraryDatabase,
) -> dict[int, TransitionTrack]:
    """Load every present track without crossing a content-generation change."""

    track_ids = tuple(track.track_id for track in db.list_track_paths())
    identities = db.get_track_identities(track_ids)
    return _load_transition_tracks(db, identities)


def load_transition_tracks_for_ids(
    db: LibraryDatabase,
    track_ids: Sequence[int],
) -> dict[int, TransitionTrack]:
    """Load current typed views for the requested IDs, omitting stale/missing."""

    identities = db.get_track_identities(track_ids)
    return _load_transition_tracks(db, identities)


def load_transition_tracks_for_targets(
    db: LibraryDatabase,
    targets: Sequence[AnalysisTarget],
) -> dict[int, TransitionTrack]:
    """Load views only while the exact search targets remain current."""

    identities: dict[int, TrackIdentity] = {}
    for target in targets:
        if target.catalog_uuid != db.catalog_uuid:
            raise ValueError(
                "Evaluation target belongs to another catalog"
            )
        identity = TrackIdentity(
            catalog_uuid=target.catalog_uuid,
            track_id=target.track_id,
            track_uuid=target.track_uuid,
            content_generation=target.content_generation,
        )
        existing = identities.get(identity.track_id)
        if existing is not None and existing != identity:
            raise ValueError(
                "Conflicting evaluation targets for one track ID"
            )
        identities[identity.track_id] = identity
    return _load_transition_tracks(db, identities)


def _load_transition_tracks(
    db: LibraryDatabase,
    expected_identities: dict[int, TrackIdentity],
) -> dict[int, TransitionTrack]:
    if not expected_identities:
        return {}
    current_before = db.get_track_identities(expected_identities)
    stable_identities = {
        track_id: identity
        for track_id, identity in expected_identities.items()
        if current_before.get(track_id) == identity
    }
    if not stable_identities:
        return {}
    try:
        summary_rows = db.get_track_summaries(tuple(stable_identities))
    except KeyError:
        return {}
    summaries = {summary.track_id: summary for summary in summary_rows}
    stable_identities = {
        track_id: identity
        for track_id, identity in stable_identities.items()
        if (
            (summary := summaries.get(track_id)) is not None
            and summary.catalog_uuid == identity.catalog_uuid
            and summary.track_uuid == identity.track_uuid
            and summary.content_generation == identity.content_generation
        )
    }
    if not stable_identities:
        return {}

    targets = tuple(
        _analysis_target(identity)
        for identity in stable_identities.values()
    )
    sonara_by_track_id = _active_sonara_rows(db, targets)
    current_after = db.get_track_identities(stable_identities)
    views: dict[int, TransitionTrack] = {}
    for track_id, identity in stable_identities.items():
        if current_after.get(track_id) != identity:
            continue
        views[track_id] = TransitionTrack(
            identity=identity,
            summary=summaries[track_id],
            sonara=sonara_by_track_id.get(track_id),
        )
    return views


def _active_sonara_rows(
    db: LibraryDatabase,
    targets: Sequence[AnalysisTarget],
) -> dict[int, SonaraFeatureRow]:
    output = db.active_analysis_output("sonara", "core")
    if output is None:
        return {}
    rows = db.load_sonara_feature_rows(output, targets=targets)
    return {
        row.target.track_id: row
        for row in rows
    }


def _analysis_target(identity: TrackIdentity) -> AnalysisTarget:
    return AnalysisTarget(
        catalog_uuid=identity.catalog_uuid,
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
    )
