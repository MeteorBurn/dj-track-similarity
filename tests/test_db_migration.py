from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from dj_track_similarity import cli
from dj_track_similarity.analysis_models import current_embedding_spec
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_evaluation_sidecar import (
    create_evaluation_sidecar_schema,
)
from dj_track_similarity.db_migration import (
    apply_database_migration,
    plan_database_migration,
)
from dj_track_similarity.db_storage import storage_database_paths


@dataclass(frozen=True)
class _LegacyBundle:
    core: Path
    artifacts: Path
    evaluation: Path


def _legacy_bundle(tmp_path: Path) -> _LegacyBundle:
    core = tmp_path / "library.sqlite"
    paths = storage_database_paths(core)
    catalog_uuid = "catalog-for-explicit-migration"

    with sqlite3.connect(core) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE library_catalog (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                catalog_uuid TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE contracts (
                contract_hash TEXT PRIMARY KEY,
                analysis_family TEXT NOT NULL,
                output_kind TEXT NOT NULL,
                model_name TEXT NOT NULL,
                model_version TEXT,
                release_hash TEXT,
                canonical_payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE library_settings (
                setting_key TEXT NOT NULL PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE tracks (
                track_id INTEGER PRIMARY KEY AUTOINCREMENT,
                track_uuid TEXT NOT NULL UNIQUE,
                file_path TEXT NOT NULL UNIQUE,
                file_size_bytes INTEGER NOT NULL,
                file_modified_ns INTEGER NOT NULL,
                audio_format TEXT,
                audio_codec TEXT,
                sample_rate_hz INTEGER,
                channel_count INTEGER,
                bit_rate_bps INTEGER,
                audio_duration_seconds REAL,
                content_generation INTEGER NOT NULL,
                last_scanned_at TEXT NOT NULL,
                missing_since TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE tags (
                track_id INTEGER PRIMARY KEY REFERENCES tracks ON DELETE CASCADE,
                title TEXT,
                artist TEXT,
                album TEXT,
                tag_bpm REAL,
                tag_key TEXT,
                comment TEXT,
                year INTEGER,
                label TEXT,
                catalog_number TEXT,
                country TEXT,
                isrc TEXT,
                track_number TEXT,
                disc_number TEXT,
                genres_json TEXT NOT NULL,
                tags_read_at TEXT NOT NULL
            );
            CREATE TABLE maest_genres (
                track_id INTEGER PRIMARY KEY REFERENCES tracks ON DELETE CASCADE,
                content_generation INTEGER NOT NULL,
                contract_hash TEXT NOT NULL REFERENCES contracts,
                syncopated_rhythm INTEGER,
                genres_json TEXT NOT NULL,
                analyzed_at TEXT NOT NULL
            );
            CREATE TABLE classifier_scores (
                track_id INTEGER NOT NULL REFERENCES tracks ON DELETE CASCADE,
                classifier_key TEXT NOT NULL,
                content_generation INTEGER NOT NULL,
                model_id TEXT NOT NULL,
                feature_set TEXT NOT NULL,
                feature_manifest_hash TEXT NOT NULL,
                required_outputs_hash TEXT NOT NULL,
                uses_sonara INTEGER NOT NULL,
                sonara_release_hash TEXT,
                positive_label TEXT NOT NULL,
                predicted_class TEXT NOT NULL,
                score_bucket TEXT NOT NULL,
                score REAL NOT NULL,
                confidence REAL NOT NULL,
                probabilities_json TEXT NOT NULL,
                analyzed_at TEXT NOT NULL,
                PRIMARY KEY(track_id, classifier_key)
            );
            CREATE TABLE likes (
                track_id INTEGER PRIMARY KEY REFERENCES tracks ON DELETE CASCADE,
                liked_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO library_catalog
                (singleton_id, catalog_uuid, created_at, updated_at)
            VALUES (1, ?, '2025-01-01T00:00:00Z', '2025-01-02T00:00:00Z')
            """,
            (catalog_uuid,),
        )
        connection.executemany(
            """
            INSERT INTO library_settings(setting_key, setting_value, updated_at)
            VALUES (?, ?, '2025-01-02T00:00:00Z')
            """,
            (
                ("ui.theme", '{"name":"dark","release_notes":"keep"}'),
                ("sonara.active_release_hash", "legacy-release"),
                ("analysis.active_contract.core", "legacy-contract"),
                (
                    "runtime.state",
                    '{"nested":{"active_contract_hash":"legacy"},"keep":true}',
                ),
            ),
        )
        connection.execute(
            """
            INSERT INTO contracts
                (contract_hash, analysis_family, output_kind, model_name,
                 model_version, release_hash, canonical_payload_json, created_at)
            VALUES ('legacy-maest', 'maest', 'analysis', 'maest', 'old', NULL,
                    '{}', '2025-01-01T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO tracks
                (track_id, track_uuid, file_path, file_size_bytes,
                 file_modified_ns, audio_format, audio_codec, sample_rate_hz,
                 channel_count, bit_rate_bps, audio_duration_seconds,
                 content_generation, last_scanned_at, missing_since,
                 created_at, updated_at)
            VALUES
                (1, 'track-one', 'C:\\music\\one.wav', 1000, 100,
                 'wav', 'pcm_s16le', 44100, 2, 1411200, 120.0,
                 3, '2025-01-02T00:00:00Z', NULL,
                 '2025-01-01T00:00:00Z', '2025-01-02T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO tags
                (track_id, title, artist, album, tag_bpm, tag_key, comment,
                 year, label, catalog_number, country, isrc, track_number,
                 disc_number, genres_json, tags_read_at)
            VALUES
                (1, 'One', 'Artist', 'Album', 128.0, '8A', 'kept', 2025,
                 'Label', 'CAT-1', 'UA', 'ISRC1', '1', '1',
                 '["Techno"]', '2025-01-02T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO maest_genres
                (track_id, content_generation, contract_hash,
                 syncopated_rhythm, genres_json, analyzed_at)
            VALUES
                (1, 3, 'legacy-maest', 1,
                 '[{"genre_name":"Techno","score":0.9}]',
                 '2025-01-02T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO classifier_scores
                (track_id, classifier_key, content_generation, model_id,
                 feature_set, feature_manifest_hash, required_outputs_hash,
                 uses_sonara, sonara_release_hash, positive_label,
                 predicted_class, score_bucket, score, confidence,
                 probabilities_json, analyzed_at)
            VALUES
                (1, 'break-energy', 3, 'legacy-model', 'legacy-features',
                 'legacy-feature-hash', 'legacy-output-hash', 1,
                 'legacy-release', 'break', 'break', 'high', 0.9, 0.8,
                 '{"break":0.9,"not_break":0.1}',
                 '2025-01-02T00:00:00Z')
            """
        )
        connection.execute(
            "INSERT INTO likes(track_id, liked_at) VALUES "
            "(1, '2025-01-03T00:00:00Z')"
        )

    mert_spec = current_embedding_spec("mert")
    vector = np.zeros((mert_spec.dimension,), dtype="<f4")
    vector[0] = 1.0
    with sqlite3.connect(paths.artifacts) as connection:
        connection.executescript(
            """
            CREATE TABLE storage_metadata (
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                catalog_uuid TEXT NOT NULL,
                schema_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE mert_embeddings (
                track_id INTEGER PRIMARY KEY,
                track_uuid TEXT NOT NULL,
                content_generation INTEGER NOT NULL,
                contract_hash TEXT NOT NULL,
                dim INTEGER NOT NULL,
                normalization TEXT NOT NULL,
                embedding_blob BLOB NOT NULL,
                analyzed_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            INSERT INTO storage_metadata
                (singleton_id, catalog_uuid, schema_version, created_at, updated_at)
            VALUES
                (1, ?, 7, '2025-01-01T00:00:00Z',
                 '2025-01-02T00:00:00Z')
            """,
            (catalog_uuid,),
        )
        connection.execute(
            """
            INSERT INTO mert_embeddings
                (track_id, track_uuid, content_generation, contract_hash, dim,
                 normalization, embedding_blob, analyzed_at)
            VALUES
                (1, 'track-one', 3, 'legacy-mert', ?, 'l2', ?,
                 '2025-01-02T00:00:00Z')
            """,
            (mert_spec.dimension, vector.tobytes()),
        )

    create_evaluation_sidecar_schema(
        paths.evaluation,
        catalog_uuid=catalog_uuid,
    )
    with sqlite3.connect(paths.evaluation) as connection:
        request_json = json.dumps(
            {
                "mode": "evaluation_candidate_pool",
                "filters": {"limit": 10},
                "source_contract_hashes": {"mert": "legacy"},
                "nested": {
                    "release_hash": "legacy-release",
                    "weights": {"mert": 1.0},
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        cursor = connection.execute(
            """
            INSERT INTO search_sessions(mode, request_json, created_at)
            VALUES ('evaluation_candidate_pool', ?, '2025-01-03T00:00:00Z')
            """,
            (request_json,),
        )
        session_id = int(cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO search_session_seeds
                (session_id, position, track_id, track_uuid, content_generation)
            VALUES (?, 0, 1, 'track-one', 3)
            """,
            (session_id,),
        )
        connection.execute(
            """
            INSERT INTO search_result_events
                (session_id, rank, track_id, track_uuid, content_generation,
                 total_score, score_breakdown_json, created_at)
            VALUES
                (?, 0, 1, 'track-one', 3, 0.8,
                 '{"mert":0.8,"contract_hash":"legacy"}',
                 '2025-01-03T00:00:00Z')
            """,
            (session_id,),
        )

    return _LegacyBundle(core, paths.artifacts, paths.evaluation)


def _bundle_hashes(bundle: _LegacyBundle) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (bundle.core, bundle.artifacts, bundle.evaluation)
    }


def _bundle_snapshot(bundle: _LegacyBundle) -> dict[str, object]:
    with sqlite3.connect(bundle.core) as core:
        core_tables = {
            str(row[0])
            for row in core.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        track = core.execute(
            "SELECT track_uuid, file_path, content_generation FROM tracks"
        ).fetchone()
        catalog = core.execute(
            "SELECT catalog_uuid FROM library_catalog"
        ).fetchone()[0]
    with sqlite3.connect(bundle.artifacts) as artifacts:
        artifact_columns = tuple(
            str(row[1])
            for row in artifacts.execute("PRAGMA table_info(storage_metadata)")
        )
        artifact_catalog = artifacts.execute(
            "SELECT catalog_uuid FROM storage_metadata"
        ).fetchone()[0]
        embedding_count = artifacts.execute(
            "SELECT COUNT(*) FROM mert_embeddings"
        ).fetchone()[0]
    with sqlite3.connect(bundle.evaluation) as evaluation:
        request_json = evaluation.execute(
            "SELECT request_json FROM search_sessions"
        ).fetchone()[0]
    return {
        "core_tables": core_tables,
        "track": tuple(track),
        "catalog": catalog,
        "artifact_columns": artifact_columns,
        "artifact_catalog": artifact_catalog,
        "embedding_count": embedding_count,
        "request": json.loads(request_json),
    }


def _assert_sqlite_ok(path: Path) -> None:
    with sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_plan_is_read_only_and_reports_structural_changes(tmp_path: Path) -> None:
    bundle = _legacy_bundle(tmp_path)
    before_hashes = _bundle_hashes(bundle)
    before_entries = {path.name for path in tmp_path.iterdir()}

    plan = plan_database_migration(bundle.core)

    assert plan.has_changes
    assert plan.analysis_families_needing_reanalysis == ("classifiers",)
    assert any(
        "Evaluation" in warning and "legacy identity" in warning
        for warning in plan.warnings
    )
    assert _bundle_hashes(bundle) == before_hashes
    assert {path.name for path in tmp_path.iterdir()} == before_entries


def test_apply_rejects_inexact_confirmation_before_backup(
    tmp_path: Path,
) -> None:
    bundle = _legacy_bundle(tmp_path)
    plan = plan_database_migration(bundle.core)
    backup_dir = tmp_path / "backup"
    before_hashes = _bundle_hashes(bundle)

    with pytest.raises(ValueError, match="MIGRATE DATABASE"):
        apply_database_migration(plan, backup_dir, "yes")

    assert not backup_dir.exists()
    assert _bundle_hashes(bundle) == before_hashes


def test_apply_backs_up_then_migrates_and_reports_excluded_derived_rows(
    tmp_path: Path,
) -> None:
    bundle = _legacy_bundle(tmp_path)
    plan = plan_database_migration(bundle.core)
    backup_dir = tmp_path / "backup"
    evaluation_before = hashlib.sha256(bundle.evaluation.read_bytes()).hexdigest()

    receipt = apply_database_migration(
        plan,
        backup_dir,
        "MIGRATE DATABASE",
    )

    assert receipt.core_backup.is_file()
    assert receipt.artifacts_backup.is_file()
    assert receipt.integrity_check == "ok"
    assert receipt.foreign_key_violations == 0
    assert receipt.orphan_count == 0
    assert receipt.analysis_families_needing_reanalysis == ("classifiers",)
    assert receipt.excluded_rows == (("core", "classifier_scores", 1),)
    assert receipt.recovery_receipt.is_file()
    assert json.loads(
        receipt.recovery_receipt.read_text(encoding="utf-8")
    )["status"] == "completed"

    for path in (
        receipt.core_backup,
        receipt.artifacts_backup,
        bundle.core,
        bundle.artifacts,
        bundle.evaluation,
    ):
        _assert_sqlite_ok(path)

    with sqlite3.connect(bundle.core) as core:
        tables = {
            str(row[0])
            for row in core.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "contracts" not in tables
        assert "tags" in tables
        assert core.execute(
            """
            SELECT setting_key, setting_value
            FROM library_settings
            ORDER BY setting_key
            """
        ).fetchall() == [
            ("ui.theme", '{"name":"dark","release_notes":"keep"}')
        ]
        assert core.execute(
            "SELECT created_at, updated_at FROM library_catalog"
        ).fetchone() == (
            "2025-01-01T00:00:00Z",
            "2025-01-02T00:00:00Z",
        )
        assert core.execute("SELECT title FROM tags").fetchone()[0] == "One"
        assert tuple(
            str(row[1]) for row in core.execute("PRAGMA table_info(tags)")
        ) == (
            "track_id",
            "title",
            "artist",
            "album",
            "track_number",
            "label",
            "country",
            "year",
            "tag_key",
            "tag_bpm",
            "comment",
            "genres_json",
            "tags_read_at",
        )
        track_columns = {
            str(row[1]) for row in core.execute("PRAGMA table_info(tracks)")
        }
        assert "audio_codec" not in track_columns
        assert "bit_depth" in track_columns
        assert core.execute("SELECT COUNT(*) FROM likes").fetchone()[0] == 1
        assert core.execute("SELECT COUNT(*) FROM maest_genres").fetchone()[0] == 1
        assert core.execute("SELECT COUNT(*) FROM classifier_scores").fetchone()[0] == 0
        classifier_columns = {
            str(row[1])
            for row in core.execute("PRAGMA table_info(classifier_scores)")
        }
        assert {"track_uuid", "feature_names_json"} <= classifier_columns
        assert "feature_manifest_hash" not in classifier_columns

    with sqlite3.connect(bundle.artifacts) as artifacts:
        metadata_columns = {
            str(row[1])
            for row in artifacts.execute("PRAGMA table_info(storage_metadata)")
        }
        embedding_columns = {
            str(row[1])
            for row in artifacts.execute("PRAGMA table_info(mert_embeddings)")
        }
        assert metadata_columns == {
            "singleton_id",
            "catalog_uuid",
            "created_at",
            "updated_at",
        }
        assert "contract_hash" not in embedding_columns
        assert artifacts.execute(
            "SELECT COUNT(*) FROM mert_embeddings"
        ).fetchone()[0] == 1

    assert (
        hashlib.sha256(bundle.evaluation.read_bytes()).hexdigest()
        == evaluation_before
    )

    database = LibraryDatabase(bundle.core)
    assert database.catalog_uuid == "catalog-for-explicit-migration"


@pytest.mark.parametrize(
    "failure_stage",
    (
        "after_core_backup",
        "after_artifacts_backup",
        "after_backup_validation",
        "after_replacement_validation",
        "after_first_replace",
    ),
)
def test_failure_injection_never_leaves_a_mixed_bundle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_stage: str,
) -> None:
    from dj_track_similarity import db_migration

    bundle = _legacy_bundle(tmp_path)
    before = _bundle_snapshot(bundle)
    plan = plan_database_migration(bundle.core)

    def fail_at_stage(stage: str) -> None:
        if stage == failure_stage:
            raise RuntimeError(f"injected failure at {stage}")

    monkeypatch.setattr(db_migration, "_stage_checkpoint", fail_at_stage)

    with pytest.raises(RuntimeError, match="injected failure"):
        apply_database_migration(
            plan,
            tmp_path / f"backup-{failure_stage}",
            "MIGRATE DATABASE",
        )

    assert _bundle_snapshot(bundle) == before
    for path in (bundle.core, bundle.artifacts, bundle.evaluation):
        _assert_sqlite_ok(path)


def test_unrestored_commit_boundary_is_fail_closed_with_recovery_instructions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dj_track_similarity import db_migration

    bundle = _legacy_bundle(tmp_path)
    plan = plan_database_migration(bundle.core)

    def fail_after_first_commit(stage: str) -> None:
        if stage == "after_first_replace":
            raise RuntimeError("simulated process loss at pair commit boundary")

    def unavailable_restore(**_: object) -> None:
        raise OSError("simulated recovery interruption")

    monkeypatch.setattr(db_migration, "_stage_checkpoint", fail_after_first_commit)
    monkeypatch.setattr(db_migration, "_restore_backup_pair", unavailable_restore)

    with pytest.raises(
        RuntimeError,
        match="automatic restoration also failed",
    ):
        apply_database_migration(
            plan,
            tmp_path / "backup-crash-boundary",
            "MIGRATE DATABASE",
        )

    marker = bundle.core.with_name(
        f".{bundle.core.name}.migration-recovery.json"
    )
    payload = json.loads(marker.read_text(encoding="utf-8"))
    core_backup = Path(payload["core_backup"])
    artifacts_backup = Path(payload["artifacts_backup"])
    for backup in (core_backup, artifacts_backup):
        assert backup.is_file()
        _assert_sqlite_ok(backup)

    with pytest.raises(
        RuntimeError,
        match="Pending database migration recovery",
    ):
        LibraryDatabase(bundle.core)

    result = CliRunner().invoke(
        cli.app,
        ["migrate-database", "--db", str(bundle.core), "--dry-run"],
    )
    assert result.exit_code == 1
    assert "Pending database migration recovery" in result.output
    assert str(core_backup) in result.output
    assert str(artifacts_backup) in result.output


def test_apply_rejects_a_plan_after_source_changes(tmp_path: Path) -> None:
    bundle = _legacy_bundle(tmp_path)
    plan = plan_database_migration(bundle.core)
    with closing(sqlite3.connect(bundle.core)) as connection:
        connection.execute(
            "UPDATE tags SET title = 'Changed after preview' WHERE track_id = 1"
        )
        connection.commit()

    with pytest.raises(RuntimeError, match="changed since migration preview"):
        apply_database_migration(
            plan,
            tmp_path / "backup",
            "MIGRATE DATABASE",
        )

    assert not (tmp_path / "backup").exists()


def test_wal_commit_after_preview_is_rejected_without_losing_the_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dj_track_similarity import db_migration

    monkeypatch.setattr(db_migration, "_BUSY_TIMEOUT_SECONDS", 0.05)
    bundle = _legacy_bundle(tmp_path)
    for path in (bundle.core, bundle.artifacts):
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute(
                "PRAGMA journal_mode = WAL"
            ).fetchone()[0] == "wal"
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    plan = plan_database_migration(bundle.core)

    writer = sqlite3.connect(bundle.core)
    try:
        writer.execute(
            "UPDATE tags SET title = 'Committed after preview' WHERE track_id = 1"
        )
        writer.commit()

        with pytest.raises(
            RuntimeError,
            match="changed since migration preview|stop.*writers",
        ):
            apply_database_migration(
                plan,
                tmp_path / "backup",
                "MIGRATE DATABASE",
            )
    finally:
        writer.close()

    assert not (tmp_path / "backup").exists()
    with sqlite3.connect(bundle.core) as connection:
        assert connection.execute(
            "SELECT title FROM tags WHERE track_id = 1"
        ).fetchone()[0] == "Committed after preview"
        assert connection.execute(
            "SELECT COUNT(*) FROM contracts"
        ).fetchone()[0] == 1
    with sqlite3.connect(bundle.artifacts) as connection:
        assert "schema_version" in {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(storage_metadata)")
        }


def test_write_attempt_during_pair_publication_is_rejected_and_not_lost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dj_track_similarity import db_migration

    bundle = _legacy_bundle(tmp_path)
    plan = plan_database_migration(bundle.core)
    writer_errors: dict[str, str] = {}
    writer_succeeded: set[str] = set()

    def attempt_write(stage: str) -> None:
        if stage != "after_first_replace":
            return
        writes = (
            (
                "core",
                bundle.core,
                """
                UPDATE tags
                SET title = 'Raced during publication'
                WHERE track_id = 1
                """,
            ),
                (
                    "artifacts",
                    bundle.artifacts,
                    "DELETE FROM mert_embeddings WHERE track_id = 1",
            ),
        )
        for role, path, statement in writes:
            try:
                with closing(sqlite3.connect(path, timeout=0.05)) as connection:
                    connection.execute(statement)
                    connection.commit()
                    writer_succeeded.add(role)
            except sqlite3.OperationalError as error:
                writer_errors[role] = str(error)

    monkeypatch.setattr(db_migration, "_stage_checkpoint", attempt_write)

    apply_database_migration(
        plan,
        tmp_path / "backup",
        "MIGRATE DATABASE",
    )

    assert writer_succeeded == set()
    assert set(writer_errors) == {"core", "artifacts"}
    assert all("locked" in error.lower() for error in writer_errors.values())
    with sqlite3.connect(bundle.core) as connection:
        assert connection.execute(
            "SELECT title FROM tags WHERE track_id = 1"
        ).fetchone()[0] == "One"
    with sqlite3.connect(bundle.artifacts) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM mert_embeddings WHERE track_id = 1"
        ).fetchone()[0] == 1


def test_transferable_classifier_with_wrong_track_uuid_is_excluded(
    tmp_path: Path,
) -> None:
    bundle = _legacy_bundle(tmp_path)
    with closing(sqlite3.connect(bundle.core)) as connection:
        connection.execute(
            "ALTER TABLE classifier_scores ADD COLUMN track_uuid TEXT"
        )
        connection.execute(
            "ALTER TABLE classifier_scores ADD COLUMN feature_names_json TEXT"
        )
        connection.execute(
            """
            UPDATE classifier_scores
            SET track_uuid = 'wrong-track-uuid',
                feature_names_json = '["sonara:detected_bpm"]'
            """
        )
        connection.commit()
    plan = plan_database_migration(bundle.core)

    receipt = apply_database_migration(
        plan,
        tmp_path / "backup",
        "MIGRATE DATABASE",
    )

    assert receipt.analysis_families_needing_reanalysis == ("classifiers",)
    assert receipt.excluded_rows == (("core", "classifier_scores", 1),)
    with sqlite3.connect(bundle.core) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM classifier_scores"
        ).fetchone()[0] == 0


def test_stale_core_derived_rows_are_excluded_and_reported(
    tmp_path: Path,
) -> None:
    bundle = _legacy_bundle(tmp_path)
    with closing(sqlite3.connect(bundle.core)) as connection:
        connection.execute(
            "UPDATE maest_genres SET content_generation = 2 WHERE track_id = 1"
        )
        connection.commit()
    plan = plan_database_migration(bundle.core)

    receipt = apply_database_migration(
        plan,
        tmp_path / "backup",
        "MIGRATE DATABASE",
    )

    assert receipt.analysis_families_needing_reanalysis == (
        "classifiers",
        "maest",
    )
    assert receipt.excluded_rows == (
        ("core", "classifier_scores", 1),
        ("core", "maest_genres", 1),
    )
    with sqlite3.connect(bundle.core) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM maest_genres"
        ).fetchone()[0] == 0


def test_cli_dry_run_is_read_only_and_apply_requires_explicit_confirmation(
    tmp_path: Path,
) -> None:
    bundle = _legacy_bundle(tmp_path)
    before = _bundle_hashes(bundle)

    dry_run = CliRunner().invoke(
        cli.app,
        ["migrate-database", "--db", str(bundle.core), "--dry-run"],
    )

    assert dry_run.exit_code == 0, dry_run.output
    assert "MIGRATE DATABASE" in dry_run.output
    assert _bundle_hashes(bundle) == before
    assert not (tmp_path / "backup").exists()

    applied = CliRunner().invoke(
        cli.app,
        [
            "migrate-database",
            "--db",
            str(bundle.core),
            "--backup-dir",
            str(tmp_path / "backup"),
            "--confirm",
            "MIGRATE DATABASE",
        ],
    )

    assert applied.exit_code == 0, applied.output
    assert "integrity_check=ok" in applied.output
    assert (tmp_path / "backup").is_dir()
