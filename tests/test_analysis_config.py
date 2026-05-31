from __future__ import annotations

import pytest

from dj_track_similarity.analysis_config import normalize_analysis_models, parse_analysis_models_text


def test_normalize_analysis_models_preserves_canonical_order_and_deduplicates() -> None:
    assert normalize_analysis_models(["CLAP", "mert", "clap", "sonara"]) == ("sonara", "mert", "clap")


def test_normalize_analysis_models_rejects_empty_and_unknown_values() -> None:
    with pytest.raises(ValueError, match="At least one analysis model"):
        normalize_analysis_models([])

    with pytest.raises(ValueError, match="Unknown analysis model: unknown"):
        normalize_analysis_models(["unknown"])


def test_parse_analysis_models_text_uses_same_rules() -> None:
    assert parse_analysis_models_text("mert, maest, mert") == ("maest", "mert")
