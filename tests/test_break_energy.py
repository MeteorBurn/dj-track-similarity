from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import fields
from pathlib import Path

import joblib
import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    SonaraWrite,
    current_embedding_spec,
)
from dj_track_similarity.classifier_jobs import ClassifierJobManager
from dj_track_similarity.classifier_scoring import (
    ClassifierScorer,
    default_classifier_model_path,
    load_classifier_requirements,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_ddl import SonaraRow


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
    return AnalysisOutput("mert", "embedding")


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


def _write_sonara_core(
    db: LibraryDatabase,
    target: AnalysisTarget,
) -> None:
    values = {field.name: None for field in fields(SonaraRow)}
    values.update(
        {
            "track_id": target.track_id,
            "content_generation": target.content_generation,
            "detected_bpm": 128.0,
            "bpm_confidence": 0.95,
            "detected_key_name": "A minor",
            "detected_key_camelot": "8A",
            "key_confidence": 0.9,
            "energy_score": 0.7,
            "danceability_score": 0.8,
            "valence_score": 0.6,
            "acousticness_score": 0.2,
            "mfcc_mean_blob": np.full(13, 0.5, dtype="<f4").tobytes(),
            "chroma_mean_blob": np.full(12, 0.5, dtype="<f4").tobytes(),
            "spectral_contrast_mean_blob": np.full(
                7, 0.5, dtype="<f4"
            ).tobytes(),
            "analyzed_at": _NOW,
        }
    )
    result = db.save_sonara_results(
        (SonaraWrite(target=target, core=SonaraRow(**values)),)
    )[0]
    assert result.ok, result.error


def _write_model(
    root: Path,
    output: AnalysisOutput,
    *,
    broken_probability: float = 0.87,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "model.joblib"
    joblib.dump(
        {
            "classifier_key": "break_energy",
            "feature_set": "mert",
            "feature_names": ["mert:0"],
            "feature_count": 1,
            "label_order": ["straight", "broken"],
            "positive_label": "broken",
            "model": _FixedProbabilityModel(broken_probability),
        },
        model_path,
    )
    artifact_hash = f"sha256:{hashlib.sha256(model_path.read_bytes()).hexdigest()}"

    manifest = {
        "classifier_key": "break_energy",
        "profile_name": "Break Energy",
        "artifact_hash": artifact_hash,
        "feature_set": "mert",
        "feature_names": ["mert:0"],
        "feature_count": 1,
        "label_order": ["straight", "broken"],
        "negative_label": "straight",
        "positive_label": "broken",
        "production": {
            "score_semantics": "positive_label_probability",
            "calibration": {"status": "uncalibrated"},
        },
    }
    model_path.with_name("model.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return model_path


def test_classifier_artifact_loads_without_version_or_contract_identity(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    model_path = _write_model(tmp_path / "break-energy", _mert_output())

    metadata = json.loads(model_path.with_name("model.json").read_text(encoding="utf-8"))
    requirements = load_classifier_requirements(
        db,
        "break_energy",
        model_path=model_path,
    )

    assert "manifest_version" not in metadata
    assert "feature_manifest_hash" not in metadata
    assert "required_outputs" not in metadata["production"]
    assert requirements.feature_names == ("mert:0",)


def test_break_energy_job_scores_tracks_with_required_rows(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    ready = _insert_track(db)
    missing = _insert_track(db)
    _write_sonara_core(db, ready)
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

    completed = manager.run_job(job_id)

    assert completed.state == "completed"
    assert (completed.processed, completed.analyzed, completed.failed) == (
        1,
        1,
        0,
    )
    ready_detail = db.get_track_detail(
        ready.track_id,
        classifier_specifications=(requirements.specification,),
    ).classifier_scores_detail
    assert len(ready_detail) == 1
    assert ready_detail[0].classifier_key == "break_energy"
    assert ready_detail[0].score == pytest.approx(0.87)
    assert ready_detail[0].predicted_class == "broken"
    assert ready_detail[0].score_bucket == "high"
    assert (
        db.get_track_detail(
            missing.track_id,
            classifier_specifications=(requirements.specification,),
        ).classifier_scores_detail
        == ()
    )


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
    row = db.load_classifier_work_batch(
        requirements.specification,
        after_track_id=0,
        limit=1,
    )[0][1]

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
