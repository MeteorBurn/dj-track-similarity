"""Focused end-to-end tests for the clean-v7 QA harness."""

from __future__ import annotations

import json
import sqlite3
import struct
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from dj_track_similarity.analysis_contracts import (
    FLOAT32_LE_ENCODING,
    ContractIdentity,
    register_contract,
    utc_timestamp,
)
from dj_track_similarity.analysis_models import (
    ACTIVE_CONTRACT_SETTING_PREFIX,
    AnalysisOutput,
    classifier_required_outputs_hash,
)
from dj_track_similarity.db_artifacts import create_artifacts_sidecar_schema
from dj_track_similarity.db_evaluation_sidecar import (
    create_evaluation_sidecar_schema,
)
from dj_track_similarity.db_schema import (
    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
    insert_library_catalog,
)
from dj_track_similarity.db_schema_v7 import create_v7_schema
from dj_track_similarity.db_storage import storage_database_paths

_SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import qa_schema_v7  # noqa: E402


ACTIVE_RELEASE = "sha256:active-sonara-release"
OTHER_RELEASE = "sha256:other-sonara-release"
DIM = 4


@dataclass(frozen=True)
class Bundle:
    core: Path
    artifacts: Path
    catalog_uuid: str
    track_id: int
    track_uuid: str
    contracts: dict[str, ContractIdentity]


def _float_blob(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _identity(
    family: str,
    output_kind: str,
    *,
    release_hash: str | None = None,
    normalization: str | None = None,
) -> ContractIdentity:
    is_embedding = output_kind == "embedding"
    return ContractIdentity(
        analysis_family=family,
        output_kind=output_kind,
        model_name=f"{family}-{output_kind}",
        model_version="test-v1",
        release_hash=release_hash,
        dim=DIM if is_embedding else None,
        encoding=FLOAT32_LE_ENCODING if is_embedding else None,
        normalization=normalization if is_embedding else None,
        checkpoint_id=f"{family}-checkpoint",
        preprocessing="test-preprocessing",
        parameters={"fixture": True},
    )


def _contract_set() -> dict[str, ContractIdentity]:
    identities = [
        _identity("sonara", "core", release_hash=ACTIVE_RELEASE),
        _identity("sonara", "timeline", release_hash=ACTIVE_RELEASE),
        _identity("sonara", "fingerprint", release_hash=ACTIVE_RELEASE),
        _identity(
            "sonara",
            "embedding",
            release_hash=ACTIVE_RELEASE,
            normalization="l2",
        ),
        _identity("maest", "analysis"),
        _identity("maest", "embedding", normalization="l2"),
        _identity("mert", "embedding", normalization="l2"),
        _identity("muq", "embedding", normalization="l2"),
        _identity("clap", "embedding", normalization="l2"),
    ]
    return {
        f"{identity.analysis_family}/{identity.output_kind}": identity
        for identity in identities
    }


def _insert_track(
    connection: sqlite3.Connection,
    *,
    file_path: str,
    now: str,
) -> tuple[int, str]:
    track_uuid = str(uuid.uuid4())
    cursor = connection.execute(
        """
        INSERT INTO tracks(
            track_uuid, file_path, file_size_bytes, file_modified_ns,
            content_generation, last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, 1024, 1700000000000000000, 1, ?, ?, ?)
        """,
        (track_uuid, file_path, now, now, now),
    )
    return int(cursor.lastrowid), track_uuid


def _insert_sonara(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    contract_hash: str,
    now: str,
) -> None:
    connection.execute(
        """
        INSERT INTO sonara(
            track_id, content_generation, contract_hash,
            mfcc_mean_blob, chroma_mean_blob,
            spectral_contrast_mean_blob, analyzed_at
        ) VALUES (?, 1, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            contract_hash,
            _float_blob([0.1] * 13),
            _float_blob([0.2] * 12),
            _float_blob([0.3] * 7),
            now,
        ),
    )


def _insert_classifier(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    now: str,
    required_outputs_hash: str,
    model_id: str = "model-v1",
    probabilities_json: str = '{"calm":0.2,"energetic":0.8}',
) -> None:
    connection.execute(
        """
        INSERT INTO classifier_scores(
            track_id, classifier_key, content_generation,
            model_id, feature_set, feature_manifest_hash,
            required_outputs_hash,
            uses_sonara, sonara_release_hash,
            positive_label, predicted_class, score_bucket,
            score, confidence, probabilities_json, analyzed_at
        ) VALUES (
            ?, 'energy', 1,
            ?, 'sonara+mert', 'sha256:fixture-manifest', ?,
            1, ?,
            'energetic', 'energetic', 'high',
            0.8, 0.8, ?, ?
        )
        """,
        (
            track_id,
            model_id,
            required_outputs_hash,
            ACTIVE_RELEASE,
            probabilities_json,
            now,
        ),
    )


def _build_healthy_bundle(tmp_path: Path) -> Bundle:
    core_path = tmp_path / "library.sqlite"
    paths = storage_database_paths(core_path)
    catalog_uuid = str(uuid.uuid4())
    contracts = _contract_set()
    now = utc_timestamp()

    with sqlite3.connect(core_path) as core:
        core.execute("PRAGMA foreign_keys = ON")
        create_v7_schema(core)
        insert_library_catalog(core, catalog_uuid, created_at=now)
        core.execute(
            """
            INSERT INTO library_settings(setting_key, setting_value, updated_at)
            VALUES (?, ?, ?)
            """,
            (SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY, ACTIVE_RELEASE, now),
        )
        for identity in contracts.values():
            register_contract(core, identity, created_at=now)
            core.execute(
                """
                INSERT INTO library_settings(
                    setting_key, setting_value, updated_at
                ) VALUES (?, ?, ?)
                """,
                (
                    f"{ACTIVE_CONTRACT_SETTING_PREFIX}."
                    f"{identity.analysis_family}.{identity.output_kind}",
                    identity.contract_hash,
                    now,
                ),
            )

        track_id, track_uuid = _insert_track(
            core,
            file_path="/music/track-1.wav",
            now=now,
        )
        core.execute(
            """
            INSERT INTO file_tags(
                track_id, title, artist, genres_json, tags_read_at
            ) VALUES (?, 'Track One', 'Artist', '[]', ?)
            """,
            (track_id, now),
        )
        _insert_sonara(
            core,
            track_id=track_id,
            contract_hash=contracts["sonara/core"].contract_hash,
            now=now,
        )
        core.execute(
            """
            INSERT INTO maest_scores(
                track_id, content_generation, contract_hash,
                syncopated_rhythm, genres_json, analyzed_at
            ) VALUES (?, 1, ?, 1, '["electronic"]', ?)
            """,
            (track_id, contracts["maest/analysis"].contract_hash, now),
        )
        _insert_classifier(
            core,
            track_id=track_id,
            now=now,
            required_outputs_hash=classifier_required_outputs_hash(
                (
                    AnalysisOutput(contracts["sonara/core"]),
                    AnalysisOutput(contracts["mert/embedding"]),
                )
            ),
        )

    create_artifacts_sidecar_schema(
        str(paths.artifacts),
        catalog_uuid=catalog_uuid,
    )
    unit_vector = _float_blob([1.0, 0.0, 0.0, 0.0])
    embedding_tables = {
        "maest_embeddings": contracts["maest/embedding"],
        "mert_embeddings": contracts["mert/embedding"],
        "muq_embeddings": contracts["muq/embedding"],
        "clap_embeddings": contracts["clap/embedding"],
        "sonara_similarity_embeddings": contracts["sonara/embedding"],
    }
    with sqlite3.connect(paths.artifacts) as artifacts:
        for table, identity in embedding_tables.items():
            artifacts.execute(
                f"""
                INSERT INTO "{table}"(
                    track_id, track_uuid, content_generation, contract_hash,
                    dim, normalization, embedding_blob, analyzed_at
                ) VALUES (?, ?, 1, ?, ?, 'l2', ?, ?)
                """,
                (
                    track_id,
                    track_uuid,
                    identity.contract_hash,
                    DIM,
                    unit_vector,
                    now,
                ),
            )
        artifacts.execute(
            """
            INSERT INTO sonara_timeline(
                track_id, track_uuid, content_generation, contract_hash,
                payload_json, analyzed_at
            ) VALUES (?, ?, 1, ?, '{"beats":[]}', ?)
            """,
            (
                track_id,
                track_uuid,
                contracts["sonara/timeline"].contract_hash,
                now,
            ),
        )
        artifacts.execute(
            """
            INSERT INTO sonara_fingerprints(
                track_id, track_uuid, content_generation, contract_hash,
                fingerprint_version, word_count, byte_order,
                fingerprint_blob, analyzed_at
            ) VALUES (?, ?, 1, ?, 'test-v1', 2, 'little', ?, ?)
            """,
            (
                track_id,
                track_uuid,
                contracts["sonara/fingerprint"].contract_hash,
                struct.pack("<II", 1, 2),
                now,
            ),
        )

    return Bundle(
        core=core_path,
        artifacts=paths.artifacts,
        catalog_uuid=catalog_uuid,
        track_id=track_id,
        track_uuid=track_uuid,
        contracts=contracts,
    )


def _run_default(bundle: Bundle) -> int:
    return qa_schema_v7.run_qa(bundle.core, None, None)


def _assert_failure(
    bundle: Bundle,
    capsys: pytest.CaptureFixture[str],
    *needles: str,
) -> None:
    assert _run_default(bundle) == 1
    output = capsys.readouterr().out.lower()
    assert "fail:" in output
    for needle in needles:
        assert needle.lower() in output


def test_qa_passes_clean_v7_bundle_with_canonical_default_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)

    assert bundle.artifacts.name == "library.artifacts.sqlite"
    assert _run_default(bundle) == 0
    output = capsys.readouterr().out
    assert "QA PASSED" in output
    assert str(bundle.artifacts) in output
    assert not (tmp_path / "library.sqlite.artifacts.sqlite").exists()


def test_qa_requires_artifacts_and_never_uses_legacy_double_suffix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    legacy_wrong_path = tmp_path / "library.sqlite.artifacts.sqlite"
    bundle.artifacts.replace(legacy_wrong_path)

    _assert_failure(bundle, capsys, "required artifacts", "not found")
    assert not bundle.artifacts.exists()
    assert legacy_wrong_path.exists()


def test_qa_rejects_artifacts_catalog_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    bundle.artifacts.unlink()
    create_artifacts_sidecar_schema(
        str(bundle.artifacts),
        catalog_uuid=str(uuid.uuid4()),
    )

    _assert_failure(bundle, capsys, "artifacts", "another library catalog")


def test_qa_rejects_artifacts_schema_definition_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.artifacts) as connection:
        connection.execute("CREATE TABLE unexpected(value TEXT)")

    _assert_failure(bundle, capsys, "artifacts", "table set mismatch")


def test_qa_rejects_artifacts_definition_fingerprint_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.artifacts) as connection:
        connection.execute("DROP INDEX idx_mert_embeddings_track_uuid")
        connection.execute(
            """
            CREATE INDEX idx_mert_embeddings_track_uuid
            ON mert_embeddings(track_uuid DESC)
            """
        )

    _assert_failure(
        bundle,
        capsys,
        "artifacts",
        "definition fingerprint mismatch",
    )


def test_qa_rejects_contract_self_hash_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    identity = _identity("mert", "embedding", normalization="l2")
    with sqlite3.connect(bundle.core) as core:
        core.execute(
            """
            INSERT INTO contracts(
                contract_hash, analysis_family, output_kind, model_name,
                model_version, release_hash, canonical_payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "sha256:" + ("f" * 64),
                identity.analysis_family,
                identity.output_kind,
                identity.model_name,
                identity.model_version,
                identity.release_hash,
                identity.canonical_payload_json,
                utc_timestamp(),
            ),
        )

    _assert_failure(bundle, capsys, "contract registry", "self-hash")


def test_qa_rejects_contract_registry_columns_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    identity = ContractIdentity(
        analysis_family="mert",
        output_kind="embedding",
        model_name="canonical-mert",
        dim=DIM,
        encoding=FLOAT32_LE_ENCODING,
        normalization="l2",
    )
    with sqlite3.connect(bundle.core) as core:
        core.execute(
            """
            INSERT INTO contracts(
                contract_hash, analysis_family, output_kind, model_name,
                model_version, release_hash, canonical_payload_json, created_at
            ) VALUES (?, 'maest', 'embedding', 'wrong-columns',
                      NULL, NULL, ?, ?)
            """,
            (
                identity.contract_hash,
                identity.canonical_payload_json,
                utc_timestamp(),
            ),
        )

    _assert_failure(bundle, capsys, "contract registry", "columns")


@pytest.mark.parametrize(
    ("case", "needles"),
    [
        ("orphan_track", ("mert_embeddings", "orphan track_id")),
        ("track_uuid", ("mert_embeddings", "track_uuid mismatch")),
        ("generation", ("mert_embeddings", "content_generation mismatch")),
        ("unregistered_contract", ("mert_embeddings", "unregistered contract")),
        ("wrong_contract_family", ("mert_embeddings", "expected mert/embedding")),
        ("dim", ("mert_embeddings", "dim mismatch")),
        ("normalization", ("mert_embeddings", "normalization mismatch")),
        ("blob_length", ("mert_embeddings", "blob length mismatch")),
        ("nonfinite", ("mert_embeddings", "non-finite")),
        ("l2", ("mert_embeddings", "not unit-normalized")),
    ],
)
def test_qa_rejects_one_artifact_invariant_at_a_time(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: str,
    needles: tuple[str, ...],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.artifacts) as artifacts:
        if case == "orphan_track":
            artifacts.execute(
                "UPDATE mert_embeddings SET track_id = 999 WHERE track_id = ?",
                (bundle.track_id,),
            )
        elif case == "track_uuid":
            artifacts.execute("UPDATE mert_embeddings SET track_uuid = 'wrong-uuid'")
        elif case == "generation":
            artifacts.execute("UPDATE mert_embeddings SET content_generation = 2")
        elif case == "unregistered_contract":
            artifacts.execute(
                "UPDATE mert_embeddings SET contract_hash = ?",
                ("sha256:" + ("0" * 64),),
            )
        elif case == "wrong_contract_family":
            artifacts.execute(
                "UPDATE mert_embeddings SET contract_hash = ?",
                (bundle.contracts["clap/embedding"].contract_hash,),
            )
        elif case == "dim":
            artifacts.execute(
                """
                UPDATE mert_embeddings
                SET dim = 2, embedding_blob = ?
                """,
                (_float_blob([1.0, 0.0]),),
            )
        elif case == "normalization":
            artifacts.execute("UPDATE mert_embeddings SET normalization = 'none'")
        elif case == "blob_length":
            artifacts.execute("PRAGMA ignore_check_constraints = ON")
            artifacts.execute(
                "UPDATE mert_embeddings SET embedding_blob = ?",
                (_float_blob([1.0, 0.0, 0.0]),),
            )
        elif case == "nonfinite":
            artifacts.execute(
                "UPDATE mert_embeddings SET embedding_blob = ?",
                (_float_blob([float("nan"), 0.0, 0.0, 1.0]),),
            )
        else:
            artifacts.execute(
                "UPDATE mert_embeddings SET embedding_blob = ?",
                (_float_blob([1.0, 1.0, 0.0, 0.0]),),
            )

    _assert_failure(bundle, capsys, *needles)


def test_qa_rejects_sonara_core_release_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        core.execute(
            """
            UPDATE library_settings SET setting_value = ?
            WHERE setting_key = ?
            """,
            (OTHER_RELEASE, SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY),
        )

    _assert_failure(bundle, capsys, "sonara", "release mismatch")


def test_qa_rejects_stale_core_analysis_generation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        core.execute("UPDATE sonara SET content_generation = 2")

    _assert_failure(bundle, capsys, "sonara", "content_generation mismatch")


def test_qa_rejects_sonara_artifact_from_non_active_release(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    other_identity = _identity(
        "sonara",
        "embedding",
        release_hash=OTHER_RELEASE,
        normalization="l2",
    )
    with sqlite3.connect(bundle.core) as core:
        register_contract(core, other_identity, created_at=utc_timestamp())
    with sqlite3.connect(bundle.artifacts) as artifacts:
        artifacts.execute(
            "UPDATE sonara_similarity_embeddings SET contract_hash = ?",
            (other_identity.contract_hash,),
        )

    _assert_failure(
        bundle,
        capsys,
        "sonara_similarity_embeddings",
        "release mismatch",
    )


def test_qa_rejects_stale_classifier_generation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        core.execute("UPDATE classifier_scores SET content_generation = 2")

    _assert_failure(
        bundle,
        capsys,
        "classifier_scores",
        "content_generation mismatch",
    )


def test_qa_rejects_mixed_classifier_identity(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    now = utc_timestamp()
    with sqlite3.connect(bundle.core) as core:
        core.execute("PRAGMA foreign_keys = ON")
        track_id, _ = _insert_track(
            core,
            file_path="/music/track-2.wav",
            now=now,
        )
        _insert_sonara(
            core,
            track_id=track_id,
            contract_hash=bundle.contracts["sonara/core"].contract_hash,
            now=now,
        )
        _insert_classifier(
            core,
            track_id=track_id,
            model_id="model-v2",
            now=now,
            required_outputs_hash=classifier_required_outputs_hash(
                (
                    AnalysisOutput(bundle.contracts["sonara/core"]),
                    AnalysisOutput(bundle.contracts["mert/embedding"]),
                )
            ),
        )

    _assert_failure(bundle, capsys, "classifier identity")


def test_qa_rejects_inactive_classifier_required_outputs_hash(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        core.execute(
            """
            UPDATE classifier_scores
            SET required_outputs_hash = ?
            """,
            ("sha256:" + "f" * 64,),
        )

    _assert_failure(
        bundle,
        capsys,
        "required_outputs_hash",
        "active analysis contracts",
    )


def test_qa_rejects_nonfinite_classifier_probability(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        core.execute(
            """
            UPDATE classifier_scores
            SET probabilities_json = '{"calm":0.0,"energetic":1e999}'
            """
        )

    _assert_failure(bundle, capsys, "probability", "non-finite")


def test_qa_rejects_classifier_probabilities_that_do_not_sum_to_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    probabilities = json.dumps({"calm": 0.1, "energetic": 0.8})
    with sqlite3.connect(bundle.core) as core:
        core.execute(
            "UPDATE classifier_scores SET probabilities_json = ?",
            (probabilities,),
        )

    _assert_failure(bundle, capsys, "probabilities do not sum to 1")


def test_qa_rejects_core_foreign_key_orphan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        core.execute("PRAGMA foreign_keys = OFF")
        core.execute(
            """
            INSERT INTO likes(track_id, liked_at)
            VALUES (999, ?)
            """,
            (utc_timestamp(),),
        )

    _assert_failure(bundle, capsys, "foreign-key")


def test_qa_validates_optional_evaluation_only_when_present(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    evaluation_path = storage_database_paths(bundle.core).evaluation

    assert _run_default(bundle) == 0
    assert not evaluation_path.exists()
    capsys.readouterr()

    create_evaluation_sidecar_schema(
        evaluation_path,
        catalog_uuid=str(uuid.uuid4()),
    )
    _assert_failure(bundle, capsys, "evaluation", "another library catalog")


def test_qa_runs_quick_check(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    original = qa_schema_v7._quick_check

    def fail_core_quick_check(
        connection: sqlite3.Connection,
        label: str,
    ) -> None:
        if label == "Core":
            raise qa_schema_v7.QAError("Core quick_check failed: injected")
        original(connection, label)

    monkeypatch.setattr(
        qa_schema_v7,
        "_quick_check",
        fail_core_quick_check,
    )

    _assert_failure(bundle, capsys, "quick_check", "injected")
