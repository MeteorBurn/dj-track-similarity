from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path
import zipfile

import numpy as np


def _load_dedup_module():
    path = Path(__file__).resolve().parents[1] / "audio_dedup" / "audio_dedup.py"
    spec = importlib.util.spec_from_file_location("audio_dedup", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _create_library_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY,
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
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE embeddings (
                track_id INTEGER NOT NULL,
                embedding_key TEXT NOT NULL,
                model_name TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector BLOB NOT NULL,
                PRIMARY KEY(track_id, embedding_key)
            );
            """
        )


def _create_rhythm_lab_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE classifier_labels (
                classifier_key TEXT NOT NULL,
                source_track_id INTEGER NOT NULL,
                path TEXT,
                size INTEGER,
                mtime REAL,
                label TEXT NOT NULL,
                note TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(classifier_key, source_track_id)
            );

            CREATE TABLE classifier_predictions (
                classifier_key TEXT NOT NULL,
                source_track_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                artist TEXT,
                title TEXT,
                feature_set TEXT NOT NULL,
                model_artifact TEXT NOT NULL,
                label TEXT NOT NULL,
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(classifier_key, source_track_id, feature_set, model_artifact)
            );

            CREATE TABLE classifier_training_checkpoints (
                classifier_key TEXT PRIMARY KEY,
                counts_json TEXT NOT NULL
            );
            """
        )


def _insert_track(
    db_path: Path,
    *,
    track_id: int,
    path: str,
    size: int = 10_000_000,
    mtime: float = 100.0,
    artist: str = "Artist",
    title: str = "Title",
    album: str | None = "Album",
    bpm: float | None = 128.0,
    musical_key: str | None = "8A",
    duration: float = 300.0,
    sonara: dict[str, object] | None = None,
    vectors: dict[str, list[float]] | None = None,
) -> None:
    metadata = {"duration": duration}
    if sonara is not None:
        metadata["sonara_features"] = sonara
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            INSERT INTO tracks(id, path, size, mtime, artist, title, album, bpm, musical_key, energy, duration, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                path,
                size,
                mtime,
                artist,
                title,
                album,
                bpm,
                musical_key,
                0.7,
                duration,
                json.dumps(metadata),
            ),
        )
        for key, values in (vectors or {}).items():
            vector = np.asarray(values, dtype=np.float32)
            vector = vector / np.linalg.norm(vector)
            connection.execute(
                """
                INSERT INTO embeddings(track_id, embedding_key, model_name, dim, vector)
                VALUES (?, ?, ?, ?, ?)
                """,
                (track_id, key, f"{key}-test", int(vector.shape[0]), vector.tobytes()),
            )


def test_root_filter_selects_only_tracks_inside_root(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(db_path, track_id=1, path="M:/Volumes/Abstracted/A/one.flac")
    _insert_track(db_path, track_id=2, path="M:/Volumes/Abstractedness/A/two.flac")
    _insert_track(db_path, track_id=3, path="N:/Volumes/Abstracted/A/three.flac")

    tracks = dedup.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[])

    assert [track.track_id for track in tracks] == [1]


def test_path_contains_additionally_filters_inside_root(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(db_path, track_id=1, path="M:/Volumes/Abstracted/Keep/one.flac")
    _insert_track(db_path, track_id=2, path="M:/Volumes/Abstracted/Other/two.flac")

    tracks = dedup.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=["keep"])

    assert [track.track_id for track in tracks] == [1]


def test_min_score_overrides_preset_threshold() -> None:
    dedup = _load_dedup_module()

    config = dedup.resolve_preset("safe", min_score=0.91)

    assert config.name == "safe"
    assert config.min_score == 0.91


def test_report_only_main_does_not_delete_files_or_mutate_database(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    first_path = audio_dir / "first.flac"
    second_path = audio_dir / "second.mp3"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    _create_library_db(db_path)
    vectors = {"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(first_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(second_path), size=8_000_000, mtime=200, vectors=vectors)

    exit_code = dedup.main(["--db", str(db_path), "--root", str(audio_dir), "--out-dir", str(out_dir)])

    assert exit_code == 0
    assert first_path.exists()
    assert second_path.exists()
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 2
    finally:
        connection.close()
    db_path.rename(tmp_path / "library-renamed.sqlite")
    report_paths = sorted(out_dir.glob("audio_dedup_report_*.json"))
    assert len(report_paths) == 1
    payload = json.loads(report_paths[0].read_text(encoding="utf-8"))
    assert payload["mode"] == "report-only"
    assert payload["groups"][0]["suggested_keeper"]["track_id"] == 1
    assert payload["groups"][0]["candidate_deletes"][0]["track_id"] == 2
    assert payload["groups"][0]["candidate_deletes"][0]["safe_to_delete"] == "true_candidate"


def test_keeper_selection_prefers_lossless_then_bitrate_proxy() -> None:
    dedup = _load_dedup_module()
    low_bitrate_flac = dedup.TrackRecord(
        track_id=1,
        path="M:/Volumes/Abstracted/a.flac",
        size=10_000_000,
        mtime=100.0,
        artist="A",
        title="T",
        album="Album",
        bpm=128.0,
        musical_key="8A",
        duration=300.0,
        metadata={},
        embeddings={},
    )
    high_bitrate_flac = dedup.TrackRecord(
        track_id=2,
        path="M:/Volumes/Abstracted/b.flac",
        size=20_000_000,
        mtime=50.0,
        artist="A",
        title="T",
        album="Album",
        bpm=128.0,
        musical_key="8A",
        duration=300.0,
        metadata={},
        embeddings={},
    )
    mp3 = dedup.TrackRecord(
        track_id=3,
        path="M:/Volumes/Abstracted/c.mp3",
        size=30_000_000,
        mtime=300.0,
        artist="A",
        title="T",
        album="Album",
        bpm=128.0,
        musical_key="8A",
        duration=300.0,
        metadata={},
        embeddings={},
    )

    assert dedup.choose_keeper([low_bitrate_flac, high_bitrate_flac, mp3]).track_id == 2


def test_ambiguous_chain_group_is_report_only(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    _create_library_db(db_path)
    _insert_track(
        db_path,
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        vectors={"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]},
    )
    _insert_track(
        db_path,
        track_id=2,
        path="M:/Volumes/Abstracted/two.flac",
        vectors={"mert": [0.96, 0.28, 0.0], "maest": [0.96, 0.28, 0.0]},
    )
    _insert_track(
        db_path,
        track_id=3,
        path="M:/Volumes/Abstracted/three.flac",
        vectors={"mert": [0.84, 0.5425864, 0.0], "maest": [0.84, 0.5425864, 0.0]},
    )

    tracks = dedup.load_tracks(db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[])
    groups = dedup.find_duplicate_groups(tracks, dedup.resolve_preset("safe", min_score=0.925), limit_groups=None)
    payload = dedup.build_report(groups, tracks, dedup.resolve_preset("safe", min_score=0.925), root=Path("M:/Volumes/Abstracted"), path_contains=[])

    group = payload["groups"][0]
    assert {track["track_id"] for track in group["candidate_deletes"]} == {2, 3}
    assert all(track["safe_to_delete"] == "false" for track in group["candidate_deletes"])
    assert "ambiguous chain" in " ".join(group["blocked_reasons"])


def test_tag_bpm_and_key_are_not_used_for_duplicate_scoring() -> None:
    dedup = _load_dedup_module()
    config = dedup.resolve_preset("safe", min_score=None)
    sonara = {"bpm": 128.0, "energy": 0.7, "onset_density": 0.4}
    left = dedup.TrackRecord(
        track_id=1,
        path="M:/Volumes/Abstracted/one.flac",
        size=20_000_000,
        mtime=100.0,
        artist="A",
        title="T",
        album="Album",
        bpm=90.0,
        musical_key="1A",
        duration=300.0,
        metadata={"sonara_features": sonara},
        embeddings={},
    )
    right = dedup.TrackRecord(
        track_id=2,
        path="M:/Volumes/Abstracted/two.flac",
        size=20_000_000,
        mtime=100.0,
        artist="A",
        title="T",
        album="Album",
        bpm=180.0,
        musical_key="12B",
        duration=300.0,
        metadata={"sonara_features": sonara},
        embeddings={},
    )

    evidence = dedup.score_pair(left, right, config)

    assert evidence.sonara_similarity == 1.0
    assert not hasattr(evidence, "bpm_diff")
    assert not hasattr(evidence, "key_match")


def test_json_and_xlsx_reports_include_candidate_evidence(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    _create_library_db(db_path)
    vectors = {
        "mert": [1.0, 0.0, 0.0],
        "maest": [1.0, 0.0, 0.0],
        "clap": [1.0, 0.0, 0.0],
    }
    sonara = {"bpm": 128.0, "danceability": 0.8, "energy": 0.7, "valence": 0.5}
    _insert_track(db_path, track_id=1, path="M:/Volumes/Abstracted/one.flac", size=20_000_000, sonara=sonara, vectors=vectors)
    _insert_track(db_path, track_id=2, path="M:/Volumes/Abstracted/two.mp3", size=8_000_000, sonara=sonara, vectors=vectors)
    _insert_track(db_path, track_id=3, path="N:/Volumes/Other/three.flac", size=20_000_000, sonara=sonara, vectors=vectors)

    result = dedup.run_report(db_path=db_path, root=Path("M:/Volumes/Abstracted"), path_contains=[], preset_name="safe", min_score=None, limit_groups=None, out_dir=out_dir)

    json_payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert json_payload["database_path"] == str(db_path.resolve())
    assert json_payload["database_track_count"] == 3
    assert json_payload["scoped_track_count"] == 2
    assert json_payload["track_count"] == 2
    assert "mert_similarity" in json_payload["groups"][0]["pairwise_evidence"][0]
    assert "keeper_reasons" in json_payload["groups"][0]["suggested_keeper"]
    assert json_payload["groups"][0]["suggested_keeper"]["role"] == "KEEP"
    assert json_payload["groups"][0]["candidate_deletes"][0]["role"] == "DUPLICATE"
    assert json_payload["groups"][0]["candidate_deletes"][0]["decision"] == "delete_candidate"
    assert json_payload["groups"][0]["candidate_deletes"][0]["why_delete_or_review"]
    assert result.xlsx_path.exists()
    assert not result.xlsx_path.with_suffix(".csv").exists()
    with zipfile.ZipFile(result.xlsx_path) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        summary_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        candidates_xml = archive.read("xl/worksheets/sheet3.xml").decode("utf-8")
    assert "Summary" in workbook_xml
    assert "Candidates" in workbook_xml
    assert "DELETE CANDIDATE" in candidates_xml
    assert "one.flac" in candidates_xml
    assert "mert_similarity" in candidates_xml
    assert "Duplicate audio summary" in summary_xml
    assert str(db_path.resolve()) in summary_xml
    assert "Total tracks in database" in summary_xml
    assert "Tracks inside selected root" in summary_xml
    assert not list(out_dir.glob("audio_dedup_report_*.png"))


def test_apply_duplicate_deletions_removes_only_safe_temp_files_and_database_rows(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    _create_library_db(db_path)
    vectors = {"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, vectors=vectors)
    result = dedup.run_report(
        db_path=db_path,
        root=audio_dir,
        path_contains=[],
        preset_name="safe",
        min_score=None,
        limit_groups=None,
        out_dir=out_dir,
    )

    apply_result = dedup.apply_duplicate_deletions(db_path=db_path, root=audio_dir, payload=result.payload)

    assert keeper_path.exists()
    assert not duplicate_path.exists()
    assert apply_result.deleted_track_ids == (2,)
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute("SELECT id FROM tracks ORDER BY id").fetchall() == [(1,)]
        assert connection.execute("SELECT track_id FROM embeddings ORDER BY track_id").fetchall() == [(1,), (1,)]
    finally:
        connection.close()


def test_apply_duplicate_deletions_removes_deleted_tracks_from_rhythm_lab_database(tmp_path: Path) -> None:
    dedup = _load_dedup_module()
    db_path = tmp_path / "library.sqlite"
    rhythm_lab_db = tmp_path / "rhythm_lab.sqlite"
    out_dir = tmp_path / "reports"
    audio_dir = tmp_path / "Abstracted"
    audio_dir.mkdir()
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.mp3"
    keeper_path.write_bytes(b"keeper")
    duplicate_path.write_bytes(b"duplicate")
    _create_library_db(db_path)
    _create_rhythm_lab_db(rhythm_lab_db)
    vectors = {"mert": [1.0, 0.0, 0.0], "maest": [1.0, 0.0, 0.0]}
    _insert_track(db_path, track_id=1, path=str(keeper_path), size=20_000_000, mtime=100, vectors=vectors)
    _insert_track(db_path, track_id=2, path=str(duplicate_path), size=8_000_000, mtime=200, vectors=vectors)
    with sqlite3.connect(rhythm_lab_db) as connection:
        connection.executemany(
            """
            INSERT INTO classifier_labels(classifier_key, source_track_id, path, size, mtime, label)
            VALUES ('break_energy', ?, ?, 1, 1, 'broken')
            """,
            [(1, str(keeper_path)), (2, str(duplicate_path))],
        )
        connection.executemany(
            """
            INSERT INTO classifier_predictions(
                classifier_key, source_track_id, path, feature_set, model_artifact,
                label, confidence, probabilities_json
            )
            VALUES ('break_energy', ?, ?, 'combined', 'model.joblib', 'broken', 0.9, '{}')
            """,
            [(1, str(keeper_path)), (2, str(duplicate_path))],
        )
        connection.execute(
            "INSERT INTO classifier_training_checkpoints(classifier_key, counts_json) VALUES ('break_energy', '{}')"
        )
    result = dedup.run_report(
        db_path=db_path,
        root=audio_dir,
        path_contains=[],
        preset_name="safe",
        min_score=None,
        limit_groups=None,
        out_dir=out_dir,
    )

    apply_result = dedup.apply_duplicate_deletions(
        db_path=db_path,
        root=audio_dir,
        payload=result.payload,
        rhythm_lab_db=rhythm_lab_db,
    )

    assert apply_result.rhythm_lab_deleted_rows == 2
    with sqlite3.connect(rhythm_lab_db) as connection:
        assert connection.execute("SELECT source_track_id FROM classifier_labels").fetchall() == [(1,)]
        assert connection.execute("SELECT source_track_id FROM classifier_predictions").fetchall() == [(1,)]
        assert connection.execute("SELECT classifier_key FROM classifier_training_checkpoints").fetchall() == [("break_energy",)]
