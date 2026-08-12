"""Conservative deterministic match assessment for source records."""

from __future__ import annotations

import re
import unicodedata

from .models import MatchAssessment, SourceRecord, TrackInput


def score_candidate(track: TrackInput, candidate: SourceRecord) -> MatchAssessment:
    """Score observable identity evidence without treating it as genre truth."""

    if not track.artist or not track.title:
        return MatchAssessment(0, None, ("artist and title are required",))
    score = 0
    evidence: list[str] = []
    if _same(track.title, candidate.title):
        score += 4
        evidence.append("title exact")
    if _same(track.artist, candidate.artist):
        score += 4
        evidence.append("artist exact")
    if track.album and _same(track.album, candidate.album):
        score += 1
        evidence.append("album exact")
    if track.year and track.year == candidate.year:
        score += 1
        evidence.append("year exact")
    if track.duration_seconds is not None and candidate.duration_seconds is not None:
        if abs(track.duration_seconds - candidate.duration_seconds) <= 2:
            score += 1
            evidence.append("duration within 2s")
    confidence = "high" if score >= 8 else "medium" if score >= 6 else "low"
    return MatchAssessment(score, confidence if score else None, tuple(evidence))


def _same(left: str | None, right: str | None) -> bool:
    return bool(left and right and _normalized(left) == _normalized(right))


def _normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    return re.sub(r"[^\w]+", "", decomposed, flags=re.UNICODE)
