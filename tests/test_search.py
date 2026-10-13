from __future__ import annotations

from contextlib import closing
from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.analysis.model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    CLAP_EMBEDDING_DIM,
    EmbeddingOutput,
    EmbeddingWrite,
    MUQ_EMBEDDING_DIM,
    MERT_V2_EMBEDDING_DIM,
    MULAN_EMBEDDING_DIM,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.search.engine import SearchFilters, SimilaritySearch
from dj_track_similarity.search.vector_index import ExactVectorQuery, ExactVectorSearchBackend, VectorSearchHit
from dj_track_similarity.track_models import FileTags, ScannedFile
from embedding_test_support import same_vector_layers


_NOW = "2026-07-24T12:00:00.000000Z"


def test_search_uses_multi_seed_centroid_and_excludes_seed_tracks(
    tmp_path: Path,
) -> None:
    db, output = _library(tmp_path, "mert_v2")
    seeds = tuple(
        _add_track(db, tmp_path, output, f"seed-{index}.wav", [1.0, 0.0, 0.0] if index < 3 else [0.0, 1.0, 0.0])
        for index in range(6)
    )
    bridge = _add_track(db, tmp_path, output, "bridge.wav", [0.7, 0.7, 0.0])
    far = _add_track(db, tmp_path, output, "far.wav", [0.0, 0.0, 1.0])

    results = SimilaritySearch(
        db,
        "mert_v2",
        analysis_output=output,
    ).search(seeds, limit=20)

    assert [result.target.track_id for result in results] == [
        bridge.track_id,
        far.track_id,
    ]
    assert [result.score for result in results] == pytest.approx([1.0, 0.0])
    for target in (*seeds, bridge, far):
        final_vector = db.load_analysis_vectors(output, targets=(target,))[0].vector
        layer_vector = _query(output, [1.0, 0.0] if target == bridge else [0.0, 1.0])
        saved = db.save_embedding_results((EmbeddingWrite(target=target, output=EmbeddingOutput(
            family="mert_v2", vector=final_vector, analyzed_at=_NOW,
            layer_vectors=tuple(layer_vector if layer == 12 else final_vector for layer in range(1, 25)),
        )),))
        assert saved[0].ok
    layer_search = SimilaritySearch(db, "mert_v2", analysis_output=output, layer=12)
    layer_results = layer_search.search(layer_search.resolve_targets([target.track_id for target in seeds]), limit=20)
    assert [result.target for result in layer_results] == [far, bridge]
    assert [result.score for result in layer_results] == pytest.approx([1.0, 0.0])
    for invalid in (0, 25, True):
        with pytest.raises(ValueError, match="layer"):
            SimilaritySearch(db, "mert_v2", analysis_output=output, layer=invalid)


def test_search_epsilon_keeps_only_candidates_near_the_best_score(
    tmp_path: Path,
) -> None:
    db, output = _library(tmp_path, "muq")
    seed = _add_track(db, tmp_path, output, "seed.wav", [1.0, 0.0, 0.0])
    near = _add_track(db, tmp_path, output, "near.wav", [0.99, 0.01, 0.0])
    far = _add_track(db, tmp_path, output, "far.wav", [0.7, 0.3, 0.0])

    results = SimilaritySearch(db, "muq", analysis_output=output).search(
        (seed,), filters=SearchFilters(epsilon=0.02), limit=10
    )

    assert [result.target.track_id for result in results] == [near.track_id]
    assert far not in {result.target for result in results}


def test_search_noise_changes_near_tie_ranking_but_keeps_similarity_scores(
    tmp_path: Path,
) -> None:
    db, output = _library(tmp_path, "muq")
    seed = _add_track(db, tmp_path, output, "seed.wav", [1.0, 0.0, 0.0])
    first = _add_track(db, tmp_path, output, "first.wav", [0.99, 0.01, 0.0])
    second = _add_track(db, tmp_path, output, "second.wav", [0.98, 0.02, 0.0])

    plain = SimilaritySearch(
        db,
        "muq",
        analysis_output=output,
    ).search((seed,), limit=2)
    noisy = SimilaritySearch(db, "muq", analysis_output=output).search(
        (seed,), filters=SearchFilters(noise=0.2), limit=2
    )

    assert [result.target for result in plain] == [first, second]
    assert {result.target for result in noisy} == {first, second}
    assert {result.target: result.score for result in noisy} == pytest.approx(
        {result.target: result.score for result in plain}
    )


def test_search_vector_uses_requested_embedding_space(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    muq = _output("muq")
    clap = _output("clap")
    db.register_analysis_outputs((muq, clap))
    muq_track = _add_track(db, tmp_path, muq, "muq.wav", [1.0, 0.0, 0.0])
    clap_near = _add_track(db, tmp_path, clap, "clap-near.wav", [0.0, 1.0, 0.0])
    clap_far = _add_track(db, tmp_path, clap, "clap-far.wav", [1.0, 0.0, 0.0])

    searcher = SimilaritySearch(
        db,
        "clap",
        analysis_output=clap,
    )
    results = searcher.search_vector(
        _query(clap, [0.0, 1.0, 0.0]), limit=5
    )

    assert [result.target.track_id for result in results] == [
        clap_near.track_id,
        clap_far.track_id,
    ]
    assert muq_track not in {result.target for result in results}

    assert searcher.text_eligible_count == 2
    assert searcher.text_feedback_status["reason"] == "not_requested"
    searcher.text_feedback_status["reason"] = "applied"
    searcher.search_vector(_query(clap, [1.0, 0.0, 0.0]), limit=1)
    assert searcher.text_eligible_count == 2
    assert searcher.text_feedback_status["reason"] == "not_requested"


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

    from dj_track_similarity.search.engine import FEEDBACK_MINIMUM_TRACKS

    searcher = SimilaritySearch(db, "clap", analysis_output=output)
    query = [_query(output, [0.0, 1.0, 0.0])]
    cold = searcher.search_contrast_vectors(positive_vectors=query)
    duplicate_history = {"relevant": [positive_match.track_id] * FEEDBACK_MINIMUM_TRACKS + [999999], "irrelevant": []}
    unchanged = searcher.search_contrast_vectors(positive_vectors=query, feedback_track_ids=duplicate_history)
    assert [(r.target, r.score) for r in unchanged] == [(r.target, r.score) for r in cold]
    assert searcher.text_feedback_status["reason"] == "insufficient_relevant"
    assert searcher.text_feedback_status["usable_relevant_count"] == 1
    cancelling = [
        _add_track(db, tmp_path, output, f"cancel-{index}.wav", [1.0 if index % 2 else -1.0, 0.0, 0.0])
        for index in range(2 * FEEDBACK_MINIMUM_TRACKS)
    ]
    history = {"relevant": [target.track_id for target in cancelling], "irrelevant": []}
    searcher = SimilaritySearch(db, "clap", analysis_output=output)
    searcher.search_contrast_vectors(positive_vectors=query, feedback_track_ids=history)
    assert searcher.text_feedback_status["reason"] == "invalid_centroid"
    approved = [target.track_id for index, target in enumerate(cancelling) if index % 2]
    searcher.search_contrast_vectors(positive_vectors=query, feedback_track_ids={"relevant": approved, "irrelevant": []})
    assert searcher.text_feedback_status["applied"] is True
    searcher.search_contrast_vectors(positive_vectors=query, feedback_track_ids={"relevant": approved, "irrelevant": [target.track_id for target in cancelling]})
    assert searcher.text_feedback_status["reason"] == "insufficient_relevant"


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


def test_cached_library_vectors_reload_after_a_write_from_another_connection(
    tmp_path: Path,
) -> None:
    """A repeated full-library load is served from memory, but never stale.

    The cache is keyed by what the stored rows look like, not by a counter
    this object owns, because analysis also runs from the CLI against a
    database the server has open. A rewrite that never passes through this
    object must still be visible on the next load.
    """

    db, output = _library(tmp_path, "muq")
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
                    analyzed_at=_NOW,
                    layer_vectors=same_vector_layers(output.analysis_family, rewritten),
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

    returning = _add_track(db, tmp_path, output, "returning.wav", [0.0, 1.0, 0.0])
    anchor, disappearing, returning = sorted(
        (kept, moved, returning), key=lambda target: target.track_uuid, reverse=True,
    )
    with foreign.connect() as connection:
        connection.execute(
            "UPDATE tracks SET updated_at = ? WHERE track_id = ?",
            ("2026-07-25T12:00:00.000000Z", anchor.track_id),
        )
    foreign.mark_missing(returning.track_id, missing_at=_NOW)
    before_swap = db.load_analysis_vectors(output)
    assert {row.target for row in before_swap} == {anchor, disappearing}

    foreign.mark_missing(disappearing.track_id, missing_at=_NOW)
    returned_file = foreign.get_track_file_states_by_ids(
        (returning.track_id,), include_missing=True,
    )[0]
    foreign.upsert_scanned_track(
        file=ScannedFile(
            file_path=returned_file.file_path,
            file_size_bytes=returned_file.file_size_bytes,
            file_modified_ns=returned_file.file_modified_ns,
        ),
        tags=FileTags(),
        scanned_at=_NOW,
    )
    after_swap = db.load_analysis_vectors(output)
    assert {row.target for row in after_swap} == {anchor, returning}

    # Relocation changes the exact row order, without changing IDs or vectors.
    reversed_targets = [row.target for row in reversed(after_swap)]
    for ordered_targets, names in (
        (reversed_targets, ("a.wav", "z.wav")),
        (sorted(reversed_targets, key=lambda target: target.track_id), ("tie.wav", "TIE.wav")),
    ):
        with closing(foreign.connect()) as connection, connection:
            connection.executemany(
                "UPDATE tracks SET file_path = ? WHERE track_id = ?",
                [(str(tmp_path / name), target.track_id) for target, name in zip(ordered_targets, names)],
            )
        assert [row.target for row in db.load_analysis_vectors(output)] == ordered_targets

    # Same IDs, embedding COUNT/MAX and generation: only the current UUID differs.
    with closing(foreign.connect()) as connection, connection:
        connection.execute(
            "UPDATE tracks SET track_uuid = ? WHERE track_id = ?",
            ("00000000-0000-4000-8000-000000000002", returning.track_id),
        )
    assert [row.target for row in db.load_analysis_vectors(output)] == [anchor]
    with closing(foreign.connect()) as connection, connection:
        connection.execute(
            "UPDATE tracks SET track_uuid = ? WHERE track_id = ?",
            (returning.track_uuid, returning.track_id),
        )
    assert {row.target for row in db.load_analysis_vectors(output)} == {anchor, returning}

    with closing(foreign.connect()) as connection, connection:
        connection.execute("UPDATE tracks SET missing_since = ?", (_NOW,))
    assert db.load_analysis_vectors(output) == ()
    with closing(foreign.connect()) as connection, connection:
        connection.execute(
            "UPDATE tracks SET missing_since = NULL WHERE track_id IN (?, ?)",
            (anchor.track_id, returning.track_id),
        )
    assert {row.target for row in db.load_analysis_vectors(output)} == {anchor, returning}

    with closing(foreign.connect()) as connection, connection:
        connection.execute(
            "UPDATE library SET catalog_uuid = ?",
            ("00000000-0000-4000-8000-000000000003",),
        )
    with pytest.raises(RuntimeError, match="catalog"):
        db.load_analysis_vectors(output)


class _FullDepthQuery(ExactVectorQuery):
    """Independent full stable sort, bypassing the optimized selector."""

    def search(self, limit):  # noqa: ANN001, ANN201
        return [
            VectorSearchHit(self.targets[index], float(self.scores[index]), int(index))
            for index in np.argsort(-self.scores, kind="stable")
        ]


class _FullDepthSearch(SimilaritySearch):
    def _rank(self, prepared, query, **kwargs):  # noqa: ANN001, ANN201
        scores = query.scores if isinstance(query, ExactVectorQuery) else prepared.matrix @ query
        return super()._rank(prepared, _FullDepthQuery(prepared.targets, scores), **kwargs)


class _DepthRecordingBackend(ExactVectorSearchBackend):
    def __init__(self) -> None:
        self.requested: list[int] = []

    def search(self, matrix, targets, query, limit):  # noqa: ANN001, ANN201
        self.requested.append(limit)
        return super().search(matrix, targets, query, limit)


def test_bounded_ranking_depth_matches_ranking_the_whole_library(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Reading a prefix of the ranking must not change the answer.

    Deterministic noise reorders results within a band of the score, so the
    depth a search reads has to grow until no unseen score can reach the last
    result kept. This pins that bound against the ranking it approximates.
    """

    from dj_track_similarity.search import engine

    db, output = _library(tmp_path, "clap")
    seed = _add_track(db, tmp_path, output, "seed.wav", [1.0, 0.0, 0.0])
    # Six tracks packed inside the noise band, where the jitter decides the
    # order, and six far below it, where it cannot.
    tracks = []
    for index in range(12):
        cosine = 0.99 - index * 0.01 if index < 6 else 0.30 - index * 0.02
        tracks.append(_add_track(
            db,
            tmp_path,
            output,
            f"track-{index}.wav",
            [cosine, (1.0 - cosine * cosine) ** 0.5, 0.0],
        ))

    # Force a later near candidate into the result, independent of random UUIDs.
    favored = frozenset(tracks[3:6])
    monkeypatch.setattr(
        engine, "_ranking_score",
        lambda target, score, noise: score + (noise / 2 if target in favored else -noise / 2),
    )

    filters = SearchFilters(noise=0.2, epsilon=1.0)
    recorder = _DepthRecordingBackend()
    bounded = SimilaritySearch(
        db,
        "clap",
        analysis_output=output,
        vector_backend=recorder,
    ).search((seed,), filters=filters, limit=3)
    whole = _FullDepthSearch(
        db,
        "clap",
        analysis_output=output,
    ).search((seed,), filters=filters, limit=3)

    assert bounded == whole
    assert len(recorder.requested) > 1
    assert max(recorder.requested) < 13

    # The contrast path bypasses the vector backend, but must obey the same bound.
    positive = [_query(output, [1.0, 0.0, 0.0]), _query(output, [1.0, 0.05, 0.0])]
    negative = [_query(output, [0.0, 1.0, 0.0]), _query(output, [0.0, 0.0, 1.0])]
    history = {"relevant": [target.track_id for target in tracks[:engine.FEEDBACK_MINIMUM_TRACKS]], "irrelevant": []}
    for active_filters, limit, candidates, feedback in (
        (SearchFilters(), 3, None, None),
        (filters, 3, None, None),
        (SearchFilters(noise=0.2, epsilon=0.015), 3, None, None),
        (SearchFilters(noise=0.2, min_similarity=0.95), 3, None, None),
        (SearchFilters(min_similarity=1.0), 3, None, None),
        (SearchFilters(), 0, None, None),
        (SearchFilters(), 30, None, None),
        (filters, 3, tuple(tracks[:7]), history),
    ):
        searcher = SimilaritySearch(db, "clap", analysis_output=output)
        reference = _FullDepthSearch(db, "clap", analysis_output=output)
        arguments = dict(
            positive_vectors=positive, negative_vectors=negative, negative_weight=0.5,
            candidate_targets=candidates, filters=active_filters, limit=limit,
            feedback_track_ids=feedback,
        )
        bounded = searcher.search_contrast_vectors(**arguments)
        whole = reference.search_contrast_vectors(**arguments)
        assert bounded == whole
        assert searcher.text_eligible_count == reference.text_eligible_count
        assert searcher.text_feedback_status == reference.text_feedback_status
        assert searcher.text_feedback_track_ids == reference.text_feedback_track_ids
        if feedback is not None:
            assert searcher.text_feedback_status["applied"]

        # Derive expected breakdowns by target, independently of result position.
        rows = db.load_analysis_vectors(output, targets=candidates)
        matrix = np.stack([row.vector for row in rows])
        shifted = engine._apply_relevance_feedback(
            positive, matrix=matrix, rows=rows, output=output, feedback_track_ids=feedback,
        )
        positive_scores, negative_scores, scores, weight = engine._contrast_vector_scores(
            matrix, output=output, positive_vectors=shifted,
            negative_vectors=negative, negative_weight=0.5,
        )
        indices = {row.target: index for index, row in enumerate(rows)}
        for result in bounded:
            index = indices[result.target]
            assert result.score == float(scores[index])
            assert result.score_breakdown == {
                "positive": float(positive_scores[index]),
                "negative": float(negative_scores[index]),
                "contrast": float(scores[index]),
                "negative_weight": weight,
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
    )
    vector = _query(output, values)
    result = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family=output.analysis_family,
                    vector=vector,
                    analyzed_at=_NOW,
                    layer_vectors=same_vector_layers(output.analysis_family, vector),
                ),
            ),
        )
    )[0]
    assert result.ok, result.error
    return target


def _query(output: AnalysisOutput, values: list[float]) -> np.ndarray:
    dimensions = {
        "clap": CLAP_EMBEDDING_DIM,
        "muq": MUQ_EMBEDDING_DIM,
        "mert_v2": MERT_V2_EMBEDDING_DIM,
        "mulan": MULAN_EMBEDDING_DIM,
    }
    vector = np.zeros(dimensions[output.analysis_family], dtype=np.float32)
    vector[: len(values)] = values
    return vector / np.linalg.norm(vector)


def _output(family: str) -> AnalysisOutput:
    if family not in {"muq", "mert_v2", "mulan", "clap"}:
        raise ValueError(f"Unsupported fixture family: {family}")
    return current_embedding_analysis_output(family)
