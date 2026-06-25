from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import dj_track_similarity.cli as cli
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.calibration import (
    brier_score,
    build_calibration_report,
    expected_calibration_error,
    reliability_bins,
    score_quantiles,
    threshold_table,
)


def test_calibration_probability_metrics_match_known_values() -> None:
    probabilities = [0.1, 0.4, 0.8]
    labels = [0, 1, 1]

    bins = reliability_bins(probabilities, labels, bins=2)

    assert brier_score(probabilities, labels) == pytest.approx((0.01 + 0.36 + 0.04) / 3)
    assert bins == [
        {"lower": 0.0, "upper": 0.5, "count": 2, "avg_score": 0.25, "positive_rate": 0.5, "gap": 0.25},
        {"lower": 0.5, "upper": 1.0, "count": 1, "avg_score": 0.8, "positive_rate": 1.0, "gap": 0.19999999999999996},
    ]
    assert expected_calibration_error(probabilities, labels, bins=2) == pytest.approx((2 / 3 * 0.25) + (1 / 3 * 0.2))
    assert threshold_table(probabilities, labels, thresholds=[0.5])[0] == {
        "threshold": 0.5,
        "count": 1,
        "positive_count": 1,
        "precision": 1.0,
        "recall": 0.5,
    }
    assert score_quantiles([4.0, 1.0, 2.0], quantiles=[0, 0.5, 1]) == [
        {"quantile": 0.0, "value": 1.0},
        {"quantile": 0.5, "value": 2.0},
        {"quantile": 1.0, "value": 4.0},
    ]


def test_probability_metrics_reject_out_of_range_or_non_finite_values() -> None:
    with pytest.raises(ValueError, match=r"predicted probability must be in \[0, 1\]"):
        brier_score([1.2], [1])

    with pytest.raises(ValueError, match="predicted probability must be finite"):
        expected_calibration_error([float("nan")], [0])

    with pytest.raises(ValueError, match="Labels must be 0 or 1"):
        brier_score([0.5], [2])


def test_calibration_report_returns_insufficient_data_but_keeps_counts_and_quantiles(tmp_path: Path) -> None:
    db, _track_ids = _calibration_library(tmp_path)

    report = build_calibration_report(db, score_mode="rank-percentile", bins=2, min_samples=30, accepted_threshold=2)

    assert report["status"] == "insufficient_data"
    assert report["calibration_status"] == "insufficient_data"
    assert report["sample_count"] == 2
    assert report["positive_count"] == 1
    assert report["brier_score"] is None
    assert report["score_quantiles"]
    assert report["reliability_bins"][0]["count"] == 1


def test_rank_percentile_and_rrf_reports_are_json_safe_diagnostics(tmp_path: Path) -> None:
    db, _track_ids = _calibration_library(tmp_path)

    rank_report = build_calibration_report(db, score_mode="rank-percentile", bins=2, min_samples=1, accepted_threshold=2)
    rrf_report = build_calibration_report(db, score_mode="rrf", bins=2, min_samples=1, accepted_threshold=2)

    assert rank_report["status"] == "ok"
    assert rank_report["score_kind"] == "rank_percentile_diagnostic"
    assert rank_report["calibration_status"] == "diagnostic_only"
    assert rrf_report["status"] == "ok"
    assert rrf_report["score_kind"] == "rrf_minmax_diagnostic"
    assert rrf_report["calibration_status"] == "diagnostic_only"
    json.dumps(rank_report, allow_nan=False)
    json.dumps(rrf_report, allow_nan=False)


def test_calibration_judged_only_applies_pr23_label_gate(tmp_path: Path) -> None:
    db, _track_ids = _calibration_library(tmp_path)

    report = build_calibration_report(db, score_mode="rrf", bins=2, min_samples=1, accepted_threshold=2, judged_only=True)

    assert report["status"] == "insufficient_data"
    assert report["calibration_status"] == "insufficient_data"
    assert report["evaluation_mode"] == "judged_validation"
    assert report["label_status"] == "insufficient_data"
    assert report["judged_pairs"] == 2
    assert report["brier_score"] is None
    assert report["metric_availability"]["explanation_tag_agreement_at_3"]["coverage"] == 0.0


def test_rrf_calibration_accepts_recorded_clap_source(tmp_path: Path) -> None:
    db, _track_ids = _calibration_library(tmp_path, source_payloads=({"clap": {"rank": 1}}, {"clap": {"rank": 2}}))

    report = build_calibration_report(db, score_mode="rrf", bins=2, min_samples=1, accepted_threshold=2)

    assert report["status"] == "ok"
    assert report["sample_count"] == 2
    assert report["score_kind"] == "rrf_minmax_diagnostic"


def test_event_total_score_reports_out_of_range_without_probability_metrics(tmp_path: Path) -> None:
    db, track_ids = _calibration_library(tmp_path, total_scores=(2.5, 0.2))

    report = build_calibration_report(db, score_mode="event-total-score", bins=2, min_samples=1, accepted_threshold=2)

    assert track_ids["candidate_a"] > 0
    assert report["status"] == "uncalibrated_score_out_of_range"
    assert report["calibration_status"] == "uncalibrated_score_out_of_range"
    assert report["brier_score"] is None
    assert report["reliability_bins"] == []
    assert report["score_quantiles"]


def test_run_calibration_cli_writes_report_without_recording_by_default(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "calibration.json"
    db, _track_ids = _calibration_library(tmp_path, db_path=db_path)

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "run-calibration",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--score-mode",
            "rrf",
            "--bins",
            "2",
            "--min-samples",
            "1",
            "--accepted-threshold",
            "2",
        ],
    )

    assert result.exit_code == 0
    assert "status=ok" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["score_mode"] == "rrf"
    assert report["recorded"] is False
    assert report["sample_count"] == 2
    assert db.count_evaluation_rows()["calibration_runs"] == 0


def test_run_calibration_cli_judged_only_writes_gate_guidance(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "calibration.json"
    _calibration_library(tmp_path, db_path=db_path)

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "run-calibration",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--score-mode",
            "rrf",
            "--bins",
            "2",
            "--min-samples",
            "1",
            "--judged-only",
        ],
    )

    assert result.exit_code == 0
    assert "status=insufficient_data" in result.output
    assert "label_status=insufficient_data" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["judged_only"] is True
    assert "Fewer than 50" in report["label_guidance"]


def _calibration_library(
    tmp_path: Path,
    *,
    db_path: Path | None = None,
    total_scores: tuple[float, float] = (0.8, 0.4),
    source_payloads: tuple[dict[str, dict[str, int]], dict[str, dict[str, int]]] | None = None,
) -> tuple[LibraryDatabase, dict[str, int]]:
    db = LibraryDatabase(db_path or tmp_path / "library.sqlite")
    track_ids = {
        "seed": _track(db, tmp_path, "seed"),
        "candidate_a": _track(db, tmp_path, "candidate_a"),
        "candidate_b": _track(db, tmp_path, "candidate_b"),
    }
    session_id = db.create_search_session(
        "evaluation_candidate_pool",
        [track_ids["seed"]],
        {"feedback_source": "manual", "sources": ["mert", "maest"]},
    )
    first_sources, second_sources = source_payloads or (
        {"mert": {"rank": 1}, "maest": {"rank": 2}},
        {"mert": {"rank": 2}},
    )
    db.record_search_result_event(
        session_id,
        track_ids["candidate_a"],
        rank=1,
        total_score=total_scores[0],
        score_breakdown={"blind_rank": 1, "sources": first_sources},
    )
    db.record_search_result_event(
        session_id,
        track_ids["candidate_b"],
        rank=2,
        total_score=total_scores[1],
        score_breakdown={"blind_rank": 2, "sources": second_sources},
    )
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["candidate_a"], 3, source="manual")
    db.upsert_track_pair_feedback(track_ids["seed"], track_ids["candidate_b"], 0, source="manual")
    return db, track_ids


def _track(db: LibraryDatabase, tmp_path: Path, stem: str) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.replace("_", " ").title()},
    )
