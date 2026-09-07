from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class PresetConfig:
    name: str
    min_score: float
    min_similarity: float
    duration_seconds: float
    duration_ratio: float
    direct_keeper_score: float
    strict_duration_ratio: float


@dataclass(frozen=True)
class SourceConfig:
    sources: tuple[str, ...]
    weights: dict[str, float]


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
    embeddings: dict[str, np.ndarray]
    catalog_uuid: str = ""
    track_uuid: str = ""
    file_modified_ns: int = 0


@dataclass(frozen=True)
class PairEvidence:
    left_id: int
    right_id: int
    score: float
    content_similarity: float | None
    mert_similarity: float | None
    maest_similarity: float | None
    muq_similarity: float | None
    clap_similarity: float | None
    sonara_similarity: float | None
    duration_diff_seconds: float | None
    duration_diff_ratio: float | None
    blocked_reasons: tuple[str, ...]
    fingerprint_similarity: float | None = None
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
