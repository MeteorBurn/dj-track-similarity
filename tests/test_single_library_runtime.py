from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sys

import numpy as np

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.scanner import scan_library
from dj_track_similarity.track_models import TrackIdentity


def test_new_library_database_bootstraps_one_sqlite_file(tmp_path: Path) -> None:
    database_path = tmp_path / "library.sqlite"

    database = LibraryDatabase(database_path)

    assert database.path == database_path.resolve()
    assert database_path.is_file()
    with closing(database.connect()) as connection:
        library = connection.execute(
            """
            SELECT catalog_uuid, schema_version, roots_json
            FROM library
            WHERE singleton_id = 1
            """
        ).fetchone()
        assert library is not None
        assert str(library[0]) == database.catalog_uuid
        assert int(library[1]) == 1
        assert json.loads(str(library[2])) == []
        connection.execute("SELECT * FROM sonara_features LIMIT 0")
        connection.execute("SELECT * FROM maest_embeddings LIMIT 0")


def test_library_records_each_scanned_root_once(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    first_root = tmp_path / "music-a"
    second_root = tmp_path / "music-b"
    first_root.mkdir()
    second_root.mkdir()

    assert database.record_library_root(first_root) == (first_root.as_posix(),)
    assert database.record_library_root(second_root) == (
        first_root.as_posix(),
        second_root.as_posix(),
    )
    assert database.record_library_root(first_root) == (
        first_root.as_posix(),
        second_root.as_posix(),
    )
    with closing(database.connect()) as connection:
        roots_json = connection.execute(
            "SELECT roots_json FROM library WHERE singleton_id = 1"
        ).fetchone()[0]
    assert json.loads(str(roots_json)) == [
        first_root.as_posix(),
        second_root.as_posix(),
    ]


def test_scan_records_the_selected_root(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    music_root = tmp_path / "music"
    music_root.mkdir()

    scan_library(database, music_root)

    with closing(database.connect()) as connection:
        roots_json = connection.execute(
            "SELECT roots_json FROM library WHERE singleton_id = 1"
        ).fetchone()[0]
    assert json.loads(str(roots_json)) == [music_root.as_posix()]


def test_embedding_round_trip_uses_the_library_connection(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    with closing(database.connect()) as connection, connection:
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks(
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    content_generation, last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "track-a",
                    (tmp_path / "track-a.wav").as_posix(),
                    1,
                    1,
                    1,
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                ),
            ).lastrowid
        )
    vector = np.zeros(768, dtype=np.float32)
    vector[0] = 1.0
    target = TrackIdentity(
        catalog_uuid=database.catalog_uuid,
        track_id=track_id,
        track_uuid="track-a",
        content_generation=1,
    )

    database.write_embedding(
        track=target,
        output=EmbeddingOutput(
            family="mert",
            vector=vector,
            analyzed_at="2026-08-12T00:00:00.000000Z",
        ),
    )

    stored = database.read_embedding(family="mert", track_id=track_id)
    assert stored is not None
    assert np.array_equal(stored, vector)
    with closing(database.connect()) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0]
            == 1
        )


def test_current_embedding_removes_track_from_its_analysis_candidates(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    with closing(database.connect()) as connection, connection:
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks(
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    content_generation, last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "track-b",
                    (tmp_path / "track-b.wav").as_posix(),
                    1,
                    1,
                    1,
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                ),
            ).lastrowid
        )
    target = TrackIdentity(database.catalog_uuid, track_id, "track-b", 1)
    output = AnalysisOutput("mert", "embedding")
    assert [
        candidate.target for candidate in database.list_analysis_candidates((output,))
    ] == [
        AnalysisTarget(
            catalog_uuid=target.catalog_uuid,
            track_id=target.track_id,
            track_uuid=target.track_uuid,
            content_generation=target.content_generation,
        )
    ]
    vector = np.zeros(768, dtype=np.float32)
    vector[0] = 1.0
    database.write_embedding(
        track=target,
        output=EmbeddingOutput(
            family="mert",
            vector=vector,
            analyzed_at="2026-08-12T00:00:00.000000Z",
        ),
    )

    assert database.list_analysis_candidates((output,)) == []


def test_library_summary_counts_embedding_rows_directly(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    vector = np.zeros(768, dtype="<f4")
    vector[0] = 2.0
    with closing(database.connect()) as connection, connection:
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks(
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    content_generation, last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "track-summary",
                    (tmp_path / "track-summary.wav").as_posix(),
                    1,
                    1,
                    1,
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                ),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO mert_embeddings(
                track_id, track_uuid, content_generation,
                dim, normalization, embedding_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                "track-summary",
                1,
                768,
                "l2",
                vector.tobytes(),
                "2026-08-12T00:00:00.000000Z",
            ),
        )

    summary = database.library_summary()

    assert summary.tracks == 1
    assert summary.mert == 1


def test_rhythm_lab_reads_embeddings_from_the_library_database(
    tmp_path: Path,
) -> None:
    lab_root = Path(__file__).resolve().parents[1] / "tools" / "rhythm-lab"
    sys.path.insert(0, str(lab_root))
    try:
        from rhythm_lab.source_db import SourceDatabase
    finally:
        sys.path.remove(str(lab_root))

    database = LibraryDatabase(tmp_path / "library.sqlite")
    with closing(database.connect()) as connection, connection:
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks(
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    content_generation, last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "track-c",
                    (tmp_path / "track-c.wav").as_posix(),
                    1,
                    1,
                    1,
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                ),
            ).lastrowid
        )
    vector = np.zeros(768, dtype=np.float32)
    vector[0] = 1.0
    database.write_embedding(
        track=TrackIdentity(database.catalog_uuid, track_id, "track-c", 1),
        output=EmbeddingOutput(
            family="mert",
            vector=vector,
            analyzed_at="2026-08-12T00:00:00.000000Z",
        ),
    )

    source = SourceDatabase(database.path)

    assert source.count_tracks() == 1
    assert source.count_embeddings("mert") == 1


def test_evaluation_profile_creates_the_optional_sidecar_on_save(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")

    assert database.connect_evaluation(create=False) is None
    assert not database.evaluation_path.exists()

    profile_id = database.save_evaluation_profile(
        "weighted-candidates",
        {"weights": {"mert": 1.0}},
    )

    assert profile_id == 1
    assert database.evaluation_path.is_file()
    stored = database.get_evaluation_profile("weighted-candidates")
    assert stored is not None
    assert stored["profile_id"] == 1
    assert stored["profile_name"] == "weighted-candidates"
    assert stored["profile"] == {"weights": {"mert": 1.0}}
    connection = database.connect_evaluation(create=False)
    assert connection is not None
    with closing(connection):
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "evaluation_profiles" in tables
