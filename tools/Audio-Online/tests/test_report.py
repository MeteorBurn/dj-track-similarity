from __future__ import annotations

from metadata_enrichment.models import LocalEvidence, SourceRecord, SourceResult, TrackInput
from metadata_enrichment.report import build_report_contract


def test_contract_places_maest_last_and_joins_values_with_semicolon() -> None:
    """Prevent report regressions that mix sources or drop MAEST confidence."""

    contract = build_report_contract(
        [(TrackInput(artist="Artist", title="Title"), LocalEvidence(("Electronic", "Dance"), (("House", .81), ("Techno", .64), ("Electronic", .52))), (SourceResult("Discogs", "matched", SourceRecord(genres=("Electronic",), styles=("Melodic Techno",))),))],
        ("Discogs",),
    )

    assert contract["columns"] == ["Field", "Local tags", "Discogs", "MAEST"]
    block = contract["tracks"][0]["rows"]
    assert block["Genre"]["MAEST"] == "House (81%); Techno (64%); Electronic (52%)"
    assert block["Genre"]["Local tags"] == "Electronic; Dance"
    assert block["Style"]["MAEST"] == ""


def test_contract_keeps_source_provenance_and_match_reason() -> None:
    """Make a service result auditable rather than a merged genre claim."""

    contract = build_report_contract(
        [(
            TrackInput(artist="Artist", title="Title", album="Release", year=2024, duration_seconds=402),
            LocalEvidence(),
            (SourceResult(
                "Discogs", "matched",
                SourceRecord(title="Title", artist="Artist", album="Release", year=2024,
                             duration_seconds=402, record_type="release", record_id="123",
                             record_url="https://example.test/release/123"),
                queried_at="2026-08-13T12:00:00+00:00",
            ),),
        )],
        ("Discogs",),
    )

    rows = contract["tracks"][0]["rows"]
    assert rows["Record"]["Discogs"] == "release"
    assert rows["Record ID"]["Discogs"] == "123"
    assert rows["URL"]["Discogs"] == "https://example.test/release/123"
    assert rows["Queried at"]["Discogs"] == "2026-08-13T12:00:00+00:00"
    assert rows["Match confidence"]["Discogs"] == "high"
    assert "title exact" in rows["Match evidence"]["Discogs"]
