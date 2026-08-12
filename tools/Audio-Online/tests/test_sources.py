from __future__ import annotations

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


def test_discogs_keeps_genres_and_styles_separate() -> None:
    """Prevent Discogs styles from being silently merged into genre evidence."""

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
    assert result.record.genres == ("Electronic", "Dance")
    assert result.record.styles == ("Melodic Techno",)
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


def test_beatport_without_official_endpoint_is_unavailable() -> None:
    """Prevent an undocumented storefront scraping fallback."""

    result = BeatportSource(access_token=None, search_url=None, get_json=lambda *_args, **_kwargs: {}).fetch(TrackInput(artist="Artist", title="Title"))

    assert result.status == "unavailable"
