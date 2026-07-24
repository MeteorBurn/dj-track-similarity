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
    MERT_CHECKPOINT_ID,
    MERT_MODEL_REVISION,
    MERT_PREPROCESSING,
    classifier_required_outputs_hash,
    mert_embedding_output,
)
from dj_track_similarity.classifier_manifest import (
    classifier_feature_manifest_hash,
    load_classifier_manifest_summary,
)
from dj_track_similarity.classifier_scoring import (
    ClassifierScorer,
    analyze_classifier,
    load_classifier_requirements,
    promoted_classifiers,
    save_classifier_score_v7,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_schema_v7 import ClassifierScoreV7


_NOW = "2026-07-24T10:00:00.000000Z"
_ARTIFACT_BYTES = b"classifier-v7-test-artifact"


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
    return mert_embedding_output(
        model_version=MERT_MODEL_REVISION,
        checkpoint_id=MERT_CHECKPOINT_ID,
        preprocessing=MERT_PREPROCESSING,
        sample_rate_hz=24_000,
        window_seconds=5.0,
        max_windows=5,
        hidden_layers=(9, 10, 11, 12),
        pooling="last-4-layer-mean+masked-time-mean+window-mean+l2",
        parameters={
            "channel_downmix": "arithmetic-mean",
            "decoder": "shared-load-audio-mono-v1",
            "window_selection": "10%-90%-interior-evenly-spaced-rounded",
            "short_audio": "single-variable-length-window",
            "processor_normalization": "wav2vec2-do-normalize",
            "processor_padding": "right-zero-with-attention-mask",
        },
    )


def _artifact_hash(data: bytes = _ARTIFACT_BYTES) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _manifest_payload(
    output: AnalysisOutput,
    *,
    classifier_key: str = "test_classifier",
    model_id: str = "model-current",
    feature_names: tuple[str, ...] = ("mert:0",),
    artifact_hash: str | None = None,
    label_order: tuple[str, str] = ("negative", "positive"),
) -> dict[str, object]:
    return {
        "manifest_version": 2,
        "classifier_key": classifier_key,
        "model_id": model_id,
        "artifact_hash": artifact_hash or _artifact_hash(),
        "feature_set": "mert-contract",
        "feature_names": list(feature_names),
        "feature_count": len(feature_names),
        "feature_manifest_hash": classifier_feature_manifest_hash(feature_names),
        "label_order": list(label_order),
        "negative_label": "negative",
        "positive_label": "positive",
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


def _write_artifact(
    tmp_path: Path,
    output: AnalysisOutput,
    **manifest_changes: object,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(_ARTIFACT_BYTES)
    payload = _manifest_payload(output)
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


def _write_mert_embedding(
    db: LibraryDatabase,
    target: AnalysisTarget,
    output: AnalysisOutput,
) -> None:
    vector = np.zeros(int(output.contract.dim), dtype=np.float32)
    vector[0] = 1.0
    results = db.save_embedding_results(
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
    )
    assert len(results) == 1 and results[0].ok


def _score_write(
    target: AnalysisTarget,
    *,
    classifier_key: str,
    model_id: str,
    feature_manifest_hash: str = "sha256:" + "b" * 64,
    score: float = 0.8,
) -> ClassifierScoreWrite:
    output = _mert_output()
    specification = ClassifierSpecification(
        classifier_key=classifier_key,
        model_id=model_id,
        feature_set="mert-contract",
        feature_manifest_hash=feature_manifest_hash,
        required_outputs_hash=classifier_required_outputs_hash((output,)),
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
        score=ClassifierScoreV7(
            track_id=target.track_id,
            classifier_key=classifier_key,
            content_generation=target.content_generation,
            model_id=model_id,
            feature_set="mert-contract",
            feature_manifest_hash=feature_manifest_hash,
            required_outputs_hash=specification.required_outputs_hash,
            uses_sonara=0,
            sonara_release_hash=None,
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
                SELECT classifier_key, model_id, feature_manifest_hash,
                       required_outputs_hash,
                       predicted_class, score_bucket, score, confidence
                FROM classifier_scores
                WHERE classifier_key = ?
                ORDER BY track_id
                """,
                (classifier_key,),
            ).fetchall()
        ]


def test_artifact_and_model_validation_precede_stale_score_deletion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_mert_embedding(db, target, output)
    assert db.save_classifier_scores(
        (
            _score_write(
                target,
                classifier_key="test_classifier",
                model_id="model-stale",
            ),
            _score_write(
                target,
                classifier_key="other_classifier",
                model_id="other-model",
            ),
        )
    )[0].ok

    wrong_path = _write_artifact(
        tmp_path / "wrong-digest",
        output,
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
    assert _score_rows(db, "test_classifier")[0][1] == "model-stale"

    invalid_path = _write_artifact(tmp_path / "invalid-model", output)
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
    assert _score_rows(db, "test_classifier")[0][1] == "model-stale"

    valid_path = _write_artifact(tmp_path / "valid-model", output)
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
    assert result["deleted_stale"] == 1
    assert result["scored"] == 1
    current = _score_rows(db, "test_classifier")
    assert current == [
        (
            "test_classifier",
            "model-current",
            classifier_feature_manifest_hash(("mert:0",)),
            classifier_required_outputs_hash((output,)),
            "positive",
            "high",
            pytest.approx(0.8),
            pytest.approx(0.8),
        )
    ]
    assert _score_rows(db, "other_classifier")[0][1] == "other-model"


def test_requirements_reject_non_current_contract_and_out_of_range_feature(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    active = _mert_output()
    declared = AnalysisOutput(
        replace(active.contract, model_version="b" * 40),
    )
    db.register_analysis_outputs((active,))
    model_path = _write_artifact(tmp_path / "contract-mismatch", declared)

    with pytest.raises(ValueError, match="mert model_version must be"):
        load_classifier_requirements(
            db,
            "test_classifier",
            model_path=model_path,
        )

    out_of_range = _manifest_payload(
        active,
        feature_names=("mert:768",),
    )
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
        "outside the declared contract dimension" in error for error in summary.errors
    )
    with pytest.raises(ValueError, match="outside the declared contract dimension"):
        load_classifier_requirements(
            db,
            "test_classifier",
            model_path=range_path / "model.joblib",
        )


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
    model_path = _write_artifact(tmp_path / "artifact", output)
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
    feature_rows = db.load_classifier_feature_rows(
        requirements.specification,
        targets=(target,),
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
    payload = _manifest_payload(
        output,
        label_order=("positive", "negative"),
    )
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
    row = db.load_classifier_feature_rows(
        requirements.specification,
        targets=(target,),
    )[0]

    write = scorer.score_row(row, analyzed_at=_NOW)

    assert write.score.predicted_class == "positive"
    assert write.score.score_bucket == "medium"
    assert json.loads(write.score.probabilities_json) == {
        "negative": 0.5,
        "positive": 0.5,
    }


def test_classifier_writes_reject_wrong_uuid_and_generation(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    target = _insert_track(db, content_generation=2)
    base = _score_write(
        target,
        classifier_key="test_classifier",
        model_id="model-current",
    )

    wrong_uuid = replace(
        base,
        target=replace(target, track_uuid=str(uuid.uuid4())),
    )
    wrong_generation_target = replace(target, content_generation=1)
    wrong_generation = replace(
        base,
        target=wrong_generation_target,
        score=replace(base.score, content_generation=1),
    )

    uuid_result = save_classifier_score_v7(db, wrong_uuid)
    generation_result = save_classifier_score_v7(db, wrong_generation)

    assert not uuid_result.ok
    assert "track_uuid mismatch" in str(uuid_result.error)
    assert not generation_result.ok
    assert "generation" in str(generation_result.error)
    assert _score_rows(db, "test_classifier") == []


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
        model_id="model-current",
        score=0.5,
    )
    contradictory = replace(
        base,
        score=replace(base.score, **score_changes),
    )

    result = save_classifier_score_v7(db, contradictory)

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
        model_id="model-current",
        score=0.5,
    )
    malformed = replace(
        base,
        score=replace(base.score, **score_changes),
    )

    result = save_classifier_score_v7(db, malformed)

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
        model_id="model-current",
        score=numeric_score,
    )

    result = save_classifier_score_v7(db, write)
    detail = db.get_track_detail(target.track_id)

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


def test_promoted_discovery_hash_gates_scoring_compatibility(
    tmp_path: Path,
) -> None:
    output = _mert_output()
    _write_artifact(
        tmp_path / "bad-digest",
        output,
        artifact_hash="sha256:" + "0" * 64,
    )

    classifiers = promoted_classifiers(tmp_path)

    assert len(classifiers) == 1
    assert classifiers[0]["manifest_status"] == "invalid"
    assert classifiers[0]["production_status"] == "invalid"
    assert classifiers[0]["is_scoring_compatible"] is False
    assert "artifact SHA-256 mismatch" in " ".join(classifiers[0]["manifest_errors"])
