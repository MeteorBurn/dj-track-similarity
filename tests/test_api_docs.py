from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.api import create_app


def test_docs_route_explains_when_static_docs_are_not_built(monkeypatch, tmp_path: Path) -> None:
    original_exists = Path.exists

    def fake_exists(path: Path) -> bool:
        normalized = path.as_posix()
        if normalized.endswith("/docs/dj-track-similarity/site"):
            return False
        return original_exists(path)

    monkeypatch.setattr(api.Path, "exists", fake_exists)

    response = TestClient(create_app(tmp_path / "library.sqlite")).get("/docs/")

    assert response.status_code == 503
    assert "Documentation is not built" in response.text
    assert "npm run build" in response.text
