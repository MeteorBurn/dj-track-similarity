from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

import typer

from ..db.validation import DatabaseValidator, format_validation_finding
from ..db.migration import (
    MIGRATION_CONFIRMATION,
    LegacyLibraryMigrationError,
    migrate_legacy_library_database,
)
from ..db.optimize import OptimizationError, inspect_database, optimize_database
from ..scanner import scan_library
from .common import _db, _write_json_report


def scan(music_root: Path, db_path: Optional[Path] = typer.Option(None, "--db")) -> None:
    try:
        stats = scan_library(_db(db_path), music_root)
    except (FileNotFoundError, NotADirectoryError, OSError, ValueError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    typer.echo(f"added={stats.added} updated={stats.updated} unchanged={stats.unchanged} skipped={stats.skipped}")


def validate_database(db_path: Path = typer.Option(..., "--db"), report: Path | None = typer.Option(None, "--report")) -> None:
    def echo_finding(item) -> None:
        typer.echo(format_validation_finding(item))

    def echo_track(track) -> None:
        for finding in track.findings:
            echo_finding(finding)

    try:
        result = DatabaseValidator(db_path).run(echo_finding, on_track=echo_track)
        payload = {
            "status": result.status,
            "tracks": result.tracks_checked,
            "checked": result.checked,
            "warnings": result.warning_count,
            "errors": result.error_count,
        }
        if report is not None:
            _write_json_report(report, payload)
        typer.echo(json.dumps(payload, ensure_ascii=False))
        if result.error_count:
            raise typer.Exit(2)
    except (FileNotFoundError, sqlite3.Error, ValueError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error


def optimize_database_command(
    db_path: Path = typer.Option(..., "--db"),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Inspect the database and report free space without writing anything.",
    ),
) -> None:
    """Back up, verify, and optimize one SQLite database (VACUUM, ANALYZE, FTS merge)."""

    def echo_event(level: str, message: str, path: Optional[str]) -> None:
        typer.echo(f"[{level.upper()}] {message}" + (f" ({path})" if path else ""))

    try:
        if dry_run:
            inspection = inspect_database(db_path, on_event=echo_event)
            free = "unknown" if inspection.free_bytes is None else inspection.free_bytes
            typer.echo(f"database_kind={inspection.database_kind}")
            typer.echo(f"size={inspection.size}")
            typer.echo(f"compacted_estimate={inspection.compacted_bytes}")
            typer.echo(f"free_bytes={free}")
            typer.echo(f"required_free_bytes={inspection.required_free_bytes}")
            typer.echo(f"free_space_ok={inspection.free_space_ok}")
            if not inspection.free_space_ok:
                raise typer.Exit(1)
            return
        summary = optimize_database(db_path, on_event=echo_event)
    except (OptimizationError, sqlite3.Error, OSError, ValueError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    typer.echo(f"database_kind={summary.database_kind}")
    typer.echo(f"size_before={summary.size_before}")
    typer.echo(f"size_after={summary.size_after}")
    typer.echo(f"integrity_before={summary.integrity_before}")
    typer.echo(f"integrity_after={summary.integrity_after}")
    for item in summary.files:
        backup = "removed (verified)" if item.backup_path is None else str(item.backup_path)
        typer.echo(
            f"{item.role}: size {item.size_before}->{item.size_after} "
            f"journal={item.journal_mode} backup={backup}"
        )


def migrate_database_command(
    db_path: Path = typer.Option(..., "--db", help="Legacy Core database path."),
    backup_root: Optional[Path] = typer.Option(
        None,
        "--backup-root",
        help="Parent directory for the timestamped migration backup.",
    ),
    confirm: Optional[str] = typer.Option(
        None,
        "--confirm",
        help=f"Required exact phrase: {MIGRATION_CONFIRMATION}",
    ),
) -> None:
    """Explicitly merge a legacy Core/Artifacts pair into one library database."""

    try:
        phrase = confirm or typer.prompt(
            f"Type {MIGRATION_CONFIRMATION} to continue"
        )
        result = migrate_legacy_library_database(
            db_path,
            confirm=phrase,
            backup_root=backup_root,
        )
    except (OSError, sqlite3.Error, LegacyLibraryMigrationError, ValueError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    typer.echo(
        f"library={result.library_path}\n"
        f"backup={result.backup_dir}\n"
        f"catalog_uuid={result.catalog_uuid}\n"
        f"roots={','.join(result.roots)}\n"
        f"fts_rows={result.fts_rows}\n"
        f"integrity_check={result.integrity_check} "
        f"foreign_key_violations={result.foreign_key_violations}"
    )


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


def register_commands(app: typer.Typer) -> None:
    app.command()(scan)
    app.command('validate-database')(validate_database)
    app.command('optimize-database')(optimize_database_command)
    app.command('migrate-database')(migrate_database_command)
    app.command('relocate-library')(relocate_library)
