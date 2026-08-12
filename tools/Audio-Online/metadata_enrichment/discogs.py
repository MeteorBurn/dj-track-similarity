"""Discogs database adapter using only its documented API surface."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .models import SourceRecord, SourceResult, TrackInput


class DiscogsSource:
    name = "Discogs"

    def __init__(self, *, token: str | None, get_json: Callable[..., Mapping[str, object]]) -> None:
        self.token = token
        self.get_json = get_json

    def fetch(self, track: TrackInput) -> SourceResult:
        if not self.token:
            return SourceResult(self.name, "not_configured")
        if not track.artist or not track.title:
            return SourceResult(self.name, "no_match", error="artist and title are required")
        headers = {"Authorization": f"Discogs token={self.token}", "User-Agent": "AudioOnline/0.1"}
        search = self.get_json("https://api.discogs.com/database/search", headers=headers, params={"q": track.track_name, "type": "release"})
        results = search.get("results")
        if not isinstance(results, list) or not results or not isinstance(results[0], Mapping):
            return SourceResult(self.name, "no_match")
        release_id = results[0].get("id")
        if not isinstance(release_id, int):
            return SourceResult(self.name, "no_match")
        release = self.get_json(f"https://api.discogs.com/releases/{release_id}", headers=headers, params={})
        record = SourceRecord(
            title=str(release.get("title") or ""), artist=track.artist, album=str(release.get("title") or "") or None,
            year=release.get("year") if isinstance(release.get("year"), int) else None,
            country=str(release.get("country") or "") or None,
            label=_first_label(release.get("labels")), genres=_strings(release.get("genres")), styles=_strings(release.get("styles")),
            duration_seconds=_track_duration(release.get("tracklist"), track.title), record_id=str(release_id),
            record_url=f"https://www.discogs.com/release/{release_id}",
        )
        return SourceResult(self.name, "matched", record=record)


def _strings(value: object) -> tuple[str, ...]:
    return tuple(item for item in value if isinstance(item, str) and item) if isinstance(value, list) else ()


def _first_label(value: object) -> str | None:
    if isinstance(value, list) and value and isinstance(value[0], Mapping) and isinstance(value[0].get("name"), str):
        return value[0]["name"]
    return None


def _track_duration(value: object, title: str) -> float | None:
    if not isinstance(value, list): return None
    for item in value:
        if isinstance(item, Mapping) and item.get("title") == title and isinstance(item.get("duration"), str):
            parts = item["duration"].split(":")
            if len(parts) == 2 and all(part.isdigit() for part in parts): return int(parts[0]) * 60 + int(parts[1])
    return None
