from __future__ import annotations

import numpy as np

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
)
from dj_track_similarity.search import SimilaritySearch


class _Repository:
    catalog_uuid = "catalog-test"

    def __init__(self) -> None:
        self.output = AnalysisOutput("mert", "embedding")
        self.target = AnalysisTarget("catalog-test", 1, "track-1", 1)

    def active_analysis_output(self, analysis_family: str, output_kind: str):
        assert (analysis_family, output_kind) == ("mert", "embedding")
        return self.output

    def load_analysis_vectors(self, output, *, targets=None):
        assert output == self.output
        vector = np.zeros(768, dtype=np.float32)
        vector[0] = 1.0
        return (AnalysisVectorRow(self.target, self.output, vector),)


def test_embedding_search_uses_current_family_spec_without_contract_identity() -> None:
    repository = _Repository()

    search = SimilaritySearch(
        repository,
        "mert",
        analysis_output=repository.output,
    )

    assert search.resolve_targets([1]) == (repository.target,)
