from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.api import create_app


def test_choose_folder_endpoint_returns_selected_path(monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "Music"
    selected.mkdir()
    monkeypatch.setattr(api, "open_folder_dialog", lambda: selected, raising=False)

    client = TestClient(create_app(tmp_path / "library.sqlite"))
    response = client.post("/api/dialog/folder")

    assert response.status_code == 200
    assert response.json() == {"path": str(selected)}


def test_create_app_requires_ffmpeg(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: (_ for _ in ()).throw(RuntimeError("ffmpeg is required")))

    try:
        create_app(tmp_path / "library.sqlite")
    except RuntimeError as error:
        assert "ffmpeg is required" in str(error)
    else:
        raise AssertionError("create_app should fail when ffmpeg is unavailable")


def test_choose_folder_endpoint_allows_cancel(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "open_folder_dialog", lambda: None, raising=False)

    client = TestClient(create_app(tmp_path / "library.sqlite"))
    response = client.post("/api/dialog/folder")

    assert response.status_code == 200
    assert response.json() == {"path": None}


def test_relocate_library_endpoint_returns_dry_run_preview(monkeypatch, tmp_path: Path) -> None:
    old_root = tmp_path / "ssd"
    new_root = tmp_path / "archive"
    old_root.mkdir()
    new_root.mkdir()
    old_file = old_root / "track.wav"
    old_file.write_bytes(b"audio")

    db_path = tmp_path / "library.sqlite"
    database = api.LibraryDatabase(db_path)
    track_id = database.upsert_track(path=old_file, size=old_file.stat().st_size, mtime=old_file.stat().st_mtime)

    client = TestClient(create_app(db_path))
    response = client.post(
        "/api/library/relocate",
        json={"old_root": str(old_root), "new_root": str(new_root), "apply": False},
    )

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["tracks_matched"] == 1
    assert api.LibraryDatabase(db_path).get_track(track_id).path == old_file.as_posix()


def test_analyze_endpoint_rejects_removed_fake_adapter(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/analyze", json={"adapter": "fake"})

    assert response.status_code == 422


def test_analysis_reset_endpoint_rejects_removed_fake_adapter(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/analysis/reset", json={"adapter": "fake"})

    assert response.status_code == 422
