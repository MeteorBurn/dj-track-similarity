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
