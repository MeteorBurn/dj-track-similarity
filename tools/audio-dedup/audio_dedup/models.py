from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class TrackRecord:
    track_id: int
    path: str
    size: int
    mtime: float
    artist: str | None
    title: str | None
    album: str | None
    bpm: float | None
    musical_key: str | None
    duration: float | None
    metadata: dict[str, object]
    catalog_uuid: str = ""
    track_uuid: str = ""
    file_modified_ns: int = 0
    # SONARA's own duration_sec: the length the fingerprint was computed over,
    # which is what the upstream duplicate recipe buckets on. `duration` stays
    # the container value the report and keeper choice read.
    analyzed_duration: float | None = None


@dataclass(frozen=True)
class PairEvidence:
    """One verified SONARA fingerprint match between two copies."""

    left_id: int
    right_id: int
    fingerprint_similarity: float
    duration_diff_seconds: float | None
    duration_diff_ratio: float | None
    candidate_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class DuplicateGroup:
    group_id: int
    track_ids: tuple[int, ...]
    pair_evidence: tuple[PairEvidence, ...]


@dataclass(frozen=True)
class ReportResult:
    json_path: Path
    xlsx_path: Path
    log_path: Path
    payload: dict[str, object]
    groups: int


@dataclass(frozen=True)
class ApplyResult:
    deleted_track_ids: tuple[int, ...]
    deleted_paths: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[str, ...]
    rhythm_lab_deleted_rows: int = 0


class AudioDedupCancelled(Exception):
    """Cancellation is control flow; keep it out of every failure except tuple."""
