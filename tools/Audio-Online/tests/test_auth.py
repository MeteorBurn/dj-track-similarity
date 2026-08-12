from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone

from metadata_enrichment.auth import authorize_lastfm
from metadata_enrichment.beatport_auth import authorize_beatport, check_beatport_auth, ensure_beatport_access_token
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


def test_beatport_authorize_uses_client_credentials_and_saves_tokens(tmp_path: Path, capsys) -> None:
    """Catalog OAuth must persist tokens locally without leaking them to stdout."""

    config_path = tmp_path / "config.toml"
    config_path.write_text("[sources.beatport]\nclient_id = 'id'\nclient_secret = 'secret'\n", encoding="utf-8")
    requests: list[dict[str, object]] = []

    def post_form_json(url: str, **kwargs: object) -> dict[str, object]:
        requests.append({"url": url, **kwargs})
        return {"access_token": "access-token", "refresh_token": "refresh-token", "expires_in": 36000, "scope": "catalog"}

    message = authorize_beatport(config_path, load_config(config_path), post_form_json=post_form_json, now=datetime(2026, 8, 13, tzinfo=timezone.utc))

    assert message == "Beatport authorization saved."
    assert requests == [{"url": "https://api.beatport.com/v4/auth/o/token/", "headers": {}, "fields": {"client_id": "id", "client_secret": "secret", "grant_type": "client_credentials"}}]
    saved = config_path.read_text(encoding="utf-8")
    assert 'access_token = "access-token"' in saved
    assert 'expires_at = "2026-08-13T10:00:00+00:00"' in saved
    assert "access-token" not in capsys.readouterr().out


def test_check_beatport_auth_uses_bearer_header(tmp_path: Path) -> None:
    """Token validation must be a read-only introspection request."""

    config_path = tmp_path / "config.toml"
    config_path.write_text("[sources.beatport.auth]\naccess_token = 'access-token'\n", encoding="utf-8")
    requests: list[dict[str, object]] = []

    def get_json(url: str, **kwargs: object) -> dict[str, object]:
        requests.append({"url": url, **kwargs})
        return {"active": True, "scope": "catalog"}

    result = check_beatport_auth(load_config(config_path), get_json=get_json)

    assert result == {"active": True, "scope": "catalog"}
    assert requests == [{"url": "https://api.beatport.com/v4/auth/o/introspect/", "headers": {"Authorization": "Bearer access-token"}, "params": {}}]


def test_beatport_refreshes_token_within_five_minutes_of_expiry(tmp_path: Path) -> None:
    """Prevent a long enrichment job from starting with a nearly expired token."""

    config_path = tmp_path / "config.toml"
    config_path.write_text("""[sources.beatport]
client_id = 'id'
client_secret = 'secret'

[sources.beatport.auth]
access_token = 'old-token'
refresh_token = 'refresh-token'
expires_at = '2026-08-13T10:04:00+00:00'
""", encoding="utf-8")
    requests: list[dict[str, object]] = []

    def post_form_json(url: str, **kwargs: object) -> dict[str, object]:
        requests.append({"url": url, **kwargs})
        return {"access_token": "new-token", "refresh_token": "new-refresh", "expires_in": 36000, "scope": "catalog"}

    refreshed = ensure_beatport_access_token(config_path, load_config(config_path), post_form_json=post_form_json, now=datetime(2026, 8, 13, 10, 0, tzinfo=timezone.utc))

    assert refreshed.sources["beatport"]["auth"]["access_token"] == "new-token"
    assert requests == [{"url": "https://api.beatport.com/v4/auth/o/token/", "headers": {"Authorization": "Bearer old-token"}, "fields": {"client_id": "id", "refresh_token": "refresh-token", "grant_type": "refresh_token"}}]
