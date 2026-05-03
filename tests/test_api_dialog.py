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


def test_choose_folder_endpoint_allows_cancel(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "open_folder_dialog", lambda: None, raising=False)

    client = TestClient(create_app(tmp_path / "library.sqlite"))
    response = client.post("/api/dialog/folder")

    assert response.status_code == 200
    assert response.json() == {"path": None}
