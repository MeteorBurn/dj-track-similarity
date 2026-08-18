from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.api as api


def create_api_client(monkeypatch: pytest.MonkeyPatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None)
    return TestClient(api.create_app(db_path))
