from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np

from .features import FEATURE_SETS, build_labeled_feature_matrix
from .lab_db import BREAK_ENERGY_CLASSIFIER_KEY, RhythmLabDatabase


LABEL_ORDER = ["broken", "straight"]
DEFAULT_POSITIVE_LABEL = "broken"
ARTIFACT_PREFIX = "break-energy"
POSITIVE_DISCOVERY_THRESHOLDS = (0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
TOP_N_VALUES = (1, 5, 10, 25, 50, 100, 250, 500, 1000)
MIN_CALIBRATION_LABELS = 100
MIN_CALIBRATION_POSITIVE = 20
MIN_CALIBRATION_NEGATIVE = 20


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
    label_order: list[str] | None = None,
    positive_label: str = DEFAULT_POSITIVE_LABEL,
    artifact_prefix: str = ARTIFACT_PREFIX,
    classifier_key: str = BREAK_ENERGY_CLASSIFIER_KEY,
    random_state: int = 42,
    calibrate: bool = False,
) -> TrainResult:
    from joblib import dump
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split

    matrix = np.asarray(matrix, dtype=np.float32)
    labels = [str(label) for label in labels]
    ordered_labels = [str(label) for label in (label_order or LABEL_ORDER)]
    positive_label = str(positive_label)
    _validate_training_data(matrix, labels, label_order=ordered_labels)

    train_x, test_x, train_y, test_y = train_test_split(
        matrix,
        labels,
        test_size=_test_size(len(labels)),
        random_state=random_state,
        stratify=labels,
    )
    label_counts = {label: labels.count(label) for label in ordered_labels}
    calibration_gate = _calibration_gate(
        label_counts,
        positive_label=positive_label,
        label_order=ordered_labels,
        calibrate_requested=calibrate,
    )
    if calibration_gate["status"] == "ready":
        cv_folds = min(3, *(label_counts[label] for label in ordered_labels))
        model = CalibratedClassifierCV(
            estimator=_make_model(random_state),
            method="sigmoid",
            cv=max(2, int(cv_folds)),
        )
        calibration_method = "sigmoid"
    else:
        model = _make_model(random_state)
        calibration_method = None
    model.fit(train_x, train_y)
    predictions = model.predict(test_x)
    positive_probabilities = _positive_probabilities(model, test_x, positive_label=positive_label)
    report = classification_report(test_y, predictions, labels=ordered_labels, output_dict=True, zero_division=0)
    confusion = confusion_matrix(test_y, predictions, labels=ordered_labels).tolist()

    artifact_root = Path(artifact_dir)
    artifact_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact_path = artifact_root / f"{artifact_prefix}-{feature_set}-{stamp}.joblib"
    metrics_path = artifact_root / f"{artifact_prefix}-{feature_set}-{stamp}.metrics.json"
    payload = {
        "classifier_key": classifier_key,
        "model": model,
        "feature_set": feature_set,
        "feature_names": list(feature_names),
        "label_order": ordered_labels,
        "positive_label": positive_label,
        "created_at": stamp,
    }
    positive_discovery = _positive_discovery_metrics(test_y, positive_probabilities, positive_label=positive_label)
    cross_validation = _cross_validation_metrics(
        matrix,
        labels,
        label_order=ordered_labels,
        positive_label=positive_label,
        random_state=random_state,
    )
    production_calibration = _production_calibration_report(
        test_y,
        predictions,
        positive_probabilities,
        label_counts=label_counts,
        label_order=ordered_labels,
        positive_label=positive_label,
        calibration_gate=calibration_gate,
        calibration_method=calibration_method,
    )
    payload["production_calibration"] = production_calibration
    dump(payload, artifact_path)
    metrics = {
        "classifier_key": classifier_key,
        "feature_set": feature_set,
        "created_at": stamp,
        "label_order": ordered_labels,
        "positive_label": positive_label,
        "trained_rows": len(labels),
        "test_rows": len(test_y),
        "feature_count": int(matrix.shape[1]),
        "classification_report": report,
        "confusion_matrix": confusion,
        "positive_discovery": positive_discovery,
        "cross_validation": cross_validation,
        "production_calibration": production_calibration,
    }
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return TrainResult(feature_set, model, artifact_path, metrics_path, len(labels), 0)


def benchmark_lab_database(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    artifact_dir: str | Path,
    *,
    classifier_key: str = BREAK_ENERGY_CLASSIFIER_KEY,
    feature_sets: tuple[str, ...] = FEATURE_SETS,
    random_state: int = 42,
    calibrate: bool = False,
) -> dict[str, dict[str, object]]:
    profile = RhythmLabDatabase(labels_db_path, classifier_key=classifier_key).get_profile()
    label_order = list(profile.training_label_keys)
    results: dict[str, dict[str, object]] = {}
    for feature_set in feature_sets:
        features = build_labeled_feature_matrix(
            source_db_path,
            labels_db_path,
            feature_set,
            classifier_key=profile.classifier_key,
        )
        try:
            result = train_feature_set(
                features.matrix,
                features.labels,
                feature_names=features.feature_names,
                feature_set=feature_set,
                artifact_dir=artifact_dir,
                label_order=label_order,
                positive_label=profile.positive_label,
                artifact_prefix=profile.artifact_prefix,
                classifier_key=profile.classifier_key,
                random_state=random_state,
                calibrate=calibrate,
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


def _validate_training_data(matrix: np.ndarray, labels: list[str], *, label_order: list[str]) -> None:
    if matrix.ndim != 2:
        raise ValueError("Training matrix must be two-dimensional")
    if matrix.shape[0] != len(labels):
        raise ValueError("Training matrix row count must match label count")
    if matrix.shape[0] < 4:
        raise ValueError("At least four labeled rows are required for train/test split")
    counts = {label: labels.count(label) for label in label_order}
    missing = [label for label, count in counts.items() if count < 2]
    if missing:
        raise ValueError(f"At least two rows are required for each training label: {', '.join(missing)}")
    unsupported = sorted(set(labels) - set(label_order))
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


def _positive_discovery_metrics(
    labels: list[str] | np.ndarray,
    positive_probabilities: np.ndarray,
    *,
    positive_label: str,
) -> dict[str, object]:
    label_list = [str(label) for label in labels]
    scores = np.asarray(positive_probabilities, dtype=np.float32)
    total_positive = sum(1 for label in label_list if label == positive_label)
    thresholds = [
        _threshold_row(label_list, scores, threshold, total_positive, positive_label=positive_label)
        for threshold in POSITIVE_DISCOVERY_THRESHOLDS
    ]
    top_n = [
        _top_n_row(label_list, scores, n, total_positive, positive_label=positive_label)
        for n in _bounded_top_n_values(len(label_list))
    ]
    return {
        "positive_label": positive_label,
        "thresholds": thresholds,
        "top_n": top_n,
    }


def _threshold_row(
    labels: list[str],
    scores: np.ndarray,
    threshold: float,
    total_positive: int,
    *,
    positive_label: str,
) -> dict[str, float | int]:
    selected = scores >= threshold
    candidate_count = int(np.count_nonzero(selected))
    positive_found = sum(
        1 for index, selected_row in enumerate(selected) if selected_row and labels[index] == positive_label
    )
    negative_candidates = candidate_count - positive_found
    return {
        "threshold": float(threshold),
        "candidate_count": candidate_count,
        "positive_found": int(positive_found),
        "negative_candidates": int(negative_candidates),
        "positive_recall": _safe_ratio(positive_found, total_positive),
        "positive_precision": _safe_ratio(positive_found, candidate_count),
    }


def _top_n_row(
    labels: list[str],
    scores: np.ndarray,
    n: int,
    total_positive: int,
    *,
    positive_label: str,
) -> dict[str, float | int]:
    order = np.argsort(-scores, kind="stable")[:n]
    positive_found = sum(1 for index in order if labels[int(index)] == positive_label)
    return {
        "n": int(n),
        "positive_found": int(positive_found),
        "positive_recall": _safe_ratio(positive_found, total_positive),
        "positive_precision": _safe_ratio(positive_found, n),
    }


def _bounded_top_n_values(row_count: int) -> list[int]:
    values = [n for n in TOP_N_VALUES if n <= row_count]
    if row_count and row_count not in values:
        values.append(row_count)
    return values


def _cross_validation_metrics(
    matrix: np.ndarray,
    labels: list[str],
    *,
    label_order: list[str],
    positive_label: str,
    random_state: int,
) -> dict[str, object]:
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.model_selection import StratifiedKFold

    class_counts = [labels.count(label) for label in label_order]
    fold_count = min(5, min(class_counts))
    splitter = StratifiedKFold(n_splits=fold_count, shuffle=True, random_state=random_state)
    positive_recalls: list[float] = []
    positive_precisions: list[float] = []
    macro_f1s: list[float] = []
    accuracies: list[float] = []
    for train_index, test_index in splitter.split(matrix, labels):
        model = _make_model(random_state)
        train_y = [labels[index] for index in train_index]
        test_y = [labels[index] for index in test_index]
        model.fit(matrix[train_index], train_y)
        predictions = model.predict(matrix[test_index])
        report = classification_report(test_y, predictions, labels=label_order, output_dict=True, zero_division=0)
        positive_recalls.append(float(report[positive_label]["recall"]))
        positive_precisions.append(float(report[positive_label]["precision"]))
        macro_f1s.append(float(report["macro avg"]["f1-score"]))
        accuracies.append(float(accuracy_score(test_y, predictions)))
    metrics = {
        "fold_count": int(fold_count),
        "positive_recall_mean": _mean(positive_recalls),
        "positive_recall_std": _std(positive_recalls),
        "positive_precision_mean": _mean(positive_precisions),
        "positive_precision_std": _std(positive_precisions),
        "macro_f1_mean": _mean(macro_f1s),
        "macro_f1_std": _std(macro_f1s),
        "accuracy_mean": _mean(accuracies),
        "accuracy_std": _std(accuracies),
    }
    return metrics


def _calibration_gate(
    label_counts: dict[str, int],
    *,
    positive_label: str,
    label_order: list[str],
    calibrate_requested: bool,
) -> dict[str, object]:
    positive_count = int(label_counts.get(positive_label, 0))
    negative_count = sum(count for label, count in label_counts.items() if label != positive_label)
    total = positive_count + negative_count
    base = {
        "min_required_labels": MIN_CALIBRATION_LABELS,
        "min_required_positive": MIN_CALIBRATION_POSITIVE,
        "min_required_negative": MIN_CALIBRATION_NEGATIVE,
        "actual_labels": total,
        "actual_positive": positive_count,
        "actual_negative": negative_count,
    }
    if not calibrate_requested:
        return {**base, "status": "skipped", "reason": "calibration_not_requested"}
    if len(label_order) != 2:
        return {**base, "status": "skipped", "reason": "binary_calibration_required"}
    if total < MIN_CALIBRATION_LABELS:
        return {**base, "status": "skipped", "reason": "insufficient_labels"}
    if positive_count < MIN_CALIBRATION_POSITIVE:
        return {**base, "status": "skipped", "reason": "insufficient_positive_labels"}
    if negative_count < MIN_CALIBRATION_NEGATIVE:
        return {**base, "status": "skipped", "reason": "insufficient_negative_labels"}
    return {**base, "status": "ready", "reason": None}


def _production_calibration_report(
    validation_labels: list[str] | np.ndarray,
    predictions: list[str] | np.ndarray,
    positive_probabilities: np.ndarray,
    *,
    label_counts: dict[str, int],
    label_order: list[str],
    positive_label: str,
    calibration_gate: dict[str, object],
    calibration_method: str | None,
) -> dict[str, object]:
    validation = _validation_metrics(
        validation_labels,
        predictions,
        positive_probabilities,
        positive_label=positive_label,
    )
    calibrated = calibration_gate.get("status") == "ready" and calibration_method is not None
    status = "calibrated" if calibrated else "uncalibrated"
    return {
        "status": status,
        "method": calibration_method if calibrated else None,
        "reason": None if calibrated else calibration_gate.get("reason"),
        "score_semantics": "positive_label_probability",
        "label_order": list(label_order),
        "positive_label": positive_label,
        "trained_label_counts": {label: int(label_counts.get(label, 0)) for label in label_order},
        "gate": dict(calibration_gate),
        "validation": validation,
        "thresholds": _calibration_thresholds(
            validation_labels,
            positive_probabilities,
            positive_label=positive_label,
        ),
        "split": "stratified_train_validation_calibration" if calibrated else "stratified_train_validation",
    }


def _validation_metrics(
    labels: list[str] | np.ndarray,
    predictions: list[str] | np.ndarray,
    positive_probabilities: np.ndarray,
    *,
    positive_label: str,
) -> dict[str, object]:
    from sklearn.metrics import average_precision_score, brier_score_loss, f1_score, roc_auc_score

    label_list = [str(label) for label in labels]
    prediction_list = [str(label) for label in predictions]
    y_true = np.asarray([1 if label == positive_label else 0 for label in label_list], dtype=np.int32)
    y_pred = np.asarray([1 if label == positive_label else 0 for label in prediction_list], dtype=np.int32)
    scores = np.asarray(positive_probabilities, dtype=np.float64)
    positive_count = int(np.count_nonzero(y_true))
    negative_count = int(y_true.shape[0] - positive_count)
    metrics = {
        "roc_auc": _safe_metric(lambda: float(roc_auc_score(y_true, scores))),
        "average_precision": _safe_metric(lambda: float(average_precision_score(y_true, scores))),
        "f1_at_0_5": _safe_metric(lambda: float(f1_score(y_true, y_pred, zero_division=0))),
        "brier": _safe_metric(lambda: float(brier_score_loss(y_true, scores))),
        "ece10": expected_calibration_error(scores, y_true, bins=10),
        "sample_count": int(y_true.shape[0]),
        "positive_count": positive_count,
        "negative_count": negative_count,
    }
    return metrics


def _calibration_thresholds(
    labels: list[str] | np.ndarray,
    positive_probabilities: np.ndarray,
    *,
    positive_label: str,
) -> dict[str, float | None]:
    from sklearn.metrics import precision_recall_curve

    y_true = np.asarray([1 if str(label) == positive_label else 0 for label in labels], dtype=np.int32)
    scores = np.asarray(positive_probabilities, dtype=np.float64)
    if y_true.shape[0] == 0 or np.count_nonzero(y_true) == 0:
        return {"default": 0.5, "precision_80": None, "recall_80": None}
    precision, recall, thresholds = precision_recall_curve(y_true, scores)
    threshold_rows = [
        (float(threshold), float(precision[index]), float(recall[index]))
        for index, threshold in enumerate(thresholds)
    ]
    precision_candidates = [row for row in threshold_rows if row[1] >= 0.8]
    recall_candidates = [row for row in threshold_rows if row[2] >= 0.8]
    precision_80 = max(precision_candidates, key=lambda row: (row[2], -row[0]))[0] if precision_candidates else None
    recall_80 = max(recall_candidates, key=lambda row: (row[1], -row[0]))[0] if recall_candidates else None
    return {
        "default": 0.5,
        "precision_80": precision_80,
        "recall_80": recall_80,
    }


def expected_calibration_error(probabilities: np.ndarray, labels: np.ndarray, *, bins: int = 10) -> float | None:
    scores = np.asarray(probabilities, dtype=np.float64)
    y_true = np.asarray(labels, dtype=np.float64)
    if scores.shape[0] == 0 or y_true.shape[0] != scores.shape[0]:
        return None
    total = float(scores.shape[0])
    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        if index == bins - 1:
            mask = (scores >= lower) & (scores <= upper)
        else:
            mask = (scores >= lower) & (scores < upper)
        count = int(np.count_nonzero(mask))
        if count == 0:
            continue
        confidence = float(np.mean(scores[mask]))
        accuracy = float(np.mean(y_true[mask]))
        error += (count / total) * abs(accuracy - confidence)
    return float(error)


def _safe_metric(callback) -> float | None:
    try:
        value = callback()
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _safe_ratio(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _mean(values: list[float]) -> float:
    return float(np.mean(np.asarray(values, dtype=np.float32))) if values else 0.0


def _std(values: list[float]) -> float:
    return float(np.std(np.asarray(values, dtype=np.float32))) if values else 0.0
