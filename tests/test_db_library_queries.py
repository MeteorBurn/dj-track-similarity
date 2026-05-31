from __future__ import annotations

import pytest

from dj_track_similarity.db_library_queries import build_track_filter_sql, track_order_sql


def test_build_track_filter_sql_combines_search_preset_liked_and_classifier_filters() -> None:
    where_sql, params = build_track_filter_sql(
        query="Breaks",
        preset="syncopated",
        liked_only=True,
        classifier_min_scores={"live": 0.75},
    )

    assert where_sql.startswith("WHERE ")
    assert "LOWER(COALESCE(t.artist, '')) LIKE ?" in where_sql
    assert "json_extract(t.metadata_json, '$.maest_syncopated_rhythm') = 1" in where_sql
    assert "track_likes" in where_sql
    assert "track_classifier_scores" in where_sql
    assert params == ["%breaks%", "%breaks%", "%breaks%", "%breaks%", "%breaks%", "live", 0.75]


def test_build_track_filter_sql_rejects_unknown_library_preset() -> None:
    with pytest.raises(ValueError, match="Unknown library preset"):
        build_track_filter_sql(query="", preset="legacy", liked_only=False)


def test_track_order_sql_prefers_classifier_score_when_thresholds_are_active() -> None:
    assert track_order_sql(classifier_min_scores={}) == "COALESCE(t.artist, ''), COALESCE(t.title, ''), t.path"
    assert track_order_sql(classifier_min_scores={"break'energy": 0.5}).startswith(
        "(SELECT cs.score FROM track_classifier_scores cs WHERE cs.track_id = t.id AND cs.classifier = 'break''energy') DESC"
    )
