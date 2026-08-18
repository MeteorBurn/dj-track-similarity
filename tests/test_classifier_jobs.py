from __future__ import annotations

import json
import uuid
from pathlib import Path

import numpy as np
import pytest

import dj_track_similarity.classifier_jobs as classifier_jobs_module
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    ClassifierFeatureRow,
    ClassifierScoreWrite,
    ClassifierSpecification,
    EmbeddingOutput,
    EmbeddingWrite,
    current_embedding_spec,
)
from dj_track_similarity.classifier_jobs import ClassifierJobManager
from dj_track_similarity.classifier_manifest import ClassifierManifestSummary
from dj_track_similarity.classifier_scoring import ClassifierRequirements
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_ddl import ClassifierScoreRecord


_NOW = "2026-07-24T11:00:00.000000Z"
_ARTIFACT_HASH = "sha256:" + "a" * 64


def _mert_output() -> AnalysisOutput:
    return AnalysisOutput("mert", "embedding")


def _insert_track(db: LibraryDatabase) -> AnalysisTarget:
    track_uuid = str(uuid.uuid4())
    with db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, 123456789, ?, ?, ?)
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
        connection.execute(
            """
            INSERT INTO sonara_features(
                track_id, mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analysis_schema_version,
                bpm_min, bpm_max, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                np.zeros(13, dtype="<f4").tobytes(),
                np.zeros(12, dtype="<f4").tobytes(),
                np.zeros(7, dtype="<f4").tobytes(),
                6,
                70.0,
                180.0,
                _NOW,
            ),
        )
    return AnalysisTarget(
        catalog_uuid=db.catalog_uuid,
        track_id=track_id,
        track_uuid=track_uuid,
    )


def _write_embedding(
    db: LibraryDatabase,
    target: AnalysisTarget,
    output: AnalysisOutput,
) -> None:
    vector = np.zeros(current_embedding_spec(output.analysis_family).dimension, dtype=np.float32)
    vector[0] = 1.0
    result = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family=output.analysis_family,
                    vector=vector,
                    analyzed_at=_NOW,
                ),
            ),
        )
    )[0]
    assert result.ok


def _insert_present_classifier_inputs(db: LibraryDatabase, count: int) -> None:
    """Create more persisted classifier inputs than one job batch holds."""

    with db.connect() as connection:
        for index in range(count):
            track_uuid = str(uuid.uuid4())
            cursor = connection.execute(
                """
                INSERT INTO tracks (
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, 1024, 123456789, ?, ?, ?)
                """,
                (
                    track_uuid,
                    f"C:/music/present-{index}.wav",
                    _NOW,
                    _NOW,
                    _NOW,
                ),
            )
            track_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO sonara_features(
                    track_id, mfcc_mean_blob, chroma_mean_blob,
                    spectral_contrast_mean_blob, analysis_schema_version,
                    bpm_min, bpm_max, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    track_id,
                    np.zeros(13, dtype="<f4").tobytes(),
                    np.zeros(12, dtype="<f4").tobytes(),
                    np.zeros(7, dtype="<f4").tobytes(),
                    6,
                    70.0,
                    180.0,
                    _NOW,
                ),
            )
            vector = np.zeros(
                current_embedding_spec("mert").dimension,
                dtype="<f4",
            )
            vector[0] = 1.0
            connection.execute(
                """
                INSERT INTO mert_embeddings(
                    track_id, track_uuid, dim, normalization, embedding_blob, analyzed_at
                ) VALUES (?, ?, ?, 'l2', ?, ?)
                """,
                (
                    track_id,
                    track_uuid,
                    vector.size,
                    vector.tobytes(),
                    _NOW,
                ),
            )


def _requirements(
    classifier_key: str,
    output: AnalysisOutput,
) -> ClassifierRequirements:
    feature_names = ("mert:0",)
    specification = ClassifierSpecification(
        classifier_key=classifier_key,
        feature_set="mert-features",
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
        label_order=("negative", "positive"),
        positive_label="positive",
        negative_label="negative",
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
            score=ClassifierScoreRecord(
                track_id=row.target.track_id,
                track_uuid=row.target.track_uuid,
                classifier_key=self.specification.classifier_key,
                feature_set=self.specification.feature_set,
                feature_names_json=json.dumps(list(self.specification.feature_names)),
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


def test_classifier_job_streams_inputs_in_200_track_batches(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    _insert_present_classifier_inputs(db, 201)
    requirements = _requirements("test_classifier", output)
    manager = ClassifierJobManager(
        db,
        requirements_loader=lambda _key: requirements,
        scorer_factory=_FakeScorer,
    )

    job_id = manager.create_job(classifier="test_classifier")

    queued = manager.get(job_id)
    assert queued.total == 201
    assert queued.batch_size == 200

    completed = manager.run_job(job_id)

    assert (completed.processed, completed.analyzed, completed.failed) == (201, 201, 0)
    assert _score_count(db, "test_classifier") == 201
    assert [event.message for event in completed.events] == [
        "CLASSIFIER queued · test_classifier",
        "CLASSIFIERS started",
        "CLASSIFIERS batch: 200 tracks scored",
        "CLASSIFIERS batch: 1 tracks scored",
        "CLASSIFIERS completed",
    ]


def test_custom_model_path_calls_current_requirements_loader_with_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    _insert_track(db)
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
