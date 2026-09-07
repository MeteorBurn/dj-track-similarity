from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

import typer

from ..classifier.production import (
    build_classifier_calibration_report,
    normalize_label_suggestion_mode,
    suggest_classifier_labels,
)
from .common import _db, _emit_json_report


classifier_app = typer.Typer(help="Inspect promoted classifier production reports and label suggestions.")


@classifier_app.command("calibration-report")
def classifier_calibration_report(
    classifier: str = typer.Option(..., "--classifier", help="Promoted classifier key."),
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Optional[Path] = typer.Option(None, "--output", dir_okay=False, writable=True),
    min_feedback: int = typer.Option(
        30,
        "--min-feedback",
        min=1,
        help="Candidate feedback rows requested before diagnostics are considered usable.",
    ),
) -> None:
    try:
        report = build_classifier_calibration_report(
            _db(db_path),
            classifier,
            min_feedback=min_feedback,
        )
        _emit_json_report(report, output_path)
    except (ValueError, sqlite3.IntegrityError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error


@classifier_app.command("suggest-labels")
def classifier_suggest_labels(
    classifier: str = typer.Option(..., "--classifier", help="Promoted classifier key."),
    mode: str = typer.Option("uncertainty", "--mode", help="Suggestion mode: uncertainty, hard_negative, diversity, disagreement, or high_impact_unlabeled."),
    db_path: Optional[Path] = typer.Option(None, "--db"),
    limit: int = typer.Option(25, "--limit", min=1, max=500),
    random_seed: int = typer.Option(123, "--random-seed", help="Deterministic tie-ordering seed."),
    output_path: Optional[Path] = typer.Option(None, "--output", dir_okay=False, writable=True),
) -> None:
    try:
        report = suggest_classifier_labels(
            _db(db_path),
            classifier,
            mode=normalize_label_suggestion_mode(mode),
            limit=limit,
            random_seed=random_seed,
        )
        _emit_json_report(report, output_path)
    except (ValueError, sqlite3.IntegrityError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
