"""Input normalization without external requests."""

from __future__ import annotations

from pathlib import Path

from .models import TrackInput


def load_tracks(path: Path) -> list[TrackInput]:
    """Read a plain Artist-Title list; other formats are added incrementally."""

    if path.suffix.lower() != ".txt":
        raise ValueError(f"unsupported input format: {path.suffix or '<none>'}")
    tracks: list[TrackInput] = []
    for number, raw_line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        artist, title = _split_track_line(line)
        if not artist or not title:
            raise ValueError(f"line {number} must contain Artist - Title")
        tracks.append(TrackInput(artist=artist, title=title))
    return tracks


def _split_track_line(line: str) -> tuple[str, str]:
    for delimiter in (" — ", " - "):
        if delimiter in line:
            artist, title = line.split(delimiter, maxsplit=1)
            return artist.strip(), title.strip()
    return "", ""
