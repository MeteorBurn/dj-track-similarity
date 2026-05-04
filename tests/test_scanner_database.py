from pathlib import Path
import json
import sqlite3

import pytest

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


def test_read_audio_metadata_uses_fixed_tag_whitelist(monkeypatch, tmp_path: Path) -> None:
    class FakeInfo:
        length = 123.4

    class FakeAudio:
        info = FakeInfo()
        tags = {
            "title": ["Warm Pad"],
            "artist": ["Artist"],
            "genre": ["Deep Techno"],
            "year": ["2024"],
            "country": ["DE"],
            "publisher": ["Small Label"],
            "CATALOGNUMBER": ["CAT-001"],
            "isrc": ["US-ABC-24-00001"],
            "random_plugin_blob": ["ignore me"],
        }

    monkeypatch.setattr(scanner, "MutagenFile", lambda path: FakeAudio())

    metadata = read_audio_metadata(tmp_path / "track.flac")

    assert metadata == {
        "artist": "Artist",
        "catalog_number": "CAT-001",
        "duration": 123.4,
        "genre": "Deep Techno",
        "isrc": "US-ABC-24-00001",
        "country": "DE",
        "label": "Small Label",
        "title": "Warm Pad",
        "year": "2024",
    }


def test_read_audio_metadata_converts_mutagen_objects_to_json_safe_values(monkeypatch, tmp_path: Path) -> None:
    class FakeTimestamp:
        def __str__(self) -> str:
            return "2025-04-01"

    class FakeFrame:
        text = [FakeTimestamp()]

    class FakeAudio:
        info = None
        tags = {
            "TDRC": FakeFrame(),
            "trkn": [(2, 4)],
        }

    monkeypatch.setattr(scanner, "MutagenFile", lambda path: FakeAudio())

    metadata = read_audio_metadata(tmp_path / "track.mp3")

    assert metadata["year"] == "2025-04-01"
    assert metadata["track_number"] == "2/4"
    assert json.dumps(metadata)


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


def test_database_resets_embedding_analysis_independently(tmp_path: Path) -> None:
    import numpy as np

    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(path=tmp_path / "track.wav", size=10, mtime=1, metadata={"title": "Track"})
    db.save_embedding(track_id, np.array([1, 0, 0], dtype=np.float32), "mert-model", 3, embedding_key="mert")
    db.save_embedding(track_id, np.array([0, 1, 0], dtype=np.float32), "clap-model", 3, embedding_key="clap")

    result = db.reset_analysis("mert")

    assert result == {"adapter": "mert", "tracks_updated": 0, "embeddings_deleted": 1}
    assert db.load_embedding_matrix("mert")[0] == []
    assert [track.id for track in db.load_embedding_matrix("clap")[0]] == [track_id]
    assert db.get_track(track_id).analyses == ["clap"]


def test_database_clear_library_removes_tracks_embeddings_and_playlists(tmp_path: Path) -> None:
    import numpy as np

    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(path=tmp_path / "track.wav", size=10, mtime=1, metadata={"title": "Track"})
    db.save_embedding(track_id, np.array([1, 0, 0], dtype=np.float32), "mert-model", 3, embedding_key="mert")
    playlist_id = db.create_playlist("Set", [track_id])

    result = db.clear_library()

    assert result == {
        "tracks_deleted": 1,
        "embeddings_deleted": 1,
        "playlists_deleted": 1,
        "playlist_tracks_deleted": 1,
    }
    assert db.list_tracks() == []
    assert db.load_embedding_matrix("mert")[0] == []
    with pytest.raises(KeyError):
        db.get_playlist_name(playlist_id)


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


def test_database_resets_metadata_backed_analyses(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=tmp_path / "track.wav",
        size=10,
        mtime=1,
        metadata={"title": "Track", "bpm": 120, "initialkey": "A minor", "duration": 90},
    )
    db.save_genres(track_id, [{"label": "Techno", "score": 0.91}], model_name="maest")
    db.save_sonara_features(
        track_id,
        {"bpm": {"value": 128}},
        bpm=128,
        musical_key="F major",
        energy=0.8,
        duration=100,
        model_name="sonara",
    )

    sonara_result = db.reset_analysis("sonara")
    after_sonara = db.get_track(track_id)
    maest_result = db.reset_analysis("maest")
    after_maest = db.get_track(track_id)

    assert sonara_result["tracks_updated"] == 1
    assert after_sonara.bpm == 120
    assert after_sonara.musical_key == "A minor"
    assert after_sonara.energy is None
    assert after_sonara.duration == 90
    assert "sonara_features" not in after_sonara.metadata
    assert after_sonara.analyses == ["maest"]
    assert maest_result["tracks_updated"] == 1
    assert "maest_genres" not in after_maest.metadata
    assert after_maest.analyses is None


def test_refresh_track_file_metadata_preserves_analysis_outputs(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=tmp_path / "track.wav",
        size=10,
        mtime=1,
        metadata={"title": "Old", "year": "2023", "random_old": "kept"},
    )
    db.save_sonara_features(
        track_id,
        {"bpm": {"value": 128}},
        bpm=128,
        musical_key="F major",
        energy=0.8,
        duration=100,
        model_name="sonara",
    )

    db.refresh_track_file_metadata(
        track_id,
        size=20,
        mtime=2,
        metadata={"title": "New", "year": "2024", "country": "DE", "duration": 90, "bpm": 120, "key": "A minor"},
        replace_metadata_keys=("title", "year", "country", "duration", "bpm", "key"),
    )
    track = db.get_track(track_id)

    assert track.title == "New"
    assert track.bpm == 128
    assert track.musical_key == "F major"
    assert track.duration == 100
    assert track.metadata["year"] == "2024"
    assert track.metadata["country"] == "DE"
    assert track.metadata["random_old"] == "kept"
    assert track.analyses == ["sonara"]


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
