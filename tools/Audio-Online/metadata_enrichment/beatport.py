"""Beatport v4 Catalog Search adapter using documented bearer authentication."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .matching import score_candidate
from .models import SourceRecord, SourceResult, TrackInput


CATALOG_SEARCH_URL = "https://api.beatport.com/v4/catalog/search/"


class BeatportSource:
    name = "Beatport"

    def __init__(self, *, access_token: str | None, get_json: Callable[..., Mapping[str, object]]) -> None:
        self.access_token, self.get_json = access_token, get_json

    def fetch(self, track: TrackInput) -> SourceResult:
        if not self.access_token:
            return SourceResult(self.name, "unavailable", error="official catalog access is not configured")
        if not track.artist or not track.title:
            return SourceResult(self.name, "no_match", error="artist and title are required")
        payload = self.get_json(
            CATALOG_SEARCH_URL,
            headers={"Authorization": f"Bearer {self.access_token}"},
            params={"q": track.track_name, "type": "tracks", "artist_name": track.artist, "per_page": "5"},
        )
        rows = payload.get("results")
        if not isinstance(rows, list):
            return SourceResult(self.name, "unavailable", error="catalog search response has no results list")
        candidates = [_record(item) for item in rows if isinstance(item, Mapping)]
        candidates = [candidate for candidate in candidates if candidate is not None]
        if not candidates:
            return SourceResult(self.name, "no_match")
        record = max(candidates, key=lambda candidate: score_candidate(track, candidate).score)
        assessment = score_candidate(track, record)
        if assessment.confidence is None:
            return SourceResult(self.name, "no_match")
        return SourceResult(self.name, "matched", record)


def _record(item: Mapping[str, object]) -> SourceRecord | None:
    title = _text(item, "name") or _text(item, "title")
    artist = _artists(item.get("artists")) or _text(item, "artist_name")
    record_id = item.get("id")
    if not title or not artist or record_id is None:
        return None
    release = item.get("release")
    release_values = release if isinstance(release, Mapping) else {}
    label_values = release_values.get("label")
    label = _label(label_values) or _text(item, "label_name")
    genre = _label(item.get("genre")) or _text(item, "genre_name")
    subgenre = _label(item.get("subgenre")) or _label(item.get("sub_genre"))
    return SourceRecord(
        title=title,
        artist=artist,
        album=_text(release_values, "name") or _text(item, "release_name"),
        year=_year(_text(release_values, "publish_date") or _text(item, "publish_date")),
        label=label,
        genres=(genre,) if genre else (),
        styles=(subgenre,) if subgenre else (),
        record_type="track",
        record_id=str(record_id),
        record_url=_text(item, "url"),
    )


def _text(value: object, key: str) -> str | None:
    return value.get(key) if isinstance(value, Mapping) and isinstance(value.get(key), str) and value.get(key) else None


def _label(value: object) -> str | None:
    return _text(value, "name") if isinstance(value, Mapping) else None


def _artists(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    names = tuple(_text(item, "name") for item in value if _text(item, "name"))
    return "; ".join(names) if names else None


def _year(value: str | None) -> int | None:
    if value and len(value) >= 4 and value[:4].isdigit():
        return int(value[:4])
    return None
