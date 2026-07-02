from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import math
import sqlite3

import numpy as np
import pytest

import dj_track_similarity.scanner as scanner
from dj_track_similarity.db_schema import CURRENT_SCHEMA_VERSION
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.scanner import read_audio_metadata, scan_library


def test_database_uses_wal_and_busy_timeout_for_concurrent_jobs(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")

    with db.connect() as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        busy_timeout = connection.execute("PRAGMA busy_timeout").fetchone()[0]
        synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
        temp_store = connection.execute("PRAGMA temp_store").fetchone()[0]

    assert str(journal_mode).lower() == "wal"
    assert busy_timeout >= 30_000
    assert synchronous == 1
    assert temp_store == 2


def test_new_database_uses_current_schema_version_and_indexes(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")

    with db.connect() as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        track_columns = {row["name"] for row in connection.execute("PRAGMA table_info(tracks)").fetchall()}
        track_indexes = {row["name"] for row in connection.execute("PRAGMA index_list(tracks)").fetchall()}
        embedding_indexes = {row["name"] for row in connection.execute("PRAGMA index_list(embeddings)").fetchall()}

    assert version == CURRENT_SCHEMA_VERSION
    assert "library_settings" in tables
    assert "track_search_fts" in tables
    assert {
        "idx_tracks_sort_artist_title_path",
        "idx_tracks_syncopated_sort",
        "idx_tracks_missing_sonara_flag_sort",
        "idx_tracks_missing_maest_embedding_flag_sort",
        "idx_tracks_missing_mert_embedding_flag_sort",
        "idx_tracks_missing_muq_embedding_flag_sort",
        "idx_tracks_missing_clap_embedding_flag_sort",
        "idx_tracks_present_sonara_flag",
        "idx_tracks_present_maest_embedding_flag",
        "idx_tracks_present_mert_embedding_flag",
        "idx_tracks_present_muq_embedding_flag",
        "idx_tracks_present_clap_embedding_flag",
    }.issubset(track_indexes)
    assert {
        "has_sonara_analysis",
        "has_maest_embedding",
        "has_mert_embedding",
        "has_muq_embedding",
        "has_clap_embedding",
    }.issubset(track_columns)
    assert not {
        "idx_tracks_sonara_present",
        "idx_tracks_maest_present",
        "idx_tracks_sonara_missing_sort",
        "idx_tracks_maest_missing_sort",
    }.intersection(track_indexes)
    assert "idx_embeddings_key_track" in embedding_indexes


def test_existing_v4_database_without_muq_flag_is_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
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
                has_sonara_analysis INTEGER NOT NULL DEFAULT 0,
                has_maest_embedding INTEGER NOT NULL DEFAULT 0,
                has_mert_embedding INTEGER NOT NULL DEFAULT 0,
                has_clap_embedding INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE embeddings (
                track_id INTEGER NOT NULL,
                embedding_key TEXT NOT NULL DEFAULT 'mert',
                model_name TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector BLOB NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(track_id, embedding_key)
            );
            INSERT INTO tracks (path, size, mtime, title, metadata_json)
            VALUES ('muq.wav', 10, 1, 'MuQ', '{}'), ('mert.wav', 10, 1, 'MERT', '{}');
            INSERT INTO embeddings (track_id, embedding_key, model_name, dim, vector)
            VALUES (1, 'muq', 'muq-test', 2, X'0000'), (2, 'mert', 'mert-test', 2, X'0000');
            PRAGMA user_version = 4;
            """
        )

    with pytest.raises(RuntimeError, match="schema is not current"):
        LibraryDatabase(db_path)


def test_track_search_fts_mode_is_explicit_token_search(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    substring_id = db.upsert_track(
        path=tmp_path / "substring.wav",
        size=10,
        mtime=1,
        metadata={"artist": "DJ One", "title": "AlphaBeta"},
    )
    token_id = db.upsert_track(
        path=tmp_path / "token.wav",
        size=10,
        mtime=1,
        metadata={"artist": "DJ Two", "title": "Deep House"},
    )

    like_page = db.list_tracks_page(query="phaB")
    fts_substring_page = db.list_tracks_page(query="phaB", search_mode="fts")
    fts_token_page = db.list_tracks_page(query="deep house", search_mode="fts")

    assert [track.id for track in like_page["items"]] == [substring_id]
    assert fts_substring_page["total"] == 0
    assert [track.id for track in fts_token_page["items"]] == [token_id]


def test_database_persists_library_root_setting(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    music_root = tmp_path / "music"
    music_root.mkdir()
    db = LibraryDatabase(db_path)

    assert db.get_library_root() is None
    db.set_library_root(music_root)

    assert db.get_library_root() == music_root.as_posix()
    assert LibraryDatabase(db_path).get_library_root() == music_root.as_posix()


def test_database_instances_for_same_file_share_write_lock(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    first = LibraryDatabase(db_path)
    second = LibraryDatabase(db_path)

    assert first._write_lock is second._write_lock


def test_database_serializes_parallel_sonara_feature_writes(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = [
        db.upsert_track(path=tmp_path / f"track-{index}.wav", size=10, mtime=1, metadata={"title": f"Track {index}"})
        for index in range(16)
    ]

    def save(track_id: int) -> None:
        db.save_sonara_features(
            track_id,
            {"bpm": {"value": 120 + track_id}},
            bpm=120 + track_id,
            model_name="sonara-test",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save, track_ids))

    tracks = db.list_tracks()
    assert len(tracks) == len(track_ids)
    assert all(track.metadata["sonara_model"] == "sonara-test" for track in tracks)


def test_database_serializes_mixed_parallel_analysis_writes_across_instances(tmp_path: Path) -> None:
    import numpy as np

    db_path = tmp_path / "library.sqlite"
    setup_db = LibraryDatabase(db_path)
    sonara_id = setup_db.upsert_track(path=tmp_path / "sonara.wav", size=10, mtime=1, metadata={"title": "Sonara"})
    maest_id = setup_db.upsert_track(path=tmp_path / "maest.wav", size=10, mtime=1, metadata={"title": "Maest"})
    mert_id = setup_db.upsert_track(path=tmp_path / "mert.wav", size=10, mtime=1, metadata={"title": "Mert"})

    def save_sonara() -> None:
        LibraryDatabase(db_path).save_sonara_features(
            sonara_id,
            {"energy": {"value": 0.7}},
            energy=0.7,
            model_name="sonara-test",
        )

    def save_genres() -> None:
        LibraryDatabase(db_path).save_genres(maest_id, [{"label": "Techno", "score": 0.9}], model_name="maest-test")

    def save_embedding() -> None:
        LibraryDatabase(db_path).save_embedding(
            mert_id,
            np.array([1, 0, 0], dtype=np.float32),
            "mert-test",
            3,
            embedding_key="mert",
        )

    with ThreadPoolExecutor(max_workers=3) as executor:
        list(executor.map(lambda action: action(), [save_sonara, save_genres, save_embedding]))

    tracks = {Path(track.path).name: track for track in LibraryDatabase(db_path).list_tracks()}
    assert tracks["sonara.wav"].metadata["sonara_model"] == "sonara-test"
    assert tracks["maest.wav"].metadata["maest_model"] == "maest-test"
    assert tracks["mert.wav"].analyses == ["mert"]


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


def test_scan_library_skips_appledouble_resource_fork_audio_names(tmp_path: Path) -> None:
    music_root = tmp_path / "music"
    music_root.mkdir()
    audio = music_root / "01. Lampetee.aiff"
    resource_fork = music_root / "._01. Lampetee.aiff"
    audio.write_bytes(b"FORM\x00\x00\x00\x04AIFF")
    resource_fork.write_bytes(b"not an audio stream")
    db = LibraryDatabase(tmp_path / "library.sqlite")

    stats = scan_library(db, music_root)

    assert stats.added == 1
    assert [Path(track.path).name for track in db.list_tracks()] == ["01. Lampetee.aiff"]


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
        codec = "FLAC"

    class FakeAudio:
        info = FakeInfo()
        mime = ["audio/flac"]
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
        "audio_codec": "FLAC",
        "audio_format": "FLAC",
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
    db.save_embedding(track_id, np.array([0, 0, 1], dtype=np.float32), "muq-model", 3, embedding_key="muq")
    db.save_embedding(track_id, np.array([0, 1, 0], dtype=np.float32), "clap-model", 3, embedding_key="clap")

    mert_tracks, mert_matrix = db.load_embedding_matrix("mert")
    muq_tracks, muq_matrix = db.load_embedding_matrix("muq")
    clap_tracks, clap_matrix = db.load_embedding_matrix("clap")

    assert [track.id for track in mert_tracks] == [track_id]
    assert [track.id for track in muq_tracks] == [track_id]
    assert [track.id for track in clap_tracks] == [track_id]
    assert mert_tracks[0].embedding_model == "mert-model"
    assert muq_tracks[0].embedding_model == "muq-model"
    assert clap_tracks[0].embedding_model == "clap-model"
    assert mert_matrix.shape == (1, 3)
    assert muq_matrix.shape == (1, 3)
    assert clap_matrix.shape == (1, 3)

    track = db.get_track(track_id)

    assert track.analyses == ["mert", "muq", "clap"]


def test_database_keeps_embedding_matrix_cache_when_unembedded_track_changes(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    embedded_id = db.upsert_track(path=tmp_path / "embedded.wav", size=10, mtime=1, metadata={"title": "Embedded"})
    plain_id = db.upsert_track(path=tmp_path / "plain.wav", size=10, mtime=1, metadata={"title": "Plain"})
    db.save_embedding(embedded_id, np.array([1, 0, 0], dtype=np.float32), "mert-model", 3, embedding_key="mert")

    cached = db.load_embedding_matrix("mert")
    db.set_track_liked(plain_id, True)
    db.upsert_track(path=tmp_path / "new.wav", size=10, mtime=1, metadata={"title": "New"})

    assert db.load_embedding_matrix("mert") is cached


def test_database_invalidates_only_changed_track_embedding_keys(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    mert_id = db.upsert_track(path=tmp_path / "mert.wav", size=10, mtime=1, metadata={"title": "Mert"})
    clap_id = db.upsert_track(path=tmp_path / "clap.wav", size=10, mtime=1, metadata={"title": "Clap"})
    db.save_embedding(mert_id, np.array([1, 0, 0], dtype=np.float32), "mert-model", 3, embedding_key="mert")
    db.save_embedding(clap_id, np.array([0, 1, 0], dtype=np.float32), "clap-model", 3, embedding_key="clap")

    db.load_embedding_matrix("mert")
    cached_clap = db.load_embedding_matrix("clap")
    db.save_sonara_features(mert_id, {"energy": {"value": 0.8}}, energy=0.8, model_name="sonara")

    assert "mert" not in db._embedding_matrix_cache
    assert db.load_embedding_matrix("clap") is cached_clap


def test_database_resets_embedding_analysis_independently(tmp_path: Path) -> None:
    import numpy as np

    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(path=tmp_path / "track.wav", size=10, mtime=1, metadata={"title": "Track"})
    db.save_embedding(track_id, np.array([1, 0, 0], dtype=np.float32), "mert-model", 3, embedding_key="mert")
    db.save_embedding(track_id, np.array([0, 0, 1], dtype=np.float32), "muq-model", 3, embedding_key="muq")
    db.save_embedding(track_id, np.array([0, 1, 0], dtype=np.float32), "clap-model", 3, embedding_key="clap")

    result = db.reset_analysis("muq")

    assert result == {"adapter": "muq", "tracks_updated": 0, "embeddings_deleted": 1}
    assert [track.id for track in db.load_embedding_matrix("mert")[0]] == [track_id]
    assert db.load_embedding_matrix("muq")[0] == []
    assert [track.id for track in db.load_embedding_matrix("clap")[0]] == [track_id]
    assert db.get_track(track_id).analyses == ["mert", "clap"]


def test_database_maintains_analysis_presence_flags(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(path=tmp_path / "track.wav", size=10, mtime=1, metadata={"title": "Track"})

    assert _analysis_flag_row(db, track_id) == {
        "has_sonara_analysis": 0,
        "has_maest_embedding": 0,
        "has_mert_embedding": 0,
        "has_muq_embedding": 0,
        "has_clap_embedding": 0,
    }

    db.save_sonara_features(track_id, {"bpm": {"value": 128}}, model_name="sonara")
    db.save_embedding(track_id, np.asarray([1.0, 0.0], dtype=np.float32), "maest", embedding_key="maest")
    db.save_embedding(track_id, np.asarray([0.0, 1.0], dtype=np.float32), "mert", embedding_key="mert")
    db.save_embedding(track_id, np.asarray([1.0, 0.0], dtype=np.float32), "muq", embedding_key="muq")
    db.save_embedding(track_id, np.asarray([1.0, 1.0], dtype=np.float32), "clap", embedding_key="clap")

    assert _analysis_flag_row(db, track_id) == {
        "has_sonara_analysis": 1,
        "has_maest_embedding": 1,
        "has_mert_embedding": 1,
        "has_muq_embedding": 1,
        "has_clap_embedding": 1,
    }

    db.reset_analysis("mert")
    db.reset_analysis("muq")
    db.reset_analysis("sonara")
    db.reset_analysis("maest")

    assert _analysis_flag_row(db, track_id) == {
        "has_sonara_analysis": 0,
        "has_maest_embedding": 0,
        "has_mert_embedding": 0,
        "has_muq_embedding": 0,
        "has_clap_embedding": 1,
    }


def test_database_lists_lean_analysis_candidates_with_missing_models(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    missing_mert = db.upsert_track(path=tmp_path / "a-missing-mert.wav", size=10, mtime=1, metadata={"title": "A"})
    missing_sonara = db.upsert_track(path=tmp_path / "b-missing-sonara.wav", size=10, mtime=1, metadata={"title": "B"})
    complete = db.upsert_track(path=tmp_path / "c-complete.wav", size=10, mtime=1, metadata={"title": "C"})
    missing_unselected = db.upsert_track(path=tmp_path / "d-missing-clap.wav", size=10, mtime=1, metadata={"title": "D"})

    db.save_sonara_features(missing_mert, {"bpm": {"value": 128.0}}, model_name="sonara")
    db.save_embedding(missing_sonara, np.asarray([1.0, 0.0], dtype=np.float32), "mert", embedding_key="mert")
    for track_id in (complete, missing_unselected):
        db.save_sonara_features(track_id, {"bpm": {"value": 128.0}}, model_name="sonara")
        db.save_embedding(track_id, np.asarray([1.0, 0.0], dtype=np.float32), "mert", embedding_key="mert")

    candidates = db.list_analysis_candidates(["sonara", "mert"], limit=10)

    assert [(candidate.id, candidate.missing_models, candidate.analyses) for candidate in candidates] == [
        (missing_mert, ("mert",), ("sonara",)),
        (missing_sonara, ("sonara",), ("mert",)),
    ]


def test_database_lists_muq_analysis_candidates_from_muq_flag(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    missing_muq = db.upsert_track(path=tmp_path / "a-missing-muq.wav", size=10, mtime=1, metadata={"title": "A"})
    present_muq = db.upsert_track(path=tmp_path / "b-present-muq.wav", size=10, mtime=1, metadata={"title": "B"})
    db.save_embedding(present_muq, np.asarray([1.0, 0.0], dtype=np.float32), "muq", embedding_key="muq")

    candidates = db.list_analysis_candidates(["muq"], limit=10)

    assert [(candidate.id, candidate.missing_models, candidate.analyses) for candidate in candidates] == [
        (missing_muq, ("muq",), ()),
    ]


def test_database_lists_analysis_candidates_with_one_read_connection(tmp_path: Path) -> None:
    class CountingDatabase(LibraryDatabase):
        connect_calls = 0

        def connect(self):
            self.connect_calls += 1
            return super().connect()

    db = CountingDatabase(tmp_path / "library.sqlite")
    db.upsert_track(path=tmp_path / "a-missing-mert.wav", size=10, mtime=1, metadata={"title": "A"})
    db.upsert_track(path=tmp_path / "b-missing-sonara.wav", size=10, mtime=1, metadata={"title": "B"})
    db.connect_calls = 0

    candidates = db.list_analysis_candidates(["sonara", "mert"], limit=10)

    assert len(candidates) == 2
    assert db.connect_calls == 1


@pytest.mark.parametrize(
    ("model", "index_name"),
    [
        ("mert", "idx_tracks_missing_mert_embedding_flag_sort"),
        ("muq", "idx_tracks_missing_muq_embedding_flag_sort"),
    ],
)
def test_database_analysis_candidates_use_presence_flag_indexes(
    tmp_path: Path,
    monkeypatch,
    model: str,
    index_name: str,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    db.upsert_track(path=tmp_path / f"a-missing-{model}.wav", size=10, mtime=1, metadata={"title": "A"})
    present_id = db.upsert_track(path=tmp_path / f"b-present-{model}.wav", size=10, mtime=1, metadata={"title": "B"})
    db.save_embedding(present_id, np.asarray([1.0, 0.0], dtype=np.float32), model, embedding_key=model)
    statements: list[str] = []
    original_connect = db.connect

    def traced_connect():
        connection = original_connect()
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(db, "connect", traced_connect)

    candidates = db.list_analysis_candidates([model], limit=10)

    assert [candidate.path for candidate in candidates] == [(tmp_path / f"a-missing-{model}.wav").as_posix()]
    candidate_sql = next(statement for statement in statements if "SELECT t.id" in statement and f"has_{model}_embedding" in statement)
    assert "LEFT JOIN embeddings" not in candidate_sql
    with db.connect() as connection:
        plan = "\n".join(
            str(row["detail"])
            for row in connection.execute(f"EXPLAIN QUERY PLAN {candidate_sql}").fetchall()
        )
    assert index_name in plan


def test_database_reset_rejects_removed_fake_adapter(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")

    with pytest.raises(ValueError, match="Unsupported analysis adapter reset: fake"):
        db.reset_analysis("fake")


def test_database_clear_library_removes_tracks_and_embeddings(tmp_path: Path) -> None:
    import numpy as np

    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(path=tmp_path / "track.wav", size=10, mtime=1, metadata={"title": "Track"})
    db.save_embedding(track_id, np.array([1, 0, 0], dtype=np.float32), "mert-model", 3, embedding_key="mert")

    result = db.clear_library()

    assert result == {
        "tracks_deleted": 1,
        "embeddings_deleted": 1,
    }
    assert db.list_tracks() == []
    assert db.load_embedding_matrix("mert")[0] == []


def test_existing_database_with_old_user_version_is_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
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
                metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE embeddings (
                track_id INTEGER NOT NULL,
                embedding_key TEXT NOT NULL DEFAULT 'mert',
                model_name TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector BLOB NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(track_id, embedding_key),
                FOREIGN KEY(track_id) REFERENCES tracks(id) ON DELETE CASCADE
            );
            INSERT INTO tracks (path, size, mtime, title, metadata_json)
            VALUES ('track.wav', 10, 1, 'Track', '{}');
            """
        )

    with pytest.raises(RuntimeError, match="schema is not current"):
        LibraryDatabase(db_path)


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
        [{"label": "Electronic---Techno", "score": 0.91}, {"label": "Electronic---Dub_Techno", "score": 0.72}],
        model_name="discogs-maest-30s-pw-129e-519l",
    )

    track = db.get_track(track_id)
    with db.connect() as connection:
        metadata_json = connection.execute("SELECT metadata_json FROM tracks WHERE id = ?", (track_id,)).fetchone()["metadata_json"]
    metadata_keys = list(json.loads(metadata_json).keys())

    assert track.metadata["title"] == "Track"
    assert track.metadata["artist"] == "Artist"
    assert metadata_keys[-3:] == ["maest_model", "maest_genres", "maest_syncopated_rhythm"]
    assert track.analyses is None
    assert track.genres == ["Techno", "Dub Techno"]
    assert track.genre_scores == {"Techno": 0.91, "Dub Techno": 0.72}
    assert track.metadata["maest_syncopated_rhythm"] is False
    assert track.artist == "Artist"

    db.save_embedding(
        track_id,
        np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
        "discogs-maest-30s-pw-129e-519l",
        embedding_key="maest",
    )
    assert db.get_track(track_id).analyses == ["maest"]


def test_database_marks_maest_syncopated_rhythm_from_saved_genres(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    breaks_id = db.upsert_track(path=tmp_path / "breaks.wav", size=10, mtime=1, metadata={"title": "Breaks"})
    house_id = db.upsert_track(path=tmp_path / "house.wav", size=10, mtime=1, metadata={"title": "House"})

    db.save_genres(breaks_id, [{"label": "Electronic---Breakbeat", "score": 0.91}], model_name="maest")
    db.save_genres(house_id, [{"label": "Electronic---Tech House", "score": 0.82}], model_name="maest")

    assert db.get_track(breaks_id).metadata["maest_syncopated_rhythm"] is True
    assert db.get_track(house_id).metadata["maest_syncopated_rhythm"] is False


def test_database_stores_metadata_json_without_non_finite_numbers(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=tmp_path / "track.wav",
        size=10,
        mtime=1,
        metadata={"title": "Track", "tag_confidence": math.nan},
    )
    db.save_genres(track_id, [{"label": "Breakbeat", "score": math.nan}], model_name="maest")
    db.save_sonara_features(track_id, {"energy": {"value": math.inf}}, energy=math.inf, model_name="sonara")

    with db.connect() as connection:
        row = connection.execute(
            "SELECT metadata_json, json_valid(metadata_json) AS valid FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()

    assert row["valid"] == 1
    metadata = json.loads(row["metadata_json"])
    assert metadata["tag_confidence"] is None
    assert metadata["maest_genres"][0]["score"] == 0.0
    assert metadata["sonara_features"]["energy"]["value"] is None
    assert db.get_track(track_id).energy is None


def test_database_rejects_non_finite_embedding_vectors(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(path=tmp_path / "track.wav", size=10, mtime=1, metadata={"title": "Track"})

    for vector in (
        np.asarray([1.0, np.nan, 0.0], dtype=np.float32),
        np.asarray([1.0, np.inf, 0.0], dtype=np.float32),
        np.asarray([1.0, -np.inf, 0.0], dtype=np.float32),
    ):
        with pytest.raises(ValueError, match="finite"):
            db.save_embedding(track_id, vector, "mert-test", embedding_key="mert")

    assert db.load_embedding_matrix("mert")[0] == []


def test_database_resets_metadata_backed_analyses(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=tmp_path / "track.wav",
        size=10,
        mtime=1,
        metadata={"title": "Track", "bpm": 120, "initialkey": "A minor", "duration": 90},
    )
    db.save_genres(track_id, [{"label": "Techno", "score": 0.91}], model_name="maest")
    db.save_embedding(
        track_id,
        np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
        "maest",
        embedding_key="maest",
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

    sonara_result = db.reset_analysis("sonara")
    after_sonara = db.get_track(track_id)
    maest_result = db.reset_analysis("maest")
    after_maest = db.get_track(track_id)

    assert sonara_result["tracks_updated"] == 1
    assert maest_result["embeddings_deleted"] == 1
    assert after_sonara.bpm == 120
    assert after_sonara.musical_key == "A minor"
    assert after_sonara.energy is None
    assert after_sonara.duration == 90
    assert "sonara_features" not in after_sonara.metadata
    assert after_sonara.analyses == ["maest"]
    assert maest_result["tracks_updated"] == 1
    assert "maest_genres" not in after_maest.metadata
    assert db.load_embedding_matrix("maest")[0] == []
    assert "maest_syncopated_rhythm" not in after_maest.metadata
    assert after_maest.analyses is None


def test_database_does_not_enrich_existing_sonara_key_with_camelot_on_read(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(
        path=tmp_path / "track.wav",
        size=10,
        mtime=1,
        metadata={
            "title": "Track",
            "sonara_features": {
                "bpm": {"value": 128, "type": "float"},
                "key": {"value": "F major", "type": "str"},
            },
            "sonara_model": "sonara-playlist-lab",
        },
        bpm=128,
        musical_key="F major",
    )

    track = db.get_track(track_id)

    assert track.musical_key == "F major"
    assert "camelot_key" not in track.metadata["sonara_features"]


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


def test_database_blocks_new_invalid_metadata_json_values(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = db.upsert_track(path=tmp_path / "track.wav", size=10, mtime=1, metadata={"title": "Track"})

    with db.connect() as connection:
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute(
                "UPDATE tracks SET metadata_json = ? WHERE id = ?",
                ("{", track_id),
            )


def test_relocate_library_dry_run_preserves_tracks_and_reports_missing_files(tmp_path: Path) -> None:
    old_root = tmp_path / "ssd_music"
    new_root = tmp_path / "archive_music"
    old_root.mkdir()
    new_root.mkdir()
    old_file = old_root / "Artist" / "track.wav"
    old_file.parent.mkdir()
    old_file.write_bytes(b"audio")

    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(path=old_file, size=old_file.stat().st_size, mtime=old_file.stat().st_mtime)
    db.save_sonara_features(track_id, {"tempo": 128}, bpm=128.0, model_name="sonara-test")

    result = db.relocate_library(old_root, new_root, apply=False)

    assert result["dry_run"] is True
    assert result["tracks_matched"] == 1
    assert result["tracks_updated"] == 0
    assert result["missing_files"] == [
        {
            "track_id": track_id,
            "path": (new_root / "Artist" / "track.wav").as_posix(),
        }
    ]
    assert db.get_track(track_id).path == old_file.as_posix()
    assert db.get_track(track_id).bpm == 128.0


def test_relocate_library_apply_updates_paths_without_losing_analysis(tmp_path: Path) -> None:
    old_root = tmp_path / "ssd_music"
    new_root = tmp_path / "archive_music"
    old_root.mkdir()
    new_root.mkdir()
    old_file = old_root / "Artist" / "track.wav"
    new_file = new_root / "Artist" / "track.wav"
    old_file.parent.mkdir()
    new_file.parent.mkdir()
    old_file.write_bytes(b"audio")
    new_file.write_bytes(b"audio")

    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = db.upsert_track(path=old_file, size=old_file.stat().st_size, mtime=old_file.stat().st_mtime)
    db.save_sonara_features(track_id, {"tempo": 128}, bpm=128.0, model_name="sonara-test")

    result = db.relocate_library(old_root, new_root, apply=True)

    assert result["dry_run"] is False
    assert result["tracks_matched"] == 1
    assert result["tracks_updated"] == 1
    assert result["missing_files"] == []
    track = db.get_track(track_id)
    assert track.path == new_file.as_posix()
    assert track.bpm == 128.0


def test_relocate_library_apply_rejects_path_conflicts(tmp_path: Path) -> None:
    old_root = tmp_path / "ssd_music"
    new_root = tmp_path / "archive_music"
    old_root.mkdir()
    new_root.mkdir()
    old_file = old_root / "track.wav"
    new_file = new_root / "track.wav"
    old_file.write_bytes(b"old")
    new_file.write_bytes(b"new")

    db = LibraryDatabase(tmp_path / "library.sqlite")
    old_track_id = db.upsert_track(path=old_file, size=old_file.stat().st_size, mtime=old_file.stat().st_mtime)
    existing_track_id = db.upsert_track(path=new_file, size=new_file.stat().st_size, mtime=new_file.stat().st_mtime)

    result = db.relocate_library(old_root, new_root, apply=False)

    assert result["conflicts"] == [
        {
            "track_id": old_track_id,
            "old_path": old_file.as_posix(),
            "new_path": new_file.as_posix(),
            "existing_track_id": existing_track_id,
        }
    ]
    try:
        db.relocate_library(old_root, new_root, apply=True)
    except ValueError as error:
        assert "conflict" in str(error).lower()
    else:
        raise AssertionError("relocate_library should reject conflicting paths")
    assert db.get_track(old_track_id).path == old_file.as_posix()


def _analysis_flag_row(db: LibraryDatabase, track_id: int) -> dict[str, int]:
    with db.connect() as connection:
        row = connection.execute(
            """
            SELECT has_sonara_analysis, has_maest_embedding, has_mert_embedding, has_muq_embedding, has_clap_embedding
            FROM tracks
            WHERE id = ?
            """,
            (track_id,),
        ).fetchone()
    return {key: int(row[key]) for key in row.keys()}
