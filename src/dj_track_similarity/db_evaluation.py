from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import closing
from datetime import datetime, timezone
import json
import math
from numbers import Integral, Real
import sqlite3
from typing import Any

from .db_ddl import (
    TEXT_PRESET_FEEDBACK_INDEX_DDL,
    TEXT_PRESET_FEEDBACK_SELECTION_SIZE_DDL,
    TEXT_PRESET_FEEDBACK_TABLE_DDL,
    TEXT_PRESET_FEEDBACK_WEIGHT_DDL,
)
from .track_models import TrackIdentity


class EvaluationRepository:
    """Evaluation persistence mixin.

    The concrete database gateway must provide:

    * ``connect()`` for the library database;
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

    def record_text_preset_feedback(
        self,
        *,
        track_uuid: str,
        preset_keys: Sequence[str],
        analysis_family: str,
        verdict: int,
        preset_scores: Mapping[str, float] | None = None,
    ) -> int:
        """Store one relevance verdict per selected preset for a text-search hit.

        ``verdict`` is +1 (relevant) or -1 (irrelevant); 0 removes the stored
        verdicts for the given presets. This is the raw reinforcement signal
        that ``scripts/prompt_preset_tune.py`` reads. It lives in the library
        database beside ``likes``; trained classifier outputs never enter it.
        """
        clean_uuid = _required_text(track_uuid, "Track uuid")
        clean_keys: list[str] = []
        for preset_key in preset_keys:
            clean_key = _required_text(preset_key, "Preset key")
            if clean_key not in clean_keys:
                clean_keys.append(clean_key)
        if not clean_keys:
            raise ValueError("At least one preset key is required")
        if analysis_family not in ("clap", "mulan"):
            raise ValueError(f"Unknown text embedding family: {analysis_family}")
        if verdict not in (-1, 0, 1):
            raise ValueError("Verdict must be -1, 0 or 1")
        timestamp = _utc_timestamp()
        with self._write_lock:
            with closing(self.connect()) as connection, connection:
                # Libraries created before this table gain it on the first
                # explicit verdict click: an additive capability, not a
                # migration of existing data.
                connection.execute(TEXT_PRESET_FEEDBACK_TABLE_DDL)
                connection.execute(TEXT_PRESET_FEEDBACK_INDEX_DDL)
                _add_missing_columns(connection)
                row = connection.execute(
                    """
                    SELECT track_id FROM tracks
                    WHERE track_uuid = ? AND missing_since IS NULL
                    """,
                    (clean_uuid,),
                ).fetchone()
                if row is None:
                    raise KeyError(f"Unknown track uuid: {clean_uuid}")
                track_id = int(row[0])
                placeholders = ", ".join("?" for _ in clean_keys)
                if verdict == 0:
                    cursor = connection.execute(
                        f"""
                        DELETE FROM text_preset_feedback
                        WHERE track_id = ?
                          AND analysis_family = ?
                          AND preset_key IN ({placeholders})
                        """,
                        (track_id, analysis_family, *clean_keys),
                    )
                    return int(cursor.rowcount)
                weights = _preset_weights(clean_keys, preset_scores)
                connection.executemany(
                    """
                    INSERT INTO text_preset_feedback(
                        track_id, preset_key, analysis_family, verdict,
                        selection_size, weight, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(track_id, preset_key, analysis_family)
                    DO UPDATE SET
                        verdict = excluded.verdict,
                        selection_size = excluded.selection_size,
                        weight = excluded.weight,
                        updated_at = excluded.updated_at
                    """,
                    (
                        (
                            track_id,
                            preset_key,
                            analysis_family,
                            verdict,
                            len(clean_keys),
                            weights[preset_key],
                            timestamp,
                            timestamp,
                        )
                        for preset_key in clean_keys
                    ),
                )
                return len(clean_keys)

    def read_text_preset_feedback(
        self,
        *,
        track_uuids: Sequence[str],
        preset_keys: Sequence[str],
        analysis_family: str,
    ) -> dict[str, int]:
        """Return the verdict already stored for each of these tracks.

        A click writes the same verdict to every preset that built the bank, so
        a track normally carries one answer across the selection. Where an older
        selection disagrees with this one the track is reported as unmarked
        rather than as whichever row happened to sort first: a half-remembered
        verdict is worse than none, because the tab would render it as settled.

        Tracks with nothing stored are absent from the result.
        """

        clean_uuids = [uuid for uuid in (u.strip() for u in track_uuids) if uuid]
        clean_keys = [key for key in (k.strip() for k in preset_keys) if key]
        if not clean_uuids or not clean_keys:
            return {}
        if analysis_family not in ("clap", "mulan"):
            raise ValueError(f"Unknown text embedding family: {analysis_family}")
        with closing(self.connect()) as connection:
            # A library that has never carried a verdict has no table yet, and
            # asking for one is a read, not a reason to create it.
            if connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name = 'text_preset_feedback'
                """
            ).fetchone() is None:
                return {}
            uuid_slots = ", ".join("?" for _ in clean_uuids)
            key_slots = ", ".join("?" for _ in clean_keys)
            rows = connection.execute(
                f"""
                SELECT tracks.track_uuid, feedback.verdict
                FROM text_preset_feedback AS feedback
                JOIN tracks ON tracks.track_id = feedback.track_id
                WHERE tracks.track_uuid IN ({uuid_slots})
                  AND feedback.preset_key IN ({key_slots})
                  AND feedback.analysis_family = ?
                """,
                (*clean_uuids, *clean_keys, analysis_family),
            ).fetchall()
        verdicts: dict[str, int] = {}
        conflicted: set[str] = set()
        for track_uuid, verdict in rows:
            stored = verdicts.get(track_uuid)
            if stored is not None and stored != int(verdict):
                conflicted.add(track_uuid)
            verdicts[track_uuid] = int(verdict)
        for track_uuid in conflicted:
            verdicts.pop(track_uuid, None)
        return verdicts

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
                    track_uuid
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
            "evaluation_profiles",
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

    def save_evaluation_profile(
        self,
        profile_name: str,
        profile: Mapping[str, Any],
    ) -> int:
        """Append an explicit score profile to optional Evaluation storage."""

        clean_name = _required_text(profile_name, "Evaluation profile name")
        profile_json = _json_text(_json_object(profile, "Evaluation profile"))
        with self._write_lock:
            connection = _required_evaluation_connection(self, create=True)
            with closing(connection), connection:
                cursor = connection.execute(
                    """
                    INSERT INTO evaluation_profiles(
                        profile_name, profile_json, created_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (clean_name, profile_json, _utc_timestamp()),
                )
                return int(cursor.lastrowid)

    def get_evaluation_profile(
        self,
        profile_name: str,
    ) -> dict[str, Any] | None:
        """Read the newest saved profile with an exact user-provided name."""

        clean_name = _required_text(profile_name, "Evaluation profile name")
        connection = self.connect_evaluation(create=False)
        if connection is None:
            return None
        with closing(connection):
            row = connection.execute(
                """
                SELECT profile_id, profile_name, profile_json, created_at
                FROM evaluation_profiles
                WHERE profile_name = ?
                ORDER BY profile_id DESC
                LIMIT 1
                """,
                (clean_name,),
            ).fetchone()
        if row is None:
            return None
        payload = _json_load(row["profile_json"], "Evaluation profile")
        if not isinstance(payload, dict):
            raise RuntimeError("Evaluation profile must contain a JSON object")
        return {
            "profile_id": int(row["profile_id"]),
            "profile_name": str(row["profile_name"]),
            "profile": payload,
            "created_at": str(row["created_at"]),
        }

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
                        track_uuid
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        (
                            session_id,
                            position,
                            snapshot["track_id"],
                            snapshot["track_uuid"],
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
                        total_score,
                        score_breakdown_json,
                        created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        clean_session_id,
                        clean_rank,
                        snapshot["track_id"],
                        snapshot["track_uuid"],
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

    def upsert_track_pair_feedback_exact(
        self,
        seed: TrackIdentity,
        candidate: TrackIdentity,
        rating: int,
        reason_tags: Sequence[str] = (),
        notes: str | None = None,
        source: str = "manual",
    ) -> int:
        """Atomically guard two current identities and persist their feedback.

        The identity predicates and the upsert execute in one SQLite statement.
        A scanner/content update therefore cannot land between a successful
        optimistic check and a numeric-id feedback write.
        """

        if not isinstance(seed, TrackIdentity):
            raise TypeError("seed must be a TrackIdentity")
        if not isinstance(candidate, TrackIdentity):
            raise TypeError("candidate must be a TrackIdentity")
        if (
            seed.catalog_uuid != self.catalog_uuid
            or candidate.catalog_uuid != self.catalog_uuid
        ):
            raise RuntimeError(
                "Track identity is stale; refresh the current catalog"
            )
        clean_rating = _rating(rating)
        reason_tags_json = _json_text(_clean_tags(reason_tags, "Reason tag"))
        clean_source = _required_text(source, "Pair feedback source")
        timestamp = _utc_timestamp()
        with (
            self._write_lock,
            closing(self.connect()) as connection,
        ):
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
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
                    SELECT ?, ?, ?, ?, ?, ?, ?, ?
                    WHERE EXISTS (
                        SELECT 1
                        FROM tracks
                        WHERE track_id = ?
                          AND track_uuid = ?
                          AND missing_since IS NULL
                    )
                      AND EXISTS (
                        SELECT 1
                        FROM tracks
                        WHERE track_id = ?
                          AND track_uuid = ?
                          AND missing_since IS NULL
                    )
                    ON CONFLICT(seed_track_id, candidate_track_id, source)
                    DO UPDATE SET
                        rating = excluded.rating,
                        reason_tags_json = excluded.reason_tags_json,
                        notes = excluded.notes,
                        updated_at = excluded.updated_at
                    """,
                    (
                        seed.track_id,
                        candidate.track_id,
                        clean_rating,
                        reason_tags_json,
                        notes,
                        clean_source,
                        timestamp,
                        timestamp,
                        seed.track_id,
                        seed.track_uuid,
                        candidate.track_id,
                        candidate.track_uuid,
                    ),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError(
                        "Track identity is stale; refresh the current catalog"
                    )
                row = connection.execute(
                    """
                    SELECT feedback_id
                    FROM pair_feedback
                    WHERE seed_track_id = ?
                      AND candidate_track_id = ?
                      AND source = ?
                    """,
                    (
                        seed.track_id,
                        candidate.track_id,
                        clean_source,
                    ),
                ).fetchone()
                if row is None:
                    raise RuntimeError(
                        "Failed to persist exact-identity pair feedback"
                    )
                connection.commit()
                return int(row["feedback_id"])
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise

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
        SELECT track_id, track_uuid
        FROM tracks
        WHERE track_id IN ({",".join("?" for _ in track_ids)})
        """,
        tuple(track_ids),
    ).fetchall()
    rows_by_track_id = {
        int(row["track_id"]): {
            "track_id": int(row["track_id"]),
            "track_uuid": str(row["track_uuid"]),
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


def _add_missing_columns(connection: sqlite3.Connection) -> None:
    """Give an older feedback table its columns, once, without a migration step.

    Verdicts are written on a click, so the write path is where a library first
    meets this table at all. Adding the columns here keeps that property: a
    library that predates one gains it on the next click, and its existing rows
    keep the defaults, which say exactly what they were — a whole example each.
    """

    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(text_preset_feedback)")
    }
    if "selection_size" not in columns:
        connection.execute(TEXT_PRESET_FEEDBACK_SELECTION_SIZE_DDL)
    if "weight" not in columns:
        connection.execute(TEXT_PRESET_FEEDBACK_WEIGHT_DDL)


def _preset_weights(
    keys: Sequence[str],
    preset_scores: Mapping[str, float] | None,
) -> dict[str, float]:
    """Split one click across the labels that shared it.

    With the search's per-label match to hand, the share follows it: a label
    that matched the track twice as well as its neighbour carries twice the
    example. Without it the click splits evenly, which is all that is known.
    Scores are cosines and can be negative or zero; a label that did not match
    at all still carries a floor, because a verdict was cast on a list it was
    part of and dropping it silently would misreport the pool size.
    """

    even = 1.0 / max(1, len(keys))
    if not preset_scores:
        return {key: even for key in keys}
    floor = 1e-6
    positive = {
        key: max(float(preset_scores.get(key, 0.0)), floor) for key in keys
    }
    total = sum(positive.values())
    if total <= 0.0:
        return {key: even for key in keys}
    return {key: value / total for key, value in positive.items()}


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
