"""Library queries over one validated SQLite library."""

from __future__ import annotations


import sqlite3

import threading


from collections.abc import Iterator, Mapping, Sequence

from contextlib import closing, contextmanager


from pathlib import Path


from .tracks import utc_now_text

from ..library_models import (
    EmbeddingSummary,
    ExportTrackRow,
    FileTechnical,
    GenreTagCandidate,
    LibrarySummary,
    SonaraCore,
    TrackDetail,
    TrackPage,
    TrackSummary,
)

from ..maest_analysis_validation import (
    validate_maest_analysis_row,
)

from ..track_models import TrackIdentity


from .library_read_models import (
    _EMBEDDING_TABLES,
    _ReadContext,
    _assemble_summaries,
    _coverage_and_classifiers,
    _file_tags,
    _json_ids,
    _maest_analysis,
    _optional_float,
    _optional_int,
    _optional_text,
    _parse_maest_genres,
    _read_context,
    _sonara_core,
    _track_summary,
)
from .library_query_sql import (
    _base_select_fields,
    _query_base_rows,
)


class LibraryQueryRepository:
    """Read-model mixin for the single library database."""

    catalog_uuid: str
    _write_lock: threading.RLock

    def connect(self) -> sqlite3.Connection:
        raise NotImplementedError

    def classifier_score_counts(
        self,
        classifier_keys: Sequence[str],
    ) -> dict[str, int]:
        counts = dict.fromkeys(classifier_keys, 0)
        if not counts:
            return counts
        placeholders = ", ".join("?" for _ in counts)
        with closing(self.connect()) as core_connection:
            rows = core_connection.execute(
                f"""
                SELECT classifier_key, COUNT(*) AS score_count
                FROM classifier_scores AS cs
                WHERE classifier_key IN ({placeholders})
                GROUP BY classifier_key
                """,
                tuple(counts),
            ).fetchall()
        for row in rows:
            classifier_key = str(row["classifier_key"])
            if classifier_key in counts:
                counts[classifier_key] = int(row["score_count"])
        return counts

    @contextmanager
    def _open_library(
        self,
        *,
        write: bool = False,
    ) -> Iterator[tuple[sqlite3.Connection, _ReadContext]]:
        with closing(self.connect()) as connection:
            # Keep context, page counts, rows and hydration on one snapshot.
            # Writers reserve their lock before reading to avoid an upgrade.
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            context = _read_context(
                connection,
                expected_catalog_uuid=self.catalog_uuid,
            )
            yield connection, context

    def list_track_summaries(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]:
        with self._open_library() as (connection, context):
            rows, _total = _query_base_rows(
                connection,
                context=context,
                query="",
                search_mode="like",
                liked_only=False,
                syncopated_only=False,
                classifier_min_scores={},
                include_missing=include_missing,
                limit=None,
                offset=0,
            )
            return _assemble_summaries(
                connection,
                context=context,
                rows=rows,
            )

    def get_track_summaries(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]:
        """Hydrate a strict selection in caller order.

        Unknown or unavailable IDs fail closed. Repeated IDs are preserved so
        callers can align the returned summaries with an existing ranked list.
        """

        requested: list[int] = []
        for value in track_ids:
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("track_ids must contain only positive integers")
            requested.append(value)
        if not requested:
            return ()

        with self._open_library() as (connection, context):
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            rows = connection.execute(
                f"""
                SELECT {_base_select_fields()}
                FROM tracks t
                LEFT JOIN tags ft ON ft.track_id = t.track_id
                WHERE t.track_id IN (
                    SELECT CAST(value AS INTEGER)
                    FROM json_each(?)
                )
                {missing_sql}
                """,
                (_json_ids(requested),),
            ).fetchall()
            summaries = _assemble_summaries(
                connection,
                context=context,
                rows=rows,
            )
        by_id = {summary.track_id: summary for summary in summaries}
        unavailable = sorted(set(requested).difference(by_id))
        if unavailable:
            raise KeyError(
                "Unknown current track ids: "
                + ", ".join(str(track_id) for track_id in unavailable)
            )
        return tuple(by_id[track_id] for track_id in requested)

    def paginate_track_summaries(
        self,
        *,
        query: str = "",
        search_mode: str = "like",
        liked_only: bool = False,
        syncopated_only: bool = False,
        classifier_min_scores: Mapping[str, float] | None = None,
        include_missing: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> TrackPage:
        bounded_limit = max(1, min(500, int(limit)))
        bounded_offset = max(0, int(offset))
        scores = dict(classifier_min_scores or {})
        with self._open_library() as (connection, context):
            rows, total = _query_base_rows(
                connection,
                context=context,
                query=query,
                search_mode=search_mode,
                liked_only=liked_only,
                syncopated_only=syncopated_only,
                classifier_min_scores=scores,
                include_missing=include_missing,
                limit=bounded_limit,
                offset=bounded_offset,
            )
            items = _assemble_summaries(
                connection,
                context=context,
                rows=rows,
            )
        return TrackPage(
            items=items,
            total=total,
            limit=bounded_limit,
            offset=bounded_offset,
        )

    def filter_track_summaries(
        self,
        *,
        query: str = "",
        search_mode: str = "like",
        liked_only: bool = False,
        syncopated_only: bool = False,
        classifier_min_scores: Mapping[str, float] | None = None,
        include_missing: bool = False,
    ) -> tuple[TrackSummary, ...]:
        scores = dict(classifier_min_scores or {})
        with self._open_library() as (connection, context):
            rows, _total = _query_base_rows(
                connection,
                context=context,
                query=query,
                search_mode=search_mode,
                liked_only=liked_only,
                syncopated_only=syncopated_only,
                classifier_min_scores=scores,
                include_missing=include_missing,
                limit=None,
                offset=0,
            )
            return _assemble_summaries(
                connection,
                context=context,
                rows=rows,
            )

    def get_track_detail(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> TrackDetail:
        with self._open_library() as (connection, context):
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            row = connection.execute(
                f"""
                SELECT {_base_select_fields()}
                FROM tracks t
                LEFT JOIN tags ft ON ft.track_id = t.track_id
                WHERE t.track_id = ?
                {missing_sql}
                """,
                (int(track_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown current track id: {track_id}")
            coverage, classifiers, embedding_rows = _coverage_and_classifiers(
                connection,
                context=context,
                rows=[row],
            )
            numeric_id = int(row["track_id"])
            classifier_details = classifiers.get(numeric_id, ())
            summary = _track_summary(
                row,
                catalog_uuid=context.catalog_uuid,
                coverage=coverage[numeric_id],
                classifiers=classifier_details,
            )
            sonara = _sonara_core(
                connection,
                track_id=numeric_id,
                output=context.outputs.get(("sonara", "core")),
            )
            maest = _maest_analysis(
                connection,
                track_id=numeric_id,
                output=context.outputs.get(("maest", "analysis")),
            )
            embeddings = tuple(
                EmbeddingSummary(
                    analysis_family=family,
                    dim=int(embedding_row["dim"]),
                    normalization=str(embedding_row["normalization"]),
                    analyzed_at=str(embedding_row["analyzed_at"]),
                )
                for family, output_kind, _table in _EMBEDDING_TABLES
                if context.outputs.get((family, output_kind))
                is not None
                and (
                    embedding_row := embedding_rows[(family, output_kind)].get(numeric_id)
                )
                is not None
            )
            return TrackDetail(
                **summary.__dict__,
                file=FileTechnical(
                    file_size_bytes=int(row["file_size_bytes"]),
                    file_modified_ns=int(row["file_modified_ns"]),
                    audio_format=_optional_text(row["audio_format"]),
                    sample_rate_hz=_optional_int(row["sample_rate_hz"]),
                    channel_count=_optional_int(row["channel_count"]),
                    bit_rate_bps=_optional_int(row["bit_rate_bps"]),
                    bit_depth=_optional_int(row["bit_depth"]),
                    audio_duration_seconds=_optional_float(
                        row["audio_duration_seconds"]
                    ),
                    last_scanned_at=str(row["last_scanned_at"]),
                    missing_since=_optional_text(row["missing_since"]),
                ),
                file_tags=_file_tags(row),
                sonara_core=sonara,
                maest=maest,
                embeddings=embeddings,
                classifier_scores_detail=classifier_details,
            )

    def get_media_path(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> Path:
        with self._open_library() as (connection, _context):
            missing_sql = "" if include_missing else "AND missing_since IS NULL"
            row = connection.execute(
                f"""
                SELECT file_path
                FROM tracks
                WHERE track_id = ?
                {missing_sql}
                """,
                (int(track_id),),
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown current track id: {track_id}")
            return Path(str(row["file_path"]))

    def set_track_liked(
        self,
        *,
        expected: TrackIdentity,
        liked: bool,
    ) -> TrackSummary:
        if not isinstance(liked, bool):
            raise TypeError("liked must be a bool")
        if expected.catalog_uuid != self.catalog_uuid:
            raise RuntimeError("Track like candidate belongs to a different catalog")
        with (
            self._write_lock,
            self._open_library(write=True) as (connection, context),
        ):
            try:
                row = connection.execute(
                    """
                    SELECT track_id, track_uuid
                    FROM tracks
                    WHERE track_id = ?
                      AND track_uuid = ?
                      AND missing_since IS NULL
                    """,
                    (
                        expected.track_id,
                        expected.track_uuid,
                    ),
                ).fetchone()
                if row is None:
                    raise RuntimeError(
                        "Track identity changed before the liked-state mutation"
                    )
                if liked:
                    connection.execute(
                        """
                        INSERT INTO likes(track_id, liked_at)
                        VALUES (?, ?)
                        ON CONFLICT(track_id) DO UPDATE SET
                            liked_at = excluded.liked_at
                        """,
                        (expected.track_id, utc_now_text()),
                    )
                else:
                    connection.execute(
                        "DELETE FROM likes WHERE track_id = ?",
                        (expected.track_id,),
                    )
                base_row = connection.execute(
                    f"""
                    SELECT {_base_select_fields()}
                    FROM tracks t
                    LEFT JOIN tags ft ON ft.track_id = t.track_id
                    WHERE t.track_id = ?
                    """,
                    (expected.track_id,),
                ).fetchone()
                assert base_row is not None
                summary = _assemble_summaries(
                    connection,
                    context=context,
                    rows=[base_row],
                    )[0]
                connection.commit()
                return summary
            except BaseException:
                if connection.in_transaction:
                    connection.rollback()
                raise

    def list_liked_track_ids(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[int, ...]:
        with self._open_library() as (connection, _context):
            missing_sql = "" if include_missing else "WHERE t.missing_since IS NULL"
            rows = connection.execute(
                f"""
                SELECT l.track_id
                FROM likes l
                JOIN tracks t ON t.track_id = l.track_id
                {missing_sql}
                ORDER BY l.liked_at DESC, l.track_id
                """
            )
            return tuple(int(row[0]) for row in rows)

    def list_genre_tag_candidates(
        self,
        *,
        include_missing: bool = False,
    ) -> tuple[GenreTagCandidate, ...]:
        """Return present tracks with current, non-empty MAEST genre scores."""

        with self._open_library() as (connection, context):
            output = context.outputs.get(("maest", "analysis"))
            if output is None:
                return ()
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            rows = connection.execute(
                f"""
                SELECT
                    t.track_id,
                    t.track_uuid,
                    t.file_path,
                    t.file_size_bytes,
                    t.file_modified_ns,
                    ms.syncopated_rhythm,
                    ms.genres_json,
                    ms.analyzed_at
                FROM tracks t
                JOIN maest_genres ms
                 ON ms.track_id = t.track_id
                WHERE 1 = 1
                {missing_sql}
                ORDER BY t.file_path COLLATE NOCASE, t.track_id
                """
            ).fetchall()
            candidates: list[GenreTagCandidate] = []
            for row in rows:
                valid, _reason = validate_maest_analysis_row(
                    row,
                    expected_track_id=int(row["track_id"]),
                )
                if not valid:
                    continue
                genres = tuple(
                    genre.genre_name
                    for genre in _parse_maest_genres(row["genres_json"])
                )
                if not genres:
                    continue
                candidates.append(
                    GenreTagCandidate(
                        catalog_uuid=context.catalog_uuid,
                        track_id=int(row["track_id"]),
                        track_uuid=str(row["track_uuid"]),
                        file_path=str(row["file_path"]),
                        expected_file_size_bytes=int(row["file_size_bytes"]),
                        expected_file_modified_ns=int(row["file_modified_ns"]),
                        genres=genres,
                        maest_analyzed_at=str(row["analyzed_at"]),
                    )
                )
            return tuple(candidates)

    def export_track_rows(
        self,
        track_ids: Sequence[int],
        *,
        include_missing: bool = False,
    ) -> tuple[ExportTrackRow, ...]:
        requested = tuple(int(track_id) for track_id in track_ids)
        if not requested:
            return ()
        with self._open_library() as (connection, context):
            missing_sql = "" if include_missing else "AND t.missing_since IS NULL"
            rows = connection.execute(
                f"""
                SELECT
                    t.track_id,
                    t.track_uuid,
                    t.file_path,
                    ft.artist,
                    ft.title,
                    ft.album,
                    ft.tag_bpm,
                    ft.tag_key
                FROM tracks t
                LEFT JOIN tags ft ON ft.track_id = t.track_id
                WHERE t.track_id IN (
                    SELECT CAST(value AS INTEGER)
                    FROM json_each(?)
                )
                {missing_sql}
                """,
                (_json_ids(requested),),
            ).fetchall()
            by_id = {int(row["track_id"]): row for row in rows}
            unavailable_ids = sorted(set(requested).difference(by_id))
            if unavailable_ids:
                raise KeyError(
                    "Unknown current track ids: "
                    + ", ".join(str(track_id) for track_id in unavailable_ids)
                )
            sonara_by_id: dict[int, SonaraCore | None] = {
                track_id: _sonara_core(
                    connection,
                    track_id=track_id,
                    output=context.outputs.get(("sonara", "core")),
                )
                for track_id, row in by_id.items()
            }
            result: list[ExportTrackRow] = []
            for track_id in requested:
                row = by_id.get(track_id)
                if row is None:
                    continue
                sonara = sonara_by_id[track_id]
                result.append(
                    ExportTrackRow(
                        track_id=track_id,
                        file_path=str(row["file_path"]),
                        artist=_optional_text(row["artist"]),
                        title=_optional_text(row["title"]),
                        album=_optional_text(row["album"]),
                        tag_bpm=_optional_float(row["tag_bpm"]),
                        tag_key=_optional_text(row["tag_key"]),
                        sonara_bpm=(None if sonara is None else sonara.detected_bpm),
                        sonara_key=(
                            None
                            if sonara is None
                            else sonara.detected_key_camelot or sonara.detected_key_name
                        ),
                        sonara_energy=(None if sonara is None else sonara.energy_score),
                    )
                )
            return tuple(result)

    def claim_sonara_analysis_range(
        self,
        bpm_min: float,
        bpm_max: float,
    ) -> tuple[float, float]:
        """Return the library BPM range, claiming this pair when none is set.

        The range belongs to the library, not to any single analysed row: the
        first analysis job claims it, every later run reuses it, and only a
        SONARA reset or a full library clear releases it. Reading and claiming
        share one transaction so two jobs started against a fresh library
        cannot settle on different ranges.
        """

        with self._write_lock:
            with closing(self.connect()) as connection:
                try:
                    connection.execute("BEGIN IMMEDIATE")
                    claimed = _stored_sonara_range(connection)
                    if claimed is not None:
                        connection.rollback()
                        return claimed
                    connection.execute(
                        """
                        UPDATE library
                        SET sonara_bpm_min = ?,
                            sonara_bpm_max = ?,
                            updated_at = ?
                        WHERE singleton_id = 1
                        """,
                        (float(bpm_min), float(bpm_max), utc_now_text()),
                    )
                    connection.commit()
                except BaseException:
                    if connection.in_transaction:
                        connection.rollback()
                    raise
        return (float(bpm_min), float(bpm_max))

    def library_summary(self) -> LibrarySummary:
        def count_rows(connection: sqlite3.Connection, table: str) -> int:
            return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])

        with closing(self.connect()) as connection:
            return LibrarySummary(
                tracks=count_rows(connection, "tracks"),
                sonara=count_rows(connection, "sonara_features"),
                maest_analysis=count_rows(connection, "maest_genres"),
                maest_embedding=count_rows(connection, "maest_embeddings"),
                mert=count_rows(connection, "mert_embeddings"),
                muq=count_rows(connection, "muq_embeddings"),
                mulan=count_rows(connection, "mulan_embeddings"),
                clap=count_rows(connection, "clap_embeddings"),
                liked=count_rows(connection, "likes"),
                classifiers=count_rows(connection, "classifier_scores"),
                **_sonara_range_fields(connection),
            )


def _stored_sonara_range(
    connection: sqlite3.Connection,
) -> tuple[float, float] | None:
    """Read the claimed library BPM range, or None while none is claimed."""
    row = connection.execute(
        """
        SELECT sonara_bpm_min, sonara_bpm_max
        FROM library
        WHERE singleton_id = 1
        """
    ).fetchone()
    if row is None or row[0] is None or row[1] is None:
        return None
    return (float(row[0]), float(row[1]))


def _sonara_range_fields(
    connection: sqlite3.Connection,
) -> dict[str, float | None]:
    """Expose the claimed library range, or nulls while none is claimed."""
    claimed = _stored_sonara_range(connection)
    if claimed is None:
        return {"sonara_bpm_min": None, "sonara_bpm_max": None}
    return {"sonara_bpm_min": claimed[0], "sonara_bpm_max": claimed[1]}
