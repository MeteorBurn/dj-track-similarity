from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from .lab_db import RhythmLabDatabase
from .predictions import apply_model_to_lab, export_predictions_csv
from .training import benchmark_lab_database


LAB_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = LAB_ROOT.parents[1]
DEFAULT_SOURCE_DB = Path(r"C:\db\abstracted.sqlite")
DEFAULT_LABELS_DB = LAB_ROOT / "data" / "rhythm_lab.sqlite"
DEFAULT_ARTIFACT_DIR = LAB_ROOT / "artifacts" / "break-energy"
DEFAULT_BREAK_ENERGY_TARGET = PROJECT_ROOT / "models" / "classifiers" / "break-energy"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Auxiliary classifier labeling and training lab.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    train_parser = subcommands.add_parser("train", help="Benchmark the Break Energy classifier for available feature sets.")
    _add_data_options(train_parser)
    train_parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACT_DIR)
    train_parser.set_defaults(func=_train)

    predict_parser = subcommands.add_parser("predict", help="Apply a trained model artifact to feature-complete source tracks.")
    predict_parser.add_argument("artifact", type=Path)
    _add_data_options(predict_parser)
    predict_parser.set_defaults(func=_predict)

    export_parser = subcommands.add_parser("export-predictions", help="Export saved Break Energy predictions to CSV.")
    export_parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_DB)
    export_parser.add_argument("--output", type=Path, default=DEFAULT_ARTIFACT_DIR / "predictions.csv")
    export_parser.set_defaults(func=_export_predictions)

    promote_parser = subcommands.add_parser(
        "promote-break-energy",
        help="Copy the latest combined Break Energy model into the main project's classifier slot.",
    )
    promote_parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACT_DIR)
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
    results = benchmark_lab_database(args.source, args.labels, args.artifacts)
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


def _predict(args: argparse.Namespace) -> None:
    result = apply_model_to_lab(args.source, args.labels, args.artifact)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def _export_predictions(args: argparse.Namespace) -> None:
    path = export_predictions_csv(args.labels, args.output)
    print(f"output={path}")


def _promote_break_energy(args: argparse.Namespace) -> None:
    artifact = _latest_combined_artifact(args.artifacts)
    payload = _load_artifact_payload(artifact)
    if str(payload.get("feature_set")) != "combined":
        raise SystemExit(f"Expected a combined artifact, got feature_set={payload.get('feature_set')!r}")

    target = Path(args.target)
    target.mkdir(parents=True, exist_ok=True)
    model_path = target / "model.joblib"
    metadata_path = target / "model.json"
    shutil.copy2(artifact, model_path)
    metadata = {
        "classifier": "break_energy",
        "score_name": "Break Energy",
        "feature_set": payload.get("feature_set"),
        "feature_count": len(payload.get("feature_names", [])),
        "label_order": payload.get("label_order", ["broken", "straight"]),
        "source_artifact": str(artifact),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
        "trained_label_counts": RhythmLabDatabase(args.labels).label_counts(),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(f"model={model_path} metadata={metadata_path} source={artifact}")


def _latest_combined_artifact(artifact_dir: str | Path) -> Path:
    artifacts = sorted(Path(artifact_dir).glob("break-energy-combined-*.joblib"))
    if not artifacts:
        raise SystemExit(f"No combined Break Energy model artifacts found in {artifact_dir}")
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
