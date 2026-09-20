from __future__ import annotations

from pathlib import Path
import sqlite3

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.tracks import canonical_file_path, ordinal_path_key

from . import models as models_module
from . import progress as progress_module
from . import values as values_module

TRACK_LOAD_CHUNK_SIZE = 200


def load_tracks(
    database: LibraryDatabase | Path,
    *,
    path_contains: list[str],
    progress_callback: models_module.ProgressCallback | None = None,
) -> list[models_module.TrackRecord]:
    selected_database = (
        database
        if isinstance(database, LibraryDatabase)
        else _resolve_database(database=None, db_path=database)
    )
    contains = [ordinal_path_key(item) for item in path_contains if item.strip()]
    connection = selected_database.connect()
    try:
        active_track_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM tracks WHERE missing_since IS NULL"
            ).fetchone()[0]
        )
        progress_module._report_progress(
            progress_callback,
            0,
            active_track_count,
            "Loading scoped tracks",
        )
        cursor = connection.execute(
            """
            SELECT
                t.track_id,
                t.track_uuid,
                t.file_path,
                t.file_size_bytes,
                t.file_modified_ns,
                t.sample_rate_hz,
                t.bit_rate_bps,
                t.bit_depth,
                t.channel_count,
                t.audio_duration_seconds,
                ft.artist,
                ft.title,
                ft.album,
                ft.tag_bpm,
                ft.tag_key,
                ft.genres_json,
                s.dynamic_range_db,
                s.loudness_range_lu,
                s.true_peak_dbtp,
                s.integrated_loudness_lufs
            FROM tracks AS t
            LEFT JOIN tags AS ft
              ON ft.track_id = t.track_id
            LEFT JOIN sonara_features AS s
              ON s.track_id = t.track_id
            WHERE t.missing_since IS NULL
            ORDER BY t.track_id
            """,
        )
        tracks: list[models_module.TrackRecord] = []
        processed = 0
        while rows := cursor.fetchmany(TRACK_LOAD_CHUNK_SIZE):
            for row in rows:
                if _path_matches(row["file_path"], contains):
                    tracks.append(
                        _track_from_row(
                            row,
                            catalog_uuid=selected_database.catalog_uuid,
                        )
                    )
            processed += len(rows)
            progress_module._report_progress(
                progress_callback,
                processed,
                active_track_count,
                "Loading scoped tracks",
            )
    finally:
        connection.close()
    return tracks


def count_database_tracks(database: LibraryDatabase | Path) -> int:
    selected_database = (
        database
        if isinstance(database, LibraryDatabase)
        else _resolve_database(database=None, db_path=database)
    )
    connection = selected_database.connect()
    try:
        return int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
    finally:
        connection.close()


def _resolve_database(
    *,
    database: LibraryDatabase | None,
    db_path: Path | None,
) -> LibraryDatabase:
    if database is not None:
        if db_path is not None:
            raise ValueError("Pass either database or db_path, not both")
        return database
    if db_path is None:
        raise ValueError("Database path is required")
    selected = Path(db_path).expanduser().resolve(strict=False)
    if not selected.is_file():
        raise FileNotFoundError(f"Database does not exist: {selected}")
    return LibraryDatabase(selected)


def _track_from_row(
    row: sqlite3.Row,
    *,
    catalog_uuid: str,
) -> models_module.TrackRecord:
    genres = values_module._json_string_list(row["genres_json"])
    sonara_features = {
        key: value
        for key, value in {
            "dynamic_range_db": row["dynamic_range_db"],
            "loudness_range_lu": row["loudness_range_lu"],
            "true_peak_dbtp": row["true_peak_dbtp"],
            "loudness_lufs": row["integrated_loudness_lufs"],
        }.items()
        if value is not None
    }
    metadata: dict[str, object] = {}
    if genres:
        metadata["genres"] = genres
    if sonara_features:
        metadata["sonara_features"] = sonara_features
    if row["sample_rate_hz"] is not None:
        metadata["sample_rate_hz"] = int(row["sample_rate_hz"])
    if row["bit_rate_bps"] is not None:
        metadata["bit_rate_bps"] = int(row["bit_rate_bps"])
    if row["bit_depth"] is not None:
        metadata["bit_depth"] = int(row["bit_depth"])
    if row["channel_count"] is not None:
        metadata["channel_count"] = int(row["channel_count"])
    modified_ns = int(row["file_modified_ns"])
    return models_module.TrackRecord(
        track_id=int(row["track_id"]),
        path=str(row["file_path"]),
        size=int(row["file_size_bytes"]),
        mtime=modified_ns / 1_000_000_000,
        artist=values_module._string_or_none(row["artist"]),
        title=values_module._string_or_none(row["title"]),
        album=values_module._string_or_none(row["album"]),
        bpm=values_module._float_or_none(row["tag_bpm"]),
        musical_key=values_module._string_or_none(row["tag_key"]),
        duration=values_module._float_or_none(row["audio_duration_seconds"]),
        metadata=metadata,
        catalog_uuid=catalog_uuid,
        track_uuid=str(row["track_uuid"]),
        file_modified_ns=modified_ns,
    )


def _path_matches(path: str, contains: list[str]) -> bool:
    """Whether one stored path carries every requested fragment."""
    key = canonical_file_path(path)
    return all(item in key for item in contains)
