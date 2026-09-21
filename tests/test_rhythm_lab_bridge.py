from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

import dj_track_similarity.rhythm_lab_launcher as launcher
from dj_track_similarity.rhythm_lab_collections import (
    DEFAULT_RHYTHM_LAB_LABELS_FILENAME,
    RhythmLabCollectionSelection,
    RhythmLabCollections,
    RhythmLabTrackSelection,
    default_rhythm_lab_labels_path,
)


def _selection(
    catalog_uuid: str,
    *tracks: tuple[str, str, str],
) -> RhythmLabCollectionSelection:
    return RhythmLabCollectionSelection(
        catalog_uuid=catalog_uuid,
        tracks=tuple(
            RhythmLabTrackSelection(
                catalog_uuid=catalog_uuid,
                track_uuid=track_uuid,
                selected_path=selected_path,
                content_key=content_key,
            )
            for track_uuid, selected_path, content_key in tracks
        ),
    )


_V1_LABELS_DDL = """
    CREATE TABLE classifier_labels (
        classifier_key TEXT NOT NULL,
        catalog_uuid TEXT NOT NULL,
        track_uuid TEXT NOT NULL,
        selected_path TEXT NOT NULL,
        file_size_bytes INTEGER NOT NULL,
        file_modified_ns INTEGER NOT NULL,
        label TEXT NOT NULL,
        note TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(classifier_key, catalog_uuid, track_uuid, selected_path)
    )
"""


def test_default_rhythm_lab_labels_path_is_stable_current() -> None:
    labels_path = default_rhythm_lab_labels_path()

    assert labels_path.name == DEFAULT_RHYTHM_LAB_LABELS_FILENAME
    assert labels_path.name == "rhythm_lab.sqlite"
    assert labels_path.parent.name == "database"


def test_collection_repository_rejects_legacy_labels_without_mutation(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "rhythm_lab.sqlite"
    with sqlite3.connect(legacy_path) as connection:
        connection.execute(_V1_LABELS_DDL)
        connection.execute(
            """
            INSERT INTO classifier_labels (
                classifier_key, catalog_uuid, track_uuid, selected_path,
                file_size_bytes, file_modified_ns, label
            ) VALUES ('legacy-profile', 'catalog-old', 'uuid-17', 'C:/Music/legacy.wav', 1, 2, 'positive')
            """
        )
    wal_path = Path(f"{legacy_path}-wal")
    shm_path = Path(f"{legacy_path}-shm")
    wal_path.write_bytes(b"preserved collection WAL")
    shm_path.write_bytes(b"preserved collection SHM")
    before = {
        path: path.read_bytes()
        for path in (legacy_path, wal_path, shm_path)
    }

    with pytest.raises(
        RuntimeError,
        match=r"retired pre-content-identity layout.*no longer supported",
    ):
        RhythmLabCollections(legacy_path)

    assert {
        path: path.read_bytes()
        for path in (legacy_path, wal_path, shm_path)
    } == before


def test_collection_repository_rejects_partial_current_labels_before_ddl(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / "partial.sqlite"
    with sqlite3.connect(labels_path) as connection:
        connection.execute(
            """
            CREATE TABLE classifier_labels (
                classifier_key TEXT NOT NULL,
                content_key TEXT NOT NULL,
                label TEXT NOT NULL
            )
            """
        )
    before = labels_path.read_bytes()

    with pytest.raises(RuntimeError, match="not the canonical structure"):
        RhythmLabCollections(labels_path)

    assert labels_path.read_bytes() == before
    with sqlite3.connect(
        f"file:{labels_path.as_posix()}?mode=ro&immutable=1",
        uri=True,
    ) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert tables == {"classifier_labels"}


def test_collection_repository_rejects_wal_visible_legacy_identity_before_ddl(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "rhythm_lab.sqlite"
    setup = sqlite3.connect(legacy_path)
    try:
        assert setup.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
        setup.execute("CREATE TABLE sentinel (value TEXT NOT NULL)")
        setup.execute("INSERT INTO sentinel(value) VALUES ('base')")
        setup.commit()
        setup.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        setup.close()

    reader = sqlite3.connect(legacy_path)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT value FROM sentinel").fetchall() == [
            ("base",)
        ]

        writer = sqlite3.connect(legacy_path)
        try:
            writer.execute("PRAGMA wal_autocheckpoint = 0")
            writer.execute(_V1_LABELS_DDL)
            writer.execute(
                """
                INSERT INTO classifier_labels (
                    classifier_key, catalog_uuid, track_uuid, selected_path,
                    file_size_bytes, file_modified_ns, label
                ) VALUES ('wal-profile', 'catalog-old', 'uuid-31', 'C:/Music/wal.wav', 1, 2, 'positive')
                """
            )
            writer.commit()
        finally:
            writer.close()

        wal_path = Path(f"{legacy_path}-wal")
        shm_path = Path(f"{legacy_path}-shm")
        assert wal_path.stat().st_size > 0
        assert shm_path.stat().st_size > 0
        before = {
            path: path.read_bytes()
            for path in (legacy_path, wal_path)
        }
        shm_size_before = shm_path.stat().st_size

        with pytest.raises(RuntimeError, match="retired pre-content-identity layout"):
            RhythmLabCollections(legacy_path)

        # The SHM file is SQLite's transient WAL index; validation reads may
        # update its read marks. Durable database and WAL bytes must not change.
        assert {
            path: path.read_bytes()
            for path in (legacy_path, wal_path)
        } == before
        assert shm_path.stat().st_size == shm_size_before
        with sqlite3.connect(
            f"file:{legacy_path.as_posix()}?mode=ro",
            uri=True,
        ) as observer:
            tables = {
                str(row[0])
                for row in observer.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        assert tables == {"sentinel", "classifier_labels"}
    finally:
        reader.close()


def test_collection_append_never_rebinds_and_replace_is_explicit(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / "rhythm_lab.sqlite"
    collections = RhythmLabCollections(labels_path)
    first = _selection(
        "catalog-a",
        ("uuid-a", "C:/Music/A.wav", "sfp1:a"),
        ("uuid-b", "C:/Music/B.wav", "sfp1:b"),
    )

    saved = collections.save_collection(
        "Main set",
        first,
        source="main_ui_playlist",
        mode="replace",
    )
    assert saved.catalog_uuid == "catalog-a"
    assert saved.track_count == 2

    # The same content under another path or uuid is already in the set.
    append = _selection(
        "catalog-a",
        ("uuid-a", "D:/Relocated/A.wav", "sfp1:a"),
        ("uuid-a2", "D:/Copy/A.wav", "sfp1:a"),
        ("uuid-c", "C:/Music/C.wav", "sfp1:c"),
    )
    appended = collections.append_tracks(saved.id, append)
    assert [
        (
            track.content_key,
            track.track_uuid,
            track.selected_path,
            track.position,
        )
        for track in appended.tracks
    ] == [
        ("sfp1:a", "uuid-a", "C:/Music/A.wav", 1),
        ("sfp1:b", "uuid-b", "C:/Music/B.wav", 2),
        ("sfp1:c", "uuid-c", "C:/Music/C.wav", 3),
    ]

    replacement = _selection(
        "catalog-a",
        ("uuid-a", "D:/Relocated/A.wav", "sfp1:a"),
    )
    replaced = collections.replace_tracks(saved.id, replacement)
    assert [
        (
            track.track_uuid,
            track.selected_path,
        )
        for track in replaced.tracks
    ] == [("uuid-a", "D:/Relocated/A.wav")]

    with sqlite3.connect(labels_path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(review_collection_tracks)"
            ).fetchall()
        }
    assert "source_track_id" not in columns
    assert {
        "content_key",
        "catalog_uuid",
        "track_uuid",
        "selected_path",
    } <= columns


def test_collection_keeps_origin_catalog_and_accepts_content_from_another(
    tmp_path: Path,
) -> None:
    collections = RhythmLabCollections(tmp_path / "rhythm_lab.sqlite")
    original = collections.save_collection(
        "Bound set",
        _selection(
            "catalog-a",
            ("uuid-a", "C:/Music/A.wav", "sfp1:a"),
        ),
        mode="replace",
    )

    collections.save_collection(
        "Bound set",
        _selection(
            "catalog-b",
            ("uuid-b", "C:/Music/B.wav", "sfp1:b"),
            ("uuid-a-in-b", "E:/Music/A.wav", "sfp1:a"),
        ),
        mode="append",
    )

    current = collections.get_collection(original.id)
    assert current.catalog_uuid == "catalog-a"
    assert [(track.content_key, track.catalog_uuid) for track in current.tracks] == [
        ("sfp1:a", "catalog-a"),
        ("sfp1:b", "catalog-b"),
    ]


def test_legacy_collection_schema_is_rejected_without_rewrite(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(labels_path) as connection:
        connection.executescript(
            """
            CREATE TABLE review_collections (
                id INTEGER PRIMARY KEY,
                catalog_uuid TEXT NOT NULL,
                name TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE review_collection_tracks (
                collection_id INTEGER NOT NULL,
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                selected_path TEXT NOT NULL,
                position INTEGER NOT NULL,
                score REAL,
                note TEXT,
                added_at TEXT NOT NULL,
                PRIMARY KEY(collection_id, catalog_uuid, track_uuid)
            );
            """
        )
    before = labels_path.read_bytes()

    with pytest.raises(RuntimeError, match=r"retired pre-content-identity layout.*no longer supported"):
        RhythmLabCollections(labels_path)

    assert labels_path.read_bytes() == before


def test_launcher_passes_verified_catalog_binding_without_opening_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pid_path = tmp_path / "rhythm_lab.pid"
    log_path = tmp_path / "rhythm_lab.log"
    commands: list[list[str]] = []
    port_checks = iter((False, True))

    class _FakeProcess:
        pid = 12345

        def poll(self) -> None:
            return None

    monkeypatch.setattr(launcher, "_bind_to_server_lifetime", lambda _process: None)
    monkeypatch.setattr(launcher, "_pid_path", lambda: pid_path)
    monkeypatch.setattr(launcher, "_log_path", lambda: log_path)
    monkeypatch.setattr(
        launcher,
        "_port_is_open",
        lambda *_args: next(port_checks),
    )
    monkeypatch.setattr(
        launcher,
        "_start_log_mirror",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        launcher.subprocess,
        "Popen",
        lambda command, **_kwargs: (
            commands.append(command) or _FakeProcess()
        ),
    )
    source_path = tmp_path / "library.sqlite"
    binding = launcher.RhythmLabSourceBinding(
        source_db=source_path,
        catalog_uuid="catalog-a",
    )

    result = launcher.launch_rhythm_lab(binding)

    assert source_path.exists() is False
    assert result["source"] == {
        "catalog_uuid": "catalog-a",
        "database_path": str(source_path.resolve()),
    }
    assert commands
    command = commands[0]
    source_index = command.index("--source")
    catalog_index = command.index("--source-catalog-uuid")
    assert command[source_index + 1] == str(source_path.resolve())
    assert command[catalog_index + 1] == "catalog-a"


def test_launcher_switches_managed_source_and_refuses_unverified(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pid_path = tmp_path / "rhythm_lab.pid"
    pid_path.write_text("12345", encoding="utf-8")
    active = launcher.RhythmLabSourceBinding(
        source_db=tmp_path / "first.sqlite",
        catalog_uuid="catalog-a",
    )
    requested = launcher.RhythmLabSourceBinding(
        source_db=tmp_path / "second.sqlite",
        catalog_uuid="catalog-b",
    )
    switch_requests: list[launcher.RhythmLabSourceBinding] = []
    switch_refusal: list[str] = []

    def fake_switch(binding: launcher.RhythmLabSourceBinding) -> dict[str, object]:
        switch_requests.append(binding)
        if switch_refusal:
            raise RuntimeError(switch_refusal[0])
        return {"catalog_uuid": binding.catalog_uuid, "path": str(binding.source_db)}

    monkeypatch.setattr(launcher, "_pid_path", lambda: pid_path)
    monkeypatch.setattr(launcher, "_start_log_mirror", lambda *_args: None)
    monkeypatch.setattr(launcher, "_port_is_open", lambda *_args: True)
    monkeypatch.setattr(launcher, "_managed_process_id", lambda pid: pid)
    monkeypatch.setattr(launcher, "_live_source", lambda: active.as_payload())
    monkeypatch.setattr(launcher, "_request_source_switch", fake_switch)
    launcher._write_source_binding(active)

    # A managed lab on another library is asked to switch; the binding follows.
    result = launcher.launch_rhythm_lab(requested)
    assert result["already_running"] is True
    assert result["switched"] is True
    assert result["switch_error"] is None
    assert result["source"] == requested.as_payload()
    assert switch_requests == [requested]
    assert launcher._read_source_binding() == requested

    # A refusal is reported, not raised; the binding stays with the live source.
    launcher._write_source_binding(active)
    switch_refusal.append("Cannot switch the source while a train operation is running")
    result = launcher.launch_rhythm_lab(requested)
    assert result["switched"] is False
    assert result["switch_error"] == switch_refusal[0]
    assert result["source"] == active.as_payload()
    assert launcher._read_source_binding() == active

    # An unmanaged listener is never switched.
    monkeypatch.setattr(launcher, "_managed_process_id", lambda _pid: None)
    with pytest.raises(RuntimeError, match="cannot be verified"):
        launcher.launch_rhythm_lab(requested)
    assert len(switch_requests) == 2
