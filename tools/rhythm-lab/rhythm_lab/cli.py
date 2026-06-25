from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from .lab_db import BREAK_ENERGY_CLASSIFIER_KEY, RhythmLabDatabase
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
    train_parser.add_argument("--profile", default=BREAK_ENERGY_CLASSIFIER_KEY)
    train_parser.add_argument("--artifacts", type=Path, default=None)
    train_parser.set_defaults(func=_train)

    predict_parser = subcommands.add_parser("predict", help="Apply a trained model artifact to feature-complete source tracks.")
    predict_parser.add_argument("artifact", type=Path)
    _add_data_options(predict_parser)
    predict_parser.add_argument("--profile", default=None)
    predict_parser.set_defaults(func=_predict)

    export_parser = subcommands.add_parser("export-predictions", help="Export saved classifier profile predictions to CSV.")
    export_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    export_parser.add_argument("--output", type=Path, default=None)
    export_parser.add_argument("--profile", default=BREAK_ENERGY_CLASSIFIER_KEY)
    export_parser.set_defaults(func=_export_predictions)

    promote_parser = subcommands.add_parser("promote", help="Copy the latest combined profile model into the main project.")
    promote_parser.add_argument("--profile", default=BREAK_ENERGY_CLASSIFIER_KEY)
    promote_parser.add_argument("--artifacts", type=Path, default=None)
    promote_parser.add_argument("--target", type=Path, default=DEFAULT_CLASSIFIER_TARGET_ROOT)
    promote_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    promote_parser.set_defaults(func=_promote_profile)

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
    results = benchmark_lab_database(args.source, args.labels, artifact_dir, classifier_key=args.profile)
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


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
    target_root: str | Path = DEFAULT_CLASSIFIER_TARGET_ROOT,
) -> dict[str, object]:
    labels_db = RhythmLabDatabase(labels_path, classifier_key=profile_key)
    profile = labels_db.get_profile()
    if artifact_path is not None:
        artifact = Path(artifact_path)
    else:
        artifact_dir = Path(artifacts) if artifacts is not None else Path(profile.artifact_dir)
        artifact = _latest_combined_artifact(artifact_dir, profile.artifact_prefix)
    payload = _load_artifact_payload(artifact)
    classifier_key = str(payload.get("classifier_key") or "")
    if classifier_key != profile.classifier_key:
        raise PromotionError(
            f"Expected artifact for profile {profile.classifier_key!r}, got classifier_key={classifier_key!r}"
        )
    if str(payload.get("feature_set")) != "combined":
        raise PromotionError(f"Expected a combined artifact, got feature_set={payload.get('feature_set')!r}")

    target = Path(target_root) / profile.artifact_prefix
    target.mkdir(parents=True, exist_ok=True)
    model_path = target / "model.joblib"
    metadata_path = target / "model.json"
    shutil.copy2(artifact, model_path)
    metadata = {
        "classifier_key": profile.classifier_key,
        "manifest_version": 1,
        "profile_name": profile.name,
        "profile_type": profile.profile_type,
        "feature_set": payload.get("feature_set"),
        "feature_count": len(payload.get("feature_names", [])),
        "label_order": payload.get("label_order", list(profile.training_label_keys)),
        "positive_label": payload.get("positive_label", profile.positive_label),
        "negative_label": profile.negative_label,
        "source_artifact": str(artifact),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "production": {
            "score_semantics": "positive_label_probability",
            "required_inputs": ["sonara", "mert", "maest"],
            "calibration": {
                "status": "uncalibrated",
                "method": None,
                "report": None,
            },
            "limitations": [
                "Scores are the promoted model's positive-label probability, not a calibrated probability.",
                "Promotion copies a local artifact and manifest; it does not benchmark the classifier.",
            ],
        },
        "trained_label_counts": labels_db.label_counts(),
    }
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
            target_root=args.target,
        )
    except PromotionError as error:
        raise SystemExit(str(error)) from error
    print(f"model={result['model_path']} metadata={result['metadata_path']} source={result['source_artifact']}")


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


def _latest_combined_artifact(artifact_dir: str | Path, artifact_prefix: str) -> Path:
    artifacts = sorted(Path(artifact_dir).glob(f"{artifact_prefix}-combined-*.joblib"))
    if not artifacts:
        raise PromotionError(f"No combined model artifacts found in {artifact_dir}")
    return artifacts[-1]


def _load_artifact_payload(path: Path) -> dict[str, object]:
    import joblib

    try:
        payload = joblib.load(path)
    except Exception as error:
        raise PromotionError(f"Unsupported artifact payload: {path}") from error
    if not isinstance(payload, dict):
        raise PromotionError(f"Unsupported artifact payload: {path}")
    return payload


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .web_app import create_app

    uvicorn.run(create_app(args.source, labels_db_path=args.labels), host=args.host, port=args.port)
