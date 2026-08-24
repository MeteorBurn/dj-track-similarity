from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from dj_track_similarity.cli import app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.database_validation import DatabaseValidator
from dj_track_similarity.db_embeddings import write_valid_embedding
from dj_track_similarity.track_models import FileTags, ScannedFile


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
    before = database.path.read_bytes()

    report = DatabaseValidator(database.path).run()

    assert report.error_count == 0
    assert report.warning_count == 0
    assert any(
        finding.level == "ok"
        and finding.entity == "track"
        and finding.track_id == identity.track_id
        for finding in report.findings
    )
    assert database.path.read_bytes() == before


def test_validator_warns_when_stored_track_path_is_missing(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _track(database, tmp_path / "removed.wav")
    (tmp_path / "removed.wav").unlink()

    report = DatabaseValidator(database.path).run()

    assert any(
        finding.level == "warning"
        and finding.code == "track_path_missing"
        and finding.track_id == identity.track_id
        for finding in report.findings
    )


def test_validator_reports_corrupt_embedding_payload(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _track(database, tmp_path / "track.wav")
    with database.connect() as connection:
        write_valid_embedding(
            connection=connection,
            track=identity,
            family="mert",
            embedding=np.ones(768, dtype="<f4") / np.sqrt(768),
            analyzed_at="2026-08-13T00:00:00Z",
        )
    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE mert_embeddings SET track_uuid = ?, normalization = 'none' WHERE track_id = ?",
            ("wrong-uuid", identity.track_id),
        )
        connection.commit()

    report = DatabaseValidator(database.path).run()

    assert any(
        finding.level == "error"
        and finding.entity == "embedding"
        and finding.table == "mert_embeddings"
        and finding.track_id == identity.track_id
        and finding.code == "embedding_invalid"
        for finding in report.findings
    )


def test_validator_reports_non_finite_sonara_feature_vector(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _track(database, tmp_path / "sonara.wav")
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "INSERT INTO sonara_features(track_id, mfcc_mean_blob, chroma_mean_blob, spectral_contrast_mean_blob, analysis_schema_version, bpm_min, bpm_max, analyzed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (identity.track_id, np.full(13, np.nan, dtype="<f4").tobytes(), np.zeros(12, dtype="<f4").tobytes(), np.zeros(7, dtype="<f4").tobytes(), 6, 70.0, 180.0, "2026-08-13T00:00:00Z"),
        )
        connection.commit()

    report = DatabaseValidator(database.path).run()

    assert any(finding.code == "sonara_feature_invalid" and finding.track_id == identity.track_id for finding in report.findings)


def test_validator_reports_invalid_classifier_probabilities(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _track(database, tmp_path / "classifier.wav")
    with sqlite3.connect(database.path) as connection:
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "INSERT INTO classifier_scores(track_id, track_uuid, classifier_key, feature_set, feature_names_json, positive_label, predicted_class, score_bucket, score, confidence, probabilities_json, analyzed_at) VALUES (?, ?, 'voice', 'sonara', '[]', 'voice', 'voice', 'high', 1.2, 0.5, '{}', '2026-08-13T00:00:00Z')",
            (identity.track_id, identity.track_uuid),
        )
        connection.commit()

    report = DatabaseValidator(database.path).run()

    assert any(
        finding.code == "classifier_score_invalid"
        and finding.track_id == identity.track_id
        and finding.message == "Classifier «voice»: stored values are invalid"
        for finding in report.findings
    )


def test_validate_database_cli_uses_concise_human_messages(tmp_path: Path) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")

    result = CliRunner().invoke(app, ["validate-database", "--db", str(database.path)])

    assert result.exit_code == 0
    assert "[OK] SQLite integrity check passed" in result.output
    assert "sqlite_integrity_ok" not in result.output
