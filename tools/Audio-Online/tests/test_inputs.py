from __future__ import annotations

from pathlib import Path

from metadata_enrichment import inputs
from metadata_enrichment.inputs import load_tracks


def test_text_reader_accepts_hyphen_and_em_dash(tmp_path: Path) -> None:
    """Prevent a common plain-text list format from being rejected or mangled."""

    input_path = tmp_path / "tracks.txt"
    input_path.write_text("Artist A - Title A\nArtist B — Title B\n", encoding="utf-8")

    assert [track.track_name for track in load_tracks(input_path)] == [
        "Artist A — Title A",
        "Artist B — Title B",
    ]


def test_csv_reader_maps_common_columns(tmp_path: Path) -> None:
    """Catch regressions in the interchange format expected from DJ tables."""

    input_path = tmp_path / "tracks.csv"
    input_path.write_text("Artist,Title,Album,Year\nArtist,Title,Release,2024\n", encoding="utf-8")

    track = load_tracks(input_path)[0]

    assert (track.artist, track.title, track.album, track.year) == ("Artist", "Title", "Release", 2024)


def test_m3u_reader_uses_playlist_path_as_exact_local_identity(tmp_path: Path) -> None:
    """Preserve path identity so local DB data is not fuzzily associated."""

    input_path = tmp_path / "tracks.m3u"
    input_path.write_text("#EXTM3U\n#EXTINF:402,Artist - Title\nC:\\music\\one.flac\n", encoding="utf-8")

    track = load_tracks(input_path)[0]

    assert track.track_name == "Artist — Title"
    assert str(track.file_path) == r"C:\music\one.flac"
    assert track.duration_seconds == 402


def test_directory_reader_reads_tags_without_writing_audio(tmp_path: Path, monkeypatch) -> None:
    """Folders are supported while tags remain a read-only input signal."""

    audio_path = tmp_path / "Artist - Title.flac"
    audio_path.touch()

    class Metadata:
        tags = {"artist": ["Artist"], "title": ["Title"], "album": ["Release"]}

    monkeypatch.setattr(inputs, "MutagenFile", lambda *_args, **_kwargs: Metadata())

    track = load_tracks(tmp_path)[0]

    assert (track.artist, track.title, track.album, track.file_path) == ("Artist", "Title", "Release", audio_path)
