from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

import dj_track_similarity.cli as cli
from dj_track_similarity.ann_index import (
    PersistentAnnVectorSearchBackend,
    benchmark_persistent_index,
    build_persistent_index,
    clear_persistent_indexes,
    default_index_dir_for_db,
    verify_persistent_index,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.search import SimilaritySearch


def test_default_sidecar_path_and_clear_scope_are_safe(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "data" / "library.sqlite")
    index_dir = tmp_path / ".dj-track-similarity-indexes"
    index_dir.mkdir()
    kept_file = index_dir / "notes.txt"
    kept_file.write_text("keep\n", encoding="utf-8")
    kept_subdir = index_dir / "nested"
    kept_subdir.mkdir()
    mert_artifact = index_dir / "embeddings_mert_fake_3.npz"
    mert_manifest = index_dir / "embeddings_mert_fake_3.manifest.json"
    clap_artifact = index_dir / "embeddings_clap_fake_3.npz"
    outside_file = tmp_path / "embeddings_mert_outside_3.npz"
    for path in (mert_artifact, mert_manifest, clap_artifact, outside_file):
        path.write_text("generated\n", encoding="utf-8")

    result = clear_persistent_indexes(index_dir, adapter="mert")

    assert default_index_dir_for_db(db) == db.path.parent / ".dj-track-similarity-indexes"
    assert result.deleted_count == 2
    assert {path.name for path in result.deleted_files} == {mert_artifact.name, mert_manifest.name}
    assert kept_file.exists()
    assert kept_subdir.exists()
    assert clap_artifact.exists()
    assert outside_file.exists()


def test_build_and_verify_persistent_index_metadata(tmp_path: Path) -> None:
    db = _small_db(tmp_path)
    index_dir = tmp_path / "indexes"

    build = build_persistent_index(db, "mert", index_dir=index_dir, backend="exact-numpy")
    verification = verify_persistent_index(db, "mert", index_dir=index_dir)
    manifest = json.loads(build.manifest_path.read_text(encoding="utf-8"))

    assert build.backend == "exact_numpy"
    assert build.artifact_path.exists()
    assert build.manifest_path.exists()
    assert manifest["adapter"] == "mert"
    assert manifest["embedding_count"] == 4
    assert manifest["embedding_dim"] == 3
    assert manifest["db_path_hash"]
    assert manifest["track_ids_hash"]
    assert manifest["embedding_version_hash"]
    assert verification.status == "ok"
    assert verification.artifact_path == build.artifact_path


def test_verify_detects_stale_embeddings_and_db_mismatch(tmp_path: Path) -> None:
    db = _small_db(tmp_path)
    index_dir = tmp_path / "indexes"
    build_persistent_index(db, "mert", index_dir=index_dir, backend="exact-numpy")

    db.save_embedding(2, np.asarray([0.0, 0.0, 1.0], dtype=np.float32), "fake-mert", embedding_key="mert")
    stale = verify_persistent_index(db, "mert", index_dir=index_dir)

    assert stale.status == "stale"
    assert "embedding_version_hash" in stale.reasons

    other_db = _small_db(tmp_path, name="other.sqlite")
    mismatch = verify_persistent_index(other_db, "mert", index_dir=index_dir)

    assert mismatch.status == "stale"
    assert "db_path_hash" in mismatch.reasons


def test_benchmark_reports_recall_threshold_result(tmp_path: Path) -> None:
    db = _small_db(tmp_path)
    index_dir = tmp_path / "indexes"
    build_persistent_index(db, "mert", index_dir=index_dir, backend="exact-numpy")

    report = benchmark_persistent_index(
        db,
        "mert",
        index_dir=index_dir,
        threshold=0.97,
        recall_k=2,
        k_values=(1,),
        seed_count=3,
        random_seed=7,
    )

    assert report["status"] == "pass"
    assert report["compare"] == "exact"
    assert report["recall"]["recall_at_2"]["mean"] == 1.0
    assert report["threshold"] == 0.97


def test_persistent_backend_falls_back_to_exact_when_index_missing_or_stale(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed = _add_track(db, tmp_path, "seed", [1.0, 0.0, 0.0])
    near = _add_track(db, tmp_path, "near", [0.99, 0.01, 0.0])
    far = _add_track(db, tmp_path, "far", [0.0, 1.0, 0.0])
    missing_backend = PersistentAnnVectorSearchBackend(db, embedding_key="mert", index_dir=tmp_path / "missing")

    missing_results = SimilaritySearch(db, vector_backend=missing_backend).search([seed], limit=2)

    assert [result.track.id for result in missing_results] == [near, far]
    assert missing_backend.last_backend_name == "exact_numpy"
    assert "manifest" in str(missing_backend.last_fallback_reason)

    index_dir = tmp_path / "indexes"
    build_persistent_index(db, "mert", index_dir=index_dir, backend="exact-numpy")
    db.save_embedding(near, np.asarray([0.0, 1.0, 0.0], dtype=np.float32), "fake-mert", embedding_key="mert")
    db.save_embedding(far, np.asarray([1.0, 0.0, 0.0], dtype=np.float32), "fake-mert", embedding_key="mert")
    stale_backend = PersistentAnnVectorSearchBackend(db, embedding_key="mert", index_dir=index_dir)

    stale_results = SimilaritySearch(db, vector_backend=stale_backend).search([seed], limit=2)

    assert [result.track.id for result in stale_results] == [far, near]
    assert stale_backend.last_backend_name == "exact_numpy"
    assert "stale" in str(stale_backend.last_fallback_reason)


def test_index_cli_build_verify_benchmark_and_clear(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    index_dir = tmp_path / "indexes"
    _small_db(tmp_path, name=db_path.name)
    runner = CliRunner()

    build = runner.invoke(
        cli.app,
        ["index", "build", "--db", str(db_path), "--adapter", "mert", "--index-dir", str(index_dir), "--backend", "exact-numpy"],
    )
    verify = runner.invoke(cli.app, ["index", "verify", "--db", str(db_path), "--adapter", "mert", "--index-dir", str(index_dir)])
    benchmark = runner.invoke(
        cli.app,
        [
            "index",
            "benchmark",
            "--db",
            str(db_path),
            "--adapter",
            "mert",
            "--index-dir",
            str(index_dir),
            "--recall-k",
            "2",
            "--seed-count",
            "2",
        ],
    )
    clear = runner.invoke(cli.app, ["index", "clear", "--adapter", "mert", "--db", str(db_path), "--index-dir", str(index_dir)])

    assert build.exit_code == 0, build.output
    assert "status=ok" in build.output
    assert verify.exit_code == 0, verify.output
    assert "status=ok" in verify.output
    assert benchmark.exit_code == 0, benchmark.output
    assert "status=pass" in benchmark.output
    assert clear.exit_code == 0, clear.output
    assert "deleted=2" in clear.output


def _small_db(tmp_path: Path, *, name: str = "library.sqlite") -> LibraryDatabase:
    db = LibraryDatabase(tmp_path / name)
    _add_track(db, tmp_path, "seed", [1.0, 0.0, 0.0])
    _add_track(db, tmp_path, "near", [0.9, 0.1, 0.0])
    _add_track(db, tmp_path, "mid", [0.0, 1.0, 0.0])
    _add_track(db, tmp_path, "far", [0.0, 0.0, 1.0])
    return db


def _add_track(db: LibraryDatabase, tmp_path: Path, stem: str, embedding: list[float]) -> int:
    track_id = db.upsert_track(
        path=tmp_path / f"{stem}-{db.path.stem}.wav",
        size=100,
        mtime=1,
        metadata={"artist": "ANN Test", "title": stem},
    )
    db.save_embedding(track_id, np.asarray(embedding, dtype=np.float32), "fake-mert", embedding_key="mert")
    return track_id
