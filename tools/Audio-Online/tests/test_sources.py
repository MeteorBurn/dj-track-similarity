from __future__ import annotations

import pytest

from metadata_enrichment.discogs import DiscogsSource
from metadata_enrichment.lastfm import LastFmSource
from metadata_enrichment.beatport import BeatportSource
from metadata_enrichment.musicbrainz import MusicBrainzSource
from metadata_enrichment.models import SourceResult, TrackInput
from metadata_enrichment.sources import collect_source_results


class ErroringSource:
    name = "Discogs"

    def fetch(self, track: TrackInput) -> SourceResult:
        raise RuntimeError("temporary outage")


class MatchingSource:
    name = "MusicBrainz"

    def fetch(self, track: TrackInput) -> SourceResult:
        return SourceResult(name=self.name, status="matched")


def test_source_error_does_not_block_next_source() -> None:
    """Prevent a single unavailable source from suppressing other evidence."""

    results = collect_source_results(TrackInput(title="Title", artist="Artist"), (ErroringSource(), MatchingSource()))

    assert [result.status for result in results] == ["error", "matched"]
    assert results[0].error == "temporary outage"


def test_discogs_uses_styles_as_genre_evidence() -> None:
    """Discogs styles are the source's useful genre granularity."""

    calls: list[str] = []

    def get_json(url: str, **_: object) -> dict[str, object]:
        calls.append(url)
        if url.endswith("/database/search"):
            return {"results": [{"id": 123, "title": "Artist - Title"}]}
        return {
            "id": 123,
            "title": "Release",
            "genres": ["Electronic", "Dance"],
            "styles": ["Melodic Techno"],
            "country": "Germany",
            "year": 2024,
            "labels": [{"name": "Label"}],
            "tracklist": [{"title": "Title", "duration": "6:42"}],
        }

    result = DiscogsSource(token="token", get_json=get_json).fetch(TrackInput(artist="Artist", title="Title"))

    assert result.status == "matched"
    assert result.record is not None
    assert result.record.genres == ("Melodic Techno",)
    assert result.record.styles == ()
    assert len(calls) == 2


def test_lastfm_without_api_key_is_not_configured() -> None:
    """Prevent Last.fm requests that would fail with an absent API key."""

    result = LastFmSource(api_key=None, get_json=lambda *_args, **_kwargs: {}).fetch(
        TrackInput(artist="Artist", title="Title")
    )

    assert result.status == "not_configured"


def test_musicbrainz_requires_meaningful_user_agent() -> None:
    """Prevent anonymous calls that violate MusicBrainz access guidance."""

    result = MusicBrainzSource(user_agent=None, get_json=lambda *_args, **_kwargs: {}).fetch(TrackInput(artist="Artist", title="Title"))

    assert result.status == "not_configured"


def test_musicbrainz_waits_between_requests() -> None:
    """Respect MusicBrainz's one-request-per-second public API limit."""

    clock_values = iter((10.0, 10.4, 11.0))
    waits: list[float] = []
    source = MusicBrainzSource(
        user_agent="Audio Online/0.1 (contact@example.test)",
        get_json=lambda *_args, **_kwargs: {"recordings": []},
        clock=lambda: next(clock_values), sleeper=waits.append,
    )

    source.fetch(TrackInput(artist="Artist", title="One"))
    source.fetch(TrackInput(artist="Artist", title="Two"))

    assert waits == pytest.approx([0.6])


def test_beatport_without_official_endpoint_is_unavailable() -> None:
    """Prevent an undocumented storefront scraping fallback."""

    result = BeatportSource(access_token=None, get_json=lambda *_args, **_kwargs: {}).fetch(TrackInput(artist="Artist", title="Title"))

    assert result.status == "unavailable"


def test_beatport_maps_catalog_track_and_keeps_genre_separate_from_subgenre() -> None:
    """Beatport v4 Catalog Search must become independent source evidence."""

    calls: list[dict[str, object]] = []

    def get_json(url: str, **kwargs: object) -> dict[str, object]:
        calls.append({"url": url, **kwargs})
        return {"results": [{
            "id": 123,
            "name": "Title",
            "artists": [{"name": "Artist"}],
            "release": {"name": "Release", "label": {"name": "Label"}, "publish_date": "2024-04-30"},
            "genre": {"name": "Techno"},
            "subgenre": {"name": "Peak Time / Driving"},
            "length_ms": 402000,
            "url": "https://www.beatport.com/track/title/123",
        }]}

    result = BeatportSource(access_token="token", get_json=get_json).fetch(TrackInput(artist="Artist", title="Title"))

    assert result.status == "matched"
    assert result.record is not None
    assert result.record.genres == ("Techno",)
    assert result.record.styles == ("Peak Time / Driving",)
    assert result.record.record_id == "123"
    assert calls == [{"url": "https://api.beatport.com/v4/catalog/search/", "headers": {"Authorization": "Bearer token"}, "params": {"q": "Artist — Title", "type": "tracks", "artist_name": "Artist", "per_page": "5"}}]
