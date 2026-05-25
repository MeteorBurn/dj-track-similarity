from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

import typer

from .analysis_jobs import AnalysisJobManager
from .classifier_scoring import analyze_classifier as run_classifier_analysis
from .database import LibraryDatabase
from .dependencies import require_ffmpeg
from .embedding import ClapEmbeddingAdapter
from .genre_jobs import GenreAnalysisJobManager
from .logging_config import configure_logging, set_analysis_diagnostics_enabled
from .runtime import get_torch_runtime_info, recommended_torch_index
from .scanner import scan_library
from .search import SearchFilters, SimilaritySearch
from .sonara_jobs import SonaraFeatureJobManager


app = typer.Typer(help="Local dj-track-similarity utility.")
LOGGER = logging.getLogger(__name__)


def _db(path: Optional[Path]) -> LibraryDatabase:
    log_path = configure_logging()
    db_path = path or Path("dj-track-similarity.sqlite")
    LOGGER.info("CLI database opened db_path=%s log_path=%s", db_path, log_path)
    return LibraryDatabase(db_path)


def _run_cli_job_with_progress(manager: object, job_id: str, *, label: str, poll_interval: float = 0.5):
    typer.echo(f"Starting {label} analysis")
    result = None
    errors: list[BaseException] = []

    def run() -> None:
        nonlocal result
        try:
            result = manager.run_job(job_id)  # type: ignore[attr-defined]
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    previous_width = 0
    while thread.is_alive():
        previous_width = _write_cli_progress(manager.get(job_id), previous_width)  # type: ignore[attr-defined]
        thread.join(poll_interval)
    thread.join()
    if errors:
        raise errors[0]
    status = result or manager.get(job_id)  # type: ignore[attr-defined]
    _write_cli_progress(status, previous_width)
    typer.echo()
    return status


def _write_cli_progress(status: object, previous_width: int = 0) -> int:
    line = _format_cli_progress(status)
    padding = " " * max(0, previous_width - len(line))
    typer.echo(f"\r{line}{padding}", nl=False)
    return len(line)


def _format_cli_progress(status: object) -> str:
    total = int(getattr(status, "total", 0) or 0)
    processed = int(getattr(status, "processed", 0) or 0)
    analyzed = int(getattr(status, "analyzed", 0) or 0)
    failed = int(getattr(status, "failed", 0) or 0)
    progress = (processed / total) if total else (1.0 if getattr(status, "state", "") == "completed" else 0.0)
    progress = min(1.0, max(0.0, progress))
    bar_width = 24
    filled = int(round(progress * bar_width))
    bar = "#" * filled + "-" * (bar_width - filled)
    speed = _status_tracks_per_second(status, processed)
    eta = _format_eta_seconds(_eta_seconds(total, processed, speed))
    total_text = str(total) if total else "?"
    return (
        f"[{bar}] {progress * 100:5.1f}% "
        f"processed={processed}/{total_text} analyzed={analyzed} failed={failed} "
        f"{speed:.2f} tracks/s eta={eta}"
    )


def _status_tracks_per_second(status: object, processed: int) -> float:
    avg_seconds = getattr(status, "avg_seconds_per_track", None)
    if avg_seconds:
        return 1.0 / float(avg_seconds)
    started_at = getattr(status, "started_at", None)
    if started_at and processed:
        elapsed = max(0.001, time.time() - float(started_at))
        return processed / elapsed
    return 0.0


def _eta_seconds(total: int, processed: int, speed: float) -> float | None:
    if total <= 0 or processed >= total:
        return 0.0
    if speed <= 0:
        return None
    return max(0.0, (total - processed) / speed)


def _format_eta_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    remaining = int(round(seconds))
    hours, remainder = divmod(remaining, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


@app.command()
def scan(music_root: Path, db_path: Optional[Path] = typer.Option(None, "--db")) -> None:
    stats = scan_library(_db(db_path), music_root)
    typer.echo(f"added={stats.added} updated={stats.updated} unchanged={stats.unchanged} skipped={stats.skipped}")


@app.command("relocate-library")
def relocate_library(
    old_root: Path,
    new_root: Path,
    apply: bool = typer.Option(False, "--apply", help="Update stored track paths after preview checks pass."),
    db_path: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    try:
        result = _db(db_path).relocate_library(old_root, new_root, apply=apply)
    except ValueError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    typer.echo(
        f"dry_run={result['dry_run']} tracks_matched={result['tracks_matched']} "
        f"tracks_updated={result['tracks_updated']} missing_files={len(result['missing_files'])} "
        f"conflicts={len(result['conflicts'])}"
    )
    for conflict in result["conflicts"]:
        typer.echo(
            f"conflict track_id={conflict['track_id']} existing_track_id={conflict['existing_track_id']} "
            f"{conflict['old_path']} -> {conflict['new_path']}"
        )
    for missing in result["missing_files"]:
        typer.echo(f"missing track_id={missing['track_id']} path={missing['path']}")


@app.command()
def analyze(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    limit: Optional[int] = typer.Option(None, "--limit"),
    adapter: str = typer.Option("mert", "--adapter", help="Embedding adapter: mert or clap. clap uses the LAION music checkpoint."),
    device: str = typer.Option("auto", "--device", help="Embedding device: auto, cpu, or cuda."),
    batch_size: int = typer.Option(4, "--batch-size", min=1, max=64, help="Embedding inference batch size."),
    diagnostics: bool = typer.Option(False, "--diagnostics", help="Write decoder fallback and batch timing diagnostics to the file log."),
) -> None:
    set_analysis_diagnostics_enabled(diagnostics)
    manager = AnalysisJobManager(_db(db_path))
    job_id = manager.create_job(
        adapter_name=adapter,
        limit=limit,
        device=device,
        batch_size=batch_size,
    )
    status = _run_cli_job_with_progress(manager, job_id, label=adapter)
    typer.echo(
        f"state={status.state} total={status.total} processed={status.processed} "
        f"analyzed={status.analyzed} failed={status.failed} embedding_key={status.embedding_key} "
        f"device={status.device} batch_size={status.batch_size}"
    )


@app.command("analyze-genres")
def analyze_genres(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    limit: Optional[int] = typer.Option(None, "--limit"),
    device: str = typer.Option("auto", "--device", help="MAEST device: auto, cpu, or cuda."),
    top_k: int = typer.Option(3, "--top-k", min=1, max=10, help="Number of MAEST genre labels to store per track."),
    batch_size: int = typer.Option(4, "--batch-size", min=1, max=64, help="MAEST inference batch size."),
    diagnostics: bool = typer.Option(False, "--diagnostics", help="Write decoder fallback and batch timing diagnostics to the file log."),
) -> None:
    set_analysis_diagnostics_enabled(diagnostics)
    manager = GenreAnalysisJobManager(_db(db_path))
    job_id = manager.create_job(
        limit=limit,
        device=device,
        top_k=top_k,
        batch_size=batch_size,
    )
    status = _run_cli_job_with_progress(manager, job_id, label="maest")
    typer.echo(
        f"state={status.state} total={status.total} processed={status.processed} "
        f"analyzed={status.analyzed} failed={status.failed} embedding_key={status.embedding_key} "
        f"device={status.device} top_k={status.top_k} batch_size={status.batch_size}"
    )


@app.command("analyze-sonara")
def analyze_sonara(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    limit: Optional[int] = typer.Option(None, "--limit"),
    batch_size: int = typer.Option(1, "--batch-size", min=1, max=64, help="Parallel Sonara track workers."),
    diagnostics: bool = typer.Option(False, "--diagnostics", help="Write analysis timing diagnostics to the file log."),
) -> None:
    set_analysis_diagnostics_enabled(diagnostics)
    manager = SonaraFeatureJobManager(_db(db_path))
    job_id = manager.create_job(limit=limit, batch_size=batch_size)
    status = _run_cli_job_with_progress(manager, job_id, label="sonara")
    typer.echo(
        f"state={status.state} total={status.total} processed={status.processed} "
        f"analyzed={status.analyzed} failed={status.failed} batch_size={status.batch_size}"
    )


@app.command("analyze-classifier")
def analyze_classifier(
    classifier: str = typer.Argument(..., help="Classifier key, for example live_instrumentation."),
    db_path: Optional[Path] = typer.Option(None, "--db"),
    model_path: Optional[Path] = typer.Option(None, "--model"),
    limit: Optional[int] = typer.Option(None, "--limit"),
) -> None:
    result = run_classifier_analysis(_db(db_path), classifier=classifier, model_path=model_path, limit=limit)
    typer.echo(
        f"classifier={result['classifier']} scored={result['scored']} "
        f"skipped={result['skipped']} model={result['model']}"
    )


@app.command()
def doctor() -> None:
    info = get_torch_runtime_info()
    typer.echo(f"python={info.python}")
    if not info.torch_installed:
        typer.echo(f"torch=missing error={info.error}")
        index_url = recommended_torch_index(info)
        if index_url:
            typer.echo(f"suggested_torch_index={index_url}")
            typer.echo(f"install=torch torchaudio --index-url {index_url}")
        return

    typer.echo(f"torch={info.torch_version}")
    typer.echo(f"torch_cuda_build={info.torch_cuda_build}")
    typer.echo(f"cuda_available={info.cuda_available}")
    typer.echo(f"cuda_device_count={info.device_count}")
    typer.echo(f"cuda_device_name={info.device_name}")
    typer.echo(f"nvidia_smi_cuda={info.nvidia_smi_cuda}")
    if info.cuda_available:
        typer.echo("device_auto=cuda")
    else:
        typer.echo("device_auto=cpu")
        index_url = recommended_torch_index(info)
        if index_url:
            typer.echo(f"suggested_torch_index={index_url}")
            typer.echo(f"install=torch torchaudio --index-url {index_url}")


@app.command("text-search")
def text_search(
    query: str,
    db_path: Optional[Path] = typer.Option(None, "--db"),
    limit: int = typer.Option(50, "--limit", min=1, max=500),
    min_similarity: Optional[float] = typer.Option(None, "--min-similarity"),
    device: str = typer.Option("auto", "--device", help="CLAP device: auto, cpu, or cuda."),
) -> None:
    adapter = ClapEmbeddingAdapter(device=device)
    vector = adapter.embed_text(query.strip())
    results = SimilaritySearch(_db(db_path), embedding_key=adapter.embedding_key).search_vector(
        vector,
        filters=SearchFilters(min_similarity=min_similarity),
        limit=limit,
    )
    for result in results:
        typer.echo(f"{result.score:.3f}\t{result.track.id}\t{result.track.path}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    db_path: Optional[Path] = typer.Option(None, "--db"),
    log_level: str = typer.Option("info", "--log-level", help="File log level: debug, info, warning, error, critical."),
    log_track_events: bool = typer.Option(
        False,
        "--log-track-events",
        help="Write successful per-track events to the file log.",
    ),
) -> None:
    import uvicorn

    from .api import create_app

    try:
        log_path = configure_logging(level=log_level, log_track_events=log_track_events)
        ffmpeg_path = require_ffmpeg()
    except (RuntimeError, ValueError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    LOGGER.info("Server starting host=%s port=%s db_path=%s log_path=%s", host, port, db_path, log_path)
    LOGGER.debug("ffmpeg available path=%s", ffmpeg_path)
    uvicorn.run(
        create_app(
            db_path,
            log_level=log_level,
            log_track_events=log_track_events,
        ),
        host=host,
        port=port,
    )
