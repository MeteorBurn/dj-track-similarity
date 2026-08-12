from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from metadata_enrichment.local_library import read_local_evidence
from metadata_enrichment.models import TrackInput


def test_local_reader_uses_exact_file_path_and_keeps_top_three_maest(tmp_path: Path) -> None:
    """Prevent fuzzy DB matching from attaching another track's genre evidence."""

    db_path = tmp_path / "library.sqlite"
    track_path = r"C:\music\one.flac"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE tracks (track_id INTEGER PRIMARY KEY, file_path TEXT NOT NULL UNIQUE);
            CREATE TABLE tags (track_id INTEGER PRIMARY KEY, genres_json TEXT NOT NULL);
            CREATE TABLE maest_genres (track_id INTEGER PRIMARY KEY, genres_json TEXT NOT NULL);
            """
        )
        connection.execute("INSERT INTO tracks VALUES (1, ?)", (track_path,))
        connection.execute("INSERT INTO tags VALUES (1, ?)", (json.dumps(["Electronic", "Dance"]),))
        connection.execute(
            "INSERT INTO maest_genres VALUES (1, ?)",
            (json.dumps([
                {"label": "House", "score": 0.81},
                {"label": "Techno", "score": 0.64},
                {"label": "Electronic", "score": 0.52},
                {"label": "Ambient", "score": 0.40},
            ]),),
        )

    evidence = read_local_evidence(db_path, TrackInput(file_path=Path(track_path)))

    assert evidence.file_tags == ("Electronic", "Dance")
    assert evidence.maest == (("House", 0.81), ("Techno", 0.64), ("Electronic", 0.52))


def test_local_reader_accepts_only_the_same_windows_path_with_slash_normalization(tmp_path: Path) -> None:
    """Path separators may differ between an indexed Windows path and CLI input."""

    db_path = tmp_path / "library.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript("""
            CREATE TABLE tracks (track_id INTEGER PRIMARY KEY, file_path TEXT NOT NULL UNIQUE);
            CREATE TABLE tags (track_id INTEGER PRIMARY KEY, genres_json TEXT NOT NULL);
            CREATE TABLE maest_genres (track_id INTEGER PRIMARY KEY, genres_json TEXT NOT NULL);
        """)
        connection.execute("INSERT INTO tracks VALUES (1, ?)", ("C:/music/one.flac",))
        connection.execute("INSERT INTO tags VALUES (1, ?)", (json.dumps(["House"]),))
        connection.execute("INSERT INTO maest_genres VALUES (1, ?)", (json.dumps([]),))

    evidence = read_local_evidence(db_path, TrackInput(file_path=Path(r"C:\music\one.flac")))

    assert evidence.matched_path == "C:/music/one.flac"
    assert evidence.file_tags == ("House",)


def test_local_reader_falls_back_to_one_exact_artist_and_title_match(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript("""
            CREATE TABLE tracks (track_id INTEGER PRIMARY KEY, file_path TEXT NOT NULL UNIQUE);
            CREATE TABLE tags (track_id INTEGER PRIMARY KEY, artist TEXT, title TEXT, genres_json TEXT NOT NULL);
            CREATE TABLE maest_genres (track_id INTEGER PRIMARY KEY, genres_json TEXT NOT NULL);
        """)
        connection.execute("INSERT INTO tracks VALUES (1, ?)", ("M:/library/alex.flac",))
        connection.execute("INSERT INTO tags VALUES (1, ?, ?, ?)", ("Alex Font & Barac", "Healing Through Music", json.dumps(["Techno"])) )
        connection.execute("INSERT INTO maest_genres VALUES (1, ?)", (json.dumps([{"label": "Progressive House", "score": .42}]),))

    evidence = read_local_evidence(db_path, TrackInput(artist="Alex Font & Barac", title="Healing Through Music"))

    assert evidence.matched_path == "M:/library/alex.flac"
    assert evidence.file_tags == ("Techno",)
    assert evidence.maest == (("Progressive House", .42),)


def test_local_reader_refuses_ambiguous_artist_and_title_matches(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript("""
            CREATE TABLE tracks (track_id INTEGER PRIMARY KEY, file_path TEXT NOT NULL UNIQUE);
            CREATE TABLE tags (track_id INTEGER PRIMARY KEY, artist TEXT, title TEXT, genres_json TEXT NOT NULL);
            CREATE TABLE maest_genres (track_id INTEGER PRIMARY KEY, genres_json TEXT NOT NULL);
        """)
        for track_id, path in ((1, "M:/library/one.flac"), (2, "M:/library/two.flac")):
            connection.execute("INSERT INTO tracks VALUES (?, ?)", (track_id, path))
            connection.execute("INSERT INTO tags VALUES (?, ?, ?, ?)", (track_id, "Artist", "Title", json.dumps(["House"])))
            connection.execute("INSERT INTO maest_genres VALUES (?, ?)", (track_id, json.dumps([])))

    evidence = read_local_evidence(db_path, TrackInput(artist="Artist", title="Title"))

    assert evidence.matched_path is None
    assert evidence.file_tags == ()
