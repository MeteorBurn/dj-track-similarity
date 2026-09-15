from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from dj_track_similarity.db.storage import evaluation_database_path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "benchmark_search.py"
REPO_ROOT = Path(__file__).resolve().parents[2]


def test_benchmark_search_keep_db_preserves_current_bundle(tmp_path: Path) -> None:
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

    assert run["kept_db"] is True
    assert Path(run["db_path"]) == keep_db_path.resolve(strict=False)
    assert keep_db_path.exists()
    assert evaluation_database_path(keep_db_path).exists() is False
    with sqlite3.connect(keep_db_path) as library:
        assert library.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 20
        assert library.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name = 'contracts'"
        ).fetchone()[0] == 0
        assert library.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 20
        assert library.execute("SELECT COUNT(*) FROM maest_embeddings").fetchone()[0] == 20


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
