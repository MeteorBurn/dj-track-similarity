"""Last.fm community tag adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .models import SourceRecord, SourceResult, TrackInput


class LastFmSource:
    name = "Last.fm"

    def __init__(self, *, api_key: str | None, get_json: Callable[..., Mapping[str, object]]) -> None:
        self.api_key, self.get_json = api_key, get_json

    def fetch(self, track: TrackInput) -> SourceResult:
        if not self.api_key: return SourceResult(self.name, "not_configured")
        if not track.artist or not track.title: return SourceResult(self.name, "no_match", error="artist and title are required")
        payload = self.get_json("https://ws.audioscrobbler.com/2.0/", params={"method": "track.getTopTags", "artist": track.artist, "track": track.title, "api_key": self.api_key, "format": "json"}, headers={})
        rows = payload.get("toptags", {}).get("tag", []) if isinstance(payload.get("toptags"), Mapping) else []
        tags = tuple(row["name"] for row in rows if isinstance(row, Mapping) and isinstance(row.get("name"), str)) if isinstance(rows, list) else ()
        return SourceResult(self.name, "matched" if tags else "no_match", SourceRecord(title=track.title, artist=track.artist, tags=tags, record_url=f"https://www.last.fm/music/{track.artist}/_/{track.title}"))
