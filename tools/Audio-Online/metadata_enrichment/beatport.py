"""Beatport adapter requiring an explicitly configured official endpoint."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .models import SourceResult, TrackInput


class BeatportSource:
    name = "Beatport"

    def __init__(self, *, access_token: str | None, search_url: str | None, get_json: Callable[..., Mapping[str, object]]) -> None:
        self.access_token, self.search_url, self.get_json = access_token, search_url, get_json

    def fetch(self, track: TrackInput) -> SourceResult:
        if not self.access_token or not self.search_url:
            return SourceResult(self.name, "unavailable", error="official catalog access is not configured")
        if not track.artist or not track.title:
            return SourceResult(self.name, "no_match", error="artist and title are required")
        return SourceResult(self.name, "unavailable", error="Beatport response mapping requires approved API schema")
