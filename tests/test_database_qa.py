from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from dj_track_similarity.analysis_models import current_embedding_spec
from dj_track_similarity.db_artifacts import create_artifacts_sidecar_schema
from dj_track_similarity.db_ddl import create_core_schema
from dj_track_similarity.db_evaluation_sidecar import (
    create_evaluation_sidecar_schema,
)
from dj_track_similarity.db_schema import insert_library_catalog
from dj_track_similarity.db_storage import storage_database_paths


_MODULE_PATH = Path(__file__).parents[1] / "scripts" / "qa_database.py"
_SPEC = importlib.util.spec_from_file_location("qa_database", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
qa_database = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(qa_database)

_NOW = "2026-07-30T00:00:00.000000Z"


@dataclass(frozen=True)
class Bundle:
    core: Path
    artifacts: Path
    evaluation: Path
    catalog_uuid: str
    track_id: int
    track_uuid: str


def _float_blob(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _insert_track(connection: sqlite3.Connection) -> tuple[int, str]:
    track_uuid = str(uuid.uuid4())
    cursor = connection.execute(
        """
        INSERT INTO tracks(
            track_uuid, file_path, file_size_bytes, file_modified_ns,
            content_generation, last_scanned_at, created_at, updated_at
        ) VALUES (?, '/music/track.wav', 4096, 123456789, 1, ?, ?, ?)
        """,
        (track_uuid, _NOW, _NOW, _NOW),
    )
    return int(cursor.lastrowid), track_uuid


def _insert_healthy_core_rows(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    track_uuid: str,
) -> None:
    connection.execute(
        """
        INSERT INTO file_tags(
            track_id, title, artist, genres_json, tags_read_at
        ) VALUES (?, 'Track', 'Artist', '["electronic"]', ?)
        """,
        (track_id, _NOW),
    )
    connection.execute(
        """
        INSERT INTO sonara(
            track_id, content_generation,
            mfcc_mean_blob, chroma_mean_blob, spectral_contrast_mean_blob,
            analyzed_at
        ) VALUES (?, 1, ?, ?, ?, ?)
        """,
        (
            track_id,
            _float_blob([0.1] * 13),
            _float_blob([0.2] * 12),
            _float_blob([0.3] * 7),
            _NOW,
        ),
    )
    connection.execute(
        """
        INSERT INTO maest_scores(
            track_id, content_generation, syncopated_rhythm,
            genres_json, analyzed_at
        ) VALUES (?, 1, 1, '["electronic"]', ?)
        """,
        (track_id, _NOW),
    )
    connection.execute(
        """
        INSERT INTO classifier_scores(
            track_id, track_uuid, classifier_key, content_generation,
            feature_set, feature_names_json, positive_label,
            predicted_class, score_bucket, score, confidence,
            probabilities_json, analyzed_at
        ) VALUES (
            ?, ?, 'energy', 1,
            'sonara+mert',
            '["sonara:energy_score","mert:0"]',
            'energetic', 'energetic', 'high', 0.8, 0.8,
            '{"calm":0.2,"energetic":0.8}', ?
        )
        """,
        (track_id, track_uuid, _NOW),
    )


def _build_healthy_bundle(tmp_path: Path) -> Bundle:
    core_path = tmp_path / "library.sqlite"
    paths = storage_database_paths(core_path)
    catalog_uuid = str(uuid.uuid4())
    with sqlite3.connect(core_path) as core:
        core.execute("PRAGMA foreign_keys = ON")
        create_core_schema(core)
        insert_library_catalog(core, catalog_uuid, created_at=_NOW)
        track_id, track_uuid = _insert_track(core)
        _insert_healthy_core_rows(
            core,
            track_id=track_id,
            track_uuid=track_uuid,
        )

    create_artifacts_sidecar_schema(
        str(paths.artifacts),
        catalog_uuid=catalog_uuid,
    )
    spec = current_embedding_spec("mert")
    vector = [0.0] * spec.dimension
    vector[0] = 1.0
    with sqlite3.connect(paths.artifacts) as artifacts:
        artifacts.execute(
            """
            INSERT INTO mert_embeddings(
                track_id, track_uuid, content_generation,
                dim, normalization, embedding_blob, analyzed_at
            ) VALUES (?, ?, 1, ?, ?, ?, ?)
            """,
            (
                track_id,
                track_uuid,
                spec.dimension,
                spec.normalization,
                _float_blob(vector),
                _NOW,
            ),
        )

    return Bundle(
        core=core_path,
        artifacts=paths.artifacts,
        evaluation=paths.evaluation,
        catalog_uuid=catalog_uuid,
        track_id=track_id,
        track_uuid=track_uuid,
    )


def _run_default(bundle: Bundle) -> int:
    return qa_database.run_qa(bundle.core, None, None)


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


def test_qa_passes_current_bundle_read_only_and_uses_canonical_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    hashes_before = {
        bundle.core: _file_hash(bundle.core),
        bundle.artifacts: _file_hash(bundle.artifacts),
    }

    assert _run_default(bundle) == 0

    output = capsys.readouterr().out
    assert "QA PASSED" in output
    assert str(bundle.artifacts) in output
    assert "contracts=" not in output
    assert not bundle.evaluation.exists()
    assert not (tmp_path / "library.sqlite.artifacts.sqlite").exists()
    assert {
        path: _file_hash(path) for path in hashes_before
    } == hashes_before


def test_qa_requires_artifacts_and_never_uses_legacy_double_suffix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    legacy_wrong_path = tmp_path / "library.sqlite.artifacts.sqlite"
    bundle.artifacts.replace(legacy_wrong_path)

    _assert_failure(bundle, capsys, "required artifacts", "not found")
    assert legacy_wrong_path.exists()
    assert not bundle.artifacts.exists()


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


@pytest.mark.parametrize("database", ["core", "artifacts"])
def test_qa_rejects_noncurrent_structure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    database: str,
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    path = bundle.core if database == "core" else bundle.artifacts
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unexpected(value TEXT)")

    _assert_failure(bundle, capsys, database, "structure")


def test_qa_rejects_stale_core_analysis_generation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        core.execute("UPDATE sonara SET content_generation = 2")

    _assert_failure(bundle, capsys, "sonara", "content_generation mismatch")


def test_qa_rejects_nonfinite_sonara_short_vector(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        core.execute(
            "UPDATE sonara SET mfcc_mean_blob = ?",
            (_float_blob([float("nan")] + [0.0] * 12),),
        )

    _assert_failure(bundle, capsys, "mfcc_mean_blob", "non-finite")


@pytest.mark.parametrize(
    ("case", "needles"),
    [
        ("orphan_track", ("mert_embeddings", "orphan track_id")),
        ("track_uuid", ("mert_embeddings", "track_uuid mismatch")),
        ("generation", ("mert_embeddings", "content_generation mismatch")),
        ("dim", ("mert_embeddings", "dim mismatch")),
        ("normalization", ("mert_embeddings", "normalization mismatch")),
        ("nonfinite", ("mert_embeddings", "non-finite")),
        ("l2", ("mert_embeddings", "unit-normalized")),
    ],
)
def test_qa_rejects_artifact_invariant_corruption(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: str,
    needles: tuple[str, ...],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.artifacts) as artifacts:
        if case == "orphan_track":
            artifacts.execute("UPDATE mert_embeddings SET track_id = 999")
        elif case == "track_uuid":
            artifacts.execute("UPDATE mert_embeddings SET track_uuid = 'wrong'")
        elif case == "generation":
            artifacts.execute("UPDATE mert_embeddings SET content_generation = 2")
        elif case == "dim":
            artifacts.execute(
                "UPDATE mert_embeddings SET dim = 2, embedding_blob = ?",
                (_float_blob([1.0, 0.0]),),
            )
        elif case == "normalization":
            artifacts.execute("UPDATE mert_embeddings SET normalization = 'none'")
        elif case == "nonfinite":
            spec = current_embedding_spec("mert")
            values = [0.0] * spec.dimension
            values[0] = float("nan")
            artifacts.execute(
                "UPDATE mert_embeddings SET embedding_blob = ?",
                (_float_blob(values),),
            )
        else:
            spec = current_embedding_spec("mert")
            values = [0.0] * spec.dimension
            values[0] = 1.0
            values[1] = 1.0
            artifacts.execute(
                "UPDATE mert_embeddings SET embedding_blob = ?",
                (_float_blob(values),),
            )

    _assert_failure(bundle, capsys, *needles)


def test_qa_does_not_validate_reserved_timeline_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.artifacts) as artifacts:
        artifacts.execute(
            """
            INSERT INTO sonara_timeline(
                track_id, track_uuid, content_generation,
                payload_json, analyzed_at
            ) VALUES (?, ?, 1, '{}', ?)
            """,
            (bundle.track_id, bundle.track_uuid, _NOW),
        )

    assert _run_default(bundle) == 0
    assert "QA PASSED" in capsys.readouterr().out


def test_qa_does_not_validate_reserved_fingerprint_payload(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.artifacts) as artifacts:
        artifacts.execute(
            """
            INSERT INTO sonara_fingerprints(
                track_id, track_uuid, content_generation,
                fingerprint_version, word_count, byte_order,
                fingerprint_blob, analyzed_at
            ) VALUES (?, ?, 1, 'native', 0, 'little', x'', ?)
            """,
            (bundle.track_id, bundle.track_uuid, _NOW),
        )

    assert _run_default(bundle) == 0
    assert "QA PASSED" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("case", "needles"),
    [
        ("uuid", ("classifier_scores", "track_uuid mismatch")),
        ("generation", ("classifier_scores", "content_generation mismatch")),
        ("empty_features", ("classifier_scores", "must not be empty")),
        ("duplicate_features", ("classifier_scores", "duplicate features")),
        ("invalid_feature", ("classifier_scores", "family:name")),
    ],
)
def test_qa_rejects_classifier_structural_corruption(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    case: str,
    needles: tuple[str, ...],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        if case == "uuid":
            core.execute("UPDATE classifier_scores SET track_uuid = 'wrong'")
        elif case == "generation":
            core.execute("UPDATE classifier_scores SET content_generation = 2")
        elif case == "empty_features":
            core.execute("UPDATE classifier_scores SET feature_names_json = '[]'")
        elif case == "duplicate_features":
            core.execute(
                """
                UPDATE classifier_scores
                SET feature_names_json = '["mert:0","mert:0"]'
                """
            )
        else:
            core.execute(
                "UPDATE classifier_scores SET feature_names_json = '[\"bad\"]'"
            )

    _assert_failure(bundle, capsys, *needles)


@pytest.mark.parametrize(
    ("probabilities", "needles"),
    [
        ('{"calm":0.0,"energetic":1e999}', ("non-finite",)),
        ('{"calm":0.1,"energetic":0.8}', ("do not sum to 1",)),
    ],
)
def test_qa_rejects_classifier_probability_corruption(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    probabilities: str,
    needles: tuple[str, ...],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        core.execute(
            "UPDATE classifier_scores SET probabilities_json = ?",
            (probabilities,),
        )

    _assert_failure(bundle, capsys, *needles)


def test_qa_rejects_core_foreign_key_orphan(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    with sqlite3.connect(bundle.core) as core:
        core.execute("PRAGMA foreign_keys = OFF")
        core.execute(
            "INSERT INTO likes(track_id, liked_at) VALUES (999, ?)",
            (_NOW,),
        )

    _assert_failure(bundle, capsys, "foreign-key", "likes")


def test_qa_validates_optional_evaluation_only_when_present(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)

    assert _run_default(bundle) == 0
    assert not bundle.evaluation.exists()
    capsys.readouterr()

    create_evaluation_sidecar_schema(
        bundle.evaluation,
        catalog_uuid=str(uuid.uuid4()),
    )
    _assert_failure(bundle, capsys, "evaluation", "another library catalog")


def test_qa_rejects_evaluation_track_orphan_without_mutating_sidecar(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    create_evaluation_sidecar_schema(
        bundle.evaluation,
        catalog_uuid=bundle.catalog_uuid,
    )
    with sqlite3.connect(bundle.evaluation) as evaluation:
        cursor = evaluation.execute(
            """
            INSERT INTO search_sessions(mode, request_json, created_at)
            VALUES ('hybrid', '{}', ?)
            """,
            (_NOW,),
        )
        evaluation.execute(
            """
            INSERT INTO search_session_seeds(
                session_id, position, track_id, track_uuid, content_generation
            ) VALUES (?, 0, 999, 'orphan', 1)
            """,
            (int(cursor.lastrowid),),
        )
    before = _file_hash(bundle.evaluation)

    _assert_failure(bundle, capsys, "evaluation", "orphan track_id")
    assert _file_hash(bundle.evaluation) == before


def test_qa_rejects_nonfinite_evaluation_score(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    create_evaluation_sidecar_schema(
        bundle.evaluation,
        catalog_uuid=bundle.catalog_uuid,
    )
    with sqlite3.connect(bundle.evaluation) as evaluation:
        cursor = evaluation.execute(
            """
            INSERT INTO search_sessions(mode, request_json, created_at)
            VALUES ('hybrid', '{}', ?)
            """,
            (_NOW,),
        )
        evaluation.execute(
            """
            INSERT INTO search_result_events(
                session_id, rank, track_id, track_uuid, content_generation,
                total_score, score_breakdown_json, created_at
            ) VALUES (?, 0, ?, ?, 1, ?, '{}', ?)
            """,
            (
                int(cursor.lastrowid),
                bundle.track_id,
                bundle.track_uuid,
                float("inf"),
                _NOW,
            ),
        )

    _assert_failure(bundle, capsys, "evaluation", "total_score", "not finite")


def test_qa_enables_query_only_before_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _build_healthy_bundle(tmp_path)
    original = qa_database._integrity_check
    observed: list[str] = []

    def assert_query_only(
        connection: sqlite3.Connection,
        label: str,
    ) -> None:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("CREATE TABLE qa_must_not_write(value TEXT)")
        observed.append(label)
        original(connection, label)

    monkeypatch.setattr(qa_database, "_integrity_check", assert_query_only)

    assert _run_default(bundle) == 0
    assert observed == ["Core", "Artifacts"]


def test_qa_source_has_no_versioned_identity_gates() -> None:
    source = _MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "schema_" + "version",
        "contract_" + "hash",
        "release_" + "hash",
        "manifest_" + "version",
        "model_" + "version",
        "required_outputs_" + "hash",
        "feature_manifest_" + "hash",
    )
    assert not any(term in source for term in forbidden)
