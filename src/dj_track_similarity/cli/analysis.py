from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from ..analysis.config import (
    DEFAULT_ANALYSIS_DEVICE,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    DEFAULT_ANALYSIS_TOP_K,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    DEFAULT_SONARA_BATCH_SIZE,
    MAX_ANALYSIS_INFERENCE_BATCH_SIZE,
    MAX_ANALYSIS_TOP_K,
    MAX_ANALYSIS_TRACK_BATCH_SIZE,
    MAX_SONARA_BATCH_SIZE,
    ML_ANALYSIS_MODEL_ORDER,
    MIN_ANALYSIS_INFERENCE_BATCH_SIZE,
    MIN_ANALYSIS_TOP_K,
    MIN_ANALYSIS_TRACK_BATCH_SIZE,
    MIN_SONARA_BATCH_SIZE,
    build_analysis_job_config,
    parse_analysis_models_text,
    parse_sonara_bpm_range,
)
from ..analysis.jobs import AnalysisJobManager
from ..analysis.sonara_runtime import DEFAULT_SONARA_BPM_PRESET, SONARA_BPM_PRESETS
from ..classifier.scoring import analyze_classifier as run_classifier_analysis
from .common import _db
from .progress import _run_cli_job_with_progress


_SONARA_BPM_RANGE_HELP = (
    "SONARA BPM analysis range: a preset ("
    + ", ".join(f"{name} {low:g}-{high:g}" for name, (low, high) in SONARA_BPM_PRESETS.items())
    + ") or MIN-MAX such as 70-140, where MAX is at least twice MIN. Defaults to the "
    f"library's range, or {DEFAULT_SONARA_BPM_PRESET} for a library without SONARA analysis."
)


def _parse_analysis_models(value: str) -> list[str]:
    try:
        return list(parse_analysis_models_text(value))
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


def analyze(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    limit: Optional[int] = typer.Option(None, "--limit"),
    models: str = typer.Option(",".join(ML_ANALYSIS_MODEL_ORDER), "--models", help="Comma-separated ML models, or SONARA alone: maest,mert_v2,muq,mulan,clap | sonara."),
    device: str = typer.Option(DEFAULT_ANALYSIS_DEVICE, "--device", help="Embedding device: auto, cpu, or cuda."),
    top_k: int = typer.Option(
        DEFAULT_ANALYSIS_TOP_K,
        "--top-k",
        min=MIN_ANALYSIS_TOP_K,
        max=MAX_ANALYSIS_TOP_K,
        help="Number of MAEST genre labels to store per track.",
    ),
    track_batch_size: int = typer.Option(
        DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
        "--track-batch-size",
        min=MIN_ANALYSIS_TRACK_BATCH_SIZE,
        max=MAX_ANALYSIS_TRACK_BATCH_SIZE,
        help="Number of decoded tracks held and processed together.",
    ),
    inference_batch_size: int = typer.Option(
        DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
        "--inference-batch-size",
        min=MIN_ANALYSIS_INFERENCE_BATCH_SIZE,
        max=MAX_ANALYSIS_INFERENCE_BATCH_SIZE,
        help="MERT-v2/CLAP/MAEST model inference batch size.",
    ),
    sonara_batch_size: int = typer.Option(
        DEFAULT_SONARA_BATCH_SIZE,
        "--sonara-batch-size",
        min=MIN_SONARA_BATCH_SIZE,
        max=MAX_SONARA_BATCH_SIZE,
        help="Native SONARA/Symphonia file batch size; independent from ML batching.",
    ),
    sonara_bpm_range: Optional[str] = typer.Option(
        None,
        "--sonara-bpm-range",
        help=_SONARA_BPM_RANGE_HELP,
    ),
    ml_staged: bool = typer.Option(False, "--ml-staged", help="Enable ML Staged Mode (copy→decode→inference pipeline for HDD optimization)."),
    ml_staging_path: Optional[str] = typer.Option(None, "--ml-staging-path", help="ML staging folder (SSD recommended). Required when --ml-staged is enabled."),
    ml_copy_workers: int = typer.Option(4, "--ml-copy-workers", min=1, max=16, help="ML staged: parallel copy workers (HDD→SSD)."),
    ml_decode_workers: int = typer.Option(8, "--ml-decode-workers", min=1, max=32, help="ML staged: parallel TorchCodec decoders."),
    ml_stage_size: int = typer.Option(64, "--ml-stage-size", min=1, max=512, help="ML staged: max files in staging directory."),
) -> None:
    # Validate and build ML staging config if enabled
    ml_staging_config = None
    if ml_staged:
        if not ml_staging_path:
            typer.secho(
                "Error: --ml-staging-path is required when --ml-staged is enabled",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(1)
        staging_root = Path(ml_staging_path)
        if not staging_root.is_dir():
            typer.secho(
                f"Error: ML staging folder does not exist: {staging_root}",
                err=True,
                fg=typer.colors.RED,
            )
            raise typer.Exit(1)
        from ..analysis.ml_staging import MLStagingConfig
        ml_staging_config = MLStagingConfig(
            root=staging_root,
            copy_workers=ml_copy_workers,
            decode_workers=ml_decode_workers,
            stage_size=ml_stage_size,
            inference_batch_size=inference_batch_size,
        )

    try:
        selected_models = _parse_analysis_models(models)
        sonara_bpm_min, sonara_bpm_max = parse_sonara_bpm_range(sonara_bpm_range) or (None, None)
        config = build_analysis_job_config(
            models=selected_models,
            limit=limit,
            device=device,
            top_k=top_k,
            track_batch_size=track_batch_size,
            inference_batch_size=inference_batch_size,
            sonara_batch_size=sonara_batch_size,
            sonara_bpm_min=sonara_bpm_min,
            sonara_bpm_max=sonara_bpm_max,
            ml_staging_config=ml_staging_config,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    manager = AnalysisJobManager(_db(db_path))
    try:
        job_id = manager.create_job(
            models=list(config.models),
            limit=config.limit,
            device=config.device,
            top_k=config.top_k,
            track_batch_size=config.track_batch_size,
            inference_batch_size=config.inference_batch_size,
            sonara_batch_size=config.sonara_batch_size,
            sonara_bpm_min=config.sonara_bpm_min,
            sonara_bpm_max=config.sonara_bpm_max,
            ml_staging_config=config.ml_staging_config,
        )
        status = _run_cli_job_with_progress(manager, job_id, label=",".join(config.models))
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    finally:
        manager.close()
    result_summary = (
        f"state={status.state} total={status.total} processed={status.processed} "
        f"analyzed={status.analyzed} failed={status.failed} models={','.join(status.models)}"
    )
    if config.models == ("sonara",):
        result_summary += (
            f" sonara_batch_size={config.sonara_batch_size}"
            f" sonara_bpm={status.sonara_bpm_min:g}-{status.sonara_bpm_max:g}"
        )
    else:
        result_summary += (
            f" device={status.device} top_k={status.top_k}"
            f" track_batch_size={status.track_batch_size} inference_batch_size={status.inference_batch_size}"
        )
    typer.echo(result_summary)


def analyze_classifier(
    classifier: str = typer.Argument(..., help="Classifier key, for example live_instrumentation."),
    db_path: Optional[Path] = typer.Option(None, "--db"),
    model_path: Optional[Path] = typer.Option(None, "--model"),
    limit: Optional[int] = typer.Option(None, "--limit"),
) -> None:
    try:
        result = run_classifier_analysis(_db(db_path), classifier=classifier, model_path=model_path, limit=limit)
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    for warning in result.get("warnings", []):
        typer.secho(f"warning: {warning}", err=True, fg=typer.colors.YELLOW)
    typer.echo(
        f"classifier={result['classifier']} scored={result['scored']} "
        f"skipped={result['skipped']} model={result['model']}"
    )


def register_commands(app: typer.Typer) -> None:
    app.command()(analyze)
    app.command('analyze-classifier')(analyze_classifier)
    app.command('export-maest-mel')(export_maest_mel)


def export_maest_mel(
    track_id: int = typer.Argument(..., min=1),
    db_path: Path = typer.Option(..., "--db", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output", help="New .npz file containing mel, embedding and metadata_json."),
    device: str = typer.Option(DEFAULT_ANALYSIS_DEVICE, "--device"),
    top_k: int = typer.Option(DEFAULT_ANALYSIS_TOP_K, "--top-k", min=MIN_ANALYSIS_TOP_K, max=MAX_ANALYSIS_TOP_K),
) -> None:
    from ..analysis.maest_export import write_maest_mel_export

    if output.suffix.lower() != ".npz" or output.exists() or not output.parent.is_dir():
        raise typer.BadParameter("Choose a new .npz file in an existing output directory", param_hint="--output")
    database = _db(db_path, configure_file_logging=False)
    manager = AnalysisJobManager(database)
    try:
        export = manager.export_maest_mel(
            track_id, device=device, top_k=top_k,
        )
        write_maest_mel_export(export, output)
    except (OSError, RuntimeError, ValueError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    finally:
        manager.close()
    typer.echo(f"output={output.resolve()} track_id={track_id}")
