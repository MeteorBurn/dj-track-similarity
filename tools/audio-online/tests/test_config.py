from __future__ import annotations

from pathlib import Path

import pytest

from metadata_enrichment.config import load_config, save_auth_data


def test_load_config_rejects_unknown_configured_source(tmp_path: Path) -> None:
    """Prevent silently sending a credential to an unimplemented service."""

    config_path = tmp_path / "config.toml"
    config_path.write_text("[sources.unknown]\ntoken = 'secret'\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported source: unknown"):
        load_config(config_path)


def test_save_auth_data_persists_session_without_printing_secret(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Prevent OAuth session material from leaking into normal CLI output."""

    config_path = tmp_path / "config.toml"

    save_auth_data(config_path, "lastfm", {"session_key": "not-for-output"})

    assert "not-for-output" not in capsys.readouterr().out
    assert "session_key = \"not-for-output\"" in config_path.read_text(encoding="utf-8")
