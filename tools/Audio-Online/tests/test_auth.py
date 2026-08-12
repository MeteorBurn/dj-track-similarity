from __future__ import annotations

from pathlib import Path

from metadata_enrichment.auth import authorize_lastfm
from metadata_enrichment.config import load_config


def test_lastfm_authorize_opens_consent_and_saves_session_key(tmp_path: Path) -> None:
    """Prevent a successful OAuth exchange from being discarded."""

    config_path = tmp_path / "config.toml"
    config_path.write_text("[sources.lastfm]\napi_key = 'key'\nshared_secret = 'secret'\n", encoding="utf-8")
    opened: list[str] = []

    message = authorize_lastfm(str(config_path), load_config(config_path), opener=opened.append, input_fn=lambda _: "one-time", get_json=lambda *_args, **_kwargs: {"session": {"key": "session-value"}})

    assert opened == ["https://www.last.fm/api/auth/?api_key=key"]
    assert message == "Last.fm authorization saved."
    assert 'session_key = "session-value"' in config_path.read_text(encoding="utf-8")
