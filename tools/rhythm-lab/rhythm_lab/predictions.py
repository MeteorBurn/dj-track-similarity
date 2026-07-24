from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from .artifact_io import load_verified_artifact
from .features import build_unlabeled_feature_matrix
from .lab_db import RhythmLabDatabase


def apply_model_to_lab(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    artifact_path: str | Path,
    *,
    classifier_key: str | None = None,
) -> dict[str, int | str]:
    artifact = Path(artifact_path)
    payload = load_verified_artifact(artifact).payload
    resolved_classifier_key = str(classifier_key or payload.get("classifier_key") or "").strip()
    if not resolved_classifier_key:
        raise ValueError("classifier_key is required for prediction artifacts that do not declare one")
    model = payload["model"]
    feature_set = str(payload["feature_set"])
    label_order = [str(label) for label in payload.get("label_order", getattr(model, "classes_", []))]
    required_outputs = payload.get("required_outputs")
    features = build_unlabeled_feature_matrix(
        source_db_path,
        feature_set,
        expected_required_outputs=required_outputs,
    )
    if features.matrix.shape[0] == 0:
        return {
            "feature_set": feature_set,
            "predicted": 0,
            "skipped": len(features.skipped_identities),
        }

    predictions = model.predict(features.matrix)
    probabilities = _predict_probabilities(model, features.matrix, label_order)
    labels_db = RhythmLabDatabase(labels_db_path, classifier_key=resolved_classifier_key)
    for index, track in enumerate(features.tracks):
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
        "predicted": len(features.tracks),
        "skipped": len(features.skipped_identities),
    }


def export_predictions_csv(
    db_path: str | Path,
    output_path: str | Path,
    *,
    classifier_key: str,
) -> Path:
    lab = RhythmLabDatabase(db_path, classifier_key=classifier_key)
    profile = lab.get_profile()
    probability_labels = list(profile.training_label_keys)
    sort_label = profile.positive_label if profile.profile_type == "binary" else None
    rows = sorted(
        latest_predictions_by_track(lab.predictions()),
        key=lambda row: (
            -(_probability(row, sort_label) if sort_label is not None else float(row["confidence"])),
            -float(row["confidence"]),
            str(row["selected_path"]),
        ),
    )
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "catalog_uuid",
        "track_uuid",
        "content_generation",
        "label",
        "confidence",
        *[f"probability_{label}" for label in probability_labels],
        "feature_set",
        "artist",
        "title",
        "selected_path",
        "model_artifact",
        "probabilities",
    ]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "catalog_uuid": row["catalog_uuid"],
                    "track_uuid": row["track_uuid"],
                    "content_generation": row["content_generation"],
                    "label": row["label"],
                    "confidence": row["confidence"],
                    **{f"probability_{label}": _probability(row, label) for label in probability_labels},
                    "feature_set": row["feature_set"],
                    "artist": row["artist"],
                    "title": row["title"],
                    "selected_path": row["selected_path"],
                    "model_artifact": row["model_artifact"],
                    "probabilities": row["probabilities"],
                }
            )
    return target


def latest_predictions_by_track(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    latest: dict[tuple[str, str, int], dict[str, object]] = {}
    for row in rows:
        identity = (
            str(row["catalog_uuid"]),
            str(row["track_uuid"]),
            int(row["content_generation"]),
        )
        current = latest.get(identity)
        if current is None or _prediction_sort_key(row) > _prediction_sort_key(current):
            latest[identity] = row
    return list(latest.values())


def _prediction_sort_key(row: dict[str, object]) -> tuple[str, int, str]:
    return (
        str(row.get("updated_at") or ""),
        int(row.get("prediction_rowid") or 0),
        str(row.get("model_artifact") or ""),
    )


def _probability(row: dict[str, object], label: str) -> float:
    probabilities = row.get("probabilities")
    if not isinstance(probabilities, dict):
        return 0.0
    try:
        return float(probabilities.get(label, 0.0))
    except (TypeError, ValueError):
        return 0.0


def _predict_probabilities(model: object, matrix: np.ndarray, label_order: list[str]) -> list[dict[str, float]]:
    predict_proba = getattr(model, "predict_proba", None)
    if callable(predict_proba):
        raw = np.asarray(predict_proba(matrix), dtype=np.float64)
        classes = [str(label) for label in getattr(model, "classes_", label_order)]
        return [
            {classes[index]: float(row[index]) for index in range(len(classes))}
            for row in raw
        ]
    predictions = [str(label) for label in model.predict(matrix)]
    return [{label: 1.0 if label == predicted else 0.0 for label in label_order} for predicted in predictions]
