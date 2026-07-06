from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

from dj_track_similarity.classifier_production import normalize_label_suggestion_mode, suggest_classifier_labels
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.logging_config import uvicorn_log_config
from dj_track_similarity.rhythm_lab_collections import RhythmLabCollections

from .ablation import ABLATION_FEATURE_SETS, cli_summary, run_ablation_benchmark
from .features import feature_sources
from .lab_db import RhythmLabDatabase
from .predictions import apply_model_to_lab, export_predictions_csv
from .training import benchmark_lab_database


LAB_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = LAB_ROOT.parents[1]
DEFAULT_SOURCE_DB = Path(r"C:\db\abstracted.sqlite")
DEFAULT_LABELS_DB = LAB_ROOT / "data" / "rhythm_lab.sqlite"
DEFAULT_CLASSIFIER_TARGET_ROOT = PROJECT_ROOT / "models" / "classifiers"


class PromotionError(ValueError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auxiliary classifier labeling and training lab.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    train_parser = subcommands.add_parser("train", help="Benchmark a classifier profile for available feature sets.")
    _add_data_options(train_parser)
    train_parser.add_argument("--profile", required=True)
    train_parser.add_argument("--artifacts", type=Path, default=None)
    train_parser.add_argument("--calibrate", action="store_true", help="Fit a calibrated classifier when label gates are satisfied.")
    train_parser.set_defaults(func=_train)

    ablation_parser = subcommands.add_parser("benchmark-ablation", help="Run per-profile feature-combination ablation benchmarks.")
    _add_data_options(ablation_parser)
    ablation_parser.add_argument("--profile", action="append", default=None, help="Classifier profile key. Repeat to benchmark multiple profiles; omit for all trainable active profiles.")
    ablation_parser.add_argument("--feature-set", action="append", default=None, help="Feature set to evaluate, such as sonara+mert or sonara+mert+maest+clap. Repeat to override the default full ablation matrix.")
    ablation_parser.add_argument("--artifacts-root", type=Path, default=None, help="Override profile artifact directories with <root>/<artifact-prefix>.")
    ablation_parser.add_argument("--output", type=Path, default=None, help="Write the combined JSON report to this path.")
    ablation_parser.add_argument("--random-state", type=int, default=42)
    ablation_parser.add_argument("--calibrate-finalists", action="store_true", help="After ranking uncalibrated combinations, retrain each winning profile combination with calibration enabled when gates allow it.")
    ablation_parser.set_defaults(func=_benchmark_ablation)

    predict_parser = subcommands.add_parser("predict", help="Apply a trained model artifact to feature-complete source tracks.")
    predict_parser.add_argument("artifact", type=Path)
    _add_data_options(predict_parser)
    predict_parser.add_argument("--profile", default=None)
    predict_parser.set_defaults(func=_predict)

    export_parser = subcommands.add_parser("export-predictions", help="Export saved classifier profile predictions to CSV.")
    export_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    export_parser.add_argument("--output", type=Path, default=None)
    export_parser.add_argument("--profile", required=True)
    export_parser.set_defaults(func=_export_predictions)

    promote_parser = subcommands.add_parser("promote", help="Copy the latest combined profile model into the main project.")
    promote_parser.add_argument("--profile", required=True)
    promote_parser.add_argument("--artifacts", type=Path, default=None)
    promote_parser.add_argument("--feature-set", default=None, help="Promote the latest artifact for this feature set. Defaults to combined.")
    promote_parser.add_argument("--target", type=Path, default=DEFAULT_CLASSIFIER_TARGET_ROOT)
    promote_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    promote_parser.add_argument("--require-calibration", action="store_true", help="Fail unless the selected artifact has a calibrated production report.")
    promote_parser.add_argument("--allow-uncalibrated", action="store_true", help="Allow experimental promotion when the artifact is not calibrated.")
    promote_parser.set_defaults(func=_promote_profile)

    calibration_parser = subcommands.add_parser("calibration-report", help="Print the latest combined artifact calibration report.")
    calibration_parser.add_argument("--profile", required=True)
    calibration_parser.add_argument("--artifacts", type=Path, default=None)
    calibration_parser.add_argument("--artifact", type=Path, default=None)
    calibration_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    calibration_parser.set_defaults(func=_calibration_report)

    suggest_parser = subcommands.add_parser("suggest-labels", help="Rank classifier label suggestions and optionally persist them to the lab queue.")
    _add_data_options(suggest_parser)
    suggest_parser.add_argument("--profile", required=True)
    suggest_parser.add_argument("--mode", default="uncertainty")
    suggest_parser.add_argument("--limit", type=int, default=25)
    suggest_parser.add_argument("--random-seed", type=int, default=123)
    suggest_parser.add_argument("--write-queue", action="store_true", help="Upsert suggestions into classifier_label_queue.")
    suggest_parser.set_defaults(func=_suggest_labels)

    queue_parser = subcommands.add_parser("queue", help="List persistent active-learning queue rows.")
    queue_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    queue_parser.add_argument("--profile", required=True)
    queue_parser.add_argument("--state", default=None)
    queue_parser.set_defaults(func=_queue_list)

    queue_export_parser = subcommands.add_parser("queue-export", help="Export persistent active-learning queue rows to CSV.")
    queue_export_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    queue_export_parser.add_argument("--profile", required=True)
    queue_export_parser.add_argument("--state", default=None)
    queue_export_parser.add_argument("--output", type=Path, required=True)
    queue_export_parser.set_defaults(func=_queue_export)

    queue_mark_parser = subcommands.add_parser("queue-mark", help="Set one queue row state explicitly.")
    queue_mark_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    queue_mark_parser.add_argument("--profile", required=True)
    queue_mark_parser.add_argument("--track-id", type=int, required=True)
    queue_mark_parser.add_argument("--mode", default="uncertainty")
    queue_mark_parser.add_argument("--state", required=True)
    queue_mark_parser.set_defaults(func=_queue_mark)

    queue_clear_parser = subcommands.add_parser("queue-clear", help="Delete queue rows in one state for one profile.")
    queue_clear_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    queue_clear_parser.add_argument("--profile", required=True)
    queue_clear_parser.add_argument("--state", required=True)
    queue_clear_parser.set_defaults(func=_queue_clear)

    collection_save_parser = subcommands.add_parser("collection-save", help="Create, append, or replace a Rhythm Lab review collection.")
    collection_save_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    collection_save_parser.add_argument("--name", required=True)
    collection_save_parser.add_argument("--source", default="agent")
    collection_save_parser.add_argument("--note", default=None)
    collection_save_parser.add_argument("--track-id", type=int, action="append", default=[])
    collection_save_parser.add_argument("--track-ids", type=Path, default=None, help="Text file with one track id per line.")
    collection_save_parser.add_argument("--replace", action="store_true", help="Replace collection contents instead of appending.")
    collection_save_parser.set_defaults(func=_collection_save)

    collection_list_parser = subcommands.add_parser("collection-list", help="List Rhythm Lab review collections.")
    collection_list_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    collection_list_parser.set_defaults(func=_collection_list)

    delete_parser = subcommands.add_parser("delete-profile", help="Permanently delete one classifier profile and its lab data.")
    delete_target = delete_parser.add_mutually_exclusive_group(required=True)
    delete_target.add_argument("--profile", default=None, help="Delete by classifier_key.")
    delete_target.add_argument("--name", default=None, help="Delete by unique profile name.")
    delete_parser.add_argument("--confirm", required=True, help="Must exactly match the profile key or name being deleted.")
    delete_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    delete_parser.set_defaults(func=_delete_profile)

    serve_parser = subcommands.add_parser("serve", help="Start the minimal labeling web app.")
    serve_parser.add_argument("--source", type=Path, default=None)
    serve_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8777)
    serve_parser.set_defaults(func=_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


def _add_data_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)


def _train(args: argparse.Namespace) -> None:
    profile = RhythmLabDatabase(args.labels, classifier_key=args.profile).get_profile()
    artifact_dir = args.artifacts or Path(profile.artifact_dir)
    results = benchmark_lab_database(args.source, args.labels, artifact_dir, classifier_key=args.profile, calibrate=args.calibrate)
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


def _benchmark_ablation(args: argparse.Namespace) -> None:
    report = run_ablation_benchmark(
        args.source,
        args.labels,
        profile_keys=args.profile,
        feature_sets=tuple(args.feature_set or ABLATION_FEATURE_SETS),
        artifacts_root=args.artifacts_root,
        output_path=args.output,
        random_state=args.random_state,
        calibrate_finalists=args.calibrate_finalists,
    )
    print(json.dumps(cli_summary(report), ensure_ascii=False, indent=2, sort_keys=True))


def _predict(args: argparse.Namespace) -> None:
    result = apply_model_to_lab(args.source, args.labels, args.artifact, classifier_key=args.profile)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def _export_predictions(args: argparse.Namespace) -> None:
    profile = RhythmLabDatabase(args.labels, classifier_key=args.profile).get_profile()
    output = args.output or Path(profile.artifact_dir) / "predictions.csv"
    path = export_predictions_csv(args.labels, output, classifier_key=args.profile)
    print(f"output={path}")


def promote_profile_model(
    labels_path: str | Path,
    profile_key: str,
    *,
    artifacts: str | Path | None = None,
    artifact_path: str | Path | None = None,
    feature_set: str | None = None,
    target_root: str | Path = DEFAULT_CLASSIFIER_TARGET_ROOT,
    require_calibration: bool = False,
    allow_uncalibrated: bool = False,
) -> dict[str, object]:
    labels_db = RhythmLabDatabase(labels_path, classifier_key=profile_key)
    profile = labels_db.get_profile()
    if artifact_path is not None:
        artifact = Path(artifact_path)
    else:
        artifact_dir = Path(artifacts) if artifacts is not None else Path(profile.artifact_dir)
        calibration_filter = "calibrated" if require_calibration else "uncalibrated"
        artifact = _latest_feature_artifact(
            artifact_dir,
            profile.artifact_prefix,
            feature_set or "combined",
            calibration=calibration_filter,
        )
    payload = _load_artifact_payload(artifact)
    classifier_key = str(payload.get("classifier_key") or "")
    if classifier_key != profile.classifier_key:
        raise PromotionError(
            f"Expected artifact for profile {profile.classifier_key!r}, got classifier_key={classifier_key!r}"
        )
    artifact_feature_set = str(payload.get("feature_set") or "")
    if feature_set is not None and artifact_feature_set != feature_set:
        raise PromotionError(f"Expected a {feature_set!r} artifact, got feature_set={artifact_feature_set!r}")
    required_inputs = list(feature_sources(artifact_feature_set))
    production_calibration = _artifact_calibration_payload(payload)
    if require_calibration and production_calibration.get("status") != "calibrated":
        reason = production_calibration.get("reason") or production_calibration.get("status") or "unknown"
        raise PromotionError(f"Artifact calibration is required but not available: {reason}")

    target = Path(target_root) / profile.artifact_prefix
    target.mkdir(parents=True, exist_ok=True)
    model_path = target / "model.joblib"
    metadata_path = target / "model.json"
    shutil.copyfile(artifact, model_path)
    artifact_hash = _sha256_file(model_path)
    promoted_at = datetime.now(timezone.utc)
    promoted_stamp = promoted_at.strftime("%Y%m%dT%H%M%SZ")
    model_id = f"{profile.classifier_key}_{promoted_stamp}_{artifact_hash[:8]}"
    metadata = {
        "classifier_key": profile.classifier_key,
        "manifest_version": 1,
        "model_id": model_id,
        "artifact_hash": f"sha256:{artifact_hash}",
        "profile_name": profile.name,
        "profile_type": profile.profile_type,
        "feature_set": artifact_feature_set,
        "feature_count": len(payload.get("feature_names", [])),
        "label_order": payload.get("label_order", list(profile.training_label_keys)),
        "positive_label": payload.get("positive_label", profile.positive_label),
        "negative_label": profile.negative_label,
        "source_artifact": str(artifact),
        "promoted_at": promoted_at.isoformat(),
        "production": {
            "score_semantics": "positive_label_probability",
            "required_inputs": required_inputs,
            "calibration": _manifest_calibration_payload(production_calibration),
            "limitations": _manifest_limitations(production_calibration),
        },
        "trained_label_counts": labels_db.label_counts(),
    }
    if production_calibration.get("status") == "uncalibrated" and allow_uncalibrated:
        metadata["production"]["calibration"]["allowed_uncalibrated"] = True
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "model_path": model_path,
        "metadata_path": metadata_path,
        "source_artifact": artifact,
        "metadata": metadata,
    }


def _promote_profile(args: argparse.Namespace) -> None:
    try:
        result = promote_profile_model(
            args.labels,
            args.profile,
            artifacts=args.artifacts,
            feature_set=args.feature_set,
            target_root=args.target,
            require_calibration=args.require_calibration,
            allow_uncalibrated=args.allow_uncalibrated,
        )
    except PromotionError as error:
        raise SystemExit(str(error)) from error
    print(f"model={result['model_path']} metadata={result['metadata_path']} source={result['source_artifact']}")


def _calibration_report(args: argparse.Namespace) -> None:
    profile = RhythmLabDatabase(args.labels, classifier_key=args.profile).get_profile()
    artifact = (
        Path(args.artifact)
        if args.artifact is not None
        else _latest_feature_artifact(args.artifacts or profile.artifact_dir, profile.artifact_prefix, "combined", calibration="any")
    )
    payload = _load_artifact_payload(artifact)
    report = _artifact_calibration_payload(payload)
    print(json.dumps({"profile": profile.classifier_key, "artifact": str(artifact), "calibration": report}, ensure_ascii=False, indent=2, sort_keys=True))


def _suggest_labels(args: argparse.Namespace) -> None:
    mode = normalize_label_suggestion_mode(args.mode)
    labels_db = RhythmLabDatabase(args.labels, classifier_key=args.profile)
    report = suggest_classifier_labels(
        LibraryDatabase(args.source),
        args.profile,
        mode=mode,
        limit=max(1, int(args.limit)),
        random_seed=int(args.random_seed),
    )
    if args.write_queue:
        written = labels_db.upsert_label_queue_items(
            mode=mode,
            items=_queue_items_from_suggestions(report.get("suggestions", [])),
        )
        report["queue_written"] = written
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def _queue_list(args: argparse.Namespace) -> None:
    rows = RhythmLabDatabase(args.labels, classifier_key=args.profile).label_queue_items(state=args.state)
    print(json.dumps({"profile": args.profile, "state": args.state, "count": len(rows), "items": rows}, ensure_ascii=False, indent=2, sort_keys=True))


def _queue_export(args: argparse.Namespace) -> None:
    rows = RhythmLabDatabase(args.labels, classifier_key=args.profile).label_queue_items(state=args.state)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write_queue_csv(args.output, rows)
    print(f"output={args.output} rows={len(rows)}")


def _queue_mark(args: argparse.Namespace) -> None:
    row = RhythmLabDatabase(args.labels, classifier_key=args.profile).mark_queue_item(
        args.track_id,
        mode=args.mode,
        state=args.state,
    )
    print(json.dumps(row, ensure_ascii=False, sort_keys=True))


def _queue_clear(args: argparse.Namespace) -> None:
    deleted = RhythmLabDatabase(args.labels, classifier_key=args.profile).clear_label_queue(state=args.state)
    print(f"profile={args.profile} state={args.state} deleted={deleted}")


def _collection_save(args: argparse.Namespace) -> None:
    track_ids = _collection_track_ids_from_args(args)
    mode = "replace" if args.replace else "append"
    collection = RhythmLabCollections(args.labels).save_collection(
        args.name,
        track_ids,
        source=args.source,
        note=args.note,
        mode=mode,
    )
    print(f"collection={collection.id} name={collection.name} tracks={collection.track_count} mode={mode}")


def _collection_list(args: argparse.Namespace) -> None:
    collections = RhythmLabCollections(args.labels).list_collections()
    for collection in collections:
        print(f"{collection.id}\t{collection.name}\ttracks={collection.track_count}\tsource={collection.source}")


def _delete_profile(args: argparse.Namespace) -> None:
    target = args.profile if args.profile is not None else args.name
    if args.confirm != target:
        raise SystemExit("Refusing to delete profile: --confirm must exactly match --profile or --name")
    labels_db = RhythmLabDatabase(args.labels)
    try:
        profile = labels_db.delete_profile(classifier_key=args.profile, name=args.name)
    except (KeyError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(f"deleted={profile.classifier_key} name={profile.name}")


def _collection_track_ids_from_args(args: argparse.Namespace) -> list[int]:
    values: list[int] = []
    if args.track_ids is not None:
        for line in args.track_ids.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            values.append(int(text))
    values.extend(args.track_id or [])
    if not values:
        raise SystemExit("At least one --track-id or --track-ids entry is required")
    return values


def _latest_combined_artifact(artifact_dir: str | Path, artifact_prefix: str) -> Path:
    return _latest_feature_artifact(artifact_dir, artifact_prefix, "combined")


def _latest_feature_artifact(
    artifact_dir: str | Path,
    artifact_prefix: str,
    feature_set: str,
    *,
    calibration: str = "uncalibrated",
) -> Path:
    feature_sources(feature_set)
    artifacts = sorted(Path(artifact_dir).glob(f"{artifact_prefix}-combined-*.joblib"))
    if feature_set != "combined":
        artifacts = sorted(Path(artifact_dir).glob(f"{artifact_prefix}-{feature_set}-*.joblib"))
    artifacts.reverse()
    for artifact in artifacts:
        if _artifact_matches_calibration_filter(artifact, calibration):
            return artifact
    detail = "" if calibration == "any" else f" {calibration}"
    suffix = "; calibration is required" if calibration == "calibrated" else ""
    raise PromotionError(f"No{detail} {feature_set} model artifacts found in {artifact_dir}{suffix}")


def _load_artifact_payload(path: Path) -> dict[str, object]:
    import joblib

    try:
        payload = joblib.load(path)
    except Exception as error:
        raise PromotionError(f"Unsupported artifact payload: {path}") from error
    if not isinstance(payload, dict):
        raise PromotionError(f"Unsupported artifact payload: {path}")
    return payload


def _artifact_matches_calibration_filter(path: Path, calibration: str) -> bool:
    if calibration == "any":
        return True
    payload = _load_artifact_payload(path)
    status = str(_artifact_calibration_payload(payload).get("status") or "uncalibrated")
    if calibration == "calibrated":
        return status == "calibrated"
    if calibration == "uncalibrated":
        return status != "calibrated"
    raise PromotionError(f"Unsupported calibration filter: {calibration}")


def _artifact_calibration_payload(payload: dict[str, object]) -> dict[str, object]:
    calibration = payload.get("production_calibration")
    if isinstance(calibration, dict):
        return dict(calibration)
    return {
        "status": "uncalibrated",
        "method": None,
        "reason": "missing_calibration_report",
        "validation": {},
        "thresholds": {"default": 0.5, "precision_80": None, "recall_80": None},
        "gate": {},
    }


def _manifest_calibration_payload(calibration: dict[str, object]) -> dict[str, object]:
    validation = calibration.get("validation") if isinstance(calibration.get("validation"), dict) else {}
    gate = calibration.get("gate") if isinstance(calibration.get("gate"), dict) else {}
    status = str(calibration.get("status") or "uncalibrated")
    payload: dict[str, object] = {
        "status": "calibrated" if status == "calibrated" else "uncalibrated",
        "method": calibration.get("method") if status == "calibrated" else None,
        "reason": None if status == "calibrated" else calibration.get("reason"),
        "brier": validation.get("brier"),
        "ece10": validation.get("ece10"),
        "validation_roc_auc": validation.get("roc_auc"),
        "validation_average_precision": validation.get("average_precision"),
        "validation_f1": validation.get("f1_at_0_5"),
        "label_count": gate.get("actual_labels"),
        "positive_count": gate.get("actual_positive"),
        "negative_count": gate.get("actual_negative"),
        "split": calibration.get("split"),
        "thresholds": calibration.get("thresholds") if isinstance(calibration.get("thresholds"), dict) else {},
    }
    if status != "calibrated":
        for key in ("min_required_labels", "min_required_positive", "min_required_negative", "actual_labels", "actual_positive", "actual_negative"):
            if key in gate:
                payload[key] = gate[key]
    return payload


def _manifest_limitations(calibration: dict[str, object]) -> list[str]:
    status = str(calibration.get("status") or "uncalibrated")
    if status == "calibrated":
        score_limitation = "Scores are calibrated positive-label probabilities for the promoted model."
    else:
        score_limitation = "Scores are the promoted model's positive-label probability, not a calibrated probability."
    return [
        score_limitation,
        "Promotion copies a local artifact and manifest; it does not benchmark the classifier.",
    ]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _queue_items_from_suggestions(suggestions: object) -> list[dict[str, object]]:
    if not isinstance(suggestions, list):
        return []
    items: list[dict[str, object]] = []
    total = len(suggestions)
    for suggestion in suggestions:
        if not isinstance(suggestion, dict):
            continue
        track = suggestion.get("track")
        if not isinstance(track, dict):
            continue
        rank = int(suggestion.get("rank") or len(items) + 1)
        items.append(
            {
                "source_track_id": track.get("id"),
                "score": suggestion.get("score"),
                "priority": float(total - rank + 1),
                "reason": {
                    "rank": rank,
                    "reason": suggestion.get("reason"),
                    "label_status": suggestion.get("label_status"),
                    "feedback_count": suggestion.get("feedback_count"),
                },
            }
        )
    return items


def _write_queue_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "id",
        "classifier_key",
        "source_track_id",
        "mode",
        "score",
        "priority",
        "state",
        "reason_json",
        "created_at",
        "updated_at",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "id": row["id"],
                    "classifier_key": row["classifier_key"],
                    "source_track_id": row["source_track_id"],
                    "mode": row["mode"],
                    "score": row["score"],
                    "priority": row["priority"],
                    "state": row["state"],
                    "reason_json": json.dumps(row.get("reason", {}), ensure_ascii=False, sort_keys=True),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                }
            )


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .web_app import create_app

    uvicorn.run(
        create_app(args.source, labels_db_path=args.labels),
        host=args.host,
        port=args.port,
        log_config=uvicorn_log_config(),
    )
