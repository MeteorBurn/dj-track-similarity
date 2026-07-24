from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity import db_artifacts as artifact_module
from dj_track_similarity.analysis_contracts import (
    ContractIdentity,
    ContractIdentityError,
    ContractRegistryError,
    read_registered_contract,
    register_contract,
    require_registered_contract,
)
from dj_track_similarity.db_artifacts import (
    ArtifactTrackIdentity,
    create_artifacts_sidecar_schema,
    current_track_identity,
    read_valid_embedding,
    validate_sidecar_row,
    validate_storage_binding,
    write_valid_embedding,
    write_valid_embedding_in_transaction,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_schema_v7 import create_v7_schema


CATALOG_UUID = "11111111-2222-3333-4444-555555555555"
OTHER_CATALOG_UUID = "99999999-8888-7777-6666-555555555555"
TRACK_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OTHER_TRACK_UUID = "ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb"
ANALYZED_AT = "2026-07-23T00:00:00.000000Z"
EMBEDDING_TABLES = {
    "maest": "maest_embeddings",
    "mert": "mert_embeddings",
    "muq": "muq_embeddings",
    "clap": "clap_embeddings",
    "sonara": "sonara_similarity_embeddings",
}


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
    create_v7_schema(core)
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


def _mert_identity(
    *,
    model_name: str = "m-a-p/MERT-v1-95M",
    model_version: str = "revision-1",
    checkpoint_id: str = "sha256:checkpoint",
    preprocessing: str = "mono-24khz-window-v1",
    dim: int = 4,
    encoding: str = "float32-le",
    normalization: str = "l2",
    parameters: dict[str, object] | None = None,
) -> ContractIdentity:
    return ContractIdentity(
        analysis_family="mert",
        output_kind="embedding",
        model_name=model_name,
        model_version=model_version,
        checkpoint_id=checkpoint_id,
        preprocessing=preprocessing,
        dim=dim,
        encoding=encoding,
        normalization=normalization,
        parameters=parameters or {"window_seconds": 5.0, "max_windows": 12},
    )


def _embedding_identity(
    family: str,
    *,
    dim: int = 4,
    normalization: str = "l2",
) -> ContractIdentity:
    return ContractIdentity(
        analysis_family=family,
        output_kind="embedding",
        model_name=f"{family}-model",
        model_version="revision-1",
        release_hash="sha256:sonara-release" if family == "sonara" else None,
        checkpoint_id="sha256:checkpoint",
        preprocessing="mono-window-v1",
        dim=dim,
        encoding="float32-le",
        normalization=normalization,
        parameters={"window_seconds": 5.0},
    )


def _required_track(
    core: sqlite3.Connection,
    artifacts: sqlite3.Connection,
) -> ArtifactTrackIdentity:
    track = current_track_identity(core, artifacts, 1)
    assert track is not None
    return track


def _embedding_row(
    track: ArtifactTrackIdentity,
    contract: ContractIdentity,
    vector: np.ndarray | None = None,
) -> dict[str, object]:
    embedding = (
        np.asarray([0.0, 0.6, 0.0, 0.8], dtype="<f4")
        if vector is None
        else np.asarray(vector, dtype="<f4")
    )
    return {
        "track_id": track.track_id,
        "track_uuid": track.track_uuid,
        "content_generation": track.content_generation,
        "contract_hash": contract.contract_hash,
        "dim": contract.dim,
        "normalization": contract.normalization,
        "embedding_blob": embedding.tobytes(order="C"),
    }


def _insert_embedding_row(
    artifacts: sqlite3.Connection,
    *,
    family: str,
    row: Mapping[str, object],
) -> None:
    artifacts.execute(
        f"""
        INSERT INTO {EMBEDDING_TABLES[family]} (
            track_id, track_uuid, content_generation, contract_hash,
            dim, normalization, embedding_blob, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["track_id"],
            row["track_uuid"],
            row["content_generation"],
            row["contract_hash"],
            row["dim"],
            row["normalization"],
            row["embedding_blob"],
            ANALYZED_AT,
        ),
    )


def test_contract_identity_round_trips_through_one_canonical_payload() -> None:
    identity = _mert_identity()

    reconstructed = ContractIdentity.from_canonical_payload_json(
        identity.canonical_payload_json
    )

    assert reconstructed.canonical_payload_json == identity.canonical_payload_json
    assert reconstructed.contract_hash == identity.contract_hash
    assert identity.contract_hash.startswith("sha256:")
    assert len(identity.contract_hash) == len("sha256:") + 64
    assert json.loads(identity.canonical_payload_json) == identity.canonical_payload


def test_contract_identity_detaches_from_mutable_parameter_input() -> None:
    source_parameters: dict[str, object] = {
        "window": {"sizes": [5.0, 10.0]},
        "feature_names": ["a", "b"],
    }
    identity = _mert_identity(parameters=source_parameters)
    original_json = identity.canonical_payload_json
    original_hash = identity.contract_hash

    window = source_parameters["window"]
    assert isinstance(window, dict)
    sizes = window["sizes"]
    assert isinstance(sizes, list)
    sizes.append(20.0)
    feature_names = source_parameters["feature_names"]
    assert isinstance(feature_names, list)
    feature_names[0] = "mutated"

    assert identity.canonical_payload_json == original_json
    assert identity.contract_hash == original_hash


def test_contract_identity_exposes_deeply_immutable_parameters() -> None:
    identity = _mert_identity(
        parameters={
            "window": {"sizes": [5.0, 10.0]},
            "feature_names": ["a", "b"],
        }
    )
    original_json = identity.canonical_payload_json
    original_hash = identity.contract_hash

    window = identity.parameters["window"]
    assert isinstance(window, Mapping)
    with pytest.raises((AttributeError, TypeError)):
        window["new_key"] = "must-not-mutate"  # type: ignore[index]

    feature_names = identity.parameters["feature_names"]
    assert isinstance(feature_names, Sequence)
    with pytest.raises((AttributeError, TypeError)):
        getattr(feature_names, "append")("must-not-mutate")

    assert identity.canonical_payload_json == original_json
    assert identity.contract_hash == original_hash


@pytest.mark.parametrize(
    "value",
    [None, True, False, 123, 1.5, b"model", ["model"], {"name": "model"}],
)
@pytest.mark.parametrize(
    "field_name",
    ["analysis_family", "output_kind", "model_name"],
)
def test_contract_identity_rejects_non_string_required_text_fields(
    field_name: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "analysis_family": "mert",
        "output_kind": "embedding",
        "model_name": "model",
        "dim": 4,
        "encoding": "float32-le",
        "normalization": "l2",
    }
    values[field_name] = value

    with pytest.raises(ContractIdentityError, match=rf"(?i){field_name}"):
        ContractIdentity(**values)  # type: ignore[arg-type]


def test_register_and_require_contract_use_the_same_canonical_identity() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, _artifacts):
        written_hash = register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        registered = require_registered_contract(core, identity)
        repeated_hash = register_contract(core, identity, created_at=ANALYZED_AT)

    assert written_hash == identity.contract_hash
    assert repeated_hash == identity.contract_hash
    assert registered.contract_hash == identity.contract_hash
    assert registered.canonical_payload_json == identity.canonical_payload_json


def test_register_contract_preserves_caller_owned_transaction() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, _artifacts):
        core.execute("BEGIN IMMEDIATE")
        register_contract(core, identity, created_at=ANALYZED_AT)

        assert core.in_transaction
        core.rollback()
        assert read_registered_contract(core, identity.contract_hash) is None


def test_register_contract_is_race_safe_across_two_connections(
    tmp_path: Path,
) -> None:
    core_path = tmp_path / "contracts.sqlite"
    create_v7_schema(str(core_path))
    identity = _mert_identity()
    first_has_write_lock = threading.Event()
    release_first_writer = threading.Event()
    second_attempting = threading.Event()
    second_finished = threading.Event()
    errors: list[BaseException] = []
    results: list[str] = []

    def first_writer() -> None:
        try:
            with closing(sqlite3.connect(core_path, timeout=5)) as connection:
                connection.execute("PRAGMA busy_timeout = 5000")
                connection.execute("BEGIN IMMEDIATE")
                first_has_write_lock.set()
                if not release_first_writer.wait(timeout=5):
                    raise TimeoutError(
                        "timed out waiting to release first registry writer"
                    )
                results.append(
                    register_contract(
                        connection,
                        identity,
                        created_at=ANALYZED_AT,
                    )
                )
                assert connection.in_transaction
                connection.commit()
        except BaseException as error:
            errors.append(error)

    def second_writer() -> None:
        try:
            if not first_has_write_lock.wait(timeout=5):
                raise TimeoutError("first registry writer did not acquire its lock")
            with closing(sqlite3.connect(core_path, timeout=5)) as connection:
                connection.execute("PRAGMA busy_timeout = 5000")
                second_attempting.set()
                results.append(
                    register_contract(
                        connection,
                        identity,
                        created_at="2026-07-23T00:00:01.000000Z",
                    )
                )
                second_finished.set()
        except BaseException as error:
            errors.append(error)

    first_thread = threading.Thread(target=first_writer, name="first-contract-writer")
    second_thread = threading.Thread(
        target=second_writer,
        name="second-contract-writer",
    )
    first_thread.start()
    try:
        assert first_has_write_lock.wait(timeout=5)
        second_thread.start()
        assert second_attempting.wait(timeout=5)
        assert not second_finished.wait(timeout=0.1)
    finally:
        release_first_writer.set()
        first_thread.join(timeout=5)
        if second_thread.ident is not None:
            second_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert errors == []
    assert results == [identity.contract_hash, identity.contract_hash]
    assert second_finished.is_set()

    with closing(sqlite3.connect(core_path)) as connection:
        registered = read_registered_contract(connection, identity.contract_hash)
        count = connection.execute(
            "SELECT COUNT(*) FROM contracts WHERE contract_hash = ?",
            (identity.contract_hash,),
        ).fetchone()[0]
        stored_created_at = connection.execute(
            "SELECT created_at FROM contracts WHERE contract_hash = ?",
            (identity.contract_hash,),
        ).fetchone()[0]

    assert registered is not None
    assert registered.canonical_payload_json == identity.canonical_payload_json
    assert count == 1
    assert stored_created_at == ANALYZED_AT


@pytest.mark.parametrize(
    ("change", "expected_difference"),
    [
        ({"model_name": "different-model"}, "model_name"),
        ({"model_version": "revision-2"}, "model_version"),
        ({"checkpoint_id": "sha256:different"}, "checkpoint_id"),
        ({"preprocessing": "mono-24khz-window-v2"}, "preprocessing"),
        ({"dim": 8}, "dim"),
        ({"normalization": "none"}, "normalization"),
        (
            {"parameters": {"window_seconds": 10.0, "max_windows": 12}},
            "parameters",
        ),
    ],
)
def test_semantic_contract_change_changes_hash(
    change: dict[str, object],
    expected_difference: str,
) -> None:
    baseline = _mert_identity()
    changed = _mert_identity(**change)

    assert changed.contract_hash != baseline.contract_hash, expected_difference


@pytest.mark.parametrize(
    ("family", "output_kind"),
    [
        ("mert", "timeline"),
        ("mert", "core"),
        ("clap", "fingerprint"),
        ("maest", "timeline"),
        ("unknown", "embedding"),
    ],
)
def test_contract_identity_rejects_wrong_family_output_pair(
    family: str,
    output_kind: str,
) -> None:
    with pytest.raises(ContractIdentityError, match=r"(?i)(family|output_kind)"):
        ContractIdentity(
            analysis_family=family,
            output_kind=output_kind,
            model_name="model",
            dim=4,
            encoding="float32-le",
            normalization="l2",
        )


def test_contract_registry_rejects_unknown_identity() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, _artifacts):
        with pytest.raises(ContractRegistryError, match=r"(?i)unknown contract"):
            require_registered_contract(core, identity)


def test_contract_registry_rejects_canonical_payload_with_wrong_self_hash() -> None:
    identity = _mert_identity()
    false_hash = "sha256:" + ("0" * 64)
    assert false_hash != identity.contract_hash
    with _bound_bundle() as (core, _artifacts):
        core.execute(
            """
            INSERT INTO contracts(
                contract_hash, analysis_family, output_kind, model_name,
                model_version, release_hash, canonical_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                false_hash,
                identity.analysis_family,
                identity.output_kind,
                identity.model_name,
                identity.model_version,
                identity.release_hash,
                identity.canonical_payload_json,
                ANALYZED_AT,
            ),
        )
        core.commit()

        with pytest.raises(ContractRegistryError, match=r"(?i)self-hash"):
            read_registered_contract(core, false_hash)


def test_contract_registry_rejects_columns_that_disagree_with_payload() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, _artifacts):
        core.execute(
            """
            INSERT INTO contracts(
                contract_hash, analysis_family, output_kind, model_name,
                model_version, release_hash, canonical_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity.contract_hash,
                identity.analysis_family,
                identity.output_kind,
                "different-model-name",
                identity.model_version,
                identity.release_hash,
                identity.canonical_payload_json,
                ANALYZED_AT,
            ),
        )
        core.commit()

        with pytest.raises(
            ContractRegistryError,
            match=r"(?i)(columns|canonical payload|identity)",
        ):
            require_registered_contract(core, identity)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_contract_identity_rejects_non_finite_parameters(value: float) -> None:
    with pytest.raises(ContractIdentityError, match=r"(?i)non-finite"):
        _mert_identity(parameters={"window_seconds": value})


@pytest.mark.parametrize("family", tuple(EMBEDDING_TABLES))
def test_embedding_gateway_round_trip_uses_one_canonical_contract_hash(
    family: str,
) -> None:
    identity = _embedding_identity(family)
    vector = np.asarray([0.0, 0.6, 0.0, 0.8], dtype="<f4")
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)

        write_valid_embedding(
            core_connection=core,
            artifacts_connection=artifacts,
            track=track,
            contract=identity,
            embedding=vector,
            analyzed_at=ANALYZED_AT,
        )
        artifacts.commit()

        stored = artifacts.execute(
            f"""
            SELECT track_uuid, content_generation, contract_hash, dim,
                   normalization, embedding_blob
            FROM {EMBEDDING_TABLES[family]}
            WHERE track_id = 1
            """
        ).fetchone()
        read_back = read_valid_embedding(
            family=family,
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
            expected_contract=identity,
        )
        registered = require_registered_contract(core, identity)

    assert stored is not None
    assert tuple(stored[:5]) == (
        TRACK_UUID,
        1,
        identity.contract_hash,
        identity.dim,
        identity.normalization,
    )
    assert bytes(stored[5]) == vector.astype("<f4").tobytes(order="C")
    assert registered.contract_hash == identity.contract_hash
    assert read_back is not None
    np.testing.assert_array_equal(read_back, vector)


def test_in_transaction_embedding_gateway_requires_both_transactions() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        track = _required_track(core, artifacts)

        with pytest.raises(RuntimeError, match=r"(?i)active Core transaction"):
            write_valid_embedding_in_transaction(
                core_connection=core,
                artifacts_connection=artifacts,
                track=track,
                contract=identity,
                embedding=[0.0, 0.6, 0.0, 0.8],
                analyzed_at=ANALYZED_AT,
            )

        core.execute("BEGIN IMMEDIATE")
        with pytest.raises(RuntimeError, match=r"(?i)active Artifacts transaction"):
            write_valid_embedding_in_transaction(
                core_connection=core,
                artifacts_connection=artifacts,
                track=track,
                contract=identity,
                embedding=[0.0, 0.6, 0.0, 0.8],
                analyzed_at=ANALYZED_AT,
            )
        core.rollback()


def test_in_transaction_embedding_gateway_preserves_transaction_ownership() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        track = _required_track(core, artifacts)
        core.execute("BEGIN IMMEDIATE")
        artifacts.execute("BEGIN IMMEDIATE")

        write_valid_embedding_in_transaction(
            core_connection=core,
            artifacts_connection=artifacts,
            track=track,
            contract=identity,
            embedding=[0.0, 0.6, 0.0, 0.8],
            analyzed_at=ANALYZED_AT,
        )

        assert core.in_transaction
        assert artifacts.in_transaction
        assert (
            artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 1
        )
        artifacts.rollback()
        core.rollback()
        assert (
            artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 0
        )


@pytest.mark.parametrize("encoding", ["float32-be", "float64-le", "raw"])
def test_embedding_contract_rejects_noncanonical_encoding(encoding: str) -> None:
    with pytest.raises(ContractIdentityError, match=r"(?i)encoding"):
        _mert_identity(encoding=encoding)


def test_storage_binding_rejects_artifacts_from_another_catalog() -> None:
    identity = _mert_identity()
    track = ArtifactTrackIdentity(
        catalog_uuid=CATALOG_UUID,
        track_id=1,
        track_uuid=TRACK_UUID,
        content_generation=1,
    )
    with _bound_bundle(artifacts_catalog_uuid=OTHER_CATALOG_UUID) as (
        core,
        artifacts,
    ):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()

        with pytest.raises(RuntimeError, match=r"(?i)(catalog|another library)"):
            validate_storage_binding(core, artifacts)
        with pytest.raises(
            RuntimeError,
            match=r"(?i)(stale artifact write|catalog|another library)",
        ):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=track,
                contract=identity,
                embedding=[0.0, 0.6, 0.0, 0.8],
                analyzed_at=ANALYZED_AT,
            )

        assert (
            artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 0
        )


def test_reused_storage_binding_proof_avoids_revalidation_queries(
    tmp_path: Path,
) -> None:
    identity = _mert_identity()
    vector = np.asarray([0.0, 0.6, 0.0, 0.8], dtype="<f4")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    with (
        closing(database.connect()) as core,
        closing(database.connect_artifacts()) as artifacts,
    ):
        core.execute(
            """
            INSERT INTO tracks(
                track_id, track_uuid, file_path, file_size_bytes,
                file_modified_ns, content_generation, last_scanned_at,
                created_at, updated_at
            ) VALUES (1, ?, 'C:/music/track.wav', 100, 1000, 1, ?, ?, ?)
            """,
            (TRACK_UUID, ANALYZED_AT, ANALYZED_AT, ANALYZED_AT),
        )
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)
        write_valid_embedding(
            core_connection=core,
            artifacts_connection=artifacts,
            track=track,
            contract=identity,
            embedding=vector,
            analyzed_at=ANALYZED_AT,
        )
        storage_binding = validate_storage_binding(core, artifacts)

        core_queries: list[str] = []
        artifact_queries: list[str] = []
        core.set_trace_callback(core_queries.append)
        artifacts.set_trace_callback(artifact_queries.append)
        iterations = 10
        try:
            for _ in range(iterations):
                result = read_valid_embedding(
                    family="mert",
                    track_id=track.track_id,
                    core_connection=core,
                    artifacts_connection=artifacts,
                    expected_contract=identity,
                    storage_binding=storage_binding,
                )
                assert result is not None
                assert np.array_equal(result, vector)
        finally:
            core.set_trace_callback(None)
            artifacts.set_trace_callback(None)

    traced_queries = [*core_queries, *artifact_queries]
    forbidden_fragments = (
        "sqlite_master",
        "table_info",
        "foreign_key_check",
        "pragma ",
    )
    assert not any(
        fragment in query.lower()
        for query in traced_queries
        for fragment in forbidden_fragments
    )
    assert len(core_queries) <= iterations * 7
    assert len(artifact_queries) <= iterations * 5


def test_wrong_bound_connections_cannot_forge_read_catalog_with_string() -> None:
    identity = _mert_identity()
    with _bound_bundle(artifacts_catalog_uuid=OTHER_CATALOG_UUID) as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = ArtifactTrackIdentity(
            catalog_uuid=CATALOG_UUID,
            track_id=1,
            track_uuid=TRACK_UUID,
            content_generation=1,
        )
        _insert_embedding_row(
            artifacts,
            family="mert",
            row=_embedding_row(track, identity),
        )
        artifacts.commit()

        with pytest.raises(RuntimeError, match=r"(?i)binding proof"):
            read_valid_embedding(
                family="mert",
                track_id=track.track_id,
                core_connection=core,
                artifacts_connection=artifacts,
                expected_contract=identity,
                storage_binding=CATALOG_UUID,  # type: ignore[arg-type]
            )

        assert (
            artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 1
        )


def test_wrong_bound_connections_cannot_forge_write_catalog_with_string() -> None:
    identity = _mert_identity()
    with _bound_bundle(artifacts_catalog_uuid=OTHER_CATALOG_UUID) as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = ArtifactTrackIdentity(
            catalog_uuid=CATALOG_UUID,
            track_id=1,
            track_uuid=TRACK_UUID,
            content_generation=1,
        )
        core.execute("BEGIN IMMEDIATE")
        artifacts.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(
                RuntimeError,
                match=r"(?i)binding proof",
            ):
                write_valid_embedding_in_transaction(
                    core_connection=core,
                    artifacts_connection=artifacts,
                    track=track,
                    contract=identity,
                    embedding=[0.0, 0.6, 0.0, 0.8],
                    analyzed_at=ANALYZED_AT,
                    storage_binding=CATALOG_UUID,  # type: ignore[arg-type]
                )
        finally:
            artifacts.rollback()
            core.rollback()


@pytest.mark.parametrize(
    ("field_name", "bad_value", "reason"),
    [
        ("catalog_uuid", OTHER_CATALOG_UUID, "catalog_uuid"),
        ("track_uuid", OTHER_TRACK_UUID, "track_uuid"),
        ("content_generation", 2, "content_generation"),
    ],
)
def test_embedding_writer_rejects_one_field_track_identity_mismatch_before_insert(
    field_name: str,
    bad_value: object,
    reason: str,
) -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)
        stale_track = replace(track, **{field_name: bad_value})

        with pytest.raises(
            RuntimeError,
            match=rf"(?i)stale artifact write.*{reason}",
        ):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=stale_track,
                contract=identity,
                embedding=[0.0, 0.6, 0.0, 0.8],
                analyzed_at=ANALYZED_AT,
            )

        assert (
            artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 0
        )


def test_embedding_writer_rejects_generation_that_became_stale_before_insert() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        captured_track = _required_track(core, artifacts)
        core.execute("UPDATE tracks SET content_generation = 2 WHERE track_id = 1")
        core.commit()

        with pytest.raises(
            RuntimeError,
            match=r"(?i)stale artifact write.*content_generation",
        ):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=captured_track,
                contract=identity,
                embedding=[0.0, 0.6, 0.0, 0.8],
                analyzed_at=ANALYZED_AT,
            )

        assert (
            artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 0
        )


def test_older_interleaved_writer_cannot_overwrite_newer_generation_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _mert_identity()
    old_vector = np.asarray([1.0, 0.0, 0.0, 0.0], dtype="<f4")
    current_vector = np.asarray([0.0, 1.0, 0.0, 0.0], dtype="<f4")

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
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
    with (
        closing(database.connect()) as core,
        closing(database.connect_artifacts()) as artifacts,
    ):
        stale_track = _required_track(core, artifacts)

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
            if not result[0]:
                raise AssertionError(
                    f"stale writer did not initially validate: {result}"
                )
            stale_validated.set()
            if not release_stale_writer.wait(timeout=5):
                raise TimeoutError("timed out waiting to release stale artifact writer")
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
                    contract=identity,
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
                current_track = _required_track(core, artifacts)
                write_valid_embedding(
                    core_connection=core,
                    artifacts_connection=artifacts,
                    track=current_track,
                    contract=identity,
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
        read_back = read_valid_embedding(
            family="mert",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
            expected_contract=identity,
        )

    assert row is not None
    assert int(row["content_generation"]) == 2
    np.testing.assert_array_equal(
        np.frombuffer(row["embedding_blob"], dtype="<f4"),
        current_vector,
    )
    assert read_back is not None
    np.testing.assert_array_equal(read_back, current_vector)


def test_embedding_writer_rejects_unknown_contract_before_insert() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        track = _required_track(core, artifacts)

        with pytest.raises(ContractRegistryError, match=r"(?i)unknown contract"):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=track,
                contract=identity,
                embedding=[0.0, 0.6, 0.0, 0.8],
                analyzed_at=ANALYZED_AT,
            )

        assert (
            artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 0
        )


def test_embedding_writer_rejects_registry_self_hash_failure_before_insert() -> None:
    expected = _mert_identity()
    different = _mert_identity(model_version="different-revision")
    with _bound_bundle() as (core, artifacts):
        core.execute(
            """
            INSERT INTO contracts(
                contract_hash, analysis_family, output_kind, model_name,
                model_version, release_hash, canonical_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                expected.contract_hash,
                different.analysis_family,
                different.output_kind,
                different.model_name,
                different.model_version,
                different.release_hash,
                different.canonical_payload_json,
                ANALYZED_AT,
            ),
        )
        core.commit()
        track = _required_track(core, artifacts)

        with pytest.raises(ContractRegistryError, match=r"(?i)self-hash"):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=track,
                contract=expected,
                embedding=[0.0, 0.6, 0.0, 0.8],
                analyzed_at=ANALYZED_AT,
            )

        assert (
            artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 0
        )


def test_embedding_writer_rejects_non_embedding_output_before_insert() -> None:
    identity = ContractIdentity(
        analysis_family="maest",
        output_kind="analysis",
        model_name="maest-model",
        model_version="revision-1",
        checkpoint_id="sha256:checkpoint",
        preprocessing="mono-window-v1",
    )
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)

        with pytest.raises(ValueError, match=r"(?i)output_kind"):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=track,
                contract=identity,
                embedding=[0.0, 0.6, 0.0, 0.8],
                analyzed_at=ANALYZED_AT,
            )

        assert (
            artifacts.execute("SELECT COUNT(*) FROM maest_embeddings").fetchone()[0]
            == 0
        )


def test_sidecar_row_rejects_contract_from_another_family() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)

        valid, reason = validate_sidecar_row(
            family="maest",
            row=_embedding_row(track, identity),
            expected_contract=identity,
            expected_track=track,
            core_connection=core,
            artifacts_connection=artifacts,
        )

    assert valid is False
    assert reason == "analysis_family mismatch"


@pytest.mark.parametrize(
    ("case", "sql", "parameters"),
    [
        (
            "track_uuid",
            "UPDATE mert_embeddings SET track_uuid = ? WHERE track_id = 1",
            (OTHER_TRACK_UUID,),
        ),
        (
            "content_generation",
            "UPDATE mert_embeddings SET content_generation = ? WHERE track_id = 1",
            (2,),
        ),
        (
            "contract_hash",
            "UPDATE mert_embeddings SET contract_hash = ? WHERE track_id = 1",
            ("sha256:" + ("0" * 64),),
        ),
        (
            "dim",
            """
            UPDATE mert_embeddings
            SET dim = ?, embedding_blob = ?
            WHERE track_id = 1
            """,
            (2, np.asarray([0.6, 0.8], dtype="<f4").tobytes()),
        ),
        (
            "normalization",
            "UPDATE mert_embeddings SET normalization = ? WHERE track_id = 1",
            ("none",),
        ),
        (
            "nonfinite",
            "UPDATE mert_embeddings SET embedding_blob = ? WHERE track_id = 1",
            (
                np.asarray(
                    [0.0, float("nan"), 0.0, 0.8],
                    dtype="<f4",
                ).tobytes(),
            ),
        ),
    ],
)
def test_embedding_reader_fails_closed_on_one_field_row_corruption(
    case: str,
    sql: str,
    parameters: tuple[object, ...],
) -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)
        write_valid_embedding(
            core_connection=core,
            artifacts_connection=artifacts,
            track=track,
            contract=identity,
            embedding=[0.0, 0.6, 0.0, 0.8],
            analyzed_at=ANALYZED_AT,
        )
        artifacts.execute(sql, parameters)
        artifacts.commit()

        read_back = read_valid_embedding(
            family="mert",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
            expected_contract=identity,
        )

    assert read_back is None, case


def test_sidecar_row_rejects_wrong_blob_length() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)
        row = _embedding_row(track, identity)
        row["embedding_blob"] = bytes(row["embedding_blob"])[:-1]

        valid, reason = validate_sidecar_row(
            family="mert",
            row=row,
            expected_contract=identity,
            expected_track=track,
            core_connection=core,
            artifacts_connection=artifacts,
        )

    assert valid is False
    assert reason == "blob length mismatch"


def test_embedding_reader_fails_closed_for_unregistered_contract() -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        track = _required_track(core, artifacts)
        _insert_embedding_row(
            artifacts,
            family="mert",
            row=_embedding_row(track, identity),
        )
        artifacts.commit()

        read_back = read_valid_embedding(
            family="mert",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
            expected_contract=identity,
        )

    assert read_back is None


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("track_id", None),
        ("track_id", "not-an-integer"),
        ("content_generation", None),
        ("content_generation", "not-an-integer"),
        ("dim", None),
        ("dim", "not-an-integer"),
    ],
)
def test_sidecar_row_bad_numeric_conversions_fail_closed(
    field_name: str,
    bad_value: object,
) -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)
        row = _embedding_row(track, identity)
        row[field_name] = bad_value

        valid, reason = validate_sidecar_row(
            family="mert",
            row=row,
            expected_contract=identity,
            expected_track=track,
            core_connection=core,
            artifacts_connection=artifacts,
        )

    assert valid is False
    assert reason


@pytest.mark.parametrize(
    "vector",
    [
        [0.0, float("nan"), 0.0, 0.8],
        [0.0, float("inf"), 0.0, 0.8],
        [0.0, float("-inf"), 0.0, 0.8],
    ],
)
def test_embedding_writer_rejects_nonfinite_values_before_insert(
    vector: list[float],
) -> None:
    identity = _mert_identity()
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)

        with pytest.raises(ValueError, match=r"(?i)non-finite"):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=track,
                contract=identity,
                embedding=vector,
                analyzed_at=ANALYZED_AT,
            )

        assert (
            artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 0
        )


def test_l2_writer_normalizes_nonunit_vector_or_rejects_it() -> None:
    identity = _mert_identity(normalization="l2")
    nonunit = np.asarray([1.0, 1.0, 0.0, 0.0], dtype="<f4")
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)

        try:
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=track,
                contract=identity,
                embedding=nonunit,
                analyzed_at=ANALYZED_AT,
            )
        except ValueError:
            assert (
                artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0]
                == 0
            )
        else:
            read_back = read_valid_embedding(
                family="mert",
                track_id=1,
                core_connection=core,
                artifacts_connection=artifacts,
                expected_contract=identity,
            )
            assert read_back is not None
            assert np.linalg.norm(read_back) == pytest.approx(1.0, abs=1e-6)


def test_l2_writer_rejects_zero_vector_before_insert() -> None:
    identity = _mert_identity(normalization="l2")
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)

        with pytest.raises(ValueError, match=r"(?i)(l2|norm|zero)"):
            write_valid_embedding(
                core_connection=core,
                artifacts_connection=artifacts,
                track=track,
                contract=identity,
                embedding=[0.0, 0.0, 0.0, 0.0],
                analyzed_at=ANALYZED_AT,
            )

        assert (
            artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 0
        )


def test_l2_reader_rejects_row_whose_vector_is_not_unit_normalized() -> None:
    identity = _mert_identity(normalization="l2")
    nonunit = np.asarray([1.0, 1.0, 0.0, 0.0], dtype="<f4")
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)
        _insert_embedding_row(
            artifacts,
            family="mert",
            row=_embedding_row(track, identity, nonunit),
        )
        artifacts.commit()

        read_back = read_valid_embedding(
            family="mert",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
            expected_contract=identity,
        )

    assert read_back is None


def test_none_normalization_preserves_finite_nonunit_vector() -> None:
    identity = _mert_identity(normalization="none")
    vector = np.asarray([1.0, 2.0, 3.0, 4.0], dtype="<f4")
    with _bound_bundle() as (core, artifacts):
        register_contract(core, identity, created_at=ANALYZED_AT)
        core.commit()
        track = _required_track(core, artifacts)
        write_valid_embedding(
            core_connection=core,
            artifacts_connection=artifacts,
            track=track,
            contract=identity,
            embedding=vector,
            analyzed_at=ANALYZED_AT,
        )
        read_back = read_valid_embedding(
            family="mert",
            track_id=1,
            core_connection=core,
            artifacts_connection=artifacts,
            expected_contract=identity,
        )

    assert read_back is not None
    np.testing.assert_array_equal(read_back, vector)
