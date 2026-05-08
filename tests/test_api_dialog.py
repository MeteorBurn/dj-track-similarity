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
