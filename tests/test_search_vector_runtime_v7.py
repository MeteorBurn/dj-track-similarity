from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import replace
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
    StaleAnalysisTargetError,
)
from dj_track_similarity.db_analysis import AnalysisRepository
from dj_track_similarity.db_artifacts import (
    create_artifacts_sidecar_schema,
)
from dj_track_similarity.db_schema_v7 import create_v7_schema
from dj_track_similarity.search import (
    SearchFilters,
    SimilaritySearch,
)
from dj_track_similarity.vector_index import (
    ExactVectorSearchBackend,
    VectorIndexUnavailable,
    create_vector_backend,
)


_NOW = "2026-07-24T10:00:00.000000Z"


class _Repository(AnalysisRepository):
    def __init__(self, root: Path) -> None:
        self.path = root / "library.sqlite"
        self.artifacts_path = root / "library.artifacts.sqlite"
        self.catalog_uuid = str(uuid.uuid4())
        self._write_lock = threading.RLock()

        core = sqlite3.connect(self.path)
        try:
            create_v7_schema(core)
            core.execute(
                """
                INSERT INTO library_catalog (
                    singleton_id, catalog_uuid, created_at, updated_at
                ) VALUES (1, ?, ?, ?)
                """,
                (self.catalog_uuid, _NOW, _NOW),
            )
            core.commit()
        finally:
            core.close()

        artifacts = sqlite3.connect(self.artifacts_path)
        try:
            create_artifacts_sidecar_schema(
                artifacts,
                catalog_uuid=self.catalog_uuid,
            )
            artifacts.commit()
        finally:
            artifacts.close()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def connect_artifacts(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.artifacts_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _insert_track(
    repository: _Repository,
    track_uuid: str,
) -> AnalysisTarget:
    with repository.connect() as core:
        cursor = core.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, 123456789, 1, ?, ?, ?)
            """,
            (
                track_uuid,
                f"C:/music/{track_uuid}.wav",
                _NOW,
                _NOW,
                _NOW,
            ),
        )
    return AnalysisTarget(
        catalog_uuid=repository.catalog_uuid,
        track_id=int(cursor.lastrowid),
        track_uuid=track_uuid,
        content_generation=1,
    )


def _mert_output() -> AnalysisOutput:
    return current_embedding_analysis_output("mert")


def _drifted_output(
    output: AnalysisOutput,
    *,
    checkpoint_digit: str,
) -> AnalysisOutput:
    return AnalysisOutput(
        replace(
            output.contract,
            checkpoint_id="sha256:" + checkpoint_digit * 64,
        )
    )


def _unit_vector(
    first: float,
    second: float,
) -> np.ndarray:
    vector = np.zeros(768, dtype=np.float32)
    vector[0] = first
    vector[1] = second
    return vector


def _write(
    target: AnalysisTarget,
    output: AnalysisOutput,
    vector: np.ndarray,
) -> EmbeddingWrite:
    return EmbeddingWrite(
        target=target,
        output=EmbeddingOutput(
            contract=output.contract,
            vector=vector,
            analyzed_at=_NOW,
        ),
    )


def test_search_uses_active_contract_and_returns_full_targets(
    tmp_path: Path,
) -> None:
    repository = _Repository(tmp_path)
    output = _mert_output()
    repository.register_analysis_outputs((output,))
    seed = _insert_track(repository, "00000000-0000-4000-8000-000000000001")
    close = _insert_track(repository, "00000000-0000-4000-8000-000000000002")
    orthogonal = _insert_track(
        repository,
        "00000000-0000-4000-8000-000000000003",
    )
    writes = (
        _write(seed, output, _unit_vector(1.0, 0.0)),
        _write(close, output, _unit_vector(0.8, 0.6)),
        _write(orthogonal, output, _unit_vector(0.0, 1.0)),
    )
    assert all(
        result.ok
        for result in repository.save_embedding_results(writes)
    )

    searcher = SimilaritySearch(
        repository,
        "mert",
        analysis_output=output,
    )
    assert searcher.active_output() == output
    assert searcher.resolve_targets(
        [seed.track_id, close.track_id]
    ) == (seed, close)

    results = searcher.search((seed,), limit=10)
    assert [result.target for result in results] == [
        close,
        orthogonal,
    ]
    assert [result.score for result in results] == pytest.approx(
        [0.8, 0.0]
    )
    assert all(
        result.target.catalog_uuid == repository.catalog_uuid
        and result.target.track_uuid
        and result.target.content_generation == 1
        for result in results
    )

    restricted = searcher.search(
        (seed,),
        candidate_targets=(orthogonal,),
        filters=SearchFilters(min_similarity=-0.1),
        limit=10,
    )
    assert [result.target for result in restricted] == [orthogonal]


def test_search_rejects_stale_target_and_inactive_contract_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _Repository(tmp_path)
    old_output = _mert_output()
    repository.register_analysis_outputs((old_output,))
    seed = _insert_track(repository, "00000000-0000-4000-8000-000000000004")
    assert repository.save_embedding_results(
        (
            _write(
                seed,
                old_output,
                _unit_vector(1.0, 0.0),
            ),
        )
    )[0].ok
    searcher = SimilaritySearch(
        repository,
        "mert",
        analysis_output=old_output,
    )

    with repository.connect() as core:
        core.execute(
            """
            UPDATE tracks
            SET content_generation = 2, updated_at = ?
            WHERE track_id = ?
            """,
            (_NOW, seed.track_id),
        )
    with pytest.raises(
        StaleAnalysisTargetError,
        match="content_generation mismatch",
    ):
        searcher.search((seed,))

    current = AnalysisTarget(
        catalog_uuid=seed.catalog_uuid,
        track_id=seed.track_id,
        track_uuid=seed.track_uuid,
        content_generation=2,
    )
    new_output = _drifted_output(old_output, checkpoint_digit="2")
    monkeypatch.setattr(
        repository,
        "active_analysis_output",
        lambda *_args: new_output,
    )
    with pytest.raises(
        VectorIndexUnavailable,
        match="reanalysis is required",
    ):
        searcher.search((current,))


def test_runtime_contract_drift_blocks_old_vectors_before_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repository = _Repository(tmp_path)
    stored_output = _mert_output()
    current_output = _drifted_output(
        stored_output,
        checkpoint_digit="2",
    )
    repository.register_analysis_outputs((stored_output,))

    def fail_vector_read(*_args, **_kwargs):
        raise AssertionError("old vectors must not be read after runtime drift")

    monkeypatch.setattr(
        repository,
        "load_analysis_vectors",
        fail_vector_read,
    )

    with pytest.raises(
        VectorIndexUnavailable,
        match="reanalysis is required",
    ):
        SimilaritySearch(
            repository,
            "mert",
            analysis_output=current_output,
        )


def test_vector_backend_binds_hits_to_exact_analysis_targets() -> None:
    catalog_uuid = "00000000-0000-4000-8000-000000000010"
    targets = (
        AnalysisTarget(
            catalog_uuid=catalog_uuid,
            track_id=1,
            track_uuid="00000000-0000-4000-8000-000000000011",
            content_generation=1,
        ),
        AnalysisTarget(
            catalog_uuid=catalog_uuid,
            track_id=2,
            track_uuid="00000000-0000-4000-8000-000000000012",
            content_generation=3,
        ),
    )
    matrix = np.asarray(
        [[1.0, 0.0], [0.0, 1.0]],
        dtype=np.float32,
    )
    hits = ExactVectorSearchBackend().search(
        matrix,
        targets,
        matrix[1],
        2,
    )
    assert [hit.target for hit in hits] == [targets[1], targets[0]]
    assert [hit.index for hit in hits] == [1, 0]
    assert [hit.score for hit in hits] == pytest.approx([1.0, 0.0])

    with pytest.raises(ValueError, match="unit-normalized matrix rows"):
        ExactVectorSearchBackend().search(
            matrix * 2.0,
            targets,
            matrix[0],
            1,
        )
    with pytest.raises(ValueError, match="Unknown vector backend"):
        create_vector_backend("exact")
