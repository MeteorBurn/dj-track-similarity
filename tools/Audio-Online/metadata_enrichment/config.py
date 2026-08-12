"""Local credential configuration for the Audio Online tool."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Mapping

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility.
    import tomli as tomllib


SUPPORTED_SOURCES = ("discogs", "musicbrainz", "lastfm", "beatport")


@dataclass(frozen=True)
class ToolConfig:
    """Validated local source configuration without a revealing repr."""

    sources: Mapping[str, Mapping[str, object]] = field(default_factory=dict, repr=False)


def load_config(path: Path) -> ToolConfig:
    """Load source settings from a local TOML file."""

    if not path.exists():
        return ToolConfig()
    with path.open("rb") as config_file:
        values = tomllib.load(config_file)
    sources = values.get("sources", {})
    if not isinstance(sources, dict):
        raise ValueError("sources must be a TOML table")
    unknown = sorted(set(sources) - set(SUPPORTED_SOURCES))
    if unknown:
        raise ValueError("unsupported source: " + ", ".join(unknown))
    for source, source_values in sources.items():
        if not isinstance(source_values, dict):
            raise ValueError(f"sources.{source} must be a TOML table")
    return ToolConfig(sources=sources)


def save_auth_data(path: Path, source: str, values: Mapping[str, str]) -> None:
    """Persist a successful authorization session without emitting its values."""

    if source not in SUPPORTED_SOURCES:
        raise ValueError(f"unsupported source: {source}")
    existing = _load_document(path)
    sources = existing.setdefault("sources", {})
    if not isinstance(sources, dict):
        raise ValueError("sources must be a TOML table")
    source_values = sources.setdefault(source, {})
    if not isinstance(source_values, dict):
        raise ValueError(f"sources.{source} must be a TOML table")
    auth_values = source_values.setdefault("auth", {})
    if not isinstance(auth_values, dict):
        raise ValueError(f"sources.{source}.auth must be a TOML table")
    for key, value in values.items():
        if not key or not isinstance(value, str):
            raise ValueError("authorization values must use non-empty string keys and values")
        auth_values[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_toml(existing), encoding="utf-8")


def _load_document(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    with path.open("rb") as config_file:
        values = tomllib.load(config_file)
    if not isinstance(values, dict):
        raise ValueError("configuration root must be a TOML table")
    return values


def _render_toml(document: Mapping[str, object]) -> str:
    sources = document.get("sources", {})
    if not isinstance(sources, Mapping):
        raise ValueError("sources must be a TOML table")
    lines: list[str] = []
    for source in sorted(sources):
        values = sources[source]
        if not isinstance(values, Mapping):
            raise ValueError(f"sources.{source} must be a TOML table")
        direct_values = {key: value for key, value in values.items() if key != "auth"}
        if direct_values:
            lines.append(f"[sources.{source}]")
            lines.extend(_render_values(direct_values))
            lines.append("")
        auth_values = values.get("auth")
        if auth_values is not None:
            if not isinstance(auth_values, Mapping):
                raise ValueError(f"sources.{source}.auth must be a TOML table")
            lines.append(f"[sources.{source}.auth]")
            lines.extend(_render_values(auth_values))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_values(values: Mapping[object, object]) -> list[str]:
    rendered: list[str] = []
    for key in sorted(values, key=str):
        value = values[key]
        if not isinstance(key, str) or not key or not isinstance(value, str):
            raise ValueError("configuration values must use non-empty string keys and string values")
        rendered.append(f"{key} = {json.dumps(value, ensure_ascii=False)}")
    return rendered
