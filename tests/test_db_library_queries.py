from __future__ import annotations

from pathlib import Path

import pytest

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.track_models import FileTags, ScannedFile


def test_public_library_filter_combines_search_and_liked_state(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    selected = _add_track(
        database,
        tmp_path / "selected.wav",
        title="Breaks One",
        artist="Alpha",
    )
    _add_track(
        database,
        tmp_path / "unliked.wav",
        title="Breaks Two",
        artist="Beta",
    )
    _add_track(
        database,
        tmp_path / "other.wav",
        title="House",
        artist="Gamma",
    )
    database.set_track_liked(expected=selected, liked=True)

    rows = database.filter_track_summaries(
        query="Breaks",
        liked_only=True,
    )

    assert [row.track_id for row in rows] == [selected.track_id]
    assert rows[0].liked


def test_public_library_filter_rejects_unknown_search_mode(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")

    with pytest.raises(ValueError, match="search_mode"):
        database.filter_track_summaries(
            query="Breaks",
            search_mode="legacy",
        )


def test_public_library_order_is_deterministic_by_artist_title_and_path(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    _add_track(
        database,
        tmp_path / "z.wav",
        title="Second",
        artist="Beta",
    )
    _add_track(
        database,
        tmp_path / "b.wav",
        title="Second",
        artist="Alpha",
    )
    _add_track(
        database,
        tmp_path / "a.wav",
        title="First",
        artist="Alpha",
    )

    rows = database.list_track_summaries()

    assert [
        (row.artist, row.title, Path(row.file_path).name)
        for row in rows
    ] == [
        ("Alpha", "First", "a.wav"),
        ("Alpha", "Second", "b.wav"),
        ("Beta", "Second", "z.wav"),
    ]


def test_classifier_score_counts_use_keys_and_count_rows_only(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    first = _add_track(
        database,
        tmp_path / "first.wav",
        title="First",
        artist="Artist",
    )
    second = _add_track(
        database,
        tmp_path / "second.wav",
        title="Second",
        artist="Artist",
    )
    with database.connect() as connection:
        connection.executemany(
            """
            INSERT INTO classifier_scores (
                track_id, track_uuid, classifier_key, feature_set,
                feature_names_json, positive_label, predicted_class,
                score_bucket, score, confidence, probabilities_json,
                analyzed_at
            ) VALUES (?, ?, ?, 'fixture', '["feature"]', 'positive',
                      'positive', 'high', 0.9, 0.9,
                      '{"negative": 0.1, "positive": 0.9}',
                      '2026-08-12T00:00:00Z')
            """,
            (
                (first.track_id, first.track_uuid, "voice_presence"),
                (second.track_id, second.track_uuid, "voice_presence"),
                (first.track_id, first.track_uuid, "energy"),
            ),
        )

    assert database.classifier_score_counts(
        ("voice_presence", "energy", "missing"),
    ) == {
        "voice_presence": 2,
        "energy": 1,
        "missing": 0,
    }


def test_fts_search_reads_the_rowid_the_index_writer_stores(
    tmp_path: Path,
) -> None:
    """Search resolves FTS hits through ``rowid``, not the stored column.

    The index writer sets ``rowid`` and the UNINDEXED ``track_id`` column to
    the same value, and both search modes rely on that to skip the FTS content
    table. Pin the two halves together: whichever side moves first, this fails
    instead of silently returning the wrong tracks.
    """

    database = LibraryDatabase(tmp_path / "library.sqlite")
    wanted = _add_track(
        database,
        tmp_path / "wanted.wav",
        title="Kollektiv Turmstrasse",
        artist="Alpha",
    )
    _add_track(
        database,
        tmp_path / "other.wav",
        title="Unrelated",
        artist="Beta",
    )

    rows = database.filter_track_summaries(
        query="Kollektiv",
        search_mode="fts",
    )

    assert [row.track_id for row in rows] == [wanted.track_id]
    with database.connect() as connection:
        mismatched = connection.execute(
            """
            SELECT COUNT(*)
            FROM track_search_fts
            WHERE rowid <> CAST(track_id AS INTEGER)
            """
        ).fetchone()[0]
    assert mismatched == 0


def _add_track(
    database: LibraryDatabase,
    path: Path,
    *,
    title: str,
    artist: str,
):
    mutation = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=100,
            file_modified_ns=1_000,
            audio_format="wav",
        ),
        tags=FileTags(
            title=title,
            artist=artist,
            album="Fixture",
        ),
    )
    return mutation.identity
