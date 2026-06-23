from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import dj_track_similarity.cli as cli
from dj_track_similarity.database import LibraryDatabase


def test_eval_import_pair_feedback_cli_upserts_labels(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1)
    candidate_id = db.upsert_track(path=tmp_path / "candidate.wav", size=10, mtime=1)
    input_path = tmp_path / "feedback.csv"
    input_path.write_text(
        "seed_track_id,candidate_track_id,rating,reason_tags,notes,source\n"
        f"{seed_id},{candidate_id},3,mixable,works,manual\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli.app,
        ["eval", "import-pair-feedback", "--db", str(db_path), "--input", str(input_path)],
    )

    assert result.exit_code == 0
    assert "imported=1 upserted=1" in result.output
    feedback = LibraryDatabase(db_path).get_pair_feedback_map()
    assert feedback[(seed_id, candidate_id, "manual")]["rating"] == 3


def test_eval_report_cli_writes_json_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "report.json"
    db = LibraryDatabase(db_path)
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1)
    candidate_id = db.upsert_track(path=tmp_path / "candidate.wav", size=10, mtime=1)
    session_id = db.create_search_session("mert", [seed_id], {"limit": 1})
    db.record_search_result_event(session_id, candidate_id, rank=1, total_score=0.9, score_breakdown={"mert": 0.9})
    db.upsert_track_pair_feedback(seed_id, candidate_id, 3)

    result = CliRunner().invoke(
        cli.app,
        ["eval", "report", "--db", str(db_path), "--output", str(output_path), "--k", "1"],
    )

    assert result.exit_code == 0
    assert "status=ok" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["k_values"] == [1]
    assert report["counts"]["judged_results"] == 1
