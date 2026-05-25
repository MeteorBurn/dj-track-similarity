from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np

from dj_track_similarity.break_energy import analyze_break_energy, default_break_energy_model_path
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


def test_analyze_break_energy_scores_feature_complete_tracks_and_skips_missing_features(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    complete_id = _track(db, tmp_path, "complete.wav")
    missing_id = _track(db, tmp_path, "missing.wav")
    db.save_sonara_features(complete_id, {"bpm": {"type": "float", "value": 128.0}}, model_name="sonara-test")
    db.save_embedding(complete_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(complete_id, np.asarray([1.0], dtype=np.float32), "maest-test", embedding_key="maest")
    model_path = _write_model(tmp_path / "model.joblib")

    result = analyze_break_energy(db, model_path=model_path)

    assert result == {"classifier": "break_energy", "scored": 1, "skipped": 1, "model": str(model_path)}
    score = db.classifier_score(complete_id, "break_energy")
    assert score is not None
    assert score["score"] == 0.87
    assert score["confidence"] == 0.87
    assert score["label"] == "high"
    assert score["probabilities"] == {
        "break_energy": 0.87,
        "straight_energy": 0.13,
    }
    assert score["feature_set"] == "combined"
    assert score["model_id"] == str(model_path)
    assert db.classifier_score(missing_id, "break_energy") is None


def test_analyze_break_energy_preserves_high_confidence_probability_precision(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "complete.wav")
    db.save_sonara_features(track_id, {"bpm": {"type": "float", "value": 128.0}}, model_name="sonara-test")
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "maest-test", embedding_key="maest")
    model_path = _write_model(tmp_path / "model.joblib", model=AlmostCertainModel())

    analyze_break_energy(db, model_path=model_path)

    score = db.classifier_score(track_id, "break_energy")
    assert score is not None
    assert score["score"] == 0.99999999
    assert score["confidence"] == 0.99999999
    assert score["probabilities"] == {
        "break_energy": 0.99999999,
        "straight_energy": 0.00000001,
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

    page = db.list_tracks_page(min_break_energy=0.8)
    filtered = db.list_filtered_tracks(min_break_energy=0.8)

    assert [track.id for track in page["items"]] == [high_id]
    assert page["items"][0].classifier_scores["break_energy"]["score"] == 0.94
    assert [track.id for track in filtered["items"]] == [high_id]


def test_default_break_energy_model_path_points_to_stable_classifier_asset() -> None:
    assert default_break_energy_model_path().as_posix().endswith("models/classifiers/break-energy/model.joblib")


def _track(db: LibraryDatabase, tmp_path: Path, filename: str, title: str | None = None) -> int:
    path = tmp_path / filename
    path.write_bytes(b"audio")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1.0, metadata={"title": title or filename})


def _write_model(path: Path, *, model: object | None = None) -> Path:
    payload = {
        "model": model or FixedProbabilityModel(),
        "feature_set": "combined",
        "feature_names": ["sonara:bpm", "mert:0", "maest:0"],
        "label_order": ["broken", "straight"],
    }
    joblib.dump(payload, path)
    return path
