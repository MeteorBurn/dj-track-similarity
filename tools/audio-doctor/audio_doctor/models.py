from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class RepairError(Exception):
    pass


class AudioDoctorCancelled(RuntimeError):
    pass


class TrackPathRecord(Protocol):
    """Typed repository projection used for database-backed path collection."""

    track_id: int
    file_path: str


@dataclass(frozen=True)
class ParsedChunk:
    chunk_id: bytes
    payload: bytes
    source_start: int
    source_end: int


@dataclass
class ByteRepairResult:
    changed: bool
    data: bytes
    actions: list[str] = field(default_factory=list)
    id3_seen: int = 0
    id3_removed: int = 0
    original_size: int = 0
    repaired_size: int = 0
    mutagen_summary: str | None = None


@dataclass
class FileRepairResult:
    path: Path
    status: str
    message: str
    actions: list[str] = field(default_factory=list)
    backup_path: Path | None = None
    original_size: int = 0
    repaired_size: int = 0
    id3_seen: int = 0
    id3_removed: int = 0
    mutagen_summary: str | None = None


@dataclass(frozen=True)
class FileInspectionResult:
    path: Path
    status: str
    message: str
    detected_format: str | None = None
    detected_codec: str | None = None
    tag_summary: str | None = None


@dataclass(frozen=True)
class RepairRunResult:
    exit_code: int
    results: list[FileRepairResult]
    skipped_state_results: list[StateRepairResult]
    total_collected: int
    skipped_from_state: int
    skipped_by_reason: int
    missing_db_files: int
    state_path: Path | None
    state_mode: bool
    apply_changes: bool
    keep_id3: str
    backup_dir: Path | None
    no_backup: bool
    workers: int


@dataclass(frozen=True)
class StateRepairResult:
    path: Path
    entry: dict[str, object]


@dataclass(frozen=True)
class ReportResult:
    json_path: Path
    xlsx_path: Path
    log_path: Path
    payload: dict[str, object]
