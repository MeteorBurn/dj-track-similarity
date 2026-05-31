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
    queries: list[str] = []

    def __init__(self, device: str = "auto") -> None:
        self.device = device

    def embed_text(self, query: str):
        self.queries.append(query)
        vectors = {
            "dark rolling techno": [0.0, 1.0, 0.0],
            "track with vocals and speech": [0.0, 1.0, 0.0],
            "instrumental track without voices": [1.0, 0.0, 0.0],
        }
        return np.array(vectors[query], dtype=np.float32)


def test_text_search_uses_clap_embedding_space(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
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
    assert FakeClapAdapter.queries == ["dark rolling techno"]


def test_text_search_supports_adaptive_contrast_prompts(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    positive_id = _track_with_embedding(db, "positive.wav", [0.0, 1.0, 0.0], "clap")
    mixed_id = _track_with_embedding(db, "mixed.wav", [0.7, 0.7, 0.0], "clap")
    negative_id = _track_with_embedding(db, "negative.wav", [1.0, 0.0, 0.0], "clap")
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "query": "track with vocals and speech",
            "positive_queries": ["track with vocals and speech"],
            "negative_queries": ["instrumental track without voices"],
            "adaptive_contrast": True,
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["id"] for item in payload] == [positive_id, mixed_id, negative_id]
    assert payload[0]["score"] > payload[1]["score"] > payload[2]["score"]
    assert payload[0]["score_breakdown"] == {"positive": 1.0, "negative": 0.0, "contrast": 1.0}
    assert FakeClapAdapter.queries == ["track with vocals and speech", "instrumental track without voices"]


def _track_with_embedding(db: LibraryDatabase, name: str, embedding: list[float], embedding_key: str) -> int:
    path = Path("C:/music") / name
    track_id = db.upsert_track(path=path, size=100, mtime=1, metadata={"title": name})
    db.save_embedding(track_id, np.array(embedding, dtype=np.float32), f"{embedding_key}-model", 3, embedding_key=embedding_key)
    return track_id
