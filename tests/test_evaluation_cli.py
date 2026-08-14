from __future__ import annotations

import csv
from dataclasses import fields
import json
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

import dj_track_similarity.cli as cli
import dj_track_similarity.evaluation.judged as judged_module
import dj_track_similarity.evaluation.score_profile_optimizer as optimizer_module
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    MaestGenreScore,
    MaestWrite,
    SonaraWrite,
    current_embedding_spec,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_ddl import SonaraRow
from dj_track_similarity.track_models import (
    FileTags,
    ScannedFile,
    TrackIdentity,
)


_NOW = "2026-07-24T10:00:00.000000Z"


def test_eval_import_pair_feedback_cli_upserts_labels(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _add_cli_track(db, tmp_path, "seed")
    candidate_id = _add_cli_track(db, tmp_path, "candidate")
    input_path = tmp_path / "feedback.csv"
    input_path.write_text(
        "seed_track_id,candidate_track_id,rating,reason_tags,notes,source\n"
        f"{seed_id},{candidate_id},3,mixable,works,manual\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "import-pair-feedback",
            "--db",
            str(db_path),
            "--input",
            str(input_path),
        ],
    )

    assert result.exit_code == 0
    assert "imported=1 upserted=1" in result.output
    feedback = LibraryDatabase(db_path).get_pair_feedback_map()
    assert feedback[(seed_id, candidate_id, "manual")]["rating"] == 3


def test_eval_report_cli_writes_json_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "report.json"
    db = LibraryDatabase(db_path)
    seed_id = _add_cli_track(db, tmp_path, "seed")
    candidate_id = _add_cli_track(db, tmp_path, "candidate")
    _record_current_session(
        db,
        mode="mert",
        seed_id=seed_id,
        events=((candidate_id, 1, {"mert": {"score": 0.9}}),),
        request={"limit": 1},
    )
    db.upsert_track_pair_feedback(seed_id, candidate_id, 3)

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "report",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--k",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "status=ok" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["k_values"] == [1]
    assert report["counts"]["judged_results"] == 1


def test_eval_report_cli_judged_only_writes_label_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "report.json"
    db = LibraryDatabase(db_path)
    seed_id = _add_cli_track(db, tmp_path, "seed")
    candidate_id = _add_cli_track(db, tmp_path, "candidate")
    _record_current_session(
        db,
        mode="evaluation_candidate_pool",
        seed_id=seed_id,
        events=((candidate_id, 1, {"mert": {"score": 0.9}}),),
        request={"feedback_source": "manual"},
    )
    db.upsert_track_pair_feedback(seed_id, candidate_id, 3, source="manual")

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "report",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--k",
            "1",
            "--judged-only",
        ],
    )

    assert result.exit_code == 0
    assert "status=insufficient_data" in result.output
    assert "judged_pairs=1" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["evaluation_mode"] == "judged_validation"
    assert report["label_status"] == "insufficient_data"
    assert report["judged_pairs"] == 1


def test_eval_run_ablation_cli_writes_json_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "ablation.json"
    db = LibraryDatabase(db_path)
    seed_id = _add_cli_track(db, tmp_path, "seed")
    candidate_id = _add_cli_track(db, tmp_path, "candidate")
    _record_current_session(
        db,
        mode="evaluation_candidate_pool",
        seed_id=seed_id,
        events=(
            (
                candidate_id,
                1,
                {"mert": {"rank": 1}, "maest": {"rank": 2}},
            ),
        ),
        request={"feedback_source": "manual"},
    )
    db.upsert_track_pair_feedback(seed_id, candidate_id, 3)

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "run-ablation",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--k",
            "1",
            "--rrf-k",
            "60",
        ],
    )

    assert result.exit_code == 0
    assert "status=ok" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["k_values"] == [1]
    assert report["rrf_k"] == 60
    assert report["counts"]["judged_results"] == 1
    assert "fusion:rrf_all" in report["variants"]


def test_eval_build_score_profile_cli_writes_profile_artifact(tmp_path: Path) -> None:
    source_report_path = tmp_path / "source_profile.json"
    output_path = tmp_path / "score_profile.json"
    source_report_path.write_text(
        json.dumps(_source_profile_report({"mert": 0.75, "maest": 0.25})),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "build-score-profile",
            "--source-profile-report",
            str(source_report_path),
            "--output",
            str(output_path),
            "--name",
            "auto",
            "--rrf-k",
            "60",
        ],
    )

    assert result.exit_code == 0
    assert "profile=auto" in result.output
    profile = json.loads(output_path.read_text(encoding="utf-8"))
    assert profile["profile_kind"] == "unsupervised_source_profile"
    assert profile["weight_kind"] == "unsupervised_internal_profile"
    assert profile["weights"]["mert"] == 0.75
    assert profile["weights"]["maest"] == 0.25


def test_eval_run_ablation_cli_with_score_profile_includes_weighted_variant(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "ablation.json"
    score_profile_path = tmp_path / "score_profile.json"
    score_profile_path.write_text(
        json.dumps(
            {
                "name": "maest_auto",
                "profile_kind": "unsupervised_source_profile",
                "weight_kind": "unsupervised_internal_profile",
                "sources": ["mert", "maest"],
                "weights": {"mert": 0.1, "maest": 0.9},
                "created_at": "2026-06-23T00:00:00Z",
                "source_report_summary": {"status": "ok"},
                "limitations": [
                    "This is an unsupervised automatic internal score profile.",
                    "These weights are not probability or calibrated confidence.",
                    "This profile is not human ground truth.",
                ],
                "version": 1,
            },
        ),
        encoding="utf-8",
    )
    db = LibraryDatabase(db_path)
    seed_id = _add_cli_track(db, tmp_path, "seed")
    candidate_id = _add_cli_track(db, tmp_path, "candidate")
    _record_current_session(
        db,
        mode="evaluation_candidate_pool",
        seed_id=seed_id,
        events=(
            (
                candidate_id,
                1,
                {"mert": {"rank": 2}, "maest": {"rank": 1}},
            ),
        ),
        request={"feedback_source": "manual"},
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "run-ablation",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--k",
            "1",
            "--score-profile",
            str(score_profile_path),
        ],
    )

    assert result.exit_code == 0
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["score_profile"]["name"] == "maest_auto"
    assert "fusion:weighted_rrf:maest_auto" in report["variants"]


def test_eval_apply_score_profile_cli_reports_rankings_without_labels(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "apply.json"
    profile_path = tmp_path / "score_profile.json"
    db = LibraryDatabase(db_path)
    seed_id = _add_cli_track(db, tmp_path, "seed")
    candidate_a = _add_cli_track(db, tmp_path, "candidate_a")
    candidate_b = _add_cli_track(db, tmp_path, "candidate_b")
    _write_score_profile(profile_path, {"mert": 0.1, "maest": 0.9})
    _record_current_session(
        db,
        mode="evaluation_candidate_pool",
        seed_id=seed_id,
        events=(
            (
                candidate_a,
                1,
                {"mert": {"rank": 1}, "maest": {"rank": 20}},
            ),
            (candidate_b, 2, {"maest": {"rank": 1}}),
        ),
        request={"feedback_source": "manual"},
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "apply-score-profile",
            "--db",
            str(db_path),
            "--profile",
            str(profile_path),
            "--output",
            str(output_path),
            "--k",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "status=ok" in result.output
    assert "label_status=insufficient_data" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["label_status"] == "insufficient_data"
    assert "metrics" not in report
    assert report["ranked_sessions"][0]["ranked_candidate_track_ids"] == [
        candidate_b,
        candidate_a,
    ]


def test_eval_apply_score_profile_cli_includes_metrics_with_pair_feedback(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "apply.json"
    profile_path = tmp_path / "score_profile.json"
    db = LibraryDatabase(db_path)
    seed_id = _add_cli_track(db, tmp_path, "seed")
    candidate_a = _add_cli_track(db, tmp_path, "candidate_a")
    candidate_b = _add_cli_track(db, tmp_path, "candidate_b")
    _write_score_profile(profile_path, {"mert": 0.1, "maest": 0.9})
    _record_current_session(
        db,
        mode="evaluation_candidate_pool",
        seed_id=seed_id,
        events=(
            (
                candidate_a,
                1,
                {"mert": {"rank": 1}, "maest": {"rank": 20}},
            ),
            (candidate_b, 2, {"maest": {"rank": 1}}),
        ),
        request={"feedback_source": "manual"},
    )
    db.upsert_track_pair_feedback(seed_id, candidate_a, 0, source="manual")
    db.upsert_track_pair_feedback(seed_id, candidate_b, 3, source="manual")

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "apply-score-profile",
            "--db",
            str(db_path),
            "--profile",
            str(profile_path),
            "--output",
            str(output_path),
            "--k",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "label_status=insufficient_data" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["judged_results"] == 2
    assert report["label_status"] == "insufficient_data"
    assert report["metrics"]["mean_ndcg_at_1"] == 1.0
    assert report["metrics"]["mean_precision_at_1"] == 1.0


def test_eval_optimize_score_profile_cli_writes_report_without_recording_by_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "optimizer.json"
    _use_small_optimizer_policy(monkeypatch)
    _build_optimizer_cli_library(db_path, tmp_path, seed_count=2)
    before_counts = LibraryDatabase(db_path).count_evaluation_rows()

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "optimize-score-profile",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--grid-step",
            "0.5",
            "--bootstrap-samples",
            "0",
            "--min-judged-pairs",
            "4",
            "--no-record",
        ],
    )

    assert result.exit_code == 0
    assert "status=ok" in result.output
    assert "recorded=False" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["source"] == "judged_feedback"
    assert report["weights"]["mert"] > report["weights"]["maest"]
    assert LibraryDatabase(db_path).count_evaluation_rows() == before_counts
    assert (
        LibraryDatabase(db_path).get_evaluation_profile(
            "weighted_candidates_judged_v1"
        )
        is None
    )


def test_eval_optimize_score_profile_cli_record_writes_only_calibration_run(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "optimizer.json"
    _use_small_optimizer_policy(monkeypatch)
    _build_optimizer_cli_library(db_path, tmp_path, seed_count=2)
    before_counts = LibraryDatabase(db_path).count_evaluation_rows()

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "optimize-score-profile",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--grid-step",
            "0.5",
            "--bootstrap-samples",
            "0",
            "--min-judged-pairs",
            "4",
            "--record",
        ],
    )

    assert result.exit_code == 0
    assert "recorded=True" in result.output
    after_counts = LibraryDatabase(db_path).count_evaluation_rows()
    assert after_counts["calibration_runs"] == before_counts["calibration_runs"] + 1
    assert after_counts["search_sessions"] == before_counts["search_sessions"]
    assert after_counts["search_result_events"] == before_counts["search_result_events"]
    assert after_counts["pair_feedback"] == before_counts["pair_feedback"]
    assert (
        LibraryDatabase(db_path).get_evaluation_profile(
            "weighted_candidates_judged_v1"
        )
        is None
    )
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["recorded"] is True
    connection = LibraryDatabase(db_path).connect_evaluation(create=False)
    assert connection is not None
    with connection:
        row = connection.execute(
            "SELECT profile_name, search_mode, metrics_json FROM calibration_runs"
        ).fetchone()
    assert row["profile_name"] == "weighted_candidates_judged_v1"
    assert row["search_mode"] == "score_profile_optimizer"
    assert json.loads(row["metrics_json"])["status"] == "ok"


def test_eval_optimize_score_profile_cli_save_profile_appends_evaluation_profile(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "optimizer.json"
    _use_small_optimizer_policy(monkeypatch)
    _build_optimizer_cli_library(db_path, tmp_path, seed_count=4)
    before_counts = LibraryDatabase(db_path).count_evaluation_rows()

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "optimize-score-profile",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--grid-step",
            "0.5",
            "--bootstrap-samples",
            "0",
            "--min-judged-pairs",
            "4",
            "--save-profile",
        ],
    )

    assert result.exit_code == 0
    assert "saved_profile=True" in result.output
    after_counts = LibraryDatabase(db_path).count_evaluation_rows()
    assert after_counts["evaluation_profiles"] == before_counts["evaluation_profiles"] + 1
    for table, before_count in before_counts.items():
        if table != "evaluation_profiles":
            assert after_counts[table] == before_count
    saved_profile = LibraryDatabase(db_path).get_evaluation_profile(
        "weighted_candidates_judged_v1"
    )
    assert saved_profile is not None
    assert saved_profile["profile_name"] == "weighted_candidates_judged_v1"
    payload = saved_profile["profile"]
    assert payload["source"] == "judged_feedback"
    assert payload["profile_source"] == "score_profile_optimizer"
    assert payload["can_apply_as_default"] is True
    assert payload["judged_pairs"] == 8
    assert payload["weights"]["mert"] > payload["weights"]["maest"]
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["saved_profile"] is True
    assert report["evaluation_profile_id"] == saved_profile["profile_id"]


def test_eval_optimize_score_profile_cli_save_profile_requires_review_gate(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "optimizer.json"
    _use_small_optimizer_policy(monkeypatch)
    _build_optimizer_cli_library(db_path, tmp_path, seed_count=2)

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "optimize-score-profile",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--grid-step",
            "0.5",
            "--bootstrap-samples",
            "0",
            "--min-judged-pairs",
            "4",
            "--save-profile",
        ],
    )

    assert result.exit_code == 1
    assert "Cannot save score profile until the 500 matched judged-pair" in result.output
    assert (
        LibraryDatabase(db_path).get_evaluation_profile(
            "weighted_candidates_judged_v1"
        )
        is None
    )
    assert not output_path.exists()


def test_eval_sweep_risk_penalty_cli_writes_json_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "risk_sweep.json"
    profile_path = tmp_path / "score_profile.json"
    db = LibraryDatabase(db_path)
    seed_id = _add_cli_track(db, tmp_path, "seed")
    risky_id = _add_cli_track(db, tmp_path, "risky")
    safe_id = _add_cli_track(db, tmp_path, "safe")
    _write_score_profile(profile_path, {"mert": 1.0})
    _record_current_session(
        db,
        mode="evaluation_weighted_candidate_pool",
        seed_id=seed_id,
        events=(
            (
                risky_id,
                1,
                {"mert": {"rank": 1}},
                {
                    "transition_risk": 1.0,
                    "transition_risk_version": "v2",
                },
            ),
            (
                safe_id,
                2,
                {"mert": {"rank": 2}},
                {
                    "transition_risk": 0.0,
                    "transition_risk_version": "v2",
                },
            ),
        ),
        request={"feedback_source": "manual", "sources": ["mert"]},
    )
    db.upsert_track_pair_feedback(seed_id, safe_id, 3, source="manual")

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "sweep-risk-penalty",
            "--db",
            str(db_path),
            "--profile",
            str(profile_path),
            "--output",
            str(output_path),
            "--weight",
            "0",
            "--weight",
            "1",
            "--k",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert "label_status=insufficient_data" in result.output
    assert "best_mean_precision_at_1_weight=1" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert (
        report["best_by_metric"]["mean_precision_at_1"]["transition_risk_weight"] == 1.0
    )
    assert report["variants"]["transition_risk_weight:1"]["ranked_sessions"][0][
        "ranked_candidate_track_ids"
    ] == [safe_id, risky_id]


def test_eval_sweep_risk_penalty_cli_rejects_invalid_weight(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "risk_sweep.json"
    profile_path = tmp_path / "score_profile.json"
    LibraryDatabase(db_path)
    _write_score_profile(profile_path, {"mert": 1.0})

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "sweep-risk-penalty",
            "--db",
            str(db_path),
            "--profile",
            str(profile_path),
            "--output",
            str(output_path),
            "--weight",
            "1.5",
        ],
    )

    assert result.exit_code == 1
    assert "weight must be between 0 and 1" in result.output


def test_eval_profile_sources_cli_writes_score_profile_output(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "source_profile.json"
    profile_path = tmp_path / "score_profile.json"
    seed_sample_path = tmp_path / "seed_sample.csv"
    seed_id, _candidate_ids = _build_candidate_export_library(db_path, tmp_path)
    seed_sample_path.write_text(f"track_id\n{seed_id}\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "profile-sources",
            "--db",
            str(db_path),
            "--seed-sample",
            str(seed_sample_path),
            "--output",
            str(output_path),
            "--profile-output",
            str(profile_path),
            "--profile-name",
            "auto-test",
            "--source",
            "mert",
            "--per-source",
            "2",
        ],
    )

    assert result.exit_code == 0
    assert "score_profile=auto-test" in result.output
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["name"] == "auto-test"
    assert profile["weights"] == {"mert": 1.0}


def test_eval_export_candidates_cli_writes_csv_without_recording_sessions(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "candidates.csv"
    seed_id, candidate_ids = _build_candidate_export_library(db_path, tmp_path)

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "export-candidates",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--seed-track-id",
            str(seed_id),
            "--source",
            "mert",
            "--per-source",
            "2",
            "--random-seed",
            "123",
            "--no-record-session",
        ],
    )

    assert result.exit_code == 0
    assert "exported=2" in result.output
    rows = _read_csv_rows(output_path)
    assert {int(row["candidate_track_id"]) for row in rows} == set(candidate_ids[:2])
    assert all(int(row["candidate_track_id"]) != seed_id for row in rows)
    assert all(row["rating"] == "" for row in rows)
    assert all(row["source"] == "manual" for row in rows)
    assert LibraryDatabase(db_path).count_evaluation_rows()["search_sessions"] == 0


def test_eval_export_candidates_cli_records_sessions_and_events(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "candidates.csv"
    seed_id, candidate_ids = _build_candidate_export_library(db_path, tmp_path)

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "export-candidates",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--seed-track-id",
            str(seed_id),
            "--source",
            "mert",
            "--source",
            "sonara",
            "--per-source",
            "2",
            "--random-seed",
            "321",
            "--record-session",
        ],
    )

    assert result.exit_code == 0
    assert "sessions_recorded=1" in result.output
    db = LibraryDatabase(db_path)
    counts = db.count_evaluation_rows()
    sessions = db.list_search_sessions_with_events()
    assert counts["search_sessions"] == 1
    assert counts["search_result_events"] == len(_read_csv_rows(output_path))
    assert sessions[0]["mode"] == "evaluation_candidate_pool"
    assert sessions[0]["seed_track_ids"] == [seed_id]
    assert sessions[0]["request"]["sources"] == ["mert", "sonara"]
    assert sessions[0]["request"]["feedback_source"] == "manual"
    assert {event["track_id"] for event in sessions[0]["events"]}.issubset(
        set(candidate_ids)
    )
    assert all(
        "blind_rank" in event["score_breakdown"] for event in sessions[0]["events"]
    )


def test_eval_export_weighted_candidates_cli_writes_csv_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "weighted_candidates.csv"
    profile_path = tmp_path / "score_profile.json"
    seed_id, candidate_ids = _build_candidate_export_library(db_path, tmp_path)
    _write_score_profile(profile_path, {"mert": 1.0})

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "export-weighted-candidates",
            "--db",
            str(db_path),
            "--profile",
            str(profile_path),
            "--output",
            str(output_path),
            "--seed-track-id",
            str(seed_id),
            "--per-source",
            "2",
            "--random-seed",
            "123",
            "--no-record-session",
        ],
    )

    assert result.exit_code == 0
    assert "profile=auto" in result.output
    assert "exported=2" in result.output
    rows = _read_csv_rows(output_path)
    assert {int(row["candidate_track_id"]) for row in rows} == set(candidate_ids[:2])
    assert rows[0]["profile_rank"] == "1"
    assert rows[0]["rating"] == ""
    assert rows[0]["source"] == "manual"
    assert set(rows[0]) == {
        "seed_track_id",
        "candidate_track_id",
        "profile_rank",
        "profile_score",
        "adjusted_score",
        "raw_rrf_score",
        "transition_risk",
        "transition_risk_penalty",
        "transition_risk_weight",
        "rating",
        "reason_tags",
        "notes",
        "source",
        "seed_artist",
        "seed_title",
        "candidate_artist",
        "candidate_title",
        "candidate_album",
        "candidate_bpm",
        "candidate_musical_key",
        "candidate_energy",
        "source_count",
        "sources_json",
        "score_profile_name",
        "score_profile_weights_json",
    }
    assert LibraryDatabase(db_path).count_evaluation_rows()["search_sessions"] == 0


def test_eval_export_seed_sample_cli_writes_csv(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "seed_sample.csv"
    db = LibraryDatabase(db_path)
    track_ids = [
        _upsert_cli_candidate_track(db, tmp_path, "seed_a", bpm=120.0, energy=0.3),
        _upsert_cli_candidate_track(db, tmp_path, "seed_b", bpm=128.0, energy=0.7),
        _upsert_cli_candidate_track(db, tmp_path, "seed_c", bpm=136.0, energy=0.5),
    ]
    for track_id in track_ids:
        _save_cli_seed_sample_analysis(db, track_id)

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "export-seed-sample",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--count",
            "2",
            "--random-seed",
            "123",
        ],
    )

    assert result.exit_code == 0
    assert "eligible_count=3" in result.output
    assert "selected_count=2" in result.output
    rows = _read_csv_rows(output_path)
    assert len(rows) == 2
    assert set(rows[0]) == {
        "track_id",
        "artist",
        "title",
        "album",
        "bpm",
        "musical_key",
        "energy",
            "sonara_core",
            "mert_embedding",
            "muq_embedding",
            "mulan_embedding",
            "clap_embedding",
        "maest_analysis",
        "maest_embedding",
        "bucket",
    }
    assert {int(row["track_id"]) for row in rows}.issubset(set(track_ids))


def _build_candidate_export_library(
    db_path: Path, tmp_path: Path
) -> tuple[int, list[int]]:
    db = LibraryDatabase(db_path)
    seed_id = _upsert_cli_candidate_track(db, tmp_path, "seed", bpm=120.0, energy=0.5)
    candidate_a = _upsert_cli_candidate_track(
        db, tmp_path, "candidate_a", bpm=121.0, energy=0.55
    )
    candidate_b = _upsert_cli_candidate_track(
        db, tmp_path, "candidate_b", bpm=122.0, energy=0.6
    )
    candidate_c = _upsert_cli_candidate_track(
        db, tmp_path, "candidate_c", bpm=130.0, energy=0.9
    )

    _save_cli_candidate_analysis(
        db, seed_id, embedding=[1.0, 0.0], bpm=120.0, energy=0.5, danceability=0.7
    )
    _save_cli_candidate_analysis(
        db,
        candidate_a,
        embedding=[0.99, 0.1],
        bpm=121.0,
        energy=0.55,
        danceability=0.72,
    )
    _save_cli_candidate_analysis(
        db, candidate_b, embedding=[0.8, 0.2], bpm=122.0, energy=0.6, danceability=0.75
    )
    _save_cli_candidate_analysis(
        db, candidate_c, embedding=[0.0, 1.0], bpm=130.0, energy=0.9, danceability=0.3
    )
    return seed_id, [candidate_a, candidate_b, candidate_c]


def _build_optimizer_cli_library(
    db_path: Path, tmp_path: Path, *, seed_count: int
) -> None:
    db = LibraryDatabase(db_path)
    source_outputs = _register_evaluation_source_outputs(
        db,
        ("mert", "maest"),
    )
    for index in range(seed_count):
        seed_id = _add_cli_track(
            db,
            tmp_path,
            f"optimizer_seed_{index}",
        )
        bad_id = _add_cli_track(
            db,
            tmp_path,
            f"optimizer_bad_{index}",
        )
        good_id = _add_cli_track(
            db,
            tmp_path,
            f"optimizer_good_{index}",
        )
        _record_current_session(
            db,
            mode="evaluation_candidate_pool",
            seed_id=seed_id,
            events=(
                (
                    bad_id,
                    1,
                    {"mert": {"rank": 10}, "maest": {"rank": 1}},
                ),
                (
                    good_id,
                    2,
                    {"mert": {"rank": 1}, "maest": {"rank": 10}},
                ),
            ),
            request={"feedback_source": "manual"},
            source_outputs=source_outputs,
        )
        db.upsert_track_pair_feedback(seed_id, bad_id, 0, source="manual")
        db.upsert_track_pair_feedback(seed_id, good_id, 3, source="manual")


def _use_small_optimizer_policy(monkeypatch) -> None:
    monkeypatch.setattr(judged_module, "INSUFFICIENT_JUDGED_PAIRS", 2)
    for module in (judged_module, optimizer_module):
        monkeypatch.setattr(module, "CANDIDATE_PROFILE_JUDGED_PAIRS", 4)
        monkeypatch.setattr(module, "DEFAULT_UPDATE_JUDGED_PAIRS", 8)


def _upsert_cli_candidate_track(
    db: LibraryDatabase, tmp_path: Path, stem: str, *, bpm: float, energy: float
) -> int:
    del energy
    return db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / f"{stem}.wav"),
            file_size_bytes=10,
            file_modified_ns=1,
        ),
        tags=FileTags(
            artist=f"Artist {stem}",
            title=stem.replace("_", " ").title(),
            tag_bpm=bpm,
            tag_key="1A",
        ),
        scanned_at=_NOW,
    ).identity.track_id


def _save_cli_candidate_analysis(
    db: LibraryDatabase,
    track_id: int,
    *,
    embedding: list[float],
    bpm: float,
    energy: float,
    danceability: float,
) -> None:
    identity = _required_identity(db, track_id)
    target = _target(identity)
    mert = current_embedding_analysis_output("mert")
    db.register_analysis_outputs(
        (
            mert,
            AnalysisOutput("sonara", "core"),
        )
    )
    embedding_result = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family="mert",
                    vector=_expanded_unit_vector(
                        current_embedding_spec("mert").dimension,
                        embedding,
                    ),
                    analyzed_at=_NOW,
                ),
            ),
        )
    )
    assert embedding_result[0].ok
    sonara_result = db.save_sonara_results(
        (
            SonaraWrite(
                target=target,
                core=_sonara_row(
                    target,
                    bpm=bpm,
                    energy=energy,
                    danceability=danceability,
                ),
            ),
        )
    )
    assert sonara_result[0].ok


def _save_cli_seed_sample_analysis(db: LibraryDatabase, track_id: int) -> None:
    vector = [1.0, float(track_id)]
    _save_cli_candidate_analysis(
        db,
        track_id,
        embedding=vector,
        bpm=120.0,
        energy=0.5,
        danceability=0.7,
    )
    identity = _required_identity(db, track_id)
    target = _target(identity)
    muq = current_embedding_analysis_output("muq")
    clap = current_embedding_analysis_output("clap")
    maest_analysis, maest_embedding = _maest_outputs()
    db.register_analysis_outputs((muq, clap, maest_analysis, maest_embedding))
    embedding_results = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family="muq",
                    vector=_expanded_unit_vector(
                        current_embedding_spec("muq").dimension,
                        vector,
                    ),
                    analyzed_at=_NOW,
                ),
            ),
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family="clap",
                    vector=_expanded_unit_vector(
                        current_embedding_spec("clap").dimension,
                        vector,
                    ),
                    analyzed_at=_NOW,
                ),
            ),
        )
    )
    assert all(result.ok for result in embedding_results)
    maest_result = db.save_maest_results(
        (
            MaestWrite(
                target=target,
                genres=(MaestGenreScore(label="Techno", score=0.9),),
                syncopated_rhythm=None,
                analyzed_at=_NOW,
                embedding=EmbeddingOutput(
                    family="maest",
                    vector=_expanded_unit_vector(
                        current_embedding_spec("maest").dimension,
                        vector,
                    ),
                    analyzed_at=_NOW,
                ),
            ),
        )
    )
    assert maest_result[0].ok


def _add_cli_track(
    db: LibraryDatabase,
    tmp_path: Path,
    stem: str,
) -> int:
    return db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / f"{stem}.wav"),
            file_size_bytes=10,
            file_modified_ns=1,
        ),
        tags=FileTags(title=stem.replace("_", " ").title()),
        scanned_at=_NOW,
    ).identity.track_id


def _required_identity(
    db: LibraryDatabase,
    track_id: int,
) -> TrackIdentity:
    identity = db.get_track_identity(track_id)
    assert identity is not None
    return identity


def _target(identity: TrackIdentity) -> AnalysisTarget:
    return AnalysisTarget(
        catalog_uuid=identity.catalog_uuid,
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
    )


def _identity_payload(identity: TrackIdentity) -> dict[str, object]:
    return {
        "catalog_uuid": identity.catalog_uuid,
        "track_id": identity.track_id,
        "track_uuid": identity.track_uuid,
    }


def _record_current_session(
    db: LibraryDatabase,
    *,
    mode: str,
    seed_id: int,
    events: tuple[tuple[object, ...], ...],
    request: dict[str, object],
    source_outputs: dict[str, AnalysisOutput] | None = None,
) -> int:
    sources = tuple(
        dict.fromkeys(
            str(source) for event in events for source in dict(event[2]).keys()
        )
    )
    if source_outputs is None:
        _register_evaluation_source_outputs(db, sources)
    else:
        db.register_analysis_outputs(tuple(source_outputs.values()))
    seed_identity = _required_identity(db, seed_id)
    session_request = {
        **request,
        "catalog_uuid": db.catalog_uuid,
        "seed_identities": [_identity_payload(seed_identity)],
        "sources": list(sources),
    }
    session_id = db.create_search_session(
        mode,
        [seed_id],
        session_request,
    )
    for event in events:
        candidate_id = int(event[0])
        rank = int(event[1])
        raw_sources = dict(event[2])
        extra = dict(event[3]) if len(event) == 4 else {}
        candidate_identity = _required_identity(db, candidate_id)
        source_contributions = {
            source: dict(contribution)
            for source, contribution in raw_sources.items()
        }
        db.record_search_result_event(
            session_id,
            candidate_id,
            rank=rank,
            total_score=0.0,
            score_breakdown={
                **extra,
                "candidate_identity": _identity_payload(candidate_identity),
                "sources": source_contributions,
            },
        )
    return session_id


def _register_evaluation_source_outputs(
    db: LibraryDatabase,
    sources: tuple[str, ...],
) -> dict[str, AnalysisOutput]:
    outputs: dict[str, AnalysisOutput] = {}
    for source in sources:
        if source == "mert":
            outputs[source] = current_embedding_analysis_output("mert")
        elif source == "maest":
            outputs[source] = _maest_outputs()[1]
        elif source == "muq":
            outputs[source] = current_embedding_analysis_output("muq")
        elif source == "clap":
            outputs[source] = current_embedding_analysis_output("clap")
        else:
            raise AssertionError(f"unsupported test source: {source}")
    db.register_analysis_outputs(tuple(outputs.values()))
    return outputs


def _maest_outputs() -> tuple[AnalysisOutput, AnalysisOutput]:
    return AnalysisOutput("maest", "analysis"), current_embedding_analysis_output(
        "maest"
    )


def _sonara_row(
    target: AnalysisTarget,
    *,
    bpm: float,
    energy: float,
    danceability: float,
) -> SonaraRow:
    values = {field.name: None for field in fields(SonaraRow)}
    values.update(
        {
            "track_id": target.track_id,
            "detected_bpm": bpm,
            "detected_key_camelot": "1A",
            "key_confidence": 0.9,
            "energy_score": energy,
            "danceability_score": danceability,
            "valence_score": danceability,
            "acousticness_score": 1.0 - energy,
            "rms_mean": energy / 2.0,
            "onset_density_per_second": danceability * 2.0,
            "mfcc_mean_blob": bytes(13 * 4),
            "chroma_mean_blob": bytes(12 * 4),
            "spectral_contrast_mean_blob": bytes(7 * 4),
            "analyzed_at": _NOW,
        }
    )
    return SonaraRow(**values)


def _expanded_unit_vector(
    dim: int,
    values: list[float],
) -> np.ndarray:
    vector = np.zeros(dim, dtype=np.float32)
    source = np.asarray(values, dtype=np.float32)
    vector[: min(dim, source.size)] = source[:dim]
    norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
    assert norm > 0.0
    vector /= norm
    return vector


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _write_score_profile(path: Path, weights: dict[str, float]) -> None:
    path.write_text(
        json.dumps(
            {
                "name": "auto",
                "profile_kind": "unsupervised_source_profile",
                "weight_kind": "unsupervised_internal_profile",
                "sources": list(weights),
                "weights": weights,
                "created_at": "2026-06-23T00:00:00Z",
                "source_report_summary": {"status": "ok"},
                "limitations": [
                    "This is an unsupervised automatic internal score profile.",
                    "These weights are not probability or calibrated confidence.",
                    "This profile is not human ground truth.",
                ],
                "version": 1,
            },
        ),
        encoding="utf-8",
    )


def _source_profile_report(weights: dict[str, float]) -> dict[str, object]:
    return {
        "status": "ok",
        "profile_kind": "unsupervised_source_profile",
        "weight_kind": "unsupervised_internal_profile",
        "sources": list(weights),
        "seed_count": 1,
        "per_source": {},
        "consensus": {},
        "recommended_weights": {
            "weight_kind": "unsupervised_internal_profile",
            "weights": weights,
            "note": "test",
        },
        "warnings": [],
        "limitations": [],
    }
