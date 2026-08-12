from __future__ import annotations

import hashlib
import json
import sys
import types
import uuid
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    ClassifierScoreWrite,
    ClassifierSpecification,
    EmbeddingOutput,
    EmbeddingWrite,
    current_embedding_spec,
)
from dj_track_similarity.classifier_manifest import load_classifier_manifest_summary
from dj_track_similarity.classifier_scoring import (
    ClassifierScorer,
    analyze_classifier,
    load_classifier_requirements,
    promoted_classifiers,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_ddl import ClassifierScoreRecord


_NOW = "2026-07-24T10:00:00.000000Z"
_ARTIFACT_BYTES = b"classifier-current-test-artifact"


class _ProbabilityModel:
    def __init__(
        self,
        probabilities: tuple[float, float],
        *,
        feature_count: int,
        classes: tuple[str, str] = ("negative", "positive"),
    ) -> None:
        self.probabilities = probabilities
        self.n_features_in_ = feature_count
        self.classes_ = np.asarray(classes, dtype=object)

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        return np.tile(
            np.asarray(self.probabilities, dtype=np.float64),
            (matrix.shape[0], 1),
        )


def _mert_output() -> AnalysisOutput:
    return AnalysisOutput("mert", "embedding")


def _muq_output() -> AnalysisOutput:
    return AnalysisOutput("muq", "embedding")


def _artifact_hash(data: bytes = _ARTIFACT_BYTES) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _manifest_payload(
    *,
    classifier_key: str = "test_classifier",
    feature_names: tuple[str, ...] = ("mert:0",),
    artifact_hash: str | None = None,
    label_order: tuple[str, str] = ("negative", "positive"),
) -> dict[str, object]:
    return {
        "classifier_key": classifier_key,
        "artifact_hash": artifact_hash or _artifact_hash(),
        "feature_set": "mert-features",
        "feature_names": list(feature_names),
        "feature_count": len(feature_names),
        "label_order": list(label_order),
        "negative_label": "negative",
        "positive_label": "positive",
        "production": {
            "score_semantics": "positive_label_probability",
            "calibration": {"status": "uncalibrated"},
        },
    }


def _write_artifact(
    tmp_path: Path,
    **manifest_changes: object,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(_ARTIFACT_BYTES)
    payload = _manifest_payload()
    payload.update(manifest_changes)
    (tmp_path / "model.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    return model_path


def _insert_track(
    db: LibraryDatabase,
    *,
    content_generation: int = 1,
) -> AnalysisTarget:
    track_uuid = str(uuid.uuid4())
    with db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, 123456789, ?, ?, ?, ?)
            """,
            (
                track_uuid,
                f"C:/music/{track_uuid}.wav",
                content_generation,
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
        content_generation=content_generation,
    )


def _write_embedding(
    db: LibraryDatabase,
    target: AnalysisTarget,
    output: AnalysisOutput,
) -> None:
    vector = np.zeros(current_embedding_spec(output.analysis_family).dimension, dtype=np.float32)
    vector[0] = 1.0
    results = db.save_embedding_results(
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
    )
    assert len(results) == 1 and results[0].ok


def _write_mert_embedding(
    db: LibraryDatabase,
    target: AnalysisTarget,
    output: AnalysisOutput,
) -> None:
    _write_embedding(db, target, output)


def _write_sonara_core(
    db: LibraryDatabase,
    target: AnalysisTarget,
) -> None:
    with db.connect() as connection:
        connection.execute(
            """
            INSERT INTO sonara_features(
                track_id, content_generation,
                mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                target.track_id,
                target.content_generation,
                np.zeros(13, dtype="<f4").tobytes(),
                np.zeros(12, dtype="<f4").tobytes(),
                np.zeros(7, dtype="<f4").tobytes(),
                _NOW,
            ),
        )


def _score_write(
    target: AnalysisTarget,
    *,
    classifier_key: str,
    score: float = 0.8,
) -> ClassifierScoreWrite:
    output = _mert_output()
    specification = ClassifierSpecification(
        classifier_key=classifier_key,
        feature_set="mert-features",
        feature_names=("mert:0",),
        required_outputs=(output,),
        label_order=("negative", "positive"),
        positive_label="positive",
    )
    probabilities = {
        "negative": 1.0 - score,
        "positive": score,
    }
    return ClassifierScoreWrite(
        target=target,
        specification=specification,
        score=ClassifierScoreRecord(
            track_id=target.track_id,
            track_uuid=target.track_uuid,
            classifier_key=classifier_key,
            content_generation=target.content_generation,
            feature_set="mert-features",
            feature_names_json=json.dumps(list(specification.feature_names)),
            positive_label="positive",
            predicted_class=("positive" if score > 0.5 else "negative"),
            score_bucket=(
                "high" if score >= 0.7 else "medium" if score >= 0.3 else "low"
            ),
            score=score,
            confidence=max(probabilities.values()),
            probabilities_json=json.dumps(
                probabilities,
                sort_keys=True,
                separators=(",", ":"),
            ),
            analyzed_at=_NOW,
        ),
    )


def _install_fake_joblib(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payload: dict[str, object] | None = None,
    error: Exception | None = None,
) -> list[bytes]:
    loaded: list[bytes] = []

    def load(handle: object) -> dict[str, object]:
        read = getattr(handle, "read")
        loaded.append(bytes(read()))
        if error is not None:
            raise error
        assert payload is not None
        return payload

    monkeypatch.setitem(sys.modules, "joblib", types.SimpleNamespace(load=load))
    return loaded


def _score_rows(
    db: LibraryDatabase,
    classifier_key: str,
) -> list[tuple[object, ...]]:
    with db.connect() as connection:
        return [
            tuple(row)
            for row in connection.execute(
                """
                SELECT classifier_key, feature_names_json, predicted_class,
                       score_bucket, score, confidence
                FROM classifier_scores
                WHERE classifier_key = ?
                ORDER BY track_id
                """,
                (classifier_key,),
            ).fetchall()
        ]


def test_artifact_validation_preserves_existing_scores_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_sonara_core(db, target)
    _write_mert_embedding(db, target, output)
    assert db.save_classifier_scores(
        (
            _score_write(
                target,
                classifier_key="test_classifier",
            ),
            _score_write(
                target,
                classifier_key="other_classifier",
            ),
        )
    )[0].ok

    wrong_path = _write_artifact(
        tmp_path / "wrong-digest",
        artifact_hash="sha256:" + "0" * 64,
    )
    digest_loads = _install_fake_joblib(
        monkeypatch,
        payload={
            "model": _ProbabilityModel((0.2, 0.8), feature_count=1),
        },
    )
    with pytest.raises(ValueError, match="artifact SHA-256 mismatch"):
        analyze_classifier(
            db,
            classifier="test_classifier",
            model_path=wrong_path,
        )
    assert digest_loads == []
    assert len(_score_rows(db, "test_classifier")) == 1

    invalid_path = _write_artifact(tmp_path / "invalid-model")
    invalid_loads = _install_fake_joblib(
        monkeypatch,
        error=ValueError("synthetic joblib rejection"),
    )
    with pytest.raises(ValueError, match="synthetic joblib rejection"):
        analyze_classifier(
            db,
            classifier="test_classifier",
            model_path=invalid_path,
        )
    assert invalid_loads == [_ARTIFACT_BYTES]
    assert len(_score_rows(db, "test_classifier")) == 1

    valid_path = _write_artifact(tmp_path / "valid-model")
    valid_loads = _install_fake_joblib(
        monkeypatch,
        payload={
            "model": _ProbabilityModel((0.2, 0.8), feature_count=1),
        },
    )
    result = analyze_classifier(
        db,
        classifier="test_classifier",
        model_path=valid_path,
    )

    assert valid_loads == [_ARTIFACT_BYTES]
    assert result["scored"] == 0
    current = _score_rows(db, "test_classifier")
    assert current == [
        (
            "test_classifier",
            '["mert:0"]',
            "positive",
            "high",
            pytest.approx(0.8),
            pytest.approx(0.8),
        )
    ]
    assert len(_score_rows(db, "other_classifier")) == 1


def test_production_scoring_loads_current_muq_embedding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _muq_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_sonara_core(db, target)
    _write_embedding(db, target, output)
    names = ("muq:0",)
    model_path = _write_artifact(
        tmp_path / "muq-artifact",
        feature_set="muq-features",
        feature_names=list(names),
        feature_count=len(names),
    )
    _install_fake_joblib(
        monkeypatch,
        payload={
            "model": _ProbabilityModel((0.25, 0.75), feature_count=1),
        },
    )

    result = analyze_classifier(
        db,
        classifier="test_classifier",
        model_path=model_path,
    )

    assert result["scored"] == 1
    assert result["skipped"] == 0
    stored = _score_rows(db, "test_classifier")
    assert stored[0][1] == '["muq:0"]'
    assert stored[0][2] == "positive"
    assert stored[0][4] == pytest.approx(0.75)


def test_requirements_reject_out_of_range_feature(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    active = _mert_output()
    db.register_analysis_outputs((active,))
    out_of_range = _manifest_payload(feature_names=("mert:768",))
    range_path = tmp_path / "out-of-range"
    range_path.mkdir()
    (range_path / "model.joblib").write_bytes(_ARTIFACT_BYTES)
    (range_path / "model.json").write_text(
        json.dumps(out_of_range),
        encoding="utf-8",
    )
    summary = load_classifier_manifest_summary(
        range_path / "model.joblib",
        expected_classifier_key="test_classifier",
    )

    assert summary.status == "invalid"
    assert any(
        "outside the current mert dimension 768" in error for error in summary.errors
    )
    with pytest.raises(ValueError, match="outside the current mert dimension 768"):
        load_classifier_requirements(
            db,
            "test_classifier",
            model_path=range_path / "model.joblib",
        )


def test_rhythm_lab_sonara_aliases_are_scoring_ready(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = AnalysisOutput("sonara", "core")
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_sonara_core(db, target)
    with db.connect() as connection:
        connection.execute(
            "UPDATE sonara_features SET detected_bpm = ? WHERE track_id = ?",
            (128.0, target.track_id),
        )

    model_path = _write_artifact(
        tmp_path / "artifact",
        feature_names=("sonara:bpm", "sonara:mfcc_mean:0"),
        feature_count=2,
    )
    requirements = load_classifier_requirements(
        db,
        "test_classifier",
        model_path=model_path,
    )
    rows = tuple(
        row
        for _candidate, row in db.load_classifier_work_batch(
            requirements.specification,
            after_track_id=0,
            limit=1,
        )
    )

    assert len(rows) == 1
    assert rows[0].vector.tolist() == [128.0, 0.0]


@pytest.mark.parametrize(
    ("positive_score", "expected_bucket"),
    (
        (0.29, "low"),
        (0.30, "medium"),
        (0.69, "medium"),
        (0.70, "high"),
    ),
)
def test_public_scorer_uses_deterministic_argmax_and_bucket_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    positive_score: float,
    expected_bucket: str,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_mert_embedding(db, target, output)
    model_path = _write_artifact(tmp_path / "artifact")
    _install_fake_joblib(
        monkeypatch,
        payload={
            "model": _ProbabilityModel(
                (1.0 - positive_score, positive_score),
                feature_count=1,
            ),
        },
    )
    requirements = load_classifier_requirements(
        db,
        "test_classifier",
        model_path=model_path,
    )
    scorer = ClassifierScorer(requirements)
    feature_rows = tuple(
        row
        for _candidate, row in db.load_classifier_work_batch(
            requirements.specification,
            after_track_id=0,
            limit=1,
        )
    )

    write = scorer.score_row(feature_rows[0], analyzed_at=_NOW)

    expected_class = "negative" if positive_score <= 0.5 else "positive"
    assert write.score.predicted_class == expected_class
    assert write.score.score_bucket == expected_bucket
    assert write.score.score == pytest.approx(positive_score)
    assert write.score.confidence == pytest.approx(
        max(positive_score, 1.0 - positive_score)
    )


def test_public_scorer_breaks_exact_ties_by_manifest_label_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_mert_embedding(db, target, output)
    payload = _manifest_payload(label_order=("positive", "negative"))
    artifact_dir = tmp_path / "tie"
    artifact_dir.mkdir()
    model_path = artifact_dir / "model.joblib"
    model_path.write_bytes(_ARTIFACT_BYTES)
    (artifact_dir / "model.json").write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    _install_fake_joblib(
        monkeypatch,
        payload={
            "model": _ProbabilityModel(
                (0.5, 0.5),
                feature_count=1,
                classes=("negative", "positive"),
            ),
        },
    )
    requirements = load_classifier_requirements(
        db,
        "test_classifier",
        model_path=model_path,
    )
    scorer = ClassifierScorer(requirements)
    row = db.load_classifier_work_batch(
        requirements.specification,
        after_track_id=0,
        limit=1,
    )[0][1]

    write = scorer.score_row(row, analyzed_at=_NOW)

    assert write.score.predicted_class == "positive"
    assert write.score.score_bucket == "medium"
    assert json.loads(write.score.probabilities_json) == {
        "negative": 0.5,
        "positive": 0.5,
    }


@pytest.mark.parametrize(
    ("score_changes", "expected_error"),
    [
        (
            {"predicted_class": "positive"},
            "canonical label-order argmax",
        ),
        (
            {"score": 0.4},
            "positive-label probability",
        ),
        (
            {"confidence": 0.4},
            "max(probabilities)",
        ),
        (
            {"score_bucket": "high"},
            "score_bucket does not match",
        ),
    ],
)
def test_classifier_writer_rejects_contradictory_score_math(
    tmp_path: Path,
    score_changes: dict[str, object],
    expected_error: str,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    base = _score_write(
        target,
        classifier_key="test_classifier",
        score=0.5,
    )
    contradictory = replace(
        base,
        score=replace(base.score, **score_changes),
    )

    result = db.save_classifier_scores((contradictory,))[0]

    assert not result.ok
    assert expected_error in str(result.error)
    assert _score_rows(db, "test_classifier") == []


@pytest.mark.parametrize(
    ("score_changes", "expected_error"),
    [
        (
            {"score": "0.5"},
            "classifier score must be a finite number",
        ),
        (
            {"confidence": "0.5"},
            "classifier confidence must be a finite number",
        ),
        (
            {"probabilities_json": '{"negative":"0.5","positive":"0.5"}'},
            "classifier probabilities must be finite numbers",
        ),
        (
            {"score": True},
            "classifier score must be a finite number",
        ),
        (
            {"confidence": True},
            "classifier confidence must be a finite number",
        ),
        (
            {"probabilities_json": '{"negative":true,"positive":false}'},
            "classifier probabilities must be finite numbers",
        ),
    ],
)
def test_classifier_writer_rejects_numeric_strings_before_persistence(
    tmp_path: Path,
    score_changes: dict[str, object],
    expected_error: str,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    base = _score_write(
        target,
        classifier_key="test_classifier",
        score=0.5,
    )
    malformed = replace(
        base,
        score=replace(base.score, **score_changes),
    )

    result = db.save_classifier_scores((malformed,))[0]

    assert not result.ok
    assert expected_error in str(result.error)
    assert _score_rows(db, "test_classifier") == []


@pytest.mark.parametrize("numeric_score", (0, 0.5, 1))
def test_classifier_writer_valid_numbers_round_trip_through_reader(
    tmp_path: Path,
    numeric_score: int | float,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    write = _score_write(
        target,
        classifier_key="test_classifier",
        score=numeric_score,
    )

    result = db.save_classifier_scores((write,))[0]
    detail = db.get_track_detail(
        target.track_id,
        classifier_specifications=(write.specification,),
    )

    assert result.ok
    assert len(detail.classifier_scores_detail) == 1
    stored = detail.classifier_scores_detail[0]
    assert stored.score == pytest.approx(numeric_score)
    assert stored.confidence == pytest.approx(
        max(float(numeric_score), 1.0 - float(numeric_score))
    )
    assert stored.probabilities == {
        "negative": pytest.approx(1.0 - float(numeric_score)),
        "positive": pytest.approx(numeric_score),
    }


def test_promoted_discovery_rejects_artifact_digest_mismatch(
    tmp_path: Path,
) -> None:
    _write_artifact(
        tmp_path / "bad-digest",
        artifact_hash="sha256:" + "0" * 64,
    )

    classifiers = promoted_classifiers(tmp_path)

    assert len(classifiers) == 1
    assert classifiers[0]["manifest_status"] == "invalid"
    assert classifiers[0]["production_status"] == "invalid"
    assert classifiers[0]["is_scoring_compatible"] is False
    assert "artifact SHA-256 mismatch" in " ".join(classifiers[0]["manifest_errors"])
