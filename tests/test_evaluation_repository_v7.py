from __future__ import annotations

from contextlib import closing
import inspect
from pathlib import Path
import sqlite3
import threading

import pytest

from dj_track_similarity.db_evaluation import (
    EvaluationRepository,
    PROMOTED_SCORE_PROFILE_SETTING_KEY,
)
from dj_track_similarity import db_evaluation
from dj_track_similarity.db_evaluation_sidecar import (
    connect_evaluation_sidecar,
    validate_evaluation_sidecar_schema,
)
from dj_track_similarity.db_schema import insert_library_catalog, validate_core_schema
from dj_track_similarity.db_schema_v7 import create_v7_schema
from dj_track_similarity.db_storage import storage_database_paths


_CATALOG_UUID = "evaluation-v7-test-catalog"
_TIMESTAMP = "2026-07-23T12:00:00.000000Z"


class _EvaluationTestRepository(EvaluationRepository):
    def __init__(self, core_path: Path) -> None:
        self.path = core_path
        self.evaluation_path = storage_database_paths(core_path).evaluation
        self.catalog_uuid = _CATALOG_UUID
        self._write_lock = threading.RLock()

        create_v7_schema(str(core_path))
        with sqlite3.connect(core_path) as connection:
            insert_library_catalog(connection, self.catalog_uuid)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode=rw",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        validate_core_schema(
            connection,
            expected_catalog_uuid=self.catalog_uuid,
        )
        return connection

    def connect_evaluation(
        self,
        *,
        create: bool = False,
    ) -> sqlite3.Connection | None:
        return connect_evaluation_sidecar(
            self.evaluation_path,
            expected_catalog_uuid=self.catalog_uuid,
            create=create,
        )


def test_evaluation_reads_and_core_only_writes_do_not_create_sidecar(
    tmp_path: Path,
) -> None:
    repository = _EvaluationTestRepository(tmp_path / "library.sqlite")
    seed_id = _insert_track(repository, "seed")
    candidate_id = _insert_track(repository, "candidate")

    assert repository.list_search_sessions_with_events() == []
    assert repository.get_evaluation_setting("optimizer.state") is None
    assert repository.count_evaluation_rows() == {
        "pair_feedback": 0,
        "transition_feedback": 0,
        "search_sessions": 0,
        "search_session_seeds": 0,
        "search_result_events": 0,
        "calibration_runs": 0,
    }
    assert not repository.evaluation_path.exists()

    profile = {"name": "balanced", "weights": {"mert": 1.0}}
    assert repository.set_promoted_score_profile(profile) == profile
    pair_feedback_id = repository.upsert_track_pair_feedback(
        seed_id,
        candidate_id,
        3,
        reason_tags=("mixable",),
    )
    transition_feedback_id = repository.add_transition_feedback(
        seed_id,
        candidate_id,
        2,
        risk_tags=("energy",),
    )

    assert pair_feedback_id > 0
    assert transition_feedback_id > 0
    assert not repository.evaluation_path.exists()
    assert repository.get_promoted_score_profile() == profile
    assert repository.count_evaluation_rows()["pair_feedback"] == 1
    assert repository.count_evaluation_rows()["transition_feedback"] == 1

    with closing(repository.connect()) as connection:
        tables = _user_tables(connection)
        assert "pair_feedback" in tables
        assert "transition_feedback" in tables
        assert "search_sessions" not in tables
        assert "calibration_runs" not in tables
        assert "track_pair_feedback" not in tables
        stored_profile = connection.execute(
            """
            SELECT setting_value
            FROM library_settings
            WHERE setting_key = ?
            """,
            (PROMOTED_SCORE_PROFILE_SETTING_KEY,),
        ).fetchone()
        assert stored_profile is not None


def test_search_session_persists_track_uuid_and_generation_snapshots(
    tmp_path: Path,
) -> None:
    repository = _EvaluationTestRepository(tmp_path / "library.sqlite")
    seed_id = _insert_track(repository, "seed")
    candidate_id = _insert_track(repository, "candidate")

    session_id = repository.create_search_session(
        "evaluation_candidate_pool",
        (seed_id,),
        {"feedback_source": "manual"},
    )
    event_id = repository.record_search_result_event(
        session_id,
        candidate_id,
        rank=1,
        total_score=0.875,
        score_breakdown={"mert": {"rank": 1}},
    )
    assert repository.evaluation_path.is_file()

    with closing(repository.connect()) as connection, connection:
        connection.execute(
            """
            UPDATE tracks
            SET content_generation = content_generation + 1,
                updated_at = ?
            WHERE track_id IN (?, ?)
            """,
            (_TIMESTAMP, seed_id, candidate_id),
        )

    sessions = repository.list_search_sessions_with_events()
    assert sessions == [
        {
            "id": session_id,
            "mode": "evaluation_candidate_pool",
            "seed_track_ids": [seed_id],
            "seeds": [
                {
                    "position": 0,
                    "track_id": seed_id,
                    "track_uuid": "track-seed",
                    "content_generation": 1,
                }
            ],
            "request": {"feedback_source": "manual"},
            "created_at": sessions[0]["created_at"],
            "events": [
                {
                    "id": event_id,
                    "session_id": session_id,
                    "track_id": candidate_id,
                    "track_uuid": "track-candidate",
                    "content_generation": 1,
                    "rank": 1,
                    "total_score": 0.875,
                    "score_breakdown": {"mert": {"rank": 1}},
                    "created_at": sessions[0]["events"][0]["created_at"],
                }
            ],
        }
    ]

    with closing(repository.connect_evaluation()) as connection:
        assert connection is not None
        assert validate_evaluation_sidecar_schema(
            connection,
            expected_catalog_uuid=_CATALOG_UUID,
        ) == _CATALOG_UUID
        tables = _user_tables(connection)
        assert "search_sessions" in tables
        assert "search_session_seeds" in tables
        assert "search_result_events" in tables
        assert "pair_feedback" not in tables
        assert "transition_feedback" not in tables


def test_unknown_track_is_rejected_before_sidecar_creation(
    tmp_path: Path,
) -> None:
    repository = _EvaluationTestRepository(tmp_path / "library.sqlite")

    with pytest.raises(ValueError, match="does not exist"):
        repository.create_search_session("mert", (999,), {})

    assert not repository.evaluation_path.exists()


def test_calibration_setting_and_explicit_open_lazily_create_sidecar(
    tmp_path: Path,
) -> None:
    repository = _EvaluationTestRepository(tmp_path / "library.sqlite")

    calibration_id = repository.record_calibration_run(
        "manual-feedback",
        "hybrid",
        {"k": [5, 10]},
        {"precision_at_5": 0.5},
    )
    assert calibration_id > 0
    assert repository.evaluation_path.is_file()

    value = {"cursor": 4, "done": False}
    assert repository.set_evaluation_setting("optimizer.state", value) == value
    assert repository.get_evaluation_setting("optimizer.state") == value
    assert repository.count_evaluation_rows()["calibration_runs"] == 1

    second_repository = _EvaluationTestRepository(tmp_path / "second.sqlite")
    second_repository.open_evaluation_storage()
    assert second_repository.evaluation_path.is_file()


def test_evaluation_sidecar_requires_exact_catalog_and_schema(
    tmp_path: Path,
) -> None:
    repository = _EvaluationTestRepository(tmp_path / "library.sqlite")
    repository.open_evaluation_storage()

    with pytest.raises(RuntimeError, match="another library catalog"):
        connect_evaluation_sidecar(
            repository.evaluation_path,
            expected_catalog_uuid="wrong-catalog",
        )

    with sqlite3.connect(repository.evaluation_path) as connection:
        connection.execute("CREATE TABLE unexpected_table(value TEXT)")

    with pytest.raises(RuntimeError, match="table set mismatch"):
        repository.connect_evaluation()


def test_storage_metadata_binding_is_immutable(tmp_path: Path) -> None:
    repository = _EvaluationTestRepository(tmp_path / "library.sqlite")
    repository.open_evaluation_storage()

    with sqlite3.connect(repository.evaluation_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """
                UPDATE storage_metadata
                SET catalog_uuid = 'other'
                WHERE singleton_id = 1
                """
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                """
                INSERT OR REPLACE INTO storage_metadata(
                    singleton_id,
                    catalog_uuid,
                    schema_version,
                    created_at,
                    updated_at
                )
                VALUES (1, 'other', 1, ?, ?)
                """,
                (_TIMESTAMP, _TIMESTAMP),
            )


def test_evaluation_json_is_local_canonical_and_strict(tmp_path: Path) -> None:
    repository = _EvaluationTestRepository(tmp_path / "library.sqlite")

    value = {
        "z": (2, 1),
        "a": {"enabled": True, "score": 0.5},
    }
    assert repository.set_evaluation_setting("canonical", value) == {
        "a": {"enabled": True, "score": 0.5},
        "z": [2, 1],
    }
    with closing(repository.connect_evaluation()) as connection:
        assert connection is not None
        raw_json = connection.execute(
            """
            SELECT value_json
            FROM evaluation_settings
            WHERE setting_key = 'canonical'
            """
        ).fetchone()[0]
    assert raw_json == '{"a":{"enabled":true,"score":0.5},"z":[2,1]}'

    with pytest.raises(ValueError, match="finite"):
        repository.set_evaluation_setting("not-finite", {"score": float("inf")})
    with pytest.raises(TypeError, match="keys must be strings"):
        repository.set_evaluation_setting("bad-key", {1: "value"})
    with pytest.raises(TypeError, match="unsupported JSON value type"):
        repository.set_evaluation_setting("unsupported", {"value": object()})

    source = inspect.getsource(db_evaluation)
    assert "metadata_payload" not in source
    assert "json_safe_value" not in source


def _insert_track(
    repository: _EvaluationTestRepository,
    suffix: str,
) -> int:
    with closing(repository.connect()) as connection, connection:
        cursor = connection.execute(
            """
            INSERT INTO tracks(
                track_uuid,
                file_path,
                file_size_bytes,
                file_modified_ns,
                content_generation,
                last_scanned_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                f"track-{suffix}",
                str(repository.path.with_name(f"{suffix}.wav")),
                100,
                1_000,
                _TIMESTAMP,
                _TIMESTAMP,
                _TIMESTAMP,
            ),
        )
        return int(cursor.lastrowid)


def _user_tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }
