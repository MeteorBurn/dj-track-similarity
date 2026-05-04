from pathlib import Path
import sqlite3

import dj_track_similarity.scanner as scanner
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.scanner import read_audio_metadata, scan_library


def test_scan_library_indexes_supported_audio_files_and_skips_unchanged(tmp_path: Path) -> None:
    music_root = tmp_path / "music"
    music_root.mkdir()
    first = music_root / "Artist - Track.mp3"
    second = music_root / "ambient.wav"
    ignored = music_root / "notes.txt"
    first.write_bytes(b"not really mp3")
    second.write_bytes(b"RIFF0000WAVE")
    ignored.write_text("skip me", encoding="utf-8")

    db = LibraryDatabase(tmp_path / "library.sqlite")

    first_stats = scan_library(db, music_root)
    second_stats = scan_library(db, music_root)

    tracks = db.list_tracks()
    assert first_stats.added == 2
    assert first_stats.updated == 0
    assert first_stats.unchanged == 0
    assert second_stats.added == 0
    assert second_stats.updated == 0
    assert second_stats.unchanged == 2
    assert {Path(track.path).name for track in tracks} == {"Artist - Track.mp3", "ambient.wav"}
    assert all(track.size > 0 for track in tracks)


def test_read_audio_metadata_skips_tag_keys_that_mutagen_rejects(monkeypatch, tmp_path: Path) -> None:
    class RejectingTags(dict):
        def __contains__(self, key: object) -> bool:
            if key == "\xa9ART":
                raise ValueError("invalid Vorbis key")
            return super().__contains__(key)

    class FakeAudio:
        info = None
        tags = RejectingTags({"title": ["Warm Pad"]})

    monkeypatch.setattr(scanner, "MutagenFile", lambda path: FakeAudio())

    metadata = read_audio_metadata(tmp_path / "track.flac")

    assert metadata["title"] == "Warm Pad"
    assert "artist" not in metadata


def test_database_stores_multiple_embedding_spaces_per_track(tmp_path: Path) -> None:
    import numpy as np

    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(path=tmp_path / "track.wav", size=10, mtime=1, metadata={"title": "Track"})

    db.save_embedding(track_id, np.array([1, 0, 0], dtype=np.float32), "mert-model", 3, embedding_key="mert")
    db.save_embedding(track_id, np.array([0, 1, 0], dtype=np.float32), "clap-model", 3, embedding_key="clap")

    mert_tracks, mert_matrix = db.load_embedding_matrix("mert")
    clap_tracks, clap_matrix = db.load_embedding_matrix("clap")

    assert [track.id for track in mert_tracks] == [track_id]
    assert [track.id for track in clap_tracks] == [track_id]
    assert mert_tracks[0].embedding_model == "mert-model"
    assert clap_tracks[0].embedding_model == "clap-model"
    assert mert_matrix.shape == (1, 3)
    assert clap_matrix.shape == (1, 3)

    track = db.get_track(track_id)

    assert track.analyses == ["mert", "clap"]


def test_database_stores_maest_genres_in_track_metadata(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=tmp_path / "track.wav",
        size=10,
        mtime=1,
        metadata={"title": "Track", "artist": "Artist"},
    )

    db.save_genres(
        track_id,
        [{"label": "Techno", "score": 0.91}, {"label": "Dub Techno", "score": 0.72}],
        model_name="discogs-maest-30s-pw-129e-519l",
    )

    track = db.get_track(track_id)

    assert track.metadata["title"] == "Track"
    assert track.metadata["artist"] == "Artist"
    assert track.analyses == ["maest"]
    assert track.genres == ["Techno", "Dub Techno"]
    assert track.genre_scores == {"Techno": 0.91, "Dub Techno": 0.72}
    assert track.artist == "Artist"


def test_database_migrates_legacy_embedding_table(tmp_path: Path) -> None:
    import numpy as np

    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL UNIQUE,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                artist TEXT,
                title TEXT,
                album TEXT,
                bpm REAL,
                musical_key TEXT,
                energy REAL,
                duration REAL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE embeddings (
                track_id INTEGER PRIMARY KEY,
                model_name TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector BLOB NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO tracks (path, size, mtime, title) VALUES ('C:/music/a.wav', 10, 1, 'A');
            """
        )
        connection.execute(
            "INSERT INTO embeddings (track_id, model_name, dim, vector) VALUES (1, 'legacy-mert', 3, ?)",
            (np.array([1, 0, 0], dtype=np.float32).tobytes(),),
        )

    db = LibraryDatabase(db_path)
    tracks, matrix = db.load_embedding_matrix("mert")

    assert [track.id for track in tracks] == [1]
    assert tracks[0].embedding_model == "legacy-mert"
    assert matrix.shape == (1, 3)
