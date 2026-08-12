from __future__ import annotations

from pathlib import Path

from metadata_enrichment.inputs import load_tracks


def test_text_reader_accepts_hyphen_and_em_dash(tmp_path: Path) -> None:
    """Prevent a common plain-text list format from being rejected or mangled."""

    input_path = tmp_path / "tracks.txt"
    input_path.write_text("Artist A - Title A\nArtist B — Title B\n", encoding="utf-8")

    assert [track.track_name for track in load_tracks(input_path)] == [
        "Artist A — Title A",
        "Artist B — Title B",
    ]
