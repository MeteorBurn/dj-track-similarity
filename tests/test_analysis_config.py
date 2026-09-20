from __future__ import annotations

from pathlib import Path

import pytest

from dj_track_similarity.analysis.ml_staging import MLStagingConfig
from dj_track_similarity.analysis.config import (
    build_analysis_job_config,
    normalize_analysis_device,
    normalize_analysis_models,
    parse_analysis_models_text,
    parse_sonara_bpm_range,
)


def test_sonara_bpm_range_is_one_argument_holding_a_preset_or_an_octave_wide_range() -> None:
    assert parse_sonara_bpm_range(None) is None
    assert parse_sonara_bpm_range("mixed-in-key") == (79.0, 192.0)
    assert parse_sonara_bpm_range(" Rekordbox ") == (70.0, 180.0)
    assert parse_sonara_bpm_range("virtual-dj") == (80.0, 240.0)
    for value, expected in (("70-140", (70.0, 140.0)), ("50 - 100", (50.0, 100.0)), ("90-180", (90.0, 180.0))):
        assert parse_sonara_bpm_range(value) == expected
    for value, message in (
        ("100-150", "at least twice"),
        ("techno", "must be a preset"),
        ("70", "must be a preset"),
        ("70-140-280", "must be a preset"),
        ("", "must be a preset"),
    ):
        with pytest.raises(ValueError, match=message):
            parse_sonara_bpm_range(value)


def test_normalize_analysis_models_preserves_canonical_order_and_deduplicates() -> None:
    assert normalize_analysis_models(["CLAP", "muq", "mert_v2", "clap"]) == ("mert_v2", "muq", "clap")


def test_normalize_analysis_models_rejects_empty_and_unknown_values() -> None:
    with pytest.raises(ValueError, match="At least one analysis model"):
        normalize_analysis_models([])

    with pytest.raises(ValueError, match="Unknown analysis model: unknown"):
        normalize_analysis_models(["unknown"])

    with pytest.raises(ValueError, match="SONARA analysis must run alone"):
        normalize_analysis_models(["sonara", "mert_v2"])


def test_parse_analysis_models_text_uses_same_rules() -> None:
    assert parse_analysis_models_text("mert_v2, maest, mert_v2") == ("maest", "mert_v2")


def test_normalize_analysis_device_accepts_canonical_torch_devices() -> None:
    assert normalize_analysis_device(None) == "auto"
    assert normalize_analysis_device(" CPU ") == "cpu"
    assert normalize_analysis_device("cuda") == "cuda"


def test_normalize_analysis_device_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="Unknown torch device: gpu"):
        normalize_analysis_device("gpu")


def test_build_analysis_job_config_normalizes_shared_cli_api_values() -> None:
    config = build_analysis_job_config(
        models=["clap", "MERT_V2"],
        limit=12,
        device=" CPU ",
        top_k=4,
        track_batch_size=3,
        inference_batch_size=18,
    )

    assert config.models == ("mert_v2", "clap")
    assert config.limit == 12
    assert config.device == "cpu"
    assert config.top_k == 4
    assert config.track_batch_size == 3
    assert config.inference_batch_size == 18
    assert not hasattr(config, "sonara_outputs")


def test_ml_jobs_require_current_sonara_but_sonara_jobs_do_not() -> None:
    assert build_analysis_job_config(
        models=["maest", "mert_v2"],
    ).require_current_sonara
    assert not build_analysis_job_config(
        models=["sonara"],
    ).require_current_sonara


def test_sonara_mode_rejects_unknown_or_incomplete_staged_configuration() -> None:
    with pytest.raises(ValueError, match="Unknown SONARA analysis mode: turbo"):
        build_analysis_job_config(models=["sonara"], sonara_mode="turbo")
    with pytest.raises(ValueError, match="Staged SONARA mode requires staging settings"):
        build_analysis_job_config(models=["sonara"], sonara_mode="staged")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"top_k": 0}, "top_k must be between 1 and 10"),
        ({"track_batch_size": 65}, "track_batch_size must be between 1 and 64"),
        ({"inference_batch_size": 0}, "inference_batch_size must be between 1 and 128"),
        ({"sonara_batch_size": 17}, "sonara_batch_size must be between 1 and 16"),
        # A setting of the other layer is refused rather than silently ignored.
        ({"sonara_bpm_min": 70.0, "sonara_bpm_max": 140.0}, "BPM range applies only to SONARA"),
        (
            {"models": ["sonara"], "ml_staging_config": MLStagingConfig(root=Path("staging"))},
            "ML staged mode applies only to ML models",
        ),
    ],
)
def test_build_analysis_job_config_rejects_out_of_range_or_other_layer_settings(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        build_analysis_job_config(**kwargs)
