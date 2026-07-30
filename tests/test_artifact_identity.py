from __future__ import annotations

import sqlite3
import threading
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Iterator

import numpy as np
import pytest

from dj_track_similarity import db_artifacts as artifact_module
from dj_track_similarity.analysis_models import (
    EmbeddingOutput,
    MERT_EMBEDDING_DIM,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_artifacts import (
    ArtifactTrackIdentity,
    create_artifacts_sidecar_schema,
    current_track_identity,
    read_valid_embedding,
    validate_embedding_row_payload,
    validate_storage_binding,
    write_valid_embedding,
    write_valid_embedding_in_transaction,
)
from dj_track_similarity.db_ddl import create_core_schema


CATALOG_UUID = "11111111-2222-3333-4444-555555555555"
OTHER_CATALOG_UUID = "99999999-8888-7777-6666-555555555555"
TRACK_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ANALYZED_AT = "2026-07-30T00:00:00.000000Z"


@contextmanager
def _bound_bundle(
    *,
    artifacts_catalog_uuid: str = CATALOG_UUID,
) -> Iterator[tuple[sqlite3.Connection, sqlite3.Connection]]:
    core = sqlite3.connect(":memory:")
    artifacts = sqlite3.connect(":memory:")
    core.row_factory = sqlite3.Row
    artifacts.row_factory = sqlite3.Row
    core.execute("PRAGMA foreign_keys = ON")
    artifacts.execute("PRAGMA foreign_keys = ON")
    create_core_schema(core)
    create_artifacts_sidecar_schema(
        artifacts,
        catalog_uuid=artifacts_catalog_uuid,
    )
    core.execute(
        """
        INSERT INTO library_catalog(
            singleton_id, catalog_uuid, created_at, updated_at
        ) VALUES (1, ?, ?, ?)
        """,
        (CATALOG_UUID, ANALYZED_AT, ANALYZED_AT),
    )
    core.execute(
        """
        INSERT INTO tracks(
            track_id, track_uuid, file_path, file_size_bytes, file_modified_ns,
            content_generation, last_scanned_at, created_at, updated_at
        ) VALUES (1, ?, 'C:/music/track.wav', 100, 1000, 1, ?, ?, ?)
        """,
        (TRACK_UUID, ANALYZED_AT, ANALYZED_AT, ANALYZED_AT),
    )
    core.commit()
    try:
        yield core, artifacts
    finally:
        artifacts.close()
        core.close()


def _track(**changes: object) -> ArtifactTrackIdentity:
    values: dict[str, object] = {
        "catalog_uuid": CATALOG_UUID,
        "track_id": 1,
        "track_uuid": TRACK_UUID,
        "content_generation": 1,
    }
    values.update(changes)
    return ArtifactTrackIdentity(**values)  # type: ignore[arg-type]


def _mert_vector(*, index: int = 0) -> np.ndarray:
    vector = np.zeros(MERT_EMBEDDING_DIM, dtype=np.float32)
    vector[index] = 1.0
    return vector


def test_embedding_output_validates_current_family_dimension_without_contract() -> None:
    output = EmbeddingOutput(
        family="mert",
        vector=_mert_vector(),
        analyzed_at=ANALYZED_AT,
    )

    assert output.family == "mert"
    assert output.vector.shape == (MERT_EMBEDDING_DIM,)
    assert not hasattr(output, "contract")


def test_fresh_storage_has_no_contract_identity_schema() -> None:
    with _bound_bundle() as (core, artifacts):
        core_tables = {
            str(row[0])
            for row in core.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "contracts" not in core_tables
        for table in ("sonara", "maest_scores", "classifier_scores"):
            columns = {
                str(row[1]) for row in core.execute(f'PRAGMA table_info("{table}")')
            }
            assert "contract_hash" not in columns
            assert "release_hash" not in columns
            assert "model_version" not in columns

        for table in (
            "maest_embeddings",
            "mert_embeddings",
            "muq_embeddings",
            "clap_embeddings",
            "sonara_similarity_embeddings",
            "sonara_timeline",
            "sonara_fingerprints",
        ):
            columns = {
                str(row[1])
                for row in artifacts.execute(f'PRAGMA table_info("{table}")')
            }
            assert "contract_hash" not in columns


@pytest.mark.parametrize(
    "family",
    ("maest", "mert", "muq", "clap", "sonara"),
)
def test_embedding_gateway_round_trip_uses_data_identity(family: str) -> None:
    dimensions = {
        "maest": 768,
        "mert": 768,
        "muq": 1024,
        "clap": 512,
        "sonara": 48,
    }
    vector = np.zeros(dimensions[family], dtype=np.float32)
    vector[0] = 1.0
    if family == "sonara":
        vector[1] = 0.25
    with _bound_bundle() as (core, artifacts):
        write_valid_embedding(
            core_connection=core,
            artifacts_connection=artifacts,
            track=_track(),
            family=family,
            embedding=vector,
            analyzed_at=ANALYZED_AT,
        )

        restored = read_valid_embedding(
            family=family,
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
        )

    assert restored is not None
    np.testing.assert_array_equal(restored, vector)


def test_storage_binding_rejects_artifacts_from_another_catalog() -> None:
    with _bound_bundle(artifacts_catalog_uuid=OTHER_CATALOG_UUID) as (
        core,
        artifacts,
    ):
        with pytest.raises(RuntimeError, match="another library catalog"):
            validate_storage_binding(core, artifacts)


def test_embedding_reader_rejects_artifacts_from_another_catalog() -> None:
    with _bound_bundle(artifacts_catalog_uuid=OTHER_CATALOG_UUID) as (
        core,
        artifacts,
    ):
        with pytest.raises(RuntimeError, match="another library catalog"):
            read_valid_embedding(
                family="mert",
                track_id=1,
                core_connection=core,
                artifacts_connection=artifacts,
            )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("catalog_uuid", OTHER_CATALOG_UUID, "catalog_uuid"),
        ("track_uuid", "ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb", "track_uuid"),
        ("content_generation", 2, "content_generation"),
    ),
)
def test_embedding_writer_rejects_stale_track_identity_before_insert(
    field: str,
    value: object,
    message: str,
) -> None:
    with _bound_bundle() as (core, artifacts):
        with pytest.raises(RuntimeError, match=message):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=_track(**{field: value}),
                family="mert",
                embedding=_mert_vector(),
                analyzed_at=ANALYZED_AT,
            )
        assert artifacts.execute(
            "SELECT COUNT(*) FROM mert_embeddings"
        ).fetchone()[0] == 0


@pytest.mark.parametrize(
    "vector",
    (
        np.full(MERT_EMBEDDING_DIM, np.nan, dtype=np.float32),
        np.full(MERT_EMBEDDING_DIM, np.inf, dtype=np.float32),
        np.zeros(MERT_EMBEDDING_DIM, dtype=np.float32),
        np.full(MERT_EMBEDDING_DIM, 1.0, dtype=np.float32),
    ),
)
def test_embedding_writer_rejects_nonfinite_or_nonunit_vectors(
    vector: np.ndarray,
) -> None:
    with _bound_bundle() as (core, artifacts):
        with pytest.raises(ValueError):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=_track(),
                family="mert",
                embedding=vector,
                analyzed_at=ANALYZED_AT,
            )


def test_embedding_writer_rejects_wrong_current_family_dimension() -> None:
    with _bound_bundle() as (core, artifacts):
        with pytest.raises(ValueError, match="mert dimension"):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=_track(),
                family="mert",
                embedding=np.ones(MERT_EMBEDDING_DIM - 1, dtype=np.float32),
                analyzed_at=ANALYZED_AT,
            )


@pytest.mark.parametrize(
    ("column", "value"),
    (
        ("track_uuid", "ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb"),
        ("content_generation", 2),
    ),
)
def test_embedding_reader_fails_closed_on_corrupt_track_identity(
    column: str,
    value: object,
) -> None:
    with _bound_bundle() as (core, artifacts):
        write_valid_embedding(
            core_connection=core,
            artifacts_connection=artifacts,
            track=_track(),
            family="mert",
            embedding=_mert_vector(),
            analyzed_at=ANALYZED_AT,
        )
        artifacts.execute(
            f"UPDATE mert_embeddings SET {column} = ? WHERE track_id = 1",
            (value,),
        )
        artifacts.commit()

        restored = read_valid_embedding(
            family="mert",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
        )

    assert restored is None


def test_embedding_reader_fails_closed_on_wrong_blob_length() -> None:
    with _bound_bundle() as (core, artifacts):
        write_valid_embedding(
            core_connection=core,
            artifacts_connection=artifacts,
            track=_track(),
            family="mert",
            embedding=_mert_vector(),
            analyzed_at=ANALYZED_AT,
        )
        artifacts.execute("PRAGMA ignore_check_constraints = ON")
        blob = _mert_vector().tobytes(order="C")[:-1]
        artifacts.execute(
            "UPDATE mert_embeddings SET embedding_blob = ? WHERE track_id = 1",
            (blob,),
        )
        artifacts.commit()

        restored = read_valid_embedding(
            family="mert",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
        )

    assert restored is None


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    (
        ("track_id", None),
        ("track_id", "not-an-integer"),
        ("content_generation", None),
        ("content_generation", "not-an-integer"),
        ("dim", None),
        ("dim", "not-an-integer"),
    ),
)
def test_embedding_row_bad_numeric_fields_fail_closed(
    field_name: str,
    bad_value: object,
) -> None:
    row: dict[str, object] = {
        "track_id": 1,
        "track_uuid": TRACK_UUID,
        "content_generation": 1,
        "dim": MERT_EMBEDDING_DIM,
        "normalization": "l2",
        "embedding_blob": _mert_vector().tobytes(order="C"),
    }
    row[field_name] = bad_value

    valid, reason = validate_embedding_row_payload(
        family="mert",
        row=row,
        expected_track=_track(),
    )

    assert valid is False
    assert reason


@pytest.mark.parametrize(
    ("column", "bad_value"),
    (
        ("content_generation", "not-an-integer"),
        ("dim", "not-an-integer"),
    ),
)
def test_embedding_reader_fails_closed_on_bad_numeric_fields(
    column: str,
    bad_value: object,
) -> None:
    with _bound_bundle() as (core, artifacts):
        write_valid_embedding(
            core_connection=core,
            artifacts_connection=artifacts,
            track=_track(),
            family="mert",
            embedding=_mert_vector(),
            analyzed_at=ANALYZED_AT,
        )
        artifacts.execute("PRAGMA ignore_check_constraints = ON")
        artifacts.execute(
            f"UPDATE mert_embeddings SET {column} = ? WHERE track_id = 1",
            (bad_value,),
        )
        artifacts.commit()

        restored = read_valid_embedding(
            family="mert",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
        )

    assert restored is None


@pytest.mark.parametrize(
    "vector",
    (
        np.full(MERT_EMBEDDING_DIM, np.nan, dtype=np.float32),
        np.full(MERT_EMBEDDING_DIM, np.inf, dtype=np.float32),
        np.full(MERT_EMBEDDING_DIM, 1.0, dtype=np.float32),
    ),
)
def test_embedding_reader_fails_closed_on_invalid_l2_payload(
    vector: np.ndarray,
) -> None:
    with _bound_bundle() as (core, artifacts):
        write_valid_embedding(
            core_connection=core,
            artifacts_connection=artifacts,
            track=_track(),
            family="mert",
            embedding=_mert_vector(),
            analyzed_at=ANALYZED_AT,
        )
        artifacts.execute(
            "UPDATE mert_embeddings SET embedding_blob = ? WHERE track_id = 1",
            (vector.astype("<f4", copy=False).tobytes(order="C"),),
        )
        artifacts.commit()

        restored = read_valid_embedding(
            family="mert",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
        )

    assert restored is None


def test_sonara_none_normalization_preserves_finite_nonunit_vector() -> None:
    vector = np.zeros(48, dtype=np.float32)
    vector[:4] = (1.0, 2.0, 3.0, 4.0)
    with _bound_bundle() as (core, artifacts):
        write_valid_embedding(
            core_connection=core,
            artifacts_connection=artifacts,
            track=_track(),
            family="sonara",
            embedding=vector,
            analyzed_at=ANALYZED_AT,
        )
        restored = read_valid_embedding(
            family="sonara",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
        )

    assert restored is not None
    np.testing.assert_array_equal(restored, vector)


def test_in_transaction_gateway_requires_both_transactions() -> None:
    with _bound_bundle() as (core, artifacts):
        with pytest.raises(RuntimeError, match="Core transaction"):
            write_valid_embedding_in_transaction(
                core_connection=core,
                artifacts_connection=artifacts,
                track=_track(),
                family="mert",
                embedding=_mert_vector(),
                analyzed_at=ANALYZED_AT,
            )

        core.execute("BEGIN IMMEDIATE")
        with pytest.raises(RuntimeError, match="Artifacts transaction"):
            write_valid_embedding_in_transaction(
                core_connection=core,
                artifacts_connection=artifacts,
                track=_track(),
                family="mert",
                embedding=_mert_vector(),
                analyzed_at=ANALYZED_AT,
            )
        core.rollback()


def test_in_transaction_gateway_preserves_ownership_and_caller_rollback() -> None:
    with _bound_bundle() as (core, artifacts):
        core.execute("BEGIN IMMEDIATE")
        artifacts.execute("BEGIN IMMEDIATE")

        write_valid_embedding_in_transaction(
            core_connection=core,
            artifacts_connection=artifacts,
            track=_track(),
            family="mert",
            embedding=_mert_vector(),
            analyzed_at=ANALYZED_AT,
        )

        assert core.in_transaction
        assert artifacts.in_transaction
        assert artifacts.execute(
            "SELECT COUNT(*) FROM mert_embeddings"
        ).fetchone()[0] == 1
        artifacts.rollback()
        core.rollback()
        assert artifacts.execute(
            "SELECT COUNT(*) FROM mert_embeddings"
        ).fetchone()[0] == 0


def test_older_interleaved_writer_cannot_overwrite_newer_generation_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    old_vector = _mert_vector(index=0)
    current_vector = _mert_vector(index=1)

    with closing(database.connect()) as core:
        core.execute(
            """
            INSERT INTO tracks(
                track_id, track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (1, ?, 'C:/music/track.wav', 100, 1000, 1, ?, ?, ?)
            """,
            (TRACK_UUID, ANALYZED_AT, ANALYZED_AT, ANALYZED_AT),
        )
        core.commit()
    with (
        closing(database.connect()) as core,
        closing(database.connect_artifacts()) as artifacts,
    ):
        stale_track = current_track_identity(core, artifacts, 1)
    assert stale_track is not None

    stale_validated = threading.Event()
    release_stale_writer = threading.Event()
    generation_attempting = threading.Event()
    generation_committed = threading.Event()
    current_artifact_written = threading.Event()
    errors: list[BaseException] = []
    original_validate = artifact_module._validate_current_track_identity

    def pause_stale_writer_after_validation(
        core_connection: sqlite3.Connection,
        artifacts_connection: sqlite3.Connection,
        expected: ArtifactTrackIdentity,
        *,
        storage_binding: artifact_module.StorageBindingProof | None = None,
    ) -> tuple[bool, str | None]:
        result = original_validate(
            core_connection,
            artifacts_connection,
            expected,
            storage_binding=storage_binding,
        )
        if (
            threading.current_thread().name == "stale-artifact-writer"
            and expected.content_generation == 1
        ):
            assert result[0]
            stale_validated.set()
            if not release_stale_writer.wait(timeout=5):
                raise TimeoutError("timed out waiting to release stale writer")
        return result

    monkeypatch.setattr(
        artifact_module,
        "_validate_current_track_identity",
        pause_stale_writer_after_validation,
    )

    def stale_writer() -> None:
        try:
            with (
                closing(database.connect()) as core,
                closing(database.connect_artifacts()) as artifacts,
            ):
                write_valid_embedding(
                    core_connection=core,
                    artifacts_connection=artifacts,
                    track=stale_track,
                    family="mert",
                    embedding=old_vector,
                    analyzed_at=ANALYZED_AT,
                )
        except BaseException as error:
            errors.append(error)

    def generation_writer() -> None:
        try:
            with closing(database.connect()) as core:
                generation_attempting.set()
                core.execute("BEGIN IMMEDIATE")
                core.execute(
                    """
                    UPDATE tracks
                    SET content_generation = 2, updated_at = ?
                    WHERE track_id = 1
                    """,
                    (ANALYZED_AT,),
                )
                core.commit()
                generation_committed.set()
            with (
                closing(database.connect()) as core,
                closing(database.connect_artifacts()) as artifacts,
            ):
                current_track = current_track_identity(core, artifacts, 1)
                assert current_track is not None
                write_valid_embedding(
                    core_connection=core,
                    artifacts_connection=artifacts,
                    track=current_track,
                    family="mert",
                    embedding=current_vector,
                    analyzed_at=ANALYZED_AT,
                )
                current_artifact_written.set()
        except BaseException as error:
            errors.append(error)

    stale_thread = threading.Thread(
        target=stale_writer,
        name="stale-artifact-writer",
    )
    generation_thread = threading.Thread(
        target=generation_writer,
        name="generation-writer",
    )
    stale_thread.start()
    try:
        assert stale_validated.wait(timeout=5)
        generation_thread.start()
        assert generation_attempting.wait(timeout=5)
        assert not generation_committed.wait(timeout=0.1)
    finally:
        release_stale_writer.set()
        stale_thread.join(timeout=5)
        if generation_thread.ident is not None:
            generation_thread.join(timeout=5)

    assert not stale_thread.is_alive()
    assert not generation_thread.is_alive()
    assert errors == []
    assert generation_committed.is_set()
    assert current_artifact_written.is_set()
    with (
        closing(database.connect()) as core,
        closing(database.connect_artifacts()) as artifacts,
    ):
        row = artifacts.execute(
            """
            SELECT content_generation, embedding_blob
            FROM mert_embeddings
            WHERE track_id = 1
            """
        ).fetchone()
        restored = read_valid_embedding(
            family="mert",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
        )

    assert row is not None
    assert int(row["content_generation"]) == 2
    np.testing.assert_array_equal(
        np.frombuffer(row["embedding_blob"], dtype="<f4"),
        current_vector,
    )
    assert restored is not None
    np.testing.assert_array_equal(restored, current_vector)
