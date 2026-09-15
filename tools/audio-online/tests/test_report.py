from __future__ import annotations

from metadata_enrichment.models import LocalEvidence, TrackInput
from metadata_enrichment.report import build_report_contract


def test_contract_strips_line_breaks_and_limits_genre_values_to_three() -> None:
    contract = build_report_contract(
        [(TrackInput(artist="Artist\nName", title="Title\r\nHere"), LocalEvidence(("One", "Two", "Three", "Four"), (("Electronic---House", .81), ("Style---Minimal Techno", .64))), ())],
        (),
    )

    row = contract["rows"][0]
    assert row["Track Name"] == "Artist Name — Title Here"
    assert row["Genres"] == "One; Two; Three"
    assert row["MAEST Genres"] == "House (81%); Minimal Techno (64%)"
