from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from .features import build_unlabeled_feature_matrix
from .lab_db import RhythmLabDatabase
from .source_db import SourceDatabase


def apply_model_to_lab(source_db_path: str | Path, labels_db_path: str | Path, artifact_path: str | Path) -> dict[str, int | str]:
    import joblib

    artifact = Path(artifact_path)
    payload = joblib.load(artifact)
    model = payload["model"]
    feature_set = str(payload["feature_set"])
    label_order = [str(label) for label in payload.get("label_order", getattr(model, "classes_", []))]
    features = build_unlabeled_feature_matrix(source_db_path, feature_set)
    if features.matrix.shape[0] == 0:
        return {"feature_set": feature_set, "predicted": 0, "skipped": len(features.skipped_track_ids)}

    predictions = model.predict(features.matrix)
    probabilities = _predict_probabilities(model, features.matrix, label_order)
    labels_db = RhythmLabDatabase(labels_db_path)
    source = SourceDatabase(source_db_path)
    for index, track_id in enumerate(features.track_ids):
        track = source.get_track(track_id)
        label = str(predictions[index])
        row_probabilities = probabilities[index]
        confidence = float(row_probabilities.get(label, 0.0))
        labels_db.save_prediction(
            track,
            feature_set=feature_set,
            model_artifact=artifact,
            label=label,
            confidence=confidence,
            probabilities=row_probabilities,
        )
    return {
        "feature_set": feature_set,
        "predicted": len(features.track_ids),
        "skipped": len(features.skipped_track_ids),
    }


def export_predictions_csv(db_path: str | Path, output_path: str | Path) -> Path:
    lab = RhythmLabDatabase(db_path)
    rows = lab.predictions()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "source_track_id",
        "label",
        "confidence",
        "feature_set",
        "artist",
        "title",
        "path",
        "model_artifact",
        "probabilities",
    ]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source_track_id": row["source_track_id"],
                    "label": row["label"],
                    "confidence": row["confidence"],
                    "feature_set": row["feature_set"],
                    "artist": row["artist"],
                    "title": row["title"],
                    "path": row["path"],
                    "model_artifact": row["model_artifact"],
                    "probabilities": row["probabilities"],
                }
            )
    return target


def _predict_probabilities(model: object, matrix: np.ndarray, label_order: list[str]) -> list[dict[str, float]]:
    predict_proba = getattr(model, "predict_proba", None)
    if callable(predict_proba):
        raw = np.asarray(predict_proba(matrix), dtype=np.float32)
        classes = [str(label) for label in getattr(model, "classes_", label_order)]
        return [
            {classes[index]: float(row[index]) for index in range(len(classes))}
            for row in raw
        ]
    predictions = [str(label) for label in model.predict(matrix)]
    return [{label: 1.0 if label == predicted else 0.0 for label in label_order} for predicted in predictions]
