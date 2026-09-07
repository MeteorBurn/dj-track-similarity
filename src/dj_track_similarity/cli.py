from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .analysis_config import DEFAULT_ANALYSIS_DEVICE
from .analysis_model_runners import embedding_analysis_output
from .embedding import adapter_factories
from .ffmpeg_runtime import configure_shared_ffmpeg_runtime, inspect_audio_runtime
from .logging_config import configure_logging, uvicorn_log_config
from .runtime import get_torch_runtime_info, recommended_torch_index
from .search import SearchFilters, SimilaritySearch
from .vector_index import VectorIndexUnavailable
from .cli_common import _db, _parse_analysis_device
from .cli_common import LOGGER
from .cli_evaluation import eval_app
from .cli_classifier import classifier_app
from . import cli_analysis, cli_database


app = typer.Typer(help="Local dj-track-similarity utility for current library bundles.")
app.add_typer(eval_app, name="eval")
app.add_typer(classifier_app, name="classifier")
cli_database.register_commands(app)
cli_analysis.register_commands(app)


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

    try:
        audio_runtime = inspect_audio_runtime()
    except RuntimeError as error:
        typer.echo("audio_runtime_check=failed")
        typer.echo(f"audio_runtime_error={error}")
        return

    typer.echo("audio_runtime_check=ok")
    typer.echo(f"ffmpeg_shared_dir={audio_runtime.ffmpeg_directory}")
    typer.echo(f"ffmpeg_version={audio_runtime.ffmpeg_version}")
    for component, library_path in audio_runtime.ffmpeg_libraries:
        typer.echo(f"ffmpeg_{component}={library_path}")
    typer.echo(f"pyav={audio_runtime.pyav_version}")
    typer.echo(f"pyav_module={audio_runtime.pyav_module_path}")
    typer.echo(
        "pyav_libavcodec=" + ".".join(str(part) for part in audio_runtime.pyav_avcodec_version)
    )


@app.command("text-search")
def text_search(
    query: str,
    db_path: Optional[Path] = typer.Option(None, "--db"),
    model: str = typer.Option("clap", "--model", help="Text embedding model: clap or mulan."),
    limit: int = typer.Option(50, "--limit", min=1, max=500),
    min_similarity: Optional[float] = typer.Option(None, "--min-similarity"),
    device: str = typer.Option(DEFAULT_ANALYSIS_DEVICE, "--device", help="Text embedding device: auto, cpu, or cuda."),
) -> None:
    try:
        device_name = _parse_analysis_device(device)
        db = _db(db_path)
        clean_model = model.strip().lower()
        adapter_class = adapter_factories().get(clean_model)
        if adapter_class is None:
            raise ValueError(f"Unsupported text embedding model: {model}")
        adapter = adapter_class(device=device_name)
        if not callable(getattr(adapter, "embed_text", None)):
            raise ValueError(f"{clean_model} does not support text embeddings")
        analysis_output = embedding_analysis_output(
            adapter.embedding_key,
            adapter,
        )
        searcher = SimilaritySearch(
            db,
            adapter.embedding_key,
            analysis_output=analysis_output,
        )
        vector = adapter.embed_text(query.strip())
        results = searcher.search_vector(
            vector,
            filters=SearchFilters(min_similarity=min_similarity),
            limit=limit,
        )
        tracks = db.get_track_summaries(
            [result.target.track_id for result in results]
        )
        for result, track in zip(results, tracks, strict=True):
            if (
                track.catalog_uuid != result.target.catalog_uuid
                or track.track_uuid != result.target.track_uuid
            ):
                raise RuntimeError(
                    "Search result became stale before output: "
                    f"track_id={result.target.track_id}"
                )
            typer.echo(
                f"{result.score:.3f}\t{track.track_id}\t"
                f"{track.track_uuid}\t{track.file_path}"
            )
    except (RuntimeError, ValueError, VectorIndexUnavailable) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    db_path: Optional[Path] = typer.Option(
        None,
        "--db",
        help=(
            "Open an existing library database or create a new one at this "
            "path. Omit to start with no database selected."
        ),
    ),
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
        ffmpeg_runtime_dir = configure_shared_ffmpeg_runtime()
    except (RuntimeError, ValueError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    selected_database_path: Path | None = None
    if db_path is not None:
        selected_database_path = _db(
            db_path,
            configure_file_logging=False,
        ).path
    LOGGER.info(
        "Server starting host=%s port=%s db_path=%s log_path=%s",
        host,
        port,
        selected_database_path,
        log_path,
    )
    LOGGER.debug("shared FFmpeg runtime directory=%s", ffmpeg_runtime_dir)
    uvicorn.run(
        create_app(
            selected_database_path,
            log_level=log_level,
            log_track_events=log_track_events,
        ),
        host=host,
        port=port,
        log_config=uvicorn_log_config(log_level),
    )
