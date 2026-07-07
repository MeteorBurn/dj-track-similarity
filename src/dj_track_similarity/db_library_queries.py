from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .db_search_fts import fts_match_query, normalize_search_mode


SqlParam = str | float


@dataclass(frozen=True, slots=True)
class TrackListingRequest:
    query: str = ""
    preset: str = "all"
    liked_only: bool = False
    classifier_min_scores: Mapping[str, float] | None = None
    search_mode: str = "like"


@dataclass(frozen=True, slots=True)
class TrackListingQuery:
    where_sql: str
    params: tuple[SqlParam, ...]
    primary_classifier: tuple[str, float] | None
    fts_join_sql: str
    from_sql: str
    order_sql: str


def split_primary_classifier_filter(
    classifier_min_scores: dict[str, float] | None,
) -> tuple[tuple[str, float] | None, dict[str, float]]:
    items = list((classifier_min_scores or {}).items())
    if not items:
        return None, {}
    classifier, threshold = items[0]
    return (str(classifier), float(threshold)), {str(key): float(value) for key, value in items[1:]}


def combine_where_condition(condition_sql: str, where_sql: str) -> str:
    if not where_sql:
        return f"WHERE {condition_sql}"
    return f"WHERE {condition_sql} AND {where_sql.removeprefix('WHERE ').strip()}"


def build_track_listing_query(request: TrackListingRequest) -> TrackListingQuery:
    mode = normalize_search_mode(request.search_mode)
    use_fts = mode == "fts" and bool(request.query.strip())
    fts_query = fts_match_query(request.query) if use_fts else ""
    thresholds = dict(request.classifier_min_scores or {})
    primary_classifier, remaining_thresholds = split_primary_classifier_filter(thresholds)
    where_sql, params = build_track_filter_sql(
        query="" if use_fts else request.query,
        preset=request.preset,
        liked_only=request.liked_only,
        classifier_min_scores=remaining_thresholds if primary_classifier else thresholds,
    )
    if use_fts:
        condition = "track_search_fts MATCH ?" if fts_query else "0 = 1"
        where_sql = combine_where_condition(condition, where_sql)
        if fts_query:
            params = [fts_query, *params]
    return TrackListingQuery(
        where_sql=where_sql,
        params=tuple(params),
        primary_classifier=primary_classifier,
        fts_join_sql="JOIN track_search_fts fts ON fts.track_id = t.id" if use_fts and fts_query else "",
        from_sql="track_search_fts fts JOIN tracks t ON t.id = fts.track_id" if use_fts and fts_query else "tracks t",
        order_sql=track_order_sql(liked_only=request.liked_only, classifier_min_scores=thresholds),
    )


def build_track_filter_sql(
    *,
    query: str,
    preset: str,
    liked_only: bool = False,
    classifier_min_scores: dict[str, float] | None = None,
) -> tuple[str, list[SqlParam]]:
    where_parts: list[str] = []
    params: list[SqlParam] = []
    needle = query.strip().lower()
    if needle:
        like = f"%{needle}%"
        searchable_columns = (
            "LOWER(COALESCE(t.artist, ''))",
            "LOWER(COALESCE(t.title, ''))",
            "LOWER(COALESCE(t.album, ''))",
            "LOWER(t.path)",
            "LOWER(t.metadata_json)",
        )
        where_parts.append("(" + " OR ".join(f"{column} LIKE ?" for column in searchable_columns) + ")")
        params.extend([like] * len(searchable_columns))
    if preset == "syncopated":
        where_parts.append("json_extract(t.metadata_json, '$.maest_syncopated_rhythm') = 1")
    elif preset != "all":
        raise ValueError(f"Unknown library preset: {preset}")
    if liked_only:
        where_parts.append("EXISTS (SELECT 1 FROM track_likes tl WHERE tl.track_id = t.id)")
    for classifier, threshold in (classifier_min_scores or {}).items():
        where_parts.append(
            """
            EXISTS (
                SELECT 1
                FROM track_classifier_scores cs
                WHERE cs.track_id = t.id
                  AND cs.classifier = ?
                  AND cs.score >= ?
            )
            """
        )
        params.extend([classifier, float(threshold)])
    where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
    return where_sql, params


def track_order_sql(*, liked_only: bool = False, classifier_min_scores: dict[str, float] | None = None) -> str:
    fallback_order = "COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path"
    liked_order = ""
    if liked_only:
        liked_order = "(SELECT tl.liked_at FROM track_likes tl WHERE tl.track_id = t.id) ASC, "
    classifiers = list((classifier_min_scores or {}).keys())
    if not classifiers:
        return liked_order + fallback_order
    classifier = classifiers[0].replace("'", "''")
    classifier_order = (
        "(SELECT cs.score FROM track_classifier_scores cs "
        f"WHERE cs.track_id = t.id AND cs.classifier = '{classifier}') DESC, "
    )
    return liked_order + classifier_order + fallback_order
