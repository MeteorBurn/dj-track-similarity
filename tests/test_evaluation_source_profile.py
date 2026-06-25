from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

import dj_track_similarity.cli as cli
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.candidates import CandidatePoolRow, CandidateSourceContribution
from dj_track_similarity.evaluation.source_profile import SourceProfileRequest, build_source_profile, profile_candidate_rows
from dj_track_similarity.models import Track


def test_source_profile_is_deterministic_for_same_seed(tmp_path: Path) -> None:
    db, track_ids = _profile_library(tmp_path)

    first = build_source_profile(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        per_source=2,
        top_k_values=[1, 2],
        random_seed=17,
    )
    second = build_source_profile(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        per_source=2,
        top_k_values=[1, 2],
        random_seed=17,
    )

    assert first == second
    assert first["status"] == "ok"
    assert first["profile_kind"] == "unsupervised_source_profile"


def test_source_profile_weights_sum_to_one_for_available_sources(tmp_path: Path) -> None:
    db, track_ids = _profile_library(tmp_path)

    report = build_source_profile(
        db,
        seed_track_ids=[track_ids["seed"]],
        sources=["mert", "maest"],
        per_source=2,
        random_seed=123,
    )

    weights = report["recommended_weights"]["weights"]

    assert report["recommended_weights"]["weight_kind"] == "unsupervised_internal_profile"
    assert sum(weights.values()) == 1.0
    assert all(weight >= 0 for weight in weights.values())


def test_source_profile_zero_coverage_source_gets_zero_weight_and_warning(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _upsert_track(db, tmp_path, "seed")
    candidate_id = _upsert_track(db, tmp_path, "candidate")
    db.save_embedding(seed_id, np.asarray([1.0, 0.0], dtype=np.float32), "test-mert", embedding_key="mert")
    db.save_embedding(candidate_id, np.asarray([0.9, 0.1], dtype=np.float32), "test-mert", embedding_key="mert")

    report = build_source_profile(
        db,
        seed_track_ids=[seed_id],
        sources=["mert", "maest"],
        per_source=1,
        random_seed=123,
    )

    assert report["per_source"]["maest"]["seeds_with_results"] == 0
    assert report["recommended_weights"]["weights"]["maest"] == 0.0
    assert any("source=maest has no coverage" in warning for warning in report["warnings"])


def test_source_profile_default_clap_without_rows_is_neutral(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    seed_id = _upsert_track(db, tmp_path, "seed")
    candidate_id = _upsert_track(db, tmp_path, "candidate")
    db.save_embedding(seed_id, np.asarray([1.0, 0.0], dtype=np.float32), "test-mert", embedding_key="mert")
    db.save_embedding(candidate_id, np.asarray([0.9, 0.1], dtype=np.float32), "test-mert", embedding_key="mert")

    report = build_source_profile(
        db,
        seed_track_ids=[seed_id],
        sources=None,
        per_source=1,
        random_seed=123,
    )

    weights = report["recommended_weights"]["weights"]
    assert report["sources"] == ["mert", "maest", "sonara", "clap"]
    assert weights["mert"] == 1.0
    assert weights["clap"] == 0.0
    assert any("source=clap has no coverage" in warning for warning in report["warnings"])


def test_source_profile_consensus_source_outweighs_isolated_source() -> None:
    seed = _track(1)
    rows = (
        _row(seed, _track(101), {"mert": 1, "maest": 1}),
        _row(seed, _track(102), {"mert": 2}),
        _row(seed, _track(103), {"maest": 2}),
        _row(seed, _track(104), {"sonara": 1}),
        _row(seed, _track(105), {"sonara": 2}),
    )

    report = profile_candidate_rows(
        SourceProfileRequest(
            seed_track_ids=(seed.id,),
            sources=("mert", "maest", "sonara"),
            per_source=2,
            top_k_values=(2,),
            random_seed=123,
        ),
        rows,
    )
    weights = report["recommended_weights"]["weights"]

    assert weights["mert"] > weights["sonara"]
    assert weights["maest"] > weights["sonara"]
    assert report["per_source"]["sonara"]["conflict_rate"] == 1.0
    assert report["pairwise_agreement"]["mert"]["maest"]["jaccard_at_k"]["2"] > 0.0


def test_eval_profile_sources_cli_writes_json_without_manual_labels(tmp_path: Path) -> None:
    db, track_ids = _profile_library(tmp_path)
    db_path = Path(db.path)
    seed_sample_path = tmp_path / "seed_sample.csv"
    output_path = tmp_path / "source_profile.json"
    with seed_sample_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["track_id"])
        writer.writeheader()
        writer.writerow({"track_id": track_ids["seed"]})

    result = CliRunner().invoke(
        cli.app,
        [
            "eval",
            "profile-sources",
            "--db",
            str(db_path),
            "--output",
            str(output_path),
            "--seed-sample",
            str(seed_sample_path),
            "--source",
            "mert",
            "--source",
            "maest",
            "--per-source",
            "2",
            "--top-k",
            "1",
            "--random-seed",
            "123",
        ],
    )

    assert result.exit_code == 0
    assert "weight_kind=unsupervised_internal_profile" in result.output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["seed_count"] == 1
    assert report["limitations"]
    assert LibraryDatabase(db_path).count_evaluation_rows()["track_pair_feedback"] == 0


def _profile_library(tmp_path: Path) -> tuple[LibraryDatabase, dict[str, int]]:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = {
        "seed": _upsert_track(db, tmp_path, "seed"),
        "shared": _upsert_track(db, tmp_path, "shared"),
        "mert_only": _upsert_track(db, tmp_path, "mert_only"),
        "maest_only": _upsert_track(db, tmp_path, "maest_only"),
    }
    _save_profile_embeddings(db, track_ids["seed"], mert=[1.0, 0.0], maest=[0.0, 1.0])
    _save_profile_embeddings(db, track_ids["shared"], mert=[0.99, 0.1], maest=[0.1, 0.99])
    _save_profile_embeddings(db, track_ids["mert_only"], mert=[0.8, 0.2], maest=[1.0, 0.0])
    _save_profile_embeddings(db, track_ids["maest_only"], mert=[0.0, 1.0], maest=[0.2, 0.8])
    return db, track_ids


def _upsert_track(db: LibraryDatabase, tmp_path: Path, stem: str) -> int:
    return db.upsert_track(
        path=tmp_path / f"{stem}.wav",
        size=10,
        mtime=1,
        metadata={"artist": f"Artist {stem}", "title": stem.replace("_", " ").title()},
        bpm=120.0,
        musical_key="1A",
        energy=0.5,
    )


def _save_profile_embeddings(db: LibraryDatabase, track_id: int, *, mert: list[float], maest: list[float]) -> None:
    db.save_embedding(track_id, np.asarray(mert, dtype=np.float32), "test-mert", embedding_key="mert")
    db.save_embedding(track_id, np.asarray(maest, dtype=np.float32), "test-maest", embedding_key="maest")


def _track(track_id: int) -> Track:
    return Track(id=track_id, path=f"{track_id}.wav", size=10, mtime=1.0)


def _row(seed: Track, candidate: Track, source_ranks: dict[str, int]) -> CandidatePoolRow:
    return CandidatePoolRow(
        seed_track=seed,
        candidate_track=candidate,
        blind_rank=candidate.id,
        source_contributions={
            source: CandidateSourceContribution(rank=rank, score=1.0 / rank)
            for source, rank in source_ranks.items()
        },
    )
