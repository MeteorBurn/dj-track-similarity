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
