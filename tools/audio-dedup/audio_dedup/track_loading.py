from __future__ import annotations

import math
from pathlib import Path
import sqlite3
from typing import Iterable

import numpy as np

from dj_track_similarity.analysis_models import current_embedding_spec
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_tracks import canonical_file_path, ordinal_path_key

from . import config as config_module
from . import models as models_module
from . import progress as progress_module
from . import values as values_module

TRACK_LOAD_CHUNK_SIZE = 200
EMBEDDING_LOAD_CHUNK_SIZE = 200


def load_tracks(
    database: LibraryDatabase | Path,
    *,
    root: Path,
    path_contains: list[str],
    sources: Iterable[str] | None = None,
    progress_callback: models_module.ProgressCallback | None = None,
) -> list[models_module.TrackRecord]:
    selected_database = (
        database
        if isinstance(database, LibraryDatabase)
        else _resolve_database(database=None, db_path=database)
    )
    root_text = canonical_file_path(root)
    contains = [ordinal_path_key(item) for item in path_contains if item.strip()]
    selected_sources = tuple(config_module.SUPPORTED_EMBEDDINGS if sources is None else sources)
    unsupported_sources = set(selected_sources) - set(config_module.SUPPORTED_EMBEDDINGS)
    if unsupported_sources:
        raise ValueError(
            "Unsupported embedding source(s): "
            + ", ".join(sorted(unsupported_sources))
        )
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
                s.detected_bpm,
                s.danceability_score,
                s.energy_score,
                s.valence_score,
                s.acousticness_score,
                s.spectral_centroid_hz,
                s.onset_density_per_second,
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
                if _path_matches(row["file_path"], root_text, contains):
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
        _attach_embeddings(
            connection,
            tracks,
            sources=selected_sources,
            progress_callback=progress_callback,
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
            "bpm": row["detected_bpm"],
            "danceability": row["danceability_score"],
            "energy": row["energy_score"],
            "valence": row["valence_score"],
            "acousticness": row["acousticness_score"],
            "spectral_centroid_mean": row["spectral_centroid_hz"],
            "onset_density": row["onset_density_per_second"],
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
        embeddings={},
        catalog_uuid=catalog_uuid,
        track_uuid=str(row["track_uuid"]),
        file_modified_ns=modified_ns,
    )


def _attach_embeddings(
    connection: sqlite3.Connection,
    tracks: list[models_module.TrackRecord],
    *,
    sources: Iterable[str] = config_module.SUPPORTED_EMBEDDINGS,
    progress_callback: models_module.ProgressCallback | None = None,
) -> None:
    if not tracks:
        return
    embeddings_by_track = {track.track_id: {} for track in tracks}
    identity_by_track = {
        track.track_id: track.track_uuid
        for track in tracks
    }
    track_ids = [track.track_id for track in tracks]
    for family in sources:
        if family not in config_module.SUPPORTED_EMBEDDINGS:
            raise ValueError(f"Unsupported embedding source: {family}")
        specification = current_embedding_spec(family)
        table = f"{family}_embeddings"
        message = f"Loading {family.upper()} embeddings"
        progress_module._report_progress(progress_callback, 0, len(track_ids), message)
        processed = 0
        for chunk in values_module._chunks(track_ids, EMBEDDING_LOAD_CHUNK_SIZE):
            placeholders = ",".join("?" for _ in chunk)
            rows = connection.execute(
                f"""
                SELECT
                    track_id,
                    track_uuid,
                    dim,
                    normalization,
                    embedding_blob
                FROM {table}
                WHERE track_id IN ({placeholders})
                ORDER BY track_id
                """,
                chunk,
            ).fetchall()
            for row in rows:
                track_id = int(row["track_id"])
                expected_identity = identity_by_track.get(track_id)
                if expected_identity != str(row["track_uuid"]):
                    continue
                dim = int(row["dim"])
                if (
                    dim != specification.dimension
                    or str(row["normalization"]) != specification.normalization
                ):
                    continue
                vector = np.frombuffer(
                    row["embedding_blob"],
                    dtype="<f4",
                ).copy()
                if (
                    vector.shape != (dim,)
                    or not np.all(np.isfinite(vector))
                ):
                    continue
                norm = float(np.linalg.norm(vector))
                if not math.isfinite(norm) or norm <= 0:
                    continue
                if (
                    specification.normalization == "l2"
                    and not np.isclose(
                        norm,
                        1.0,
                        rtol=1e-4,
                        atol=1e-5,
                    )
                ):
                    continue
                embeddings_by_track[track_id][family] = (
                    vector / norm
                ).astype(np.float32)
            processed += len(chunk)
            progress_module._report_progress(progress_callback, processed, len(track_ids), message)
    for index, track in enumerate(tracks):
        tracks[index] = models_module.TrackRecord(
            track_id=track.track_id,
            path=track.path,
            size=track.size,
            mtime=track.mtime,
            artist=track.artist,
            title=track.title,
            album=track.album,
            bpm=track.bpm,
            musical_key=track.musical_key,
            duration=track.duration,
            metadata=track.metadata,
            embeddings=embeddings_by_track[track.track_id],
            catalog_uuid=track.catalog_uuid,
            track_uuid=track.track_uuid,
            file_modified_ns=track.file_modified_ns,
        )

def _path_matches(path: str, root: str, contains: list[str]) -> bool:
    key = canonical_file_path(path)
    root_key = canonical_file_path(root).rstrip("/")
    if key != root_key and not key.startswith(root_key + "/"):
        return False
    return all(item in key for item in contains)
