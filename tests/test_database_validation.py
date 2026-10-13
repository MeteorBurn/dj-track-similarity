from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from dj_track_similarity.analysis_models import AnalysisTarget, EMBEDDING_LAYERS, current_embedding_spec
from dj_track_similarity.cli.application import app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.validation import DatabaseValidator
from dj_track_similarity.db.embeddings import write_valid_embedding_in_transaction
from dj_track_similarity.track_models import FileTags, ScannedFile
from sheetsage2_test_support import complete_sheetsage2_write


def _track(database: LibraryDatabase, path: Path):
    path.write_bytes(b"audio")
    stat = path.stat()
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
        ),
        tags=FileTags(title="Validation fixture"),
    ).identity


def test_validator_reports_each_track_and_does_not_mutate_database(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _track(database, tmp_path / "present.wav")
    # A layered family keeps one row per layer; the track is still one track.
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        for family, layers in EMBEDDING_LAYERS.items():
            if family == "sheetsage2":
                continue
            dimension = current_embedding_spec(family).dimension
            for layer, vector in enumerate(np.eye(dimension, dtype="<f4")[:layers.count], start=1):
                write_valid_embedding_in_transaction(
                    connection=connection,
                    track=identity,
                    family=family,
                    embedding=vector,
                    analyzed_at="2026-08-13T00:00:00Z",
                    layer=layer,
                )
        connection.commit()
    write = complete_sheetsage2_write(database, AnalysisTarget(identity.catalog_uuid, identity.track_id, identity.track_uuid))
    assert database.save_sheetsage2_results((write,))[0].ok
    before = database.path.read_bytes()

    report = DatabaseValidator(database.path).run()

    assert report.tracks_checked == 1
    assert report.error_count == 0
    assert report.warning_count == 0
    assert any(
        finding.level == "ok"
        and finding.entity == "track"
        and finding.track_id == identity.track_id
        for finding in report.findings
    )
    assert database.path.read_bytes() == before
    for statement, table in (
        ("DELETE FROM sheetsage2_embeddings WHERE layer = 7", "sheetsage2_embeddings"),
        ("UPDATE sheetsage2_embeddings SET analyzed_at = 'stale' WHERE layer = 7", "sheetsage2_embeddings"),
        ("UPDATE sheetsage2_embeddings SET embedding_blob = zeroblob(4096) WHERE layer = 7", "sheetsage2_embeddings"),
        ("UPDATE sheetsage2_features SET beat_count = beat_count + 1", "sheetsage2_features"),
        ("UPDATE sheetsage2_timeline SET track_uuid = 'stale'", "sheetsage2_timeline"),
        ("DELETE FROM sheetsage2_features", "sheetsage2_features"),
    ):
        with database.connect() as connection:
            connection.execute(statement)
            connection.commit()
        corrupted = DatabaseValidator(database.path).run()
        assert any(
            finding.level == "error" and finding.table == table and finding.track_id == identity.track_id
            for finding in corrupted.findings
        )
        assert database.save_sheetsage2_results((write,))[0].ok
    assert DatabaseValidator(database.path).run().error_count == 0


def test_validator_reports_corrupt_embedding_payload(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _track(database, tmp_path / "track.wav")
    with database.connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        write_valid_embedding_in_transaction(
            connection=connection,
            track=identity,
            family="muq",
            embedding=np.ones(1024, dtype="<f4") / np.sqrt(1024),
            analyzed_at="2026-08-13T00:00:00Z",
        )
        connection.commit()
    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE muq_embeddings SET track_uuid = ?, normalization = 'none' WHERE track_id = ?",
            ("wrong-uuid", identity.track_id),
        )
        connection.commit()

    report = DatabaseValidator(database.path).run()

    assert any(
        finding.level == "error"
        and finding.entity == "embedding"
        and finding.table == "muq_embeddings"
        and finding.track_id == identity.track_id
        and finding.code == "embedding_invalid"
        for finding in report.findings
    )


def test_validator_reports_non_finite_sonara_feature_vector(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _track(database, tmp_path / "sonara.wav")
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "INSERT INTO sonara_features(track_id, mfcc_mean_blob, chroma_mean_blob, spectral_contrast_mean_blob, analysis_schema_version, analyzed_at) VALUES (?, ?, ?, ?, ?, ?)",
            (identity.track_id, np.full(13, np.nan, dtype="<f4").tobytes(), np.zeros(12, dtype="<f4").tobytes(), np.zeros(7, dtype="<f4").tobytes(), 6, "2026-08-13T00:00:00Z"),
        )
        connection.commit()

    report = DatabaseValidator(database.path).run()

    assert any(finding.code == "sonara_feature_invalid" and finding.track_id == identity.track_id for finding in report.findings)


def test_validate_database_cli_uses_concise_human_messages(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")

    result = CliRunner().invoke(app, ["validate-database", "--db", str(database.path)])

    assert result.exit_code == 0
    assert "[OK] SQLite integrity check passed" in result.output
    assert "sqlite_integrity_ok" not in result.output
