from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
)
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.embedding import ClapEmbeddingAdapter
from dj_track_similarity.track_models import FileTags, ScannedFile


class FakeClapAdapter(ClapEmbeddingAdapter):
    queries: list[str] = []

    def __init__(self, device: str = "auto") -> None:
        super().__init__(device=device)

    def embed_text(self, query: str):
        self.queries.append(query)
        vectors = {
            "dark rolling techno": [0.0, 1.0, 0.0],
            "track with vocals and speech": [0.0, 1.0, 0.0],
            "instrumental track without voices": [1.0, 0.0, 0.0],
            "broken drums.": [1.0, 0.0, 0.0],
            "syncopated percussion.": [0.0, 1.0, 0.0],
            "straight house groove.": [0.0, 0.0, 1.0],
        }
        return _typed_vector(
            current_embedding_analysis_output("clap"),
            vectors[query],
        )


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
    assert [item["track"]["track_id"] for item in payload] == [near_id, far_id]
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
    assert [item["track"]["track_id"] for item in payload] == [
        positive_id,
        mixed_id,
        negative_id,
    ]
    assert payload[0]["score"] > payload[1]["score"] > payload[2]["score"]
    assert payload[0]["score_breakdown"] == {"positive": 1.0, "negative": 0.0, "contrast": 1.0, "negative_weight": 0.35}
    assert FakeClapAdapter.queries == ["track with vocals and speech", "instrumental track without voices"]


def test_text_search_mean_pools_positive_prompt_bank(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    bank_match_id = _track_with_embedding(db, "bank-match.wav", [0.70710677, 0.70710677, 0.0], "clap")
    single_prompt_id = _track_with_embedding(db, "single-prompt.wav", [1.0, 0.0, 0.0], "clap")
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "query": "broken drums.",
            "positive_queries": ["broken drums.", "syncopated percussion."],
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["track_id"] for item in payload] == [
        bank_match_id,
        single_prompt_id,
    ]
    assert payload[0]["score"] > payload[1]["score"]
    assert FakeClapAdapter.queries == ["broken drums.", "syncopated percussion."]


def test_text_search_uses_weighted_hard_negative_margin(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    positive_id = _track_with_embedding(db, "positive.wav", [1.0, 0.0, 0.0], "clap")
    negative_aligned_id = _track_with_embedding(db, "negative-aligned.wav", [0.70710677, 0.0, 0.70710677], "clap")
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "query": "broken drums.",
            "positive_queries": ["broken drums."],
            "negative_queries": ["straight house groove."],
            "adaptive_contrast": True,
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["track_id"] for item in payload] == [
        positive_id,
        negative_aligned_id,
    ]
    assert payload[1]["score"] == pytest.approx(0.4596194)
    assert payload[1]["score_breakdown"] == {
        "positive": pytest.approx(0.70710677),
        "negative": pytest.approx(0.70710677),
        "contrast": pytest.approx(0.4596194),
        "negative_weight": 0.35,
    }
    assert FakeClapAdapter.queries == ["broken drums.", "straight house groove."]


def test_text_search_disabled_adaptive_contrast_uses_single_positive_prompt(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    direct_id = _track_with_embedding(db, "direct.wav", [1.0, 0.0, 0.0], "clap")
    bank_id = _track_with_embedding(db, "bank.wav", [0.70710677, 0.70710677, 0.0], "clap")
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "query": "broken drums.",
            "positive_queries": ["broken drums.", "syncopated percussion."],
            "negative_queries": ["straight house groove."],
            "adaptive_contrast": False,
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["track_id"] for item in payload] == [
        direct_id,
        bank_id,
    ]
    assert payload[0]["score_breakdown"] is None
    assert FakeClapAdapter.queries == ["broken drums."]


def test_text_search_rejects_blank_query_before_loading_clap(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(tmp_path / "library.sqlite")).post(
        "/api/search/text",
        json={"query": "   ", "positive_queries": ["broken drums."], "device": "cpu"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Text query is required"}
    assert FakeClapAdapter.queries == []


def test_text_search_rejects_unknown_contract_fields(tmp_path: Path) -> None:
    response = TestClient(create_app(tmp_path / "library.sqlite")).post(
        "/api/search/text",
        json={"query": "broken drums.", "score_is_probability": True},
    )

    assert response.status_code == 422


def _track_with_embedding(
    db: LibraryDatabase,
    name: str,
    embedding: list[float],
    embedding_key: str,
) -> int:
    output = current_embedding_analysis_output(embedding_key)
    db.register_analysis_outputs((output,))
    path = Path(db.path).parent / name
    path.write_bytes(name.encode("utf-8"))
    stat = path.stat()
    identity = db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
        ),
        tags=FileTags(title=name, artist="Test"),
    ).identity
    target = AnalysisTarget(
        identity.catalog_uuid,
        identity.track_id,
        identity.track_uuid,
        identity.content_generation,
    )
    result = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    contract=output.contract,
                    vector=_typed_vector(output, embedding),
                    analyzed_at="2026-07-24T12:00:00.000000Z",
                ),
            ),
        )
    )[0]
    assert result.ok, result.error
    return target.track_id


def _typed_vector(
    output: AnalysisOutput,
    values: list[float],
) -> np.ndarray:
    vector = np.zeros(output.contract.dim, dtype=np.float32)
    vector[: len(values)] = values
    return vector / np.linalg.norm(vector)
