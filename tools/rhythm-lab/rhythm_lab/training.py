from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from uuid import uuid4

import numpy as np

from .artifact_io import artifact_sha256
from .features import (
    FEATURE_SETS,
    build_labeled_feature_matrix,
)
from .lab_db import RhythmLabDatabase
from .source_db import SourceDatabase, SourceDatabaseError


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
    label_order: list[str],
    positive_label: str,
    artifact_prefix: str,
    classifier_key: str,
    random_state: int = 42,
    calibrate: bool = False,
    source_catalog_uuid: str | None = None,
    skipped_rows: int = 0,
) -> TrainResult:
    from joblib import dump
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split

    matrix = np.asarray(matrix, dtype=np.float32)
    labels = [str(label) for label in labels]
    ordered_labels = [str(label) for label in label_order]
    positive_label = str(positive_label)
    _validate_training_data(matrix, labels, label_order=ordered_labels)
    clean_source_catalog_uuid = (
        str(source_catalog_uuid).strip() if source_catalog_uuid is not None else None
    )
    if source_catalog_uuid is not None and not clean_source_catalog_uuid:
        raise ValueError("source_catalog_uuid must be non-empty when provided")
    clean_skipped_rows = int(skipped_rows)
    if clean_skipped_rows < 0:
        raise ValueError("skipped_rows must be non-negative")
    feature_group_weights = _feature_group_weights(feature_names)

    label_counts = {label: labels.count(label) for label in ordered_labels}
    calibration_gate = _calibration_gate(
        label_counts,
        positive_label=positive_label,
        label_order=ordered_labels,
        calibrate_requested=calibrate,
    )
    if calibrate and calibration_gate["status"] != "ready":
        raise ValueError(
            "Calibration requested but usable training rows do not satisfy "
            f"the calibration gate: {calibration_gate['reason']} "
            f"(total={calibration_gate['actual_labels']}, "
            f"positive={calibration_gate['actual_positive']}, "
            f"negative={calibration_gate['actual_negative']})"
        )
    train_x, test_x, train_y, test_y = train_test_split(
        matrix,
        labels,
        test_size=_test_size(len(labels)),
        random_state=random_state,
        stratify=labels,
    )
    if calibration_gate["status"] == "ready":
        cv_folds = min(3, *(label_counts[label] for label in ordered_labels))
        evaluation_model = CalibratedClassifierCV(
            estimator=_make_model(
                random_state,
                feature_names=feature_names,
            ),
            method="sigmoid",
            cv=max(2, int(cv_folds)),
        )
        calibration_method = "sigmoid"
    else:
        evaluation_model = _make_model(
            random_state,
            feature_names=feature_names,
        )
        calibration_method = None
    evaluation_model.fit(train_x, train_y)
    predictions = evaluation_model.predict(test_x)
    positive_probabilities = _positive_probabilities(
        evaluation_model,
        test_x,
        positive_label=positive_label,
    )
    report = classification_report(test_y, predictions, labels=ordered_labels, output_dict=True, zero_division=0)
    confusion = confusion_matrix(test_y, predictions, labels=ordered_labels).tolist()

    artifact_root = Path(artifact_dir)
    artifact_root.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(timezone.utc)
    stamp = created_at.strftime("%Y%m%dT%H%M%S%fZ") + uuid4().hex[:8]
    artifact_path = artifact_root / f"{artifact_prefix}-{feature_set}-{stamp}.joblib"
    metrics_path = artifact_root / f"{artifact_prefix}-{feature_set}-{stamp}.metrics.json"
    payload = {
        "classifier_key": classifier_key,
        "model": None,
        "feature_set": feature_set,
        "feature_names": list(feature_names),
        "label_order": ordered_labels,
        "positive_label": positive_label,
        "feature_count": int(matrix.shape[1]),
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
    }
    positive_discovery = _positive_discovery_metrics(test_y, positive_probabilities, positive_label=positive_label)
    cross_validation = _cross_validation_metrics(
        matrix,
        labels,
        label_order=ordered_labels,
        positive_label=positive_label,
        random_state=random_state,
        feature_names=feature_names,
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
    if calibration_gate["status"] == "ready":
        production_model = CalibratedClassifierCV(
            estimator=_make_model(
                random_state,
                feature_names=feature_names,
            ),
            method="sigmoid",
            cv=max(2, int(cv_folds)),
        )
    else:
        production_model = _make_model(
            random_state,
            feature_names=feature_names,
        )
    production_model.fit(matrix, labels)
    payload["model"] = production_model
    payload["production_calibration"] = production_calibration
    payload["source_catalog_uuid"] = clean_source_catalog_uuid
    payload["feature_group_weights"] = feature_group_weights
    dump(payload, artifact_path)
    artifact_hash = artifact_sha256(artifact_path.read_bytes())
    metrics = {
        "classifier_key": classifier_key,
        "feature_set": feature_set,
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "label_order": ordered_labels,
        "positive_label": positive_label,
        "feature_names": list(feature_names),
        "trained_rows": len(labels),
        "skipped_rows": clean_skipped_rows,
        "test_rows": len(test_y),
        "feature_count": int(matrix.shape[1]),
        "source_catalog_uuid": clean_source_catalog_uuid,
        "feature_group_weights": feature_group_weights,
        "artifact_filename": artifact_path.name,
        "artifact_hash": artifact_hash,
        "classification_report": report,
        "confusion_matrix": confusion,
        "positive_discovery": positive_discovery,
        "cross_validation": cross_validation,
        "production_calibration": production_calibration,
    }
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return TrainResult(
        feature_set,
        production_model,
        artifact_path,
        metrics_path,
        len(labels),
        clean_skipped_rows,
    )


def benchmark_lab_database(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    artifact_dir: str | Path,
    *,
    classifier_key: str,
    feature_sets: tuple[str, ...] = FEATURE_SETS,
    random_state: int = 42,
    calibrate: bool = False,
) -> dict[str, dict[str, object]]:
    profile = RhythmLabDatabase(labels_db_path, classifier_key=classifier_key).get_profile()
    source_catalog_uuid = SourceDatabase(source_db_path).catalog_uuid
    label_order = list(profile.training_label_keys)
    results: dict[str, dict[str, object]] = {}
    for feature_set in feature_sets:
        features = None
        try:
            features = build_labeled_feature_matrix(
                source_db_path,
                labels_db_path,
                feature_set,
                classifier_key=profile.classifier_key,
            )
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
                source_catalog_uuid=source_catalog_uuid,
                skipped_rows=len(features.skipped_identities),
            )
            results[feature_set] = {
                "status": "trained",
                "artifact_path": str(result.artifact_path),
                "metrics_path": str(result.metrics_path),
                "trained_rows": result.trained_rows,
                "skipped_rows": len(features.skipped_identities),
                "feature_count": len(features.feature_names),
            }
        except (SourceDatabaseError, ValueError) as error:
            results[feature_set] = {
                "status": "skipped",
                "error": str(error),
                "available_rows": (
                    int(features.matrix.shape[0])
                    if features is not None
                    else 0
                ),
                "skipped_rows": (
                    len(features.skipped_identities)
                    if features is not None
                    else 0
                ),
                "feature_count": (
                    len(features.feature_names)
                    if features is not None
                    else 0
                ),
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


def _make_model(random_state: int, *, feature_names: list[str]):
    from sklearn.compose import ColumnTransformer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    groups = _feature_group_indices(feature_names)
    weights = _feature_group_weights(feature_names)
    source_balance = ColumnTransformer(
        [
            (f"source_{index}_{source}", "passthrough", indices)
            for index, (source, indices) in enumerate(groups.items())
        ],
        transformer_weights={
            f"source_{index}_{source}": weights[source]
            for index, source in enumerate(groups)
        },
        remainder="drop",
        sparse_threshold=0.0,
        verbose_feature_names_out=False,
    )
    return make_pipeline(
        StandardScaler(),
        source_balance,
        LogisticRegression(class_weight="balanced", max_iter=1000, random_state=random_state),
    )


def _feature_group_indices(feature_names: list[str]) -> dict[str, list[int]]:
    groups: dict[str, list[int]] = {}
    for index, feature_name in enumerate(feature_names):
        source, separator, _ = str(feature_name).partition(":")
        if not separator or not source:
            raise ValueError(
                "Feature names must use the '<source>:<feature>' format"
            )
        groups.setdefault(source, []).append(index)
    if not groups:
        raise ValueError("At least one feature source is required")
    return groups


def _feature_group_weights(feature_names: list[str]) -> dict[str, float]:
    groups = _feature_group_indices(feature_names)
    total_features = len(feature_names)
    group_count = len(groups)
    return {
        source: math.sqrt(total_features / (group_count * len(indices)))
        for source, indices in groups.items()
    }


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
    feature_names: list[str],
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
        model = _make_model(random_state, feature_names=feature_names)
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
