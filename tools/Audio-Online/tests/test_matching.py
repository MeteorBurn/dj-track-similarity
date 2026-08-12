from __future__ import annotations

from metadata_enrichment.matching import score_candidate
from metadata_enrichment.models import SourceRecord, TrackInput


def test_exact_title_artist_album_and_duration_is_high_confidence() -> None:
    """Catch a matcher that overlooks corroborating album/duration evidence."""

    assessment = score_candidate(
        TrackInput(title="Title", artist="Artist", album="Album", duration_seconds=402),
        SourceRecord(title="Title", artist="Artist", album="Album", duration_seconds=401),
    )

    assert assessment.confidence == "high"
    assert assessment.evidence == (
        "title exact",
        "artist exact",
        "album exact",
        "duration within 2s",
    )


def test_candidate_without_artist_or_title_is_not_matchable() -> None:
    """Prevent weak release metadata from being presented as a confident match."""

    assessment = score_candidate(TrackInput(title="Title"), SourceRecord(title="Title", artist="Artist"))

    assert assessment.confidence is None
    assert assessment.evidence == ("artist and title are required",)
