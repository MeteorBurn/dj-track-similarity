from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.search import SearchFilters, SimilaritySearch
from dj_track_similarity.track_models import FileTags, ScannedFile


_NOW = "2026-07-24T12:00:00.000000Z"


def test_search_uses_multi_seed_centroid_and_excludes_seed_tracks(
    tmp_path: Path,
) -> None:
    db, output = _library(tmp_path, "mert")
    seed_a = _add_track(db, tmp_path, output, "seed-a.wav", [1.0, 0.0, 0.0])
    seed_b = _add_track(db, tmp_path, output, "seed-b.wav", [0.0, 1.0, 0.0])
    bridge = _add_track(db, tmp_path, output, "bridge.wav", [0.7, 0.7, 0.0])
    far = _add_track(db, tmp_path, output, "far.wav", [0.0, 0.0, 1.0])

    results = SimilaritySearch(
        db,
        "mert",
        analysis_output=output,
    ).search((seed_a, seed_b), limit=5)

    assert [result.target.track_id for result in results] == [
        bridge.track_id,
        far.track_id,
    ]
    assert results[0].score > results[1].score


def test_search_epsilon_keeps_only_candidates_near_the_best_score(
    tmp_path: Path,
) -> None:
    db, output = _library(tmp_path, "mert")
    seed = _add_track(db, tmp_path, output, "seed.wav", [1.0, 0.0, 0.0])
    near = _add_track(db, tmp_path, output, "near.wav", [0.99, 0.01, 0.0])
    far = _add_track(db, tmp_path, output, "far.wav", [0.7, 0.3, 0.0])

    results = SimilaritySearch(db, "mert", analysis_output=output).search(
        (seed,), filters=SearchFilters(epsilon=0.02), limit=10
    )

    assert [result.target.track_id for result in results] == [near.track_id]
    assert far not in {result.target for result in results}


def test_search_uses_only_seed_tracks_as_context(tmp_path: Path) -> None:
    db, output = _library(tmp_path, "mert")
    seed = _add_track(db, tmp_path, output, "seed.wav", [1.0, 0.0, 0.0])
    bridge = _add_track(db, tmp_path, output, "bridge.wav", [0.7, 0.7, 0.0])
    seed_clone = _add_track(db, tmp_path, output, "seed-clone.wav", [1.0, 0.0, 0.0])

    results = SimilaritySearch(
        db,
        "mert",
        analysis_output=output,
    ).search((seed,), limit=10)

    assert [result.target.track_id for result in results[:2]] == [
        seed_clone.track_id,
        bridge.track_id,
    ]


def test_search_noise_changes_near_tie_ranking_but_keeps_similarity_scores(
    tmp_path: Path,
) -> None:
    db, output = _library(tmp_path, "mert")
    seed = _add_track(db, tmp_path, output, "seed.wav", [1.0, 0.0, 0.0])
    first = _add_track(db, tmp_path, output, "first.wav", [0.99, 0.01, 0.0])
    second = _add_track(db, tmp_path, output, "second.wav", [0.98, 0.02, 0.0])

    plain = SimilaritySearch(
        db,
        "mert",
        analysis_output=output,
    ).search((seed,), limit=2)
    noisy = SimilaritySearch(db, "mert", analysis_output=output).search(
        (seed,), filters=SearchFilters(noise=0.2), limit=2
    )

    assert [result.target for result in plain] == [first, second]
    assert {result.target for result in noisy} == {first, second}
    assert {result.target: result.score for result in noisy} == pytest.approx(
        {result.target: result.score for result in plain}
    )


def test_search_vector_uses_requested_embedding_space(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    mert = _output("mert")
    clap = _output("clap")
    db.register_analysis_outputs((mert, clap))
    mert_track = _add_track(db, tmp_path, mert, "mert.wav", [1.0, 0.0, 0.0])
    clap_near = _add_track(db, tmp_path, clap, "clap-near.wav", [0.0, 1.0, 0.0])
    clap_far = _add_track(db, tmp_path, clap, "clap-far.wav", [1.0, 0.0, 0.0])

    results = SimilaritySearch(
        db,
        "clap",
        analysis_output=clap,
    ).search_vector(
        _query(clap, [0.0, 1.0, 0.0]), limit=5
    )

    assert [result.target.track_id for result in results] == [
        clap_near.track_id,
        clap_far.track_id,
    ]
    assert mert_track not in {result.target for result in results}


def test_search_contrast_vectors_rank_positive_over_negative_match(
    tmp_path: Path,
) -> None:
    db, output = _library(tmp_path, "clap")
    positive_match = _add_track(db, tmp_path, output, "positive.wav", [0.0, 1.0, 0.0])
    mixed_match = _add_track(db, tmp_path, output, "mixed.wav", [0.7, 0.7, 0.0])
    negative_match = _add_track(db, tmp_path, output, "negative.wav", [1.0, 0.0, 0.0])

    results = SimilaritySearch(
        db,
        "clap",
        analysis_output=output,
    ).search_contrast_vectors(
        positive_vectors=[_query(output, [0.0, 1.0, 0.0])],
        negative_vectors=[_query(output, [1.0, 0.0, 0.0])],
        limit=5,
    )

    assert [result.target.track_id for result in results] == [
        positive_match.track_id,
        mixed_match.track_id,
        negative_match.track_id,
    ]
    assert results[0].score > results[1].score > results[2].score
    assert results[0].score_breakdown == {
        "positive": 1.0,
        "negative": 0.0,
        "contrast": 1.0,
        "negative_weight": 0.35,
    }


def test_search_contrast_vectors_use_hard_negative_margin_not_probability(
    tmp_path: Path,
) -> None:
    db, output = _library(tmp_path, "clap")
    positive_match = _add_track(db, tmp_path, output, "positive.wav", [1.0, 0.0, 0.0])
    margin_match = _add_track(
        db, tmp_path, output, "margin.wav", [0.70710677, 0.0, 0.70710677]
    )

    results = SimilaritySearch(
        db,
        "clap",
        analysis_output=output,
    ).search_contrast_vectors(
        positive_vectors=[_query(output, [1.0, 0.0, 0.0])],
        negative_vectors=[
            _query(output, [0.0, 1.0, 0.0]),
            _query(output, [0.0, 0.0, 1.0]),
        ],
        limit=5,
    )

    assert [result.target.track_id for result in results] == [
        positive_match.track_id,
        margin_match.track_id,
    ]
    assert results[1].score == pytest.approx(0.4596194)
    assert results[1].score_breakdown == {
        "positive": pytest.approx(0.70710677),
        "negative": pytest.approx(0.70710677),
        "contrast": pytest.approx(0.4596194),
        "negative_weight": 0.35,
    }


def _library(root: Path, family: str) -> tuple[LibraryDatabase, AnalysisOutput]:
    db = LibraryDatabase(root / "library.sqlite")
    output = _output(family)
    db.register_analysis_outputs((output,))
    return db, output


def _add_track(
    db: LibraryDatabase,
    root: Path,
    output: AnalysisOutput,
    name: str,
    values: list[float],
) -> AnalysisTarget:
    path = root / name
    path.write_bytes(name.encode("utf-8"))
    stat = path.stat()
    identity = db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
        ),
        tags=FileTags(title=name, artist="Test"),
        scanned_at=_NOW,
    ).identity
    target = AnalysisTarget(
        identity.catalog_uuid,
        identity.track_id,
        identity.track_uuid,
        identity.content_generation,
    )
    result = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    contract=output.contract,
                    vector=_query(output, values),
                    analyzed_at=_NOW,
                ),
            ),
        )
    )[0]
    assert result.ok, result.error
    return target


def _query(output: AnalysisOutput, values: list[float]) -> np.ndarray:
    vector = np.zeros(output.contract.dim, dtype=np.float32)
    vector[: len(values)] = values
    return vector / np.linalg.norm(vector)


def _output(family: str) -> AnalysisOutput:
    if family not in {"mert", "clap"}:
        raise ValueError(f"Unsupported fixture family: {family}")
    return current_embedding_analysis_output(family)
