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
    liked: bool = False
    metadata: dict[str, object] | None = None
    genres: list[str] | None = None
    genre_scores: dict[str, float] | None = None
    classifier_scores: dict[str, dict[str, object]] | None = None
    analyses: list[str] | None = None
    embedding_model: str | None = None
    embedding_dim: int | None = None
    timeline_fields: list[str] | None = None
    representation_fields: list[str] | None = None


@dataclass(frozen=True)
class AnalysisCandidate:
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
    analyses: tuple[str, ...] = ()
    missing_models: tuple[str, ...] = ()

    def to_track(self) -> Track:
        return Track(
            id=self.id,
            path=self.path,
            size=self.size,
            mtime=self.mtime,
            artist=self.artist,
            title=self.title,
            album=self.album,
            bpm=self.bpm,
            musical_key=self.musical_key,
            energy=self.energy,
            duration=self.duration,
            analyses=list(self.analyses) or None,
        )


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
class GenreTagApplyResult:
    track_id: int
    path: str
    tags: dict[str, str]
    status: str
    message: str
    error: str | None = None
