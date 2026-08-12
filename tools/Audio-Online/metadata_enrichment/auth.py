"""Explicit documented authorization flows for sources that support them."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from pathlib import Path
from urllib.parse import urlencode

from .config import ToolConfig, save_auth_data


def authorize_lastfm(
    config_path: str, config: ToolConfig, *, opener: Callable[[str], None], input_fn: Callable[[str], str], get_json: Callable[..., Mapping[str, object]]
) -> str:
    """Open Last.fm consent and exchange its one-time token for a session key."""
    values = config.sources.get("lastfm", {})
    api_key = values.get("api_key") if isinstance(values, Mapping) else None
    secret = values.get("shared_secret") if isinstance(values, Mapping) else None
    if not isinstance(api_key, str) or not api_key or not isinstance(secret, str) or not secret:
        raise ValueError("Last.fm api_key and shared_secret are required in config.toml")
    opener(f"https://www.last.fm/api/auth/?{urlencode({'api_key': api_key})}")
    token = input_fn("Paste the Last.fm authorization token: ").strip()
    if not token:
        raise ValueError("Last.fm authorization token is required")
    params = {"api_key": api_key, "method": "auth.getSession", "token": token}
    signature_text = "".join(f"{key}{params[key]}" for key in sorted(params)) + secret
    params["api_sig"] = hashlib.md5(signature_text.encode("utf-8")).hexdigest()  # noqa: S324 - required by Last.fm protocol.
    payload = get_json("https://ws.audioscrobbler.com/2.0/", headers={}, params={**params, "format": "json"})
    session = payload.get("session")
    key = session.get("key") if isinstance(session, Mapping) else None
    if not isinstance(key, str) or not key:
        raise ValueError("Last.fm did not return a session key")
    save_auth_data(Path(config_path), "lastfm", {"session_key": key})
    return "Last.fm authorization saved."
