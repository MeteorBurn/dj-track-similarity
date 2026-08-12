"""Small immutable domain records for Audio Online."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrackInput:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    year: int | None = None
    country: str | None = None
    label: str | None = None
    duration_seconds: float | None = None
    file_path: Path | None = None

    @property
    def track_name(self) -> str:
        if self.artist and self.title:
            return f"{self.artist} — {self.title}"
        return self.title or self.artist or ""


@dataclass(frozen=True)
class LocalEvidence:
    file_tags: tuple[str, ...] = ()
    maest: tuple[tuple[str, float], ...] = ()
    matched_path: str | None = None
