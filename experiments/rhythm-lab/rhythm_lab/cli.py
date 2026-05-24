from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path

from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.database import LibraryDatabase

from .importer import import_non_sync_sample, import_syncopated_subset
from .maest_embeddings import LabMaestAnalysisJobManager
from .predictions import apply_model_to_lab, export_predictions_csv
from .training import benchmark_lab_database


LAB_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DB = Path(r"C:\db\abstracted.sqlite")
DEFAULT_LAB_DB = LAB_ROOT / "data" / "rhythm_lab.sqlite"
DEFAULT_ARTIFACT_DIR = LAB_ROOT / "artifacts"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Temporary rhythm classifier lab.")
    subcommands = parser.add_subparsers(dest="command", required=True)

    import_parser = subcommands.add_parser("import-subset", help="Import MAEST-sync candidates into the reduced lab DB.")
    import_parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_DB)
    import_parser.add_argument("--db", type=Path, default=DEFAULT_LAB_DB)
    import_parser.set_defaults(func=_import_subset)

    non_sync_parser = subcommands.add_parser(
        "import-non-sync-sample",
        help="Import a random sample of tracks without the MAEST syncopated rhythm flag.",
    )
    non_sync_parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE_DB)
    non_sync_parser.add_argument("--db", type=Path, default=DEFAULT_LAB_DB)
    non_sync_parser.add_argument("--count", type=int, default=944)
    non_sync_parser.set_defaults(func=_import_non_sync_sample)

    mert_parser = subcommands.add_parser("analyze-mert", help="Compute missing MERT embeddings for the lab DB.")
    _add_analysis_options(mert_parser)
    mert_parser.set_defaults(func=_analyze_mert)

    maest_parser = subcommands.add_parser("analyze-maest", help="Compute missing MAEST embeddings for the lab DB.")
    _add_analysis_options(maest_parser)
    maest_parser.set_defaults(func=_analyze_maest)

    train_parser = subcommands.add_parser("train", help="Benchmark rhythm classifiers for available feature sets.")
    train_parser.add_argument("--db", type=Path, default=DEFAULT_LAB_DB)
    train_parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACT_DIR)
    train_parser.set_defaults(func=_train)

    predict_parser = subcommands.add_parser("predict", help="Apply a trained model artifact to all feature-complete lab tracks.")
    predict_parser.add_argument("artifact", type=Path)
    predict_parser.add_argument("--db", type=Path, default=DEFAULT_LAB_DB)
    predict_parser.set_defaults(func=_predict)

    export_parser = subcommands.add_parser("export-predictions", help="Export saved rhythm predictions to CSV.")
    export_parser.add_argument("--db", type=Path, default=DEFAULT_LAB_DB)
    export_parser.add_argument("--output", type=Path, default=LAB_ROOT / "artifacts" / "predictions.csv")
    export_parser.set_defaults(func=_export_predictions)

    serve_parser = subcommands.add_parser("serve", help="Start the minimal labeling web app.")
    serve_parser.add_argument("--db", type=Path, default=DEFAULT_LAB_DB)
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8777)
    serve_parser.set_defaults(func=_serve)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)
    return 0


def _add_analysis_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path, default=DEFAULT_LAB_DB)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--batch-size", type=int, default=4)


def _import_subset(args: argparse.Namespace) -> None:
    summary = import_syncopated_subset(args.source, args.db)
    print(f"source={summary.source_db} db={summary.lab_db} scanned={summary.scanned} imported={summary.imported}")


def _import_non_sync_sample(args: argparse.Namespace) -> None:
    summary = import_non_sync_sample(args.source, args.db, count=args.count)
    print(
        f"source={summary.source_db} db={summary.lab_db} scanned={summary.scanned} "
        f"requested={args.count} imported={summary.imported}"
    )


def _analyze_mert(args: argparse.Namespace) -> None:
    status = _run_analysis_with_progress(
        AnalysisJobManager(LibraryDatabase(args.db)),
        adapter_name="mert",
        limit=args.limit,
        device=args.device,
        batch_size=args.batch_size,
    )
    _print_analysis_status(status)


def _analyze_maest(args: argparse.Namespace) -> None:
    status = _run_analysis_with_progress(
        LabMaestAnalysisJobManager(LibraryDatabase(args.db)),
        adapter_name="maest",
        limit=args.limit,
        device=args.device,
        batch_size=args.batch_size,
    )
    _print_analysis_status(status)


def _train(args: argparse.Namespace) -> None:
    results = benchmark_lab_database(args.db, args.artifacts)
    print(json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True))


def _predict(args: argparse.Namespace) -> None:
    result = apply_model_to_lab(args.db, args.artifact)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


def _export_predictions(args: argparse.Namespace) -> None:
    path = export_predictions_csv(args.db, args.output)
    print(f"output={path}")


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .web_app import create_app

    uvicorn.run(create_app(args.db), host=args.host, port=args.port)


def _run_analysis_with_progress(
    manager: AnalysisJobManager,
    *,
    adapter_name: str,
    limit: int | None,
    device: str,
    batch_size: int,
    progress_interval: float = 1.0,
):
    job_id = manager.create_job(
        adapter_name=adapter_name,
        limit=limit,
        device=device,
        batch_size=batch_size,
    )
    result = []
    errors: list[BaseException] = []

    def run_job() -> None:
        try:
            result.append(manager.run_job(job_id))
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=run_job, daemon=True)
    worker.start()
    previous_line = ""
    try:
        while worker.is_alive():
            previous_line = _emit_analysis_progress(manager.get(job_id), previous_line)
            worker.join(progress_interval)
        status = result[0] if result else manager.get(job_id)
        _emit_analysis_progress(status, previous_line, final=True)
    except KeyboardInterrupt:
        manager.cancel(job_id)
        _emit_analysis_progress(manager.get(job_id), previous_line, final=True)
        raise
    if errors:
        raise errors[0]
    return status


def _emit_analysis_progress(status: object, previous_line: str, *, final: bool = False, stream=sys.stderr) -> str:
    line = _format_analysis_progress(status)
    if line == previous_line and not final:
        return previous_line
    if stream.isatty():
        padding = " " * max(0, len(previous_line) - len(line))
        stream.write(f"\r{line}{padding}")
        if final:
            stream.write("\n")
    else:
        stream.write(f"{line}\n")
    stream.flush()
    return line


def _format_analysis_progress(status: object, *, bar_width: int = 24) -> str:
    adapter_name = str(getattr(status, "adapter_name", "analysis"))
    state = str(getattr(status, "state", "unknown"))
    total = max(0, int(getattr(status, "total", 0) or 0))
    processed = max(0, int(getattr(status, "processed", 0) or 0))
    analyzed = max(0, int(getattr(status, "analyzed", 0) or 0))
    failed = max(0, int(getattr(status, "failed", 0) or 0))
    if total:
        ratio = min(1.0, processed / total)
        percent = ratio * 100
    else:
        ratio = 1.0
        percent = 100.0
    filled = min(bar_width, int(ratio * bar_width))
    bar = "#" * filled + "-" * (bar_width - filled)
    parts = [
        f"{adapter_name} {state}",
        f"[{bar}]",
        f"{processed}/{total}",
        f"{percent:.1f}%",
        f"analyzed={analyzed}",
        f"failed={failed}",
    ]
    average = getattr(status, "avg_seconds_per_track", None)
    if average is not None:
        parts.append(f"avg={float(average):.1f}s")
    current_path = getattr(status, "current_path", None)
    if current_path:
        parts.append(f"current={Path(str(current_path)).name}")
    return " ".join(parts)


def _print_analysis_status(status: object) -> None:
    print(
        f"state={status.state} total={status.total} processed={status.processed} "
        f"analyzed={status.analyzed} failed={status.failed} embedding_key={status.embedding_key} "
        f"device={status.device} batch_size={status.batch_size}"
    )
