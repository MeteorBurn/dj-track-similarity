from __future__ import annotations

from pathlib import Path
import uuid

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    ClassifierSpecification,
    EmbeddingOutput,
    EmbeddingWrite,
    current_embedding_spec,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.evaluation.candidates import CandidateSourceContribution
from dj_track_similarity.evaluation.weighted_candidates import (
    weighted_rrf_components,
    weighted_rrf_score,
)
from dj_track_similarity.tempo_resolution import (
    confidence_aware_tempo_score,
    resolve_tempo_evidence_from_values,
)


def test_weighted_rrf_components_are_exact_and_deterministically_ordered() -> None:
    contributions = {
        "mert": CandidateSourceContribution(rank=2, score=0.99),
        "maest": CandidateSourceContribution(rank=4, score=0.01),
    }
    weights = {"mert": 0.75, "maest": 0.25}

    components = weighted_rrf_components(contributions, weights, rrf_k=60)

    assert list(components) == ["maest", "mert"]
    assert components["maest"] == pytest.approx(
        {"rank": 4, "weight": 0.25, "contribution": 0.25 / 64.0}
    )
    assert components["mert"] == pytest.approx(
        {"rank": 2, "weight": 0.75, "contribution": 0.75 / 62.0}
    )
    assert weighted_rrf_score(contributions, weights, rrf_k=60) == pytest.approx(
        0.25 / 64.0 + 0.75 / 62.0
    )


def test_weighted_rrf_missing_source_keeps_its_global_weight_penalty() -> None:
    weights = {"mert": 0.75, "maest": 0.25}
    rank = 3
    only_low_weight_source = {
        "maest": CandidateSourceContribution(rank=rank, score=0.9),
    }

    actual = weighted_rrf_score(only_low_weight_source, weights, rrf_k=60)

    assert actual == pytest.approx(0.25 / (60 + rank))
    assert actual < 1.0 / (60 + rank)


def test_zero_weight_source_has_no_effect_on_weighted_rrf() -> None:
    weights = {"mert": 1.0, "maest": 0.0}
    positive = CandidateSourceContribution(rank=2, score=0.8)
    ignored = CandidateSourceContribution(rank=1, score=1.0)

    assert weighted_rrf_score(
        {"mert": positive, "maest": ignored}, weights, 60
    ) == pytest.approx(weighted_rrf_score({"mert": positive}, weights, 60))
    assert weighted_rrf_score({"maest": ignored}, weights, 60) == 0.0


def test_current_null_bpm_confidence_is_neutral_and_does_not_promote_tag_bpm() -> None:
    candidate = resolve_tempo_evidence_from_values(
        {
            "detected_bpm": 155.0,
            "bpm_confidence": None,
            "beat_grid_stability": 1.0,
            "bpm_candidates_json": "[[155.0, 1.0]]",
        },
        tag_bpm=128.0,
    )
    reference = resolve_tempo_evidence_from_values(
        {
            "detected_bpm": 128.0,
            "bpm_confidence": 1.0,
            "beat_grid_stability": 1.0,
        },
        tag_bpm=None,
    )

    assert candidate.bpm == 155.0
    assert candidate.source == "sonara_low_confidence"
    assert candidate.reliability == 0.0
    assert confidence_aware_tempo_score(candidate, reference) == pytest.approx(0.5)


def test_classifier_feature_assembly_preserves_order_and_never_zero_fills(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = AnalysisOutput("mert", "embedding")
    db.register_analysis_outputs((output,))
    track_uuid = str(uuid.uuid4())
    with db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, 123456789, 1, ?, ?, ?)
            """,
            (
                track_uuid,
                f"C:/music/{track_uuid}.wav",
                "2026-07-24T13:00:00.000000Z",
                "2026-07-24T13:00:00.000000Z",
                "2026-07-24T13:00:00.000000Z",
            ),
        )
        track_id = int(cursor.lastrowid)
    target = AnalysisTarget(
        catalog_uuid=db.catalog_uuid,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=1,
    )
    vector = np.zeros(current_embedding_spec("mert").dimension, dtype=np.float32)
    vector[:3] = (1.0, 2.0, 3.0)
    vector /= np.linalg.norm(vector)
    assert db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family="mert",
                    vector=vector,
                    analyzed_at="2026-07-24T13:00:00.000000Z",
                ),
            ),
        )
    )[0].ok

    feature_names = ("mert:2", "mert:0", "mert:1")
    specification = ClassifierSpecification(
        classifier_key="ordered_classifier",
        feature_set="mert-features",
        feature_names=feature_names,
        required_outputs=(output,),
        label_order=("negative", "positive"),
        positive_label="positive",
    )
    rows = tuple(
        row
        for _candidate, row in db.load_classifier_work_batch(
            specification,
            after_track_id=0,
            limit=1,
        )
    )

    assert len(rows) == 1
    assert rows[0].target == target
    assert rows[0].vector.tolist() == pytest.approx(
        [float(vector[2]), float(vector[0]), float(vector[1])]
    )
