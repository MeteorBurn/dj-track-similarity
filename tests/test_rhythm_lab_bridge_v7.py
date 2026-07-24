from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

import pytest

import dj_track_similarity.rhythm_lab_launcher as launcher
from dj_track_similarity.rhythm_lab_collections import (
    RhythmLabCollectionSelection,
    RhythmLabCollections,
    RhythmLabTrackSelection,
    build_rhythm_lab_collection_selection,
)


@dataclass(frozen=True)
class _FakeTrackState:
    catalog_uuid: str
    track_id: int
    track_uuid: str
    file_path: str
    content_generation: int


class _FakeTrackRepository:
    def __init__(
        self,
        *,
        catalog_uuid: str,
        states: tuple[_FakeTrackState, ...],
    ) -> None:
        self.catalog_uuid = catalog_uuid
        self.states = states
        self.calls: list[tuple[tuple[int, ...], bool]] = []

    def get_track_file_states_by_ids(
        self,
        track_ids: list[int],
        *,
        include_missing: bool = False,
    ) -> tuple[_FakeTrackState, ...]:
        self.calls.append((tuple(track_ids), include_missing))
        requested = set(track_ids)
        return tuple(
            state
            for state in reversed(self.states)
            if state.track_id in requested
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


def test_collection_selection_uses_repository_identity_and_request_order() -> None:
    repository = _FakeTrackRepository(
        catalog_uuid="catalog-a",
        states=(
            _FakeTrackState(
                catalog_uuid="catalog-a",
                track_id=7,
                track_uuid="uuid-seven",
                file_path="C:/Music/Seven.wav",
                content_generation=4,
            ),
            _FakeTrackState(
                catalog_uuid="catalog-a",
                track_id=2,
                track_uuid="uuid-two",
                file_path="C:/Music/Two.wav",
                content_generation=9,
            ),
        ),
    )

    selection = build_rhythm_lab_collection_selection(
        repository,
        [7, 2, 7],
    )

    assert repository.calls == [((7, 2), False)]
    assert selection.catalog_uuid == "catalog-a"
    assert [
        (
            track.track_uuid,
            track.content_generation,
            track.selected_path,
        )
        for track in selection.tracks
    ] == [
        ("uuid-seven", 4, "C:/Music/Seven.wav"),
        ("uuid-two", 9, "C:/Music/Two.wav"),
    ]


def test_collection_selection_rejects_invalid_or_cross_catalog_rows() -> None:
    repository = _FakeTrackRepository(
        catalog_uuid="catalog-a",
        states=(
            _FakeTrackState(
                catalog_uuid="catalog-b",
                track_id=1,
                track_uuid="uuid-one",
                file_path="C:/Music/One.wav",
                content_generation=1,
            ),
        ),
    )

    with pytest.raises(ValueError, match="positive integer"):
        build_rhythm_lab_collection_selection(repository, [True])
    with pytest.raises(RuntimeError, match="different catalog"):
        build_rhythm_lab_collection_selection(repository, [1])


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

    with pytest.raises(RuntimeError, match="explicit label recovery"):
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
