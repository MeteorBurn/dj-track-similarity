from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from numbers import Integral, Real
import sqlite3
from typing import Any


PROMOTED_SCORE_PROFILE_SETTING_KEY = "evaluation.promoted_score_profile"


class EvaluationRepository:
    """V7-only evaluation persistence mixin.

    The concrete database gateway must provide:

    * ``connect()`` for the v7 Core database;
    * ``connect_evaluation(create=False)`` for the optional Evaluation sidecar,
      returning ``None`` when it is absent and creation was not requested;
    * ``_write_lock`` shared with the other repository mixins.
    """

    def connect_evaluation(
        self,
        *,
        create: bool = False,
    ) -> sqlite3.Connection | None:
        raise NotImplementedError(
            "LibraryDatabase must provide connect_evaluation(create=...)"
        )

    def open_evaluation_storage(self) -> None:
        """Explicitly create/open and validate the optional Evaluation sidecar."""

        with self._write_lock:
            connection = self.connect_evaluation(create=True)
            if connection is None:
                raise RuntimeError("Failed to open the Evaluation database")
            connection.close()

    def list_search_sessions_with_events(self) -> list[dict[str, Any]]:
        connection = self.connect_evaluation(create=False)
        if connection is None:
            return []
        with closing(connection):
            session_rows = connection.execute(
                """
                SELECT session_id, mode, request_json, created_at
                FROM search_sessions
                ORDER BY created_at, session_id
                """
            ).fetchall()
            seed_rows = connection.execute(
                """
                SELECT
                    session_id,
                    position,
                    track_id,
                    track_uuid,
                    content_generation
                FROM search_session_seeds
                ORDER BY session_id, position
                """
            ).fetchall()
            event_rows = connection.execute(
                """
                SELECT
                    search_result_event_id,
                    session_id,
                    rank,
                    track_id,
                    track_uuid,
                    content_generation,
                    total_score,
                    score_breakdown_json,
                    created_at
                FROM search_result_events
                ORDER BY session_id, rank, search_result_event_id
                """
            ).fetchall()

        seeds_by_session: dict[int, list[dict[str, Any]]] = {}
        for row in seed_rows:
            session_id = int(row["session_id"])
            seeds_by_session.setdefault(session_id, []).append(
                {
                    "position": int(row["position"]),
                    "track_id": int(row["track_id"]),
                    "track_uuid": str(row["track_uuid"]),
                    "content_generation": int(row["content_generation"]),
                }
            )

        events_by_session: dict[int, list[dict[str, Any]]] = {}
        for row in event_rows:
            session_id = int(row["session_id"])
            events_by_session.setdefault(session_id, []).append(
                {
                    "id": int(row["search_result_event_id"]),
                    "session_id": session_id,
                    "track_id": int(row["track_id"]),
                    "track_uuid": str(row["track_uuid"]),
                    "content_generation": int(row["content_generation"]),
                    "rank": int(row["rank"]),
                    "total_score": float(row["total_score"]),
                    "score_breakdown": _json_load(
                        row["score_breakdown_json"],
                        "Search result score breakdown",
                    ),
                    "created_at": str(row["created_at"]),
                }
            )

        sessions: list[dict[str, Any]] = []
        for row in session_rows:
            session_id = int(row["session_id"])
            seeds = seeds_by_session.get(session_id, [])
            sessions.append(
                {
                    "id": session_id,
                    "mode": str(row["mode"]),
                    "seed_track_ids": [int(seed["track_id"]) for seed in seeds],
                    "seeds": seeds,
                    "request": _json_load(
                        row["request_json"],
                        "Search session request",
                    ),
                    "created_at": str(row["created_at"]),
                    "events": events_by_session.get(session_id, []),
                }
            )
        return sessions

    def get_pair_feedback_map(
        self,
    ) -> dict[tuple[int, int, str], dict[str, Any]]:
        with closing(self.connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                    feedback_id,
                    seed_track_id,
                    candidate_track_id,
                    rating,
                    reason_tags_json,
                    notes,
                    source,
                    created_at,
                    updated_at
                FROM pair_feedback
                ORDER BY seed_track_id, candidate_track_id, source
                """
            ).fetchall()
        feedback: dict[tuple[int, int, str], dict[str, Any]] = {}
        for row in rows:
            seed_track_id = int(row["seed_track_id"])
            candidate_track_id = int(row["candidate_track_id"])
            source = str(row["source"])
            feedback[(seed_track_id, candidate_track_id, source)] = {
                "id": int(row["feedback_id"]),
                "seed_track_id": seed_track_id,
                "candidate_track_id": candidate_track_id,
                "rating": int(row["rating"]),
                "reason_tags": _json_load(
                    row["reason_tags_json"],
                    "Pair feedback reason tags",
                ),
                "notes": row["notes"],
                "source": source,
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
        return feedback

    def count_evaluation_rows(self) -> dict[str, int]:
        with closing(self.connect()) as core_connection:
            counts = {
                "pair_feedback": int(
                    core_connection.execute(
                        "SELECT COUNT(*) FROM pair_feedback"
                    ).fetchone()[0]
                ),
                "transition_feedback": int(
                    core_connection.execute(
                        "SELECT COUNT(*) FROM transition_feedback"
                    ).fetchone()[0]
                ),
            }

        sidecar_tables = (
            "search_sessions",
            "search_session_seeds",
            "search_result_events",
            "calibration_runs",
        )
        sidecar_connection = self.connect_evaluation(create=False)
        if sidecar_connection is None:
            counts.update({table: 0 for table in sidecar_tables})
            return counts
        with closing(sidecar_connection):
            counts.update(
                {
                    table: int(
                        sidecar_connection.execute(
                            f'SELECT COUNT(*) FROM "{table}"'
                        ).fetchone()[0]
                    )
                    for table in sidecar_tables
                }
            )
        return counts

    def get_promoted_score_profile(self) -> dict[str, Any] | None:
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT setting_value
                FROM library_settings
                WHERE setting_key = ?
                """,
                (PROMOTED_SCORE_PROFILE_SETTING_KEY,),
            ).fetchone()
        if row is None:
            return None
        payload = _json_load(row["setting_value"], "Promoted score profile")
        if not isinstance(payload, dict):
            raise RuntimeError("Promoted score profile setting must be a JSON object")
        return payload

    def set_promoted_score_profile(
        self,
        profile: Mapping[str, Any],
    ) -> dict[str, Any]:
        clean_profile = _json_object(profile, "Promoted score profile")
        timestamp = _utc_timestamp()
        with (
            self._write_lock,
            closing(self.connect()) as connection,
            connection,
        ):
            connection.execute(
                """
                INSERT INTO library_settings(
                    setting_key,
                    setting_value,
                    updated_at
                )
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
                """,
                (
                    PROMOTED_SCORE_PROFILE_SETTING_KEY,
                    _json_text(clean_profile),
                    timestamp,
                ),
            )
        promoted_profile = self.get_promoted_score_profile()
        if promoted_profile is None:
            raise RuntimeError("Failed to persist promoted score profile")
        return promoted_profile

    def get_evaluation_setting(self, setting_key: str) -> Any | None:
        clean_key = _required_text(setting_key, "Evaluation setting key")
        connection = self.connect_evaluation(create=False)
        if connection is None:
            return None
        with closing(connection):
            row = connection.execute(
                """
                SELECT value_json
                FROM evaluation_settings
                WHERE setting_key = ?
                """,
                (clean_key,),
            ).fetchone()
        if row is None:
            return None
        return _json_load(row["value_json"], "Evaluation setting")

    def set_evaluation_setting(self, setting_key: str, value: object) -> Any:
        clean_key = _required_text(setting_key, "Evaluation setting key")
        value_json = _json_text(value)
        timestamp = _utc_timestamp()
        with self._write_lock:
            connection = _required_evaluation_connection(self, create=True)
            with closing(connection), connection:
                connection.execute(
                    """
                    INSERT INTO evaluation_settings(
                        setting_key,
                        value_json,
                        updated_at
                    )
                    VALUES (?, ?, ?)
                    ON CONFLICT(setting_key) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    (clean_key, value_json, timestamp),
                )
        return _json_load(value_json, "Evaluation setting")

    def create_search_session(
        self,
        mode: str,
        seed_track_ids: Sequence[int],
        request: Mapping[str, Any],
    ) -> int:
        clean_mode = _required_text(mode, "Search session mode")
        clean_seed_track_ids = _positive_unique_ints(
            seed_track_ids,
            "Seed track id",
        )
        request_json = _json_text(dict(request))
        timestamp = _utc_timestamp()
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                snapshots = _load_track_snapshots(
                    core_connection,
                    clean_seed_track_ids,
                    field_name="Seed track id",
                )
            evaluation_connection = _required_evaluation_connection(
                self,
                create=True,
            )
            with closing(evaluation_connection), evaluation_connection:
                cursor = evaluation_connection.execute(
                    """
                    INSERT INTO search_sessions(mode, request_json, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (clean_mode, request_json, timestamp),
                )
                session_id = int(cursor.lastrowid)
                evaluation_connection.executemany(
                    """
                    INSERT INTO search_session_seeds(
                        session_id,
                        position,
                        track_id,
                        track_uuid,
                        content_generation
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        (
                            session_id,
                            position,
                            snapshot["track_id"],
                            snapshot["track_uuid"],
                            snapshot["content_generation"],
                        )
                        for position, snapshot in enumerate(snapshots)
                    ),
                )
                return session_id

    def record_search_result_event(
        self,
        session_id: int,
        track_id: int,
        rank: int,
        total_score: float,
        score_breakdown: Mapping[str, Any],
    ) -> int:
        clean_session_id = _positive_int(session_id, "Search session id")
        clean_track_id = _positive_int(track_id, "Search result track id")
        clean_rank = _non_negative_int(rank, "Search result rank")
        clean_total_score = _finite_float(
            total_score,
            "Search result total score",
        )
        score_breakdown_json = _json_text(dict(score_breakdown))
        timestamp = _utc_timestamp()
        with self._write_lock:
            with closing(self.connect()) as core_connection:
                snapshot = _load_track_snapshots(
                    core_connection,
                    (clean_track_id,),
                    field_name="Search result track id",
                )[0]
            evaluation_connection = _required_evaluation_connection(
                self,
                create=True,
            )
            with closing(evaluation_connection), evaluation_connection:
                cursor = evaluation_connection.execute(
                    """
                    INSERT INTO search_result_events(
                        session_id,
                        rank,
                        track_id,
                        track_uuid,
                        content_generation,
                        total_score,
                        score_breakdown_json,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean_session_id,
                        clean_rank,
                        snapshot["track_id"],
                        snapshot["track_uuid"],
                        snapshot["content_generation"],
                        clean_total_score,
                        score_breakdown_json,
                        timestamp,
                    ),
                )
                return int(cursor.lastrowid)

    def upsert_track_pair_feedback(
        self,
        seed_track_id: int,
        candidate_track_id: int,
        rating: int,
        reason_tags: Sequence[str] = (),
        notes: str | None = None,
        source: str = "manual",
    ) -> int:
        feedback_ids = self.upsert_track_pair_feedback_for_seeds(
            (seed_track_id,),
            candidate_track_id,
            rating,
            reason_tags=reason_tags,
            notes=notes,
            source=source,
        )
        return feedback_ids[0]

    def upsert_track_pair_feedback_for_seeds(
        self,
        seed_track_ids: Sequence[int],
        candidate_track_id: int,
        rating: int,
        reason_tags: Sequence[str] = (),
        notes: str | None = None,
        source: str = "manual",
    ) -> list[int]:
        clean_seed_track_ids = _positive_unique_ints(
            seed_track_ids,
            "Seed track id",
        )
        clean_candidate_track_id = _positive_int(
            candidate_track_id,
            "Candidate track id",
        )
        clean_rating = _rating(rating)
        reason_tags_json = _json_text(_clean_tags(reason_tags, "Reason tag"))
        clean_source = _required_text(source, "Pair feedback source")
        timestamp = _utc_timestamp()
        with (
            self._write_lock,
            closing(self.connect()) as connection,
            connection,
        ):
            for clean_seed_track_id in clean_seed_track_ids:
                connection.execute(
                    """
                    INSERT INTO pair_feedback(
                        seed_track_id,
                        candidate_track_id,
                        rating,
                        reason_tags_json,
                        notes,
                        source,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(seed_track_id, candidate_track_id, source)
                    DO UPDATE SET
                        rating = excluded.rating,
                        reason_tags_json = excluded.reason_tags_json,
                        notes = excluded.notes,
                        updated_at = excluded.updated_at
                    """,
                    (
                        clean_seed_track_id,
                        clean_candidate_track_id,
                        clean_rating,
                        reason_tags_json,
                        notes,
                        clean_source,
                        timestamp,
                        timestamp,
                    ),
                )
            rows = connection.execute(
                f"""
                SELECT seed_track_id, feedback_id
                FROM pair_feedback
                WHERE seed_track_id IN (
                    {",".join("?" for _ in clean_seed_track_ids)}
                )
                  AND candidate_track_id = ?
                  AND source = ?
                """,
                (
                    *clean_seed_track_ids,
                    clean_candidate_track_id,
                    clean_source,
                ),
            ).fetchall()
        ids_by_seed_track_id = {
            int(row["seed_track_id"]): int(row["feedback_id"])
            for row in rows
        }
        feedback_ids = [
            ids_by_seed_track_id[seed_track_id]
            for seed_track_id in clean_seed_track_ids
            if seed_track_id in ids_by_seed_track_id
        ]
        if len(feedback_ids) != len(clean_seed_track_ids):
            raise RuntimeError(
                "Failed to upsert pair feedback for every seed"
            )
        return feedback_ids

    def add_transition_feedback(
        self,
        outgoing_track_id: int,
        incoming_track_id: int,
        rating: int,
        risk_tags: Sequence[str] = (),
        notes: str | None = None,
        source: str = "manual",
    ) -> int:
        clean_outgoing_track_id = _positive_int(
            outgoing_track_id,
            "Outgoing track id",
        )
        clean_incoming_track_id = _positive_int(
            incoming_track_id,
            "Incoming track id",
        )
        clean_rating = _rating(rating)
        risk_tags_json = _json_text(_clean_tags(risk_tags, "Risk tag"))
        clean_source = _required_text(source, "Transition feedback source")
        timestamp = _utc_timestamp()
        with (
            self._write_lock,
            closing(self.connect()) as connection,
            connection,
        ):
            cursor = connection.execute(
                """
                INSERT INTO transition_feedback(
                    outgoing_track_id,
                    incoming_track_id,
                    rating,
                    risk_tags_json,
                    notes,
                    source,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_outgoing_track_id,
                    clean_incoming_track_id,
                    clean_rating,
                    risk_tags_json,
                    notes,
                    clean_source,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def record_calibration_run(
        self,
        profile_name: str,
        search_mode: str,
        config: Mapping[str, Any],
        metrics: Mapping[str, Any],
    ) -> int:
        clean_profile_name = _required_text(
            profile_name,
            "Calibration profile name",
        )
        clean_search_mode = _required_text(
            search_mode,
            "Calibration search mode",
        )
        config_json = _json_text(dict(config))
        metrics_json = _json_text(dict(metrics))
        timestamp = _utc_timestamp()
        with self._write_lock:
            connection = _required_evaluation_connection(self, create=True)
            with closing(connection), connection:
                cursor = connection.execute(
                    """
                    INSERT INTO calibration_runs(
                        profile_name,
                        search_mode,
                        config_json,
                        metrics_json,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        clean_profile_name,
                        clean_search_mode,
                        config_json,
                        metrics_json,
                        timestamp,
                    ),
                )
                return int(cursor.lastrowid)


def _required_evaluation_connection(
    repository: EvaluationRepository,
    *,
    create: bool,
) -> sqlite3.Connection:
    connection = repository.connect_evaluation(create=create)
    if connection is None:
        raise RuntimeError("Evaluation database is not available")
    return connection


def _load_track_snapshots(
    connection: sqlite3.Connection,
    track_ids: Sequence[int],
    *,
    field_name: str,
) -> tuple[dict[str, Any], ...]:
    rows = connection.execute(
        f"""
        SELECT track_id, track_uuid, content_generation
        FROM tracks
        WHERE track_id IN ({",".join("?" for _ in track_ids)})
        """,
        tuple(track_ids),
    ).fetchall()
    rows_by_track_id = {
        int(row["track_id"]): {
            "track_id": int(row["track_id"]),
            "track_uuid": str(row["track_uuid"]),
            "content_generation": int(row["content_generation"]),
        }
        for row in rows
    }
    missing_track_ids = [
        track_id
        for track_id in track_ids
        if track_id not in rows_by_track_id
    ]
    if missing_track_ids:
        raise ValueError(
            f"{field_name} does not exist in the current catalog: "
            f"{missing_track_ids}"
        )
    snapshots = tuple(rows_by_track_id[track_id] for track_id in track_ids)
    for snapshot in snapshots:
        if not snapshot["track_uuid"].strip():
            raise RuntimeError("Track snapshot has an empty track_uuid")
        if snapshot["content_generation"] <= 0:
            raise RuntimeError(
                "Track snapshot has an invalid content_generation"
            )
    return snapshots


def _json_text(value: object) -> str:
    return json.dumps(
        _canonical_json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )


def _canonical_json_value(
    value: object,
    *,
    field_path: str = "$",
    ancestors: frozenset[int] = frozenset(),
) -> object:
    """Return a deterministic, strictly JSON-compatible value.

    This helper intentionally has no dependency on audio-analysis or legacy
    metadata modules.  It accepts ordinary JSON scalars plus mappings and
    list/tuple containers, normalises numeric scalar subclasses, and rejects
    lossy coercions.
    """

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{field_path} must contain only finite numbers")
        return number
    if isinstance(value, Mapping):
        identity = id(value)
        if identity in ancestors:
            raise ValueError(f"{field_path} contains a circular reference")
        nested_ancestors = ancestors | {identity}
        normalized: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"{field_path} JSON object keys must be strings"
                )
            normalized[key] = _canonical_json_value(
                item,
                field_path=f"{field_path}.{key}",
                ancestors=nested_ancestors,
            )
        return normalized
    if isinstance(value, (list, tuple)):
        identity = id(value)
        if identity in ancestors:
            raise ValueError(f"{field_path} contains a circular reference")
        nested_ancestors = ancestors | {identity}
        return [
            _canonical_json_value(
                item,
                field_path=f"{field_path}[{index}]",
                ancestors=nested_ancestors,
            )
            for index, item in enumerate(value)
        ]
    raise TypeError(
        f"{field_path} contains unsupported JSON value type "
        f"{type(value).__name__}"
    )


def _json_load(value: object, field_name: str) -> Any:
    try:
        return json.loads(str(value))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{field_name} is not valid JSON") from error


def _json_object(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a JSON object")
    return dict(value)


def _required_text(value: object, field_name: str) -> str:
    if value is None:
        raise ValueError(f"{field_name} must not be empty")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be empty")
    return text


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if clean_value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return clean_value


def _positive_unique_ints(
    values: Sequence[int],
    field_name: str,
) -> tuple[int, ...]:
    clean_values = tuple(
        dict.fromkeys(_positive_int(value, field_name) for value in values)
    )
    if not clean_values:
        raise ValueError(
            f"{field_name} list must contain at least one value"
        )
    return clean_values


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} must be a non-negative integer"
        ) from error
    if clean_value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return clean_value


def _finite_float(value: float, field_name: str) -> float:
    try:
        clean_value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be finite") from error
    if not math.isfinite(clean_value):
        raise ValueError(f"{field_name} must be finite")
    return clean_value


def _rating(value: int) -> int:
    if isinstance(value, bool):
        raise ValueError("Rating must be an integer between 0 and 3")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Rating must be an integer between 0 and 3"
        ) from error
    if clean_value < 0 or clean_value > 3:
        raise ValueError("Rating must be an integer between 0 and 3")
    return clean_value


def _clean_tags(tags: Sequence[str], field_name: str) -> list[str]:
    if isinstance(tags, str):
        raise TypeError(
            f"{field_name} list must be a sequence of strings, not a string"
        )
    return [text for tag in tags if (text := str(tag).strip())]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
