from __future__ import annotations

import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pytest


LAB_ROOT = Path(__file__).resolve().parents[1]
if str(LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(LAB_ROOT))

from dj_track_similarity.analysis_contracts import ContractIdentity  # noqa: E402
from dj_track_similarity.analysis_model_runners import (  # noqa: E402
    current_embedding_analysis_output,
)
from dj_track_similarity.library_models import AnalysisCoverage  # noqa: E402
from rhythm_lab.artifact_io import artifact_sha256  # noqa: E402
from rhythm_lab.cli import PromotionError, promote_profile_model  # noqa: E402
from rhythm_lab.lab_db import RhythmLabDatabase, TrackIdentity  # noqa: E402
from rhythm_lab.predictions import _predict_probabilities  # noqa: E402
from rhythm_lab.source_db import SourceTrack  # noqa: E402
from rhythm_lab.training import train_feature_set  # noqa: E402
from rhythm_lab.web_app import cleanup_training_artifacts  # noqa: E402


def _track(index: int, *, generation: int = 1) -> SourceTrack:
    return SourceTrack(
        catalog_uuid="catalog-v7",
        track_id=index,
        track_uuid=f"track-{index}",
        content_generation=generation,
        file_path=f"C:/music/{index}.wav",
        file_size_bytes=1_000 + index,
        file_modified_ns=2_000 + index,
        audio_duration_seconds=180.0,
        file_tags=None,
        liked=False,
        sonara_features=None,
        sonara_contract=None,
        maest=None,
        maest_contract=None,
        analysis_coverage=AnalysisCoverage(),
    )


def _identity(track: SourceTrack) -> TrackIdentity:
    return TrackIdentity(
        catalog_uuid=track.catalog_uuid,
        track_uuid=track.track_uuid,
        content_generation=track.content_generation,
        file_path=track.file_path,
    )


def _queue_item(track: SourceTrack, *, priority: float) -> dict[str, object]:
    return {
        "catalog_uuid": track.catalog_uuid,
        "track_uuid": track.track_uuid,
        "content_generation": track.content_generation,
        "selected_path": track.file_path,
        "score": 0.5,
        "priority": priority,
        "reason": {"source": "test"},
    }


def _create_profile(
    path: Path,
    *,
    classifier_key: str = "focused",
    artifact_dir: Path | None = None,
) -> RhythmLabDatabase:
    database = RhythmLabDatabase(path)
    database.create_profile(
        classifier_key=classifier_key,
        name=classifier_key.replace("_", " ").title(),
        artifact_dir=artifact_dir,
        labels=[
            {"key": "yes", "name": "Yes", "role": "positive"},
            {"key": "no", "name": "No", "role": "negative"},
            {"key": "review", "name": "Review", "role": "review"},
        ],
    )
    return RhythmLabDatabase(path, classifier_key=classifier_key)


def _required_output() -> ContractIdentity:
    return current_embedding_analysis_output("mert").contract


def _train_artifact(
    artifact_dir: Path,
    *,
    classifier_key: str = "focused",
):
    output = _required_output()
    matrix = np.asarray(
        [[float(index % 2), float((index + 1) % 2)] for index in range(20)],
        dtype=np.float32,
    )
    labels = ["yes" if index % 2 == 0 else "no" for index in range(20)]
    return train_feature_set(
        matrix,
        labels,
        feature_names=["mert:0", "mert:1"],
        feature_set="mert",
        artifact_dir=artifact_dir,
        label_order=["yes", "no"],
        positive_label="yes",
        artifact_prefix=classifier_key.replace("_", "-"),
        classifier_key=classifier_key,
        required_outputs=[
            {
                "contract_hash": output.contract_hash,
                "canonical_payload": output.canonical_payload,
            }
        ],
    )


class _ConstantClassifier:
    def __init__(self, label: str, *, classes_: list[str]) -> None:
        self.label = label
        self.classes_ = np.asarray(classes_)

    def predict(self, matrix: np.ndarray) -> np.ndarray:
        return np.asarray([self.label] * len(matrix))


def test_lab_database_starts_without_implicit_profiles(tmp_path: Path) -> None:
    database = RhythmLabDatabase(tmp_path / "lab.sqlite")

    assert database.list_profiles() == []
    with pytest.raises(ValueError, match="profile key is required"):
        database.get_profile()


def test_profile_creation_update_archive_and_unique_names(tmp_path: Path) -> None:
    path = tmp_path / "lab.sqlite"
    focused = _create_profile(path)
    profile = focused.get_profile()

    assert profile.training_label_keys == ("yes", "no")
    assert profile.label_keys == ("yes", "no", "review")
    updated = focused.update_profile(
        "focused",
        name="Focused Updated",
        training_min_added=12,
    )
    assert updated.name == "Focused Updated"
    assert updated.training_min_added == 12

    root = RhythmLabDatabase(path)
    with pytest.raises(ValueError, match="already exists"):
        root.create_profile(
            classifier_key="duplicate",
            name="focused updated",
            labels=[
                {"key": "up", "name": "Up", "role": "positive"},
                {"key": "down", "name": "Down", "role": "negative"},
            ],
        )
    root.archive_profile("focused")
    assert root.list_profiles() == []
    assert root.list_profiles(include_archived=True)[0].archived_at is not None


def test_multiclass_profile_uses_all_class_labels_for_training(
    tmp_path: Path,
) -> None:
    database = RhythmLabDatabase(tmp_path / "lab.sqlite")
    profile = database.create_profile(
        classifier_key="mood",
        profile_type="multiclass",
        name="Mood",
        labels=[
            {"key": "bright", "name": "Bright", "role": "class"},
            {"key": "dark", "name": "Dark", "role": "class"},
            {"key": "neutral", "name": "Neutral", "role": "class"},
        ],
    )

    assert profile.training_label_keys == ("bright", "dark", "neutral")


def test_labels_use_exact_v7_identity_and_remain_profile_scoped(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lab.sqlite"
    focused = _create_profile(path)
    other = _create_profile(path, classifier_key="other")
    track = _track(1)

    focused.set_label(track, "yes", note="manual")
    other.set_label(track, "no")

    assert focused.label_for_track(_identity(track)).label == "yes"
    assert other.label_for_track(_identity(track)).label == "no"
    assert focused.label_for_track(
        _identity(_track(1, generation=2))
    ) is None

    focused.set_label(track, "no")
    assert focused.label_counts() == {"no": 1}
    focused.set_label(track, None)
    assert focused.label_for_track(_identity(track)) is None
    assert other.label_for_track(_identity(track)).label == "no"


def test_label_rename_migrates_labels_predictions_and_checkpoint(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lab.sqlite"
    database = _create_profile(path)
    track = _track(1)
    database.set_label(track, "yes")
    database.save_prediction(
        track,
        feature_set="mert",
        model_artifact="old.joblib",
        label="yes",
        confidence=0.8,
        probabilities={"yes": 0.8, "no": 0.2},
    )
    database.record_training_checkpoint(
        {"yes": 1, "no": 0},
        model_artifact="old.joblib",
    )

    profile = database.rename_label_key("focused", "yes", "positive")

    assert profile.positive_label == "positive"
    assert database.label_counts() == {"positive": 1}
    assert database.predictions()[0]["label"] == "positive"
    assert database.predictions()[0]["probabilities"] == {
        "no": 0.2,
        "positive": 0.8,
    }
    assert database.training_checkpoint()["counts"] == {
        "no": 0,
        "positive": 1,
    }


def test_queue_upsert_state_transitions_and_profile_isolation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lab.sqlite"
    focused = _create_profile(path)
    other = _create_profile(path, classifier_key="other")
    first = _track(1)
    second = _track(2)

    assert focused.upsert_label_queue_items(
        mode="uncertainty",
        items=[_queue_item(first, priority=1), _queue_item(second, priority=2)],
    ) == 2
    assert focused.upsert_label_queue_items(
        mode="uncertainty",
        items=[_queue_item(first, priority=9)],
    ) == 1
    other.upsert_label_queue_items(
        mode="uncertainty",
        items=[_queue_item(first, priority=3)],
    )

    focused_rows = focused.label_queue_items()
    assert [row["track_uuid"] for row in focused_rows] == [
        first.track_uuid,
        second.track_uuid,
    ]
    changed = focused.mark_queue_item(
        int(focused_rows[0]["id"]),
        state="accepted_for_labeling",
    )
    assert changed["state"] == "accepted_for_labeling"
    assert focused.clear_label_queue(state="accepted_for_labeling") == 1
    assert len(focused.label_queue_items()) == 1
    assert len(other.label_queue_items()) == 1


def test_predictions_preserve_precision_and_prune_only_selected_feature(
    tmp_path: Path,
) -> None:
    database = _create_profile(tmp_path / "lab.sqlite")
    track = _track(1)
    database.save_prediction(
        track,
        feature_set="mert",
        model_artifact="old.joblib",
        label="yes",
        confidence=0.5000000001,
        probabilities={"yes": 0.5000000001, "no": 0.4999999999},
    )
    database.save_prediction(
        track,
        feature_set="mert",
        model_artifact="new.joblib",
        label="yes",
        confidence=0.75,
        probabilities={"yes": 0.75, "no": 0.25},
    )
    database.save_prediction(
        track,
        feature_set="maest",
        model_artifact="other.joblib",
        label="no",
        confidence=0.9,
        probabilities={"yes": 0.1, "no": 0.9},
    )

    assert database.prune_predictions(
        feature_set="mert",
        keep_model_artifact="new.joblib",
    ) == 1
    assert {
        (row["feature_set"], row["model_artifact"])
        for row in database.predictions()
    } == {
        ("mert", "new.joblib"),
        ("maest", "other.joblib"),
    }


def test_profile_delete_is_scoped_to_the_selected_profile(
    tmp_path: Path,
) -> None:
    path = tmp_path / "lab.sqlite"
    focused = _create_profile(path)
    other = _create_profile(path, classifier_key="other")
    focused.set_label(_track(1), "yes")
    other.set_label(_track(2), "no")

    deleted = focused.delete_profile(classifier_key="focused")

    assert deleted.classifier_key == "focused"
    assert RhythmLabDatabase(path).list_profiles()[0].classifier_key == "other"
    assert other.label_counts() == {"no": 1}


def test_training_checkpoint_tracks_only_current_profile_labels(
    tmp_path: Path,
) -> None:
    database = _create_profile(tmp_path / "lab.sqlite")

    assert database.training_checkpoint() == {
        "counts": {"yes": 0, "no": 0},
        "model_artifact": None,
        "updated_at": None,
    }
    database.record_training_checkpoint(
        {"yes": 12, "no": 9, "ignored": 99},
        model_artifact="model.joblib",
    )

    checkpoint = database.training_checkpoint()
    assert checkpoint["counts"] == {"yes": 12, "no": 9}
    assert checkpoint["model_artifact"] == "model.joblib"
    assert checkpoint["updated_at"] is not None


def test_train_feature_set_binds_exact_bytes_to_metrics(tmp_path: Path) -> None:
    result = _train_artifact(tmp_path / "artifacts")
    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))

    assert metrics["artifact_filename"] == result.artifact_path.name
    assert metrics["artifact_hash"] == artifact_sha256(
        result.artifact_path.read_bytes()
    )
    assert metrics["feature_count"] == 2
    assert metrics["required_outputs"][0]["contract_hash"] == (
        _required_output().contract_hash
    )
    payload = joblib.load(result.artifact_path)
    assert payload["classifier_key"] == "focused"
    assert payload["feature_names"] == ["mert:0", "mert:1"]


def test_promotion_requires_matching_profile_and_calibration_gate(
    tmp_path: Path,
) -> None:
    lab_path = tmp_path / "lab.sqlite"
    _create_profile(lab_path)
    result = _train_artifact(tmp_path / "artifacts")

    with pytest.raises(PromotionError, match="calibration is required"):
        promote_profile_model(
            lab_path,
            "focused",
            artifact_path=result.artifact_path,
            target_root=tmp_path / "promoted",
            require_calibration=True,
        )

    payload = joblib.load(result.artifact_path)
    payload["classifier_key"] = "other"
    joblib.dump(payload, result.artifact_path)
    metrics = json.loads(result.metrics_path.read_text(encoding="utf-8"))
    metrics["artifact_hash"] = artifact_sha256(result.artifact_path.read_bytes())
    result.metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
    with pytest.raises(PromotionError, match="Expected artifact for profile"):
        promote_profile_model(
            lab_path,
            "focused",
            artifact_path=result.artifact_path,
            target_root=tmp_path / "promoted",
        )


def test_predict_probabilities_preserves_high_confidence_precision() -> None:
    model = _ConstantClassifier("yes", classes_=["no", "yes"])

    probabilities = _predict_probabilities(
        model,
        np.zeros((2, 2), dtype=np.float32),
        ["no", "yes"],
    )

    assert probabilities == [
        {"no": 0.0, "yes": 1.0},
        {"no": 0.0, "yes": 1.0},
    ]


def test_artifact_cleanup_keeps_recent_and_protected_models(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    models = [
        root / f"focused-mert-20260724T10000{index}Z.joblib"
        for index in range(4)
    ]
    for index, model in enumerate(models):
        model.write_bytes(f"model-{index}".encode())
        model.with_suffix(".metrics.json").write_text("{}", encoding="utf-8")

    result = cleanup_training_artifacts(
        root,
        protected_artifact=models[0],
        artifact_prefix="focused",
        keep_joblib_per_feature=2,
        keep_metrics_per_feature=2,
    )

    assert result == {"deleted_joblib": 1, "deleted_metrics": 2}
    assert models[0].exists()
    assert not models[1].exists()
    assert models[2].exists()
    assert models[3].exists()
