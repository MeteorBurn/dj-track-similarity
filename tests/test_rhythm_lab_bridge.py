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
    *tracks: tuple[str, int, str],
) -> RhythmLabCollectionSelection:
    return RhythmLabCollectionSelection(
        catalog_uuid=catalog_uuid,
        tracks=tuple(
            RhythmLabTrackSelection(
                catalog_uuid=catalog_uuid,
                track_uuid=track_uuid,
                content_generation=generation,
                selected_path=selected_path,
            )
            for track_uuid, generation, selected_path in tracks
        ),
    )


def test_default_rhythm_lab_labels_path_is_stable_current() -> None:
    labels_path = default_rhythm_lab_labels_path()

    assert labels_path.name == DEFAULT_RHYTHM_LAB_LABELS_FILENAME
    assert labels_path.name == "rhythm_lab.sqlite"
    assert labels_path.parent.name == "data"


def test_collection_repository_rejects_legacy_labels_without_mutation(
    tmp_path: Path,
) -> None:
    legacy_path = tmp_path / "rhythm_lab.sqlite"
    with sqlite3.connect(legacy_path) as connection:
        connection.execute(
            """
            CREATE TABLE classifier_labels (
                classifier_key TEXT NOT NULL,
                source_track_id INTEGER NOT NULL,
                path TEXT NOT NULL,
                label TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO classifier_labels (
                classifier_key,
                source_track_id,
                path,
                label
            ) VALUES ('legacy-profile', 17, 'C:/Music/legacy.wav', 'positive')
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
        match=r"legacy track identity.*migrate",
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
                catalog_uuid TEXT NOT NULL,
                track_uuid TEXT NOT NULL,
                content_generation INTEGER NOT NULL,
                selected_path TEXT NOT NULL,
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
            writer.execute(
                """
                CREATE TABLE classifier_labels (
                    classifier_key TEXT NOT NULL,
                    source_track_id INTEGER NOT NULL,
                    path TEXT NOT NULL,
                    label TEXT NOT NULL
                )
                """
            )
            writer.execute(
                """
                INSERT INTO classifier_labels (
                    classifier_key,
                    source_track_id,
                    path,
                    label
                ) VALUES ('wal-profile', 31, 'C:/Music/wal.wav', 'positive')
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

        with pytest.raises(RuntimeError, match="legacy track identity"):
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
        ("uuid-a", 1, "C:/Music/A.wav"),
        ("uuid-b", 2, "C:/Music/B.wav"),
    )

    saved = collections.save_collection(
        "Main set",
        first,
        source="main_ui_playlist",
        mode="replace",
    )
    assert saved.catalog_uuid == "catalog-a"
    assert saved.track_count == 2

    append = _selection(
        "catalog-a",
        ("uuid-a", 3, "D:/Relocated/A.wav"),
        ("uuid-c", 1, "C:/Music/C.wav"),
    )
    appended = collections.append_tracks(saved.id, append)
    assert [
        (
            track.track_uuid,
            track.content_generation,
            track.selected_path,
            track.position,
        )
        for track in appended.tracks
    ] == [
        ("uuid-a", 1, "C:/Music/A.wav", 1),
        ("uuid-b", 2, "C:/Music/B.wav", 2),
        ("uuid-c", 1, "C:/Music/C.wav", 3),
    ]

    replacement = _selection(
        "catalog-a",
        ("uuid-a", 3, "D:/Relocated/A.wav"),
    )
    replaced = collections.replace_tracks(saved.id, replacement)
    assert [
        (
            track.track_uuid,
            track.content_generation,
            track.selected_path,
        )
        for track in replaced.tracks
    ] == [("uuid-a", 3, "D:/Relocated/A.wav")]

    with sqlite3.connect(labels_path) as connection:
        columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(review_collection_tracks)"
            ).fetchall()
        }
    assert "source_track_id" not in columns
    assert {
        "catalog_uuid",
        "track_uuid",
        "content_generation",
        "selected_path",
    } <= columns


def test_collection_catalog_mismatch_is_fail_closed(
    tmp_path: Path,
) -> None:
    collections = RhythmLabCollections(tmp_path / "rhythm_lab.sqlite")
    original = collections.save_collection(
        "Bound set",
        _selection(
            "catalog-a",
            ("uuid-a", 1, "C:/Music/A.wav"),
        ),
        mode="replace",
    )

    with pytest.raises(RuntimeError, match="different catalog"):
        collections.save_collection(
            "Bound set",
            _selection(
                "catalog-b",
                ("uuid-b", 1, "C:/Music/B.wav"),
            ),
            mode="append",
        )

    current = collections.get_collection(original.id)
    assert current.catalog_uuid == "catalog-a"
    assert [track.track_uuid for track in current.tracks] == ["uuid-a"]


def test_legacy_collection_schema_is_rejected_without_rewrite(
    tmp_path: Path,
) -> None:
    labels_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(labels_path) as connection:
        connection.executescript(
            """
            CREATE TABLE review_collections (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                source TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE review_collection_tracks (
                collection_id INTEGER NOT NULL,
                source_track_id INTEGER NOT NULL,
                position INTEGER NOT NULL,
                score REAL,
                note TEXT,
                added_at TEXT NOT NULL
            );
            """
        )

    with pytest.raises(RuntimeError, match="migrate the database"):
        RhythmLabCollections(labels_path)


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


def test_launcher_refuses_unverified_or_different_running_source(
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
    monkeypatch.setattr(launcher, "_pid_path", lambda: pid_path)
    launcher._write_source_binding(active)
    monkeypatch.setattr(
        launcher,
        "_port_is_open",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        launcher,
        "_managed_process_id",
        lambda pid: pid,
    )

    with pytest.raises(RuntimeError, match="different database or catalog"):
        launcher.launch_rhythm_lab(requested)

    monkeypatch.setattr(
        launcher,
        "_managed_process_id",
        lambda _pid: None,
    )
    with pytest.raises(RuntimeError, match="cannot be verified"):
        launcher.launch_rhythm_lab(active)


def test_launcher_rejects_path_only_legacy_source(tmp_path: Path) -> None:
    with pytest.raises(TypeError, match="without catalog_uuid"):
        launcher.launch_rhythm_lab(tmp_path / "library.sqlite")  # type: ignore[arg-type]
