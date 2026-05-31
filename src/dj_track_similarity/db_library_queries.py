from __future__ import annotations


def build_track_filter_sql(
    *,
    query: str,
    preset: str,
    liked_only: bool = False,
    classifier_min_scores: dict[str, float] | None = None,
) -> tuple[str, list[object]]:
    where_parts: list[str] = []
    params: list[object] = []
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


def track_order_sql(*, classifier_min_scores: dict[str, float] | None = None) -> str:
    classifiers = list((classifier_min_scores or {}).keys())
    if not classifiers:
        return "COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path"
    classifier = classifiers[0].replace("'", "''")
    return (
        "(SELECT cs.score FROM track_classifier_scores cs "
        f"WHERE cs.track_id = t.id AND cs.classifier = '{classifier}') DESC, "
        "COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path"
    )
