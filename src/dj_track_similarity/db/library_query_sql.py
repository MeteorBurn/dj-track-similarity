"""Library filtering and ordering SQL."""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping, Sequence

from .library_read_models import (
    _ReadContext,
)


_HUMAN_FTS_COLUMNS = (
    "file_path",
    "title",
    "artist",
    "album",
    "comment",
    "label",
    "country",
    "year",
    "track_number",
    "maest_genres",
)


def _fts_query(raw: str) -> str:
    terms = [term for term in raw.split() if term]
    if not terms:
        return ""
    quoted = " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"' for term in terms)
    columns = " ".join(_HUMAN_FTS_COLUMNS)
    return f"{{{columns}}} : ({quoted})"


def _genre_fts_query(raw: str) -> str:
    """Reach MAEST genres through the index rather than by scanning every row.

    Substring matching against ``maest_genres.genres_json`` costs a JSON parse
    per track: 78 ms against 14 ms on a 20k library, growing linearly. The
    index answers the same question in microseconds. Terms are prefix matched
    so partial typing still narrows the list, which is what LIKE mode promises;
    it stops short of matching inside a token.
    """

    terms = [term for term in raw.split() if term]
    if not terms:
        return ""
    quoted = " AND ".join(f'"{term.replace(chr(34), chr(34) * 2)}"*' for term in terms)
    return f"{{maest_genres}} : ({quoted})"


def _like_pattern(raw: str) -> str:
    escaped = raw.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _base_select_fields() -> str:
    return """
        t.track_id,
        t.track_uuid,
        t.file_path,
        t.file_size_bytes,
        t.file_modified_ns,
        t.audio_format,
        t.sample_rate_hz,
        t.channel_count,
        t.bit_rate_bps,
        t.bit_depth,
        t.audio_duration_seconds,
        t.last_scanned_at,
        t.missing_since,
        ft.title,
        ft.artist,
        ft.album,
        ft.tag_bpm,
        ft.tag_key,
        ft.comment,
        ft.year,
        ft.label,
        ft.country,
        ft.track_number,
        ft.genres_json,
        ft.tags_read_at,
        EXISTS(
            SELECT 1 FROM likes liked
            WHERE liked.track_id = t.track_id
        ) AS liked
    """


def _filter_sql(
    *,
    context: _ReadContext,
    query: str,
    search_mode: str,
    liked_only: bool,
    syncopated_only: bool,
    classifier_filters: Sequence[tuple[str, float]],
    primary_classifier: tuple[str, float] | None,
    include_missing: bool,
) -> tuple[str, list[object]]:
    conditions: list[str] = []
    params: list[object] = []
    if not include_missing:
        conditions.append("t.missing_since IS NULL")

    cleaned_query = query.strip()
    if cleaned_query:
        if search_mode == "fts":
            conditions.append(
                """
                t.track_id IN (
                    SELECT rowid
                    FROM track_search_fts
                    WHERE track_search_fts MATCH ?
                )
                """
            )
            params.append(_fts_query(cleaned_query))
        elif search_mode == "like":
            pattern = _like_pattern(cleaned_query)
            conditions.append(
                """
                (
                    t.file_path LIKE ? ESCAPE '\\'
                    OR ft.title LIKE ? ESCAPE '\\'
                    OR ft.artist LIKE ? ESCAPE '\\'
                    OR ft.album LIKE ? ESCAPE '\\'
                    OR ft.comment LIKE ? ESCAPE '\\'
                    OR ft.label LIKE ? ESCAPE '\\'
                    OR ft.country LIKE ? ESCAPE '\\'
                    OR CAST(ft.year AS TEXT) LIKE ? ESCAPE '\\'
                    OR ft.track_number LIKE ? ESCAPE '\\'
                    OR t.track_id IN (
                        SELECT rowid
                        FROM track_search_fts
                        WHERE track_search_fts MATCH ?
                    )
                )
                """
            )
            params.extend([pattern] * 9)
            params.append(_genre_fts_query(cleaned_query))
        else:
            raise ValueError("search_mode must be 'like' or 'fts'")

    if liked_only:
        conditions.append("EXISTS(SELECT 1 FROM likes l WHERE l.track_id = t.track_id)")

    if syncopated_only:
        output = context.outputs.get(("maest", "analysis"))
        if output is None:
            conditions.append("0")
        else:
            conditions.append(
                """
                EXISTS(
                    SELECT 1
                    FROM maest_genres ms
                    WHERE ms.track_id = t.track_id
                      AND ms.syncopated_rhythm = 1
                )
                """
            )

    if primary_classifier is not None:
        classifier_key, score = primary_classifier
        conditions.append(
            """
            primary_cs.classifier_key = ?
            AND primary_cs.score >= ?
            """
        )
        params.extend([classifier_key, score])

    for classifier_key, score in classifier_filters:
        if primary_classifier is not None and classifier_key == primary_classifier[0]:
            continue
        conditions.append(
            """
            EXISTS(
                SELECT 1
                FROM classifier_scores cs
                WHERE cs.track_id = t.track_id
                  AND cs.classifier_key = ?
                  AND cs.score >= ?
            )
            """
        )
        params.extend([classifier_key, score])

    return (
        "" if not conditions else "WHERE " + " AND ".join(conditions),
        params,
    )


def _validated_classifier_filters(
    classifier_min_scores: Mapping[str, float],
) -> tuple[tuple[str, float], ...]:
    filters: list[tuple[str, float]] = []
    for classifier_key, threshold in sorted(classifier_min_scores.items()):
        if not classifier_key.strip():
            raise ValueError("classifier keys must be non-empty")
        score = float(threshold)
        if not math.isfinite(score) or not 0.0 <= score <= 1.0:
            raise ValueError("classifier score thresholds must be between 0 and 1")
        filters.append((classifier_key, score))
    return tuple(filters)


def _base_from_sql(*, has_primary_classifier: bool) -> str:
    if has_primary_classifier:
        return """
            FROM classifier_scores primary_cs
                 INDEXED BY idx_classifier_scores_lookup
            JOIN tracks t ON t.track_id = primary_cs.track_id
            LEFT JOIN tags ft ON ft.track_id = t.track_id
        """
    return """
        FROM tracks t
        LEFT JOIN tags ft ON ft.track_id = t.track_id
    """


def _order_sql(
    *,
    has_primary_classifier: bool,
) -> str:
    order = [
        "liked DESC",
    ]
    if has_primary_classifier:
        order.append("primary_cs.score DESC")
    order.extend(
        [
            "COALESCE(ft.artist, '') COLLATE NOCASE",
            "COALESCE(ft.title, '') COLLATE NOCASE",
            "t.file_path COLLATE NOCASE",
            "t.track_id",
        ]
    )
    return "ORDER BY " + ", ".join(order)


def _query_base_rows(
    connection: sqlite3.Connection,
    *,
    context: _ReadContext,
    query: str,
    search_mode: str,
    liked_only: bool,
    syncopated_only: bool,
    classifier_min_scores: Mapping[str, float],
    include_missing: bool,
    limit: int | None,
    offset: int,
) -> tuple[list[sqlite3.Row], int]:
    classifier_filters = _validated_classifier_filters(classifier_min_scores)
    primary_classifier = (
        None if not classifier_filters else classifier_filters[0]
    )
    where_sql, where_params = _filter_sql(
        context=context,
        query=query,
        search_mode=search_mode,
        liked_only=liked_only,
        syncopated_only=syncopated_only,
        classifier_filters=classifier_filters,
        primary_classifier=primary_classifier,
        include_missing=include_missing,
    )
    from_sql = _base_from_sql(
        has_primary_classifier=primary_classifier is not None,
    )
    total = int(
        connection.execute(
            f"""
            SELECT COUNT(*)
            {from_sql}
            {where_sql}
            """,
            where_params,
        ).fetchone()[0]
    )
    order_sql = _order_sql(
        has_primary_classifier=primary_classifier is not None,
    )
    pagination_sql = ""
    pagination_params: list[object] = []
    if limit is not None:
        pagination_sql = "LIMIT ? OFFSET ?"
        pagination_params.extend([int(limit), int(offset)])
    rows = connection.execute(
        f"""
        SELECT {_base_select_fields()}
        {from_sql}
        {where_sql}
        {order_sql}
        {pagination_sql}
        """,
        [*where_params, *pagination_params],
    ).fetchall()
    return rows, total
