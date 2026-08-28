from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
    CLAP_EMBEDDING_DIM,
    EmbeddingOutput,
    EmbeddingWrite,
    MERT_EMBEDDING_DIM,
    MULAN_EMBEDDING_DIM,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.search import SearchFilters, SimilaritySearch
from dj_track_similarity.vector_index import ExactVectorSearchBackend
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


def test_mulan_search_uses_only_mulan_embedding_space(tmp_path: Path) -> None:
    db, output = _library(tmp_path, "mulan")
    seed = _add_track(db, tmp_path, output, "mulan-seed.wav", [1.0, 0.0, 0.0])
    near = _add_track(db, tmp_path, output, "mulan-near.wav", [0.9, 0.1, 0.0])
    far = _add_track(db, tmp_path, output, "mulan-far.wav", [0.0, 1.0, 0.0])

    results = SimilaritySearch(db, "mulan", analysis_output=output).search(
        (seed,),
        limit=5,
    )

    assert [result.target.track_id for result in results] == [near.track_id, far.track_id]


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
        "negative_weight": 0.5,
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
    # The track matches one negative and misses the other, so the penalty is the
    # mean of the two rather than the single closest: 0.707 and 0.0 average to
    # 0.354, and half of that comes off the positive score.
    assert results[1].score == pytest.approx(0.53033012)
    assert results[1].score_breakdown == {
        "positive": pytest.approx(0.70710677),
        "negative": pytest.approx(0.35355339),
        "contrast": pytest.approx(0.53033012),
        "negative_weight": 0.5,
    }


def test_random_target_skips_seeds_without_reading_any_vector(
    tmp_path: Path,
) -> None:
    db, output = _library(tmp_path, "mert")
    seed = _add_track(db, tmp_path, output, "seed.wav", [1.0, 0.0, 0.0])
    first = _add_track(db, tmp_path, output, "first.wav", [0.0, 1.0, 0.0])
    second = _add_track(db, tmp_path, output, "second.wav", [0.0, 0.0, 1.0])
    repository = _VectorLoadCountingRepository(db)

    picked = SimilaritySearch(
        repository,
        "mert",
        analysis_output=output,
    ).random_target(exclude_track_ids=(seed.track_id,))

    assert picked in {first, second}
    assert repository.vector_loads == 0


class _VectorLoadCountingRepository:
    """Repository proxy that records every vector read it is asked for."""

    def __init__(self, database: LibraryDatabase) -> None:
        self._database = database
        self.vector_loads = 0

    @property
    def catalog_uuid(self) -> str:
        return self._database.catalog_uuid

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        return self._database.active_analysis_output(analysis_family, output_kind)

    def load_analysis_vectors(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[AnalysisVectorRow, ...]:
        self.vector_loads += 1
        return self._database.load_analysis_vectors(output, targets=targets)

    def random_embedding_target(
        self,
        output: AnalysisOutput,
        *,
        exclude_track_ids: Sequence[int] = (),
    ) -> AnalysisTarget | None:
        return self._database.random_embedding_target(
            output,
            exclude_track_ids=exclude_track_ids,
        )


def test_cached_library_vectors_reload_after_a_write_from_another_connection(
    tmp_path: Path,
) -> None:
    """A repeated full-library load is served from memory, but never stale.

    The cache is keyed by what the stored rows look like, not by a counter
    this object owns, because analysis also runs from the CLI against a
    database the server has open. A rewrite that never passes through this
    object must still be visible on the next load.
    """

    db, output = _library(tmp_path, "mert")
    kept = _add_track(db, tmp_path, output, "kept.wav", [1.0, 0.0, 0.0])
    moved = _add_track(db, tmp_path, output, "moved.wav", [0.0, 1.0, 0.0])

    first = db.load_analysis_vectors(output)
    assert db.load_analysis_vectors(output) is first

    rewritten = _query(output, [0.0, 0.0, 1.0])
    foreign = LibraryDatabase(tmp_path / "library.sqlite")
    assert foreign.save_embedding_results(
        (
            EmbeddingWrite(
                target=moved,
                output=EmbeddingOutput(
                    family=output.analysis_family,
                    vector=rewritten,
                    analyzed_at="2026-07-24T13:00:00.000000Z",
                ),
            ),
        )
    )[0].ok

    reloaded = db.load_analysis_vectors(output)
    vectors = {row.target.track_id: row.vector for row in reloaded}
    assert np.array_equal(vectors[moved.track_id], rewritten)
    assert np.array_equal(
        vectors[kept.track_id],
        next(row.vector for row in first if row.target.track_id == kept.track_id),
    )


class _FullDepthBackend(ExactVectorSearchBackend):
    """Ignores the requested depth and ranks the whole library."""

    def search(self, matrix, targets, query, limit):  # noqa: ANN001, ANN201
        return super().search(matrix, targets, query, len(targets))


class _DepthRecordingBackend(ExactVectorSearchBackend):
    def __init__(self) -> None:
        self.requested: list[int] = []

    def search(self, matrix, targets, query, limit):  # noqa: ANN001, ANN201
        self.requested.append(limit)
        return super().search(matrix, targets, query, limit)


def test_bounded_ranking_depth_matches_ranking_the_whole_library(
    tmp_path: Path,
) -> None:
    """Reading a prefix of the ranking must not change the answer.

    Deterministic noise reorders results within a band of the score, so the
    depth a search reads has to grow until no unseen score can reach the last
    result kept. This pins that bound against the ranking it approximates.
    """

    db, output = _library(tmp_path, "mert")
    seed = _add_track(db, tmp_path, output, "seed.wav", [1.0, 0.0, 0.0])
    # Six tracks packed inside the noise band, where the jitter decides the
    # order, and six far below it, where it cannot.
    for index in range(12):
        cosine = 0.99 - index * 0.01 if index < 6 else 0.30 - index * 0.02
        _add_track(
            db,
            tmp_path,
            output,
            f"track-{index}.wav",
            [cosine, (1.0 - cosine * cosine) ** 0.5, 0.0],
        )

    filters = SearchFilters(noise=0.2, epsilon=1.0)
    recorder = _DepthRecordingBackend()
    bounded = SimilaritySearch(
        db,
        "mert",
        analysis_output=output,
        vector_backend=recorder,
    ).search((seed,), filters=filters, limit=3)
    whole = SimilaritySearch(
        db,
        "mert",
        analysis_output=output,
        vector_backend=_FullDepthBackend(),
    ).search((seed,), filters=filters, limit=3)

    assert [(r.target.track_id, r.score) for r in bounded] == [
        (r.target.track_id, r.score) for r in whole
    ]
    assert max(recorder.requested) < 13


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
    )
    result = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family=output.analysis_family,
                    vector=_query(output, values),
                    analyzed_at=_NOW,
                ),
            ),
        )
    )[0]
    assert result.ok, result.error
    return target


def _query(output: AnalysisOutput, values: list[float]) -> np.ndarray:
    dimensions = {
        "clap": CLAP_EMBEDDING_DIM,
        "mert": MERT_EMBEDDING_DIM,
        "mulan": MULAN_EMBEDDING_DIM,
    }
    vector = np.zeros(dimensions[output.analysis_family], dtype=np.float32)
    vector[: len(values)] = values
    return vector / np.linalg.norm(vector)


def _output(family: str) -> AnalysisOutput:
    if family not in {"mert", "mulan", "clap"}:
        raise ValueError(f"Unsupported fixture family: {family}")
    return current_embedding_analysis_output(family)
