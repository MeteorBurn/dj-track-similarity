"""SheetSage2's atomic analysis rows and shared readiness query."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from typing import Any, cast

from ..analysis.sheetsage2_features import derive_sheetsage2_features, validate_sheetsage2_timeline
from ..analysis_models import SheetSage2Write
from ..library_models import (
    SheetSage2Event,
    SheetSage2Features,
    SheetSage2Interval,
    SheetSage2Note,
    SheetSage2Rhythm,
    SheetSage2Timeline,
)
from ..track_models import TrackIdentity
from .ddl import SHEETSAGE2_FEATURE_COLUMNS, SHEETSAGE2_JSON_FEATURES


SHEETSAGE2_READY_FROM = """
    FROM tracks AS t
    JOIN sheetsage2_timeline AS timeline
      ON timeline.track_id = t.track_id AND timeline.track_uuid = t.track_uuid
    JOIN sheetsage2_features AS features
      ON features.track_id = t.track_id AND features.track_uuid = t.track_uuid
     AND features.analyzed_at = timeline.analyzed_at
    JOIN sheetsage2_embeddings AS embedding
      ON embedding.track_id = t.track_id AND embedding.track_uuid = t.track_uuid
     AND embedding.analyzed_at = timeline.analyzed_at AND embedding.layer = 24
    WHERE t.missing_since IS NULL
"""


def ready_sheetsage2_target_keys(
    connection: sqlite3.Connection,
    track_ids: Sequence[int] | None = None,
) -> set[tuple[int, str]]:
    selected = "" if track_ids is None else " AND t.track_id IN (SELECT value FROM json_each(?))"
    parameters = () if track_ids is None else (json.dumps(list(track_ids)),)
    return {
        (int(row[0]), str(row[1]))
        for row in connection.execute(
            "SELECT t.track_id, t.track_uuid " + SHEETSAGE2_READY_FROM + selected,
            parameters,
        )
    }


def read_sheetsage2_features(
    connection: sqlite3.Connection,
    track_id: int,
) -> SheetSage2Features | None:
    row = connection.execute(
        "SELECT features.* " + SHEETSAGE2_READY_FROM + " AND t.track_id = ?",
        (track_id,),
    ).fetchone()
    if row is None:
        return None
    return SheetSage2Features(
        **{
            name: json.loads(row[name]) if name in SHEETSAGE2_JSON_FEATURES else row[name]
            for name, _kind in SHEETSAGE2_FEATURE_COLUMNS
        },
        analyzed_at=str(row["analyzed_at"]),
    )


def read_sheetsage2_timeline(
    connection: sqlite3.Connection,
    expected: TrackIdentity,
) -> SheetSage2Timeline:
    track = connection.execute(
        "SELECT track_uuid FROM tracks WHERE track_id = ? AND missing_since IS NULL",
        (expected.track_id,),
    ).fetchone()
    if track is None:
        raise KeyError(f"Unknown current track id: {expected.track_id}")
    if str(track["track_uuid"]) != expected.track_uuid:
        raise RuntimeError("Track identity changed; reopen the track")
    row = connection.execute(
        "SELECT timeline.timeline_json, timeline.analyzed_at "
        + SHEETSAGE2_READY_FROM + " AND t.track_id = ?",
        (expected.track_id,),
    ).fetchone()
    if row is None:
        raise KeyError("No current complete SheetSage2 analysis for this track")
    try:
        timeline = cast(dict[str, Any], validate_sheetsage2_timeline(json.loads(row["timeline_json"])))
    except (TypeError, ValueError) as error:
        raise ValueError(f"Stored SheetSage2 timeline is invalid: {error}") from error
    events = []
    for event in timeline["events"]:
        rhythm = event.get("rhythm")
        events.append(SheetSage2Event(
            time_s=event["time_s"],
            rhythm=SheetSage2Rhythm(
                eighth_position=rhythm["eighth_position"],
                numerator=rhythm.get("numerator"),
                denominator=rhythm.get("denominator"),
            ) if rhythm is not None else None,
            **{
                name: SheetSage2Interval(label=interval["label"], end_s=interval["end_s"])
                if (interval := event.get(name)) is not None else None
                for name in ("chord", "key", "structure")
            },
            melody=tuple(SheetSage2Note(
                start_s=note["start_s"], end_s=note["end_s"],
                pitch_midi=note["pitch_midi"], source_track=note["source_track"],
            ) for note in event.get("melody", [])),
        ))
    return SheetSage2Timeline(
        catalog_uuid=expected.catalog_uuid, track_id=expected.track_id,
        track_uuid=expected.track_uuid, analyzed_at=str(row["analyzed_at"]),
        duration_s=timeline["duration_s"], events=tuple(events),
        warnings=tuple(timeline["warnings"]),
    )


def upsert_sheetsage2_analysis(connection: sqlite3.Connection, write: SheetSage2Write) -> None:
    # Revalidate mutable nested JSON at the write boundary, not only when the
    # frozen result object was constructed before entering the transaction.
    timeline = validate_sheetsage2_timeline(dict(write.timeline))
    features = derive_sheetsage2_features(timeline)
    if dict(write.features) != features:
        raise ValueError("SheetSage2 features must be derived from the same timeline")
    connection.execute(
        """
        INSERT INTO sheetsage2_timeline(track_id, track_uuid, timeline_json, analyzed_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            track_uuid = excluded.track_uuid,
            timeline_json = excluded.timeline_json,
            analyzed_at = excluded.analyzed_at
        """,
        (write.target.track_id, write.target.track_uuid, _json(timeline), write.analyzed_at),
    )
    names = tuple(name for name, _kind in SHEETSAGE2_FEATURE_COLUMNS)
    columns = ("track_id", "track_uuid", *names, "analyzed_at")
    values = (
        write.target.track_id, write.target.track_uuid,
        *(_json(features[name]) if name in SHEETSAGE2_JSON_FEATURES else features[name] for name in names),
        write.analyzed_at,
    )
    connection.execute(
        f"INSERT INTO sheetsage2_features ({', '.join(columns)}) "
        f"VALUES ({', '.join('?' for _ in columns)}) "
        "ON CONFLICT(track_id) DO UPDATE SET "
        + ", ".join(f"{name} = excluded.{name}" for name in columns if name != "track_id"),
        values,
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
