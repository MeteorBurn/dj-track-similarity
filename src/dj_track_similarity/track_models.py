"""Typed track, tag, and scan models for the v7 runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


TrackMutationAction = Literal["added", "updated", "unchanged"]


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


@dataclass(frozen=True)
class FileTags:
    """Human-readable tags read from an audio file."""

    title: str | None = None
    artist: str | None = None
    album: str | None = None
    tag_bpm: float | None = None
    tag_key: str | None = None
    comment: str | None = None
    year: int | None = None
    label: str | None = None
    catalog_number: str | None = None
    country: str | None = None
    isrc: str | None = None
    track_number: str | None = None
    disc_number: str | None = None
    genres: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScannedFile:
    """Filesystem and audio-container facts captured by one scan."""

    file_path: str
    file_size_bytes: int
    file_modified_ns: int
    audio_format: str | None = None
    audio_codec: str | None = None
    sample_rate_hz: int | None = None
    channel_count: int | None = None
    bit_rate_bps: int | None = None
    audio_duration_seconds: float | None = None


@dataclass(frozen=True)
class TrackIdentity:
    """Stable track identity and the generation of its current file content."""

    catalog_uuid: str
    track_id: int
    track_uuid: str
    content_generation: int

    def __post_init__(self) -> None:
        _required_text(self.catalog_uuid, "catalog_uuid")
        _positive_int(self.track_id, "track_id")
        _required_text(self.track_uuid, "track_uuid")
        _positive_int(self.content_generation, "content_generation")


@dataclass(frozen=True)
class TrackFileState:
    """Current identity and file facts used for cheap unchanged detection."""

    catalog_uuid: str
    track_id: int
    track_uuid: str
    file_path: str
    file_size_bytes: int
    file_modified_ns: int
    content_generation: int
    missing_since: str | None

    def __post_init__(self) -> None:
        _required_text(self.catalog_uuid, "catalog_uuid")
        _positive_int(self.track_id, "track_id")
        _required_text(self.track_uuid, "track_uuid")
        _required_text(self.file_path, "file_path")
        if (
            isinstance(self.file_size_bytes, bool)
            or not isinstance(self.file_size_bytes, int)
            or self.file_size_bytes < 0
        ):
            raise ValueError("file_size_bytes must be a non-negative integer")
        if (
            isinstance(self.file_modified_ns, bool)
            or not isinstance(self.file_modified_ns, int)
            or self.file_modified_ns < 0
        ):
            raise ValueError("file_modified_ns must be a non-negative integer")
        _positive_int(self.content_generation, "content_generation")


@dataclass(frozen=True)
class TrackPath:
    """Track identifier paired with its canonical stored file path."""

    track_id: int
    file_path: str


@dataclass(frozen=True)
class TrackMutation:
    """Result of inserting or reconciling one scanned file."""

    action: TrackMutationAction
    identity: TrackIdentity


@dataclass(frozen=True)
class TrackRemovalResult:
    """Result of removing a source-deleted track from the storage bundle."""

    identity: TrackIdentity
    file_path: str
    removed: bool
    already_absent: bool
    core_rows_deleted: int
    artifact_rows_deleted: int

    def __post_init__(self) -> None:
        _required_text(self.file_path, "file_path")
        if self.removed == self.already_absent:
            raise ValueError(
                "exactly one of removed and already_absent must be true"
            )
        for field_name, value in (
            ("core_rows_deleted", self.core_rows_deleted),
            ("artifact_rows_deleted", self.artifact_rows_deleted),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise ValueError(
                    f"{field_name} must be a non-negative integer"
                )


@dataclass(frozen=True)
class ScanStats:
    """Aggregate result returned by the synchronous scanner."""

    added: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0


class RelocationChange(TypedDict):
    track_id: int
    track_uuid: str
    content_generation: int
    old_path: str
    new_path: str


class RelocationConflict(RelocationChange):
    existing_track_id: int | None


class MissingRelocationFile(TypedDict):
    track_id: int
    path: str


class RelocationResult(TypedDict):
    old_root: str
    new_root: str
    dry_run: bool
    tracks_matched: int
    tracks_updated: int
    missing_files: list[MissingRelocationFile]
    conflicts: list[RelocationConflict]
    changes: list[RelocationChange]


class ClearLibraryResult(TypedDict):
    tracks_deleted: int
    embeddings_deleted: int
    artifacts_deleted: int
    evaluation_rows_deleted: int
