from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "benchmark_search.py"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_benchmark_search_runs_and_deletes_temporary_database(tmp_path: Path) -> None:
    output_path = tmp_path / "benchmark.json"

    _run_benchmark(
        "--output",
        str(output_path),
        "--track-counts",
        "20",
        "--embedding-dim",
        "8",
        "--seed-count",
        "3",
        "--per-source",
        "5",
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    run = report["runs"][0]
    db_path = Path(run["db_path"])

    assert report["benchmark"] == "exact_search_baseline"
    assert report["config"]["track_counts"] == [20]
    assert report["config"]["vector_backend"] == "exact_numpy"
    assert run["track_count"] == 20
    assert run["kept_db"] is False
    assert db_path.exists() is False
    assert run["load_embedding_matrix"]["mert"]["tracks"] == 20
    assert run["load_embedding_matrix"]["maest"]["dim"] == 8
    assert run["exact_similarity"]["mert"]["backend"] == "exact_numpy"
    assert run["exact_similarity"]["mert"]["seed_count"] == 3
    assert run["weighted_candidates"]["seed_count"] == 3
    assert run["hybrid_search"]["seed_count"] == 3


def test_benchmark_search_keep_db_preserves_synthetic_database(tmp_path: Path) -> None:
    output_path = tmp_path / "benchmark.json"
    keep_db_path = tmp_path / "kept-benchmark.sqlite"

    _run_benchmark(
        "--output",
        str(output_path),
        "--track-count",
        "20",
        "--embedding-dim",
        "8",
        "--seed-count",
        "3",
        "--per-source",
        "5",
        "--classifier-profiles",
        "2",
        "--keep-db",
        str(keep_db_path),
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    run = report["runs"][0]

    assert run["kept_db"] is True
    assert Path(run["db_path"]) == keep_db_path.resolve(strict=False)
    assert keep_db_path.exists()
    with sqlite3.connect(keep_db_path) as connection:
        schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
        classifier_scores = connection.execute("SELECT COUNT(*) FROM track_classifier_scores").fetchone()[0]
    assert schema_version == 4
    assert classifier_scores == 40


@pytest.mark.parametrize(
    ("track_count_args", "output_name", "keep_db_name"),
    [
        (("--track-count", "20"), "kept-benchmark.sqlite", "kept-benchmark.sqlite"),
        (("--track-counts", "20,30"), "kept-benchmark-30.sqlite", "kept-benchmark.sqlite"),
    ],
)
def test_benchmark_search_rejects_output_that_overlaps_keep_db(
    tmp_path: Path,
    track_count_args: tuple[str, ...],
    output_name: str,
    keep_db_name: str,
) -> None:
    output_path = tmp_path / output_name
    keep_db_path = tmp_path / keep_db_name

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--output",
            str(output_path),
            *track_count_args,
            "--embedding-dim",
            "8",
            "--seed-count",
            "3",
            "--per-source",
            "5",
            "--keep-db",
            str(keep_db_path),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "--output must not point to a kept synthetic database path" in result.stderr
    assert output_path.exists() is False


def _run_benchmark(*args: str) -> None:
    subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
