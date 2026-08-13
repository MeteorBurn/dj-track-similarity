"""Small immutable domain records for Audio Online."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class TrackInput:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    year: int | None = None
    country: str | None = None
    label: str | None = None
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


@dataclass(frozen=True)
class SourceRecord:
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    year: int | None = None
    country: str | None = None
    label: str | None = None
    genres: tuple[str, ...] = ()
    styles: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    record_type: str | None = None
    record_id: str | None = None
    record_url: str | None = None


@dataclass(frozen=True)
class SourceResult:
    name: str
    status: Literal["matched", "no_match", "not_configured", "unavailable", "error"]
    record: SourceRecord | None = None
    error: str | None = None
    queried_at: str | None = None


@dataclass(frozen=True)
class MatchAssessment:
    score: int
    confidence: Literal["high", "medium", "low"] | None
    evidence: tuple[str, ...]
