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
DEFAULT_BREAK_ENERGY_TARGET = PROJECT_ROOT / "models" / "classifiers" / "break-energy"


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

    promote_parser = subcommands.add_parser(
        "promote-break-energy",
        help="Copy the latest combined Break Energy model into the main project's classifier slot.",
    )
    promote_parser.add_argument("--artifacts", type=Path, default=None)
    promote_parser.add_argument("--target", type=Path, default=DEFAULT_BREAK_ENERGY_TARGET)
    promote_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    promote_parser.set_defaults(func=_promote_break_energy)

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


def _promote_break_energy(args: argparse.Namespace) -> None:
    labels_db = RhythmLabDatabase(args.labels, classifier_key=BREAK_ENERGY_CLASSIFIER_KEY)
    profile = labels_db.get_profile()
    artifact_dir = args.artifacts or Path(profile.artifact_dir)
    artifact = _latest_combined_artifact(artifact_dir, profile.artifact_prefix)
    payload = _load_artifact_payload(artifact)
    classifier_key = str(payload.get("classifier_key") or "")
    if classifier_key != profile.classifier_key:
        raise SystemExit(
            f"Expected artifact for profile {profile.classifier_key!r}, got classifier_key={classifier_key!r}"
        )
    if str(payload.get("feature_set")) != "combined":
        raise SystemExit(f"Expected a combined artifact, got feature_set={payload.get('feature_set')!r}")

    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)
    model_path = target / "model.joblib"
    metadata_path = target / "model.json"
    shutil.copy2(artifact, model_path)
    metadata = {
        "classifier_key": profile.classifier_key,
        "profile_name": profile.name,
        "profile_type": profile.profile_type,
        "feature_set": payload.get("feature_set"),
        "feature_count": len(payload.get("feature_names", [])),
        "label_order": payload.get("label_order", list(profile.training_label_keys)),
        "positive_label": payload.get("positive_label", profile.positive_label),
        "negative_label": profile.negative_label,
        "source_artifact": str(artifact),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "trained_label_counts": labels_db.label_counts(),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"model={model_path} metadata={metadata_path} source={artifact}")


def _latest_combined_artifact(artifact_dir: str | Path, artifact_prefix: str) -> Path:
    artifacts = sorted(Path(artifact_dir).glob(f"{artifact_prefix}-combined-*.joblib"))
    if not artifacts:
        raise SystemExit(f"No combined model artifacts found in {artifact_dir}")
    return artifacts[-1]


def _load_artifact_payload(path: Path) -> dict[str, object]:
    import joblib

    payload = joblib.load(path)
    if not isinstance(payload, dict):
        raise SystemExit(f"Unsupported artifact payload: {path}")
    return payload


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .web_app import create_app

    uvicorn.run(create_app(args.source, labels_db_path=args.labels), host=args.host, port=args.port)
