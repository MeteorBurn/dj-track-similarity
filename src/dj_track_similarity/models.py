from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    id: int
    path: str
    size: int
    mtime: float
    artist: str | None = None
    title: str | None = None
    album: str | None = None
    bpm: float | None = None
    musical_key: str | None = None
    energy: float | None = None
    duration: float | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = None


@dataclass(frozen=True)
class ScanStats:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class AnalyzeStats:
    analyzed: int = 0
    failed: int = 0


@dataclass(frozen=True)
class SearchResult:
    track: Track
    score: float


@dataclass(frozen=True)
class TagPreview:
    track_id: int
    path: str
    tags: dict[str, str]
