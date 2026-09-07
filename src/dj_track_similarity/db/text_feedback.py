"""Exact-query verdict storage, reached through LibraryDatabase."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Mapping, Sequence
from contextlib import closing
from typing import Any

from .connection import connect_database_read_only
from .ddl import TEXT_SEARCH_FEEDBACK_DDL
from .schema import _utc_timestamp, validate_library_schema


class TextFeedbackSchemaError(RuntimeError):
    """The explicit text feedback schema upgrade is required."""


class TextFeedbackConflict(RuntimeError):
    def __init__(self, current: dict[str, Any]) -> None:
        super().__init__("Text feedback revision conflict")
        self.current = current


def _normalized_ddl(sql: str) -> str:
    return re.sub(r"\s+", "", sql).rstrip(";").lower()


def text_feedback_capability(connection: sqlite3.Connection) -> str:
    """Validate the versioned shape, including constraints, without any DDL."""
    row = connection.execute(
        "SELECT type, sql FROM sqlite_schema WHERE name = 'text_search_feedback'"
    ).fetchone()
    if row is None:
        return "absent"
    kind, sql = row
    if (
        kind != "table"
        or not sql
        or _normalized_ddl(sql) != _normalized_ddl(TEXT_SEARCH_FEEDBACK_DDL)
    ):
        return "incompatible"
    return "ready"


def _require_ready(connection: sqlite3.Connection) -> None:
    capability = text_feedback_capability(connection)
    if capability != "ready":
        raise TextFeedbackSchemaError(f"Text feedback schema is {capability}")


class TextFeedbackRepository:
    def text_feedback_capability(self) -> str:
        with closing(connect_database_read_only(self.path)) as connection:
            validate_library_schema(connection, expected_catalog_uuid=self.catalog_uuid)
            return text_feedback_capability(connection)

    def record_text_query_feedback(
        self,
        context: Mapping[str, Any],
        run: Mapping[str, Any],
        track_uuid: str,
        verdict: int,
        expected_revision: int,
    ) -> dict[str, Any]:
        from ..text_search_models import canonical_json, query_context_key, validate_query_context

        if type(verdict) is not int or verdict not in (-1, 0, 1):
            raise ValueError("Verdict must be -1, 0 or 1")
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected revision must be a nonnegative integer")
        if not isinstance(track_uuid, str) or not track_uuid.strip():
            raise ValueError("Track UUID is required")
        context = validate_query_context(context)
        context_json = canonical_json(context)
        query_key = query_context_key(context)
        if context.get("catalog_uuid") != self.catalog_uuid:
            raise ValueError("Query context belongs to another catalog")
        if (
            run.get("query_key") != query_key
            or run.get("analysis_family") != context.get("analysis_family")
            or not isinstance(run.get("run_id"), str)
            or not run["run_id"]
            or not isinstance(run.get("executed_at"), str)
            or not run["executed_at"]
            or type(run.get("rank")) is not int
            or run["rank"] < 1
        ):
            raise ValueError("Malformed or mismatched text search run")
        run_json = canonical_json({key: run[key] for key in (
            "run_id", "query_key", "analysis_family", "executed_at", "rank",
            "mode", "comparison_id", "eligible_count", "eligibility_digest", "feedback",
            "code_revision", "device", "limit",
        ) if key in run})
        timestamp = _utc_timestamp()
        with self._write_lock, closing(self.connect()) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            _require_ready(connection)
            track = connection.execute(
                "SELECT track_id FROM tracks WHERE track_uuid=? AND missing_since IS NULL",
                (track_uuid,),
            ).fetchone()
            if track is None:
                raise KeyError(f"Unknown or missing track UUID: {track_uuid}")
            stored = connection.execute(
                "SELECT 1 FROM text_search_feedback "
                "WHERE query_key=? AND context_json != ? LIMIT 1",
                (query_key, context_json),
            ).fetchone()
            if stored is not None:
                raise ValueError("Query key collision with an immutable context")
            row = connection.execute(
                "SELECT verdict, revision, updated_at FROM text_search_feedback "
                "WHERE query_key=? AND track_id=?", (query_key, track[0]),
            ).fetchone()
            current = dict(row) if row else {"verdict": 0, "revision": 0, "updated_at": None}
            if row is not None and current["verdict"] == verdict:
                return current
            if current["revision"] != expected_revision:
                raise TextFeedbackConflict(current)
            revision = current["revision"] + 1
            connection.execute(
                "INSERT INTO text_search_feedback (query_key, track_id, context_json, "
                "verdict, revision, created_at, updated_at, last_run_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(query_key, track_id) DO UPDATE SET "
                "verdict=excluded.verdict, revision=excluded.revision, "
                "updated_at=excluded.updated_at, last_run_json=excluded.last_run_json",
                (query_key, track[0], context_json, verdict, revision, timestamp, timestamp, run_json),
            )
            return {"verdict": verdict, "revision": revision, "updated_at": timestamp}

    def read_text_query_feedback(
        self, query_key: str, track_uuids: Sequence[str]
    ) -> dict[str, dict[str, int]]:
        result: dict[str, dict[str, int]] = {}
        with closing(connect_database_read_only(self.path)) as connection:
            validate_library_schema(connection, expected_catalog_uuid=self.catalog_uuid)
            _require_ready(connection)
            for start in range(0, len(track_uuids), 500):
                chunk = track_uuids[start:start + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    "SELECT t.track_uuid, f.verdict, f.revision FROM text_search_feedback f "
                    "JOIN tracks t ON t.track_id=f.track_id WHERE f.query_key=? "
                    f"AND t.track_uuid IN ({placeholders}) AND t.missing_since IS NULL",
                    (query_key, *chunk),
                ).fetchall()
                for row in rows:
                    result[row[0]] = {"verdict": row[1], "revision": row[2]}
        return result

    def list_text_query_feedback_tracks(self, query_key: str) -> dict[str, Any]:
        from ..text_search_models import canonical_json

        with closing(connect_database_read_only(self.path)) as connection:
            validate_library_schema(connection, expected_catalog_uuid=self.catalog_uuid)
            _require_ready(connection)
            rows = connection.execute(
                "SELECT t.track_id, t.track_uuid, f.verdict, f.revision "
                "FROM text_search_feedback f JOIN tracks t ON t.track_id=f.track_id "
                "WHERE f.query_key=? AND t.missing_since IS NULL ORDER BY t.track_uuid",
                (query_key,),
            ).fetchall()
        identities = [[row[1], row[2], row[3]] for row in rows]
        return {
            "relevant": [row[0] for row in rows if row[2] == 1],
            "irrelevant": [row[0] for row in rows if row[2] == -1],
            "history_revision": hashlib.sha256(canonical_json(identities).encode()).hexdigest(),
            "judgements": {
                row[0]: {"track_uuid": row[1], "verdict": row[2], "revision": row[3]}
                for row in rows
            },
        }
