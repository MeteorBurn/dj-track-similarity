from __future__ import annotations

from dataclasses import replace
import json
import uuid
from pathlib import Path

import numpy as np
import pytest

import dj_track_similarity.classifier_jobs as classifier_jobs_module
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    ClassifierFeatureRow,
    ClassifierScoreWrite,
    ClassifierSpecification,
    EmbeddingOutput,
    EmbeddingWrite,
    classifier_required_outputs_hash,
)
from dj_track_similarity.classifier_jobs import ClassifierJobManager
from dj_track_similarity.classifier_manifest import (
    ClassifierManifestSummary,
    classifier_feature_manifest_hash,
)
from dj_track_similarity.classifier_scoring import ClassifierRequirements
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_schema_v7 import ClassifierScoreV7


_NOW = "2026-07-24T11:00:00.000000Z"
_ARTIFACT_HASH = "sha256:" + "a" * 64


def _mert_output(*, model_version: str = "active") -> AnalysisOutput:
    current = current_embedding_analysis_output("mert")
    if model_version in {"active", "revision-1"}:
        return current
    if model_version != "inactive":
        raise ValueError(f"Unsupported test MERT identity: {model_version}")
    stale_version = (
        "0" * 40
        if current.contract.model_version != "0" * 40
        else "f" * 40
    )
    return AnalysisOutput(
        replace(
            current.contract,
            model_version=stale_version,
        )
    )


def _insert_track(db: LibraryDatabase) -> AnalysisTarget:
    track_uuid = str(uuid.uuid4())
    with db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, 123456789, 1, ?, ?, ?)
            """,
            (
                track_uuid,
                f"C:/music/{track_uuid}.wav",
                _NOW,
                _NOW,
                _NOW,
            ),
        )
        track_id = int(cursor.lastrowid)
    return AnalysisTarget(
        catalog_uuid=db.catalog_uuid,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=1,
    )


def _write_embedding(
    db: LibraryDatabase,
    target: AnalysisTarget,
    output: AnalysisOutput,
) -> None:
    vector = np.zeros(int(output.contract.dim), dtype=np.float32)
    vector[0] = 1.0
    result = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    contract=output.contract,
                    vector=vector,
                    analyzed_at=_NOW,
                ),
            ),
        )
    )[0]
    assert result.ok


def _requirements(
    classifier_key: str,
    output: AnalysisOutput,
    *,
    model_id: str | None = None,
) -> ClassifierRequirements:
    feature_names = ("mert:0",)
    feature_hash = classifier_feature_manifest_hash(feature_names)
    specification = ClassifierSpecification(
        classifier_key=classifier_key,
        model_id=model_id or f"{classifier_key}-model",
        feature_set="mert-contract",
        feature_manifest_hash=feature_hash,
        required_outputs_hash=classifier_required_outputs_hash((output,)),
        feature_names=feature_names,
        required_outputs=(output,),
        label_order=("negative", "positive"),
        positive_label="positive",
    )
    manifest = ClassifierManifestSummary(
        classifier_key=classifier_key,
        metadata_path=Path(f"{classifier_key}.json"),
        model_path=Path(f"{classifier_key}.joblib"),
        status="valid",
        feature_set=specification.feature_set,
        feature_names=feature_names,
        feature_count=1,
        feature_manifest_hash=feature_hash,
        required_outputs=(output,),
        label_order=("negative", "positive"),
        positive_label="positive",
        negative_label="negative",
        manifest_version=2,
        model_id=specification.model_id,
        artifact_hash=_ARTIFACT_HASH,
    )
    return ClassifierRequirements(
        manifest=manifest,
        specification=specification,
        model_path=manifest.model_path,
        artifact_hash=_ARTIFACT_HASH,
        label_order=manifest.label_order,
    )


class _FakeScorer:
    manifest_warnings: tuple[str, ...] = ()

    def __init__(self, requirements: ClassifierRequirements) -> None:
        self.specification = requirements.specification
        self.model_name = str(requirements.model_path)

    def score_row(
        self,
        row: ClassifierFeatureRow,
    ) -> ClassifierScoreWrite:
        score = 0.8
        return ClassifierScoreWrite(
            target=row.target,
            specification=self.specification,
            score=ClassifierScoreV7(
                track_id=row.target.track_id,
                classifier_key=self.specification.classifier_key,
                content_generation=row.target.content_generation,
                model_id=self.specification.model_id,
                feature_set=self.specification.feature_set,
                feature_manifest_hash=self.specification.feature_manifest_hash,
                required_outputs_hash=(self.specification.required_outputs_hash),
                uses_sonara=0,
                sonara_release_hash=None,
                positive_label="positive",
                predicted_class="positive",
                score_bucket="high",
                score=score,
                confidence=score,
                probabilities_json=json.dumps(
                    {"negative": 0.2, "positive": 0.8},
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                analyzed_at=_NOW,
            ),
        )


def _score_count(db: LibraryDatabase, classifier_key: str) -> int:
    with db.connect() as connection:
        return int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM classifier_scores
                WHERE classifier_key = ?
                """,
                (classifier_key,),
            ).fetchone()[0]
        )


def test_aggregate_limit_caps_track_classifier_pairs_on_v7_rows(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    for _ in range(3):
        target = _insert_track(db)
        _write_embedding(db, target, output)
    requirements = {
        key: _requirements(key, output) for key in ("classifier_one", "classifier_two")
    }
    manager = ClassifierJobManager(
        db,
        requirements_loader=requirements.__getitem__,
        scorer_factory=_FakeScorer,
    )

    job_id = manager.create_job(
        classifiers=("classifier_one", "classifier_two"),
        limit=4,
    )
    queued = manager.get(job_id)

    assert queued.total == 4
    assert queued.required_families == ("mert",)
    assert not hasattr(queued, "embedding_key")
    assert queued.readiness["classifier_one"] == {
        "candidates": 3,
        "ready": 3,
        "not_ready": 0,
        "selected": 3,
    }
    assert queued.readiness["classifier_two"]["selected"] == 1

    completed = manager.run_job(job_id)

    assert completed.state == "completed"
    assert completed.processed == 4
    assert completed.analyzed == 4
    assert completed.failed == 0
    assert _score_count(db, "classifier_one") == 3
    assert _score_count(db, "classifier_two") == 1


def test_not_ready_outputs_are_excluded_before_job_total(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    ready_target = _insert_track(db)
    _write_embedding(db, ready_target, output)
    _insert_track(db)
    requirements = _requirements("test_classifier", output)
    manager = ClassifierJobManager(
        db,
        requirements_loader=lambda _key: requirements,
        scorer_factory=_FakeScorer,
    )

    readiness = manager.readiness(("test_classifier",))
    job_id = manager.create_job(classifier="test_classifier")

    assert readiness["test_classifier"] == {
        "candidates": 2,
        "ready": 1,
        "not_ready": 1,
        "blockers": [],
    }
    assert manager.get(job_id).total == 1
    completed = manager.run_job(job_id)
    assert completed.analyzed == 1
    assert completed.failed == 0


def test_all_contracts_are_preflighted_before_any_stale_cleanup(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    active = _mert_output(model_version="active")
    inactive = _mert_output(model_version="inactive")
    db.register_analysis_outputs((active,))
    target = _insert_track(db)
    stale = _requirements("classifier_one", active, model_id="old-model")
    stale_write = _FakeScorer(stale).score_row(
        ClassifierFeatureRow(
            target=target,
            specification=stale.specification,
            vector=np.asarray([1.0], dtype=np.float32),
        )
    )
    assert db.save_classifier_scores((stale_write,))[0].ok
    requirements = {
        "classifier_one": _requirements("classifier_one", active),
        "classifier_two": _requirements("classifier_two", inactive),
    }
    manager = ClassifierJobManager(
        db,
        requirements_loader=requirements.__getitem__,
        scorer_factory=_FakeScorer,
    )

    with pytest.raises(
        RuntimeError,
        match="does not match the current adapter identity",
    ):
        manager.create_job(
            classifiers=("classifier_one", "classifier_two"),
        )

    assert _score_count(db, "classifier_one") == 1


def test_job_write_rejects_track_uuid_changed_after_queueing(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_embedding(db, target, output)
    requirements = _requirements("test_classifier", output)
    manager = ClassifierJobManager(
        db,
        requirements_loader=lambda _key: requirements,
        scorer_factory=_FakeScorer,
    )
    job_id = manager.create_job(classifier="test_classifier")
    with db.connect() as connection:
        connection.execute(
            """
            UPDATE tracks
            SET track_uuid = ?, updated_at = ?
            WHERE track_id = ?
            """,
            (str(uuid.uuid4()), _NOW, target.track_id),
        )

    completed = manager.run_job(job_id)

    assert completed.state == "completed"
    assert completed.analyzed == 0
    assert completed.failed == 1
    assert "track_uuid mismatch" in completed.errors[0].error
    assert _score_count(db, "test_classifier") == 0


def test_custom_model_path_calls_v7_requirements_loader_with_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    requirements = _requirements("test_classifier", output)
    calls: list[tuple[object, str, Path | None]] = []

    def fake_load(
        database: LibraryDatabase,
        classifier: str,
        *,
        model_path: str | Path | None = None,
    ) -> ClassifierRequirements:
        calls.append(
            (
                database,
                classifier,
                None if model_path is None else Path(model_path),
            )
        )
        return requirements

    monkeypatch.setattr(
        classifier_jobs_module,
        "load_classifier_requirements",
        fake_load,
    )
    manager = ClassifierJobManager(
        db,
        scorer_factory=_FakeScorer,
    )
    custom_path = tmp_path / "custom.joblib"

    job_id = manager.create_job(
        classifier="test_classifier",
        model_path=custom_path,
        limit=0,
    )

    assert calls == [(db, "test_classifier", custom_path)]
    assert manager.get(job_id).total == 0
