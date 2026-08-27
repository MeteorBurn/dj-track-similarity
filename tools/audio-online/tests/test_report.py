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
        "Track Name", "Genres", "MAEST Genres", "Discogs Genres",
        "Title", "Artist", "Album", "Year", "Country", "Label", "Tags",
        "Discogs Title", "Discogs Artist", "Discogs Album", "Discogs Year", "Discogs Country", "Discogs Label", "Discogs Tags",
    ]
    row = contract["rows"][0]
    assert row["MAEST Genres"] == "House (81%); Techno (64%); Electronic (52%)"
    assert row["Genres"] == "Electronic; Dance"
    assert row["Discogs Genres"] == "Electronic"
    assert "Style" not in contract["columns"]


def test_contract_contains_only_requested_track_fields() -> None:

    contract = build_report_contract(
        [(
            TrackInput(artist="Artist", title="Title", album="Release", year=2024),
            LocalEvidence(),
            (SourceResult(
                "Discogs", "matched",
                SourceRecord(title="Title", artist="Artist", album="Release", year=2024,
                             record_type="release", record_id="123",
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


def test_contract_strips_line_breaks_and_limits_genre_values_to_three() -> None:
    contract = build_report_contract(
        [(TrackInput(artist="Artist\nName", title="Title\r\nHere"), LocalEvidence(("One", "Two", "Three", "Four"), (("Electronic---House", .81), ("Style---Minimal Techno", .64))), ())],
        (),
    )

    row = contract["rows"][0]
    assert row["Track Name"] == "Artist Name — Title Here"
    assert row["Genres"] == "One; Two; Three"
    assert row["MAEST Genres"] == "House (81%); Minimal Techno (64%)"
