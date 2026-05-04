from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .analysis_jobs import AnalysisJobManager
from .database import LibraryDatabase
from .embedding import ClapEmbeddingAdapter
from .exporter import export_playlist
from .scanner import scan_library
from .search import SearchFilters, SimilaritySearch
from .tags import apply_custom_tags, build_tag_preview


app = typer.Typer(help="Local dj-track-similarity utility.")


def _db(path: Optional[Path]) -> LibraryDatabase:
    return LibraryDatabase(path or Path("dj-track-similarity.sqlite"))


@app.command()
def scan(music_root: Path, db_path: Optional[Path] = typer.Option(None, "--db")) -> None:
    stats = scan_library(_db(db_path), music_root)
    typer.echo(f"added={stats.added} updated={stats.updated} unchanged={stats.unchanged} skipped={stats.skipped}")


@app.command()
def analyze(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    limit: Optional[int] = typer.Option(None, "--limit"),
    fake: bool = typer.Option(False, "--fake", help="Use deterministic fake embeddings for smoke tests."),
    adapter: str = typer.Option("mert", "--adapter", help="Embedding adapter: mert or clap."),
    device: str = typer.Option("auto", "--device", help="Embedding device: auto, cpu, or cuda."),
    batch_size: int = typer.Option(4, "--batch-size", min=1, max=64, help="Embedding inference batch size."),
) -> None:
    adapter_name = "fake" if fake else adapter
    status = AnalysisJobManager(_db(db_path)).run_sync(
        adapter_name=adapter_name,
        limit=limit,
        device=device,
        batch_size=batch_size,
    )
    typer.echo(
        f"state={status.state} total={status.total} processed={status.processed} "
        f"analyzed={status.analyzed} failed={status.failed} embedding_key={status.embedding_key} "
        f"device={status.device} batch_size={status.batch_size}"
    )


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
def export(
    playlist_id: int,
    output_dir: Path = typer.Option(Path("."), "--output-dir"),
    format: str = typer.Option("m3u", "--format"),
    db_path: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    path = export_playlist(_db(db_path), playlist_id, output_dir, format)
    typer.echo(path)


@app.command("tag-preview")
def tag_preview(track_ids: list[int], db_path: Optional[Path] = typer.Option(None, "--db")) -> None:
    for preview in build_tag_preview(_db(db_path), track_ids):
        typer.echo(f"{preview.track_id} {preview.path} {preview.tags}")


@app.command("tag-apply")
def tag_apply(track_ids: list[int], db_path: Optional[Path] = typer.Option(None, "--db")) -> None:
    for preview in apply_custom_tags(_db(db_path), track_ids):
        typer.echo(f"{preview.track_id} {preview.path} {preview.tags}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8765, "--port"),
    db_path: Optional[Path] = typer.Option(None, "--db"),
) -> None:
    import uvicorn

    from .api import create_app

    uvicorn.run(create_app(db_path or Path("dj-track-similarity.sqlite")), host=host, port=port)
