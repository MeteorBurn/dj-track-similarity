"""MusicBrainz public recording search adapter."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from time import monotonic, sleep

from .models import SourceRecord, SourceResult, TrackInput


class MusicBrainzSource:
    name = "MusicBrainz"
    minimum_interval_seconds = 1.0

    def __init__(
        self, *, user_agent: str | None, get_json: Callable[..., Mapping[str, object]],
        clock: Callable[[], float] = monotonic, sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.user_agent, self.get_json = user_agent, get_json
        self.clock, self.sleeper = clock, sleeper
        self._last_request_at: float | None = None

    def fetch(self, track: TrackInput) -> SourceResult:
        if not self.user_agent:
            return SourceResult(self.name, "not_configured")
        if not track.artist or not track.title:
            return SourceResult(self.name, "no_match", error="artist and title are required")
        if self._last_request_at is not None:
            wait = self.minimum_interval_seconds - (self.clock() - self._last_request_at)
            if wait > 0:
                self.sleeper(wait)
        self._last_request_at = self.clock()
        query = f'artist:"{track.artist}" AND recording:"{track.title}"'
        payload = self.get_json("https://musicbrainz.org/ws/2/recording/", headers={"User-Agent": self.user_agent}, params={"query": query, "fmt": "json", "limit": "5"})
        rows = payload.get("recordings")
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], Mapping):
            return SourceResult(self.name, "no_match")
        item = rows[0]
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        names = tuple(tag["name"] for tag in tags if isinstance(tag, Mapping) and isinstance(tag.get("name"), str))
        recording_id = item.get("id")
        return SourceResult(self.name, "matched", SourceRecord(title=str(item.get("title") or track.title), artist=track.artist, tags=names, record_type="recording", record_id=str(recording_id) if recording_id else None, record_url=f"https://musicbrainz.org/recording/{recording_id}" if recording_id else None))
