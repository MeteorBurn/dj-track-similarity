from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from dj_track_similarity.analysis_contracts import (
    FLOAT32_LE_ENCODING,
    ContractIdentity,
    ContractRegistryError,
)
from dj_track_similarity.analysis_model_runners import (
    MaestModelRunner,
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    ClassifierScoreWrite,
    ClassifierSpecification,
    EmbeddingOutput,
    EmbeddingWrite,
    InactiveAnalysisOutputError,
    MaestGenreScore,
    MaestWrite,
    SonaraFingerprintOutput,
    SonaraTimelineOutput,
    SonaraWrite,
    classifier_required_outputs_hash,
    mert_embedding_output,
    muq_embedding_output,
)
from dj_track_similarity.db_analysis import AnalysisRepository
from dj_track_similarity.db_artifacts import (
    create_artifacts_sidecar_schema,
)
from dj_track_similarity.db_library_queries import LibraryQueryRepository
from dj_track_similarity.db_schema_v7 import (
    ClassifierScoreV7,
    SonaraRowV7,
    create_v7_schema,
)
from dj_track_similarity.prepare_sonara_release import (
    CONFIRM_STRING,
    prepare_sonara_release,
)
from dj_track_similarity.sonara_contract import (
    SONARA_EXPECTED_SCHEMA_VERSION,
    SONARA_EXPECTED_VERSION,
    SONARA_PROJECT_FEATURE_REVISION,
    SONARA_CORE_REQUESTED_FEATURES,
    SONARA_EMBEDDING_REQUESTED_FEATURES,
    SONARA_FINGERPRINT_REQUESTED_FEATURES,
    SONARA_TIMELINE_REQUESTED_FEATURES,
    SONARA_UNIT_INTERVAL_CLAMP_EPSILON,
    SONARA_UNIT_INTERVAL_CLAMP_FIELDS,
    SONARA_UNIT_INTERVAL_CLAMP_POLICY,
    SonaraContractSet,
    SonaraRuntimeIdentity,
    build_sonara_contracts,
)


_NOW = "2026-07-23T10:00:00.000000Z"


class _Repository(AnalysisRepository, LibraryQueryRepository):
    def __init__(self, root: Path) -> None:
        self.path = root / "library.sqlite"
        self.artifacts_path = root / "library.artifacts.sqlite"
        self.catalog_uuid = str(uuid.uuid4())
        self._write_lock = threading.RLock()

        core = sqlite3.connect(self.path)
        try:
            create_v7_schema(core)
            core.execute(
                """
                INSERT INTO library_catalog (
                    singleton_id, catalog_uuid, created_at, updated_at
                ) VALUES (1, ?, ?, ?)
                """,
                (self.catalog_uuid, _NOW, _NOW),
            )
            core.commit()
        finally:
            core.close()

        artifacts = sqlite3.connect(self.artifacts_path)
        try:
            create_artifacts_sidecar_schema(
                artifacts,
                catalog_uuid=self.catalog_uuid,
            )
            artifacts.commit()
        finally:
            artifacts.close()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def connect_artifacts(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.artifacts_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


@pytest.fixture()
def repository(tmp_path: Path) -> _Repository:
    return _Repository(tmp_path)


def _insert_track(
    repository: _Repository,
    *,
    track_uuid: str | None = None,
    content_generation: int = 1,
) -> AnalysisTarget:
    identity = track_uuid or str(uuid.uuid4())
    with repository.connect() as core:
        cursor = core.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, 123456789, ?, ?, ?, ?)
            """,
            (
                identity,
                f"C:/music/{identity}.wav",
                content_generation,
                _NOW,
                _NOW,
                _NOW,
            ),
        )
        track_id = int(cursor.lastrowid)
    return AnalysisTarget(
        catalog_uuid=repository.catalog_uuid,
        track_id=track_id,
        track_uuid=identity,
        content_generation=content_generation,
    )


def _mert_output(**changes: object) -> AnalysisOutput:
    return _replace_output_identity(
        current_embedding_analysis_output("mert"),
        changes,
    )


def _replace_output_identity(
    output: AnalysisOutput,
    changes: dict[str, object],
) -> AnalysisOutput:
    top_level_fields = {
        "model_name",
        "model_version",
        "checkpoint_id",
        "preprocessing",
        "dim",
        "encoding",
        "normalization",
        "release_hash",
    }
    contract_changes: dict[str, object] = {}
    parameters = dict(output.contract.parameters)
    for field_name, value in changes.items():
        if field_name == "parameters":
            parameters.update(dict(value))  # type: ignore[arg-type]
        elif field_name in top_level_fields:
            contract_changes[field_name] = value
        elif field_name in parameters:
            parameters[field_name] = value
        else:
            raise ValueError(f"unknown contract field: {field_name}")
    return AnalysisOutput(
        replace(
            output.contract,
            parameters=parameters,
            **contract_changes,
        )
    )


def _mert_factory(**changes: object) -> AnalysisOutput:
    current = _mert_output()
    parameters = dict(current.contract.parameters)
    reserved = {
        field_name: parameters.pop(field_name)
        for field_name in (
            "sample_rate_hz",
            "window_seconds",
            "max_windows",
            "hidden_layers",
            "pooling",
        )
    }
    values: dict[str, object] = {
        "model_name": current.contract.model_name,
        "model_version": current.contract.model_version,
        "checkpoint_id": current.contract.checkpoint_id,
        "preprocessing": current.contract.preprocessing,
        **reserved,
        "parameters": parameters,
    }
    values.update(changes)
    return mert_embedding_output(**values)  # type: ignore[arg-type]


def _clap_output() -> AnalysisOutput:
    return current_embedding_analysis_output("clap")


def _unit_vector(dim: int, *, first: int = 0) -> np.ndarray:
    vector = np.zeros(dim, dtype=np.float32)
    vector[first] = 1.0
    return vector


def _embedding_write(
    target: AnalysisTarget,
    output: AnalysisOutput,
    *,
    first: int = 0,
) -> EmbeddingWrite:
    return EmbeddingWrite(
        target=target,
        output=EmbeddingOutput(
            contract=output.contract,
            vector=_unit_vector(int(output.contract.dim), first=first),
            analyzed_at=_NOW,
        ),
    )


def test_strict_factory_identity_and_omission_gate(
    repository: _Repository,
) -> None:
    baseline = _mert_output()
    variations = (
        _mert_output(model_version="2" * 40),
        _mert_output(checkpoint_id="sha256:" + "2" * 64),
        _mert_output(preprocessing="shared-mono-v2"),
        _mert_output(window_seconds=6.0),
        _mert_output(max_windows=6),
        _mert_output(hidden_layers=(8, 9, 10, 11)),
        _mert_output(pooling="last4+time+window-mean"),
    )
    assert all(output.contract_hash != baseline.contract_hash for output in variations)
    assert (
        len({baseline.contract_hash, *(item.contract_hash for item in variations)})
        == len(variations) + 1
    )

    incomplete = AnalysisOutput(
        ContractIdentity(
            analysis_family="mert",
            output_kind="embedding",
            model_name="m-a-p/MERT-v1-95M",
            dim=768,
            encoding=FLOAT32_LE_ENCODING,
            normalization="l2",
        )
    )
    with pytest.raises(ValueError, match="model_version"):
        repository.register_analysis_outputs((incomplete,))

    with pytest.raises(ValueError, match="reserved factory fields"):
        _mert_factory(parameters={"window_seconds": 99.0})
    with pytest.raises(ValueError, match="greater than zero"):
        _mert_factory(window_seconds=0.0)
    with pytest.raises(ValueError, match="positive integer"):
        _mert_factory(hidden_layers=(9, True, 11, 12))
    with pytest.raises(ValueError, match="sample_rate_hz must be 24000"):
        muq_embedding_output(
            model_version="1",
            checkpoint_id="sha256:" + "3" * 64,
            preprocessing="shared-mono-v1",
            sample_rate_hz=16_000,
            window_seconds=10.0,
            max_windows=5,
            pooling="time+window-mean",
            dtype="float32",
        )
    with pytest.raises(ValueError, match="dtype must be 'float32'"):
        muq_embedding_output(
            model_version="1",
            checkpoint_id="sha256:" + "3" * 64,
            preprocessing="shared-mono-v1",
            sample_rate_hz=24_000,
            window_seconds=10.0,
            max_windows=5,
            pooling="time+window-mean",
            dtype="float16",
        )


def test_candidate_generation_and_stale_target_fence(
    repository: _Repository,
) -> None:
    target = _insert_track(repository)
    output = _mert_output()
    repository.register_analysis_outputs((output,))

    candidates = repository.list_analysis_candidates((output,))
    assert [candidate.target for candidate in candidates] == [target]
    assert candidates[0].missing_outputs == (output,)

    result = repository.save_embedding_results((_embedding_write(target, output),))
    assert result[0].ok
    assert repository.list_analysis_candidates((output,)) == []

    with repository.connect() as core:
        core.execute(
            """
            UPDATE tracks
            SET content_generation = 2, updated_at = ?
            WHERE track_id = ?
            """,
            (_NOW, target.track_id),
        )
    stale_result = repository.save_embedding_results(
        (_embedding_write(target, output),)
    )
    assert not stale_result[0].ok
    assert "content_generation mismatch" in str(stale_result[0].error)

    current = AnalysisTarget(
        catalog_uuid=target.catalog_uuid,
        track_id=target.track_id,
        track_uuid=target.track_uuid,
        content_generation=2,
    )
    assert [
        candidate.target for candidate in repository.list_analysis_candidates((output,))
    ] == [current]
    assert repository.save_embedding_results(
        (_embedding_write(current, output, first=1),)
    )[0].ok

    with repository.connect_artifacts() as artifacts:
        row = artifacts.execute(
            """
            SELECT content_generation, contract_hash
            FROM mert_embeddings
            WHERE track_id = ?
            """,
            (target.track_id,),
        ).fetchone()
    assert tuple(row) == (2, output.contract_hash)


def test_noncurrent_same_generation_writer_cannot_overwrite_active_contract(
    repository: _Repository,
) -> None:
    target = _insert_track(repository)
    assert repository.active_analysis_output("mert", "embedding") is None
    active_output = _mert_output()
    repository.register_analysis_outputs((active_output,))
    assert repository.active_analysis_output("mert", "embedding") == active_output
    assert repository.save_embedding_results(
        (_embedding_write(target, active_output, first=1),)
    )[0].ok

    stale_output = _mert_output(checkpoint_id="sha256:" + "a" * 64)
    stale = repository.save_embedding_results(
        (_embedding_write(target, stale_output, first=2),)
    )
    assert not stale[0].ok
    assert "unknown contract" in str(stale[0].error)

    with repository.connect_artifacts() as artifacts:
        row = artifacts.execute(
            """
            SELECT contract_hash, embedding_blob
            FROM mert_embeddings
            WHERE track_id = ?
            """,
            (target.track_id,),
        ).fetchone()
    assert str(row["contract_hash"]) == active_output.contract_hash
    stored = np.frombuffer(row["embedding_blob"], dtype="<f4")
    np.testing.assert_array_equal(stored, _unit_vector(768, first=1))
    loaded = repository.load_analysis_vectors(
        active_output,
        targets=(target,),
    )
    np.testing.assert_array_equal(
        loaded[0].vector,
        _unit_vector(768, first=1),
    )
    with pytest.raises(ContractRegistryError):
        repository.list_analysis_candidates((stale_output,))


@pytest.mark.parametrize(
    "malformed_kind",
    (
        "nan",
        "zero_l2",
        "nonunit_l2",
        "wrong_dim",
        "wrong_normalization",
        "wrong_blob_length",
    ),
)
def test_malformed_embedding_reader_candidates_and_coverage_agree(
    repository: _Repository,
    malformed_kind: str,
) -> None:
    target = _insert_track(repository)
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    assert repository.save_embedding_results((_embedding_write(target, output),))[0].ok
    assert len(repository.load_analysis_vectors(output)) == 1
    assert repository.list_analysis_candidates((output,)) == []
    assert repository.get_track_summaries((target.track_id,))[0].analysis_coverage.mert
    assert repository.library_summary().mert == 1

    assert output.contract.dim is not None
    malformed_dim = output.contract.dim
    malformed_normalization = output.contract.normalization
    malformed_vector = _unit_vector(output.contract.dim)
    if malformed_kind == "nan":
        malformed_vector[0] = np.nan
    elif malformed_kind == "zero_l2":
        malformed_vector.fill(0.0)
    elif malformed_kind == "nonunit_l2":
        malformed_vector[0] = 2.0
    elif malformed_kind == "wrong_dim":
        malformed_dim -= 1
        malformed_vector = malformed_vector[:malformed_dim]
    elif malformed_kind == "wrong_normalization":
        malformed_normalization = "none"
    elif malformed_kind == "wrong_blob_length":
        malformed_vector = malformed_vector[:-1]
    else:
        raise AssertionError(f"unsupported malformed_kind: {malformed_kind}")

    with repository.connect_artifacts() as artifacts:
        if malformed_kind == "wrong_blob_length":
            artifacts.execute("PRAGMA ignore_check_constraints = ON")
        artifacts.execute(
            """
            UPDATE mert_embeddings
            SET dim = ?, normalization = ?, embedding_blob = ?
            WHERE track_id = ?
            """,
            (
                malformed_dim,
                malformed_normalization,
                malformed_vector.astype("<f4", copy=False).tobytes(),
                target.track_id,
            ),
        )

    assert repository.load_analysis_vectors(output) == ()
    candidates = repository.list_analysis_candidates((output,))
    assert [candidate.target for candidate in candidates] == [target]
    assert candidates[0].missing_outputs == (output,)
    assert not repository.get_track_summaries((target.track_id,))[
        0
    ].analysis_coverage.mert
    assert repository.library_summary().mert == 0


def test_malformed_sonara_embedding_and_fingerprint_are_rescheduled(
    repository: _Repository,
) -> None:
    target = _insert_track(repository)
    contracts = _sonara_contracts()
    outputs = _sonara_outputs(contracts)
    _prepare_release(repository)
    assert repository.save_sonara_results((_sonara_write(target, contracts),))[0].ok

    with repository.connect_artifacts() as artifacts:
        artifacts.execute(
            """
            UPDATE sonara_similarity_embeddings
            SET dim = 47, embedding_blob = ?
            WHERE track_id = ?
            """,
            (bytes(47 * 4), target.track_id),
        )
        artifacts.execute(
            """
            UPDATE sonara_fingerprints
            SET fingerprint_version = '999'
            WHERE track_id = ?
            """,
            (target.track_id,),
        )

    embedding = next(
        output for output in outputs if output.key == ("sonara", "embedding")
    )
    fingerprint = next(
        output for output in outputs if output.key == ("sonara", "fingerprint")
    )
    assert repository.load_analysis_vectors(embedding) == ()
    candidates = repository.list_analysis_candidates((embedding, fingerprint))
    assert [candidate.target for candidate in candidates] == [target]
    assert candidates[0].missing_outputs == (embedding, fingerprint)


@pytest.mark.parametrize(
    ("malformed_case", "malformed_output_kind"),
    (
        ("empty_timeline", "timeline"),
        ("malformed_nonempty_timeline", "timeline"),
        ("empty_fingerprint", "fingerprint"),
    ),
)
def test_semantically_invalid_sonara_artifact_surfaces_agree(
    repository: _Repository,
    malformed_case: str,
    malformed_output_kind: str,
) -> None:
    target = _insert_track(repository)
    contracts = _sonara_contracts()
    outputs = {
        output.contract.output_kind: output for output in _sonara_outputs(contracts)
    }
    _prepare_release(repository)
    assert repository.save_sonara_results((_sonara_write(target, contracts),))[0].ok

    selected = outputs[malformed_output_kind]
    assert repository.list_analysis_candidates((selected,)) == []
    initial = repository.get_track_detail(target.track_id)
    assert initial.analysis_coverage.timeline
    assert initial.analysis_coverage.fingerprint
    assert repository.load_sonara_timeline(target.track_id) is not None
    assert initial.optional_outputs.audio_fingerprint_available

    with repository.connect_artifacts() as artifacts:
        if malformed_output_kind == "timeline":
            payload_json = (
                "{}" if malformed_case == "empty_timeline" else '{"beats":[]}'
            )
            artifacts.execute(
                """
                UPDATE sonara_timeline
                SET payload_json = ?
                WHERE track_id = ?
                """,
                (payload_json, target.track_id),
            )
        else:
            artifacts.execute(
                """
                UPDATE sonara_fingerprints
                SET word_count = 0, fingerprint_blob = X''
                WHERE track_id = ?
                """,
                (target.track_id,),
            )

    candidates = repository.list_analysis_candidates(
        (outputs["timeline"], outputs["fingerprint"])
    )
    assert [candidate.target for candidate in candidates] == [target]
    assert candidates[0].missing_outputs == (selected,)

    summary = repository.get_track_summaries((target.track_id,))[0]
    assert not getattr(summary.analysis_coverage, malformed_output_kind)
    detail = repository.get_track_detail(target.track_id)
    if malformed_output_kind == "timeline":
        assert repository.load_sonara_timeline(target.track_id) is None
        assert detail.optional_outputs.timeline_fields == ()
        assert detail.analysis_coverage.fingerprint
    else:
        assert not detail.optional_outputs.audio_fingerprint_available
        assert detail.analysis_coverage.timeline
        assert repository.load_sonara_timeline(target.track_id) is not None


@pytest.mark.parametrize(
    "malformed_case",
    (
        "nan_mfcc",
        "truncated_mfcc",
        "nonfinite_chroma",
        "malformed_scalar",
        "malformed_json",
    ),
)
def test_semantically_invalid_sonara_core_surfaces_agree(
    repository: _Repository,
    malformed_case: str,
) -> None:
    target = _insert_track(repository)
    contracts = _sonara_contracts()
    core_output = AnalysisOutput(contracts.core)
    _prepare_release(repository)
    assert repository.save_sonara_results((_sonara_write(target, contracts),))[0].ok

    valid_rows = repository.load_sonara_feature_rows(core_output)
    assert len(valid_rows) == 1
    assert len(valid_rows[0].values["mfcc_mean_blob"]) == 13
    assert len(valid_rows[0].values["chroma_mean_blob"]) == 12
    assert len(valid_rows[0].values["spectral_contrast_mean_blob"]) == 7
    assert repository.list_analysis_candidates((core_output,)) == []
    assert repository.get_track_summaries((target.track_id,))[
        0
    ].analysis_coverage.sonara_core
    assert repository.get_track_detail(target.track_id).sonara_core is not None
    assert repository.library_summary().sonara == 1

    with repository.connect() as core:
        core.execute("PRAGMA ignore_check_constraints = ON")
        if malformed_case == "nan_mfcc":
            core.execute(
                "UPDATE sonara SET mfcc_mean_blob = ? WHERE track_id = ?",
                (
                    np.full(13, np.nan, dtype="<f4").tobytes(),
                    target.track_id,
                ),
            )
        elif malformed_case == "truncated_mfcc":
            core.execute(
                "UPDATE sonara SET mfcc_mean_blob = ? WHERE track_id = ?",
                (np.zeros(12, dtype="<f4").tobytes(), target.track_id),
            )
        elif malformed_case == "nonfinite_chroma":
            core.execute(
                "UPDATE sonara SET chroma_mean_blob = ? WHERE track_id = ?",
                (
                    np.full(12, np.inf, dtype="<f4").tobytes(),
                    target.track_id,
                ),
            )
        elif malformed_case == "malformed_scalar":
            core.execute(
                "UPDATE sonara SET detected_bpm = 'not-a-number' WHERE track_id = ?",
                (target.track_id,),
            )
        elif malformed_case == "malformed_json":
            core.execute(
                """
                UPDATE sonara
                SET bpm_candidates_json = '[{"bpm":"bad","rank":1,"score":1}]'
                WHERE track_id = ?
                """,
                (target.track_id,),
            )
        else:
            raise AssertionError(f"unsupported malformed_case: {malformed_case}")

    assert repository.load_sonara_feature_rows(core_output) == ()
    candidates = repository.list_analysis_candidates((core_output,))
    assert [candidate.target for candidate in candidates] == [target]
    assert candidates[0].missing_outputs == (core_output,)
    summary = repository.get_track_summaries((target.track_id,))[0]
    assert not summary.analysis_coverage.sonara_core
    detail = repository.get_track_detail(target.track_id)
    assert not detail.analysis_coverage.sonara_core
    assert detail.sonara_core is None
    assert repository.library_summary().sonara == 0


def test_sonara_writer_rejects_semantically_invalid_core_row(
    repository: _Repository,
) -> None:
    target = _insert_track(repository)
    contracts = _sonara_contracts()
    _prepare_release(repository)
    write = _sonara_write(target, contracts)
    write = replace(
        write,
        core=replace(
            write.core,
            bpm_candidates_json='[{"bpm":"bad","rank":1,"score":1}]',
        ),
    )

    result = repository.save_sonara_results((write,))[0]

    assert not result.ok
    assert result.error is not None
    assert "invalid SONARA Core row" in result.error
    with repository.connect() as core:
        assert (
            core.execute(
                "SELECT COUNT(*) FROM sonara WHERE track_id = ?",
                (target.track_id,),
            ).fetchone()[0]
            == 0
        )


@pytest.mark.parametrize(
    ("malformed_output_kind", "error_pattern"),
    (
        ("timeline", "invalid SONARA timeline payload"),
        ("fingerprint", "must contain at least one word"),
    ),
)
def test_sonara_writer_rejects_semantically_invalid_optional_artifacts(
    repository: _Repository,
    malformed_output_kind: str,
    error_pattern: str,
) -> None:
    target = _insert_track(repository)
    contracts = _sonara_contracts()
    _prepare_release(repository)
    write = _sonara_write(target, contracts)
    if malformed_output_kind == "timeline":
        write = replace(
            write,
            timeline=SonaraTimelineOutput(
                contract=contracts.timeline,
                payload={"beats": []},
                analyzed_at=_NOW,
            ),
        )
    else:
        write = replace(
            write,
            fingerprint=SonaraFingerprintOutput(
                contract=contracts.fingerprint,
                fingerprint_version="1",
                words=np.asarray([], dtype=np.uint32),
                analyzed_at=_NOW,
            ),
        )

    result = repository.save_sonara_results((write,))[0]

    assert not result.ok
    assert result.error is not None
    assert error_pattern in result.error
    with repository.connect() as core:
        assert (
            core.execute(
                "SELECT COUNT(*) FROM sonara WHERE track_id = ?",
                (target.track_id,),
            ).fetchone()[0]
            == 0
        )
    with repository.connect_artifacts() as artifacts:
        for table in (
            "sonara_timeline",
            "sonara_similarity_embeddings",
            "sonara_fingerprints",
        ):
            assert (
                artifacts.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE track_id = ?",
                    (target.track_id,),
                ).fetchone()[0]
                == 0
            )


def test_maest_typed_core_and_artifact_write(
    repository: _Repository,
) -> None:
    target = _insert_track(repository)
    analysis, embedding = MaestModelRunner(
        device="cpu",
        top_k=3,
        inference_batch_size=1,
    ).active_outputs
    repository.register_analysis_outputs((analysis, embedding))
    write = MaestWrite(
        target=target,
        analysis_contract=analysis.contract,
        genres=(
            MaestGenreScore(label="Techno", score=0.91),
            MaestGenreScore(label="House", score=0.72),
        ),
        syncopated_rhythm=True,
        analyzed_at=_NOW,
        embedding=EmbeddingOutput(
            contract=embedding.contract,
            vector=_unit_vector(768, first=5),
            analyzed_at=_NOW,
        ),
    )
    assert repository.save_maest_results((write,))[0].ok
    assert repository.list_analysis_candidates((analysis, embedding)) == []

    with repository.connect() as core:
        score = core.execute(
            """
            SELECT content_generation, contract_hash, syncopated_rhythm,
                   genres_json
            FROM maest_scores
            WHERE track_id = ?
            """,
            (target.track_id,),
        ).fetchone()
    assert tuple(score[:3]) == (1, analysis.contract_hash, 1)
    assert json.loads(score["genres_json"])[0] == {
        "label": "Techno",
        "score": 0.91,
    }
    assert (
        repository.load_analysis_vectors(
            embedding,
            targets=(target,),
        )[0].target
        == target
    )


@pytest.mark.parametrize(
    "genres_json",
    (
        '[{"label":"","score":0.5}]',
        '[{"label":"Techno"}]',
        '[42,{"label":"House","score":0.7}]',
        '[{"label":"Techno","score":"bad"}]',
        "[]",
        (
            '[{"label":"Techno","score":0.9},'
            '{"label":"techno","score":0.8},'
            '{"label":"House","score":0.7}]'
        ),
        (
            '[{"label":"Techno","score":0.9},'
            '{"label":"House","score":0.7},'
            '{"label":"Trance","score":0.8}]'
        ),
        (
            '[{"label":"Techno","score":0.9},'
            '{"label":"House","score":0.8},'
            '{"label":"Trance","score":0.7},'
            '{"label":"Ambient","score":0.6}]'
        ),
    ),
)
def test_semantically_invalid_maest_analysis_surfaces_agree(
    repository: _Repository,
    genres_json: str,
) -> None:
    target = _insert_track(repository)
    analysis, _embedding = MaestModelRunner(
        device="cpu",
        top_k=3,
        inference_batch_size=1,
    ).active_outputs
    repository.register_analysis_outputs((analysis,))
    write = MaestWrite(
        target=target,
        analysis_contract=analysis.contract,
        genres=(
            MaestGenreScore(label="Techno", score=0.91),
            MaestGenreScore(label="House", score=0.72),
        ),
        syncopated_rhythm=True,
        analyzed_at=_NOW,
    )
    assert repository.save_maest_results((write,))[0].ok
    assert repository.list_analysis_candidates((analysis,)) == []
    assert repository.get_track_summaries((target.track_id,))[
        0
    ].analysis_coverage.maest_analysis
    assert len(repository.get_track_detail(target.track_id).maest.genres) == 2
    assert repository.library_summary().maest_analysis == 1
    assert len(repository.list_genre_tag_candidates()) == 1

    if genres_json == '[{"label":"","score":0.5}]':
        forged_write = replace(write)
        object.__setattr__(
            forged_write,
            "genres",
            (SimpleNamespace(label="", score=0.5),),
        )
        rejected = repository.save_maest_results((forged_write,))[0]
        assert not rejected.ok
        assert rejected.error is not None
        assert "invalid MAEST analysis row" in rejected.error

    with repository.connect() as core:
        core.execute(
            "UPDATE maest_scores SET genres_json = ? WHERE track_id = ?",
            (genres_json, target.track_id),
        )

    candidates = repository.list_analysis_candidates((analysis,))
    assert [candidate.target for candidate in candidates] == [target]
    assert candidates[0].missing_outputs == (analysis,)
    summary = repository.get_track_summaries((target.track_id,))[0]
    assert not summary.analysis_coverage.maest_analysis
    detail = repository.get_track_detail(target.track_id)
    assert not detail.analysis_coverage.maest_analysis
    assert detail.maest is None
    assert repository.library_summary().maest_analysis == 0
    assert repository.list_genre_tag_candidates() == ()


def _sonara_contracts(build_digit: str = "5") -> SonaraContractSet:
    runtime = SonaraRuntimeIdentity(
        package_version=SONARA_EXPECTED_VERSION,
        package_build_id="sha256:" + build_digit * 64,
        schema_version=SONARA_EXPECTED_SCHEMA_VERSION,
        mode="playlist",
        sample_rate_hz=22_050,
        bpm_min=70,
        bpm_max=180,
        project_feature_revision=SONARA_PROJECT_FEATURE_REVISION,
        decoder_backend="sonara-symphonia",
        execution_path="analyze_batch",
        analysis_hop_samples=512,
        unit_interval_clamp_policy=SONARA_UNIT_INTERVAL_CLAMP_POLICY,
        unit_interval_clamp_epsilon=SONARA_UNIT_INTERVAL_CLAMP_EPSILON,
        unit_interval_clamp_fields=SONARA_UNIT_INTERVAL_CLAMP_FIELDS,
        vocalness_model_id="sonara-vocalness",
        vocalness_model_build_id="sha256:" + "6" * 64,
        embedding_version=2,
        embedding_dim=48,
        embedding_normalization="none",
        embedding_encoding=FLOAT32_LE_ENCODING,
        fingerprint_version=1,
        fingerprint_encoding="uint32-le",
        fingerprint_byte_order="little",
        core_requested_features=SONARA_CORE_REQUESTED_FEATURES,
        timeline_requested_features=SONARA_TIMELINE_REQUESTED_FEATURES,
        embedding_requested_features=SONARA_EMBEDDING_REQUESTED_FEATURES,
        fingerprint_requested_features=SONARA_FINGERPRINT_REQUESTED_FEATURES,
    )
    return build_sonara_contracts(runtime)


def _prepare_release(
    repository: _Repository,
    build_digit: str = "5",
) -> dict[str, object]:
    sonara_module = type(
        "_FakeSonara",
        (),
        {
            "__version__": SONARA_EXPECTED_VERSION,
            "SIMILARITY_VERSION": 2,
            "__sonara_build_id__": "sha256:" + build_digit * 64,
            "__sonara_vocalness_model_id__": "sonara-vocalness",
            "__sonara_vocalness_model_build_id__": "sha256:" + "6" * 64,
        },
    )
    backup_dir = repository.path.parent / "sonara-backups"
    backup_dir.mkdir(exist_ok=True)
    return prepare_sonara_release(
        repository,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=sonara_module,
    )


def _sonara_row(
    target: AnalysisTarget,
    contract: ContractIdentity,
) -> SonaraRowV7:
    values = {field.name: None for field in fields(SonaraRowV7)}
    values.update(
        {
            "track_id": target.track_id,
            "content_generation": target.content_generation,
            "contract_hash": contract.contract_hash,
            "detected_bpm": 128.0,
            "mfcc_mean_blob": np.zeros(13, dtype="<f4").tobytes(),
            "chroma_mean_blob": np.zeros(12, dtype="<f4").tobytes(),
            "spectral_contrast_mean_blob": np.zeros(
                7,
                dtype="<f4",
            ).tobytes(),
            "analyzed_at": _NOW,
        }
    )
    return SonaraRowV7(**values)


def _sonara_outputs(
    contracts: SonaraContractSet,
) -> tuple[AnalysisOutput, ...]:
    return tuple(AnalysisOutput(contract) for contract in contracts.identities)


def _sonara_write(
    target: AnalysisTarget,
    contracts: SonaraContractSet,
) -> SonaraWrite:
    return SonaraWrite(
        target=target,
        core_contract=contracts.core,
        core=_sonara_row(target, contracts.core),
        timeline=SonaraTimelineOutput(
            contract=contracts.timeline,
            payload={
                "beats": [0, 22, 43],
                "onset_frames": [0, 11, 22, 33, 43],
                "chord_sequence": ["Am", "C", "G"],
                "chord_events": [
                    {
                        "label": "Am",
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                    }
                ],
                "tempo_curve": [128.0, 128.0],
                "downbeats": [0, 43],
                "energy_curve": [0.2, 0.5, 0.8],
                "segments": [
                    {
                        "start_sec": 0.0,
                        "end_sec": 1.0,
                        "energy": 0.5,
                    }
                ],
                "loudness_curve": [-12.0, -10.0, -11.0],
            },
            analyzed_at=_NOW,
        ),
        similarity_embedding=EmbeddingOutput(
            contract=contracts.embedding,
            vector=np.linspace(0.0, 1.0, 48, dtype=np.float32),
            analyzed_at=_NOW,
        ),
        fingerprint=SonaraFingerprintOutput(
            contract=contracts.fingerprint,
            fingerprint_version="1",
            words=(1, 2, 3, 2**32 - 1),
            analyzed_at=_NOW,
        ),
    )


@pytest.mark.parametrize(
    ("changes", "error_pattern"),
    (
        ({"project_feature_revision": 5}, "project_feature_revision"),
        ({"analysis_hop_samples": 256}, "analysis_hop_samples"),
        ({"unit_interval_clamp_policy": "none"}, "clamp_policy"),
        ({"unit_interval_clamp_epsilon": 0.01}, "clamp_epsilon"),
        (
            {"unit_interval_clamp_fields": (SONARA_UNIT_INTERVAL_CLAMP_FIELDS[:-1])},
            "clamp_fields",
        ),
    ),
)
def test_sonara_contract_gate_requires_exact_revision_six_clamp_identity(
    repository: _Repository,
    changes: dict[str, object],
    error_pattern: str,
) -> None:
    runtime = replace(_sonara_contracts().runtime, **changes)
    outputs = _sonara_outputs(build_sonara_contracts(runtime))

    with pytest.raises(ValueError, match=error_pattern):
        repository.register_analysis_outputs(outputs)


def test_register_sonara_outputs_cannot_establish_unprepared_release(
    repository: _Repository,
) -> None:
    outputs = _sonara_outputs(_sonara_contracts())

    with pytest.raises(
        InactiveAnalysisOutputError,
        match="prepare-sonara-release",
    ):
        repository.register_analysis_outputs(outputs)

    with repository.connect() as core:
        assert (
            core.execute(
                """
            SELECT COUNT(*)
            FROM library_settings
            WHERE setting_key = 'sonara.active_release_hash'
               OR setting_key LIKE 'analysis.active.sonara.%'
            """
            ).fetchone()[0]
            == 0
        )
        assert core.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] == 0


def test_activate_sonara_release_requires_validated_preparation_receipt(
    repository: _Repository,
) -> None:
    outputs = _sonara_outputs(_sonara_contracts())

    for kwargs in ({}, {"preparation_proof": object()}):
        with pytest.raises(
            RuntimeError,
            match="validated prepare-sonara-release receipt",
        ):
            repository.activate_sonara_release(outputs, **kwargs)

    with repository.connect() as core:
        assert (
            core.execute(
                """
            SELECT COUNT(*)
            FROM library_settings
            WHERE setting_key = 'sonara.active_release_hash'
               OR setting_key LIKE 'analysis.active.sonara.%'
            """
            ).fetchone()[0]
            == 0
        )
        assert core.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] == 0


@pytest.mark.parametrize(
    "feature_field",
    (
        "core_requested_features",
        "timeline_requested_features",
        "embedding_requested_features",
        "fingerprint_requested_features",
    ),
)
def test_sonara_release_gate_rejects_self_consistent_bogus_feature_profile(
    repository: _Repository,
    feature_field: str,
) -> None:
    runtime = replace(
        _sonara_contracts().runtime,
        **{feature_field: ("bogus_project_feature",)},
    )
    outputs = _sonara_outputs(build_sonara_contracts(runtime))

    with pytest.raises(ValueError, match="internally derived canonical release"):
        repository.register_analysis_outputs(outputs)


def test_sonara_typed_core_and_optional_artifacts(
    repository: _Repository,
) -> None:
    target = _insert_track(repository)
    contract_set = _sonara_contracts()
    contracts = {
        kind: contract_set.for_output(kind)
        for kind in ("core", "timeline", "embedding", "fingerprint")
    }
    outputs = _sonara_outputs(contract_set)
    _prepare_release(repository)

    write = _sonara_write(target, contract_set)
    assert repository.save_sonara_results((write,))[0].ok
    assert repository.list_analysis_candidates(outputs) == []

    with repository.connect() as core:
        core_row = core.execute(
            """
            SELECT contract_hash, content_generation, detected_bpm
            FROM sonara
            WHERE track_id = ?
            """,
            (target.track_id,),
        ).fetchone()
    assert tuple(core_row) == (
        contracts["core"].contract_hash,
        1,
        128.0,
    )
    with repository.connect_artifacts() as artifacts:
        counts = tuple(
            artifacts.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "sonara_timeline",
                "sonara_similarity_embeddings",
                "sonara_fingerprints",
            )
        )
    assert counts == (1, 1, 1)


def test_sonara_typed_core_and_optional_artifacts_persist_exact_contract_hashes(
    repository: _Repository,
) -> None:
    target = _insert_track(repository)
    contract_set = _sonara_contracts()
    _prepare_release(repository)

    assert repository.save_sonara_results((_sonara_write(target, contract_set),))[0].ok

    with repository.connect() as core:
        core_hash = core.execute(
            "SELECT contract_hash FROM sonara WHERE track_id = ?",
            (target.track_id,),
        ).fetchone()["contract_hash"]
    with repository.connect_artifacts() as artifacts:
        artifact_hashes = {
            table: artifacts.execute(
                f"SELECT contract_hash FROM {table} WHERE track_id = ?",
                (target.track_id,),
            ).fetchone()["contract_hash"]
            for table in (
                "sonara_timeline",
                "sonara_similarity_embeddings",
                "sonara_fingerprints",
            )
        }

    assert core_hash == contract_set.core.contract_hash
    assert artifact_hashes == {
        "sonara_timeline": contract_set.timeline.contract_hash,
        "sonara_similarity_embeddings": contract_set.embedding.contract_hash,
        "sonara_fingerprints": contract_set.fingerprint.contract_hash,
    }


def test_activate_sonara_release_clears_every_prior_release_row(
    repository: _Repository,
) -> None:
    target = _insert_track(repository)
    old_contracts = _sonara_contracts("5")
    _prepare_release(repository, "5")
    assert repository.save_sonara_results((_sonara_write(target, old_contracts),))[0].ok

    with repository.connect() as core:
        core.execute(
            """
            INSERT INTO classifier_scores (
                track_id, classifier_key, content_generation, model_id,
                feature_set, feature_manifest_hash, required_outputs_hash,
                uses_sonara,
                sonara_release_hash, positive_label, predicted_class,
                score_bucket, score, confidence, probabilities_json,
                analyzed_at
            ) VALUES (?, 'voice_presence', 1, 'voice-v1', 'sonara',
                      ?, ?, 1, ?, 'voice', 'voice', 'high',
                      0.9, 0.8, '{"no_voice":0.1,"voice":0.9}', ?)
            """,
            (
                target.track_id,
                "sha256:" + "8" * 64,
                "sha256:" + "7" * 64,
                old_contracts.release_hash,
                _NOW,
            ),
        )

    new_contracts = _sonara_contracts("9")
    new_outputs = _sonara_outputs(new_contracts)
    with pytest.raises(
        InactiveAnalysisOutputError,
        match="activate_sonara_release",
    ):
        repository.register_analysis_outputs(new_outputs)

    receipt = _prepare_release(repository, "9")
    assert receipt["activation_result"] == {
        "core_rows_deleted": 1,
        "artifact_rows_deleted": 3,
        "classifier_rows_deleted": 1,
    }
    for output in new_outputs:
        assert (
            repository.active_analysis_output(
                output.contract.analysis_family,
                output.contract.output_kind,
            )
            == output
        )

    with repository.connect() as core:
        assert core.execute("SELECT COUNT(*) FROM sonara").fetchone()[0] == 0
        assert core.execute("SELECT COUNT(*) FROM classifier_scores").fetchone()[0] == 0
    with repository.connect_artifacts() as artifacts:
        counts = tuple(
            artifacts.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "sonara_timeline",
                "sonara_similarity_embeddings",
                "sonara_fingerprints",
            )
        )
    assert counts == (0, 0, 0)
    assert (
        repository.list_analysis_candidates(new_outputs)[0].missing_outputs
        == new_outputs
    )

    assert repository.save_sonara_results((_sonara_write(target, new_contracts),))[0].ok
    with repository.connect() as core:
        core.execute(
            """
            INSERT INTO classifier_scores (
                track_id, classifier_key, content_generation, model_id,
                feature_set, feature_manifest_hash, required_outputs_hash,
                uses_sonara,
                sonara_release_hash, positive_label, predicted_class,
                score_bucket, score, confidence, probabilities_json,
                analyzed_at
            ) VALUES (?, 'voice_presence', 1, 'voice-v2', 'sonara',
                      ?, ?, 1, ?, 'voice', 'voice', 'high',
                      0.9, 0.8, '{"no_voice":0.1,"voice":0.9}', ?)
            """,
            (
                target.track_id,
                "sha256:" + "a" * 64,
                "sha256:" + "b" * 64,
                new_contracts.release_hash,
                _NOW,
            ),
        )

    repeated = _prepare_release(repository, "9")
    assert repeated == receipt
    with repository.connect() as core:
        assert core.execute("SELECT COUNT(*) FROM sonara").fetchone()[0] == 1
        assert core.execute("SELECT COUNT(*) FROM classifier_scores").fetchone()[0] == 1
        core.execute(
            """
            DELETE FROM library_settings
            WHERE setting_key = ?
            """,
            ("analysis.active_contract.sonara.fingerprint",),
        )
    mismatched = _prepare_release(repository, "a")
    assert mismatched["activation_result"] == {
        "core_rows_deleted": 1,
        "artifact_rows_deleted": 3,
        "classifier_rows_deleted": 1,
    }


def test_classifier_readiness_save_and_scoped_stale_cleanup(
    repository: _Repository,
) -> None:
    target = _insert_track(repository)
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    repository.save_embedding_results((_embedding_write(target, output),))
    specification = ClassifierSpecification(
        classifier_key="voice_presence",
        model_id="voice-v1",
        feature_set="mert",
        feature_manifest_hash="sha256:" + "8" * 64,
        required_outputs_hash=classifier_required_outputs_hash((output,)),
        feature_names=("mert:0",),
        required_outputs=(output,),
        label_order=("no_voice", "voice"),
        positive_label="voice",
    )
    readiness = repository.classifier_candidate_readiness(specification)
    assert readiness.candidate_tracks == 1
    features = repository.load_classifier_feature_rows(
        specification,
        targets=(target,),
    )
    np.testing.assert_array_equal(
        features[0].vector,
        np.asarray([1.0], dtype=np.float32),
    )

    score = ClassifierScoreV7(
        track_id=target.track_id,
        classifier_key=specification.classifier_key,
        content_generation=target.content_generation,
        model_id=specification.model_id,
        feature_set=specification.feature_set,
        feature_manifest_hash=specification.feature_manifest_hash,
        required_outputs_hash=specification.required_outputs_hash,
        uses_sonara=0,
        sonara_release_hash=None,
        positive_label=specification.positive_label,
        predicted_class="voice",
        score_bucket="high",
        score=0.9,
        confidence=0.9,
        probabilities_json='{"no_voice":0.1,"voice":0.9}',
        analyzed_at=_NOW,
    )
    assert repository.save_classifier_scores(
        (
            ClassifierScoreWrite(
                target=target,
                specification=specification,
                score=score,
            ),
        )
    )[0].ok
    readiness = repository.classifier_candidate_readiness(specification)
    assert readiness.already_scored_tracks == 1
    assert readiness.candidate_tracks == 0

    changed = ClassifierSpecification(
        classifier_key=specification.classifier_key,
        model_id="voice-v2",
        feature_set=specification.feature_set,
        feature_manifest_hash="sha256:" + "9" * 64,
        required_outputs_hash=specification.required_outputs_hash,
        feature_names=specification.feature_names,
        required_outputs=specification.required_outputs,
        label_order=specification.label_order,
        positive_label=specification.positive_label,
    )
    assert repository.prepare_classifier_rescore(changed) == 1
    assert repository.classifier_candidate_readiness(changed).candidate_tracks == 1


def test_ml_activation_cleans_only_scores_with_stale_required_output(
    repository: _Repository,
) -> None:
    target = _insert_track(repository)
    mert = _mert_output()
    stale_mert = _mert_output(
        model_version="3" * 40,
        checkpoint_id="sha256:" + "3" * 64,
    )
    clap = _clap_output()
    repository.register_analysis_outputs((mert, clap))

    def score_write(
        classifier_key: str,
        output: AnalysisOutput,
    ) -> ClassifierScoreWrite:
        specification = ClassifierSpecification(
            classifier_key=classifier_key,
            model_id=f"{classifier_key}-model",
            feature_set=output.contract.analysis_family,
            feature_manifest_hash="sha256:" + "4" * 64,
            required_outputs_hash=classifier_required_outputs_hash((output,)),
            feature_names=(f"{output.contract.analysis_family}:0",),
            required_outputs=(output,),
            label_order=("negative", "positive"),
            positive_label="positive",
        )
        return ClassifierScoreWrite(
            target=target,
            specification=specification,
            score=ClassifierScoreV7(
                track_id=target.track_id,
                classifier_key=classifier_key,
                content_generation=target.content_generation,
                model_id=specification.model_id,
                feature_set=specification.feature_set,
                feature_manifest_hash=(specification.feature_manifest_hash),
                required_outputs_hash=(specification.required_outputs_hash),
                uses_sonara=0,
                sonara_release_hash=None,
                positive_label="positive",
                predicted_class="positive",
                score_bucket="high",
                score=0.8,
                confidence=0.8,
                probabilities_json=('{"negative":0.2,"positive":0.8}'),
                analyzed_at=_NOW,
            ),
        )

    writes = (
        score_write("mert_classifier", mert),
        score_write("clap_classifier", clap),
    )
    assert all(result.ok for result in repository.save_classifier_scores(writes))

    with repository.connect() as core:
        core.execute(
            """
            UPDATE classifier_scores
            SET required_outputs_hash = ?
            WHERE classifier_key = 'mert_classifier'
            """,
            (classifier_required_outputs_hash((stale_mert,)),),
        )

    repository.register_analysis_outputs((mert,))

    with repository.connect() as core:
        remaining = core.execute(
            """
            SELECT classifier_key, required_outputs_hash
            FROM classifier_scores
            ORDER BY classifier_key
            """
        ).fetchall()
    assert [tuple(row) for row in remaining] == [
        (
            "clap_classifier",
            classifier_required_outputs_hash((clap,)),
        )
    ]
