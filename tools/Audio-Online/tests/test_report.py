from __future__ import annotations

from metadata_enrichment.models import LocalEvidence, SourceRecord, SourceResult, TrackInput
from metadata_enrichment.report import build_report_contract


def test_contract_places_maest_last_and_joins_values_with_semicolon() -> None:
    """One track must occupy one row with source-qualified keys."""

    contract = build_report_contract(
        [(TrackInput(artist="Artist", title="Title"), LocalEvidence(("Electronic", "Dance"), (("House", .81), ("Techno", .64), ("Electronic", .52))), (SourceResult("Discogs", "matched", SourceRecord(genres=("Electronic",), styles=("Melodic Techno",))),))],
        ("Discogs",),
    )

    assert contract["columns"] == [
        "Track Name", "Local Title", "Local Artist", "Local Album", "Local Year", "Local Country", "Local Label", "Local Genre", "Local Style", "Local Tags", "Local Duration",
        "Discogs Title", "Discogs Artist", "Discogs Album", "Discogs Year", "Discogs Country", "Discogs Label", "Discogs Genre", "Discogs Style", "Discogs Tags", "Discogs Duration",
        "MAEST",
    ]
    row = contract["rows"][0]
    assert row["MAEST"] == "House (81%); Techno (64%); Electronic (52%)"
    assert row["Local Genre"] == "Electronic; Dance"
    assert row["Discogs Style"] == "Melodic Techno"


def test_contract_contains_only_requested_track_fields() -> None:

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

    row = contract["rows"][0]
    assert "Record" not in row
    assert "Discogs Record ID" not in row
    assert row["Discogs Album"] == "Release"
