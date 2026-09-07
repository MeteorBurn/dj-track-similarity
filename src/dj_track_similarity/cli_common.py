from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
import logging

import typer

from .analysis_config import normalize_analysis_device
from .database import LibraryDatabase
from .logging_config import configure_logging


LOGGER = logging.getLogger("dj_track_similarity.cli")


def _db(
    path: Optional[Path],
    *,
    configure_file_logging: bool = True,
) -> LibraryDatabase:
    log_path = configure_logging() if configure_file_logging else None
    db_path = path or Path("dj-track-similarity.sqlite")
    LOGGER.info("CLI database opened db_path=%s log_path=%s", db_path, log_path)
    try:
        return LibraryDatabase(db_path)
    except (OSError, RuntimeError, ValueError) as error:
        typer.secho(
            f"Cannot open library database bundle at {db_path}: {error}",
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
