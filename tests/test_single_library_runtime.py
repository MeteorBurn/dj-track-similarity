from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

import numpy as np

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_analysis_candidates import collect_analysis_candidates
from dj_track_similarity.db_embeddings import (
    read_valid_embeddings,
    write_valid_embedding_in_transaction,
)
from dj_track_similarity.scanner import scan_library
from dj_track_similarity.track_models import TrackIdentity


def _write_embedding(
    database: LibraryDatabase,
    *,
    track: TrackIdentity,
    family: str,
    vector: np.ndarray,
    analyzed_at: str,
) -> None:
    with closing(database.connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        write_valid_embedding_in_transaction(
            connection=connection,
            track=track,
            family=family,
            embedding=vector,
            analyzed_at=analyzed_at,
        )
        connection.commit()


def _read_embedding(
    database: LibraryDatabase,
    *,
    track: TrackIdentity,
    family: str,
) -> np.ndarray | None:
    with closing(database.connect()) as connection:
        return read_valid_embeddings(
            family=family,
            identities={track.track_id: track.track_uuid},
            catalog_uuid=track.catalog_uuid,
            connection=connection,
        ).get(track.track_id)


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
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "track-a",
                    (tmp_path / "track-a.wav").as_posix(),
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
    )

    _write_embedding(
        database,
        track=target,
        family="mert",
        vector=vector,
        analyzed_at="2026-08-12T00:00:00.000000Z",
    )

    stored = _read_embedding(database, track=target, family="mert")
    assert stored is not None
    assert np.array_equal(stored, vector)
    with closing(database.connect()) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0]
            == 1
        )


def test_sonara_embedding_table_uses_the_fixed_unversioned_48d_format(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    with closing(database.connect()) as connection, connection:
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks(
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "track-sonara-48d",
                    (tmp_path / "track-sonara-48d.wav").as_posix(),
                    1,
                    1,
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                ),
            ).lastrowid
        )
    target = TrackIdentity(database.catalog_uuid, track_id, "track-sonara-48d")
    vector = np.linspace(-1.0, 1.0, 48, dtype=np.float32)
    analyzed_at = "2026-08-12T00:00:00.000000Z"

    _write_embedding(
        database,
        track=target,
        family="sonara",
        vector=vector,
        analyzed_at=analyzed_at,
    )

    with closing(database.connect()) as connection:
        columns = [
            row["name"]
            for row in connection.execute("PRAGMA table_info(sonara_embeddings)")
        ]
        row = connection.execute(
            """
            SELECT track_id, track_uuid, dim, normalization,
                   length(embedding_blob) AS blob_size, analyzed_at
            FROM sonara_embeddings
            WHERE track_id = ?
            """,
            (track_id,),
        ).fetchone()

    assert columns == [
        "track_id",
        "track_uuid",
        "dim",
        "normalization",
        "embedding_blob",
        "analyzed_at",
    ]
    assert row is not None
    assert dict(row) == {
        "track_id": track_id,
        "track_uuid": "track-sonara-48d",
        "dim": 48,
        "normalization": "none",
        "blob_size": 48 * 4,
        "analyzed_at": analyzed_at,
    }


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
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "track-b",
                    (tmp_path / "track-b.wav").as_posix(),
                    1,
                    1,
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                ),
            ).lastrowid
        )
    target = TrackIdentity(database.catalog_uuid, track_id, "track-b")
    output = AnalysisOutput("mert", "embedding")
    assert [
        candidate.target for candidate in database.list_analysis_candidates((output,))
    ] == [
        AnalysisTarget(
            catalog_uuid=target.catalog_uuid,
            track_id=target.track_id,
            track_uuid=target.track_uuid,
        )
    ]
    vector = np.zeros(768, dtype=np.float32)
    vector[0] = 1.0
    _write_embedding(
        database,
        track=target,
        family="mert",
        vector=vector,
        analyzed_at="2026-08-12T00:00:00.000000Z",
    )

    assert database.list_analysis_candidates((output,)) == []


def test_stored_embedding_readiness_does_not_read_payload(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    with closing(database.connect()) as connection, connection:
        track_id = int(
            connection.execute(
                """
                INSERT INTO tracks(
                    track_uuid, file_path, file_size_bytes, file_modified_ns,
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "track-readiness",
                    (tmp_path / "track-readiness.wav").as_posix(),
                    1,
                    1,
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                    "2026-08-12T00:00:00.000000Z",
                ),
            ).lastrowid
        )
    target = TrackIdentity(database.catalog_uuid, track_id, "track-readiness")
    vector = np.zeros(768, dtype=np.float32)
    vector[0] = 1.0
    _write_embedding(
        database,
        track=target,
        family="mert",
        vector=vector,
        analyzed_at="2026-08-12T00:00:00.000000Z",
    )

    with closing(database.connect()) as connection:
        def authorizer(
            action: int,
            _arg1: str | None,
            arg2: str | None,
            _database_name: str | None,
            _trigger_name: str | None,
        ) -> int:
            if action == sqlite3.SQLITE_READ and arg2 == "embedding_blob":
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorizer)
        candidates = collect_analysis_candidates(
            connection=connection,
            catalog_uuid=database.catalog_uuid,
            outputs=(AnalysisOutput("mert", "embedding"),),
            limit=None,
        )

    assert candidates == []


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
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "track-summary",
                    (tmp_path / "track-summary.wav").as_posix(),
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
                track_id, track_uuid, dim, normalization, embedding_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                track_id,
                "track-summary",
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
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "track-c",
                    (tmp_path / "track-c.wav").as_posix(),
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
    _write_embedding(
        database,
        track=TrackIdentity(database.catalog_uuid, track_id, "track-c"),
        family="mert",
        vector=vector,
        analyzed_at="2026-08-12T00:00:00.000000Z",
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
