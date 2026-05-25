from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from .features import FEATURE_SETS, build_labeled_feature_matrix


LABEL_ORDER = ["broken", "straight"]
BROKEN_LABEL = "broken"
ARTIFACT_PREFIX = "break-energy"
BROKEN_DISCOVERY_THRESHOLDS = (0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
TOP_N_VALUES = (1, 5, 10, 25, 50, 100, 250, 500, 1000)


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
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split

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
    model = _make_model(random_state)
    model.fit(train_x, train_y)
    predictions = model.predict(test_x)
    broken_probabilities = _positive_probabilities(model, test_x, positive_label=BROKEN_LABEL)
    report = classification_report(test_y, predictions, labels=LABEL_ORDER, output_dict=True, zero_division=0)
    confusion = confusion_matrix(test_y, predictions, labels=LABEL_ORDER).tolist()

    artifact_root = Path(artifact_dir)
    artifact_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = artifact_root / f"{ARTIFACT_PREFIX}-{feature_set}-{stamp}.joblib"
    metrics_path = artifact_root / f"{ARTIFACT_PREFIX}-{feature_set}-{stamp}.metrics.json"
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
        "broken_discovery": _broken_discovery_metrics(test_y, broken_probabilities),
        "cross_validation": _cross_validation_metrics(matrix, labels, random_state=random_state),
    }
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return TrainResult(feature_set, model, artifact_path, metrics_path, len(labels), 0)


def benchmark_lab_database(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    artifact_dir: str | Path,
    *,
    feature_sets: tuple[str, ...] = FEATURE_SETS,
    random_state: int = 42,
) -> dict[str, dict[str, object]]:
    results: dict[str, dict[str, object]] = {}
    for feature_set in feature_sets:
        features = build_labeled_feature_matrix(source_db_path, labels_db_path, feature_set)
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


def _make_model(random_state: int):
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(
        StandardScaler(),
        LogisticRegression(class_weight="balanced", max_iter=1000, random_state=random_state),
    )


def _positive_probabilities(model: object, matrix: np.ndarray, *, positive_label: str) -> np.ndarray:
    predict_proba = getattr(model, "predict_proba", None)
    if callable(predict_proba):
        raw = np.asarray(predict_proba(matrix), dtype=np.float32)
        classes = [str(label) for label in getattr(model, "classes_", [])]
        if positive_label in classes:
            return raw[:, classes.index(positive_label)]
    return np.asarray([1.0 if str(label) == positive_label else 0.0 for label in model.predict(matrix)], dtype=np.float32)


def _broken_discovery_metrics(labels: list[str] | np.ndarray, broken_probabilities: np.ndarray) -> dict[str, object]:
    label_list = [str(label) for label in labels]
    scores = np.asarray(broken_probabilities, dtype=np.float32)
    total_broken = sum(1 for label in label_list if label == BROKEN_LABEL)
    thresholds = [
        _threshold_row(label_list, scores, threshold, total_broken)
        for threshold in BROKEN_DISCOVERY_THRESHOLDS
    ]
    top_n = [_top_n_row(label_list, scores, n, total_broken) for n in _bounded_top_n_values(len(label_list))]
    return {
        "positive_label": BROKEN_LABEL,
        "thresholds": thresholds,
        "top_n": top_n,
    }


def _threshold_row(labels: list[str], scores: np.ndarray, threshold: float, total_broken: int) -> dict[str, float | int]:
    selected = scores >= threshold
    candidate_count = int(np.count_nonzero(selected))
    broken_found = sum(1 for index, selected_row in enumerate(selected) if selected_row and labels[index] == BROKEN_LABEL)
    straight_candidates = candidate_count - broken_found
    return {
        "threshold": float(threshold),
        "candidate_count": candidate_count,
        "broken_found": int(broken_found),
        "straight_candidates": int(straight_candidates),
        "broken_recall": _safe_ratio(broken_found, total_broken),
        "broken_precision": _safe_ratio(broken_found, candidate_count),
    }


def _top_n_row(labels: list[str], scores: np.ndarray, n: int, total_broken: int) -> dict[str, float | int]:
    order = np.argsort(-scores, kind="stable")[:n]
    broken_found = sum(1 for index in order if labels[int(index)] == BROKEN_LABEL)
    return {
        "n": int(n),
        "broken_found": int(broken_found),
        "broken_recall": _safe_ratio(broken_found, total_broken),
        "broken_precision": _safe_ratio(broken_found, n),
    }


def _bounded_top_n_values(row_count: int) -> list[int]:
    values = [n for n in TOP_N_VALUES if n <= row_count]
    if row_count and row_count not in values:
        values.append(row_count)
    return values


def _cross_validation_metrics(matrix: np.ndarray, labels: list[str], *, random_state: int) -> dict[str, object]:
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.model_selection import StratifiedKFold

    class_counts = [labels.count(label) for label in LABEL_ORDER]
    fold_count = min(5, min(class_counts))
    splitter = StratifiedKFold(n_splits=fold_count, shuffle=True, random_state=random_state)
    broken_recalls: list[float] = []
    broken_precisions: list[float] = []
    macro_f1s: list[float] = []
    accuracies: list[float] = []
    for train_index, test_index in splitter.split(matrix, labels):
        model = _make_model(random_state)
        train_y = [labels[index] for index in train_index]
        test_y = [labels[index] for index in test_index]
        model.fit(matrix[train_index], train_y)
        predictions = model.predict(matrix[test_index])
        report = classification_report(test_y, predictions, labels=LABEL_ORDER, output_dict=True, zero_division=0)
        broken_recalls.append(float(report[BROKEN_LABEL]["recall"]))
        broken_precisions.append(float(report[BROKEN_LABEL]["precision"]))
        macro_f1s.append(float(report["macro avg"]["f1-score"]))
        accuracies.append(float(accuracy_score(test_y, predictions)))
    return {
        "fold_count": int(fold_count),
        "broken_recall_mean": _mean(broken_recalls),
        "broken_recall_std": _std(broken_recalls),
        "broken_precision_mean": _mean(broken_precisions),
        "broken_precision_std": _std(broken_precisions),
        "macro_f1_mean": _mean(macro_f1s),
        "macro_f1_std": _std(macro_f1s),
        "accuracy_mean": _mean(accuracies),
        "accuracy_std": _std(accuracies),
    }


def _safe_ratio(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float32))) if values else 0.0


def _std(values: list[float]) -> float:
    return float(np.std(np.asarray(values, dtype=np.float32))) if values else 0.0
