from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from dj_track_similarity.db_artifacts import ARTIFACTS_SCHEMA_VERSION
from dj_track_similarity.db_schema_v7 import SCHEMA_VERSION
from dj_track_similarity.db_storage import storage_database_paths


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "benchmark_search.py"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_benchmark_search_runs_and_deletes_temporary_bundle(tmp_path: Path) -> None:
    output_path = tmp_path / "benchmark.json"

    _run_benchmark(
        "--output",
        str(output_path),
        "--track-counts",
        "20",
        "--seed-count",
        "3",
        "--per-source",
        "5",
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    run = report["runs"][0]
    db_path = Path(run["db_path"])
    artifacts_path = Path(run["artifacts_path"])

    assert report["benchmark"] == "v7_embedding_search_benchmark"
    assert report["config"]["track_counts"] == [20]
    assert report["config"]["embedding_dim"] == 768
    assert report["config"]["vector_backend"] == "exact_numpy"
    assert run["track_count"] == 20
    assert run["kept_db"] is False
    assert db_path.exists() is False
    assert artifacts_path.exists() is False
    assert run["data"]["storage"] == "v7-core-artifacts"
    assert run["data"]["synthetic_audio_files_created"] is False
    assert run["load_embedding_matrix"]["mert"]["tracks"] == 20
    assert run["load_embedding_matrix"]["maest"]["dim"] == 768
    assert run["exact_similarity"]["mert"]["backend"] == "exact_numpy"
    assert run["exact_similarity"]["mert"]["seed_count"] == 3
    assert run["hybrid_search"]["seed_count"] == 3


def test_benchmark_search_rejects_invalid_vector_backend(tmp_path: Path) -> None:
    output_path = tmp_path / "benchmark.json"

    result = _run_benchmark_raw(
        "--output",
        str(output_path),
        "--track-count",
        "20",
        "--vector-backend",
        "annoy",
    )

    assert result.returncode == 2
    assert "invalid choice" in result.stderr
    assert output_path.exists() is False


def test_benchmark_search_reports_unavailable_hnsw_backend(tmp_path: Path) -> None:
    output_path = tmp_path / "benchmark.json"
    forced_missing_module = tmp_path / "hnswlib.py"
    forced_missing_module.write_text("raise ImportError('forced missing hnswlib')\n", encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tmp_path) + os.pathsep + env.get("PYTHONPATH", "")

    result = _run_benchmark_raw(
        "--output",
        str(output_path),
        "--track-count",
        "20",
        "--seed-count",
        "2",
        "--per-source",
        "5",
        "--vector-backend",
        "hnsw",
        env=env,
    )

    assert result.returncode == 1
    assert "requires optional dependency 'hnswlib'" in result.stderr
    assert output_path.exists() is False


def test_benchmark_search_keep_db_preserves_v7_bundle(tmp_path: Path) -> None:
    output_path = tmp_path / "benchmark.json"
    keep_db_path = tmp_path / "kept-benchmark.sqlite"

    _run_benchmark(
        "--output",
        str(output_path),
        "--track-count",
        "20",
        "--seed-count",
        "3",
        "--per-source",
        "5",
        "--keep-db",
        str(keep_db_path),
    )

    report = json.loads(output_path.read_text(encoding="utf-8"))
    run = report["runs"][0]
    storage_paths = storage_database_paths(keep_db_path)

    assert run["kept_db"] is True
    assert Path(run["db_path"]) == keep_db_path.resolve(strict=False)
    assert Path(run["artifacts_path"]) == storage_paths.artifacts
    assert keep_db_path.exists()
    assert storage_paths.artifacts.exists()
    assert storage_paths.evaluation.exists() is False
    with sqlite3.connect(keep_db_path) as core:
        assert core.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
        assert core.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 20
        assert core.execute("SELECT COUNT(*) FROM contracts").fetchone()[0] == 3
    with sqlite3.connect(storage_paths.artifacts) as artifacts:
        assert artifacts.execute("PRAGMA user_version").fetchone()[0] == ARTIFACTS_SCHEMA_VERSION
        assert artifacts.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 20
        assert artifacts.execute("SELECT COUNT(*) FROM maest_embeddings").fetchone()[0] == 20


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

    result = _run_benchmark_raw(
        "--output",
        str(output_path),
        *track_count_args,
        "--seed-count",
        "3",
        "--per-source",
        "5",
        "--keep-db",
        str(keep_db_path),
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


def _run_benchmark_raw(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
