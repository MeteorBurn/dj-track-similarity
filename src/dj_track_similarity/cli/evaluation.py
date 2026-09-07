from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Sequence

import typer

from ..database import LibraryDatabase
from ..evaluation.ablation import build_source_ablation_report
from ..evaluation.calibration import (
    build_calibration_report,
    calibration_record_config,
    calibration_record_metrics,
)
from ..evaluation.candidates import export_candidate_pools, write_candidate_pool_csv
from ..evaluation.labels import load_pair_feedback_labels, load_transition_feedback_labels
from ..evaluation.reports import build_search_evaluation_report
from ..evaluation.risk_sweep import build_risk_penalty_sweep_report
from ..evaluation.score_profile_optimizer import (
    build_saved_score_profile_payload,
    build_score_profile_optimizer_report,
    optimizer_record_config,
    optimizer_record_metrics,
)
from ..evaluation.score_profiles import (
    build_score_profile_application_report,
    build_score_profile_from_source_report,
    load_score_profile,
    save_score_profile,
)
from ..evaluation.seed_sampling import export_seed_sample, write_seed_sample_csv
from ..evaluation.source_profile import build_source_profile, load_seed_track_ids_from_csv
from ..evaluation.weighted_candidates import (
    build_weighted_candidate_pool,
    write_weighted_candidate_pool_csv,
)
from .common import _db, _load_json_object, _write_json_report


eval_app = typer.Typer(help="Build local evaluation diagnostics and optional manual-feedback reports.")


def _evaluation_db(path: Optional[Path]) -> LibraryDatabase:
    return _db(path)


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


@eval_app.command("export-candidates")
def export_evaluation_candidates(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    seed_track_ids: Optional[list[int]] = typer.Option(None, "--seed-track-id", help="Seed track ID. Repeat for multiple seeds."),
    sources: Optional[list[str]] = typer.Option(None, "--source", help="Candidate source: mert, maest, muq, mulan, sonara, or clap. Repeat for multiple sources."),
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
    transition_risk_weight: float = typer.Option(0.0, "--transition-risk-weight", min=0.0, max=1.0, help="Optional 0-1 diagnostic transition-risk penalty. Default keeps weighted RRF unchanged."),
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
            transition_risk_weight=transition_risk_weight,
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
        help="Require SONARA, MERT, MuQ, CLAP, and MAEST coverage before sampling.",
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
    judged_only: bool = typer.Option(False, "--judged-only", help="Evaluate only matched judged result labels and apply PR-23 label gates."),
) -> None:
    try:
        report = build_search_evaluation_report(_evaluation_db(db_path), k_values=k or [5, 10, 20], judged_only=judged_only)
        _write_json_report(output_path, report)
    except ValueError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    counts = report["counts"]
    typer.echo(
        f"status={report['status']} label_status={report['label_status']} output={output_path} "
        f"sessions_total={counts['sessions_total']} sessions_with_labels={counts['sessions_with_labels']} "
        f"judged_results={counts['judged_results']} judged_pairs={report['judged_pairs']}"
    )


@eval_app.command("run-ablation")
def evaluation_run_ablation(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    k: Optional[list[int]] = typer.Option(None, "--k", min=1, help="Metric cutoff. Repeat for multiple values."),
    rrf_k: int = typer.Option(60, "--rrf-k", min=1, help="RRF smoothing constant for source-rank fusion."),
    score_profile_path: Optional[Path] = typer.Option(None, "--score-profile", exists=True, dir_okay=False, readable=True, help="Optional score profile JSON for weighted RRF diagnostics."),
    judged_only: bool = typer.Option(False, "--judged-only", help="Compute ranking metrics only over matched judged results and apply PR-23 label gates."),
) -> None:
    try:
        score_profile = load_score_profile(score_profile_path) if score_profile_path is not None else None
        report = build_source_ablation_report(_evaluation_db(db_path), k_values=k or [5, 10, 20], rrf_k=rrf_k, score_profile=score_profile, judged_only=judged_only)
        _write_json_report(output_path, report)
    except ValueError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error
    counts = report["counts"]
    typer.echo(
        f"status={report['status']} label_status={report['label_status']} output={output_path} sessions_total={counts['sessions_total']} "
        f"sessions_with_labels={counts['sessions_with_labels']} judged_results={counts['judged_results']} "
        f"judged_pairs={report['judged_pairs']} sources_seen={','.join(counts['sources_seen'])} "
        f"classifier_adjusted_events={counts['classifier_adjusted_events']}"
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
    judged_only: bool = typer.Option(False, "--judged-only", help="Apply PR-23 matched judged-label gates before reporting calibration as ok."),
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
            judged_only=judged_only,
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
        f"status={report['status']} calibration_status={report['calibration_status']} label_status={report['label_status']} output={output_path} "
        f"score_mode={report['score_mode']} sample_count={report['sample_count']} "
        f"positive_count={report['positive_count']} judged_pairs={report['judged_pairs']} recorded={report['recorded']}"
    )


@eval_app.command("optimize-score-profile")
def evaluation_optimize_score_profile(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Optional[Path] = typer.Option(None, "--output", dir_okay=False, writable=True),
    profile_name: str = typer.Option("weighted_candidates_judged_v1", "--profile-name", help="Proposal profile name stored in the JSON report."),
    objective: str = typer.Option("balanced", "--objective", help="Optimization objective. MVP supports: balanced."),
    split_by: str = typer.Option("seed", "--split-by", help="Train/validation split strategy. MVP supports: seed."),
    min_judged_pairs: int = typer.Option(200, "--min-judged-pairs", min=1, help="Minimum matched judged pairs requested before proposing a profile."),
    rrf_k: int = typer.Option(60, "--rrf-k", min=1, help="RRF smoothing constant for source-rank fusion."),
    k: Optional[list[int]] = typer.Option(None, "--k", min=1, help="Metric cutoff. Repeat for multiple values; NDCG@10 guardrail is always included."),
    random_seed: int = typer.Option(123, "--random-seed", help="Deterministic seed for train/validation split and bootstrap."),
    grid_step: float = typer.Option(0.25, "--grid-step", min=0.01, max=1.0, help="Bounded source-weight grid step."),
    bootstrap_samples: int = typer.Option(30, "--bootstrap-samples", min=0, help="Deterministic validation bootstrap samples; 0 disables the stability check."),
    record: bool = typer.Option(False, "--record/--no-record", help="Record an ok diagnostic optimizer summary to calibration_runs."),
    save_profile: bool = typer.Option(
        False,
        "--save-profile/--no-save-profile",
        help="Save an ok 500+ judged-pair optimizer profile in optional Evaluation storage.",
    ),
) -> None:
    try:
        db = _evaluation_db(db_path)
        report = build_score_profile_optimizer_report(
            db,
            profile_name=profile_name,
            objective=objective,
            split_by=split_by,
            min_judged_pairs=min_judged_pairs,
            rrf_k=rrf_k,
            k_values=k or [10],
            random_seed=random_seed,
            grid_step=grid_step,
            bootstrap_samples=bootstrap_samples,
        )
        report["recorded"] = False
        report["saved_profile"] = False
        profile_payload = (
            build_saved_score_profile_payload(report) if save_profile else None
        )
        if record and report["status"] == "ok":
            report["calibration_run_id"] = db.record_calibration_run(
                str(report["profile_name"]),
                "score_profile_optimizer",
                optimizer_record_config(report),
                optimizer_record_metrics(report),
            )
            report["recorded"] = True
        elif record:
            report["record_note"] = "Optimizer summaries are recorded only when status is ok."
        if profile_payload is not None:
            report["evaluation_profile_id"] = db.save_evaluation_profile(
                str(report["profile_name"]),
                profile_payload,
            )
            report["saved_profile"] = True
        if output_path is not None:
            _write_json_report(output_path, report)
    except (ValueError, sqlite3.IntegrityError) as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error

    metric_cutoff = int(report["guardrails"]["metric_cutoff"])
    validation_metrics = report.get("validation_metrics", {})
    baseline_validation_metrics = report.get("baseline_validation_metrics", {})
    validation_ndcg = validation_metrics.get(f"ndcg_at_{metric_cutoff}", "n/a")
    baseline_ndcg = baseline_validation_metrics.get(f"ndcg_at_{metric_cutoff}", "n/a")
    weights = report.get("weights", {})
    weights_text = ",".join(f"{source}={float(weight):.4f}" for source, weight in sorted(weights.items())) if weights else "none"
    output_text = str(output_path) if output_path is not None else "not_written"
    typer.echo(
        f"status={report['status']} decision={report['decision']} label_status={report['label_status']} output={output_text} "
        f"judged_pairs={report['judged_pairs']} validation_ndcg_at_{metric_cutoff}={validation_ndcg} "
        f"baseline_validation_ndcg_at_{metric_cutoff}={baseline_ndcg} weights={weights_text} recorded={report['recorded']} saved_profile={report['saved_profile']}"
    )


@eval_app.command("profile-sources")
def evaluation_profile_sources(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    profile_output_path: Optional[Path] = typer.Option(None, "--profile-output", dir_okay=False, writable=True, help="Optional score profile JSON artifact to create from this report."),
    profile_name: str = typer.Option("auto-source-profile", "--profile-name", help="Score profile name when --profile-output is used."),
    seed_sample_path: Optional[Path] = typer.Option(None, "--seed-sample", exists=True, dir_okay=False, readable=True),
    sources: Optional[list[str]] = typer.Option(None, "--source", help="Candidate source: mert, maest, muq, mulan, sonara, or clap. Repeat for multiple sources."),
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
        report = build_score_profile_application_report(_evaluation_db(db_path), profile, k_values=k or [5, 10, 20], rrf_k=rrf_k)
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


@eval_app.command("sweep-risk-penalty")
def evaluation_sweep_risk_penalty(
    db_path: Optional[Path] = typer.Option(None, "--db"),
    profile_path: Path = typer.Option(..., "--profile", exists=True, dir_okay=False, readable=True),
    output_path: Path = typer.Option(..., "--output", dir_okay=False, writable=True),
    weights: Optional[list[float]] = typer.Option(None, "--weight", help="Transition-risk penalty weight from 0.0 to 1.0. Repeat for a sweep."),
    k: Optional[list[int]] = typer.Option(None, "--k", min=1, help="Metric/diagnostic cutoff. Repeat for multiple values."),
    rrf_k: int = typer.Option(60, "--rrf-k", min=1, help="RRF smoothing constant for weighted source-rank fusion."),
    transition_risk_version: str = typer.Option("v2", "--transition-risk-version", help="Transition-risk diagnostics version to sweep: v1 or v2."),
) -> None:
    try:
        profile = load_score_profile(profile_path)
        report = build_risk_penalty_sweep_report(
            _evaluation_db(db_path),
            profile,
            weights=weights,
            k_values=k or [5, 10, 20],
            rrf_k=rrf_k,
            risk_version=transition_risk_version,
        )
        _write_json_report(output_path, report)
    except ValueError as error:
        typer.secho(str(error), err=True, fg=typer.colors.RED)
        raise typer.Exit(1) from error

    counts = report["counts"]
    best_text = ""
    if "best_by_metric" in report:
        precision_metric = f"mean_precision_at_{report['k_values'][0]}"
        best = report["best_by_metric"].get(precision_metric)
        if best is not None:
            best_text = f" best_{precision_metric}_weight={best['transition_risk_weight']:g}"
    typer.echo(
        f"status={report['status']} label_status={report['label_status']} output={output_path} "
        f"profile={report['profile_name']} ranked_sessions={counts['ranked_session_count']} "
        f"judged_results={counts['judged_results']} weights={','.join(str(weight) for weight in report['risk_weights'])}"
        f" risk_version={report['risk_version']}"
        f"{best_text}"
    )
