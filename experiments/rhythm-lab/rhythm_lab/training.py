from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from .features import FEATURE_SETS, build_labeled_feature_matrix


LABEL_ORDER = ["broken", "straight"]


@dataclass(frozen=True)
class TrainResult:
    feature_set: str
    model: object
    artifact_path: Path
    metrics_path: Path
    trained_rows: int
    skipped_rows: int


def train_feature_set(
    matrix: np.ndarray,
    labels: list[str],
    *,
    feature_names: list[str],
    feature_set: str,
    artifact_dir: str | Path,
    random_state: int = 42,
) -> TrainResult:
    from joblib import dump
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    matrix = np.asarray(matrix, dtype=np.float32)
    labels = [str(label) for label in labels]
    _validate_training_data(matrix, labels)

    train_x, test_x, train_y, test_y = train_test_split(
        matrix,
        labels,
        test_size=_test_size(len(labels)),
        random_state=random_state,
        stratify=labels,
    )
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", max_iter=1000, random_state=random_state),
    )
    model.fit(train_x, train_y)
    predictions = model.predict(test_x)
    report = classification_report(test_y, predictions, labels=LABEL_ORDER, output_dict=True, zero_division=0)
    confusion = confusion_matrix(test_y, predictions, labels=LABEL_ORDER).tolist()

    artifact_root = Path(artifact_dir)
    artifact_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = artifact_root / f"rhythm-{feature_set}-{stamp}.joblib"
    metrics_path = artifact_root / f"rhythm-{feature_set}-{stamp}.metrics.json"
    payload = {
        "model": model,
        "feature_set": feature_set,
        "feature_names": list(feature_names),
        "label_order": LABEL_ORDER,
        "created_at": stamp,
    }
    dump(payload, artifact_path)
    metrics = {
        "feature_set": feature_set,
        "created_at": stamp,
        "label_order": LABEL_ORDER,
        "trained_rows": len(labels),
        "test_rows": len(test_y),
        "feature_count": int(matrix.shape[1]),
        "classification_report": report,
        "confusion_matrix": confusion,
    }
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return TrainResult(feature_set, model, artifact_path, metrics_path, len(labels), 0)


def benchmark_lab_database(
    db_path: str | Path,
    artifact_dir: str | Path,
    *,
    feature_sets: tuple[str, ...] = FEATURE_SETS,
    random_state: int = 42,
) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for feature_set in feature_sets:
        features = build_labeled_feature_matrix(db_path, feature_set)
        try:
            result = train_feature_set(
                features.matrix,
                features.labels,
                feature_names=features.feature_names,
                feature_set=feature_set,
                artifact_dir=artifact_dir,
                random_state=random_state,
            )
            results[feature_set] = {
                "status": "trained",
                "artifact_path": str(result.artifact_path),
                "metrics_path": str(result.metrics_path),
                "trained_rows": result.trained_rows,
                "skipped_rows": len(features.skipped_track_ids),
                "feature_count": len(features.feature_names),
            }
        except ValueError as error:
            results[feature_set] = {
                "status": "skipped",
                "error": str(error),
                "available_rows": int(features.matrix.shape[0]),
                "skipped_rows": len(features.skipped_track_ids),
                "feature_count": len(features.feature_names),
            }
    return results


def _validate_training_data(matrix: np.ndarray, labels: list[str]) -> None:
    if matrix.ndim != 2:
        raise ValueError("Training matrix must be two-dimensional")
    if matrix.shape[0] != len(labels):
        raise ValueError("Training matrix row count must match label count")
    if matrix.shape[0] < 4:
        raise ValueError("At least four labeled rows are required for train/test split")
    counts = {label: labels.count(label) for label in LABEL_ORDER}
    missing = [label for label, count in counts.items() if count < 2]
    if missing:
        raise ValueError(f"At least two rows are required for each training label: {', '.join(missing)}")
    unsupported = sorted(set(labels) - set(LABEL_ORDER))
    if unsupported:
        raise ValueError(f"Unsupported labels for training: {', '.join(unsupported)}")


def _test_size(row_count: int) -> float:
    return 0.5 if row_count < 8 else 0.25
