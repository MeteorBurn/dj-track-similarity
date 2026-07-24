from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dj_track_similarity import api as api_module
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_tracks import canonical_file_path
from dj_track_similarity.track_models import FileTags, ScannedFile


@pytest.fixture(autouse=True)
def _ffmpeg(monkeypatch) -> None:
    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg")


def _add_track(
    database: LibraryDatabase,
    path: Path,
):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"source audio")
    stat = path.stat()
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
            audio_codec="pcm_s16le",
            sample_rate_hz=44_100,
            channel_count=2,
            audio_duration_seconds=1.0,
        ),
        tags=FileTags(title=path.stem, artist="Relocation Fixture"),
    ).identity


def test_choose_folder_endpoint_returns_selected_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    selected = tmp_path / "Music"
    selected.mkdir()
    monkeypatch.setattr(
        api_module,
        "open_folder_dialog",
        lambda: selected,
    )

    response = TestClient(
        api_module.create_app(tmp_path / "library.sqlite")
    ).post("/api/dialog/folder")

    assert response.status_code == 200
    assert response.json() == {"path": str(selected)}


def test_create_app_requires_ffmpeg(monkeypatch, tmp_path: Path) -> None:
    def missing_ffmpeg() -> str:
        raise RuntimeError("ffmpeg is required")

    monkeypatch.setattr(api_module, "require_ffmpeg", missing_ffmpeg)

    with pytest.raises(RuntimeError, match="ffmpeg is required"):
        api_module.create_app(tmp_path / "library.sqlite")


def test_choose_folder_endpoint_allows_cancel(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        api_module,
        "open_folder_dialog",
        lambda: None,
    )

    response = TestClient(
        api_module.create_app(tmp_path / "library.sqlite")
    ).post("/api/dialog/folder")

    assert response.status_code == 200
    assert response.json() == {"path": None}


def test_choose_folder_endpoint_reports_unavailable_dialog(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def unavailable() -> None:
        raise RuntimeError("Native folder dialog is unavailable")

    monkeypatch.setattr(api_module, "open_folder_dialog", unavailable)
    response = TestClient(
        api_module.create_app(tmp_path / "library.sqlite")
    ).post("/api/dialog/folder")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Native folder dialog is unavailable"
    }


def test_relocate_library_endpoint_returns_composite_dry_run_preview(
    tmp_path: Path,
) -> None:
    old_root = tmp_path / "ssd"
    new_root = tmp_path / "archive"
    old_file = old_root / "Artist" / "track.wav"
    new_root.mkdir()
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _add_track(database, old_file)
    before = database.get_track_file_state(old_file)
    assert before is not None

    response = TestClient(api_module.create_app(database.path)).post(
        "/api/library/relocate",
        json={
            "old_root": str(old_root),
            "new_root": str(new_root),
            "apply": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is True
    assert payload["tracks_matched"] == 1
    assert payload["tracks_updated"] == 0
    assert payload["changes"] == [
        {
            "track_id": identity.track_id,
            "track_uuid": identity.track_uuid,
            "content_generation": identity.content_generation,
            "old_path": canonical_file_path(old_file),
            "new_path": canonical_file_path(
                new_root / "Artist" / "track.wav"
            ),
        }
    ]
    assert database.get_track_file_state(old_file) == before
    assert old_file.read_bytes() == b"source audio"


def test_relocate_library_apply_updates_only_database_path_and_keeps_identity(
    tmp_path: Path,
) -> None:
    old_root = tmp_path / "ssd"
    new_root = tmp_path / "archive"
    old_file = old_root / "Artist" / "track.wav"
    new_file = new_root / "Artist" / "track.wav"
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _add_track(database, old_file)
    new_file.parent.mkdir(parents=True)
    new_file.write_bytes(b"relocated audio")
    old_bytes = old_file.read_bytes()
    new_bytes = new_file.read_bytes()

    response = TestClient(api_module.create_app(database.path)).post(
        "/api/library/relocate",
        json={
            "old_root": str(old_root),
            "new_root": str(new_root),
            "apply": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dry_run"] is False
    assert payload["tracks_matched"] == 1
    assert payload["tracks_updated"] == 1
    assert payload["missing_files"] == []
    assert payload["conflicts"] == []
    assert database.get_track_file_state(old_file) is None
    after = database.get_track_file_state(new_file)
    assert after is not None
    assert (
        after.catalog_uuid,
        after.track_id,
        after.track_uuid,
        after.content_generation,
    ) == (
        identity.catalog_uuid,
        identity.track_id,
        identity.track_uuid,
        identity.content_generation,
    )
    assert old_file.read_bytes() == old_bytes
    assert new_file.read_bytes() == new_bytes


def test_relocate_library_apply_rejects_missing_target_without_partial_update(
    tmp_path: Path,
) -> None:
    old_root = tmp_path / "ssd"
    new_root = tmp_path / "archive"
    old_file = old_root / "track.wav"
    new_root.mkdir()
    database = LibraryDatabase(tmp_path / "library.sqlite")
    identity = _add_track(database, old_file)

    response = TestClient(api_module.create_app(database.path)).post(
        "/api/library/relocate",
        json={
            "old_root": str(old_root),
            "new_root": str(new_root),
            "apply": True,
        },
    )

    assert response.status_code == 400
    assert "target files are missing" in response.json()["detail"]
    assert database.get_track_identity(identity.track_id) == identity
    state = database.get_track_file_state(old_file)
    assert state is not None
    assert state.track_uuid == identity.track_uuid
