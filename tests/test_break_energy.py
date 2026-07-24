from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import joblib
import numpy as np
import pytest

from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
)
from dj_track_similarity.classifier_jobs import ClassifierJobManager
from dj_track_similarity.classifier_scoring import (
    ClassifierScorer,
    default_classifier_model_path,
    load_classifier_requirements,
)
from dj_track_similarity.database import LibraryDatabase


_NOW = "2026-07-24T14:00:00.000000Z"


class _FixedProbabilityModel:
    n_features_in_ = 1
    classes_ = np.asarray(["straight", "broken"], dtype=object)

    def __init__(self, broken_probability: float = 0.87) -> None:
        self.broken_probability = broken_probability

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        probabilities = np.asarray(
            [1.0 - self.broken_probability, self.broken_probability],
            dtype=np.float64,
        )
        return np.tile(probabilities, (matrix.shape[0], 1))


def _mert_output() -> AnalysisOutput:
    return current_embedding_analysis_output("mert", device="cpu")


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


def _write_model(
    root: Path,
    output: AnalysisOutput,
    *,
    broken_probability: float = 0.87,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "model.joblib"
    joblib.dump(
        {"model": _FixedProbabilityModel(broken_probability)},
        model_path,
    )
    artifact_hash = f"sha256:{hashlib.sha256(model_path.read_bytes()).hexdigest()}"
    feature_names = ("mert:0",)
    from dj_track_similarity.classifier_manifest import (
        classifier_feature_manifest_hash,
    )

    manifest = {
        "manifest_version": 2,
        "classifier_key": "break_energy",
        "profile_name": "Break Energy",
        "model_id": "break-energy-v2",
        "artifact_hash": artifact_hash,
        "feature_set": "mert-contract",
        "feature_names": list(feature_names),
        "feature_count": 1,
        "feature_manifest_hash": classifier_feature_manifest_hash(feature_names),
        "label_order": ["straight", "broken"],
        "negative_label": "straight",
        "positive_label": "broken",
        "production": {
            "score_semantics": "positive_label_probability",
            "required_outputs": [
                {
                    "contract_hash": output.contract_hash,
                    "canonical_payload": output.contract.canonical_payload,
                }
            ],
            "calibration": {"status": "uncalibrated"},
        },
    }
    model_path.with_name("model.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return model_path


def test_break_energy_job_aggregates_only_feature_ready_tracks(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    ready = _insert_track(db)
    missing = _insert_track(db)
    _write_embedding(db, ready, output)
    model_path = _write_model(tmp_path / "break-energy", output)
    requirements = load_classifier_requirements(
        db,
        "break_energy",
        model_path=model_path,
    )
    manager = ClassifierJobManager(
        db,
        requirements_loader=lambda key: requirements,
    )

    job_id = manager.create_job(classifier="break_energy")
    queued = manager.get(job_id)

    assert queued.total == 1
    assert queued.required_families == ("mert",)
    assert queued.readiness["break_energy"] == {
        "candidates": 2,
        "ready": 1,
        "not_ready": 1,
        "selected": 1,
    }

    completed = manager.run_job(job_id)

    assert completed.state == "completed"
    assert (completed.processed, completed.analyzed, completed.failed) == (
        1,
        1,
        0,
    )
    ready_detail = db.get_track_detail(ready.track_id).classifier_scores_detail
    assert len(ready_detail) == 1
    assert ready_detail[0].classifier_key == "break_energy"
    assert ready_detail[0].score == pytest.approx(0.87)
    assert ready_detail[0].predicted_class == "broken"
    assert ready_detail[0].score_bucket == "high"
    assert db.get_track_detail(missing.track_id).classifier_scores_detail == ()


def test_break_energy_public_scorer_preserves_probability_precision(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_embedding(db, target, output)
    model_path = _write_model(
        tmp_path / "break-energy",
        output,
        broken_probability=0.99999999,
    )
    requirements = load_classifier_requirements(
        db,
        "break_energy",
        model_path=model_path,
    )
    row = db.load_classifier_feature_rows(
        requirements.specification,
        targets=(target,),
    )[0]

    write = ClassifierScorer(requirements).score_row(row, analyzed_at=_NOW)

    assert write.score.score == pytest.approx(0.99999999)
    assert write.score.confidence == pytest.approx(0.99999999)
    assert json.loads(write.score.probabilities_json) == pytest.approx(
        {
            "straight": 0.00000001,
            "broken": 0.99999999,
        }
    )


def test_default_classifier_model_path_uses_classifier_slug() -> None:
    assert (
        default_classifier_model_path("live_instrumentation")
        .as_posix()
        .endswith("models/classifiers/live-instrumentation/model.joblib")
    )
