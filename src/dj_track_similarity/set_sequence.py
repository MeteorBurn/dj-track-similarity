from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Protocol

from .models import Track


ARTIST_SET_MAX_TRACKS = 1


class SequenceCandidate(Protocol):
    @property
    def track(self) -> Track:
        ...

    @property
    def duplicate_key(self) -> str:
        ...


class ScoredSequenceCandidate(Protocol):
    @property
    def candidate(self) -> SequenceCandidate:
        ...


def duplicate_key(track: Track) -> str:
    artist = (track.artist or "").strip().casefold()
    title = (track.title or "").strip().casefold()
    if artist or title:
        return f"{artist}|{title}"
    return Path(track.path).stem.casefold()


def artist_key(track: Track) -> str | None:
    artist = (track.artist or "").strip().casefold()
    return artist or None


def artist_allowed(
    candidate: SequenceCandidate,
    previous: SequenceCandidate | None,
    artist_counts: Counter[str],
) -> bool:
    artist = artist_key(candidate.track)
    if artist is None:
        return True
    if previous is not None and artist_key(previous.track) == artist:
        return False
    return artist_counts[artist] < ARTIST_SET_MAX_TRACKS


def pending_seed_artists(pending_seeds: list[SequenceCandidate]) -> set[str]:
    return {artist for seed in pending_seeds if (artist := artist_key(seed.track)) is not None}


def uses_pending_seed_artist(candidate: SequenceCandidate, pending_seed_artists: set[str]) -> bool:
    artist = artist_key(candidate.track)
    return artist is not None and artist in pending_seed_artists


def record_artist(candidate: SequenceCandidate, artist_counts: Counter[str]) -> None:
    artist = artist_key(candidate.track)
    if artist is not None:
        artist_counts[artist] += 1


def artist_pressure_score(candidate: SequenceCandidate, remaining: list[ScoredSequenceCandidate]) -> float:
    artist = artist_key(candidate.track)
    if artist is None:
        return 0.0
    counts: Counter[str] = Counter()
    for item in remaining:
        item_artist = artist_key(item.candidate.track)
        if item_artist is not None:
            counts[item_artist] += 1
    max_count = max(counts.values(), default=0)
    if max_count <= 1:
        return 0.0
    return max(0.0, min(1.0, float((counts[artist] - 1) / max_count)))
