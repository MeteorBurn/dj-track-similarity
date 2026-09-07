from pathlib import Path
import sys

import numpy as np

from dj_track_similarity.analysis_models import AnalysisOutput, EmbeddingFamilySpec
from dj_track_similarity.search import engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import text_prompt_benchmark as benchmark


def test_negative_poolings_match_their_names_and_production_factorization(monkeypatch):
    monkeypatch.setattr(
        engine, "current_embedding_spec", lambda _family: EmbeddingFamilySpec(2, "l2")
    )
    output = AnalysisOutput("clap", "embedding")
    matrix = np.array([[1, 0]], dtype=np.float32)
    negatives = [np.array([1, 0], dtype=np.float32), np.array([0, 1], dtype=np.float32)]
    poolings = dict(
        benchmark._negative_poolings(matrix, output=output, negative_vectors=negatives)
    )
    assert poolings["max"].tolist() == [1.0]
    assert poolings["top2-mean"].tolist() == [0.5]
    positive, penalty, score, weight = engine._contrast_vector_scores(
        matrix,
        output=output,
        positive_vectors=[matrix[0]],
        negative_vectors=negatives,
        negative_weight=0.5,
    )
    assert np.allclose(score, positive - weight * poolings["top2-mean"])
    assert score.tolist() == [0.75]
    assert penalty.tolist() == [0.5]
    for bank, expected in (([], [0.0]), (negatives[:1], [1.0])):
        edge = dict(
            benchmark._negative_poolings(matrix, output=output, negative_vectors=bank)
        )
        assert edge["max"].tolist() == edge["top2-mean"].tolist() == expected
