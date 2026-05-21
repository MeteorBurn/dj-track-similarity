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
    metadata: dict[str, object] | None = None
    genres: list[str] | None = None
    genre_scores: dict[str, float] | None = None
    analyses: list[str] | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = None


@dataclass(frozen=True)
class ScanStats:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class SearchResult:
    track: Track
    score: float
    score_breakdown: dict[str, float] | None = None


@dataclass(frozen=True)
class TagPreview:
    track_id: int
    path: str
    tags: dict[str, str]


@dataclass(frozen=True)
class GenreTagApplyResult:
    track_id: int
    path: str
    tags: dict[str, str]
    status: str
    message: str
    error: str | None = None
