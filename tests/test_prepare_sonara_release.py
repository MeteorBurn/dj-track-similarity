from __future__ import annotations

import hashlib
import inspect
import json
import sqlite3
import struct
from contextlib import closing
from pathlib import Path

import pytest

import dj_track_similarity.prepare_sonara_release as release_prepare
from dj_track_similarity.analysis_models import (
    SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,
    AnalysisOutput,
    active_contract_setting_key,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.prepare_sonara_release import (
    CONFIRM_STRING,
    LockHeldError,
    PrepareSonaraReleaseError,
    prepare_sonara_release,
    validate_backup_dir,
    validate_confirm,
)
from dj_track_similarity.sonara_contract import (
    SONARA_EXPECTED_VERSION,
    sonara_runtime_contracts,
)


class PreviousSonara:
    __version__ = SONARA_EXPECTED_VERSION
    SIMILARITY_VERSION = 2
    __sonara_build_id__ = "sha256:" + "1" * 64
    __sonara_vocalness_model_id__ = "sonara-vocalness-v2"
    __sonara_vocalness_model_build_id__ = "sha256:" + "2" * 64


class CurrentSonara(PreviousSonara):
    __sonara_build_id__ = "sha256:" + "3" * 64
    __sonara_vocalness_model_build_id__ = "sha256:" + "4" * 64


class FutureSonara(CurrentSonara):
    __sonara_build_id__ = "sha256:" + "5" * 64


def _outputs(sonara_module: object) -> tuple[AnalysisOutput, ...]:
    return tuple(
        AnalysisOutput(identity)
        for identity in sonara_runtime_contracts(sonara_module).identities
    )


def _new_library(tmp_path: Path) -> tuple[LibraryDatabase, Path]:
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return LibraryDatabase(tmp_path / "library.sqlite"), backup_dir


def _insert_track(connection: sqlite3.Connection) -> int:
    timestamp = "2026-07-24T00:00:00+00:00"
    cursor = connection.execute(
        """
        INSERT INTO tracks (
            track_uuid,
            file_path,
            file_size_bytes,
            file_modified_ns,
            content_generation,
            last_scanned_at,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "track-uuid-1",
            r"C:\Music\track.wav",
            1024,
            1,
            1,
            timestamp,
            timestamp,
            timestamp,
        ),
    )
    track_id = int(cursor.lastrowid)
    connection.execute(
        """
        INSERT INTO likes(track_id, liked_at)
        VALUES (?, ?)
        """,
        (track_id, timestamp),
    )
    return track_id


def _insert_core_sonara(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    contract_hash: str,
) -> None:
    connection.execute(
        """
        INSERT INTO sonara (
            track_id,
            content_generation,
            contract_hash,
            mfcc_mean_blob,
            chroma_mean_blob,
            spectral_contrast_mean_blob,
            analyzed_at
        ) VALUES (?, 1, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            contract_hash,
            struct.pack("<13f", *([0.0] * 13)),
            struct.pack("<12f", *([0.0] * 12)),
            struct.pack("<7f", *([0.0] * 7)),
            "2026-07-24T00:01:00+00:00",
        ),
    )


def _insert_artifact_sonara(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    outputs: tuple[AnalysisOutput, ...],
) -> None:
    by_kind = {output.contract.output_kind: output for output in outputs}
    timestamp = "2026-07-24T00:01:00+00:00"
    connection.execute(
        """
        INSERT INTO sonara_timeline (
            track_id,
            track_uuid,
            content_generation,
            contract_hash,
            payload_json,
            analyzed_at
        ) VALUES (?, 'track-uuid-1', 1, ?, '{}', ?)
        """,
        (track_id, by_kind["timeline"].contract_hash, timestamp),
    )
    embedding = by_kind["embedding"].contract
    connection.execute(
        """
        INSERT INTO sonara_similarity_embeddings (
            track_id,
            track_uuid,
            content_generation,
            contract_hash,
            dim,
            normalization,
            embedding_blob,
            analyzed_at
        ) VALUES (?, 'track-uuid-1', 1, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            embedding.contract_hash,
            embedding.dim,
            embedding.normalization,
            bytes(embedding.dim * 4),
            timestamp,
        ),
    )
    fingerprint = by_kind["fingerprint"].contract
    fingerprint_parameters = dict(fingerprint.parameters)
    connection.execute(
        """
        INSERT INTO sonara_fingerprints (
            track_id,
            track_uuid,
            content_generation,
            contract_hash,
            fingerprint_version,
            word_count,
            byte_order,
            fingerprint_blob,
            analyzed_at
        ) VALUES (?, 'track-uuid-1', 1, ?, ?, 1, 'little', ?, ?)
        """,
        (
            track_id,
            fingerprint.contract_hash,
            fingerprint_parameters["fingerprint_version"],
            b"\x01\x00\x00\x00",
            timestamp,
        ),
    )


def _insert_classifier_score(
    connection: sqlite3.Connection,
    *,
    track_id: int,
    classifier_key: str,
    uses_sonara: int,
    release_hash: str | None,
) -> None:
    connection.execute(
        """
        INSERT INTO classifier_scores (
            track_id,
            classifier_key,
            content_generation,
            model_id,
            feature_set,
            feature_manifest_hash,
            required_outputs_hash,
            uses_sonara,
            sonara_release_hash,
            positive_label,
            predicted_class,
            score_bucket,
            score,
            confidence,
            probabilities_json,
            analyzed_at
        ) VALUES (?, ?, 1, 'model', ?, ?, ?, ?, ?, 'yes', 'yes',
                  'high', 0.9, 0.8, '{"no":0.1,"yes":0.9}', ?)
        """,
        (
            track_id,
            classifier_key,
            "sonara+maest" if uses_sonara else "mert",
            "sha256:" + "9" * 64,
            "sha256:" + "8" * 64,
            uses_sonara,
            release_hash,
            "2026-07-24T00:02:00+00:00",
        ),
    )


def _seed_previous_release(
    database: LibraryDatabase,
) -> tuple[int, tuple[AnalysisOutput, ...]]:
    previous_outputs = _outputs(PreviousSonara)
    seed_backup_dir = database.path.parent / "previous-release-backups"
    seed_backup_dir.mkdir(exist_ok=True)
    prepare_sonara_release(
        database,
        backup_dir=seed_backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=PreviousSonara,
    )
    current_release_hash = sonara_runtime_contracts(CurrentSonara).release_hash
    previous_release_hash = previous_outputs[0].contract.release_hash

    with closing(database.connect()) as core:
        track_id = _insert_track(core)
        _insert_core_sonara(
            core,
            track_id=track_id,
            contract_hash=previous_outputs[0].contract_hash,
        )
        _insert_classifier_score(
            core,
            track_id=track_id,
            classifier_key="old-sonara",
            uses_sonara=1,
            release_hash=previous_release_hash,
        )
        _insert_classifier_score(
            core,
            track_id=track_id,
            classifier_key="already-new-sonara",
            uses_sonara=1,
            release_hash=current_release_hash,
        )
        _insert_classifier_score(
            core,
            track_id=track_id,
            classifier_key="mert-only",
            uses_sonara=0,
            release_hash=None,
        )
        core.commit()

    with closing(database.connect_artifacts()) as artifacts:
        _insert_artifact_sonara(
            artifacts,
            track_id=track_id,
            outputs=previous_outputs,
        )
        artifacts.execute(
            """
            INSERT INTO mert_embeddings (
                track_id,
                track_uuid,
                content_generation,
                contract_hash,
                dim,
                normalization,
                embedding_blob,
                analyzed_at
            ) VALUES (?, 'track-uuid-1', 1, ?, 1, 'none', ?, ?)
            """,
            (
                track_id,
                "sha256:" + "8" * 64,
                struct.pack("<f", 0.5),
                "2026-07-24T00:03:00+00:00",
            ),
        )
        artifacts.commit()
    return track_id, previous_outputs


def _table_count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_public_api_is_v7_only_and_requires_confirmation(tmp_path: Path) -> None:
    signature = inspect.signature(prepare_sonara_release)

    assert tuple(signature.parameters) == (
        "database",
        "backup_dir",
        "confirm",
        "sonara_module",
    )
    for removed_name in (
        "db_path",
        "sonara_outputs",
        "new_release_hash",
        "previous_release_hash",
    ):
        assert removed_name not in signature.parameters

    with pytest.raises(ValueError, match="must be exactly"):
        validate_confirm("yes")
    validate_confirm(CONFIRM_STRING)

    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="does not exist"):
        validate_backup_dir(missing)
    assert validate_backup_dir(tmp_path) == tmp_path.resolve()


def test_fresh_library_activates_exact_four_contracts_and_backs_up(
    tmp_path: Path,
) -> None:
    database, backup_dir = _new_library(tmp_path)
    contracts = sonara_runtime_contracts(CurrentSonara)

    receipt = prepare_sonara_release(
        database,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=CurrentSonara,
    )

    assert receipt["stage"] == "completed"
    assert receipt["release_hash"] == contracts.release_hash
    assert len(str(receipt["release_hash"])) == len("sha256:") + 64
    assert receipt["contract_hashes"] == {
        identity.output_kind: identity.contract_hash
        for identity in contracts.identities
    }
    assert receipt["activation_result"] == {
        "core_rows_deleted": 0,
        "artifact_rows_deleted": 0,
        "classifier_rows_deleted": 0,
    }

    backups = receipt["backups"]
    assert isinstance(backups, dict)
    for kind in ("core", "artifacts"):
        record = backups[kind]
        assert isinstance(record, dict)
        backup_path = Path(record["path"])
        assert backup_path.is_file()
        assert record["sha256"] == _file_hash(backup_path)
        with closing(sqlite3.connect(backup_path)) as connection:
            assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"

    receipt_path = database.path.with_name(
        f".{database.path.name}.prepare-sonara-release.json"
    )
    assert _read_json(receipt_path) == receipt
    archive_path = backup_dir / (
        f"{database.path.stem}.pre-sonara-"
        f"{str(receipt['operation_id']).removeprefix('sha256:')}.receipt.json"
    )
    assert _read_json(archive_path) == receipt

    expected_settings = {
        SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY: contracts.release_hash,
        **{
            active_contract_setting_key(
                AnalysisOutput(identity)
            ): identity.contract_hash
            for identity in contracts.identities
        },
    }
    with closing(database.connect()) as core:
        actual_settings = {
            str(row[0]): str(row[1])
            for row in core.execute(
                """
                SELECT setting_key, setting_value
                FROM library_settings
                WHERE setting_key = ?
                   OR setting_key LIKE 'analysis.active_contract.sonara.%'
                """,
                (SONARA_ACTIVE_RELEASE_HASH_SETTING_KEY,),
            )
        }
        assert actual_settings == expected_settings
        assert _table_count(core, "contracts") == 4


def test_activation_clears_every_sonara_row_and_preserves_independent_data(
    tmp_path: Path,
) -> None:
    database, backup_dir = _new_library(tmp_path)
    _seed_previous_release(database)

    receipt = prepare_sonara_release(
        database,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=CurrentSonara,
    )

    assert receipt["activation_result"] == {
        "core_rows_deleted": 1,
        "artifact_rows_deleted": 3,
        "classifier_rows_deleted": 2,
    }
    with closing(database.connect()) as core:
        assert _table_count(core, "tracks") == 1
        assert _table_count(core, "likes") == 1
        assert _table_count(core, "sonara") == 0
        classifier_keys = {
            str(row[0])
            for row in core.execute("SELECT classifier_key FROM classifier_scores")
        }
        assert classifier_keys == {"mert-only"}
    with closing(database.connect_artifacts()) as artifacts:
        assert _table_count(artifacts, "sonara_timeline") == 0
        assert _table_count(artifacts, "sonara_similarity_embeddings") == 0
        assert _table_count(artifacts, "sonara_fingerprints") == 0
        assert _table_count(artifacts, "mert_embeddings") == 1

    backups = receipt["backups"]
    assert isinstance(backups, dict)
    core_backup = Path(backups["core"]["path"])
    artifacts_backup = Path(backups["artifacts"]["path"])
    with closing(sqlite3.connect(core_backup)) as core:
        assert _table_count(core, "sonara") == 1
        assert _table_count(core, "classifier_scores") == 3
    with closing(sqlite3.connect(artifacts_backup)) as artifacts:
        assert _table_count(artifacts, "sonara_timeline") == 1
        assert _table_count(artifacts, "sonara_similarity_embeddings") == 1
        assert _table_count(artifacts, "sonara_fingerprints") == 1
        assert _table_count(artifacts, "mert_embeddings") == 1


def test_completed_operation_is_deterministic_and_preserves_new_outputs(
    tmp_path: Path,
) -> None:
    database, backup_dir = _new_library(tmp_path)
    track_id, _ = _seed_previous_release(database)
    current_outputs = _outputs(CurrentSonara)

    first = prepare_sonara_release(
        database,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=CurrentSonara,
    )
    with closing(database.connect()) as core:
        _insert_core_sonara(
            core,
            track_id=track_id,
            contract_hash=current_outputs[0].contract_hash,
        )
        core.commit()
    with closing(database.connect_artifacts()) as artifacts:
        _insert_artifact_sonara(
            artifacts,
            track_id=track_id,
            outputs=current_outputs,
        )
        artifacts.commit()

    backup_paths = {Path(record["path"]) for record in first["backups"].values()}
    before = {
        path: (path.stat().st_mtime_ns, _file_hash(path)) for path in backup_paths
    }
    second = prepare_sonara_release(
        database,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=CurrentSonara,
    )

    assert second == first
    assert {
        path: (path.stat().st_mtime_ns, _file_hash(path)) for path in backup_paths
    } == before
    with closing(database.connect()) as core:
        assert _table_count(core, "sonara") == 1
    with closing(database.connect_artifacts()) as artifacts:
        assert _table_count(artifacts, "sonara_timeline") == 1
        assert _table_count(artifacts, "sonara_similarity_embeddings") == 1
        assert _table_count(artifacts, "sonara_fingerprints") == 1


@pytest.mark.parametrize("crash_stage", ["started", "backed_up"])
def test_resume_before_gateway(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_stage: str,
) -> None:
    database, backup_dir = _new_library(tmp_path)
    _seed_previous_release(database)

    def crash(stage: str) -> None:
        if stage == crash_stage:
            raise RuntimeError(f"crash after {stage}")

    monkeypatch.setattr(release_prepare, "_stage_checkpoint", crash)
    with pytest.raises(RuntimeError, match=f"crash after {crash_stage}"):
        prepare_sonara_release(
            database,
            backup_dir=backup_dir,
            confirm=CONFIRM_STRING,
            sonara_module=CurrentSonara,
        )

    receipt_path = database.path.with_name(
        f".{database.path.name}.prepare-sonara-release.json"
    )
    pending = _read_json(receipt_path)
    assert pending["stage"] == crash_stage

    monkeypatch.setattr(release_prepare, "_stage_checkpoint", lambda _stage: None)
    completed = prepare_sonara_release(
        database,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=CurrentSonara,
    )
    assert completed["stage"] == "completed"
    with closing(database.connect()) as core:
        assert _table_count(core, "sonara") == 0
        assert _table_count(core, "classifier_scores") == 1
    with closing(database.connect_artifacts()) as artifacts:
        assert _table_count(artifacts, "sonara_timeline") == 0
        assert _table_count(artifacts, "sonara_similarity_embeddings") == 0
        assert _table_count(artifacts, "sonara_fingerprints") == 0


def test_resume_after_gateway_commit_is_safe_for_same_release_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, backup_dir = _new_library(tmp_path)
    track_id, _ = _seed_previous_release(database)
    current_outputs = _outputs(CurrentSonara)

    def crash(stage: str) -> None:
        if stage == "gateway_committed":
            raise RuntimeError("crash after gateway commit")

    monkeypatch.setattr(release_prepare, "_stage_checkpoint", crash)
    with pytest.raises(RuntimeError, match="crash after gateway commit"):
        prepare_sonara_release(
            database,
            backup_dir=backup_dir,
            confirm=CONFIRM_STRING,
            sonara_module=CurrentSonara,
        )

    with closing(database.connect()) as core:
        _insert_core_sonara(
            core,
            track_id=track_id,
            contract_hash=current_outputs[0].contract_hash,
        )
        _insert_classifier_score(
            core,
            track_id=track_id,
            classifier_key="new-sonara",
            uses_sonara=1,
            release_hash=current_outputs[0].contract.release_hash,
        )
        core.commit()
    with closing(database.connect_artifacts()) as artifacts:
        _insert_artifact_sonara(
            artifacts,
            track_id=track_id,
            outputs=current_outputs,
        )
        artifacts.commit()

    monkeypatch.setattr(release_prepare, "_stage_checkpoint", lambda _stage: None)
    completed = prepare_sonara_release(
        database,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=CurrentSonara,
    )

    assert completed["stage"] == "completed"
    assert completed["activation_result"] == {
        "core_rows_deleted": 0,
        "artifact_rows_deleted": 0,
        "classifier_rows_deleted": 0,
    }
    with closing(database.connect()) as core:
        assert _table_count(core, "sonara") == 1
        assert {
            str(row[0])
            for row in core.execute("SELECT classifier_key FROM classifier_scores")
        } == {"mert-only", "new-sonara"}
    with closing(database.connect_artifacts()) as artifacts:
        assert _table_count(artifacts, "sonara_timeline") == 1
        assert _table_count(artifacts, "sonara_similarity_embeddings") == 1
        assert _table_count(artifacts, "sonara_fingerprints") == 1


def test_corrupt_recorded_backup_blocks_resume_before_gateway(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, backup_dir = _new_library(tmp_path)
    previous_outputs = _seed_previous_release(database)[1]

    def crash(stage: str) -> None:
        if stage == "backed_up":
            raise RuntimeError("crash after backup")

    monkeypatch.setattr(release_prepare, "_stage_checkpoint", crash)
    with pytest.raises(RuntimeError, match="crash after backup"):
        prepare_sonara_release(
            database,
            backup_dir=backup_dir,
            confirm=CONFIRM_STRING,
            sonara_module=CurrentSonara,
        )

    receipt_path = database.path.with_name(
        f".{database.path.name}.prepare-sonara-release.json"
    )
    pending = _read_json(receipt_path)
    core_backup = Path(pending["backups"]["core"]["path"])
    with core_backup.open("ab") as stream:
        stream.write(b"corrupt")

    monkeypatch.setattr(release_prepare, "_stage_checkpoint", lambda _stage: None)
    with pytest.raises(PrepareSonaraReleaseError, match="size does not match"):
        prepare_sonara_release(
            database,
            backup_dir=backup_dir,
            confirm=CONFIRM_STRING,
            sonara_module=CurrentSonara,
        )

    active_core = database.active_analysis_output("sonara", "core")
    assert active_core is not None
    assert active_core.contract_hash == previous_outputs[0].contract_hash


def test_backup_catalog_mismatch_blocks_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, backup_dir = _new_library(tmp_path)
    _seed_previous_release(database)

    def crash(stage: str) -> None:
        if stage == "backed_up":
            raise RuntimeError("crash after backup")

    monkeypatch.setattr(release_prepare, "_stage_checkpoint", crash)
    with pytest.raises(RuntimeError, match="crash after backup"):
        prepare_sonara_release(
            database,
            backup_dir=backup_dir,
            confirm=CONFIRM_STRING,
            sonara_module=CurrentSonara,
        )

    other = LibraryDatabase(tmp_path / "other.sqlite")
    receipt_path = database.path.with_name(
        f".{database.path.name}.prepare-sonara-release.json"
    )
    pending = _read_json(receipt_path)
    artifacts_record = pending["backups"]["artifacts"]
    artifacts_backup = Path(artifacts_record["path"])
    replacement = artifacts_backup.with_suffix(".replacement")
    with (
        closing(other.connect_artifacts()) as source,
        closing(sqlite3.connect(replacement)) as target,
    ):
        source.backup(target)
        target.execute("PRAGMA journal_mode = DELETE")
    replacement.replace(artifacts_backup)
    artifacts_record["size_bytes"] = artifacts_backup.stat().st_size
    artifacts_record["sha256"] = _file_hash(artifacts_backup)
    release_prepare._atomic_write_json(receipt_path, pending)

    monkeypatch.setattr(release_prepare, "_stage_checkpoint", lambda _stage: None)
    with pytest.raises(
        PrepareSonaraReleaseError,
        match="another library catalog",
    ):
        prepare_sonara_release(
            database,
            backup_dir=backup_dir,
            confirm=CONFIRM_STRING,
            sonara_module=CurrentSonara,
        )


def test_pending_receipt_for_another_runtime_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, backup_dir = _new_library(tmp_path)

    def crash(stage: str) -> None:
        if stage == "started":
            raise RuntimeError("crash after receipt")

    monkeypatch.setattr(release_prepare, "_stage_checkpoint", crash)
    with pytest.raises(RuntimeError, match="crash after receipt"):
        prepare_sonara_release(
            database,
            backup_dir=backup_dir,
            confirm=CONFIRM_STRING,
            sonara_module=CurrentSonara,
        )

    monkeypatch.setattr(release_prepare, "_stage_checkpoint", lambda _stage: None)
    with pytest.raises(
        PrepareSonaraReleaseError,
        match="different SONARA release activation is incomplete",
    ):
        prepare_sonara_release(
            database,
            backup_dir=backup_dir,
            confirm=CONFIRM_STRING,
            sonara_module=FutureSonara,
        )


def test_corrupt_receipt_and_concurrent_lock_fail_closed(
    tmp_path: Path,
) -> None:
    database, backup_dir = _new_library(tmp_path)
    receipt_path = database.path.with_name(
        f".{database.path.name}.prepare-sonara-release.json"
    )
    receipt_path.write_text("{broken", encoding="utf-8")

    with pytest.raises(PrepareSonaraReleaseError, match="invalid JSON"):
        prepare_sonara_release(
            database,
            backup_dir=backup_dir,
            confirm=CONFIRM_STRING,
            sonara_module=CurrentSonara,
        )

    receipt_path.unlink()
    with release_prepare._release_file_lock(database.path):
        with pytest.raises(LockHeldError, match="already running"):
            prepare_sonara_release(
                database,
                backup_dir=backup_dir,
                confirm=CONFIRM_STRING,
                sonara_module=CurrentSonara,
            )


def test_completed_receipt_allows_later_distinct_release(
    tmp_path: Path,
) -> None:
    database, backup_dir = _new_library(tmp_path)
    _seed_previous_release(database)

    current = prepare_sonara_release(
        database,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=CurrentSonara,
    )
    future = prepare_sonara_release(
        database,
        backup_dir=backup_dir,
        confirm=CONFIRM_STRING,
        sonara_module=FutureSonara,
    )

    assert future["stage"] == "completed"
    assert future["operation_id"] != current["operation_id"]
    assert future["release_hash"] == sonara_runtime_contracts(FutureSonara).release_hash
    archives = sorted(backup_dir.glob("*.receipt.json"))
    assert len(archives) == 2
