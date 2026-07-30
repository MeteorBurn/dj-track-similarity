from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    MAEST_EMBEDDING_DIM,
    MERT_EMBEDDING_DIM,
    MaestGenreScore,
    MaestWrite,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.maest_windows import MaestWindowContext


ANALYZED_AT = "2026-07-30T00:00:00.000000Z"
TRACK_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _repository(tmp_path: Path) -> LibraryDatabase:
    repository = LibraryDatabase(tmp_path / "library.sqlite")
    with repository.connect() as connection:
        connection.execute(
            """
            INSERT INTO tracks(
                track_id, track_uuid, file_path, file_size_bytes,
                file_modified_ns, content_generation, last_scanned_at,
                created_at, updated_at
            ) VALUES (1, ?, 'C:/music/track.wav', 100, 1000, 1, ?, ?, ?)
            """,
            (TRACK_UUID, ANALYZED_AT, ANALYZED_AT, ANALYZED_AT),
        )
        connection.commit()
    return repository


def _insert_sonara_window_context(
    repository: LibraryDatabase,
    *,
    generation: int,
) -> None:
    with repository.connect() as connection:
        connection.execute(
            """
            INSERT INTO sonara(
                track_id, content_generation,
                analyzed_duration_seconds,
                intro_end_seconds, outro_start_seconds,
                leading_silence_seconds, trailing_silence_seconds,
                mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analyzed_at
            ) VALUES (1, ?, 200.0, 40.0, 170.0, 5.0, 10.0, ?, ?, ?, ?)
            """,
            (
                generation,
                np.zeros(13, dtype="<f4").tobytes(),
                np.zeros(12, dtype="<f4").tobytes(),
                np.zeros(7, dtype="<f4").tobytes(),
                ANALYZED_AT,
            ),
        )
        connection.commit()


def _target(repository: LibraryDatabase, *, generation: int = 1) -> AnalysisTarget:
    return AnalysisTarget(
        catalog_uuid=repository.catalog_uuid,
        track_id=1,
        track_uuid=TRACK_UUID,
        content_generation=generation,
    )


def _unit_vector(*, index: int = 0) -> np.ndarray:
    vector = np.zeros(MERT_EMBEDDING_DIM, dtype=np.float32)
    vector[index] = 1.0
    return vector


def _write(
    repository: LibraryDatabase,
    vector: np.ndarray,
    *,
    generation: int = 1,
) -> None:
    result = repository.save_embedding_results(
        (
            EmbeddingWrite(
                target=_target(repository, generation=generation),
                output=EmbeddingOutput(
                    family="mert",
                    vector=vector,
                    analyzed_at=ANALYZED_AT,
                ),
            ),
        )
    )
    assert len(result) == 1
    assert result[0].ok
    assert result[0].written_outputs == (AnalysisOutput("mert", "embedding"),)


def test_analysis_output_identity_is_only_family_and_output_kind() -> None:
    output = AnalysisOutput(
        analysis_family="MERT",
        output_kind="Embedding",
    )

    assert output.key == ("mert", "embedding")
    assert not hasattr(output, "contract")
    assert not hasattr(output, "contract_hash")


def test_valid_maest_embedding_output_saves_through_repository(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    vector = np.zeros(MAEST_EMBEDDING_DIM, dtype=np.float32)
    vector[0] = 1.0
    write = MaestWrite(
        target=_target(repository),
        genres=(MaestGenreScore(label="House", score=0.9),),
        syncopated_rhythm=False,
        analyzed_at=ANALYZED_AT,
        embedding=EmbeddingOutput(
            family="maest",
            vector=vector,
            analyzed_at=ANALYZED_AT,
        ),
    )

    results = repository.save_maest_results((write,))

    assert len(results) == 1
    assert results[0].ok
    assert results[0].written_outputs == (
        AnalysisOutput("maest", "analysis"),
        AnalysisOutput("maest", "embedding"),
    )
    with repository.connect_artifacts() as connection:
        row = connection.execute(
            "SELECT dim, embedding_blob FROM maest_embeddings WHERE track_id = 1"
        ).fetchone()
    assert row is not None
    assert int(row["dim"]) == MAEST_EMBEDDING_DIM
    np.testing.assert_array_equal(
        np.frombuffer(row["embedding_blob"], dtype="<f4"),
        vector,
    )


@pytest.mark.parametrize(
    ("family", "kind"),
    (("unknown", "embedding"), ("mert", "analysis")),
)
def test_analysis_output_rejects_unsupported_family_kind(
    family: str,
    kind: str,
) -> None:
    with pytest.raises(ValueError):
        AnalysisOutput(family, kind)


def test_candidate_readiness_is_keyed_by_track_generation_family_and_kind(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    output = AnalysisOutput("mert", "embedding")

    candidates = repository.list_analysis_candidates((output,))
    assert [candidate.target.track_id for candidate in candidates] == [1]
    assert candidates[0].missing_outputs == (output,)

    _write(repository, _unit_vector())

    assert repository.list_analysis_candidates((output,)) == []

    with repository.connect() as connection:
        connection.execute(
            "UPDATE tracks SET content_generation = 2 WHERE track_id = 1"
        )
        connection.commit()
    candidates = repository.list_analysis_candidates((output,))
    assert [candidate.target.content_generation for candidate in candidates] == [2]


def test_candidate_includes_current_sonara_maest_window_context(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _insert_sonara_window_context(repository, generation=1)

    candidate = repository.list_analysis_candidates(
        (AnalysisOutput("maest", "embedding"),)
    )[0]

    assert candidate.maest_window_context == MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=40.0,
        outro_start_seconds=170.0,
    )


def test_candidate_ignores_stale_sonara_maest_window_context(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _insert_sonara_window_context(repository, generation=1)
    with repository.connect() as connection:
        connection.execute(
            "UPDATE tracks SET content_generation = 2 WHERE track_id = 1"
        )
        connection.commit()

    candidate = repository.list_analysis_candidates(
        (AnalysisOutput("maest", "embedding"),)
    )[0]

    assert candidate.target.content_generation == 2
    assert candidate.maest_window_context is None


def test_repeated_write_replaces_same_family_row_without_version_identity(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    first = _unit_vector(index=0)
    second = _unit_vector(index=1)

    _write(repository, first)
    _write(repository, second)

    with repository.connect_artifacts() as connection:
        row = connection.execute(
            """
            SELECT track_id, track_uuid, content_generation, dim,
                   normalization, embedding_blob
            FROM mert_embeddings
            """
        ).fetchone()
        assert connection.execute(
            "SELECT COUNT(*) FROM mert_embeddings"
        ).fetchone()[0] == 1
    assert tuple(row.keys()) == (
        "track_id",
        "track_uuid",
        "content_generation",
        "dim",
        "normalization",
        "embedding_blob",
    )
    np.testing.assert_array_equal(
        np.frombuffer(row["embedding_blob"], dtype="<f4"),
        second,
    )


def test_stale_generation_write_is_rejected_without_overwriting_current_data(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    _write(repository, _unit_vector(index=0))
    with repository.connect() as connection:
        connection.execute(
            "UPDATE tracks SET content_generation = 2 WHERE track_id = 1"
        )
        connection.commit()

    result = repository.save_embedding_results(
        (
            EmbeddingWrite(
                target=_target(repository, generation=1),
                output=EmbeddingOutput(
                    family="mert",
                    vector=_unit_vector(index=1),
                    analyzed_at=ANALYZED_AT,
                ),
            ),
        )
    )

    assert len(result) == 1
    assert not result[0].ok
    assert "content_generation" in str(result[0].error)
    with repository.connect_artifacts() as connection:
        row = connection.execute(
            "SELECT content_generation, embedding_blob FROM mert_embeddings"
        ).fetchone()
    assert int(row["content_generation"]) == 1
    np.testing.assert_array_equal(
        np.frombuffer(row["embedding_blob"], dtype="<f4"),
        _unit_vector(index=0),
    )
