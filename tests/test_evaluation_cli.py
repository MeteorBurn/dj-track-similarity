from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
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


def test_eval_run_ablation_cli_writes_json_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    output_path = tmp_path / "ablation.json"
    db = LibraryDatabase(db_path)
    seed_id = db.upsert_track(path=tmp_path / "seed.wav", size=10, mtime=1)
    candidate_id = db.upsert_track(path=tmp_path / "candidate.wav", size=10, mtime=1)
    session_id = db.create_search_session("evaluation_candidate_pool", [seed_id], {"feedback_source": "manual"})
    db.record_search_result_event(
        session_id,
        candidate_id,
        rank=1,
        total_score=0.0,
        score_breakdown={"sources": {"mert": {"rank": 1}, "maest": {"rank": 2}}},
    )
    db.upsert_track_pair_feedback(seed_id, candidate_id, 3)

    result = CliRunner().invoke(
        cli.app,
        ["eval", "run-ablation", "--db", str(db_path), "--output", str(output_path), "--k", "1", "--rrf-k", "60"],
    )

    assert result.exit_code == 0
    assert "status=ok" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["k_values"] == [1]
    assert report["rrf_k"] == 60
    assert report["counts"]["judged_results"] == 1
    assert "fusion:rrf_all" in report["variants"]


def test_eval_export_candidates_cli_writes_csv_without_recording_sessions(tmp_path: Path) -> None:
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
    assert {event["track_id"] for event in sessions[0]["events"]}.issubset(set(candidate_ids))
    assert all("blind_rank" in event["score_breakdown"] for event in sessions[0]["events"])


def _build_candidate_export_library(db_path: Path, tmp_path: Path) -> tuple[int, list[int]]:
    db = LibraryDatabase(db_path)
    seed_id = _upsert_cli_candidate_track(db, tmp_path, "seed", bpm=120.0, energy=0.5)
    candidate_a = _upsert_cli_candidate_track(db, tmp_path, "candidate_a", bpm=121.0, energy=0.55)
    candidate_b = _upsert_cli_candidate_track(db, tmp_path, "candidate_b", bpm=122.0, energy=0.6)
    candidate_c = _upsert_cli_candidate_track(db, tmp_path, "candidate_c", bpm=130.0, energy=0.9)

    _save_cli_candidate_analysis(db, seed_id, embedding=[1.0, 0.0], bpm=120.0, energy=0.5, danceability=0.7)
    _save_cli_candidate_analysis(db, candidate_a, embedding=[0.99, 0.1], bpm=121.0, energy=0.55, danceability=0.72)
    _save_cli_candidate_analysis(db, candidate_b, embedding=[0.8, 0.2], bpm=122.0, energy=0.6, danceability=0.75)
    _save_cli_candidate_analysis(db, candidate_c, embedding=[0.0, 1.0], bpm=130.0, energy=0.9, danceability=0.3)
    return seed_id, [candidate_a, candidate_b, candidate_c]


def _upsert_cli_candidate_track(db: LibraryDatabase, tmp_path: Path, stem: str, *, bpm: float, energy: float) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.replace("_", " ").title()},
        bpm=bpm,
        musical_key="1A",
        energy=energy,
    )


def _save_cli_candidate_analysis(
    db: LibraryDatabase,
    track_id: int,
    *,
    embedding: list[float],
    bpm: float,
    energy: float,
    danceability: float,
) -> None:
    db.save_embedding(track_id, np.asarray(embedding, dtype=np.float32), "test-mert", embedding_key="mert")
    db.save_sonara_features(
        track_id,
        {
            "bpm": bpm,
            "energy": energy,
            "danceability": danceability,
            "valence": danceability,
            "acousticness": 1.0 - energy,
            "rms_mean": energy / 2.0,
            "onset_density": danceability * 2.0,
            "key": "1A",
            "key_confidence": 0.9,
        },
        bpm=bpm,
        musical_key="1A",
        energy=energy,
    )


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))
