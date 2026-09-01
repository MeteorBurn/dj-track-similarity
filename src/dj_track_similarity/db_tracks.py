"""Thread-safe track repository for the single library database."""

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

from .db_evaluation_sidecar import delete_evaluation_track_rows
from .db_search_fts import delete_track_search_fts, upsert_track_search_fts
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


_DERIVED_TRACK_TABLES = (
    "sonara_features",
    "maest_genres",
    "classifier_scores",
    "maest_embeddings",
    "mert_embeddings",
    "muq_embeddings",
    "mulan_embeddings",
    "clap_embeddings",
)
_EMBEDDING_TABLES = (
    "maest_embeddings",
    "mert_embeddings",
    "muq_embeddings",
    "mulan_embeddings",
    "clap_embeddings",
)
_UTC_MICROSECOND_PATTERN = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z"
)
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


def _library_roots_from_json(value: object) -> list[str]:
    try:
        payload = json.loads(str(value))
    except (TypeError, json.JSONDecodeError) as error:
        raise RuntimeError("library.roots_json must contain a JSON array") from error
    if not isinstance(payload, list) or any(
        not isinstance(root, str) or not root.strip() for root in payload
    ):
        raise RuntimeError("library.roots_json must contain non-empty path strings")
    return list(payload)


def _library_roots_json(roots: Sequence[str]) -> str:
    return json.dumps(list(roots), ensure_ascii=False, separators=(",", ":"))


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
    """Resolve and normalize a path for transient track identity."""

    return ordinal_path_key(resolved_file_path(path))


def resolved_file_path(path: str | Path) -> str:
    """Return an absolute display path without changing component casing."""

    return Path(path).expanduser().resolve(strict=False).as_posix()


def _track_id_for_path(
    connection: sqlite3.Connection,
    path: str | Path,
) -> int | None:
    display_path = resolved_file_path(path)
    exact = connection.execute(
        "SELECT track_id FROM tracks WHERE file_path = ?",
        (display_path,),
    ).fetchone()
    if exact is not None:
        return int(exact[0])

    identity_key = ordinal_path_key(display_path)
    matches = [
        int(row[0])
        for row in connection.execute(
            "SELECT track_id, file_path FROM tracks ORDER BY track_id"
        )
        if ordinal_path_key(str(row[1])) == identity_key
    ]
    if len(matches) > 1:
        raise RuntimeError(
            "Multiple tracks use the same case-insensitive Windows path"
        )
    return None if not matches else matches[0]


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
    _require_optional_positive_int("bit_depth", file.bit_depth)
    _require_optional_positive_float(
        "audio_duration_seconds",
        file.audio_duration_seconds,
    )


def _normalized_audio_duration(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


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
        INSERT INTO tags(
            track_id,
            title,
            artist,
            album,
            track_number,
            label,
            country,
            year,
            tag_key,
            tag_bpm,
            comment,
            genres_json,
            tags_read_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(track_id) DO UPDATE SET
            title = excluded.title,
            artist = excluded.artist,
            album = excluded.album,
            track_number = excluded.track_number,
            label = excluded.label,
            country = excluded.country,
            year = excluded.year,
            tag_key = excluded.tag_key,
            tag_bpm = excluded.tag_bpm,
            comment = excluded.comment,
            genres_json = excluded.genres_json,
            tags_read_at = excluded.tags_read_at
        """,
        (
            int(track_id),
            tags.title,
            tags.artist,
            tags.album,
            tags.track_number,
            tags.label,
            tags.country,
            tags.year,
            tags.tag_key,
            tags.tag_bpm,
            tags.comment,
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
    file_path_key = ordinal_path_key(file_path)
    old_root_key = ordinal_path_key(old_root)
    if file_path_key == old_root_key:
        return new_root
    prefix = f"{old_root_key}/"
    if not file_path_key.startswith(prefix):
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
        old_path = str(row[2])
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
                old_path=old_path,
                new_path=new_path,
            )
        )

    moving_ids = {change["track_id"] for change in provisional}
    existing_by_path = {
        ordinal_path_key(str(row[2])): int(row[0])
        for row in rows
    }
    planned_by_path: dict[str, int] = {}
    conflicts: list[RelocationConflict] = []
    missing_files: list[MissingRelocationFile] = []
    for change in provisional:
        new_path_key = ordinal_path_key(change["new_path"])
        existing_track_id = existing_by_path.get(new_path_key)
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
        planned_track_id = planned_by_path.get(new_path_key)
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
        planned_by_path[new_path_key] = change["track_id"]
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
    """Track repository mixed into :class:`LibraryDatabase`.

    The host must expose ``connect()`` and one path-scoped re-entrant
    ``_write_lock``.
    """

    _write_lock: threading.RLock
    catalog_uuid: str

    def connect(self) -> sqlite3.Connection:
        raise NotImplementedError

    def connect_evaluation(
        self,
        *,
        create: bool = False,
    ) -> sqlite3.Connection | None:
        raise NotImplementedError

    def _purge_evaluation_rows(self, track_id: int) -> None:
        """Drop one deleted track's rows from the Evaluation sidecar.

        The sidecar is a separate file, so SQLite cannot cascade a catalog
        delete into it and the rows would outlive the track. This runs after the
        catalog delete commits: the sidecar holds derived evidence, and clearing
        it for a track that then survived a failed delete is the worse trade.
        """

        connection = self.connect_evaluation(create=False)
        if connection is None:
            return
        try:
            with connection:
                delete_evaluation_track_rows(connection, (track_id,))
        finally:
            connection.close()

    def get_track_identity(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> TrackIdentity | None:
        """Return one current library identity or ``None`` when unavailable."""

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
                        SELECT track_id, track_uuid
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
            if rows_by_id[track_id][5] is not None
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
                missing_since=(
                    str(row[5])
                    if row[5] is not None
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
        with closing(self.connect()) as connection:
            track_id = _track_id_for_path(connection, path)
            if track_id is None:
                return None
            row = connection.execute(
                """
                SELECT
                    track_id,
                    track_uuid,
                    file_path,
                    file_size_bytes,
                    file_modified_ns,
                    missing_since
                FROM tracks
                WHERE track_id = ?
                """,
                (track_id,),
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
            missing_since=str(row[5]) if row[5] is not None else None,
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
        stored_path = resolved_file_path(file.file_path)
        audio_duration_seconds = _normalized_audio_duration(
            file.audio_duration_seconds
        )

        with self._write_lock:
            with closing(self.connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    track_id = _track_id_for_path(connection, stored_path)
                    row = connection.execute(
                        """
                        SELECT
                            track_id,
                            track_uuid,
                            file_size_bytes,
                            file_modified_ns
                        FROM tracks
                        WHERE track_id = ?
                        """,
                        (track_id,),
                    ).fetchone() if track_id is not None else None

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
                                sample_rate_hz,
                                channel_count,
                                bit_rate_bps,
                                bit_depth,
                                audio_duration_seconds,
                                last_scanned_at,
                                missing_since,
                                created_at,
                                updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                            """,
                            (
                                track_uuid,
                                stored_path,
                                int(file.file_size_bytes),
                                int(file.file_modified_ns),
                                file.audio_format,
                                file.sample_rate_hz,
                                file.channel_count,
                                file.bit_rate_bps,
                                file.bit_depth,
                                audio_duration_seconds,
                                timestamp,
                                timestamp,
                                timestamp,
                            ),
                        )
                        identity = TrackIdentity(
                            catalog_uuid=self.catalog_uuid,
                            track_id=int(cursor.lastrowid),
                            track_uuid=track_uuid,
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
                            int(row[2]) == int(file.file_size_bytes)
                            and int(row[3]) == int(file.file_modified_ns)
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
                                SET file_path = ?,
                                    last_scanned_at = ?,
                                    missing_since = NULL
                                WHERE track_id = ?
                                """,
                                (
                                    stored_path,
                                    timestamp,
                                    identity.track_id,
                                ),
                            )
                            upsert_track_search_fts(
                                connection,
                                identity.track_id,
                            )
                        else:
                            identity = TrackIdentity(
                                catalog_uuid=self.catalog_uuid,
                                track_id=int(row[0]),
                                track_uuid=str(row[1]),
                            )
                            action = "updated"
                            connection.execute(
                                """
                                UPDATE tracks
                                SET file_path = ?,
                                    file_size_bytes = ?,
                                    file_modified_ns = ?,
                                    audio_format = ?,
                                    sample_rate_hz = ?,
                                    channel_count = ?,
                                    bit_rate_bps = ?,
                                    bit_depth = ?,
                                    audio_duration_seconds = ?,
                                    last_scanned_at = ?,
                                    missing_since = NULL,
                                    updated_at = ?
                                WHERE track_id = ?
                                """,
                                (
                                    stored_path,
                                    int(file.file_size_bytes),
                                    int(file.file_modified_ns),
                                    file.audio_format,
                                    file.sample_rate_hz,
                                    file.channel_count,
                                    file.bit_rate_bps,
                                    file.bit_depth,
                                    audio_duration_seconds,
                                    timestamp,
                                    timestamp,
                                    identity.track_id,
                                ),
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

            return TrackMutation(action=action, identity=identity)

    def refresh_file_tags(
        self,
        expected: TrackFileState,
        tags: FileTags,
        *,
        technical_file: ScannedFile | None = None,
        tags_read_at: str | None = None,
    ) -> TrackIdentity:
        """Refresh tags and technical facts for one unchanged source snapshot."""

        if not isinstance(expected, TrackFileState):
            raise TypeError("expected must be a TrackFileState")
        _validate_tags(tags)
        if technical_file is not None:
            _validate_file_facts(technical_file)
            if (
                resolved_file_path(technical_file.file_path)
                != resolved_file_path(expected.file_path)
                or int(technical_file.file_size_bytes) != expected.file_size_bytes
                or int(technical_file.file_modified_ns) != expected.file_modified_ns
            ):
                raise ValueError(
                    "technical_file must match the expected source file snapshot"
                )
        timestamp = _timestamp_or_now(tags_read_at)
        source_path = Path(resolved_file_path(expected.file_path))
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
                    if technical_file is not None:
                        connection.execute(
                            """
                            UPDATE tracks
                            SET audio_format = ?,
                                sample_rate_hz = ?,
                                channel_count = ?,
                                bit_rate_bps = ?,
                                bit_depth = ?,
                                audio_duration_seconds = ?,
                                last_scanned_at = ?,
                                missing_since = NULL
                            WHERE track_id = ?
                            """,
                            (
                                technical_file.audio_format,
                                technical_file.sample_rate_hz,
                                technical_file.channel_count,
                                technical_file.bit_rate_bps,
                                technical_file.bit_depth,
                                _normalized_audio_duration(
                                    technical_file.audio_duration_seconds
                                ),
                                timestamp,
                                expected.track_id,
                            ),
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

        The path-scoped repository lock and a library ``BEGIN IMMEDIATE`` span the
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
        source_path = Path(resolved_file_path(expected.file_path))

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
                expected.file_path,
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
        stored_path_key = canonical_file_path(expected.file_path)
        path_track_id = _track_id_for_path(connection, expected.file_path)
        row = connection.execute(
            """
            SELECT
                track_id,
                track_uuid,
                file_path,
                file_size_bytes,
                file_modified_ns,
                missing_since
            FROM tracks
            WHERE track_id = ?
            """,
            (expected.track_id,),
        ).fetchone()
        if (
            row is None
            or path_track_id != expected.track_id
            or str(row[1]) != expected.track_uuid
            or canonical_file_path(str(row[2])) != stored_path_key
            or int(row[3]) != expected.file_size_bytes
            or int(row[4]) != expected.file_modified_ns
            or row[5] is not None
        ):
            raise RuntimeError(
                "Track identity, path, or stored file facts changed after "
                "candidate selection"
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

    def record_library_root(self, root: str | Path) -> tuple[str, ...]:
        """Record a scan root in ``library.roots_json`` without duplicates."""

        canonical_root = resolved_file_path(root).rstrip("/")
        timestamp = utc_now_text()
        with self._write_lock:
            with closing(self.connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    row = connection.execute(
                        "SELECT roots_json FROM library WHERE singleton_id = 1"
                    ).fetchone()
                    if row is None:
                        raise RuntimeError("library metadata row is missing")
                    roots = _library_roots_from_json(row[0])
                    root_keys = {ordinal_path_key(value) for value in roots}
                    if ordinal_path_key(canonical_root) not in root_keys:
                        roots.append(canonical_root)
                        connection.execute(
                            """
                            UPDATE library
                            SET roots_json = ?, updated_at = ?
                            WHERE singleton_id = 1
                            """,
                            (_library_roots_json(roots), timestamp),
                        )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        return tuple(roots)

    def relocate_library(
        self,
        old_root: str | Path,
        new_root: str | Path,
        *,
        apply: bool = False,
    ) -> RelocationResult:
        """Preview or apply a database-only canonical path relocation.

        Apply never moves, copies, deletes, or retags audio. It changes only
        ``tracks.file_path``, its FTS projection, and matching paths in
        ``library.roots_json``. Stable UUIDs and all analysis rows are
        preserved.
        """

        old_root_text = resolved_file_path(old_root).rstrip("/")
        new_root_text = resolved_file_path(new_root).rstrip("/")
        if ordinal_path_key(old_root_text) == ordinal_path_key(new_root_text):
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
                            str(row[2])
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
                                  AND file_path = ?
                                """,
                                (
                                    temporary_path,
                                    timestamp,
                                    change["track_id"],
                                    change["track_uuid"],
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
                                  AND file_path = ?
                                """,
                                (
                                    change["new_path"],
                                    timestamp,
                                    change["track_id"],
                                    change["track_uuid"],
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
                            "SELECT roots_json FROM library WHERE singleton_id = 1"
                        ).fetchone()
                        if root_row is None:
                            raise RuntimeError("library metadata row is missing")
                        roots = _library_roots_from_json(root_row[0])
                        relocated_roots = [
                            new_root_text
                            if ordinal_path_key(root) == ordinal_path_key(old_root_text)
                            else root
                            for root in roots
                        ]
                        if relocated_roots != roots:
                            connection.execute(
                                """
                                UPDATE library
                                SET roots_json = ?, updated_at = ?
                                WHERE singleton_id = 1
                                """,
                                (
                                    _library_roots_json(relocated_roots),
                                    timestamp,
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
        """Clear library-owned data without touching source audio.

        Evaluation data remains in its optional, independent database. This
        operation never creates that database.
        """

        tracks_deleted = 0
        feature_rows_deleted = 0
        embedding_rows_deleted = 0
        classifier_rows_deleted = 0
        with self._write_lock:
            with closing(self.connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    tracks_deleted = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM tracks"
                        ).fetchone()[0]
                    )
                    derived_counts = {
                        table: int(
                            connection.execute(
                                f"SELECT COUNT(*) FROM {table}"
                            ).fetchone()[0]
                        )
                        for table in _DERIVED_TRACK_TABLES
                    }
                    embedding_rows_deleted = sum(
                        derived_counts[table]
                        for table in _EMBEDDING_TABLES
                    )
                    feature_rows_deleted = sum(
                        derived_counts[table]
                        for table in ("sonara_features", "maest_genres")
                    )
                    classifier_rows_deleted = derived_counts["classifier_scores"]
                    connection.execute("DELETE FROM track_search_fts")
                    connection.execute("DELETE FROM tracks")
                    connection.execute(
                        """
                        UPDATE library
                        SET roots_json = '[]',
                            sonara_bpm_min = NULL,
                            sonara_bpm_max = NULL,
                            updated_at = ?
                        WHERE singleton_id = 1
                        """,
                        (utc_now_text(),),
                    )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

        return ClearLibraryResult(
            tracks_deleted=tracks_deleted,
            feature_rows_deleted=feature_rows_deleted,
            embedding_rows_deleted=embedding_rows_deleted,
            classifier_rows_deleted=classifier_rows_deleted,
        )

    def remove_deleted_track(
        self,
        *,
        expected: TrackIdentity,
        file_path: str | Path,
    ) -> TrackRemovalResult:
        """Remove one exact track after its source path was already deleted.

        This method never deletes or moves audio. A present filesystem entry or
        any catalog/UUID/path mismatch fails closed. Retrying after a
        successful removal is idempotent when both the exact row and path are
        already absent.
        """

        if expected.catalog_uuid != self.catalog_uuid:
            raise RuntimeError(
                "Track removal candidate belongs to a different catalog"
            )
        requested_path = resolved_file_path(file_path)
        requested_path_key = canonical_file_path(requested_path)
        source_path = Path(requested_path)
        track_rows_deleted = 0
        derived_rows_deleted = 0

        with self._write_lock:
            with closing(self.connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    if source_path.exists() or source_path.is_symlink():
                        raise RuntimeError(
                            "Source path still exists; refusing database removal"
                        )
                    path_track_id = _track_id_for_path(
                        connection,
                        requested_path,
                    )
                    row = connection.execute(
                        """
                        SELECT
                            track_id,
                            track_uuid,
                            file_path
                        FROM tracks
                        WHERE track_id = ?
                        """,
                        (expected.track_id,),
                    ).fetchone()
                    row_present = row is not None
                    if row_present and (
                        path_track_id != expected.track_id
                        or str(row[1]) != expected.track_uuid
                        or canonical_file_path(str(row[2]))
                        != requested_path_key
                    ):
                        raise RuntimeError(
                            "Track identity or path changed "
                            "before database removal"
                        )
                    if not row_present and path_track_id is not None:
                        raise RuntimeError(
                            "Track path now belongs to a different identity"
                        )
                    stored_path = (
                        str(row[2])
                        if row_present
                        else requested_path
                    )

                    if source_path.exists() or source_path.is_symlink():
                        raise RuntimeError(
                            "Source path reappeared; refusing database "
                            "removal"
                        )
                    if row_present:
                        derived_rows_deleted = sum(
                            int(
                                connection.execute(
                                    f"SELECT COUNT(*) FROM {table} WHERE track_id = ?",
                                    (expected.track_id,),
                                ).fetchone()[0]
                            )
                            for table in _DERIVED_TRACK_TABLES
                        )
                        connection.execute(
                            """
                            DELETE FROM track_search_fts
                            WHERE track_id = ?
                            """,
                            (expected.track_id,),
                        )
                        cursor = connection.execute(
                            """
                            DELETE FROM tracks
                            WHERE track_id = ?
                              AND track_uuid = ?
                              AND file_path = ?
                            """,
                            (
                                expected.track_id,
                                expected.track_uuid,
                                stored_path,
                            ),
                        )
                        if cursor.rowcount != 1:
                            raise RuntimeError(
                                "Track state changed before database "
                                "removal"
                            )
                        track_rows_deleted = 1
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

        if row_present:
            self._purge_evaluation_rows(expected.track_id)

        return TrackRemovalResult(
            identity=expected,
            file_path=stored_path,
            removed=row_present,
            already_absent=not row_present,
            track_rows_deleted=track_rows_deleted,
            derived_rows_deleted=derived_rows_deleted,
        )

    def delete_track(self, *, expected: TrackIdentity) -> None:
        """Delete one current catalog track and its database-owned relations.

        The source audio path is deliberately never accessed or changed.
        SQLite foreign-key cascades remove related catalog rows atomically.
        """

        if expected.catalog_uuid != self.catalog_uuid:
            raise RuntimeError("Track deletion candidate belongs to a different catalog")

        with self._write_lock:
            with closing(self.connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    row = connection.execute(
                        "SELECT track_uuid FROM tracks WHERE track_id = ?",
                        (expected.track_id,),
                    ).fetchone()
                    if row is None:
                        raise KeyError(f"Track {expected.track_id} was not found")
                    if str(row[0]) != expected.track_uuid:
                        raise RuntimeError("Track identity changed before deletion")
                    delete_track_search_fts(connection, expected.track_id)
                    connection.execute(
                        "DELETE FROM tracks WHERE track_id = ? AND track_uuid = ?",
                        (expected.track_id, expected.track_uuid),
                    )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise

        self._purge_evaluation_rows(expected.track_id)

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
        source_path = Path(resolved_file_path(expected.file_path))
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
                            expected.file_path,
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
        """Mark one track missing without changing its stored analysis."""

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
                        if canonical_file_path(str(row[1])).startswith(
                            root_prefix
                        )
                        and canonical_file_path(str(row[1])) not in seen
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
