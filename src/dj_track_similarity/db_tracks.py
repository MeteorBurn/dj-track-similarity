"""Thread-safe v7 track repository.

Track identity lives in Core. Large derived payloads live in the mandatory
Artifacts database. A content change is therefore reconciled in two ordered,
idempotent phases:

1. reserve and commit the Core generation change with ``BEGIN IMMEDIATE``;
2. delete Artifacts rows whose identity is not the exact committed identity.

The same Core-first lock order is used by artifact writers, so a stale writer
cannot publish after the cleanup and a concurrent current-generation writer is
never removed.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterable, Sequence
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .db_search_fts import upsert_track_search_fts
from .track_models import (
    ClearLibraryResult,
    FileTags,
    MissingRelocationFile,
    RelocationChange,
    RelocationConflict,
    RelocationResult,
    ScannedFile,
    TrackFileState,
    TrackIdentity,
    TrackMutation,
    TrackPath,
    TrackRemovalResult,
)


_CORE_DERIVED_TABLES = (
    "sonara",
    "maest_scores",
    "classifier_scores",
)
_ARTIFACT_TABLES = (
    "maest_embeddings",
    "mert_embeddings",
    "muq_embeddings",
    "clap_embeddings",
    "sonara_similarity_embeddings",
    "sonara_timeline",
    "sonara_fingerprints",
)
_EMBEDDING_ARTIFACT_TABLES = (
    "maest_embeddings",
    "mert_embeddings",
    "muq_embeddings",
    "clap_embeddings",
    "sonara_similarity_embeddings",
)
_EVALUATION_DATA_TABLES = (
    "search_session_seeds",
    "search_result_events",
    "search_sessions",
    "calibration_runs",
    "evaluation_settings",
)
_UTC_MICROSECOND_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z"
)
_LIBRARY_ROOT_SETTING_KEY = "library_root"
_SQLITE_IN_CHUNK_SIZE = 800


def utc_now_text() -> str:
    """Return a UTC RFC 3339 timestamp with exactly six fractional digits."""

    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _timestamp_or_now(value: str | None) -> str:
    timestamp = utc_now_text() if value is None else value
    if (
        not isinstance(timestamp, str)
        or _UTC_MICROSECOND_PATTERN.fullmatch(timestamp) is None
    ):
        raise ValueError(
            "timestamp must be UTC RFC 3339 with six fractional digits and Z"
        )
    try:
        datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ValueError(
            "timestamp must be a valid UTC RFC 3339 microsecond value"
        ) from error
    return timestamp


def ordinal_path_key(
    value: str,
    *,
    windows: bool | None = None,
) -> str:
    """Return the deterministic identity key for an already absolute path.

    Windows identity is ordinal case-insensitive for this application. Python
    ``lower`` is intentionally used instead of Unicode ``casefold`` so names
    such as ``Straße`` and ``Strasse`` remain distinct.
    """

    use_windows_rules = os.name == "nt" if windows is None else bool(windows)
    normalized = value.replace("\\", "/") if use_windows_rules else value
    return normalized.lower() if use_windows_rules else normalized


def canonical_file_path(path: str | Path) -> str:
    """Resolve and normalize a path for persistent v7 track identity."""

    resolved = Path(path).expanduser().resolve(strict=False)
    return ordinal_path_key(resolved.as_posix())


def _genres_json(tags: FileTags) -> str:
    if any(not isinstance(genre, str) for genre in tags.genres):
        raise ValueError("genres must contain only strings")
    genres = [genre.strip() for genre in tags.genres if genre.strip()]
    return json.dumps(
        genres,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _validate_file_facts(file: ScannedFile) -> None:
    _require_nonnegative_int("file_size_bytes", file.file_size_bytes)
    _require_nonnegative_int("file_modified_ns", file.file_modified_ns)
    _require_optional_positive_int("sample_rate_hz", file.sample_rate_hz)
    _require_optional_positive_int("channel_count", file.channel_count)
    _require_optional_positive_int("bit_rate_bps", file.bit_rate_bps)
    _require_optional_positive_float(
        "audio_duration_seconds",
        file.audio_duration_seconds,
    )


def _validate_self_write_facts(
    *,
    file_size_bytes: int,
    file_modified_ns: int,
) -> None:
    _require_nonnegative_int("file_size_bytes", file_size_bytes)
    _require_nonnegative_int("file_modified_ns", file_modified_ns)


def _validate_tags(tags: FileTags) -> None:
    _require_optional_positive_float("tag_bpm", tags.tag_bpm)
    if tags.year is not None:
        if (
            isinstance(tags.year, bool)
            or not isinstance(tags.year, int)
            or not 1 <= tags.year <= 9999
        ):
            raise ValueError("year must be an integer from 1 through 9999")
    _genres_json(tags)


def _require_nonnegative_int(name: str, value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _require_optional_positive_int(name: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer or None")


def _require_optional_positive_float(name: str, value: object) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive finite number or None")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive finite number or None")


def _upsert_file_tags(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    tags: FileTags,
    tags_read_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO file_tags(
            track_id,
            title,
            artist,
            album,
            tag_bpm,
            tag_key,
            comment,
            year,
            label,
            catalog_number,
            country,
            isrc,
            track_number,
            disc_number,
            genres_json,
            tags_read_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            title = excluded.title,
            artist = excluded.artist,
            album = excluded.album,
            tag_bpm = excluded.tag_bpm,
            tag_key = excluded.tag_key,
            comment = excluded.comment,
            year = excluded.year,
            label = excluded.label,
            catalog_number = excluded.catalog_number,
            country = excluded.country,
            isrc = excluded.isrc,
            track_number = excluded.track_number,
            disc_number = excluded.disc_number,
            genres_json = excluded.genres_json,
            tags_read_at = excluded.tags_read_at
        """,
        (
            int(track_id),
            tags.title,
            tags.artist,
            tags.album,
            tags.tag_bpm,
            tags.tag_key,
            tags.comment,
            tags.year,
            tags.label,
            tags.catalog_number,
            tags.country,
            tags.isrc,
            tags.track_number,
            tags.disc_number,
            _genres_json(tags),
            tags_read_at,
        ),
    )


def _identity_from_row(
    row: sqlite3.Row | tuple[object, ...],
    *,
    catalog_uuid: str,
) -> TrackIdentity:
    return TrackIdentity(
        catalog_uuid=catalog_uuid,
        track_id=int(row[0]),
        track_uuid=str(row[1]),
        content_generation=int(row[2]),
    )


def _validated_track_ids(track_ids: Sequence[int]) -> tuple[int, ...]:
    ordered: list[int] = []
    seen: set[int] = set()
    for value in track_ids:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("track_ids must contain only positive integers")
        if value not in seen:
            seen.add(value)
            ordered.append(value)
    return tuple(ordered)


def _chunks(values: Sequence[int], size: int = _SQLITE_IN_CHUNK_SIZE) -> Iterable[tuple[int, ...]]:
    for start in range(0, len(values), size):
        yield tuple(values[start : start + size])


def _relocated_path(
    file_path: str,
    *,
    old_root: str,
    new_root: str,
) -> str | None:
    if file_path == old_root:
        return new_root
    prefix = f"{old_root}/"
    if not file_path.startswith(prefix):
        return None
    return f"{new_root}/{file_path[len(prefix):]}"


def _plan_relocation(
    rows: Sequence[sqlite3.Row],
    *,
    old_root: str,
    new_root: str,
) -> tuple[
    list[RelocationChange],
    list[RelocationConflict],
    list[MissingRelocationFile],
]:
    provisional: list[RelocationChange] = []
    for row in rows:
        old_path = str(row[3])
        new_path = _relocated_path(
            old_path,
            old_root=old_root,
            new_root=new_root,
        )
        if new_path is None:
            continue
        provisional.append(
            RelocationChange(
                track_id=int(row[0]),
                track_uuid=str(row[1]),
                content_generation=int(row[2]),
                old_path=old_path,
                new_path=new_path,
            )
        )

    moving_ids = {change["track_id"] for change in provisional}
    existing_by_path = {str(row[3]): int(row[0]) for row in rows}
    planned_by_path: dict[str, int] = {}
    conflicts: list[RelocationConflict] = []
    missing_files: list[MissingRelocationFile] = []
    for change in provisional:
        existing_track_id = existing_by_path.get(change["new_path"])
        if (
            existing_track_id is not None
            and existing_track_id != change["track_id"]
            and existing_track_id not in moving_ids
        ):
            conflicts.append(
                RelocationConflict(
                    **change,
                    existing_track_id=existing_track_id,
                )
            )
        planned_track_id = planned_by_path.get(change["new_path"])
        if (
            planned_track_id is not None
            and planned_track_id != change["track_id"]
        ):
            conflicts.append(
                RelocationConflict(
                    **change,
                    existing_track_id=planned_track_id,
                )
            )
        planned_by_path[change["new_path"]] = change["track_id"]
        if not Path(change["new_path"]).is_file():
            missing_files.append(
                MissingRelocationFile(
                    track_id=change["track_id"],
                    path=change["new_path"],
                )
            )
    return provisional, conflicts, missing_files


def _temporary_relocation_path(
    old_path: str,
    occupied_paths: set[str],
) -> str:
    while True:
        candidate = f"{old_path}.relocating-{uuid.uuid4().hex}"
        if candidate not in occupied_paths:
            return candidate


class TrackRepository:
    """V7-only repository mixed into :class:`LibraryDatabase`.

    The host must expose ``connect()``, ``connect_artifacts()``, and one
    path-scoped re-entrant ``_write_lock``.
    """

    _write_lock: threading.RLock
    catalog_uuid: str

    def connect(self) -> sqlite3.Connection:
        raise NotImplementedError

    def connect_artifacts(self) -> sqlite3.Connection:
        raise NotImplementedError

    def connect_evaluation(
        self,
        *,
        create: bool = False,
    ) -> sqlite3.Connection | None:
        raise NotImplementedError

    def get_track_identity(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> TrackIdentity | None:
        """Return one current Core identity or ``None`` when it is unavailable."""

        identities = self.get_track_identities(
            (track_id,),
            include_missing=include_missing,
        )
        return identities.get(track_id)

    def get_track_identities(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> dict[int, TrackIdentity]:
        """Read current identities in one snapshot, omitting unknown tracks.

        Missing tracks are omitted by default and included only when explicitly
        requested. The returned dict follows the stable first-occurrence order
        of ``track_ids``.
        """

        ordered_ids = _validated_track_ids(track_ids)
        if not ordered_ids:
            return {}
        rows_by_id: dict[int, sqlite3.Row] = {}
        with closing(self.connect()) as connection:
            connection.execute("BEGIN")
            try:
                for chunk in _chunks(ordered_ids):
                    placeholders = ",".join("?" for _ in chunk)
                    where_missing = "" if include_missing else "AND missing_since IS NULL"
                    rows = connection.execute(
                        f"""
                        SELECT track_id, track_uuid, content_generation
                        FROM tracks
                        WHERE track_id IN ({placeholders})
                          {where_missing}
                        """,
                        chunk,
                    ).fetchall()
                    rows_by_id.update({int(row[0]): row for row in rows})
            finally:
                if connection.in_transaction:
                    connection.rollback()
        return {
            track_id: _identity_from_row(
                rows_by_id[track_id],
                catalog_uuid=self.catalog_uuid,
            )
            for track_id in ordered_ids
            if track_id in rows_by_id
        }

    def get_track_file_states_by_ids(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> tuple[TrackFileState, ...]:
        """Resolve an ordered, strict selection of current track file states.

        Duplicate IDs are stably deduplicated. Unknown IDs, and missing tracks
        unless ``include_missing`` is true, fail closed rather than silently
        shortening the caller's selection.
        """

        ordered_ids = _validated_track_ids(track_ids)
        if not ordered_ids:
            return ()
        rows_by_id: dict[int, sqlite3.Row] = {}
        with closing(self.connect()) as connection:
            connection.execute("BEGIN")
            try:
                for chunk in _chunks(ordered_ids):
                    placeholders = ",".join("?" for _ in chunk)
                    rows = connection.execute(
                        f"""
                        SELECT
                            track_id,
                            track_uuid,
                            file_path,
                            file_size_bytes,
                            file_modified_ns,
                            content_generation,
                            missing_since
                        FROM tracks
                        WHERE track_id IN ({placeholders})
                        """,
                        chunk,
                    ).fetchall()
                    rows_by_id.update({int(row[0]): row for row in rows})
            finally:
                if connection.in_transaction:
                    connection.rollback()

        unknown = [track_id for track_id in ordered_ids if track_id not in rows_by_id]
        if unknown:
            raise KeyError(f"Unknown track ids: {unknown}")
        missing = [
            track_id
            for track_id in ordered_ids
            if rows_by_id[track_id][6] is not None
        ]
        if missing and not include_missing:
            raise KeyError(f"Missing track ids are not selectable: {missing}")
        return tuple(
            TrackFileState(
                catalog_uuid=self.catalog_uuid,
                track_id=int(row[0]),
                track_uuid=str(row[1]),
                file_path=str(row[2]),
                file_size_bytes=int(row[3]),
                file_modified_ns=int(row[4]),
                content_generation=int(row[5]),
                missing_since=(
                    str(row[6])
                    if row[6] is not None
                    else None
                ),
            )
            for track_id in ordered_ids
            for row in (rows_by_id[track_id],)
        )

    def get_track_file_state(
        self,
        path: str | Path,
    ) -> TrackFileState | None:
        stored_path = canonical_file_path(path)
        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT
                    track_id,
                    track_uuid,
                    file_path,
                    file_size_bytes,
                    file_modified_ns,
                    content_generation,
                    missing_since
                FROM tracks
                WHERE file_path = ?
                """,
                (stored_path,),
            ).fetchone()
        if row is None:
            return None
        return TrackFileState(
            catalog_uuid=self.catalog_uuid,
            track_id=int(row[0]),
            track_uuid=str(row[1]),
            file_path=str(row[2]),
            file_size_bytes=int(row[3]),
            file_modified_ns=int(row[4]),
            content_generation=int(row[5]),
            missing_since=str(row[6]) if row[6] is not None else None,
        )

    def upsert_scanned_track(
        self,
        *,
        file: ScannedFile,
        tags: FileTags,
        scanned_at: str | None = None,
    ) -> TrackMutation:
        """Insert or reconcile one scanned file and maintain live FTS."""

        _validate_file_facts(file)
        _validate_tags(tags)
        timestamp = _timestamp_or_now(scanned_at)
        stored_path = canonical_file_path(file.file_path)

        with self._write_lock:
            with closing(self.connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        """
                        SELECT
                            track_id,
                            track_uuid,
                            content_generation,
                            file_size_bytes,
                            file_modified_ns
                        FROM tracks
                        WHERE file_path = ?
                        """,
                        (stored_path,),
                    ).fetchone()

                    if row is None:
                        track_uuid = str(uuid.uuid4())
                        cursor = connection.execute(
                            """
                            INSERT INTO tracks(
                                track_uuid,
                                file_path,
                                file_size_bytes,
                                file_modified_ns,
                                audio_format,
                                audio_codec,
                                sample_rate_hz,
                                channel_count,
                                bit_rate_bps,
                                audio_duration_seconds,
                                content_generation,
                                last_scanned_at,
                                missing_since,
                                created_at,
                                updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, NULL, ?, ?)
                            """,
                            (
                                track_uuid,
                                stored_path,
                                int(file.file_size_bytes),
                                int(file.file_modified_ns),
                                file.audio_format,
                                file.audio_codec,
                                file.sample_rate_hz,
                                file.channel_count,
                                file.bit_rate_bps,
                                file.audio_duration_seconds,
                                timestamp,
                                timestamp,
                                timestamp,
                            ),
                        )
                        identity = TrackIdentity(
                            catalog_uuid=self.catalog_uuid,
                            track_id=int(cursor.lastrowid),
                            track_uuid=track_uuid,
                            content_generation=1,
                        )
                        action = "added"
                        _upsert_file_tags(
                            connection,
                            track_id=identity.track_id,
                            tags=tags,
                            tags_read_at=timestamp,
                        )
                        upsert_track_search_fts(connection, identity.track_id)
                    else:
                        unchanged = (
                            int(row[3]) == int(file.file_size_bytes)
                            and int(row[4]) == int(file.file_modified_ns)
                        )
                        if unchanged:
                            identity = _identity_from_row(
                                row,
                                catalog_uuid=self.catalog_uuid,
                            )
                            action = "unchanged"
                            connection.execute(
                                """
                                UPDATE tracks
                                SET last_scanned_at = ?,
                                    missing_since = NULL
                                WHERE track_id = ?
                                """,
                                (timestamp, identity.track_id),
                            )
                            upsert_track_search_fts(
                                connection,
                                identity.track_id,
                            )
                        else:
                            next_generation = int(row[2]) + 1
                            identity = TrackIdentity(
                                catalog_uuid=self.catalog_uuid,
                                track_id=int(row[0]),
                                track_uuid=str(row[1]),
                                content_generation=next_generation,
                            )
                            action = "updated"
                            connection.execute(
                                """
                                UPDATE tracks
                                SET file_size_bytes = ?,
                                    file_modified_ns = ?,
                                    audio_format = ?,
                                    audio_codec = ?,
                                    sample_rate_hz = ?,
                                    channel_count = ?,
                                    bit_rate_bps = ?,
                                    audio_duration_seconds = ?,
                                    content_generation = ?,
                                    last_scanned_at = ?,
                                    missing_since = NULL,
                                    updated_at = ?
                                WHERE track_id = ?
                                """,
                                (
                                    int(file.file_size_bytes),
                                    int(file.file_modified_ns),
                                    file.audio_format,
                                    file.audio_codec,
                                    file.sample_rate_hz,
                                    file.channel_count,
                                    file.bit_rate_bps,
                                    file.audio_duration_seconds,
                                    next_generation,
                                    timestamp,
                                    timestamp,
                                    identity.track_id,
                                ),
                            )
                            for table in _CORE_DERIVED_TABLES:
                                connection.execute(
                                    f"DELETE FROM {table} WHERE track_id = ?",
                                    (identity.track_id,),
                                )
                            _upsert_file_tags(
                                connection,
                                track_id=identity.track_id,
                                tags=tags,
                                tags_read_at=timestamp,
                            )
                            upsert_track_search_fts(
                                connection,
                                identity.track_id,
                            )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

            self._delete_identity_mismatched_artifacts(identity.track_id)
            return TrackMutation(action=action, identity=identity)

    def refresh_file_tags(
        self,
        expected: TrackFileState,
        tags: FileTags,
        *,
        tags_read_at: str | None = None,
    ) -> TrackIdentity:
        """Refresh typed file tags only for one unchanged source snapshot."""

        if not isinstance(expected, TrackFileState):
            raise TypeError("expected must be a TrackFileState")
        _validate_tags(tags)
        timestamp = _timestamp_or_now(tags_read_at)
        source_path = Path(canonical_file_path(expected.file_path))
        with self._write_lock:
            with closing(self.connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._require_expected_file_state(connection, expected)
                    before_stat = source_path.stat()
                    before_facts = (
                        int(before_stat.st_size),
                        int(before_stat.st_mtime_ns),
                    )
                    expected_facts = (
                        expected.file_size_bytes,
                        expected.file_modified_ns,
                    )
                    if before_facts != expected_facts:
                        raise RuntimeError(
                            "Source file changed before tag refresh could be recorded"
                        )
                    _upsert_file_tags(
                        connection,
                        track_id=expected.track_id,
                        tags=tags,
                        tags_read_at=timestamp,
                    )
                    upsert_track_search_fts(connection, expected.track_id)
                    after_stat = source_path.stat()
                    after_facts = (
                        int(after_stat.st_size),
                        int(after_stat.st_mtime_ns),
                    )
                    if after_facts != expected_facts:
                        raise RuntimeError(
                            "Source file changed while tag refresh was being recorded"
                        )
                    connection.commit()
                    return TrackIdentity(
                        catalog_uuid=self.catalog_uuid,
                        track_id=expected.track_id,
                        track_uuid=expected.track_uuid,
                        content_generation=expected.content_generation,
                    )
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

    def apply_self_tag_write(
        self,
        expected: TrackFileState,
        *,
        write_source: Callable[[Path], None],
        read_source_tags: Callable[[Path], FileTags],
        validate_readback: Callable[[FileTags], None],
        tags_read_at: str | None = None,
    ) -> TrackIdentity:
        """Run one identity-bound source-tag write and record it atomically.

        The path-scoped repository lock and a Core ``BEGIN IMMEDIATE`` span the
        candidate compare-and-swap, source callback, readback, final stat, and
        database update. Scanner writes therefore cannot interleave inside this
        process, while another process is serialized by SQLite. The callbacks
        must perform source-file work only and must not call repository methods.
        """

        if not callable(write_source):
            raise TypeError("write_source must be callable")
        if not callable(read_source_tags):
            raise TypeError("read_source_tags must be callable")
        if not callable(validate_readback):
            raise TypeError("validate_readback must be callable")
        timestamp = _timestamp_or_now(tags_read_at)
        source_path = Path(canonical_file_path(expected.file_path))

        with self._write_lock:
            with closing(self.connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._require_expected_file_state(
                        connection,
                        expected,
                    )
                    before_stat = source_path.stat()
                    before_facts = (
                        int(before_stat.st_size),
                        int(before_stat.st_mtime_ns),
                    )
                    expected_facts = (
                        expected.file_size_bytes,
                        expected.file_modified_ns,
                    )
                    if before_facts != expected_facts:
                        raise RuntimeError(
                            "Source file changed before self tag write; "
                            "file facts no longer match the candidate"
                        )

                    write_source(source_path)
                    written_stat = source_path.stat()
                    written_facts = (
                        int(written_stat.st_size),
                        int(written_stat.st_mtime_ns),
                    )
                    refreshed_tags = read_source_tags(source_path)
                    _validate_tags(refreshed_tags)
                    validate_readback(refreshed_tags)
                    final_stat = source_path.stat()
                    final_facts = (
                        int(final_stat.st_size),
                        int(final_stat.st_mtime_ns),
                    )
                    if final_facts != written_facts:
                        raise RuntimeError(
                            "Source file changed while verifying self tag write"
                        )

                    identity = self._record_self_tag_write_in_transaction(
                        connection,
                        expected,
                        refreshed_tags,
                        file_size_bytes=final_facts[0],
                        file_modified_ns=final_facts[1],
                        tags_read_at=timestamp,
                    )
                    connection.commit()
                    return identity
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

    def _record_self_tag_write_in_transaction(
        self,
        connection: sqlite3.Connection,
        expected: TrackFileState,
        tags: FileTags,
        *,
        file_size_bytes: int,
        file_modified_ns: int,
        tags_read_at: str,
    ) -> TrackIdentity:
        _validate_self_write_facts(
            file_size_bytes=file_size_bytes,
            file_modified_ns=file_modified_ns,
        )
        self._require_expected_file_state(connection, expected)
        cursor = connection.execute(
            """
            UPDATE tracks
            SET file_size_bytes = ?,
                file_modified_ns = ?,
                missing_since = NULL,
                updated_at = ?
            WHERE track_id = ?
              AND track_uuid = ?
              AND content_generation = ?
              AND file_path = ?
              AND file_size_bytes = ?
              AND file_modified_ns = ?
              AND missing_since IS NULL
            """,
            (
                int(file_size_bytes),
                int(file_modified_ns),
                tags_read_at,
                expected.track_id,
                expected.track_uuid,
                expected.content_generation,
                canonical_file_path(expected.file_path),
                expected.file_size_bytes,
                expected.file_modified_ns,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(
                "Track state changed before self tag write could be recorded"
            )
        _upsert_file_tags(
            connection,
            track_id=expected.track_id,
            tags=tags,
            tags_read_at=tags_read_at,
        )
        upsert_track_search_fts(connection, expected.track_id)
        return TrackIdentity(
            catalog_uuid=self.catalog_uuid,
            track_id=expected.track_id,
            track_uuid=expected.track_uuid,
            content_generation=expected.content_generation,
        )

    def _require_expected_file_state(
        self,
        connection: sqlite3.Connection,
        expected: TrackFileState,
    ) -> None:
        if expected.catalog_uuid != self.catalog_uuid:
            raise RuntimeError(
                "Track candidate belongs to a different catalog"
            )
        stored_path = canonical_file_path(expected.file_path)
        row = connection.execute(
            """
            SELECT
                track_id,
                track_uuid,
                file_path,
                file_size_bytes,
                file_modified_ns,
                content_generation,
                missing_since
            FROM tracks
            WHERE track_id = ?
               OR file_path = ?
            ORDER BY track_id
            """,
            (expected.track_id, stored_path),
        ).fetchall()
        exact = [
            item
            for item in row
            if (
                int(item[0]) == expected.track_id
                and str(item[1]) == expected.track_uuid
                and str(item[2]) == stored_path
                and int(item[3]) == expected.file_size_bytes
                and int(item[4]) == expected.file_modified_ns
                and int(item[5]) == expected.content_generation
                and item[6] is None
            )
        ]
        if len(row) != 1 or len(exact) != 1:
            raise RuntimeError(
                "Track identity or path changed, content generation changed, "
                "or stored file facts changed after candidate selection"
            )

    def list_track_paths(
        self,
        *,
        include_missing: bool = False,
    ) -> list[TrackPath]:
        where = "" if include_missing else "WHERE missing_since IS NULL"
        with closing(self.connect()) as connection:
            rows = connection.execute(
                f"""
                SELECT track_id, file_path
                FROM tracks
                {where}
                ORDER BY file_path, track_id
                """
            ).fetchall()
        return [
            TrackPath(track_id=int(row[0]), file_path=str(row[1]))
            for row in rows
        ]

    def get_library_root(self) -> str | None:
        """Return the selected canonical library root, when configured."""

        with closing(self.connect()) as connection:
            row = connection.execute(
                """
                SELECT setting_value
                FROM library_settings
                WHERE setting_key = ?
                """,
                (_LIBRARY_ROOT_SETTING_KEY,),
            ).fetchone()
        return None if row is None else str(row[0])

    def set_library_root(self, root: str | Path) -> str:
        """Persist one canonical library root in the v7 settings table."""

        canonical_root = canonical_file_path(root).rstrip("/")
        timestamp = utc_now_text()
        with self._write_lock:
            with closing(self.connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        """
                        INSERT INTO library_settings(
                            setting_key,
                            setting_value,
                            updated_at
                        ) VALUES (?, ?, ?)
                        ON CONFLICT(setting_key) DO UPDATE SET
                            setting_value = excluded.setting_value,
                            updated_at = excluded.updated_at
                        """,
                        (
                            _LIBRARY_ROOT_SETTING_KEY,
                            canonical_root,
                            timestamp,
                        ),
                    )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        return canonical_root

    def relocate_library(
        self,
        old_root: str | Path,
        new_root: str | Path,
        *,
        apply: bool = False,
    ) -> RelocationResult:
        """Preview or apply a database-only canonical path relocation.

        Apply never moves, copies, deletes, or retags audio. It changes only
        ``tracks.file_path``, its FTS projection, and a matching library-root
        setting. Stable UUIDs, generations, and all analysis rows are preserved.
        """

        old_root_text = canonical_file_path(old_root).rstrip("/")
        new_root_text = canonical_file_path(new_root).rstrip("/")
        if old_root_text == new_root_text:
            raise ValueError("Old and new library roots must be different")

        lock = self._write_lock if apply else threading.RLock()
        with lock:
            with closing(self.connect()) as connection:
                if apply:
                    connection.execute("BEGIN IMMEDIATE")
                try:
                    rows = connection.execute(
                        """
                        SELECT
                            track_id,
                            track_uuid,
                            content_generation,
                            file_path
                        FROM tracks
                        ORDER BY track_id
                        """
                    ).fetchall()
                    changes, conflicts, missing_files = _plan_relocation(
                        rows,
                        old_root=old_root_text,
                        new_root=new_root_text,
                    )
                    if apply:
                        if conflicts:
                            raise ValueError(
                                "Cannot relocate library because one or more "
                                "target paths conflict"
                            )
                        if missing_files:
                            raise ValueError(
                                "Cannot relocate library because one or more "
                                "target files are missing"
                            )
                        timestamp = utc_now_text()
                        occupied_paths = {
                            str(row[3])
                            for row in rows
                        } | {
                            change["new_path"]
                            for change in changes
                        }
                        temporary_paths: dict[int, str] = {}
                        for change in changes:
                            temporary_path = _temporary_relocation_path(
                                change["old_path"],
                                occupied_paths,
                            )
                            occupied_paths.add(temporary_path)
                            temporary_paths[change["track_id"]] = temporary_path
                            cursor = connection.execute(
                                """
                                UPDATE tracks
                                SET file_path = ?,
                                    updated_at = ?
                                WHERE track_id = ?
                                  AND track_uuid = ?
                                  AND content_generation = ?
                                  AND file_path = ?
                                """,
                                (
                                    temporary_path,
                                    timestamp,
                                    change["track_id"],
                                    change["track_uuid"],
                                    change["content_generation"],
                                    change["old_path"],
                                ),
                            )
                            if cursor.rowcount != 1:
                                raise RuntimeError(
                                    "Track identity changed during relocation: "
                                    f"{change['track_id']}"
                                )
                        for change in changes:
                            cursor = connection.execute(
                                """
                                UPDATE tracks
                                SET file_path = ?,
                                    updated_at = ?
                                WHERE track_id = ?
                                  AND track_uuid = ?
                                  AND content_generation = ?
                                  AND file_path = ?
                                """,
                                (
                                    change["new_path"],
                                    timestamp,
                                    change["track_id"],
                                    change["track_uuid"],
                                    change["content_generation"],
                                    temporary_paths[change["track_id"]],
                                ),
                            )
                            if cursor.rowcount != 1:
                                raise RuntimeError(
                                    "Track identity changed during relocation: "
                                    f"{change['track_id']}"
                                )
                            upsert_track_search_fts(
                                connection,
                                change["track_id"],
                            )
                        root_row = connection.execute(
                            """
                            SELECT setting_value
                            FROM library_settings
                            WHERE setting_key = ?
                            """,
                            (_LIBRARY_ROOT_SETTING_KEY,),
                        ).fetchone()
                        if (
                            root_row is not None
                            and canonical_file_path(str(root_row[0])).rstrip("/")
                            == old_root_text
                        ):
                            connection.execute(
                                """
                                UPDATE library_settings
                                SET setting_value = ?,
                                    updated_at = ?
                                WHERE setting_key = ?
                                """,
                                (
                                    new_root_text,
                                    timestamp,
                                    _LIBRARY_ROOT_SETTING_KEY,
                                ),
                            )
                        connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

        return RelocationResult(
            old_root=old_root_text,
            new_root=new_root_text,
            dry_run=not apply,
            tracks_matched=len(changes),
            tracks_updated=len(changes) if apply else 0,
            missing_files=missing_files,
            conflicts=conflicts,
            changes=changes,
        )

    def clear_library(self) -> ClearLibraryResult:
        """Clear database-owned library state without touching source audio.

        Core is locked first, followed by the mandatory Artifacts database and
        the optional Evaluation database when it already exists. Sidecar
        commits complete before the Core track deletion is published. Merely
        clearing a library never creates the optional Evaluation sidecar.
        """

        tracks_deleted = 0
        embeddings_deleted = 0
        artifacts_deleted = 0
        evaluation_rows_deleted = 0
        evaluation_connection: sqlite3.Connection | None = None
        with self._write_lock:
            with closing(self.connect()) as core_connection, closing(
                self.connect_artifacts()
            ) as artifacts_connection:
                core_connection.execute("BEGIN IMMEDIATE")
                artifacts_connection.execute("BEGIN IMMEDIATE")
                try:
                    evaluation_connection = self.connect_evaluation(
                        create=False,
                    )
                    if evaluation_connection is not None:
                        evaluation_connection.execute("BEGIN IMMEDIATE")

                    tracks_deleted = int(
                        core_connection.execute(
                            "SELECT COUNT(*) FROM tracks"
                        ).fetchone()[0]
                    )
                    artifact_counts = {
                        table: int(
                            artifacts_connection.execute(
                                f"SELECT COUNT(*) FROM {table}"
                            ).fetchone()[0]
                        )
                        for table in _ARTIFACT_TABLES
                    }
                    embeddings_deleted = sum(
                        artifact_counts[table]
                        for table in _EMBEDDING_ARTIFACT_TABLES
                    )
                    artifacts_deleted = sum(artifact_counts.values())

                    if evaluation_connection is not None:
                        evaluation_rows_deleted = sum(
                            int(
                                evaluation_connection.execute(
                                    f"SELECT COUNT(*) FROM {table}"
                                ).fetchone()[0]
                            )
                            for table in _EVALUATION_DATA_TABLES
                        )

                    for table in _ARTIFACT_TABLES:
                        artifacts_connection.execute(
                            f"DELETE FROM {table}"
                        )
                    if evaluation_connection is not None:
                        for table in _EVALUATION_DATA_TABLES:
                            evaluation_connection.execute(
                                f"DELETE FROM {table}"
                            )
                    core_connection.execute("DELETE FROM track_search_fts")
                    core_connection.execute("DELETE FROM tracks")

                    artifacts_connection.commit()
                    if evaluation_connection is not None:
                        evaluation_connection.commit()
                    core_connection.commit()
                except BaseException:
                    if evaluation_connection is not None:
                        if evaluation_connection.in_transaction:
                            evaluation_connection.rollback()
                    if artifacts_connection.in_transaction:
                        artifacts_connection.rollback()
                    if core_connection.in_transaction:
                        core_connection.rollback()
                    raise
                finally:
                    if evaluation_connection is not None:
                        evaluation_connection.close()

        return ClearLibraryResult(
            tracks_deleted=tracks_deleted,
            embeddings_deleted=embeddings_deleted,
            artifacts_deleted=artifacts_deleted,
            evaluation_rows_deleted=evaluation_rows_deleted,
        )

    def remove_deleted_track(
        self,
        *,
        expected: TrackIdentity,
        file_path: str | Path,
    ) -> TrackRemovalResult:
        """Remove one exact track after its source path was already deleted.

        This method never deletes or moves audio. A present filesystem entry or
        any catalog/UUID/generation/path mismatch fails closed. Retrying after a
        successful removal is idempotent when both the exact row and path are
        already absent.
        """

        if expected.catalog_uuid != self.catalog_uuid:
            raise RuntimeError(
                "Track removal candidate belongs to a different catalog"
            )
        stored_path = canonical_file_path(file_path)
        source_path = Path(stored_path)

        with self._write_lock:
            with closing(self.connect()) as core_connection, closing(
                self.connect_artifacts()
            ) as artifacts_connection:
                core_connection.execute("BEGIN IMMEDIATE")
                try:
                    if source_path.exists() or source_path.is_symlink():
                        raise RuntimeError(
                            "Source path still exists; refusing database removal"
                        )
                    rows = core_connection.execute(
                        """
                        SELECT
                            track_id,
                            track_uuid,
                            content_generation,
                            file_path
                        FROM tracks
                        WHERE track_id = ?
                           OR file_path = ?
                        ORDER BY track_id
                        """,
                        (expected.track_id, stored_path),
                    ).fetchall()
                    exact_rows = [
                        row
                        for row in rows
                        if (
                            int(row[0]) == expected.track_id
                            and str(row[1]) == expected.track_uuid
                            and int(row[2])
                            == expected.content_generation
                            and str(row[3]) == stored_path
                        )
                    ]
                    if rows and (
                        len(rows) != 1
                        or len(exact_rows) != 1
                    ):
                        raise RuntimeError(
                            "Track identity, generation, or path changed "
                            "before database removal"
                        )
                    row_present = bool(exact_rows)

                    if source_path.exists() or source_path.is_symlink():
                        raise RuntimeError(
                            "Source path reappeared; refusing database "
                            "removal"
                        )
                    core_rows_deleted = 0
                    if row_present:
                        core_connection.execute(
                            """
                            DELETE FROM track_search_fts
                            WHERE track_id = ?
                            """,
                            (expected.track_id,),
                        )
                        cursor = core_connection.execute(
                            """
                            DELETE FROM tracks
                            WHERE track_id = ?
                              AND track_uuid = ?
                              AND content_generation = ?
                              AND file_path = ?
                            """,
                            (
                                expected.track_id,
                                expected.track_uuid,
                                expected.content_generation,
                                stored_path,
                            ),
                        )
                        if cursor.rowcount != 1:
                            raise RuntimeError(
                                "Track state changed before database "
                                "removal"
                            )
                        core_rows_deleted = 1

                    artifacts_connection.execute("BEGIN IMMEDIATE")
                    artifact_rows_deleted = 0
                    try:
                        for table in _ARTIFACT_TABLES:
                            cursor = artifacts_connection.execute(
                                f"""
                                DELETE FROM {table}
                                WHERE track_id = ?
                                   OR track_uuid = ?
                                """,
                                (
                                    expected.track_id,
                                    expected.track_uuid,
                                ),
                            )
                            artifact_rows_deleted += cursor.rowcount

                        artifacts_connection.commit()
                        core_connection.commit()
                    except BaseException:
                        if artifacts_connection.in_transaction:
                            artifacts_connection.rollback()
                        raise
                except BaseException:
                    if core_connection.in_transaction:
                        core_connection.rollback()
                    raise

        return TrackRemovalResult(
            identity=expected,
            file_path=stored_path,
            removed=row_present,
            already_absent=not row_present,
            core_rows_deleted=core_rows_deleted,
            artifact_rows_deleted=artifact_rows_deleted,
        )

    def mark_missing_if_current(
        self,
        expected: TrackFileState,
        *,
        missing_at: str | None = None,
    ) -> bool:
        """Mark one exact queued file state missing, or reject stale work."""

        if not isinstance(expected, TrackFileState):
            raise TypeError("expected must be a TrackFileState")
        timestamp = _timestamp_or_now(missing_at)
        source_path = Path(canonical_file_path(expected.file_path))
        with self._write_lock:
            with closing(self.connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    self._require_expected_file_state(connection, expected)
                    if source_path.exists() or source_path.is_symlink():
                        raise RuntimeError(
                            "Source path exists; refusing to mark queued state missing"
                        )
                    cursor = connection.execute(
                        """
                        UPDATE tracks
                        SET missing_since = ?,
                            updated_at = ?
                        WHERE track_id = ?
                          AND track_uuid = ?
                          AND content_generation = ?
                          AND file_path = ?
                          AND file_size_bytes = ?
                          AND file_modified_ns = ?
                          AND missing_since IS NULL
                        """,
                        (
                            timestamp,
                            timestamp,
                            expected.track_id,
                            expected.track_uuid,
                            expected.content_generation,
                            canonical_file_path(expected.file_path),
                            expected.file_size_bytes,
                            expected.file_modified_ns,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError(
                            "Track state changed before it could be marked missing"
                        )
                    if source_path.exists() or source_path.is_symlink():
                        raise RuntimeError(
                            "Source path reappeared while marking queued state missing"
                        )
                    connection.commit()
                    return True
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

    def mark_missing(
        self,
        track_id: int,
        *,
        missing_at: str | None = None,
    ) -> bool:
        """Mark one track missing without changing its content generation."""

        timestamp = _timestamp_or_now(missing_at)
        with self._write_lock:
            with closing(self.connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    cursor = connection.execute(
                        """
                        UPDATE tracks
                        SET missing_since = ?,
                            updated_at = ?
                        WHERE track_id = ?
                          AND missing_since IS NULL
                        """,
                        (timestamp, timestamp, int(track_id)),
                    )
                    if cursor.rowcount == 0:
                        exists = connection.execute(
                            "SELECT 1 FROM tracks WHERE track_id = ?",
                            (int(track_id),),
                        ).fetchone()
                        if exists is None:
                            raise KeyError(f"Unknown track id: {track_id}")
                    connection.commit()
                    return cursor.rowcount > 0
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

    def mark_unseen_missing(
        self,
        root: str | Path,
        seen_paths: Iterable[str | Path],
        *,
        missing_at: str | None = None,
    ) -> int:
        """Mark active tracks below *root* that were not seen by this scan."""

        timestamp = _timestamp_or_now(missing_at)
        canonical_root = canonical_file_path(root).rstrip("/")
        root_prefix = f"{canonical_root}/"
        seen = {canonical_file_path(path) for path in seen_paths}

        with self._write_lock:
            with closing(self.connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    candidates = connection.execute(
                        """
                        SELECT track_id, file_path
                        FROM tracks
                        WHERE missing_since IS NULL
                        ORDER BY track_id
                        """
                    ).fetchall()
                    missing_ids = [
                        int(row[0])
                        for row in candidates
                        if str(row[1]).startswith(root_prefix)
                        and str(row[1]) not in seen
                    ]
                    for track_id in missing_ids:
                        connection.execute(
                            """
                            UPDATE tracks
                            SET missing_since = ?,
                                updated_at = ?
                            WHERE track_id = ?
                              AND missing_since IS NULL
                            """,
                            (timestamp, timestamp, track_id),
                        )
                    connection.commit()
                    return len(missing_ids)
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

    def _delete_identity_mismatched_artifacts(
        self,
        track_id: int,
    ) -> None:
        with closing(self.connect()) as core_connection:
            core_connection.execute("BEGIN IMMEDIATE")
            try:
                row = core_connection.execute(
                    """
                    SELECT track_uuid, content_generation
                    FROM tracks
                    WHERE track_id = ?
                    """,
                    (int(track_id),),
                ).fetchone()
                with closing(self.connect_artifacts()) as artifacts_connection:
                    artifacts_connection.execute("BEGIN IMMEDIATE")
                    try:
                        for table in _ARTIFACT_TABLES:
                            if row is None:
                                artifacts_connection.execute(
                                    f"DELETE FROM {table} WHERE track_id = ?",
                                    (int(track_id),),
                                )
                            else:
                                artifacts_connection.execute(
                                    f"""
                                    DELETE FROM {table}
                                    WHERE track_id = ?
                                      AND (
                                          track_uuid <> ?
                                          OR content_generation <> ?
                                      )
                                    """,
                                    (
                                        int(track_id),
                                        str(row[0]),
                                        int(row[1]),
                                    ),
                                )
                        artifacts_connection.commit()
                    except BaseException:
                        if artifacts_connection.in_transaction:
                            artifacts_connection.rollback()
                        raise
                core_connection.commit()
            except BaseException:
                if core_connection.in_transaction:
                    core_connection.rollback()
                raise
