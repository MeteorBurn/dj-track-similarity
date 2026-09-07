from contextlib import closing
from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.connection import connect_database_read_only
from dj_track_similarity.db.text_feedback import TextFeedbackConflict, TextFeedbackSchemaError
from dj_track_similarity.text_search_models import QueryContext, query_context_key


def _library(path: Path, *, legacy: bool = False) -> LibraryDatabase:
    database = LibraryDatabase(path)
    with closing(database.connect()) as connection, connection:
        connection.execute(
            "INSERT INTO tracks(track_uuid,file_path,file_size_bytes,file_modified_ns,"
            "last_scanned_at,created_at,updated_at) VALUES ('track-a','synthetic.wav',1,1,'t','t','t')"
        )
        # A synthetic stored payload: migration must preserve arbitrary BLOB
        # bytes without decoding, rewriting, or running analysis.
        connection.execute(
            "INSERT INTO clap_embeddings VALUES (1, 'track-a', 1, 'none', ?, 't')",
            (b'\x00\x00\x80\x3f',),
        )
        if legacy:
            connection.execute("DROP TABLE text_search_feedback")
    return database


def _context(database: LibraryDatabase) -> dict:
    return QueryContext(
        catalog_uuid=database.catalog_uuid, analysis_family="clap",
        analysis_output_identity={
            "model_name": "fixture", "model_version": "1", "checkpoint_id": "fixture",
            "preprocessing": "fixture",
        },
        positive_queries=("dark",), negative_queries=(), negative_weight=0,
        selected_preset_keys=("mood/dark",), input_mode="preset",
        scope={"kind": "all_eligible_tracks", "filters": {}},
    ).to_dict()


def _run(context: dict) -> dict:
    return {"query_key": query_context_key(context), "run_id": "run-a",
            "analysis_family": "clap", "executed_at": "2026-09-07T00:00:00Z", "rank": 1}


def test_exact_context_atomic_revisions_and_withdrawal(tmp_path: Path, monkeypatch) -> None:
    database = _library(tmp_path / "new.sqlite")
    assert database.text_feedback_capability() == "ready"
    with closing(database.connect()) as connection, connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE 'text_%feedback%'"
        )}
        assert tables == {"text_search_feedback"}
        assert connection.execute(
            "SELECT 1 FROM sqlite_schema WHERE name='text_feedback_contexts'"
        ).fetchone() is None
        connection.execute(
            "INSERT INTO tracks(track_uuid,file_path,file_size_bytes,file_modified_ns,"
            "last_scanned_at,created_at,updated_at) VALUES ('track-b','other.wav',1,1,'t','t','t')"
        )
    context = _context(database)
    run = _run(context)
    key = run["query_key"]
    foreign = dict(context, catalog_uuid="foreign")
    with pytest.raises(ValueError, match="another catalog"):
        database.record_text_query_feedback(foreign, _run(foreign), "track-a", 1, 0)
    with pytest.raises(KeyError):
        database.record_text_query_feedback(context, run, "missing", 1, 0)
    with closing(database.connect()) as connection:
        assert connection.execute("SELECT count(*) FROM text_search_feedback").fetchone()[0] == 0
    first = database.record_text_query_feedback(context, run, "track-a", 1, 0)
    assert first["revision"] == 1
    assert database.record_text_query_feedback(context, run, "track-a", 1, 0) == first
    positive = database.list_text_query_feedback_tracks(key)
    assert positive["relevant"] == [1]
    with pytest.raises(TextFeedbackConflict) as conflict:
        database.record_text_query_feedback(context, run, "track-a", -1, 0)
    assert conflict.value.current == first
    withdrawal = database.record_text_query_feedback(context, run, "track-a", 0, 1)
    assert withdrawal["revision"] == 2
    withdrawn = database.list_text_query_feedback_tracks(key)
    assert withdrawn["relevant"] == withdrawn["irrelevant"] == []
    assert positive["history_revision"] != withdrawn["history_revision"]
    assert database.read_text_query_feedback(key, ["track-a"]) == {"track-a": {"verdict": 0, "revision": 2}}
    # Force a hash collision at the shared identity boundary: stored payload
    # equality must independently prevent replacement of immutable context.
    monkeypatch.setattr("dj_track_similarity.text_search_models.query_context_key", lambda _: key)
    changed = dict(context, selected_preset_keys=["mood/other"])
    with pytest.raises(ValueError, match="immutable context"):
        database.record_text_query_feedback(changed, run, "track-a", -1, 2)
    with pytest.raises(ValueError, match="immutable context"):
        database.record_text_query_feedback(changed, run, "track-b", 1, 0)
    database.record_text_query_feedback(context, run, "track-b", -1, 0)
    with closing(connect_database_read_only(database.path)) as connection:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        rows = connection.execute(
            "SELECT context_json,verdict,revision FROM text_search_feedback ORDER BY track_id"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0][0] == rows[1][0]
        assert rows[0][1:] == (0, 2)
        assert rows[1][1:] == (-1, 1)
    with closing(database.connect()) as connection, connection:
        connection.execute("DELETE FROM tracks WHERE track_uuid='track-b'")
        assert connection.execute("SELECT count(*) FROM text_search_feedback").fetchone()[0] == 1
        connection.execute("DROP TABLE text_search_feedback")
    assert LibraryDatabase(database.path).text_feedback_capability() == "absent"
    with pytest.raises(TextFeedbackSchemaError):
        database.record_text_query_feedback(context, run, "track-a", 1, 0)
    assert database.text_feedback_capability() == "absent"
    with closing(database.connect()) as connection, connection:
        connection.execute("CREATE TABLE text_search_feedback (query_key TEXT)")
    assert LibraryDatabase(database.path).text_feedback_capability() == "incompatible"
    with pytest.raises(TextFeedbackSchemaError):
        database.record_text_query_feedback(context, run, "track-a", 1, 0)
    assert database.text_feedback_capability() == "incompatible"
