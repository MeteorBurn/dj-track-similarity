from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from collections.abc import Sequence

import numpy as np

from dj_track_similarity.analysis_contracts import ContractIdentity

from .features import (
    ABLATION_FEATURE_SETS,
    build_feature_matrix,
    feature_sources,
    required_outputs_payload,
)
from .lab_db import ClassifierProfile, RhythmLabDatabase, TrackIdentity
from .source_db import SourceDatabase, SourceTrack
from .training import train_feature_set


SELECTION_METRIC = "cross_validation.macro_f1_mean"
MODEL_FAMILY = 'StandardScaler + LogisticRegression(class_weight="balanced")'
LAB_ROOT = Path(__file__).resolve().parents[1]


def run_ablation_benchmark(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    *,
    profile_keys: Sequence[str] | None = None,
    feature_sets: Sequence[str] = ABLATION_FEATURE_SETS,
    artifacts_root: str | Path | None = None,
    output_path: str | Path | None = None,
    random_state: int = 42,
    calibrate_finalists: bool = False,
) -> dict[str, object]:
    labels_path = Path(labels_db_path)
    selected_feature_sets = tuple(_normalize_feature_sets(feature_sets))
    profiles, skipped_profiles = _selected_profiles(labels_path, profile_keys)
    generated_at = datetime.now(timezone.utc)
    report: dict[str, object] = {
        "generated_at": generated_at.isoformat(),
        "source_db": str(Path(source_db_path).expanduser().resolve(strict=False)),
        "labels_db": str(labels_path.expanduser().resolve(strict=False)),
        "selection_metric": SELECTION_METRIC,
        "model_family": MODEL_FAMILY,
        "feature_sets": list(selected_feature_sets),
        "calibrate_finalists": bool(calibrate_finalists),
        "skipped_profiles": skipped_profiles,
        "profiles": [],
    }
    for profile in profiles:
        artifact_dir = _profile_artifact_dir(profile, artifacts_root)
        profile_report = benchmark_profile_ablation(
            source_db_path,
            labels_path,
            profile.classifier_key,
            artifact_dir=artifact_dir,
            feature_sets=selected_feature_sets,
            random_state=random_state,
            calibrate_finalist=calibrate_finalists,
        )
        report["profiles"].append(profile_report)

    output = Path(output_path) if output_path is not None else _default_output_path(generated_at)
    output.parent.mkdir(parents=True, exist_ok=True)
    report["output_path"] = str(output.expanduser().resolve(strict=False))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return report


def benchmark_profile_ablation(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    profile_key: str,
    *,
    artifact_dir: str | Path,
    feature_sets: Sequence[str] = ABLATION_FEATURE_SETS,
    random_state: int = 42,
    calibrate_finalist: bool = False,
) -> dict[str, object]:
    labels_db = RhythmLabDatabase(labels_db_path, classifier_key=profile_key)
    profile = labels_db.get_profile()
    label_counts = labels_db.label_counts()
    labels_by_identity = labels_db.training_labels()
    source = SourceDatabase(source_db_path)
    tracks = tuple(source.list_tracks())
    embedding_cache: dict[str, tuple[ContractIdentity, dict[int, np.ndarray]]] = {}
    result_rows: list[dict[str, object]] = []
    artifact_root = Path(artifact_dir)
    for feature_set in feature_sets:
        result_rows.append(
            _train_feature_set_row(
                source,
                labels_by_identity,
                tracks,
                embedding_cache,
                profile,
                artifact_root,
                feature_set,
                random_state=random_state,
                calibrate=False,
            )
        )
    winner = _select_winner(result_rows)
    calibrated_finalist = None
    if calibrate_finalist and winner is not None:
        calibrated_finalist = _train_feature_set_row(
            source,
            labels_by_identity,
            tracks,
            embedding_cache,
            profile,
            artifact_root,
            str(winner["feature_set"]),
            random_state=random_state,
            calibrate=True,
        )
    return {
        "classifier_key": profile.classifier_key,
        "profile_name": profile.name,
        "profile_type": profile.profile_type,
        "artifact_dir": str(artifact_root.expanduser().resolve(strict=False)),
        "artifact_prefix": profile.artifact_prefix,
        "positive_label": profile.positive_label,
        "negative_label": profile.negative_label,
        "training_label_keys": list(profile.training_label_keys),
        "label_counts": {key: int(label_counts.get(key, 0)) for key in profile.label_keys},
        "results": result_rows,
        "winner": winner,
        "calibrated_finalist": calibrated_finalist,
    }


def cli_summary(report: dict[str, object]) -> dict[str, object]:
    profiles = []
    for profile in report.get("profiles", []):
        if not isinstance(profile, dict):
            continue
        winner = profile.get("winner") if isinstance(profile.get("winner"), dict) else None
        calibrated = profile.get("calibrated_finalist")
        profiles.append(
            {
                "classifier_key": profile.get("classifier_key"),
                "profile_name": profile.get("profile_name"),
                "winner": _compact_row(winner),
                "calibrated_finalist": _compact_row(calibrated if isinstance(calibrated, dict) else None),
            }
        )
    return {
        "output_path": report.get("output_path"),
        "selection_metric": report.get("selection_metric"),
        "feature_sets": report.get("feature_sets", []),
        "profiles": profiles,
        "skipped_profiles": report.get("skipped_profiles", []),
    }


def _train_feature_set_row(
    source: SourceDatabase,
    labels_by_identity: dict[TrackIdentity, str],
    tracks: tuple[SourceTrack, ...],
    embedding_cache: dict[str, tuple[ContractIdentity, dict[int, np.ndarray]]],
    profile: ClassifierProfile,
    artifact_dir: Path,
    feature_set: str,
    *,
    random_state: int,
    calibrate: bool,
) -> dict[str, object]:
    started = time.perf_counter()
    features = None
    try:
        features = build_feature_matrix(
            source,
            feature_set,
            labels_by_identity=labels_by_identity,
            tracks=tracks,
            embedding_cache=embedding_cache,
        )
        result = train_feature_set(
            features.matrix,
            features.labels,
            feature_names=features.feature_names,
            feature_set=feature_set,
            artifact_dir=artifact_dir,
            label_order=list(profile.training_label_keys),
            positive_label=profile.positive_label,
            artifact_prefix=profile.artifact_prefix,
            classifier_key=profile.classifier_key,
            random_state=random_state,
            calibrate=calibrate,
            required_outputs=required_outputs_payload(features.required_outputs),
        )
    except ValueError as error:
        return {
            "feature_set": feature_set,
            "feature_sources": list(feature_sources(feature_set)),
            "status": "skipped",
            "error": str(error),
            "available_rows": int(features.matrix.shape[0]) if features is not None else 0,
            "skipped_rows": len(features.skipped_identities) if features is not None else 0,
            "feature_count": len(features.feature_names) if features is not None else 0,
            "calibrated": bool(calibrate),
            "elapsed_seconds": _elapsed_seconds(started),
        }
    metrics = _metrics_summary(result.metrics_path)
    return {
        "feature_set": feature_set,
        "feature_sources": list(feature_sources(feature_set)),
        "status": "trained",
        "artifact_path": str(result.artifact_path.expanduser().resolve(strict=False)),
        "metrics_path": str(result.metrics_path.expanduser().resolve(strict=False)),
        "trained_rows": result.trained_rows,
        "skipped_rows": len(features.skipped_identities) if features is not None else 0,
        "feature_count": len(features.feature_names) if features is not None else 0,
        "calibrated": bool(calibrate),
        "metrics": metrics,
        "elapsed_seconds": _elapsed_seconds(started),
    }


def _metrics_summary(metrics_path: Path) -> dict[str, object]:
    payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    report = payload.get("classification_report") if isinstance(payload.get("classification_report"), dict) else {}
    positive_label = str(payload.get("positive_label") or "")
    positive = report.get(positive_label) if isinstance(report.get(positive_label), dict) else {}
    macro = report.get("macro avg") if isinstance(report.get("macro avg"), dict) else {}
    cross_validation = payload.get("cross_validation") if isinstance(payload.get("cross_validation"), dict) else {}
    calibration = payload.get("production_calibration") if isinstance(payload.get("production_calibration"), dict) else {}
    calibration_validation = calibration.get("validation") if isinstance(calibration.get("validation"), dict) else {}
    discovery = payload.get("positive_discovery") if isinstance(payload.get("positive_discovery"), dict) else {}
    return {
        "validation": {
            "accuracy": _optional_float(report.get("accuracy")),
            "macro_f1": _optional_float(macro.get("f1-score")),
            "positive_precision": _optional_float(positive.get("precision")),
            "positive_recall": _optional_float(positive.get("recall")),
            "positive_f1": _optional_float(positive.get("f1-score")),
        },
        "cross_validation": {
            "fold_count": _optional_int(cross_validation.get("fold_count")),
            "accuracy_mean": _optional_float(cross_validation.get("accuracy_mean")),
            "accuracy_std": _optional_float(cross_validation.get("accuracy_std")),
            "macro_f1_mean": _optional_float(cross_validation.get("macro_f1_mean")),
            "macro_f1_std": _optional_float(cross_validation.get("macro_f1_std")),
            "positive_precision_mean": _optional_float(cross_validation.get("positive_precision_mean")),
            "positive_precision_std": _optional_float(cross_validation.get("positive_precision_std")),
            "positive_recall_mean": _optional_float(cross_validation.get("positive_recall_mean")),
            "positive_recall_std": _optional_float(cross_validation.get("positive_recall_std")),
        },
        "positive_discovery": {
            "thresholds": discovery.get("thresholds", []),
            "top_n": discovery.get("top_n", []),
        },
        "production_calibration": {
            "status": calibration.get("status"),
            "method": calibration.get("method"),
            "reason": calibration.get("reason"),
            "roc_auc": _optional_float(calibration_validation.get("roc_auc")),
            "average_precision": _optional_float(calibration_validation.get("average_precision")),
            "brier": _optional_float(calibration_validation.get("brier")),
            "ece10": _optional_float(calibration_validation.get("ece10")),
        },
    }


def _select_winner(rows: Sequence[dict[str, object]]) -> dict[str, object] | None:
    trained = [row for row in rows if row.get("status") == "trained"]
    if not trained:
        return None
    return max(trained, key=_winner_sort_key)


def _winner_sort_key(row: dict[str, object]) -> tuple[float, float, float, float, int, int]:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    cross_validation = metrics.get("cross_validation") if isinstance(metrics.get("cross_validation"), dict) else {}
    return (
        _sort_float(cross_validation.get("macro_f1_mean")),
        -_sort_float(cross_validation.get("macro_f1_std"), missing=999.0),
        _sort_float(cross_validation.get("positive_recall_mean")),
        _sort_float(cross_validation.get("positive_precision_mean")),
        int(row.get("trained_rows") or 0),
        -int(row.get("skipped_rows") or 0),
    )


def _selected_profiles(
    labels_path: Path,
    profile_keys: Sequence[str] | None,
) -> tuple[list[ClassifierProfile], list[dict[str, object]]]:
    labels_db = RhythmLabDatabase(labels_path)
    if profile_keys:
        return [labels_db.get_profile(key) for key in profile_keys], []
    profiles: list[ClassifierProfile] = []
    skipped: list[dict[str, object]] = []
    for profile in labels_db.list_profiles():
        scoped = RhythmLabDatabase(labels_path, classifier_key=profile.classifier_key)
        counts = scoped.label_counts()
        missing = [label for label in profile.training_label_keys if int(counts.get(label, 0)) < 2]
        if missing:
            skipped.append(
                {
                    "classifier_key": profile.classifier_key,
                    "profile_name": profile.name,
                    "reason": "insufficient_training_labels",
                    "label_counts": {key: int(counts.get(key, 0)) for key in profile.label_keys},
                }
            )
            continue
        profiles.append(profile)
    return profiles, skipped


def _profile_artifact_dir(profile: ClassifierProfile, artifacts_root: str | Path | None) -> Path:
    if artifacts_root is not None:
        return Path(artifacts_root) / profile.artifact_prefix
    return Path(profile.artifact_dir)


def _normalize_feature_sets(feature_sets: Sequence[str]) -> list[str]:
    clean: list[str] = []
    for feature_set in feature_sets:
        value = str(feature_set).strip().lower()
        feature_sources(value)
        if value not in clean:
            clean.append(value)
    if not clean:
        raise ValueError("At least one feature set is required")
    return clean


def _compact_row(row: dict[str, object] | None) -> dict[str, object] | None:
    if row is None:
        return None
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    cross_validation = metrics.get("cross_validation") if isinstance(metrics.get("cross_validation"), dict) else {}
    calibration = metrics.get("production_calibration") if isinstance(metrics.get("production_calibration"), dict) else {}
    return {
        "feature_set": row.get("feature_set"),
        "status": row.get("status"),
        "trained_rows": row.get("trained_rows"),
        "skipped_rows": row.get("skipped_rows"),
        "feature_count": row.get("feature_count"),
        "macro_f1_mean": cross_validation.get("macro_f1_mean"),
        "macro_f1_std": cross_validation.get("macro_f1_std"),
        "positive_recall_mean": cross_validation.get("positive_recall_mean"),
        "positive_precision_mean": cross_validation.get("positive_precision_mean"),
        "calibration_status": calibration.get("status"),
        "metrics_path": row.get("metrics_path"),
    }


def _default_output_path(generated_at: datetime) -> Path:
    stamp = generated_at.strftime("%Y%m%dT%H%M%SZ")
    return LAB_ROOT / "artifacts" / f"ablation-{stamp}.json"


def _optional_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sort_float(value: object, *, missing: float = -1.0) -> float:
    result = _optional_float(value)
    return result if result is not None else missing


def _elapsed_seconds(started: float) -> float:
    return round(time.perf_counter() - started, 6)
