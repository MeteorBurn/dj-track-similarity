from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pytest

from dj_track_similarity.classifier_jobs import ClassifierJobManager
from dj_track_similarity.classifier_scoring import _embedding_vectors, analyze_classifier, default_classifier_model_path
from dj_track_similarity.database import LibraryDatabase


class FixedProbabilityModel:
    classes_ = np.asarray(["broken", "straight"])

    def predict_proba(self, matrix):
        return np.tile(np.asarray([[0.87, 0.13]], dtype=np.float64), (matrix.shape[0], 1))

    def predict(self, matrix):
        return np.asarray(["broken"] * matrix.shape[0])


class AlmostCertainModel:
    classes_ = np.asarray(["broken", "straight"])

    def predict_proba(self, matrix):
        return np.tile(np.asarray([[0.99999999, 0.00000001]], dtype=np.float64), (matrix.shape[0], 1))

    def predict(self, matrix):
        return np.asarray(["broken"] * matrix.shape[0])


def test_analyze_classifier_scores_feature_complete_tracks_and_skips_missing_features(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    complete_id = _track(db, tmp_path, "complete.wav")
    missing_id = _track(db, tmp_path, "missing.wav")
    db.save_sonara_features(complete_id, {"bpm": {"type": "float", "value": 128.0}}, model_name="sonara-test")
    db.save_embedding(complete_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(complete_id, np.asarray([1.0], dtype=np.float32), "maest-test", embedding_key="maest")
    model_path = _write_model(tmp_path / "model.joblib")

    result = analyze_classifier(db, classifier="break_energy", model_path=model_path)

    assert result == {"classifier": "break_energy", "scored": 1, "skipped": 1, "model": str(model_path)}
    score = db.classifier_score(complete_id, "break_energy")
    assert score is not None
    assert score["score"] == 0.87
    assert score["confidence"] == 0.87
    assert score["label"] == "high"
    assert score["probabilities"] == {
        "broken": 0.87,
        "straight": 0.13,
    }
    assert score["feature_set"] == "combined"
    assert score["model_id"] == str(model_path)
    assert db.classifier_score(missing_id, "break_energy") is None


def test_analyze_classifier_skips_tracks_with_existing_classifier_score(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    existing_id = _complete_track(db, tmp_path, "existing.wav")
    missing_id = _complete_track(db, tmp_path, "missing.wav")
    db.save_classifier_score(
        existing_id,
        classifier="break_energy",
        score=0.42,
        label="low",
        confidence=0.58,
        probabilities={"broken": 0.42, "straight": 0.58},
        feature_set="combined",
        model_id="old-model.joblib",
    )
    model_path = _write_model(tmp_path / "model.joblib")

    result = analyze_classifier(db, classifier="break_energy", model_path=model_path)

    assert result["scored"] == 1
    assert db.classifier_score(existing_id, "break_energy")["score"] == 0.42
    assert db.classifier_score(missing_id, "break_energy")["score"] == 0.87


def test_analyze_classifier_preserves_high_confidence_probability_precision(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "complete.wav")
    db.save_sonara_features(track_id, {"bpm": {"type": "float", "value": 128.0}}, model_name="sonara-test")
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "maest-test", embedding_key="maest")
    model_path = _write_model(tmp_path / "model.joblib", model=AlmostCertainModel())

    analyze_classifier(db, classifier="break_energy", model_path=model_path)

    score = db.classifier_score(track_id, "break_energy")
    assert score is not None
    assert score["score"] == 0.99999999
    assert score["confidence"] == 0.99999999
    assert score["probabilities"] == {
        "broken": 0.99999999,
        "straight": 0.00000001,
    }


def test_break_energy_filter_orders_tracks_by_score(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    low_id = _track(db, tmp_path, "low.wav", title="Low")
    high_id = _track(db, tmp_path, "high.wav", title="High")
    db.save_classifier_score(
        low_id,
        classifier="break_energy",
        score=0.72,
        label="medium",
        confidence=0.72,
        probabilities={"break_energy": 0.72, "straight_energy": 0.28},
        feature_set="combined",
        model_id="model.joblib",
    )
    db.save_classifier_score(
        high_id,
        classifier="break_energy",
        score=0.94,
        label="high",
        confidence=0.94,
        probabilities={"break_energy": 0.94, "straight_energy": 0.06},
        feature_set="combined",
        model_id="model.joblib",
    )

    page = db.list_tracks_page(classifier_min_scores={"break_energy": 0.8})
    filtered = db.list_filtered_tracks(classifier_min_scores={"break_energy": 0.8})

    assert [track.id for track in page["items"]] == [high_id]
    assert page["items"][0].classifier_scores["break_energy"]["score"] == 0.94
    assert [track.id for track in filtered["items"]] == [high_id]


def test_generic_classifier_filter_orders_tracks_by_score(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    low_id = _track(db, tmp_path, "low-live.wav", title="Low")
    high_id = _track(db, tmp_path, "high-live.wav", title="High")
    db.save_classifier_score(
        low_id,
        classifier="live_instrumentation",
        score=0.51,
        label="medium",
        confidence=0.51,
        probabilities={"live_instrument": 0.51, "no_instrument": 0.49},
        feature_set="combined",
        model_id="model.joblib",
    )
    db.save_classifier_score(
        high_id,
        classifier="live_instrumentation",
        score=0.91,
        label="high",
        confidence=0.91,
        probabilities={"live_instrument": 0.91, "no_instrument": 0.09},
        feature_set="combined",
        model_id="model.joblib",
    )

    page = db.list_tracks_page(classifier_min_scores={"live_instrumentation": 0.8})
    filtered = db.list_filtered_tracks(classifier_min_scores={"live_instrumentation": 0.8})

    assert [track.id for track in page["items"]] == [high_id]
    assert page["items"][0].classifier_scores["live_instrumentation"]["score"] == 0.91
    assert [track.id for track in filtered["items"]] == [high_id]


def test_classifier_jobs_are_scoped_by_classifier_key(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "one.wav")
    manager = ClassifierJobManager(db)

    break_job = manager.create_job(classifier="break_energy")
    live_job = manager.create_job(classifier="live_instrumentation")

    assert manager.latest(classifier="break_energy").job_id == break_job
    assert manager.latest(classifier="live_instrumentation").job_id == live_job
    assert manager.get(break_job, classifier="break_energy").adapter_name == "break_energy"
    with pytest.raises(KeyError):
        manager.get(live_job, classifier="break_energy")
    with pytest.raises(KeyError):
        manager.cancel(live_job, classifier="break_energy")
    assert manager.get(live_job).cancel_requested is False


def test_classifier_job_total_counts_only_missing_classifier_scores(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    existing_id = _track(db, tmp_path, "existing.wav")
    _track(db, tmp_path, "missing.wav")
    db.save_classifier_score(
        existing_id,
        classifier="break_energy",
        score=0.81,
        label="high",
        confidence=0.81,
        probabilities={"broken": 0.81, "straight": 0.19},
        feature_set="combined",
        model_id="model.joblib",
    )
    manager = ClassifierJobManager(db)

    job_id = manager.create_job(classifier="break_energy")

    assert manager.get(job_id).total == 1


def test_default_classifier_model_path_points_to_profile_classifier_asset() -> None:
    assert default_classifier_model_path("live_instrumentation").as_posix().endswith(
        "models/classifiers/live-instrumentation/model.joblib"
    )


def test_classifier_embedding_vector_map_reuses_cached_matrix_rows(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "one.wav")
    db.save_embedding(track_id, np.asarray([1.0, 2.0], dtype=np.float32), "mert-test", embedding_key="mert")
    _, matrix = db.load_embedding_matrix("mert")

    vectors = _embedding_vectors(db, "mert")

    assert np.shares_memory(vectors[track_id], matrix)


def _track(db: LibraryDatabase, tmp_path: Path, filename: str, title: str | None = None) -> int:
    path = tmp_path / filename
    path.write_bytes(b"audio")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1.0, metadata={"title": title or filename})


def _complete_track(db: LibraryDatabase, tmp_path: Path, filename: str) -> int:
    track_id = _track(db, tmp_path, filename)
    db.save_sonara_features(track_id, {"bpm": {"type": "float", "value": 128.0}}, model_name="sonara-test")
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "maest-test", embedding_key="maest")
    return track_id


def _write_model(path: Path, *, model: object | None = None) -> Path:
    payload = {
        "model": model or FixedProbabilityModel(),
        "feature_set": "combined",
        "feature_names": ["sonara:bpm", "mert:0", "maest:0"],
        "label_order": ["broken", "straight"],
        "classifier_key": "break_energy",
        "positive_label": "broken",
    }
    joblib.dump(payload, path)
    return path
