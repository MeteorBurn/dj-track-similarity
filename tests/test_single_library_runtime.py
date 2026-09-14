from __future__ import annotations

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.analysis_candidates import collect_analysis_candidates
from dj_track_similarity.db.embeddings import (
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

    with closing(database.connect()) as connection, connection:
        connection.execute("DROP TABLE mert_v2_embeddings")
        connection.execute(
            "CREATE TABLE mert_v2_embeddings (track_id INTEGER PRIMARY KEY, "
            "track_uuid TEXT, dim INTEGER, normalization TEXT, embedding_blob BLOB, "
            "analyzed_at TEXT)"
        )
        old_schema = connection.execute(
            "SELECT name, sql FROM sqlite_schema ORDER BY name"
        ).fetchall()
    reopened = LibraryDatabase(database_path)
    assert reopened.mert_v2_layers_capability() == "incompatible"
    with pytest.raises(RuntimeError, match="incompatible"):
        reopened.load_analysis_vectors(AnalysisOutput("mert_v2", "embedding"))
    with closing(reopened.connect()) as connection:
        assert connection.execute(
            "SELECT name, sql FROM sqlite_schema ORDER BY name"
        ).fetchall() == old_schema


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
    target = TrackIdentity(
        catalog_uuid=database.catalog_uuid,
        track_id=track_id,
        track_uuid="track-a",
    )

    vectors = {
        "mert": np.eye(1, 768, dtype=np.float32)[0],
        "mert_v2": np.eye(1, 1024, 1, dtype=np.float32)[0],
    }
    for family, vector in vectors.items():
        _write_embedding(
            database,
            track=target,
            family=family,
            vector=vector,
            analyzed_at="2026-08-12T00:00:00.000000Z",
        )
        stored = _read_embedding(database, track=target, family=family)
        assert stored is not None
        assert np.array_equal(stored, vector)
        rows = database.load_analysis_vectors(AnalysisOutput(family, "embedding"))
        assert len(rows) == 1
        np.testing.assert_array_equal(rows[0].vector, vector)

    with pytest.raises(ValueError, match="does not match mert_v2 dimension 1024"):
        _write_embedding(
            database, track=target, family="mert_v2", vector=vectors["mert"],
            analyzed_at="2026-08-12T00:00:00.000000Z",
        )
    with pytest.raises(RuntimeError, match="stale embedding write rejected: track_uuid mismatch"):
        _write_embedding(
            database, track=TrackIdentity(database.catalog_uuid, track_id, "stale"),
            family="mert_v2", vector=vectors["mert_v2"],
            analyzed_at="2026-08-12T00:00:00.000000Z",
        )

    detail = database.get_track_detail(track_id)
    assert detail.analysis_coverage.mert and detail.analysis_coverage.mert_v2
    assert {(row.analysis_family, row.dim) for row in detail.embeddings} == {
        ("mert", 768), ("mert_v2", 1024),
    }
    with closing(database.connect()) as connection:
        row = connection.execute(
            "SELECT layer, dim, normalization, length(embedding_blob) FROM mert_v2_embeddings"
        ).fetchone()
        assert tuple(row) == (24, 1024, "l2", 4096)
        assert [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE 'mert_v2%'")
        ] == ["mert_v2_embeddings"]
        assert {row[1]: row[5] for row in connection.execute(
            "PRAGMA table_info(mert_v2_embeddings)") if row[5]
        } == {"track_id": 1, "layer": 2}
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    output = AnalysisOutput("mert_v2", "embedding")
    assert database.mert_v2_layer_counts() == {**dict.fromkeys(range(1, 24), 0), 24: 1}
    layers = tuple(np.eye(1, 1024, layer, dtype=np.float32)[0] for layer in range(23))
    layers = (*layers, vectors["mert_v2"])
    write = EmbeddingWrite(
        AnalysisTarget(target.catalog_uuid, track_id, target.track_uuid),
        EmbeddingOutput("mert_v2", layers[-1], "2026-08-13T00:00:00.000000Z", layers),
    )
    assert database.save_embedding_results((write,))[0].ok
    assert database.mert_v2_layer_counts() == dict.fromkeys(range(1, 25), 1)
    for layer in range(1, 25):
        rows = database.load_analysis_vectors(output, mert_v2_layer=layer)
        np.testing.assert_array_equal(rows[0].vector, layers[layer - 1])
        assert database.random_embedding_target(output, mert_v2_layer=layer) == write.target
    assert len(database.load_analysis_vectors(output)) == 1
    detail = database.get_track_detail(track_id)
    assert sum(row.analysis_family == "mert_v2" for row in detail.embeddings) == 1
    with closing(database.connect()) as connection:
        assert [(row[0], row[1]) for row in connection.execute(
            "SELECT layer, embedding_blob FROM mert_v2_embeddings ORDER BY layer"
        )] == [(layer, vector.tobytes()) for layer, vector in enumerate(layers, start=1)]
    with pytest.raises(ValueError, match="24 MERT-v2"):
        EmbeddingOutput("mert_v2", layers[-1], "now", layers[:-1])
    with pytest.raises(ValueError, match="layer 24 must equal the primary embedding"):
        EmbeddingOutput("mert_v2", layers[0], "now", layers)
    with pytest.raises(ValueError, match="from 1 to 24"):
        database.load_analysis_vectors(output, mert_v2_layer=0)
    with pytest.raises(ValueError, match="only supported for MERT-v2"):
        database.load_analysis_vectors(AnalysisOutput("mert", "embedding"), mert_v2_layer=12)
    with closing(database.connect()) as connection, connection:
        connection.execute(
            "UPDATE mert_v2_embeddings SET track_uuid='stale' WHERE layer=12"
        )
    assert database.load_analysis_vectors(output, mert_v2_layer=12) == ()
    assert database.save_embedding_results((write,))[0].ok
    with closing(database.connect()) as connection, connection:
        connection.execute(
            "CREATE TRIGGER fail_layer BEFORE INSERT ON mert_v2_embeddings "
            "WHEN NEW.layer=13 BEGIN SELECT RAISE(ABORT, 'test rollback'); END"
        )
    replacement = EmbeddingWrite(
        write.target, EmbeddingOutput("mert_v2", layers[0], "new", (layers[0],) * 24),
    )
    assert not database.save_embedding_results((replacement,))[0].ok
    for layer in (1, 13, 24):
        np.testing.assert_array_equal(
            database.load_analysis_vectors(output, mert_v2_layer=layer)[0].vector,
            layers[layer - 1],
        )
    with closing(database.connect()) as connection, connection:
        connection.execute("DROP TRIGGER fail_layer")

    final_only = EmbeddingWrite(
        write.target, EmbeddingOutput("mert_v2", layers[0], "final-only"),
    )
    assert database.save_embedding_results((final_only,))[0].ok
    assert database.mert_v2_layer_counts() == {**dict.fromkeys(range(1, 24), 0), 24: 1}
    np.testing.assert_array_equal(database.load_analysis_vectors(output)[0].vector, layers[0])
    with closing(database.connect()) as connection:
        assert connection.execute("SELECT layer FROM mert_v2_embeddings").fetchall()[0][0] == 24
        assert connection.execute("SELECT COUNT(*) FROM mert_v2_embeddings").fetchone()[0] == 1
    assert database.save_embedding_results((write,))[0].ok

    reset = database.reset_analysis_outputs((AnalysisOutput("mert_v2", "embedding"),))
    assert reset.embedding_rows_deleted == 1
    assert database.load_analysis_vectors(AnalysisOutput("mert_v2", "embedding")) == ()
    assert database.mert_v2_layer_counts() == dict.fromkeys(range(1, 25), 0)
    np.testing.assert_array_equal(
        _read_embedding(database, track=target, family="mert"), vectors["mert"],
    )
    _write_embedding(
        database, track=target, family="mert_v2", vector=vectors["mert_v2"],
        analyzed_at="2026-08-12T00:00:00.000000Z",
    )
    assert database.save_embedding_results((write,))[0].ok
    cleared = database.clear_library()
    assert cleared["tracks_deleted"] == 1
    assert cleared["embedding_rows_deleted"] == 2
    with closing(database.connect()) as connection:
        assert connection.execute("SELECT COUNT(*) FROM mert_v2_embeddings").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


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
    outputs = (AnalysisOutput("mert", "embedding"), AnalysisOutput("mert_v2", "embedding"))
    assert [
        candidate.target for candidate in database.list_analysis_candidates(outputs)
    ] == [
        AnalysisTarget(
            catalog_uuid=target.catalog_uuid,
            track_id=target.track_id,
            track_uuid=target.track_uuid,
        )
    ]
    for index, (family, dimension) in enumerate((("mert", 768), ("mert_v2", 1024))):
        vector = np.zeros(dimension, dtype=np.float32)
        vector[0] = 1.0
        _write_embedding(
            database,
            track=target,
            family=family,
            vector=vector,
            analyzed_at="2026-08-12T00:00:00.000000Z",
        )
        candidates = database.list_analysis_candidates(outputs)
        if index == 0:
            assert len(candidates) == 1
            assert candidates[0].missing_outputs == (outputs[1],)
        else:
            assert len(candidates) == 1
            assert candidates[0].missing_outputs == (outputs[1],)
            result = database.save_embedding_results((EmbeddingWrite(
                AnalysisTarget(target.catalog_uuid, target.track_id, target.track_uuid),
                EmbeddingOutput("mert_v2", vector, "now", (vector,) * 24),
            ),))
            assert result[0].ok
            candidates = database.list_analysis_candidates(outputs)
            assert candidates == []
            for layer in (13, 24):
                with closing(database.connect()) as connection, connection:
                    connection.execute(
                        "UPDATE mert_v2_embeddings SET analyzed_at='old' WHERE layer=?",
                        (layer,),
                    )
                candidates = database.list_analysis_candidates(outputs)
                assert len(candidates) == 1
                assert candidates[0].missing_outputs == (outputs[1],)
                with closing(database.connect()) as connection, connection:
                    connection.execute(
                        "UPDATE mert_v2_embeddings SET analyzed_at='now' WHERE layer=?",
                        (layer,),
                    )


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
    for family, dimension in (("mert", 768), ("mert_v2", 1024)):
        vector = np.zeros(dimension, dtype=np.float32)
        vector[0] = 1.0
        _write_embedding(
            database,
            track=target,
            family=family,
            vector=vector,
            analyzed_at="2026-08-12T00:00:00.000000Z",
        )

    result = database.save_embedding_results((EmbeddingWrite(
        AnalysisTarget(target.catalog_uuid, target.track_id, target.track_uuid),
        EmbeddingOutput("mert_v2", vector, "now", (vector,) * 24),
    ),))
    assert result[0].ok

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
            outputs=(AnalysisOutput("mert", "embedding"), AnalysisOutput("mert_v2", "embedding")),
            limit=None,
        )

    assert candidates == []


def test_library_summary_counts_embedding_rows_directly(tmp_path: Path) -> None:
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
        for family, dimension in (("mert", 768), ("mert_v2", 1024)):
            vector = np.zeros(dimension, dtype="<f4")
            vector[0] = 2.0
            layer_column = ", layer" if family == "mert_v2" else ""
            layer_value = ", ?" if family == "mert_v2" else ""
            values = (
                track_id,
                "track-summary",
                dimension,
                "l2",
                vector.tobytes(),
                "2026-08-12T00:00:00.000000Z",
            )
            connection.executemany(
                f"""
                INSERT INTO {family}_embeddings(
                    track_id, track_uuid, dim, normalization, embedding_blob, analyzed_at{layer_column}
                ) VALUES (?, ?, ?, ?, ?, ?{layer_value})
                """,
                [(*values, layer) for layer in range(1, 25)]
                if family == "mert_v2" else [values],
            )

    summary = database.library_summary()

    assert summary.tracks == 1
    assert summary.mert == 1
    assert summary.mert_v2 == 1


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
