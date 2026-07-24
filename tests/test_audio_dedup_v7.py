from __future__ import annotations

from pathlib import Path
import struct

import pytest

from dj_track_similarity.analysis_contracts import (
    ContractIdentity,
    register_contract,
)
from dj_track_similarity.analysis_models import ACTIVE_CONTRACT_SETTING_PREFIX
from dj_track_similarity.audio_dedup_jobs import (
    APPLY_CONFIRMATION,
    AudioDedupJobManager,
    _load_audio_dedup_core,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.track_models import FileTags, ScannedFile, TrackIdentity


_SCANNED_AT = "2026-07-24T00:00:00.000000Z"


def _scan(
    database: LibraryDatabase,
    path: Path,
    *,
    title: str,
) -> TrackIdentity:
    stat = path.stat()
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_duration_seconds=300.0,
        ),
        tags=FileTags(
            title=title,
            artist="Artist",
            album="Album",
            tag_bpm=128.0,
            tag_key="8A",
            genres=("Test",),
        ),
        scanned_at=_SCANNED_AT,
    ).identity


def _candidate(
    database: LibraryDatabase,
    identity: TrackIdentity,
    path: Path,
) -> dict[str, object]:
    state = database.get_track_file_states_by_ids((identity.track_id,))[0]
    return {
        "track_id": identity.track_id,
        "catalog_uuid": identity.catalog_uuid,
        "track_uuid": identity.track_uuid,
        "content_generation": identity.content_generation,
        "path": state.file_path,
        "size": state.file_size_bytes,
        "file_modified_ns": state.file_modified_ns,
        "decision": "delete_candidate",
        "safe_to_delete": "true_candidate",
    }


def _payload(*candidates: dict[str, object]) -> dict[str, object]:
    return {
        "groups": [
            {
                "candidate_deletes": list(candidates),
            }
        ]
    }


@pytest.mark.parametrize(
    "confirmation",
    [
        None,
        "",
        "apply delete",
        "APPLY DELETE ",
        " APPLY DELETE",
        "APPLY  DELETE",
        "DELETE",
    ],
)
def test_apply_requires_exact_confirmation(
    tmp_path: Path,
    confirmation: str | None,
) -> None:
    manager = AudioDedupJobManager(
        LibraryDatabase(tmp_path / "library.sqlite")
    )

    with pytest.raises(ValueError, match="APPLY DELETE"):
        manager.create_job(
            root=tmp_path,
            apply=True,
            confirmation=confirmation,
        )

    assert APPLY_CONFIRMATION == "APPLY DELETE"


@pytest.mark.parametrize(
    ("response", "accepted"),
    [
        ("APPLY DELETE", True),
        ("APPLY DELETE ", False),
        (" APPLY DELETE", False),
        ("apply delete", False),
    ],
)
def test_cli_prompt_requires_exact_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    response: str,
    accepted: bool,
) -> None:
    core = _load_audio_dedup_core()
    monkeypatch.setattr("builtins.input", lambda _prompt: response)

    assert core.confirm_apply(
        [{}],
        Path("C:/fixture/library.sqlite"),
        Path("C:/fixture/music"),
    ) is accepted


def test_report_reader_carries_public_v7_identity(
    tmp_path: Path,
) -> None:
    core = _load_audio_dedup_core()
    root = tmp_path / "music"
    root.mkdir()
    audio_path = root / "track.wav"
    audio_path.write_bytes(b"fixture")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _scan(database, audio_path, title="Track")

    records = core.load_tracks(
        database,
        root=root,
        path_contains=[],
    )

    assert len(records) == 1
    record = records[0]
    assert (
        record.catalog_uuid,
        record.track_uuid,
        record.content_generation,
    ) == (
        identity.catalog_uuid,
        identity.track_uuid,
        identity.content_generation,
    )
    report_track = core.track_payload(
        record,
        include_keeper_reasons=False,
    )
    assert report_track["catalog_uuid"] == identity.catalog_uuid
    assert report_track["track_uuid"] == identity.track_uuid
    assert report_track["content_generation"] == 1
    assert report_track["file_modified_ns"] == audio_path.stat().st_mtime_ns


def test_report_reader_rejects_nonunit_active_l2_embedding(
    tmp_path: Path,
) -> None:
    core = _load_audio_dedup_core()
    root = tmp_path / "music"
    root.mkdir()
    audio_path = root / "track.wav"
    audio_path.write_bytes(b"fixture")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _scan(database, audio_path, title="Track")
    contract = ContractIdentity(
        analysis_family="mert",
        output_kind="embedding",
        model_name="mert-test",
        model_version="1",
        dim=2,
        encoding="float32-le",
        normalization="l2",
    )
    with database.connect() as core_connection:
        register_contract(core_connection, contract)
        core_connection.execute(
            """
            INSERT INTO library_settings(
                setting_key, setting_value, updated_at
            ) VALUES (?, ?, ?)
            """,
            (
                f"{ACTIVE_CONTRACT_SETTING_PREFIX}.mert.embedding",
                contract.contract_hash,
                _SCANNED_AT,
            ),
        )
        core_connection.commit()
    with database.connect_artifacts() as artifacts:
        artifacts.execute(
            """
            INSERT INTO mert_embeddings(
                track_id, track_uuid, content_generation,
                contract_hash, dim, normalization,
                embedding_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, 2, 'l2', ?, ?)
            """,
            (
                identity.track_id,
                identity.track_uuid,
                identity.content_generation,
                contract.contract_hash,
                struct.pack("<2f", 2.0, 0.0),
                _SCANNED_AT,
            ),
        )
        artifacts.commit()

    records = core.load_tracks(
        database,
        root=root,
        path_contains=[],
    )

    assert len(records) == 1
    assert "mert" not in records[0].embeddings


def test_apply_uses_generation_cas_and_leaves_stale_candidate_file(
    tmp_path: Path,
) -> None:
    core = _load_audio_dedup_core()
    root = tmp_path / "music"
    root.mkdir()
    audio_path = root / "duplicate.wav"
    audio_path.write_bytes(b"old")
    database = LibraryDatabase(tmp_path / "library.sqlite")
    old_identity = _scan(database, audio_path, title="Old")
    stale_candidate = _candidate(database, old_identity, audio_path)

    audio_path.write_bytes(b"new-content")
    new_identity = _scan(database, audio_path, title="New")
    assert new_identity.content_generation == 2

    result = core.apply_duplicate_deletions(
        database=database,
        root=root,
        payload=_payload(stale_candidate),
        rhythm_lab_db=tmp_path / "missing-lab.sqlite",
    )

    assert result.deleted_track_ids == ()
    assert result.skipped == (
        f"track_id={old_identity.track_id}: report identity is stale",
    )
    assert audio_path.exists()
    assert database.get_track_identity(old_identity.track_id) == new_identity


def test_apply_removes_only_exact_deleted_track_through_repository(
    tmp_path: Path,
) -> None:
    core = _load_audio_dedup_core()
    root = tmp_path / "music"
    root.mkdir()
    delete_path = root / "duplicate.wav"
    keep_path = root / "keep.wav"
    outside_path = tmp_path / "outside.wav"
    for path in (delete_path, keep_path, outside_path):
        path.write_bytes(path.name.encode("utf-8"))
    database = LibraryDatabase(tmp_path / "library.sqlite")
    delete_identity = _scan(database, delete_path, title="Delete")
    keep_identity = _scan(database, keep_path, title="Keep")
    outside_identity = _scan(database, outside_path, title="Outside")

    with database.connect_artifacts() as artifacts:
        artifacts.execute(
            """
            INSERT INTO sonara_fingerprints(
                track_id, track_uuid, content_generation,
                contract_hash, fingerprint_version, word_count,
                byte_order, fingerprint_blob, analyzed_at
            ) VALUES (?, ?, ?, 'sha256:test', '1', 1, 'little', ?, ?)
            """,
            (
                delete_identity.track_id,
                delete_identity.track_uuid,
                delete_identity.content_generation,
                b"\x01\x00\x00\x00",
                _SCANNED_AT,
            ),
        )
        artifacts.commit()

    result = core.apply_duplicate_deletions(
        database=database,
        root=root,
        payload=_payload(
            _candidate(database, delete_identity, delete_path),
            _candidate(database, outside_identity, outside_path),
        ),
        rhythm_lab_db=tmp_path / "missing-lab.sqlite",
    )

    assert result.deleted_track_ids == (delete_identity.track_id,)
    assert result.skipped == (
        f"track_id={outside_identity.track_id}: path outside root",
    )
    assert not delete_path.exists()
    assert keep_path.exists()
    assert outside_path.exists()
    assert database.get_track_identity(delete_identity.track_id) is None
    assert database.get_track_identity(keep_identity.track_id) == keep_identity
    assert (
        database.get_track_identity(outside_identity.track_id)
        == outside_identity
    )
    with database.connect_artifacts() as artifacts:
        assert artifacts.execute(
            "SELECT COUNT(*) FROM sonara_fingerprints"
        ).fetchone()[0] == 0
