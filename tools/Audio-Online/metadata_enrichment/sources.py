"""Source collection that preserves per-provider failures."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime, timezone
from typing import Protocol

from .models import SourceResult, TrackInput
from .config import ToolConfig
from .discogs import DiscogsSource
from .lastfm import LastFmSource
from .musicbrainz import MusicBrainzSource
from .beatport import BeatportSource
from .http import get_json


class MetadataSource(Protocol):
    name: str

    def fetch(self, track: TrackInput) -> SourceResult: ...


def collect_source_results(track: TrackInput, sources: Iterable[MetadataSource]) -> tuple[SourceResult, ...]:
    """Fetch every source and turn source-local faults into reportable results."""

    results: list[SourceResult] = []
    for source in sources:
        queried_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            results.append(replace(source.fetch(track), queried_at=queried_at))
        except Exception as error:
            results.append(SourceResult(name=source.name, status="error", error=str(error), queried_at=queried_at))
    return tuple(results)


def source_registry(config: ToolConfig) -> tuple[MetadataSource, ...]:
    """Create every report column in a stable source order."""
    values = config.sources
    discogs = values.get("discogs", {})
    musicbrainz = values.get("musicbrainz", {})
    lastfm = values.get("lastfm", {})
    beatport = values.get("beatport", {})
    return (
        DiscogsSource(token=_text(discogs, "token"), get_json=get_json),
        MusicBrainzSource(user_agent=_text(musicbrainz, "user_agent"), get_json=get_json),
        LastFmSource(api_key=_text(lastfm, "api_key"), get_json=get_json),
        BeatportSource(access_token=_text(beatport, "access_token"), search_url=_text(beatport, "search_url"), get_json=get_json),
    )


def _text(values: object, key: str) -> str | None:
    return values.get(key) if isinstance(values, dict) and isinstance(values.get(key), str) and values.get(key) else None
