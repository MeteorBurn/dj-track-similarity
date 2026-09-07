from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.embedding.clap as embedding_clap
import dj_track_similarity.embedding.mulan as embedding_mulan
from dj_track_similarity.analysis.model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    CLAP_EMBEDDING_DIM,
    EmbeddingOutput,
    EmbeddingWrite,
    MERT_EMBEDDING_DIM,
    MULAN_EMBEDDING_DIM,
)
from dj_track_similarity.api.application import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.embeddings import current_track_identity, read_valid_embeddings
from dj_track_similarity.embedding.clap import ClapEmbeddingAdapter
from dj_track_similarity.embedding.mulan import MuqMulanEmbeddingAdapter
from dj_track_similarity.track_models import FileTags, ScannedFile


class FakeClapAdapter(ClapEmbeddingAdapter):
    queries: list[str] = []
    instances: int = 0

    def __init__(self, device: str = "auto") -> None:
        super().__init__(device=device)
        type(self).instances += 1

    def embed_texts(self, texts):
        vectors = {
            "dark rolling techno": [0.0, 1.0, 0.0],
            "track with vocals and speech": [0.0, 1.0, 0.0],
            "instrumental track without voices": [1.0, 0.0, 0.0],
            "broken drums.": [1.0, 0.0, 0.0],
            "syncopated percussion.": [0.0, 1.0, 0.0],
            "straight house groove.": [0.0, 0.0, 1.0],
            "warmup": [1.0, 0.0, 0.0],
        }
        output = current_embedding_analysis_output("clap")
        embedded = []
        for query in texts:
            self.queries.append(query)
            embedded.append(_typed_vector(output, vectors[query]))
        return embedded


class FakeMulanAdapter(MuqMulanEmbeddingAdapter):
    queries: list[str] = []
    instances: int = 0

    def __init__(self, device: str = "auto") -> None:
        super().__init__(device=device)
        type(self).instances += 1

    def embed_texts(self, texts):
        output = current_embedding_analysis_output("mulan")
        embedded = []
        for query in texts:
            self.queries.append(query)
            embedded.append(_typed_vector(output, [0.0, 1.0, 0.0]))
        return embedded


def test_text_search_uses_clap_embedding_space(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    near_id = _track_with_embedding(db, "near.wav", [0.0, 1.0, 0.0], "clap")
    far_id = _track_with_embedding(db, "far.wav", [1.0, 0.0, 0.0], "clap")
    _track_with_embedding(db, "mert-only.wav", [0.0, 1.0, 0.0], "mert")
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "positive_queries": [" dark rolling techno "],
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()["results"]
    assert [item["track"]["track_id"] for item in payload] == [near_id, far_id]
    assert payload[0]["score"] > payload[1]["score"]
    assert FakeClapAdapter.queries == ["dark rolling techno"]


def test_repeated_text_search_reuses_one_loaded_adapter(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    FakeClapAdapter.instances = 0
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    _track_with_embedding(db, "near.wav", [0.0, 1.0, 0.0], "clap")
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)
    client = TestClient(create_app(db_path))

    for _ in range(3):
        response = client.post(
            "/api/search/text",
            json={
                "positive_queries": ["dark rolling techno"],
                "limit": 5,
                "device": "cpu",
            },
        )
        assert response.status_code == 200

    assert FakeClapAdapter.instances == 1
    assert FakeClapAdapter.queries == ["dark rolling techno"] * 3


def test_text_search_uses_persisted_mulan_embeddings_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    FakeMulanAdapter.queries = []
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    near_id = _track_with_embedding(db, "mulan-near.wav", [0.0, 1.0, 0.0], "mulan")
    far_id = _track_with_embedding(db, "mulan-far.wav", [1.0, 0.0, 0.0], "mulan")
    _track_with_embedding(db, "clap-only.wav", [0.0, 1.0, 0.0], "clap")
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM mulan_embeddings").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM clap_embeddings").fetchone()[0] == 1
    with db.connect() as connection:
        near = current_track_identity(connection, near_id)
        assert near is not None
        stored = read_valid_embeddings(
            family="mulan",
            identities={near.track_id: near.track_uuid},
            catalog_uuid=near.catalog_uuid,
            connection=connection,
        )[near_id]
    assert np.allclose(
        stored,
        _typed_vector(current_embedding_analysis_output("mulan"), [0.0, 1.0, 0.0]),
    )
    monkeypatch.setattr(embedding_mulan, "MuqMulanEmbeddingAdapter", FakeMulanAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "positive_queries": ["dark rolling techno"],
            "analysis_family": "mulan",
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()["results"]
    assert [item["track"]["track_id"] for item in payload] == [near_id, far_id]
    assert payload[0]["score"] > payload[1]["score"]
    assert FakeMulanAdapter.queries == ["dark rolling techno"]


def test_text_search_subtracts_a_hard_negative_bank(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    positive_id = _track_with_embedding(db, "positive.wav", [0.0, 1.0, 0.0], "clap")
    mixed_id = _track_with_embedding(db, "mixed.wav", [0.7, 0.7, 0.0], "clap")
    negative_id = _track_with_embedding(db, "negative.wav", [1.0, 0.0, 0.0], "clap")
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "positive_queries": ["track with vocals and speech"],
            "negative_queries": ["instrumental track without voices"],
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()["results"]
    assert [item["track"]["track_id"] for item in payload] == [
        positive_id,
        mixed_id,
        negative_id,
    ]
    assert payload[0]["score"] > payload[1]["score"] > payload[2]["score"]
    assert payload[0]["score_breakdown"] == {"positive": 1.0, "negative": 0.0, "contrast": 1.0, "negative_weight": 0.5}
    assert FakeClapAdapter.queries == ["track with vocals and speech", "instrumental track without voices"]


def test_text_search_mean_pools_positive_prompt_bank(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    bank_match_id = _track_with_embedding(db, "bank-match.wav", [0.70710677, 0.70710677, 0.0], "clap")
    single_prompt_id = _track_with_embedding(db, "single-prompt.wav", [1.0, 0.0, 0.0], "clap")
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "positive_queries": ["broken drums.", "syncopated percussion."],
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()["results"]
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
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "positive_queries": ["broken drums."],
            "negative_queries": ["straight house groove."],
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()["results"]
    assert [item["track"]["track_id"] for item in payload] == [
        positive_id,
        negative_aligned_id,
    ]
    assert payload[1]["score"] == pytest.approx(0.35355339)
    assert payload[1]["score_breakdown"] == {
        "positive": pytest.approx(0.70710677),
        "negative": pytest.approx(0.70710677),
        "contrast": pytest.approx(0.35355339),
        "negative_weight": 0.5,
    }
    assert FakeClapAdapter.queries == ["broken drums.", "straight house groove."]


def test_text_search_applies_a_requested_negative_weight(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    positive_id = _track_with_embedding(db, "positive.wav", [1.0, 0.0, 0.0], "clap")
    negative_aligned_id = _track_with_embedding(
        db, "negative-aligned.wav", [0.70710677, 0.0, 0.70710677], "clap"
    )
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "positive_queries": ["broken drums."],
            "negative_queries": ["straight house groove."],
            "negative_weight": 1.0,
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()["results"]
    assert [item["track"]["track_id"] for item in payload] == [
        positive_id,
        negative_aligned_id,
    ]
    assert payload[1]["score_breakdown"]["negative_weight"] == 1.0
    assert payload[1]["score"] == pytest.approx(0.0)


def test_text_search_rejects_a_negative_weight_outside_the_contract(tmp_path: Path) -> None:
    response = TestClient(create_app(tmp_path / "library.sqlite")).post(
        "/api/search/text",
        json={"positive_queries": ["broken drums."], "negative_weight": -0.5},
    )

    assert response.status_code == 422


def test_text_search_rejects_a_min_similarity_outside_the_contract(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    assert (
        client.post(
            "/api/search/text",
            json={"positive_queries": ["broken drums."], "min_similarity": 1.5},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/search/text",
            json={"positive_queries": ["broken drums."], "min_similarity": -0.1},
        ).status_code
        == 422
    )


def test_text_search_embeds_every_prompt_of_a_negated_bank(monkeypatch, tmp_path: Path) -> None:
    """A multi-line bank is never reduced to its first line.

    The removed ``adaptive_contrast`` switch silently dropped every prompt after
    the first, so a five-line bank ranked on one line with no sign in the
    response. Nothing selects that behaviour now.
    """

    FakeClapAdapter.queries = []
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    first_line_id = _track_with_embedding(db, "direct.wav", [1.0, 0.0, 0.0], "clap")
    bank_id = _track_with_embedding(db, "bank.wav", [0.70710677, 0.70710677, 0.0], "clap")
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "positive_queries": ["broken drums.", "syncopated percussion."],
            "negative_queries": ["straight house groove."],
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()["results"]
    assert [item["track"]["track_id"] for item in payload] == [
        bank_id,
        first_line_id,
    ]
    assert payload[0]["score_breakdown"] is not None
    assert FakeClapAdapter.queries == [
        "broken drums.",
        "syncopated percussion.",
        "straight house groove.",
    ]


def test_text_search_rejects_a_blank_bank_before_loading_clap(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(tmp_path / "library.sqlite")).post(
        "/api/search/text",
        json={"positive_queries": ["   ", ""], "device": "cpu"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "At least one positive query is required"}
    assert FakeClapAdapter.queries == []


def test_text_search_requires_a_prompt_bank(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    assert client.post("/api/search/text", json={"device": "cpu"}).status_code == 422
    assert (
        client.post(
            "/api/search/text",
            json={"positive_queries": [], "device": "cpu"},
        ).status_code
        == 422
    )


def test_text_search_warmup_loads_the_family_without_touching_the_library(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Warming is about the model, so it holds on an empty library.

    The endpoint exists to move the weight load off the first search, and the
    second call has to find the cached adapter or it has moved nothing.
    """

    FakeClapAdapter.queries = []
    FakeClapAdapter.instances = 0
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)
    client = TestClient(create_app(db_path))

    assert client.get("/api/search/text/warmup").json() == {"loaded": []}

    response = client.post(
        "/api/search/text/warmup",
        json={"analysis_family": "clap", "device": "cpu"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_family"] == "clap"
    assert payload["device"] == "cpu"
    assert payload["seconds"] >= 0.0

    assert (
        client.post(
            "/api/search/text/warmup",
            json={"analysis_family": "clap", "device": "cpu"},
        ).status_code
        == 200
    )
    assert FakeClapAdapter.instances == 1
    assert FakeClapAdapter.queries == ["warmup", "warmup"]
    # The status is what a first search reads to say it is waiting on weights.
    assert client.get("/api/search/text/warmup").json() == {
        "loaded": [{"analysis_family": "clap", "device": "cpu"}]
    }


def test_text_search_warmup_rejects_unknown_contract_fields(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    assert (
        client.post(
            "/api/search/text/warmup",
            json={"analysis_family": "clap", "positive_queries": ["broken drums."]},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/search/text/warmup",
            json={"analysis_family": "sonara"},
        ).status_code
        == 422
    )


def test_text_search_rejects_unknown_contract_fields(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    assert (
        client.post(
            "/api/search/text",
            json={
                "positive_queries": ["broken drums."],
                "score_is_probability": True,
            },
        ).status_code
        == 422
    )
    for retired in ("query", "adaptive_contrast", "preset"):
        response = client.post(
            "/api/search/text",
            json={"positive_queries": ["broken drums."], retired: "broken drums."},
        )
        assert response.status_code == 422, retired


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
    )
    result = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family=output.analysis_family,
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
    dimensions = {
        "clap": CLAP_EMBEDDING_DIM,
        "mert": MERT_EMBEDDING_DIM,
        "mulan": MULAN_EMBEDDING_DIM,
    }
    vector = np.zeros(dimensions[output.analysis_family], dtype=np.float32)
    vector[: len(values)] = values
    return vector / np.linalg.norm(vector)


def _search(client, **fields):
    response = client.post("/api/search/text", json={"positive_queries": ["broken drums."], "limit": 20, **fields})
    assert response.status_code == 200, response.text
    return response.json()


def _judge(client, run, track_uuid, verdict=1, revision=0):
    return client.post("/api/search/text/feedback", json={"run_id": run["execution"]["run_id"], "track_uuid": track_uuid, "verdict": verdict, "expected_revision": revision})


def _feedback_client(monkeypatch, tmp_path):
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track_with_embedding(db, "judged.wav", [1.0, 0.0, 0.0], "clap")
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)
    app = create_app(db.path)
    return db, TestClient(app), app


def test_text_search_feedback_stores_updates_and_withdraws_verdicts(monkeypatch, tmp_path):
    db, client, _app = _feedback_client(monkeypatch, tmp_path)
    run = _search(client, preset_banks=[{"key": "voice/vocal-led", "positive_queries": ["broken drums."]}, {"key": "instruments/piano", "positive_queries": ["broken drums."]}], input_mode="preset")
    uuid = run["results"][0]["track"]["track_uuid"]
    assert _judge(client, run, uuid).json()["revision"] == 1
    # An identical retry is idempotent; a competing desired verdict conflicts.
    assert _judge(client, run, uuid).json()["revision"] == 1
    conflict = _judge(client, run, uuid, -1)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["current"]["revision"] == 1
    assert _judge(client, run, uuid, -1, 1).json()["revision"] == 2
    assert _judge(client, run, uuid, 0, 2).json()["revision"] == 3
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM text_search_feedback").fetchone()[0] == 1


def test_text_search_feedback_lookup_restores_exact_query_only(monkeypatch, tmp_path):
    _db, client, _app = _feedback_client(monkeypatch, tmp_path)
    run = _search(client)
    uuid = run["results"][0]["track"]["track_uuid"]
    assert _judge(client, run, uuid).status_code == 200
    repeated = _search(client, limit=5, comparison_mode="product_ab", comparison_id="comparison", use_feedback=True)
    assert repeated["execution"]["run_id"] != run["execution"]["run_id"]
    assert repeated["execution"]["query_key"] == run["execution"]["query_key"]
    assert repeated["execution"]["feedback"]["reason"] == "disabled_for_product_ab"
    lookup = client.post("/api/search/text/feedback/lookup", json={"run_id": repeated["execution"]["run_id"], "track_uuids": [uuid]})
    assert lookup.json() == {"query_key": run["execution"]["query_key"], "verdicts": {uuid: {"verdict": 1, "revision": 1}}}
    changed = _search(client, positive_queries=["dark rolling techno"])
    lookup = client.post("/api/search/text/feedback/lookup", json={"run_id": changed["execution"]["run_id"], "track_uuids": [uuid]})
    assert lookup.json()["verdicts"] == {}


def test_text_search_feedback_lookup_rejects_retired_contract_fields(monkeypatch, tmp_path):
    _db, client, _app = _feedback_client(monkeypatch, tmp_path)
    assert client.post("/api/search/text/feedback/lookup", json={"track_uuids": ["whatever"], "preset_keys": ["mood/dark"], "analysis_family": "clap"}).status_code == 422
    assert client.post("/api/search/text/feedback", json={"track_uuid": "whatever", "preset_keys": ["mood/dark"], "analysis_family": "clap", "verdict": 1}).status_code == 422


def test_query_identity_tracks_effective_bank_and_output(monkeypatch, tmp_path):
    from dj_track_similarity.text_search_models import query_context_key
    _db, client, _app = _feedback_client(monkeypatch, tmp_path)
    run = _search(client, positive_queries=[" broken drums. ", "syncopated percussion."], negative_queries=["straight house groove."], negative_weight=0.5)
    context = run["execution"]["query_context"]
    assert context["positive_queries"] == ["broken drums.", "syncopated percussion."]
    assert context["negative_weight"] == 0.5
    key = run["execution"]["query_key"]
    for fields in ({"negative_weight": 0.75}, {"positive_queries": ["syncopated percussion.", "broken drums."]}, {"input_mode": "preset"}, {"analysis_family": "mulan"}):
        monkeypatch.setattr(embedding_mulan, "MuqMulanEmbeddingAdapter", FakeMulanAdapter)
        other = _search(client, positive_queries=context["positive_queries"], negative_queries=context["negative_queries"], **({"negative_weight": 0.5} | fields)) if "positive_queries" not in fields else _search(client, negative_queries=context["negative_queries"], negative_weight=0.5, **fields)
        assert other["execution"]["query_key"] != key
    changed = {**context, "analysis_output_identity": {**context["analysis_output_identity"], "model_version": "different"}}
    assert query_context_key(changed) != key
    assert _search(client, negative_weight=0.75)["execution"]["query_key"] == _search(client, negative_weight=0.0)["execution"]["query_key"]


def test_text_search_reports_positive_only_preset_descriptors(monkeypatch, tmp_path):
    _db, client, _app = _feedback_client(monkeypatch, tmp_path)
    run = _search(client, positive_queries=["broken drums.", "straight house groove."], preset_banks=[{"key": "rhythm/breakbeat", "positive_queries": ["broken drums."]}, {"key": "rhythm/four-on-the-floor", "positive_queries": ["straight house groove."]}])
    scores = run["results"][0]["preset_scores"]
    assert scores["rhythm/breakbeat"] > scores["rhythm/four-on-the-floor"]


def test_feedback_rejects_unissued_expired_and_other_database_runs(monkeypatch, tmp_path):
    from dj_track_similarity.api.text_search_context import TextSearchRunCache
    db, client, app = _feedback_client(monkeypatch, tmp_path)
    run = _search(client)
    uuid = run["results"][0]["track"]["track_uuid"]
    assert _judge(client, run, "not-in-results").status_code == 400
    forged = {"execution": {"run_id": "not-issued"}}
    assert _judge(client, forged, uuid).status_code == 409
    # Exercise the actual cache expiration/eviction behavior using an injected clock.
    cache = TextSearchRunCache(ttl_seconds=1, max_entries=1, clock=lambda: 0.0)
    cached_run = app.state.text_search_runs.get(run["execution"]["run_id"])
    cache.put(cached_run)
    cache._clock = lambda: 2.0
    assert cache.get(run["execution"]["run_id"]) is None
    app.state.text_search_runs._clock = lambda: float("inf")
    assert _judge(client, run, uuid).status_code == 409
    app.state.text_search_runs._clock = lambda: 0.0
    new_run = _search(client)
    selected = client.post("/api/database/switch", json={"path": str(tmp_path / "other.sqlite")})
    assert selected.status_code == 200, selected.text
    assert _judge(client, new_run, uuid).status_code == 409
    with db.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM text_search_feedback").fetchone()[0] == 0


def test_text_search_pulls_exact_query_toward_kept_tracks(monkeypatch, tmp_path):
    from dj_track_similarity.search.engine import FEEDBACK_MINIMUM_TRACKS
    db = LibraryDatabase(tmp_path / "library.sqlite")
    kept = [_track_with_embedding(db, f"kept{i}.wav", [0.5, 0.866, 0.0], "clap") for i in range(FEEDBACK_MINIMUM_TRACKS)]
    distractor = _track_with_embedding(db, "distractor.wav", [0.55, 0.0, 0.835], "clap")
    monkeypatch.setattr(embedding_clap, "ClapEmbeddingAdapter", FakeClapAdapter)
    client = TestClient(create_app(db.path))
    plain = _search(client)
    assert plain["results"][0]["track"]["track_id"] == distractor
    judged = []
    for row in plain["results"]:
        if row["track"]["track_id"] in kept:
            uuid = row["track"]["track_uuid"]
            assert _judge(client, plain, uuid).status_code == 200
            judged.append(uuid)
    warm = _search(client, use_feedback=True)
    assert warm["execution"]["feedback"]["applied"]
    assert warm["results"][0]["track"]["track_id"] in kept
    assert _search(client)["results"] == plain["results"]
    other = _search(client, use_feedback=True, input_mode="preset")
    assert not other["execution"]["feedback"]["applied"]
    assert _judge(client, warm, judged[0], 0, 1).status_code == 200
    withdrawn = _search(client, use_feedback=True)
    assert not withdrawn["execution"]["feedback"]["applied"]
    assert withdrawn["execution"]["feedback"]["history_revision"] != warm["execution"]["feedback"]["history_revision"]


def test_old_library_search_is_cold_and_does_not_create_feedback_schema(monkeypatch, tmp_path):
    db, client, _app = _feedback_client(monkeypatch, tmp_path)
    with db.connect() as connection:
        connection.execute("DROP TABLE text_search_feedback")
    run = _search(client, use_feedback=True)
    assert run["execution"]["feedback"]["reason"] == "schema_unavailable"
    uuid = run["results"][0]["track"]["track_uuid"]
    assert _judge(client, run, uuid).status_code == 409
    with db.connect() as connection:
        assert connection.execute("SELECT count(*) FROM sqlite_schema WHERE name = 'text_search_feedback'").fetchone()[0] == 0
