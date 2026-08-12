"""Beatport v4 OAuth lifecycle using documented non-password grants only."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import ToolConfig, load_config, save_auth_data


TOKEN_URL = "https://api.beatport.com/v4/auth/o/token/"
INTROSPECT_URL = "https://api.beatport.com/v4/auth/o/introspect/"
REFRESH_WINDOW = timedelta(minutes=5)
JsonGet = Callable[..., Mapping[str, object]]
FormPost = Callable[..., Mapping[str, object]]


def authorize_beatport(
    config_path: Path, config: ToolConfig, *, post_form_json: FormPost, now: datetime | None = None
) -> str:
    """Obtain a Beatport catalog token through the client-credentials grant."""

    client_id, client_secret = _credentials(config)
    payload = post_form_json(
        TOKEN_URL,
        headers={},
        fields={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
    )
    _save_token_response(config_path, payload, now=now or datetime.now(timezone.utc))
    return "Beatport authorization saved."


def check_beatport_auth(config: ToolConfig, *, get_json: JsonGet) -> Mapping[str, object]:
    """Return Beatport's read-only token introspection response."""

    token = _access_token(config)
    return get_json(INTROSPECT_URL, headers={"Authorization": f"Bearer {token}"}, params={})


def ensure_beatport_access_token(
    config_path: Path, config: ToolConfig, *, post_form_json: FormPost, now: datetime | None = None
) -> ToolConfig:
    """Return locally persisted OAuth state with at least five minutes remaining."""

    current_time = now or datetime.now(timezone.utc)
    auth = _auth_values(config)
    token = auth.get("access_token")
    expiry = _expiry(auth.get("expires_at"))
    if isinstance(token, str) and token and expiry is not None and expiry - current_time > REFRESH_WINDOW:
        return config
    client_id, client_secret = _credentials(config)
    refresh_token = auth.get("refresh_token")
    if isinstance(token, str) and token and isinstance(refresh_token, str) and refresh_token:
        payload = post_form_json(
            TOKEN_URL,
            headers={"Authorization": f"Bearer {token}"},
            fields={"client_id": client_id, "refresh_token": refresh_token, "grant_type": "refresh_token"},
        )
    else:
        payload = post_form_json(
            TOKEN_URL,
            headers={},
            fields={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
        )
    _save_token_response(config_path, payload, now=current_time)
    return load_config(config_path)


def _credentials(config: ToolConfig) -> tuple[str, str]:
    values = config.sources.get("beatport", {})
    client_id = values.get("client_id") if isinstance(values, Mapping) else None
    client_secret = values.get("client_secret") if isinstance(values, Mapping) else None
    if not isinstance(client_id, str) or not client_id or not isinstance(client_secret, str) or not client_secret:
        raise ValueError("Beatport client_id and client_secret are required in config.toml")
    return client_id, client_secret


def _access_token(config: ToolConfig) -> str:
    token = _auth_values(config).get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("Beatport access token is required; run authorize beatport")
    return token


def _auth_values(config: ToolConfig) -> Mapping[str, object]:
    values = config.sources.get("beatport", {})
    auth = values.get("auth", {}) if isinstance(values, Mapping) else {}
    return auth if isinstance(auth, Mapping) else {}


def _save_token_response(config_path: Path, payload: Mapping[str, object], *, now: datetime) -> None:
    token = payload.get("access_token")
    expires_in = payload.get("expires_in")
    if not isinstance(token, str) or not token or not isinstance(expires_in, int) or isinstance(expires_in, bool) or expires_in <= 0:
        raise ValueError("Beatport token response is missing access_token or expires_in")
    values = {"access_token": token, "expires_at": (now + timedelta(seconds=expires_in)).isoformat()}
    for key in ("refresh_token", "scope"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            values[key] = value
    save_auth_data(config_path, "beatport", values)


def _expiry(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
