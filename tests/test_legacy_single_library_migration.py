from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dj_track_similarity import cli
from dj_track_similarity.db_ddl import create_library_schema
from dj_track_similarity.db_migration import (
    MIGRATION_CONFIRMATION,
    LegacyLibraryMigrationError,
    migrate_legacy_library_database,
)


_CATALOG_UUID = "legacy-catalog"
_TIMESTAMP = "2026-08-12T00:00:00.000000Z"


def _create_legacy_core(path: Path, *, catalog_uuid: str) -> None:
    with sqlite3.connect(path) as connection:
        create_library_schema(connection)
        connection.execute("PRAGMA foreign_keys = OFF")
        for table in (
            "maest_embeddings",
            "mert_embeddings",
            "muq_embeddings",
            "mulan_embeddings",
            "clap_embeddings",
            "library",
        ):
            connection.execute(f'DROP TABLE "{table}"')
        connection.execute("ALTER TABLE sonara_features RENAME TO sonara")
        connection.execute(
            """
            CREATE TABLE library_catalog (
                singleton_id INTEGER PRIMARY KEY,
                catalog_uuid TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE library_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO library_catalog VALUES (1, ?, ?, ?)",
            (catalog_uuid, _TIMESTAMP, _TIMESTAMP),
        )
        connection.execute(
            "INSERT INTO library_settings VALUES (?, ?, ?)",
            ("analysis.count.tracks", "1", _TIMESTAMP),
        )
        connection.execute(
            """
            INSERT INTO tracks(
                track_id, track_uuid, file_path, file_size_bytes, file_modified_ns,
                last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                7,
                "track-7",
                "D:/Music/House/track-7.flac",
                123,
                456,
                _TIMESTAMP,
                _TIMESTAMP,
                _TIMESTAMP,
            ),
        )
        connection.execute(
            """
            INSERT INTO tags(track_id, title, artist, genres_json, tags_read_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (7, "A Legacy Track", "Legacy Artist", '["house"]', _TIMESTAMP),
        )
        connection.execute(
            """
            INSERT INTO sonara(
                track_id, mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analysis_schema_version,
                bpm_min, bpm_max, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (7, bytes(13 * 4), bytes(12 * 4), bytes(7 * 4), 6, 70.0, 180.0, _TIMESTAMP),
        )
        connection.execute(
            """
            INSERT INTO maest_genres(
                track_id, syncopated_rhythm, genres_json, analyzed_at
            ) VALUES (?, ?, ?, ?)
            """,
            (7, 1, '[{"genre_name":"electronic"}]', _TIMESTAMP),
        )
        connection.execute(
            """
            INSERT INTO classifier_scores(
                track_id, track_uuid, classifier_key, feature_set,
                feature_names_json, positive_label, predicted_class, score_bucket,
                score, confidence, probabilities_json, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                7,
                "track-7",
                "voice_presence",
                "sonara",
                '["energy"]',
                "voice",
                "voice",
                "high",
                0.75,
                0.9,
                '{"voice":0.75}',
                _TIMESTAMP,
            ),
        )
        connection.execute("INSERT INTO likes(track_id, liked_at) VALUES (?, ?)", (7, _TIMESTAMP))
        connection.execute(
            """
            INSERT INTO pair_feedback(
                seed_track_id, candidate_track_id, rating, reason_tags_json, source,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (7, 7, 3, '["energy"]', "manual", _TIMESTAMP, _TIMESTAMP),
        )
        connection.execute(
            """
            INSERT INTO transition_feedback(
                outgoing_track_id, incoming_track_id, rating, risk_tags_json, source,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (7, 7, 2, '["key"]', "manual", _TIMESTAMP),
        )


def _create_legacy_artifacts(path: Path, *, catalog_uuid: str) -> None:
    with sqlite3.connect(path) as connection:
        create_library_schema(connection)
        connection.execute("PRAGMA foreign_keys = OFF")
        for table in (
            "library",
            "tags",
            "sonara_features",
            "maest_genres",
            "classifier_scores",
            "likes",
            "pair_feedback",
            "transition_feedback",
            "track_search_fts",
            "tracks",
            "mulan_embeddings",
        ):
            connection.execute(f'DROP TABLE "{table}"')
        connection.execute(
            """
            CREATE TABLE storage_metadata (
                singleton_id INTEGER PRIMARY KEY,
                catalog_uuid TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO storage_metadata VALUES (1, ?, ?, ?)",
            (catalog_uuid, _TIMESTAMP, _TIMESTAMP),
        )
        for table in (
            "maest_embeddings",
            "mert_embeddings",
            "muq_embeddings",
            "clap_embeddings",
        ):
            connection.execute(f'DROP TABLE "{table}"')
            connection.execute(
                f"""
                CREATE TABLE {table} (
                    track_id INTEGER PRIMARY KEY,
                    track_uuid TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    normalization TEXT NOT NULL,
                    embedding_blob BLOB NOT NULL,
                    analyzed_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                INSERT INTO {table}(
                    track_id, track_uuid, dim, normalization, embedding_blob, analyzed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (7, "track-7", 1, "none", b"\x00\x00\x80?", _TIMESTAMP),
            )


def _create_legacy_pair(root: Path, *, artifact_catalog_uuid: str = _CATALOG_UUID) -> Path:
    core_path = root / "volumes.sqlite"
    _create_legacy_core(core_path, catalog_uuid=_CATALOG_UUID)
    _create_legacy_artifacts(
        root / "volumes.artifacts.sqlite",
        catalog_uuid=artifact_catalog_uuid,
    )
    return core_path


def test_migration_merges_a_legacy_pair_without_filtering_analysis_rows(
    tmp_path: Path,
) -> None:
    core_path = _create_legacy_pair(tmp_path)

    result = migrate_legacy_library_database(
        core_path,
        confirm=MIGRATION_CONFIRMATION,
    )

    assert result.library_path == core_path
    assert result.catalog_uuid == _CATALOG_UUID
    assert result.roots == ("D:/Music/House",)
    assert result.copied_rows == {
        "tracks": 1,
        "tags": 1,
        "sonara_features": 1,
        "maest_genres": 1,
        "maest_embeddings": 1,
        "mert_embeddings": 1,
        "muq_embeddings": 1,
        "mulan_embeddings": 0,
        "clap_embeddings": 1,
        "classifier_scores": 1,
        "likes": 1,
        "pair_feedback": 1,
        "transition_feedback": 1,
    }
    assert result.fts_rows == 1
    assert result.integrity_check == "ok"
    assert result.foreign_key_violations == 0
    assert not (tmp_path / "volumes.artifacts.sqlite").exists()

    with sqlite3.connect(core_path) as connection:
        library = connection.execute(
            "SELECT catalog_uuid, schema_version, roots_json FROM library"
        ).fetchone()
        assert library == (_CATALOG_UUID, 1, '["D:/Music/House"]')
        assert connection.execute("SELECT COUNT(*) FROM sonara_features").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM mert_embeddings").fetchone()[0] == 1
        assert connection.execute(
            "SELECT embedding_blob FROM mert_embeddings WHERE track_id = 7"
        ).fetchone()[0] == b"\x00\x00\x80?"
        assert connection.execute(
            "SELECT COUNT(*) FROM track_search_fts WHERE track_search_fts MATCH 'legacy'"
        ).fetchone()[0] == 1

    assert (result.backup_dir / "legacy-volumes.sqlite").is_file()
    assert (result.backup_dir / "legacy-volumes.artifacts.sqlite").is_file()
    receipt = json.loads((result.backup_dir / "migration-receipt.json").read_text(encoding="utf-8"))
    assert receipt["excluded"] == [
        {
            "database": "core",
            "reason": "obsolete derived counters",
            "row_count": 1,
            "table": "library_settings",
        }
    ]


def test_migration_keeps_legacy_files_when_catalogs_do_not_match(tmp_path: Path) -> None:
    core_path = _create_legacy_pair(tmp_path, artifact_catalog_uuid="another-catalog")

    with pytest.raises(LegacyLibraryMigrationError, match="different library catalogs"):
        migrate_legacy_library_database(
            core_path,
            confirm=MIGRATION_CONFIRMATION,
        )

    with sqlite3.connect(core_path) as connection:
        assert connection.execute("SELECT catalog_uuid FROM library_catalog").fetchone()[0] == _CATALOG_UUID
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='library'"
        ).fetchone() is None
    assert (tmp_path / "volumes.artifacts.sqlite").is_file()


def test_migrate_database_cli_runs_the_explicit_legacy_pair_migration(
    tmp_path: Path,
) -> None:
    core_path = _create_legacy_pair(tmp_path)

    result = CliRunner().invoke(
        cli.app,
        [
            "migrate-database",
            "--db",
            str(core_path),
            "--confirm",
            MIGRATION_CONFIRMATION,
        ],
    )

    assert result.exit_code == 0, result.output
    assert f"library={core_path.resolve()}" in result.output
    assert "integrity_check=ok foreign_key_violations=0" in result.output
