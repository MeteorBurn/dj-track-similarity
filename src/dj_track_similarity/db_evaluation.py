from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from typing import Any

from .metadata_payload import json_safe_value


class EvaluationRepository:
    def create_search_session(self, mode: str, seed_track_ids: Sequence[int], request: Mapping[str, Any]) -> int:
        clean_mode = _required_text(mode, "Search session mode")
        seed_track_ids_json = _json_text([_positive_int(track_id, "Seed track id") for track_id in seed_track_ids])
        request_json = _json_text(dict(request))
        with self._write_lock, self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO search_sessions (mode, seed_track_ids_json, request_json)
                VALUES (?, ?, ?)
                """,
                (clean_mode, seed_track_ids_json, request_json),
            )
            return int(cursor.lastrowid)

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
        clean_total_score = _finite_float(total_score, "Search result total score")
        score_breakdown_json = _json_text(dict(score_breakdown))
        with self._write_lock, self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO search_result_events (
                    session_id, track_id, rank, total_score, score_breakdown_json
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (clean_session_id, clean_track_id, clean_rank, clean_total_score, score_breakdown_json),
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
        clean_seed_track_id = _positive_int(seed_track_id, "Seed track id")
        clean_candidate_track_id = _positive_int(candidate_track_id, "Candidate track id")
        clean_rating = _rating(rating)
        reason_tags_json = _json_text(_clean_tags(reason_tags, "Reason tag"))
        clean_source = _required_text(source, "Track pair feedback source")
        with self._write_lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO track_pair_feedback (
                    seed_track_id, candidate_track_id, rating, reason_tags_json, notes, source
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(seed_track_id, candidate_track_id, source) DO UPDATE SET
                    rating = excluded.rating,
                    reason_tags_json = excluded.reason_tags_json,
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    clean_seed_track_id,
                    clean_candidate_track_id,
                    clean_rating,
                    reason_tags_json,
                    notes,
                    clean_source,
                ),
            )
            row = connection.execute(
                """
                SELECT id
                FROM track_pair_feedback
                WHERE seed_track_id = ? AND candidate_track_id = ? AND source = ?
                """,
                (clean_seed_track_id, clean_candidate_track_id, clean_source),
            ).fetchone()
        if row is None:
            raise RuntimeError("Failed to upsert track pair feedback")
        return int(row["id"])

    def add_transition_feedback(
        self,
        outgoing_track_id: int,
        incoming_track_id: int,
        rating: int,
        risk_tags: Sequence[str] = (),
        notes: str | None = None,
        source: str = "manual",
    ) -> int:
        clean_outgoing_track_id = _positive_int(outgoing_track_id, "Outgoing track id")
        clean_incoming_track_id = _positive_int(incoming_track_id, "Incoming track id")
        clean_rating = _rating(rating)
        risk_tags_json = _json_text(_clean_tags(risk_tags, "Risk tag"))
        clean_source = _required_text(source, "Transition feedback source")
        with self._write_lock, self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO transition_feedback (
                    outgoing_track_id, incoming_track_id, rating, risk_tags_json, notes, source
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_outgoing_track_id,
                    clean_incoming_track_id,
                    clean_rating,
                    risk_tags_json,
                    notes,
                    clean_source,
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
        clean_profile_name = _required_text(profile_name, "Calibration profile name")
        clean_search_mode = _required_text(search_mode, "Calibration search mode")
        config_json = _json_text(dict(config))
        metrics_json = _json_text(dict(metrics))
        with self._write_lock, self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO calibration_runs (profile_name, search_mode, config_json, metrics_json)
                VALUES (?, ?, ?, ?)
                """,
                (clean_profile_name, clean_search_mode, config_json, metrics_json),
            )
            return int(cursor.lastrowid)


def _json_text(value: object) -> str:
    return json.dumps(json_safe_value(value), ensure_ascii=False, sort_keys=True, allow_nan=False)


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


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a non-negative integer")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a non-negative integer") from error
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
        raise ValueError("Rating must be an integer between 0 and 3") from error
    if clean_value < 0 or clean_value > 3:
        raise ValueError("Rating must be an integer between 0 and 3")
    return clean_value


def _clean_tags(tags: Sequence[str], field_name: str) -> list[str]:
    if isinstance(tags, str):
        raise TypeError(f"{field_name} list must be a sequence of strings, not a string")
    return [text for tag in tags if (text := str(tag).strip())]
