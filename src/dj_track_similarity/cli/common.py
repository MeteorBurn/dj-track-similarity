from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
import logging

import typer

from ..analysis.config import normalize_analysis_device
from ..database import LibraryDatabase
from ..logging_config import configure_logging


LOGGER = logging.getLogger("dj_track_similarity.cli")

DATABASE_OPTION_HELP = "Existing library database."


def _db(
    path: Optional[Path],
    *,
    create: bool = False,
    configure_file_logging: bool = True,
) -> LibraryDatabase:
    """Open an existing library; only ``serve --create`` may create a new one."""

    if path is None:
        typer.secho("Choose a library database with --db", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    if not create and not path.expanduser().exists():
        typer.secho(
            f"Library database not found: {path}. "
            f'Use `dj-sim serve --db "{path}" --create` to create a new library.',
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1)
    log_path = configure_logging() if configure_file_logging else None
    LOGGER.info("CLI database opened db_path=%s log_path=%s", path, log_path)
    try:
        return LibraryDatabase(path)
    except (OSError, RuntimeError, ValueError) as error:
        typer.secho(
            f"Cannot open library database bundle at {path}: {error}",
            err=True,
            fg=typer.colors.RED,
        )
        raise typer.Exit(1) from error


def _write_json_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _emit_json_report(report: dict[str, object], output_path: Path | None) -> None:
    if output_path is not None:
        _write_json_report(output_path, report)
        typer.echo(f"output={output_path} status={report.get('status', 'ok')}")
        return
    typer.echo(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


def _load_json_object(path: Path, description: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{description} JSON is invalid: {error.msg}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{description} JSON must be an object")
    return payload


def _parse_analysis_device(value: str | None) -> str:
    try:
        return normalize_analysis_device(value)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
