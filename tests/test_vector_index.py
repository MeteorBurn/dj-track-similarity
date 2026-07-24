from __future__ import annotations

import importlib
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
from dj_track_similarity.search import SimilaritySearch
from dj_track_similarity.track_models import (
    FileTags,
    ScannedFile,
    TrackIdentity,
)
from dj_track_similarity.vector_index import (
    ExactVectorSearchBackend,
    HnswVectorSearchBackend,
    VectorIndexUnavailable,
    create_vector_backend,
)


_NOW = "2026-07-24T10:00:00.000000Z"
_CATALOG_UUID = "00000000-0000-4000-8000-000000000001"


def test_exact_backend_matches_manual_matrix_dot_ranking() -> None:
    matrix = np.stack(
        (
            _small_unit_vector(0.0, 1.0, 0.0),
            _small_unit_vector(1.0, 0.0, 0.0),
            _small_unit_vector(0.8, 0.2, 0.0),
            _small_unit_vector(-1.0, 0.0, 0.0),
        )
    )
    targets = _targets(10, 11, 12, 13)
    query = _small_unit_vector(1.0, 0.0, 0.0)
    scores = matrix @ query
    manual_indices = np.argsort(-scores, kind="stable")[:3]

    hits = ExactVectorSearchBackend().search(
        matrix,
        targets,
        query,
        limit=3,
    )

    expected_indices = [int(index) for index in manual_indices]
    assert [hit.index for hit in hits] == expected_indices
    assert [hit.target for hit in hits] == [
        targets[index] for index in expected_indices
    ]
    assert [hit.score for hit in hits] == [
        float(scores[index]) for index in expected_indices
    ]


def test_vector_backend_factory_uses_exact_backend_name() -> None:
    backend = create_vector_backend("exact_numpy")

    assert isinstance(backend, ExactVectorSearchBackend)
    assert backend.backend_name == "exact_numpy"


def test_hnswlib_backend_reports_unavailable_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import_module = importlib.import_module

    def fail_hnsw_import(
        name: str,
        package: str | None = None,
    ) -> object:
        if name == "hnswlib":
            raise ImportError("forced missing hnswlib")
        return real_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fail_hnsw_import)

    with pytest.raises(
        VectorIndexUnavailable,
        match="requires optional dependency 'hnswlib'",
    ):
        create_vector_backend("hnswlib")


def test_hnswlib_backend_matches_exact_ranking_when_available() -> None:
    pytest.importorskip("hnswlib")
    matrix = np.stack(
        (
            _small_unit_vector(1.0, 0.0, 0.0),
            _small_unit_vector(0.8, 0.2, 0.0),
            _small_unit_vector(0.0, 1.0, 0.0),
            _small_unit_vector(-1.0, 0.0, 0.0),
        )
    )
    targets = _targets(201, 202, 203, 204)
    query = _small_unit_vector(1.0, 0.0, 0.0)
    exact_hits = ExactVectorSearchBackend().search(
        matrix,
        targets,
        query,
        limit=3,
    )

    backend = create_vector_backend("hnswlib")
    assert isinstance(backend, HnswVectorSearchBackend)
    hnsw_hits = backend.search(
        matrix,
        targets,
        query,
        limit=3,
    )

    assert [hit.target for hit in hnsw_hits] == [
        hit.target for hit in exact_hits
    ]
    assert [hit.score for hit in hnsw_hits] == pytest.approx(
        [hit.score for hit in exact_hits],
        abs=1e-5,
    )


def test_exact_backend_preserves_stable_input_order_for_ties() -> None:
    matrix = np.stack(
        (
            _small_unit_vector(1.0, 0.0),
            _small_unit_vector(1.0, 0.0),
            _small_unit_vector(0.0, 1.0),
            _small_unit_vector(1.0, 0.0),
        )
    )
    targets = _targets(101, 102, 103, 104)
    query = _small_unit_vector(1.0, 0.0)
    scores = matrix @ query
    manual_indices = [
        int(index)
        for index in np.argsort(-scores, kind="stable")
    ]
    backend = ExactVectorSearchBackend()

    first_hits = backend.search(
        matrix,
        targets,
        query,
        limit=len(targets),
    )
    second_hits = backend.search(
        matrix,
        targets,
        query,
        limit=len(targets),
    )

    assert [hit.index for hit in first_hits] == manual_indices
    assert [hit.index for hit in second_hits] == manual_indices
    assert [hit.target for hit in first_hits] == [
        targets[index] for index in manual_indices
    ]


def test_similarity_search_excludes_seed_outside_vector_backend(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    database.register_analysis_outputs((output,))
    seed = _add_track(
        database,
        tmp_path,
        "seed",
        output,
        _mert_unit_vector(1.0, 0.0),
    )
    near = _add_track(
        database,
        tmp_path,
        "near",
        output,
        _mert_unit_vector(0.99, 0.01),
    )
    far = _add_track(
        database,
        tmp_path,
        "far",
        output,
        _mert_unit_vector(0.0, 1.0),
    )
    backend = ExactVectorSearchBackend()

    rows = database.load_analysis_vectors(output)
    matrix = np.stack(tuple(row.vector for row in rows))
    targets = tuple(row.target for row in rows)
    seed_index = targets.index(seed)
    direct_hits = backend.search(
        matrix,
        targets,
        matrix[seed_index],
        limit=len(targets),
    )
    results = SimilaritySearch(
        database,
        "mert",
        analysis_output=output,
        vector_backend=backend,
    ).search(
        [seed],
        limit=5,
    )

    assert direct_hits[0].target == seed
    assert [result.target for result in results] == [near, far]
    assert seed not in {result.target for result in results}


def _targets(*track_ids: int) -> tuple[AnalysisTarget, ...]:
    return tuple(
        AnalysisTarget(
            catalog_uuid=_CATALOG_UUID,
            track_id=track_id,
            track_uuid=(
                "00000000-0000-4000-8000-"
                f"{track_id:012d}"
            ),
            content_generation=1,
        )
        for track_id in track_ids
    )


def _mert_output() -> AnalysisOutput:
    return current_embedding_analysis_output("mert")


def _add_track(
    database: LibraryDatabase,
    tmp_path: Path,
    stem: str,
    output: AnalysisOutput,
    vector: np.ndarray,
) -> AnalysisTarget:
    identity = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / f"{stem}.wav"),
            file_size_bytes=100,
            file_modified_ns=1,
            audio_format="wav",
        ),
        tags=FileTags(
            artist="Vector Test",
            title=stem,
        ),
        scanned_at=_NOW,
    ).identity
    target = _target(identity)
    result = database.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    contract=output.contract,
                    vector=vector,
                    analyzed_at=_NOW,
                ),
            ),
        )
    )
    assert result[0].ok
    return target


def _target(identity: TrackIdentity) -> AnalysisTarget:
    return AnalysisTarget(
        catalog_uuid=identity.catalog_uuid,
        track_id=identity.track_id,
        track_uuid=identity.track_uuid,
        content_generation=identity.content_generation,
    )


def _small_unit_vector(*values: float) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float32)
    norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
    assert norm > 0.0
    vector /= norm
    return vector


def _mert_unit_vector(first: float, second: float) -> np.ndarray:
    vector = np.zeros(768, dtype=np.float32)
    vector[:2] = (first, second)
    norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
    assert norm > 0.0
    vector /= norm
    return vector
