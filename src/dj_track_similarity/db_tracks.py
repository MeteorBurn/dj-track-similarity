from __future__ import annotations

from contextlib import nullcontext as _nullcontext
import sqlite3
from pathlib import Path
from typing import Iterable

from .db_library_queries import build_track_filter_sql, combine_where_condition, split_primary_classifier_filter, track_order_sql
from .db_repository_utils import (
    DEFAULT_EMBEDDING_KEY,
    LIBRARY_ROOT_SETTING_KEY,
    _classifier_scores_from_row,
    _embedding_keys_for_track,
    _normalize_root,
    _relocate_path,
    normalize_path,
)
from .db_schema import TRACK_SELECT_FIELDS, TRACK_SLIM_SELECT_FIELDS
from .db_search_fts import fts_match_query, normalize_search_mode, rebuild_track_search_fts, upsert_track_search_fts
from .metadata_payload import (
    analyses_from_row,
    genres_from_metadata,
    metadata_from_json,
    metadata_to_json,
    optional_float,
    string_or_none,
)
from .models import Track


class TrackRepository:
    def get_track_by_path(self, path: str | Path) -> Track | None:
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE t.path = ?
                """,
                (DEFAULT_EMBEDDING_KEY, normalize_path(path)),
            ).fetchone()
        return self._row_to_track(row) if row else None

    def get_library_root(self) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT value FROM library_settings WHERE key = ?",
                (LIBRARY_ROOT_SETTING_KEY,),
            ).fetchone()
        return str(row["value"]) if row is not None else None

    def set_library_root(self, root: str | Path) -> str:
        normalized = normalize_path(root)
        with self._write_lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO library_settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (LIBRARY_ROOT_SETTING_KEY, normalized),
            )
        return normalized

    def get_track(self, track_id: int) -> Track:
        with self.connect() as connection:
            row = connection.execute(
                f"""
                SELECT {TRACK_SELECT_FIELDS}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                WHERE t.id = ?
                """,
                (DEFAULT_EMBEDDING_KEY, track_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown track id: {track_id}")
        return self._row_to_track(row)

    def upsert_track(
        self,
        *,
        path: str | Path,
        size: int,
        mtime: float,
        metadata: dict[str, object] | None = None,
        bpm: float | None = None,
        musical_key: str | None = None,
        energy: float | None = None,
        duration: float | None = None,
    ) -> int:
        metadata = metadata or {}
        normalized = normalize_path(path)
        artist = string_or_none(metadata.get("artist"))
        title = string_or_none(metadata.get("title")) or Path(path).stem
        album = string_or_none(metadata.get("album"))
        bpm = optional_float(bpm) if bpm is not None else optional_float(metadata.get("bpm"))
        musical_key = musical_key or string_or_none(metadata.get("key")) or string_or_none(metadata.get("initialkey"))
        energy = optional_float(energy)
        duration = optional_float(duration) if duration is not None else optional_float(metadata.get("duration"))
        metadata_json = metadata_to_json(metadata)
        has_sonara_analysis = 1 if metadata.get("sonara_features") is not None else 0

        with self._write_lock, self.connect() as connection:
            connection.execute(
                """
                INSERT INTO tracks (
                    path, size, mtime, artist, title, album, bpm, musical_key,
                    energy, duration, has_sonara_analysis, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    size = excluded.size,
                    mtime = excluded.mtime,
                    artist = excluded.artist,
                    title = excluded.title,
                    album = excluded.album,
                    bpm = excluded.bpm,
                    musical_key = excluded.musical_key,
                    energy = excluded.energy,
                    duration = excluded.duration,
                    has_sonara_analysis = excluded.has_sonara_analysis,
                    metadata_json = excluded.metadata_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    normalized,
                    int(size),
                    float(mtime),
                    artist,
                    title,
                    album,
                    bpm,
                    musical_key,
                    energy,
                    duration,
                    has_sonara_analysis,
                    metadata_json,
                ),
            )
            row = connection.execute("SELECT id FROM tracks WHERE path = ?", (normalized,)).fetchone()
            if row is not None:
                upsert_track_search_fts(connection, int(row["id"]))
            embedding_keys = _embedding_keys_for_track(connection, int(row["id"])) if row is not None else ()
        self._invalidate_embedding_cache_keys(embedding_keys)
        self._invalidate_sonara_feature_cache()
        if row is None:
            raise RuntimeError(f"Failed to upsert track: {normalized}")
        return int(row["id"])

    def list_tracks(
        self,
        *,
        with_embeddings: bool | None = None,
        embedding_key: str = DEFAULT_EMBEDDING_KEY,
        include_metadata: bool = True,
    ) -> list[Track]:
        fields = TRACK_SELECT_FIELDS if include_metadata else TRACK_SLIM_SELECT_FIELDS
        where = ""
        if with_embeddings is True:
            where = "WHERE e.track_id IS NOT NULL"
        elif with_embeddings is False:
            where = "WHERE e.track_id IS NULL"
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {fields}
                FROM tracks t
                LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                {where}
                ORDER BY COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                """,
                (embedding_key,),
            ).fetchall()
        return [self._row_to_track(row, include_metadata=include_metadata) for row in rows]

    def list_tracks_page(
        self,
        *,
        query: str = "",
        preset: str = "all",
        liked_only: bool = False,
        classifier_min_scores: dict[str, float] | None = None,
        limit: int = 100,
        offset: int = 0,
        include_metadata: bool = False,
        embedding_key: str = DEFAULT_EMBEDDING_KEY,
        search_mode: str = "like",
    ) -> dict[str, object]:
        mode = normalize_search_mode(search_mode)
        use_fts = mode == "fts" and bool(query.strip())
        fts_query = fts_match_query(query) if use_fts else ""
        fields = TRACK_SELECT_FIELDS if include_metadata else TRACK_SLIM_SELECT_FIELDS
        thresholds = dict(classifier_min_scores or {})
        primary_classifier, remaining_thresholds = split_primary_classifier_filter(thresholds)
        where_sql, params = build_track_filter_sql(
            query="" if use_fts else query,
            preset=preset,
            liked_only=liked_only,
            classifier_min_scores=remaining_thresholds if primary_classifier else thresholds,
        )
        if use_fts:
            condition = "track_search_fts MATCH ?" if fts_query else "0 = 1"
            where_sql = combine_where_condition(condition, where_sql)
            if fts_query:
                params = [fts_query, *params]
        order_sql = track_order_sql(classifier_min_scores=thresholds)
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        with self.connect() as connection:
            if primary_classifier:
                classifier, threshold = primary_classifier
                fts_join = "JOIN track_search_fts fts ON fts.track_id = t.id" if use_fts and fts_query else ""
                classifier_where = combine_where_condition(
                    "primary_cs.classifier = ? AND primary_cs.score >= ?",
                    where_sql,
                )
                classifier_params = (classifier, threshold, *params)
                total = int(
                    connection.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM track_classifier_scores primary_cs
                        JOIN tracks t ON t.id = primary_cs.track_id
                        {fts_join}
                        {classifier_where}
                        """,
                        classifier_params,
                    ).fetchone()[0]
                )
                rows = connection.execute(
                    f"""
                    SELECT {fields}
                    FROM track_classifier_scores primary_cs
                    JOIN tracks t ON t.id = primary_cs.track_id
                    {fts_join}
                    LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                    {classifier_where}
                    ORDER BY primary_cs.score DESC, COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                    LIMIT ? OFFSET ?
                    """,
                    (embedding_key, *classifier_params, bounded_limit, bounded_offset),
                ).fetchall()
            else:
                from_sql = "track_search_fts fts JOIN tracks t ON t.id = fts.track_id" if use_fts and fts_query else "tracks t"
                total = int(connection.execute(f"SELECT COUNT(*) FROM {from_sql} {where_sql}", params).fetchone()[0])
                rows = connection.execute(
                    f"""
                    SELECT {fields}
                    FROM {from_sql}
                    LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                    {where_sql}
                    ORDER BY {order_sql}
                    LIMIT ? OFFSET ?
                    """,
                    (embedding_key, *params, bounded_limit, bounded_offset),
                ).fetchall()
        return {
            "items": [self._row_to_track(row, include_metadata=include_metadata) for row in rows],
            "total": total,
            "limit": bounded_limit,
            "offset": bounded_offset,
        }

    def list_filtered_tracks(
        self,
        *,
        query: str = "",
        preset: str = "all",
        liked_only: bool = False,
        classifier_min_scores: dict[str, float] | None = None,
        include_metadata: bool = False,
        embedding_key: str = DEFAULT_EMBEDDING_KEY,
        search_mode: str = "like",
    ) -> dict[str, object]:
        mode = normalize_search_mode(search_mode)
        use_fts = mode == "fts" and bool(query.strip())
        fts_query = fts_match_query(query) if use_fts else ""
        fields = TRACK_SELECT_FIELDS if include_metadata else TRACK_SLIM_SELECT_FIELDS
        thresholds = dict(classifier_min_scores or {})
        primary_classifier, remaining_thresholds = split_primary_classifier_filter(thresholds)
        where_sql, params = build_track_filter_sql(
            query="" if use_fts else query,
            preset=preset,
            liked_only=liked_only,
            classifier_min_scores=remaining_thresholds if primary_classifier else thresholds,
        )
        if use_fts:
            condition = "track_search_fts MATCH ?" if fts_query else "0 = 1"
            where_sql = combine_where_condition(condition, where_sql)
            if fts_query:
                params = [fts_query, *params]
        order_sql = track_order_sql(classifier_min_scores=thresholds)
        with self.connect() as connection:
            if primary_classifier:
                classifier, threshold = primary_classifier
                fts_join = "JOIN track_search_fts fts ON fts.track_id = t.id" if use_fts and fts_query else ""
                classifier_where = combine_where_condition(
                    "primary_cs.classifier = ? AND primary_cs.score >= ?",
                    where_sql,
                )
                rows = connection.execute(
                    f"""
                    SELECT {fields}
                    FROM track_classifier_scores primary_cs
                    JOIN tracks t ON t.id = primary_cs.track_id
                    {fts_join}
                    LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                    {classifier_where}
                    ORDER BY primary_cs.score DESC, COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path
                    """,
                    (embedding_key, classifier, threshold, *params),
                ).fetchall()
            else:
                from_sql = "track_search_fts fts JOIN tracks t ON t.id = fts.track_id" if use_fts and fts_query else "tracks t"
                rows = connection.execute(
                    f"""
                    SELECT {fields}
                    FROM {from_sql}
                    LEFT JOIN embeddings e ON e.track_id = t.id AND e.embedding_key = ?
                    {where_sql}
                    ORDER BY {order_sql}
                    """,
                    (embedding_key, *params),
                ).fetchall()
        tracks = [self._row_to_track(row, include_metadata=include_metadata) for row in rows]
        return {"items": tracks, "total": len(tracks)}

    def set_track_liked(self, track_id: int, liked: bool) -> Track:
        with self._write_lock, self.connect() as connection:
            row = connection.execute("SELECT id FROM tracks WHERE id = ?", (int(track_id),)).fetchone()
            if row is None:
                raise KeyError(f"Unknown track id: {track_id}")
            if liked:
                connection.execute(
                    """
                    INSERT INTO track_likes (track_id)
                    VALUES (?)
                    ON CONFLICT(track_id) DO UPDATE SET liked_at = CURRENT_TIMESTAMP
                    """,
                    (int(track_id),),
                )
            else:
                connection.execute("DELETE FROM track_likes WHERE track_id = ?", (int(track_id),))
            embedding_keys = _embedding_keys_for_track(connection, int(track_id))
        self._invalidate_embedding_cache_keys(embedding_keys)
        self._invalidate_sonara_feature_cache()
        return self.get_track(track_id)

    def list_track_paths(self) -> list[tuple[int, str]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, path
                FROM tracks
                ORDER BY COALESCE(artist, ''), COALESCE(title, ''), path
                """
            ).fetchall()
        return [(int(row["id"]), str(row["path"])) for row in rows]

    def get_track_file_stat_by_path(self, path: str | Path) -> tuple[int, int, float] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, size, mtime FROM tracks WHERE path = ?",
                (normalize_path(path),),
            ).fetchone()
        if row is None:
            return None
        return int(row["id"]), int(row["size"]), float(row["mtime"])

    def refresh_track_file_metadata(
        self,
        track_id: int,
        *,
        size: int,
        mtime: float,
        metadata: dict[str, object],
        replace_metadata_keys: Iterable[str],
    ) -> None:
        with self._write_lock, self.connect() as connection:
            existing_metadata = self._metadata_for_track_update(connection, track_id)
            for key in replace_metadata_keys:
                existing_metadata.pop(key, None)
            existing_metadata.update(metadata)
            has_sonara = bool(existing_metadata.get("sonara_features"))
            bpm = optional_float(metadata.get("bpm"))
            musical_key = string_or_none(metadata.get("key")) or string_or_none(metadata.get("initialkey"))
            duration = optional_float(metadata.get("duration"))
            connection.execute(
                """
                UPDATE tracks
                SET size = ?,
                    mtime = ?,
                    artist = ?,
                    title = ?,
                    album = ?,
                    bpm = CASE WHEN ? THEN bpm ELSE ? END,
                    musical_key = CASE WHEN ? THEN musical_key ELSE ? END,
                    duration = CASE WHEN ? THEN duration ELSE ? END,
                    metadata_json = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    int(size),
                    float(mtime),
                    string_or_none(metadata.get("artist")),
                    string_or_none(metadata.get("title")) or Path(string_or_none(existing_metadata.get("path")) or "").stem,
                    string_or_none(metadata.get("album")),
                    1 if has_sonara else 0,
                    bpm,
                    1 if has_sonara else 0,
                    musical_key,
                    1 if has_sonara else 0,
                    duration,
                    metadata_to_json(existing_metadata),
                    track_id,
                ),
            )
            upsert_track_search_fts(connection, track_id)
            embedding_keys = _embedding_keys_for_track(connection, track_id)
        self._invalidate_embedding_cache_keys(embedding_keys)
        self._invalidate_sonara_feature_cache()

    def _metadata_for_track_update(self, connection: sqlite3.Connection, track_id: int) -> dict[str, object]:
        row = connection.execute("SELECT metadata_json FROM tracks WHERE id = ?", (track_id,)).fetchone()
        if row is None:
            raise KeyError(f"Unknown track id: {track_id}")
        return metadata_from_json(row["metadata_json"])

    def relocate_library(self, old_root: str | Path, new_root: str | Path, *, apply: bool = False) -> dict[str, object]:
        old_root_text = _normalize_root(old_root)
        new_root_text = _normalize_root(new_root)
        if old_root_text == new_root_text:
            raise ValueError("Old and new library roots must be different")

        embedding_keys_to_invalidate: set[str] = set()
        with self._write_lock if apply else _nullcontext(), self.connect() as connection:
            rows = connection.execute("SELECT id, path FROM tracks ORDER BY id").fetchall()
            existing_by_path = {str(row["path"]).casefold(): int(row["id"]) for row in rows}
            changes: list[dict[str, object]] = []
            conflicts: list[dict[str, object]] = []
            missing_files: list[dict[str, object]] = []
            planned_paths: set[str] = set()

            for row in rows:
                track_id = int(row["id"])
                old_path = str(row["path"])
                new_path = _relocate_path(old_path, old_root_text, new_root_text)
                if new_path is None:
                    continue

                new_path_key = new_path.casefold()
                existing_track_id = existing_by_path.get(new_path_key)
                if existing_track_id is not None and existing_track_id != track_id:
                    conflicts.append(
                        {
                            "track_id": track_id,
                            "old_path": old_path,
                            "new_path": new_path,
                            "existing_track_id": existing_track_id,
                        }
                    )
                if new_path_key in planned_paths:
                    conflicts.append(
                        {
                            "track_id": track_id,
                            "old_path": old_path,
                            "new_path": new_path,
                            "existing_track_id": None,
                        }
                    )
                planned_paths.add(new_path_key)

                if not Path(new_path).is_file():
                    missing_files.append({"track_id": track_id, "path": new_path})
                changes.append({"track_id": track_id, "old_path": old_path, "new_path": new_path})

            if apply:
                if conflicts:
                    raise ValueError("Cannot relocate library because one or more target paths conflict")
                if missing_files:
                    raise ValueError("Cannot relocate library because one or more target files are missing")
                for change in changes:
                    embedding_keys_to_invalidate.update(_embedding_keys_for_track(connection, int(change["track_id"])))
                    connection.execute(
                        "UPDATE tracks SET path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (change["new_path"], change["track_id"]),
                    )
                    upsert_track_search_fts(connection, int(change["track_id"]))
        if apply and changes:
            self._invalidate_embedding_cache_keys(embedding_keys_to_invalidate)
            self._invalidate_sonara_feature_cache()

        return {
            "old_root": old_root_text,
            "new_root": new_root_text,
            "dry_run": not apply,
            "tracks_matched": len(changes),
            "tracks_updated": len(changes) if apply else 0,
            "missing_files": missing_files,
            "conflicts": conflicts,
            "changes": changes,
        }

    def rebuild_track_search_index(self) -> int:
        with self._write_lock, self.connect() as connection:
            return rebuild_track_search_fts(connection)

    @staticmethod
    def _row_to_track(row: sqlite3.Row, *, include_metadata: bool = True) -> Track:
        row_keys = set(row.keys())
        metadata = metadata_from_json(row["metadata_json"]) if include_metadata and "metadata_json" in row_keys else {}
        genres, genre_scores = genres_from_metadata(metadata) if include_metadata else (None, None)
        analyses = analyses_from_row(row, metadata)
        classifier_scores = _classifier_scores_from_row(row) if "classifier_scores_json" in row_keys else None
        return Track(
            id=int(row["id"]),
            path=str(row["path"]),
            size=int(row["size"]),
            mtime=float(row["mtime"]),
            artist=row["artist"],
            title=row["title"],
            album=row["album"],
            bpm=row["bpm"],
            musical_key=row["musical_key"],
            energy=row["energy"],
            duration=row["duration"],
            liked=bool(row["liked"]) if "liked" in row_keys else False,
            metadata=metadata if include_metadata else None,
            genres=genres,
            genre_scores=genre_scores,
            classifier_scores=classifier_scores,
            analyses=analyses,
            embedding_model=row["embedding_model"] if "embedding_model" in row.keys() else None,
            embedding_dim=row["embedding_dim"] if "embedding_dim" in row.keys() else None,
        )
