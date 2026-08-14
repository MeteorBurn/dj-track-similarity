from __future__ import annotations

import pytest

from dj_track_similarity.analysis_config import (
    build_analysis_job_config,
    normalize_analysis_device,
    normalize_analysis_models,
    parse_analysis_models_text,
)
from dj_track_similarity.sonara_staging import SonaraStagingConfig


def test_normalize_analysis_models_preserves_canonical_order_and_deduplicates() -> None:
    assert normalize_analysis_models(["CLAP", "muq", "mert", "clap"]) == ("mert", "muq", "clap")


def test_default_ml_models_include_mulan_in_canonical_order() -> None:
    assert normalize_analysis_models(None) == (
        "maest",
        "mert",
        "muq",
        "mulan",
        "clap",
    )


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
    assert not hasattr(config, "sonara_outputs")


def test_build_analysis_job_config_has_no_sonara_output_selection() -> None:
    assert not hasattr(build_analysis_job_config(models=["sonara"]), "sonara_outputs")


def test_ml_jobs_require_current_sonara_but_sonara_jobs_do_not() -> None:
    assert build_analysis_job_config(
        models=["maest", "mert"],
    ).require_current_sonara
    assert not build_analysis_job_config(
        models=["sonara"],
    ).require_current_sonara


def test_sonara_mode_defaults_to_direct_and_keeps_staged_configuration(
    tmp_path,
) -> None:
    direct = build_analysis_job_config(models=["sonara"])
    staged_settings = SonaraStagingConfig(
        root=tmp_path,
        processes=4,
        rayon_threads=4,
        max_native_batch_size=4,
        stage_size=32,
    )
    staged = build_analysis_job_config(
        models=["sonara"],
        sonara_mode="staged",
        sonara_batch_size=4,
        sonara_staging_config=staged_settings,
    )

    assert direct.sonara_mode == "direct"
    assert direct.sonara_staging_config is None
    assert staged.sonara_mode == "staged"
    assert staged.sonara_staging_config == staged_settings


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
    ],
)
def test_build_analysis_job_config_rejects_values_outside_shared_ranges(kwargs: dict[str, int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_analysis_job_config(**kwargs)
