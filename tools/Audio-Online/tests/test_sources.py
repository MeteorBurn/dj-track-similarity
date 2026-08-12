from __future__ import annotations

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
