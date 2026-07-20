from __future__ import annotations

import pytest

from dj_track_similarity.analysis_config import (
    DEFAULT_SONARA_OUTPUTS,
    build_analysis_job_config,
    normalize_analysis_device,
    normalize_analysis_models,
    parse_analysis_models_text,
)


def test_normalize_analysis_models_preserves_canonical_order_and_deduplicates() -> None:
    assert normalize_analysis_models(["CLAP", "muq", "mert", "clap"]) == ("mert", "muq", "clap")


def test_normalize_analysis_models_rejects_empty_and_unknown_values() -> None:
    with pytest.raises(ValueError, match="At least one analysis model"):
        normalize_analysis_models([])

    with pytest.raises(ValueError, match="Unknown analysis model: unknown"):
        normalize_analysis_models(["unknown"])

    with pytest.raises(ValueError, match="SONARA analysis must run alone"):
        normalize_analysis_models(["sonara", "mert"])


def test_parse_analysis_models_text_uses_same_rules() -> None:
    assert parse_analysis_models_text("mert, maest, mert") == ("maest", "mert")


def test_normalize_analysis_device_accepts_canonical_torch_devices() -> None:
    assert normalize_analysis_device(None) == "auto"
    assert normalize_analysis_device(" CPU ") == "cpu"
    assert normalize_analysis_device("cuda") == "cuda"


def test_normalize_analysis_device_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="Unknown torch device: gpu"):
        normalize_analysis_device("gpu")


def test_build_analysis_job_config_normalizes_shared_cli_api_values() -> None:
    config = build_analysis_job_config(
        models=["clap", "MERT"],
        limit=12,
        device=" CPU ",
        top_k=4,
        track_batch_size=3,
        inference_batch_size=18,
    )

    assert config.models == ("mert", "clap")
    assert config.limit == 12
    assert config.device == "cpu"
    assert config.top_k == 4
    assert config.track_batch_size == 3
    assert config.inference_batch_size == 18
    assert config.sonara_outputs == ()


def test_build_analysis_job_config_allows_all_explicit_sonara_outputs() -> None:
    assert build_analysis_job_config(
        models=["sonara"],
        sonara_outputs=["representations", "core", "timeline"],
    ).sonara_outputs == ("core", "timeline", "representations")


def test_build_analysis_job_config_defaults_sonara_to_core() -> None:
    assert build_analysis_job_config(models=["sonara"]).sonara_outputs == DEFAULT_SONARA_OUTPUTS


def test_build_analysis_job_config_rejects_invalid_sonara_outputs() -> None:
    with pytest.raises(ValueError, match="SONARA outputs can only"):
        build_analysis_job_config(models=["mert"], sonara_outputs=["timeline"])
    with pytest.raises(ValueError, match="At least one SONARA output"):
        build_analysis_job_config(models=["sonara"], sonara_outputs=[])


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"top_k": 0}, "top_k must be between 1 and 10"),
        ({"track_batch_size": 65}, "track_batch_size must be between 1 and 64"),
        ({"inference_batch_size": 0}, "inference_batch_size must be between 1 and 128"),
    ],
)
def test_build_analysis_job_config_rejects_values_outside_shared_ranges(kwargs: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_analysis_job_config(**kwargs)
