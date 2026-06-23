from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional, Sequence

import typer

from .analysis_config import (
    ANALYSIS_MODEL_ORDER,
    DEFAULT_ANALYSIS_DEVICE,
    DEFAULT_ANALYSIS_INFERENCE_BATCH_SIZE,
    DEFAULT_ANALYSIS_TOP_K,
    DEFAULT_ANALYSIS_TRACK_BATCH_SIZE,
    MAX_ANALYSIS_INFERENCE_BATCH_SIZE,
    MAX_ANALYSIS_TOP_K,
    MAX_ANALYSIS_TRACK_BATCH_SIZE,
    MIN_ANALYSIS_INFERENCE_BATCH_SIZE,
    MIN_ANALYSIS_TOP_K,
    MIN_ANALYSIS_TRACK_BATCH_SIZE,
    build_analysis_job_config,
    normalize_analysis_device,
    parse_analysis_models_text,
)
from .analysis_jobs import AnalysisJobManager
from .classifier_scoring import analyze_classifier as run_classifier_analysis
from .database import LibraryDatabase
from .db_schema import CURRENT_SCHEMA_VERSION
from .dependencies import require_ffmpeg
from .embedding import ClapEmbeddingAdapter
from .evaluation.ablation import build_source_ablation_report
from .evaluation.calibration import build_calibration_report, calibration_record_config, calibration_record_metrics
from .evaluation.candidates import export_candidate_pools, write_candidate_pool_csv
from .evaluation.labels import load_pair_feedback_labels, load_transition_feedback_labels
from .evaluation.reports import build_search_evaluation_report
from .evaluation.score_profiles import (
    build_score_profile_application_report,
    build_score_profile_from_source_report,
    load_score_profile,
    save_score_profile,
)
from .evaluation.seed_sampling import export_seed_sample, write_seed_sample_csv
from .evaluation.source_profile import build_source_profile, load_seed_track_ids_from_csv
from .evaluation.weighted_candidates import build_weighted_candidate_pool, write_weighted_candidate_pool_csv
from .logging_config import configure_logging, set_analysis_diagnostics_enabled
from .runtime import get_torch_runtime_info, recommended_torch_index
from .scanner import scan_library
from .search import SearchFilters, SimilaritySearch


app = typer.Typer(help="Local dj-track-similarity utility.")
eval_app = typer.Typer(help="Build local evaluation diagnostics and optional manual-feedback reports.")
app.add_typer(eval_app, name="eval")
LOGGER = logging.getLogger(__name__)


def _db(path: Optional[Path]) -> LibraryDatabase:
    log_path = configure_logging()
    db_path = path or Path("dj-track-similarity.sqlite")
    LOGGER.info("CLI database opened db_path=%s log_path=%s", db_path, log_path)
    return LibraryDatabase(db_path)


def _evaluation_db(path: Optional[Path]) -> LibraryDatabase:
    try:
        db = _db(path)
        with db.connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    except RuntimeError as error:
        typer.secho(f"Evaluation commands require SQLite schema v{CURRENT_SCHEMA_VERSION}. {error}", err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    if version != CURRENT_SCHEMA_VERSION:
        typer.secho(f"Evaluation commands require SQLite schema v{CURRENT_SCHEMA_VERSION}; found v{version}.", err=True, fg=typer.colors.RED)
        raise typer.Exit(1)
    return db


def _write_json_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json_object(path: Path, description: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"{description} JSON is invalid: {error.msg}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{description} JSON must be an object")
    return payload


def _weighted_candidate_seed_track_ids(
    db: LibraryDatabase,
    *,
    seed_sample_path: Path | None,
    seed_track_ids: Sequence[int] | None,
    sample_count: int,
    random_seed: int,
) -> tuple[int, ...]:
    if seed_sample_path is not None and seed_track_ids:
        raise ValueError("Use either --seed-sample or --seed-track-id, not both")
    if seed_sample_path is not None:
        return load_seed_track_ids_from_csv(seed_sample_path)
    if seed_track_ids:
        return tuple(dict.fromkeys(seed_track_ids))
    sample = export_seed_sample(db, count=sample_count, random_seed=random_seed, require_complete_analysis=True)
    if not sample.rows:
        raise ValueError("No eligible seed tracks were found; provide --seed-track-id or --seed-sample, or check complete analysis coverage")
    return tuple(row.track_id for row in sample.rows)


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


def _parse_analysis_models(value: str) -> list[str]:
    try:
        return list(parse_analysis_models_text(value))
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


def _parse_analysis_device(value: str | None) -> str:
    try:
        return normalize_analysis_device(value)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error


@eval_app.command("export-candidates")
def export_evaluation_candidates(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    seed_track_ids: Optional[list[int]] = typer.Option(None, "--seed-track-id", help="Seed track ID. Repeat for multiple seeds."),
    sources: Optional[list[str]] = typer.Option(None, "--source", help="Candidate source: mert, sonara, or maest. Repeat for multiple sources."),
    per_source: int = typer.Option(10, "--per-source", min=1, help="Top candidates to request from each source."),
    random_seed: int = typer.Option(123, "--random-seed", help="Deterministic blind-order random seed."),
    record_session: bool = typer.Option(True, "--record-session/--no-record-session", help="Record evaluation search_sessions and result events."),
) -> None:
    try:
        result = export_candidate_pools(
            _evaluation_db(db_path),
            seed_track_ids=seed_track_ids or [],
            sources=sources,
            per_source=per_source,
            random_seed=random_seed,
            record_session=record_session,
        )
        if not result.rows:
            for warning in result.warnings:
                typer.secho(f"warning: {warning}", err=True, fg=typer.colors.YELLOW)
            raise ValueError("No candidate rows were exported; check seed IDs and analysis coverage")
        write_candidate_pool_csv(output_path, result.rows)
    except (KeyError, ValueError, sqlite3.IntegrityError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error

    for warning in result.warnings:
        typer.secho(f"warning: {warning}", err=True, fg=typer.colors.YELLOW)
    typer.echo(
        f"exported={len(result.rows)} seeds={len({row.seed_track_id for row in result.rows})} "
        f"output={output_path} sessions_recorded={len(result.session_ids)} warnings={len(result.warnings)}"
    )


@eval_app.command("export-weighted-candidates")
def export_evaluation_weighted_candidates(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    profile_path: Path = typer.Option(..., "--profile", exists=True, dir_okay=False, readable=True),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    seed_sample_path: Optional[Path] = typer.Option(None, "--seed-sample", exists=True, dir_okay=False, readable=True),
    seed_track_ids: Optional[list[int]] = typer.Option(None, "--seed-track-id", help="Seed track ID. Repeat for multiple seeds."),
    sample_count: int = typer.Option(50, "--sample-count", min=1, help="Seeds to sample internally when no seed IDs or seed sample are provided."),
    sources: Optional[list[str]] = typer.Option(None, "--source", help="Candidate source from the score profile. Repeat for multiple sources."),
    per_source: int = typer.Option(30, "--per-source", min=1, help="Top candidates to request from each source per seed."),
    random_seed: int = typer.Option(123, "--random-seed", help="Deterministic seed for internal seed sampling and tie ordering."),
    rrf_k: int = typer.Option(60, "--rrf-k", min=1, help="RRF smoothing constant for weighted source-rank fusion."),
    record_session: bool = typer.Option(True, "--record-session/--no-record-session", help="Record evaluation weighted candidate-pool sessions and result events."),
) -> None:
    try:
        db = _evaluation_db(db_path)
        profile = load_score_profile(profile_path)
        clean_seed_track_ids = _weighted_candidate_seed_track_ids(
            db,
            seed_sample_path=seed_sample_path,
            seed_track_ids=seed_track_ids,
            sample_count=sample_count,
            random_seed=random_seed,
        )
        result = build_weighted_candidate_pool(
            db,
            seed_track_ids=clean_seed_track_ids,
            profile=profile,
            sources=sources,
            per_source=per_source,
            random_seed=random_seed,
            record_session=record_session,
            rrf_k=rrf_k,
        )
        if not result.rows:
            for warning in result.warnings:
                typer.secho(f"warning: {warning}", err=True, fg=typer.colors.YELLOW)
            raise ValueError("No weighted candidate rows were exported; check seed IDs, profile sources, and analysis coverage")
        write_weighted_candidate_pool_csv(output_path, result.rows)
    except (KeyError, ValueError, sqlite3.IntegrityError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error

    for warning in result.warnings:
        typer.secho(f"warning: {warning}", err=True, fg=typer.colors.YELLOW)
    typer.echo(
        f"exported={len(result.rows)} seeds={len(result.seed_track_ids)} output={output_path} "
        f"profile={result.score_profile_name} sources={','.join(result.sources)} "
        f"sessions_recorded={len(result.session_ids)} warnings={len(result.warnings)}"
    )


@eval_app.command("export-seed-sample")
def export_evaluation_seed_sample(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    count: int = typer.Option(50, "--count", min=1, help="Maximum seed tracks to export."),
    random_seed: int = typer.Option(123, "--random-seed", help="Deterministic sample seed."),
    require_complete_analysis: bool = typer.Option(
        True,
        "--require-complete-analysis/--allow-partial-analysis",
        help="Require SONARA, MERT, CLAP, and MAEST coverage before sampling.",
    ),
) -> None:
    try:
        result = export_seed_sample(
            _evaluation_db(db_path),
            count=count,
            random_seed=random_seed,
            require_complete_analysis=require_complete_analysis,
        )
        if not result.rows:
            raise ValueError("No eligible seed tracks were found; check analysis coverage or use --allow-partial-analysis")
        write_seed_sample_csv(output_path, result.rows)
    except ValueError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error

    typer.echo(
        f"eligible_count={result.eligible_count} selected_count={result.selected_count} "
        f"bucket_mode={result.bucket_mode} buckets_used={len(result.buckets_used)} "
        f"buckets={','.join(result.buckets_used)} output={output_path}"
    )


@eval_app.command("import-pair-feedback")
def import_pair_feedback(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False, readable=True),
) -> None:
    try:
        labels = load_pair_feedback_labels(input_path)
        db = _evaluation_db(db_path)
        for label in labels:
            db.upsert_track_pair_feedback(
                label.seed_track_id,
                label.candidate_track_id,
                label.rating,
                reason_tags=label.reason_tags,
                notes=label.notes,
                source=label.source,
            )
    except (ValueError, sqlite3.IntegrityError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    typer.echo(f"imported={len(labels)} upserted={len(labels)}")


@eval_app.command("import-transition-feedback")
def import_transition_feedback(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False, readable=True),
) -> None:
    try:
        labels = load_transition_feedback_labels(input_path)
        db = _evaluation_db(db_path)
        for label in labels:
            db.add_transition_feedback(
                label.outgoing_track_id,
                label.incoming_track_id,
                label.rating,
                risk_tags=label.risk_tags,
                notes=label.notes,
                source=label.source,
            )
    except (ValueError, sqlite3.IntegrityError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    typer.echo(f"imported={len(labels)} inserted={len(labels)} upserted=0")


@eval_app.command("report")
def evaluation_report(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    k: Optional[list[int]] = typer.Option(None, "--k", min=1, help="Metric cutoff. Repeat for multiple values."),
) -> None:
    try:
        report = build_search_evaluation_report(_evaluation_db(db_path), k_values=k or [5, 10])
        _write_json_report(output_path, report)
    except ValueError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    counts = report["counts"]
    typer.echo(
        f"status={report['status']} output={output_path} sessions_total={counts['sessions_total']} "
        f"sessions_with_labels={counts['sessions_with_labels']} judged_results={counts['judged_results']}"
    )


@eval_app.command("run-ablation")
def evaluation_run_ablation(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    k: Optional[list[int]] = typer.Option(None, "--k", min=1, help="Metric cutoff. Repeat for multiple values."),
    rrf_k: int = typer.Option(60, "--rrf-k", min=1, help="RRF smoothing constant for source-rank fusion."),
    score_profile_path: Optional[Path] = typer.Option(None, "--score-profile", exists=True, dir_okay=False, readable=True, help="Optional score profile JSON for weighted RRF diagnostics."),
) -> None:
    try:
        score_profile = load_score_profile(score_profile_path) if score_profile_path is not None else None
        report = build_source_ablation_report(_evaluation_db(db_path), k_values=k or [5, 10], rrf_k=rrf_k, score_profile=score_profile)
        _write_json_report(output_path, report)
    except ValueError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    counts = report["counts"]
    typer.echo(
        f"status={report['status']} output={output_path} sessions_total={counts['sessions_total']} "
        f"sessions_with_labels={counts['sessions_with_labels']} judged_results={counts['judged_results']} "
        f"sources_seen={','.join(counts['sources_seen'])}"
    )


@eval_app.command("build-score-profile")
def evaluation_build_score_profile(
    source_profile_report_path: Path = typer.Option(..., "--source-profile-report", exists=True, dir_okay=False, readable=True),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    name: str = typer.Option(..., "--name", help="Score profile artifact name."),
    rrf_k: int = typer.Option(60, "--rrf-k", min=1, help="RRF smoothing constant for weighted RRF."),
) -> None:
    try:
        source_report = _load_json_object(source_profile_report_path, "Source profile report")
        _ = rrf_k
        score_profile = build_score_profile_from_source_report(source_report, name=name)
        save_score_profile(score_profile, output_path)
    except ValueError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error

    weights_text = ",".join(f"{source}={float(weight):.4f}" for source, weight in sorted(score_profile.weights.items()))
    typer.echo(f"profile={score_profile.name} output={output_path} weight_kind={score_profile.weight_kind} weights={weights_text}")


@eval_app.command("run-calibration")
def evaluation_run_calibration(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    score_mode: str = typer.Option("rrf", "--score-mode", help="Calibration score mode: rrf, rank-percentile, or event-total-score."),
    bins: int = typer.Option(10, "--bins", min=1, help="Number of reliability bins."),
    min_samples: int = typer.Option(30, "--min-samples", min=1, help="Minimum judged samples required for probability metrics."),
    accepted_threshold: int = typer.Option(2, "--accepted-threshold", min=0, max=3, help="Ratings at or above this value are accepted labels."),
    rrf_k: int = typer.Option(60, "--rrf-k", min=1, help="RRF smoothing constant for rrf score mode."),
    record: bool = typer.Option(False, "--record/--no-record", help="Record an ok calibration summary to calibration_runs."),
) -> None:
    try:
        db = _evaluation_db(db_path)
        report = build_calibration_report(
            db,
            score_mode=score_mode,
            bins=bins,
            min_samples=min_samples,
            accepted_threshold=accepted_threshold,
            rrf_k=rrf_k,
        )
        report["recorded"] = False
        if record and report["status"] == "ok":
            report["calibration_run_id"] = db.record_calibration_run(
                "manual_feedback",
                str(report["score_mode"]),
                calibration_record_config(report),
                calibration_record_metrics(report),
            )
            report["recorded"] = True
        elif record:
            report["record_note"] = "Calibration summaries are recorded only when status is ok."
        _write_json_report(output_path, report)
    except ValueError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    typer.echo(
        f"status={report['status']} calibration_status={report['calibration_status']} output={output_path} "
        f"score_mode={report['score_mode']} sample_count={report['sample_count']} "
        f"positive_count={report['positive_count']} recorded={report['recorded']}"
    )


@eval_app.command("profile-sources")
def evaluation_profile_sources(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    profile_output_path: Optional[Path] = typer.Option(None, "--profile-output", dir_okay=False, writable=True, help="Optional score profile JSON artifact to create from this report."),
    profile_name: str = typer.Option("auto-source-profile", "--profile-name", help="Score profile name when --profile-output is used."),
    seed_sample_path: Optional[Path] = typer.Option(None, "--seed-sample", exists=True, dir_okay=False, readable=True),
    sources: Optional[list[str]] = typer.Option(None, "--source", help="Candidate source: mert, maest, or sonara. Repeat for multiple sources."),
    sample_count: int = typer.Option(50, "--sample-count", min=1, help="Seed count to sample when --seed-sample is not provided."),
    per_source: int = typer.Option(30, "--per-source", min=1, help="Top candidates to request from each source per seed."),
    top_k: Optional[list[int]] = typer.Option(None, "--top-k", min=1, help="Agreement cutoff. Repeat for multiple values."),
    random_seed: int = typer.Option(123, "--random-seed", help="Deterministic seed for internal seed sampling."),
) -> None:
    try:
        db = _evaluation_db(db_path)
        seed_track_ids = load_seed_track_ids_from_csv(seed_sample_path) if seed_sample_path is not None else None
        report = build_source_profile(
            db,
            seed_track_ids=seed_track_ids,
            sample_count=sample_count,
            sources=sources,
            per_source=per_source,
            top_k_values=top_k,
            random_seed=random_seed,
        )
        _write_json_report(output_path, report)
        score_profile = None
        if profile_output_path is not None:
            score_profile = build_score_profile_from_source_report(report, name=profile_name)
            save_score_profile(score_profile, profile_output_path)
    except (KeyError, ValueError, sqlite3.IntegrityError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error

    for warning in report["warnings"]:
        typer.secho(f"warning: {warning}", err=True, fg=typer.colors.YELLOW)
    weights = report["recommended_weights"]["weights"]
    weights_text = ",".join(f"{source}={float(weight):.4f}" for source, weight in sorted(weights.items()))
    typer.echo(
        f"status={report['status']} output={output_path} seed_count={report['seed_count']} "
        f"weight_kind={report['weight_kind']} weights={weights_text} warnings={len(report['warnings'])}"
    )
    if score_profile is not None:
        typer.echo(f"score_profile={score_profile.name} profile_output={profile_output_path}")


@eval_app.command("apply-score-profile")
def evaluation_apply_score_profile(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    profile_path: Path = typer.Option(..., "--profile", exists=True, dir_okay=False, readable=True),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    k: Optional[list[int]] = typer.Option(None, "--k", min=1, help="Metric cutoff. Repeat for multiple values."),
    rrf_k: int = typer.Option(60, "--rrf-k", min=1, help="RRF smoothing constant for weighted source-rank fusion."),
) -> None:
    try:
        profile = load_score_profile(profile_path)
        report = build_score_profile_application_report(_evaluation_db(db_path), profile, k_values=k or [5, 10], rrf_k=rrf_k)
        _write_json_report(output_path, report)
    except ValueError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error

    weights_text = ",".join(f"{source}={float(weight):.4f}" for source, weight in sorted(report["weights"].items()))
    typer.echo(
        f"status={report['status']} label_status={report['label_status']} output={output_path} "
        f"profile={report['profile_name']} ranked_sessions={report['ranked_session_count']} "
        f"judged_results={report['judged_results']} weights={weights_text}"
    )


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
    models: str = typer.Option(",".join(ANALYSIS_MODEL_ORDER), "--models", help="Comma-separated analysis models: sonara,maest,mert,clap."),
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
        help="MERT/CLAP/MAEST model inference batch size.",
    ),
    diagnostics: bool = typer.Option(False, "--diagnostics", help="Write decoder fallback and batch timing diagnostics to the file log."),
) -> None:
    set_analysis_diagnostics_enabled(diagnostics)
    try:
        config = build_analysis_job_config(
            models=_parse_analysis_models(models),
            limit=limit,
            device=device,
            top_k=top_k,
            track_batch_size=track_batch_size,
            inference_batch_size=inference_batch_size,
        )
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    manager = AnalysisJobManager(_db(db_path))
    job_id = manager.create_job(
        models=list(config.models),
        limit=config.limit,
        device=config.device,
        top_k=config.top_k,
        track_batch_size=config.track_batch_size,
        inference_batch_size=config.inference_batch_size,
    )
    status = _run_cli_job_with_progress(manager, job_id, label=",".join(config.models))
    typer.echo(
        f"state={status.state} total={status.total} processed={status.processed} "
        f"analyzed={status.analyzed} failed={status.failed} models={','.join(status.models)} "
        f"device={status.device} top_k={status.top_k} "
        f"track_batch_size={status.track_batch_size} inference_batch_size={status.inference_batch_size}"
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
    device: str = typer.Option(DEFAULT_ANALYSIS_DEVICE, "--device", help="CLAP device: auto, cpu, or cuda."),
) -> None:
    adapter = ClapEmbeddingAdapter(device=_parse_analysis_device(device))
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
