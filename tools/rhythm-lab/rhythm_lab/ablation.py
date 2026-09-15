from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
import json
from pathlib import Path
import time
from collections.abc import Sequence

import numpy as np

from .features import (
    MERT_V2_DEFAULT_LAYER,
    available_feature_sources,
    build_feature_matrix,
    canonical_feature_set,
    default_feature_set,
    feature_sources,
    source_availability_error,
    stored_mert_v2_layers,
)
from .lab_db import ClassifierProfile, RhythmLabDatabase
from .source_db import SourceDatabase, SourceTrack
from .training import TrainingProgressCallback, train_feature_set


SELECTION_METRIC = "cross_validation.macro_f1_mean"
MODEL_FAMILY = (
    "StandardScaler + source-balanced feature blocks + "
    'LogisticRegression(class_weight="balanced")'
)
BENCHMARK_STRATEGIES = ("singles", "singles+all", "greedy", "full", "layers", "layers+all", "custom")
DEFAULT_BENCHMARK_STRATEGY = "singles+all"
LAB_ROOT = Path(__file__).resolve().parents[1]


def benchmark_plan(
    available: Sequence[str],
    strategy: str,
    feature_sets: Sequence[str] = (),
    *,
    mert_v2_layers: Sequence[int] = (),
) -> tuple[str, ...]:
    """Feature sets a strategy trains up front, given the library's available sources.

    ``available`` holds bare family tokens; ``mert_v2_layers`` lists the stored
    MERT-v2 layers. ``greedy`` returns its opening round (the singles); later
    rounds depend on metrics. ``layers`` needs MERT-v2 and trains one set per
    stored layer; ``layers+all`` adds each layer joined with every other
    available family. ``custom`` requires every set to be trainable here.
    """

    clean_strategy = _benchmark_strategy(strategy)
    sources = feature_sources(canonical_feature_set(available)) if available else ()
    layers = tuple(sorted({int(layer) for layer in mert_v2_layers}))
    if clean_strategy == "custom":
        plan = _normalize_feature_sets(feature_sets)
        for feature_set in plan:
            error = _availability_error(feature_set, sources, layers)
            if error is not None:
                raise ValueError(error)
        return tuple(plan)
    if clean_strategy in {"layers", "layers+all"}:
        if "mert_v2" not in sources or not layers:
            raise ValueError("MERT_V2 data is not stored in this library")
        layer_tokens = tuple(
            "mert_v2" if layer == MERT_V2_DEFAULT_LAYER else f"mert_v2@{layer}"
            for layer in layers
        )
        others = tuple(source for source in sources if source != "mert_v2")
        if clean_strategy == "layers" or not others:
            return layer_tokens
        return (
            *layer_tokens,
            *(canonical_feature_set((*others, token)) for token in layer_tokens),
        )
    if clean_strategy == "full":
        return tuple(
            canonical_feature_set(combo)
            for size in range(len(sources), 0, -1)
            for combo in combinations(sources, size)
        )
    singles = tuple(sources)
    if clean_strategy == "singles+all":
        everything = default_feature_set(sources)
        if everything is not None and everything not in singles:
            return (*singles, everything)
    return singles


def planned_run_count(
    available: Sequence[str],
    strategy: str,
    feature_sets: Sequence[str] = (),
    *,
    mert_v2_layers: Sequence[int] = (),
) -> int:
    """Exact run count for fixed strategies; the n(n+1)/2 upper bound for greedy."""

    plan = benchmark_plan(available, strategy, feature_sets, mert_v2_layers=mert_v2_layers)
    return _planned_runs(plan, strategy)


def run_ablation_benchmark(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    *,
    profile_keys: Sequence[str] | None = None,
    strategy: str = DEFAULT_BENCHMARK_STRATEGY,
    feature_sets: Sequence[str] = (),
    artifacts_root: str | Path | None = None,
    output_path: str | Path | None = None,
    random_state: int = 42,
    calibrate_finalists: bool = False,
    progress_callback: TrainingProgressCallback | None = None,
) -> dict[str, object]:
    labels_path = Path(labels_db_path)
    clean_strategy = _benchmark_strategy(strategy)
    source = SourceDatabase(source_db_path)
    available = available_feature_sources(source.feature_states())
    layers = stored_mert_v2_layers(source)
    plan = _run_plan(available, clean_strategy, feature_sets, layers)
    planned_runs = _planned_runs(plan, clean_strategy)
    profiles, skipped_profiles = _selected_profiles(labels_path, profile_keys)
    generated_at = datetime.now(timezone.utc)
    report: dict[str, object] = {
        "generated_at": generated_at.isoformat(),
        "source_db": str(Path(source_db_path).expanduser().resolve(strict=False)),
        "labels_db": str(labels_path.expanduser().resolve(strict=False)),
        "selection_metric": SELECTION_METRIC,
        "model_family": MODEL_FAMILY,
        "strategy": clean_strategy,
        "available_sources": list(available),
        "available_mert_v2_layers": list(layers),
        "feature_sets": list(plan),
        "planned_runs": planned_runs,
        "calibrate_finalists": bool(calibrate_finalists),
        "skipped_profiles": skipped_profiles,
        "profiles": [],
    }
    profile_steps = max(1, planned_runs * 10 + (10 if calibrate_finalists else 0))
    total_progress_steps = max(1, len(profiles) * profile_steps + 1)
    for profile_index, profile in enumerate(profiles):
        artifact_dir = _profile_artifact_dir(profile, artifacts_root)
        profile_report = benchmark_profile_ablation(
            source_db_path,
            labels_path,
            profile.classifier_key,
            artifact_dir=artifact_dir,
            strategy=clean_strategy,
            feature_sets=feature_sets,
            random_state=random_state,
            calibrate_finalist=calibrate_finalists,
            progress_callback=lambda stage, completed, total: _report_progress(
                progress_callback,
                f"{profile.name}: {stage}",
                profile_index * profile_steps
                + round(profile_steps * completed / max(1, total)),
                total_progress_steps,
            ),
        )
        report["profiles"].append(profile_report)

    output = (
        Path(output_path)
        if output_path is not None
        else _default_output_path(generated_at, profiles)
    )
    _report_progress(
        progress_callback,
        "Writing benchmark report",
        total_progress_steps - 1,
        total_progress_steps,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    report["output_path"] = str(output.expanduser().resolve(strict=False))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    _report_progress(progress_callback, "Benchmark complete", total_progress_steps, total_progress_steps)
    return report


def benchmark_profile_ablation(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    profile_key: str,
    *,
    artifact_dir: str | Path,
    strategy: str = DEFAULT_BENCHMARK_STRATEGY,
    feature_sets: Sequence[str] = (),
    random_state: int = 42,
    calibrate_finalist: bool = False,
    progress_callback: TrainingProgressCallback | None = None,
) -> dict[str, object]:
    clean_strategy = _benchmark_strategy(strategy)
    labels_db = RhythmLabDatabase(labels_db_path, classifier_key=profile_key)
    profile = labels_db.get_profile()
    label_counts = labels_db.label_counts()
    source = SourceDatabase(source_db_path)
    labels_db.sync_track_sightings(source)
    labels_by_identity = labels_db.training_labels(catalog_uuid=source.catalog_uuid)
    available = available_feature_sources(source.feature_states())
    layers = stored_mert_v2_layers(source)
    plan = _run_plan(available, clean_strategy, feature_sets, layers)
    # One shared pool for every recipe: representatives that store every
    # available family, so rows are comparable across the benchmark.
    representatives = labels_db.representative_sightings(
        source.catalog_uuid,
        labels_by_identity,
    )
    tracks = tuple(
        source.tracks_by_ids(
            representatives.values(),
            required_sources=available or None,
        ).values()
    )
    embedding_cache: dict[str, tuple[int, dict[int, np.ndarray]]] = {}
    result_rows: list[dict[str, object]] = []
    artifact_root = Path(artifact_dir)
    calibration_steps = 10 if calibrate_finalist else 0
    runs_done = 0

    def train(feature_set: str, *, planned_runs: int, calibrate: bool = False) -> dict[str, object]:
        nonlocal runs_done
        error = _availability_error(feature_set, available, layers)
        if error is not None:
            row = _unavailable_row(feature_set, error)
        else:
            row = _train_feature_set_row(
                source,
                labels_by_identity,
                tracks,
                embedding_cache,
                profile,
                artifact_root,
                feature_set,
                random_state=random_state,
                calibrate=calibrate,
                progress_callback=progress_callback,
                progress_completed=runs_done * 10,
                progress_total=max(1, planned_runs * 10 + calibration_steps),
            )
        runs_done += 1
        return row

    if clean_strategy == "greedy":
        for feature_set in plan:
            result_rows.append(train(feature_set, planned_runs=len(plan)))
        best = _select_winner(result_rows)
        while best is not None:
            best_sources = feature_sources(str(best["feature_set"]))
            candidates = [source_name for source_name in available if source_name not in best_sources]
            if not candidates:
                break
            round_rows = [
                train(
                    canonical_feature_set((*best_sources, source_name)),
                    planned_runs=runs_done + len(candidates),
                )
                for source_name in candidates
            ]
            result_rows.extend(round_rows)
            challenger = _select_winner(round_rows)
            if challenger is None or not _beats_noise(challenger, best):
                break
            best = challenger
    else:
        for feature_set in plan:
            result_rows.append(train(feature_set, planned_runs=len(plan)))
    winner = _select_winner(result_rows)
    calibrated_finalist = None
    if calibrate_finalist and winner is not None:
        calibrated_finalist = train(
            str(winner["feature_set"]),
            planned_runs=runs_done,
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
        "strategy": report.get("strategy"),
        "available_sources": report.get("available_sources", []),
        "feature_sets": report.get("feature_sets", []),
        "planned_runs": report.get("planned_runs"),
        "profiles": profiles,
        "skipped_profiles": report.get("skipped_profiles", []),
    }


def _benchmark_strategy(strategy: str) -> str:
    clean = str(strategy or "").strip().lower()
    if clean not in BENCHMARK_STRATEGIES:
        raise ValueError(f"Unsupported benchmark strategy: {strategy!r}")
    return clean


def _run_plan(
    available: Sequence[str],
    strategy: str,
    feature_sets: Sequence[str],
    mert_v2_layers: Sequence[int],
) -> tuple[str, ...]:
    # Custom keeps sets with unavailable sources so the report can mark them
    # "unavailable" instead of failing the whole benchmark.
    if strategy == "custom":
        return tuple(_normalize_feature_sets(feature_sets))
    return benchmark_plan(available, strategy, mert_v2_layers=mert_v2_layers)


def _planned_runs(plan: Sequence[str], strategy: str) -> int:
    if _benchmark_strategy(strategy) == "greedy":
        return len(plan) * (len(plan) + 1) // 2
    return len(plan)


def _availability_error(
    feature_set: str,
    available: Sequence[str],
    mert_v2_layers: Sequence[int],
) -> str | None:
    for source in feature_sources(feature_set):
        error = source_availability_error(source, available, mert_v2_layers)
        if error is not None:
            return error
    return None


def _unavailable_row(feature_set: str, error: str) -> dict[str, object]:
    return {
        "feature_set": feature_set,
        "feature_sources": list(feature_sources(feature_set)),
        "status": "unavailable",
        "error": error,
        "available_rows": 0,
        "skipped_rows": 0,
        "feature_count": 0,
        "calibrated": False,
        "elapsed_seconds": 0.0,
    }


def _beats_noise(challenger: dict[str, object], incumbent: dict[str, object]) -> bool:
    """True when the challenger's CV macro-F1 improves on the incumbent at all.

    The 2026-09-15 strategy study showed a one-sigma gate stops greedy at single
    sources (0/20 full-grid winners); any strict improvement reaches the full-grid
    winner's noise band in 20/20 cells at about a quarter of the grid cost.
    """

    incumbent_mean = _cv_metric(incumbent, "macro_f1_mean")
    challenger_mean = _cv_metric(challenger, "macro_f1_mean")
    if challenger_mean is None or incumbent_mean is None:
        return False
    return challenger_mean > incumbent_mean


def _cv_metric(row: dict[str, object], key: str) -> float | None:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    cross_validation = metrics.get("cross_validation") if isinstance(metrics.get("cross_validation"), dict) else {}
    return _optional_float(cross_validation.get(key))


def _train_feature_set_row(
    source: SourceDatabase,
    labels_by_identity: dict[str, str],
    tracks: tuple[SourceTrack, ...],
    embedding_cache: dict[str, tuple[int, dict[int, np.ndarray]]],
    profile: ClassifierProfile,
    artifact_dir: Path,
    feature_set: str,
    *,
    random_state: int,
    calibrate: bool,
    progress_callback: TrainingProgressCallback | None = None,
    progress_completed: int = 0,
    progress_total: int = 1,
) -> dict[str, object]:
    started = time.perf_counter()
    features = None
    try:
        _report_progress(
            progress_callback,
            f"Building {feature_set} feature matrix",
            progress_completed,
            progress_total,
        )
        features = build_feature_matrix(
            source,
            feature_set,
            labels_by_identity=labels_by_identity,
            tracks=tracks,
            embedding_cache=embedding_cache,
        )
        _report_progress(
            progress_callback,
            f"Training {feature_set}",
            progress_completed + 1,
            progress_total,
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
            source_catalog_uuid=source.catalog_uuid,
            skipped_rows=len(features.skipped_identities),
            progress_callback=lambda stage, completed, total: _report_progress(
                progress_callback,
                f"{feature_set}: {stage}",
                progress_completed + 1 + round(8 * completed / max(1, total)),
                progress_total,
            ),
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
    _report_progress(
        progress_callback,
        f"Saved {feature_set} model",
        progress_completed + 10,
        progress_total,
    )
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


def _report_progress(
    callback: TrainingProgressCallback | None,
    stage: str,
    completed: int,
    total: int,
) -> None:
    if callback is not None:
        callback(str(stage), max(0, int(completed)), max(1, int(total)))


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
        value = canonical_feature_set(feature_sources(feature_set))
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


def _default_output_path(
    generated_at: datetime,
    profiles: Sequence[ClassifierProfile],
) -> Path:
    stamp = generated_at.strftime("%Y-%m-%d-%H-%M-%S")
    if len(profiles) == 1:
        return Path(profiles[0].artifact_dir) / f"ablation-benchmark-{stamp}.json"
    return LAB_ROOT / "database" / "reports" / f"ablation-benchmark-{stamp}.json"


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
