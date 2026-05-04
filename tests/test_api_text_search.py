from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase


class FakeClapAdapter:
    embedding_key = "clap"
    model_name = "fake-clap"
    dim = 3

    def __init__(self, device: str = "auto") -> None:
        self.device = device

    def embed_text(self, query: str):
        assert query == "dark rolling techno"
        return np.array([0.0, 1.0, 0.0], dtype=np.float32)


def test_text_search_uses_clap_embedding_space(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    near_id = _track_with_embedding(db, "near.wav", [0.0, 1.0, 0.0], "clap")
    far_id = _track_with_embedding(db, "far.wav", [1.0, 0.0, 0.0], "clap")
    _track_with_embedding(db, "mert-only.wav", [0.0, 1.0, 0.0], "mert")
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={"query": " dark rolling techno ", "limit": 5, "device": "cpu"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["id"] for item in payload] == [near_id, far_id]
    assert payload[0]["score"] > payload[1]["score"]


def _track_with_embedding(db: LibraryDatabase, name: str, embedding: list[float], embedding_key: str) -> int:
    path = Path("C:/music") / name
    track_id = db.upsert_track(path=path, size=100, mtime=1, metadata={"title": name})
    db.save_embedding(track_id, np.array(embedding, dtype=np.float32), f"{embedding_key}-model", 3, embedding_key=embedding_key)
    return track_id
