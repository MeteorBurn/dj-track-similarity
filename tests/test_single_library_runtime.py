from __future__ import annotations

import json
from contextlib import closing
from dataclasses import fields
from pathlib import Path
import sqlite3
import sys

import numpy as np
import pytest

from dj_track_similarity.analysis.sonara_features import analysis_outputs_for_sonara_runtime
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EMBEDDING_LAYERS,
    MAEST_EMBEDDING_DIM,
    EmbeddingOutput,
    EmbeddingWrite,
    MaestGenreScore,
    MaestWrite,
    current_embedding_spec,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.analysis_candidates import collect_analysis_candidates
from dj_track_similarity.db.ddl import SonaraRow
from dj_track_similarity.db.embeddings import (
    read_valid_embeddings,
    write_valid_embedding_in_transaction,
)
from dj_track_similarity.scanner import scan_library
from dj_track_similarity.track_models import TrackIdentity
from sonara_test_support import complete_sonara_write, save_sonara_writes


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


def _save_embedding_output(
    database: LibraryDatabase,
    target: AnalysisTarget,
    output: EmbeddingOutput,
) -> bool:
    """Save through the production writer: MAEST vectors travel with genres."""

    if output.family == "maest":
        result = database.save_maest_results((MaestWrite(
            target,
            genres=(MaestGenreScore("Electronic---House", 0.8),),
            syncopated_rhythm=False,
            analyzed_at=output.analyzed_at,
            embedding=output,
        ),))
    else:
        result = database.save_embedding_results((EmbeddingWrite(target, output),))
    return result[0].ok


def test_new_library_database_bootstraps_one_sqlite_file(tmp_path: Path) -> None:
    database_path = tmp_path / "library.sqlite"

    database = LibraryDatabase(database_path)

    assert database.path == database_path.resolve()
    assert [path.name for path in tmp_path.iterdir()] == ["library.sqlite"]
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
    assert {
        family: database.embedding_layers_capability(family) for family in EMBEDDING_LAYERS
    } == dict.fromkeys(EMBEDDING_LAYERS, "ready")

    # A single-vector table from before per-layer storage, or a missing
    # sonara_timeline table, is refused, never altered.
    gone_path = (tmp_path / "gone.wav").resolve().as_posix()
    with closing(database.connect()) as connection, connection:
        for family in EMBEDDING_LAYERS:
            connection.execute(f"DROP TABLE {family}_embeddings")
            connection.execute(
                f"CREATE TABLE {family}_embeddings (track_id INTEGER PRIMARY KEY, "
                "track_uuid TEXT, dim INTEGER, normalization TEXT, embedding_blob BLOB, "
                "analyzed_at TEXT)"
            )
        connection.execute("DROP TABLE sonara_timeline")
        track_id = int(connection.execute(
            "INSERT INTO tracks(track_uuid, file_path, file_size_bytes, file_modified_ns, "
            "last_scanned_at, created_at, updated_at) VALUES ('gone', ?, 1, 1, 'now', 'now', 'now')",
            (gone_path,),
        ).lastrowid)
        old_schema = connection.execute(
            "SELECT name, sql FROM sqlite_schema ORDER BY name"
        ).fetchall()
    reopened = LibraryDatabase(database_path)
    for family in EMBEDDING_LAYERS:
        assert reopened.embedding_layers_capability(family) == "incompatible"
        with pytest.raises(
            RuntimeError,
            match="incompatible; migrate this database with scripts/migrate_layered_embeddings.py",
        ):
            reopened.load_analysis_vectors(AnalysisOutput(family, "embedding"))
    identity = reopened.get_track_identity(track_id)
    assert identity is not None
    for refused in (
        lambda: reopened.reset_analysis_outputs(analysis_outputs_for_sonara_runtime()),
        reopened.clear_library,
        lambda: reopened.remove_deleted_track(expected=identity, file_path=gone_path),
    ):
        with pytest.raises(RuntimeError, match="no sonara_timeline table"):
            refused()
    with closing(reopened.connect()) as connection:
        assert connection.execute(
            "SELECT name, sql FROM sqlite_schema ORDER BY name"
        ).fetchall() == old_schema
        assert [row[0] for row in connection.execute("SELECT track_id FROM tracks")] == [track_id]


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
        "muq": np.eye(1, 1024, dtype=np.float32)[0],
        "mert_v2": np.eye(1, 1024, 1, dtype=np.float32)[0],
        "maest": np.eye(1, MAEST_EMBEDDING_DIM, 2, dtype=np.float32)[0],
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
            database, track=target, family="mert_v2", vector=np.zeros(512, dtype=np.float32),
            analyzed_at="2026-08-12T00:00:00.000000Z",
        )
    with pytest.raises(RuntimeError, match="stale embedding write rejected: track_uuid mismatch"):
        _write_embedding(
            database, track=TrackIdentity(database.catalog_uuid, track_id, "stale"),
            family="mert_v2", vector=vectors["mert_v2"],
            analyzed_at="2026-08-12T00:00:00.000000Z",
        )

    detail = database.get_track_detail(track_id)
    coverage = detail.analysis_coverage
    assert coverage.muq and coverage.mert_v2 and coverage.maest_embedding
    assert {(row.analysis_family, row.dim) for row in detail.embeddings} == {
        ("muq", 1024), ("mert_v2", 1024), ("maest", MAEST_EMBEDDING_DIM),
    }
    with closing(database.connect()) as connection:
        for family, layers in EMBEDDING_LAYERS.items():
            dim = vectors[family].shape[0]
            row = connection.execute(
                f"SELECT layer, dim, normalization, length(embedding_blob) FROM {family}_embeddings"
            ).fetchone()
            assert tuple(row) == (layers.default, dim, "l2", dim * 4)
            assert {row[1]: row[5] for row in connection.execute(
                f"PRAGMA table_info({family}_embeddings)") if row[5]
            } == {"track_id": 1, "layer": 2}
        assert [row[0] for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE 'mert_v2%'")
        ] == ["mert_v2_embeddings"]
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []

    for family, layers in EMBEDDING_LAYERS.items():
        output = AnalysisOutput(family, "embedding")
        numbers = range(1, layers.count + 1)
        assert database.embedding_layer_counts(family) == {
            **dict.fromkeys(numbers, 0), layers.default: 1,
        }
        stack = [
            np.eye(1, vectors[family].shape[0], 3 + number, dtype=np.float32)[0]
            for number in numbers
        ]
        stack[layers.default - 1] = vectors[family]
        write_target = AnalysisTarget(target.catalog_uuid, track_id, target.track_uuid)
        write = EmbeddingOutput(
            family, vectors[family], "2026-08-13T00:00:00.000000Z", tuple(stack),
        )
        assert _save_embedding_output(database, write_target, write)
        assert database.embedding_layer_counts(family) == dict.fromkeys(numbers, 1)
        for layer in numbers:
            rows = database.load_analysis_vectors(output, layer=layer)
            np.testing.assert_array_equal(rows[0].vector, stack[layer - 1])
            assert database.random_embedding_target(output, layer=layer) == write_target
        assert len(database.load_analysis_vectors(output)) == 1
        detail = database.get_track_detail(track_id)
        assert sum(row.analysis_family == family for row in detail.embeddings) == 1
        with closing(database.connect()) as connection:
            assert [(row[0], row[1]) for row in connection.execute(
                f"SELECT layer, embedding_blob FROM {family}_embeddings ORDER BY layer"
            )] == [(layer, vector.tobytes()) for layer, vector in enumerate(stack, start=1)]
        with pytest.raises(ValueError, match=f"all {layers.count} {family} layers"):
            EmbeddingOutput(family, vectors[family], "now", tuple(stack[:-1]))
        with pytest.raises(ValueError, match=f"all {layers.count} {family} layers"):
            EmbeddingOutput(family, vectors[family], "now")
        with pytest.raises(ValueError, match=f"layer {layers.default} must equal the primary"):
            EmbeddingOutput(family, stack[0], "now", tuple(stack))
        with pytest.raises(ValueError, match=f"from 1 to {layers.count}"):
            database.load_analysis_vectors(output, layer=0)
        with closing(database.connect()) as connection, connection:
            connection.execute(
                f"UPDATE {family}_embeddings SET track_uuid='stale' WHERE layer=12"
            )
        assert database.load_analysis_vectors(output, layer=12) == ()
        assert _save_embedding_output(database, write_target, write)
        with closing(database.connect()) as connection, connection:
            connection.execute(
                f"CREATE TRIGGER fail_layer BEFORE INSERT ON {family}_embeddings "
                "WHEN NEW.layer=7 BEGIN SELECT RAISE(ABORT, 'test rollback'); END"
            )
        replacement = EmbeddingOutput(family, stack[0], "new", (stack[0],) * layers.count)
        assert not _save_embedding_output(database, write_target, replacement)
        for layer in (1, 7, layers.default):
            np.testing.assert_array_equal(
                database.load_analysis_vectors(output, layer=layer)[0].vector,
                stack[layer - 1],
            )
        with closing(database.connect()) as connection, connection:
            connection.execute("DROP TRIGGER fail_layer")
    with pytest.raises(ValueError, match="not supported for clap"):
        database.load_analysis_vectors(AnalysisOutput("clap", "embedding"), layer=12)

    reset = database.reset_analysis_outputs(
        (AnalysisOutput("mert_v2", "embedding"), AnalysisOutput("maest", "embedding")),
    )
    assert reset.embedding_rows_deleted == 2
    for family in ("mert_v2", "maest"):
        assert database.load_analysis_vectors(AnalysisOutput(family, "embedding")) == ()
        assert database.embedding_layer_counts(family) == dict.fromkeys(
            range(1, EMBEDDING_LAYERS[family].count + 1), 0,
        )
    np.testing.assert_array_equal(
        _read_embedding(database, track=target, family="muq"), vectors["muq"],
    )
    for family in ("mert_v2", "maest"):
        _write_embedding(
            database, track=target, family=family, vector=vectors[family],
            analyzed_at="2026-08-12T00:00:00.000000Z",
        )
    cleared = database.clear_library()
    assert cleared["tracks_deleted"] == 1
    assert cleared["embedding_rows_deleted"] == 3
    with closing(database.connect()) as connection:
        for family in EMBEDDING_LAYERS:
            assert connection.execute(f"SELECT COUNT(*) FROM {family}_embeddings").fetchone()[0] == 0
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
    outputs = (AnalysisOutput("mulan", "embedding"),) + tuple(
        AnalysisOutput(family, "embedding") for family in EMBEDDING_LAYERS
    )

    def missing_outputs() -> tuple[AnalysisOutput, ...]:
        candidates = database.list_analysis_candidates(outputs)
        assert [candidate.target for candidate in candidates] in ([], [AnalysisTarget(
            catalog_uuid=target.catalog_uuid,
            track_id=target.track_id,
            track_uuid=target.track_uuid,
        )])
        return candidates[0].missing_outputs if candidates else ()

    assert missing_outputs() == outputs
    for index, output in enumerate(outputs):
        family = output.analysis_family
        vector = np.zeros(current_embedding_spec(family).dimension, dtype=np.float32)
        vector[0] = 1.0
        layers = EMBEDDING_LAYERS.get(family)
        if layers is not None:
            # Another layer's row does not make a layered family ready.
            with closing(database.connect()) as connection:
                connection.execute("BEGIN IMMEDIATE")
                write_valid_embedding_in_transaction(
                    connection=connection,
                    track=target,
                    family=family,
                    embedding=vector,
                    analyzed_at="2026-08-12T00:00:00.000000Z",
                    layer=1,
                )
                connection.commit()
            assert missing_outputs() == outputs[index:]
        # The current track's row, at the default layer of a layered family,
        # is the whole readiness check.
        _write_embedding(
            database,
            track=target,
            family=family,
            vector=vector,
            analyzed_at="2026-08-12T00:00:00.000000Z",
        )
        assert missing_outputs() == outputs[index + 1:]
        default_layer = "" if layers is None else f" AND layer = {layers.default}"
        with closing(database.connect()) as connection, connection:
            connection.execute(
                f"UPDATE {family}_embeddings SET track_uuid = 'stale' WHERE 1{default_layer}"
            )
        assert missing_outputs() == outputs[index:]
        with closing(database.connect()) as connection, connection:
            connection.execute(
                f"UPDATE {family}_embeddings SET track_uuid = ? WHERE 1{default_layer}",
                (target.track_uuid,),
            )
    assert missing_outputs() == ()


def test_stored_embedding_sonara_and_maest_readiness_does_not_read_payload(tmp_path: Path) -> None:
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
    for family, dimension in (("muq", 1024), ("mert_v2", 1024)):
        vector = np.zeros(dimension, dtype=np.float32)
        vector[0] = 1.0
        result = database.save_embedding_results((EmbeddingWrite(
            AnalysisTarget(target.catalog_uuid, target.track_id, target.track_uuid),
            EmbeddingOutput(family, vector, "now", (vector,) * EMBEDDING_LAYERS[family].count),
        ),))
        assert result[0].ok
    sonara_values = {field.name: None for field in fields(SonaraRow)}
    sonara_values.update(
        track_id=track_id,
        analysis_schema_version=6,
        analyzed_at="2026-08-12T00:00:00.000000Z",
        mfcc_mean_blob=np.zeros(13, dtype="<f4").tobytes(),
        chroma_mean_blob=np.zeros(12, dtype="<f4").tobytes(),
        spectral_contrast_mean_blob=np.zeros(7, dtype="<f4").tobytes(),
    )
    sonara = save_sonara_writes(database, (complete_sonara_write(
        AnalysisTarget(target.catalog_uuid, target.track_id, target.track_uuid),
        SonaraRow(**sonara_values),
    ),))
    assert sonara[0].ok, sonara[0].error
    maest_vector = np.zeros(MAEST_EMBEDDING_DIM, dtype=np.float32)
    maest_vector[0] = 1.0
    maest = database.save_maest_results((MaestWrite(
        AnalysisTarget(target.catalog_uuid, target.track_id, target.track_uuid),
        genres=(MaestGenreScore("Electronic---House", 0.8),),
        syncopated_rhythm=False,
        analyzed_at="2026-08-12T00:00:00.000000Z",
        embedding=EmbeddingOutput(
            "maest", maest_vector, "2026-08-12T00:00:00.000000Z",
            (maest_vector,) * EMBEDDING_LAYERS["maest"].count,
        ),
    ),))
    assert maest[0].ok, maest[0].error
    payload_tables = {
        "sonara_features",
        "sonara_fingerprints",
        "sonara_timeline",
        "sonara_embeddings",
        "maest_genres",
    }

    with closing(database.connect()) as connection:
        def authorizer(
            action: int,
            table: str | None,
            column: str | None,
            _database_name: str | None,
            _trigger_name: str | None,
        ) -> int:
            # Readiness reads the track identity of a stored row, never its payload.
            # SQLite reports the rowid behind an INTEGER PRIMARY KEY as "".
            if action == sqlite3.SQLITE_READ and (
                column == "embedding_blob"
                or (table in payload_tables and column not in {"track_id", "track_uuid", ""})
            ):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        connection.set_authorizer(authorizer)
        candidates = collect_analysis_candidates(
            connection=connection,
            catalog_uuid=database.catalog_uuid,
            outputs=(
                AnalysisOutput("muq", "embedding"),
                AnalysisOutput("mert_v2", "embedding"),
                *analysis_outputs_for_sonara_runtime(),
                AnalysisOutput("maest", "analysis"),
                AnalysisOutput("maest", "embedding"),
            ),
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
        for family, dimension in (("maest", MAEST_EMBEDDING_DIM), ("muq", 1024), ("mert_v2", 1024)):
            vector = np.zeros(dimension, dtype="<f4")
            vector[0] = 2.0
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
                    track_id, track_uuid, dim, normalization, embedding_blob, analyzed_at, layer
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [(*values, layer) for layer in range(1, EMBEDDING_LAYERS[family].count + 1)],
            )

    summary = database.library_summary()

    assert summary.tracks == 1
    assert summary.maest_embedding == 1
    assert summary.muq == 1
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
    vector = np.zeros(1024, dtype=np.float32)
    vector[0] = 1.0
    _write_embedding(
        database,
        track=TrackIdentity(database.catalog_uuid, track_id, "track-c"),
        family="muq",
        vector=vector,
        analyzed_at="2026-08-12T00:00:00.000000Z",
    )

    source = SourceDatabase(database.path)

    assert source.count_tracks() == 1
    assert source.count_embeddings("muq") == 1


def test_evaluation_profile_creates_the_optional_sidecar_on_save(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")

    assert database.connect_evaluation(create=False) is None
    assert not database.evaluation_path.exists()

    profile_id = database.save_evaluation_profile(
        "weighted-candidates",
        {"weights": {"muq": 1.0}},
    )

    assert profile_id == 1
    assert database.evaluation_path.is_file()
    stored = database.get_evaluation_profile("weighted-candidates")
    assert stored is not None
    assert stored["profile_id"] == 1
    assert stored["profile_name"] == "weighted-candidates"
    assert stored["profile"] == {"weights": {"muq": 1.0}}
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
