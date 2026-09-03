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
    CLAP_EMBEDDING_DIM,
    EmbeddingOutput,
    EmbeddingWrite,
    MERT_EMBEDDING_DIM,
    MULAN_EMBEDDING_DIM,
)
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_embeddings import current_track_identity, read_valid_embeddings
from dj_track_similarity.embedding import ClapEmbeddingAdapter, MuqMulanEmbeddingAdapter
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
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
            "positive_queries": [" dark rolling techno "],
            "limit": 5,
            "device": "cpu",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["track_id"] for item in payload] == [near_id, far_id]
    assert payload[0]["score"] > payload[1]["score"]
    assert FakeClapAdapter.queries == ["dark rolling techno"]


def test_repeated_text_search_reuses_one_loaded_adapter(monkeypatch, tmp_path: Path) -> None:
    FakeClapAdapter.queries = []
    FakeClapAdapter.instances = 0
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    _track_with_embedding(db, "near.wav", [0.0, 1.0, 0.0], "clap")
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)
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
    monkeypatch.setattr(api, "MuqMulanEmbeddingAdapter", FakeMulanAdapter)

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
    payload = response.json()
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
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

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
    payload = response.json()
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
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

    response = TestClient(create_app(db_path)).post(
        "/api/search/text",
        json={
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
            "positive_queries": ["broken drums."],
            "negative_queries": ["straight house groove."],
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
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

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
    payload = response.json()
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
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

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
    payload = response.json()
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
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)

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
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)
    client = TestClient(create_app(db_path))

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


def test_text_search_feedback_stores_updates_and_withdraws_verdicts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _track_with_embedding(db, "judged.wav", [0.0, 1.0, 0.0], "clap")
    with db.connect() as connection:
        track_uuid = connection.execute(
            "SELECT track_uuid FROM tracks WHERE track_id = ?",
            (track_id,),
        ).fetchone()[0]
    client = TestClient(create_app(db_path))

    stored = client.post(
        "/api/search/text/feedback",
        json={
            "track_uuid": track_uuid,
            "preset_keys": ["mood/dark", "tension/uneasy"],
            "analysis_family": "clap",
            "verdict": 1,
        },
    )
    assert stored.status_code == 200
    assert stored.json() == {"presets": 2, "verdict": 1}

    flipped = client.post(
        "/api/search/text/feedback",
        json={
            "track_uuid": track_uuid,
            "preset_keys": ["mood/dark"],
            "analysis_family": "clap",
            "verdict": -1,
        },
    )
    assert flipped.status_code == 200
    with db.connect() as connection:
        rows = connection.execute(
            """
            SELECT preset_key, verdict FROM text_preset_feedback
            ORDER BY preset_key
            """
        ).fetchall()
    assert [(row[0], row[1]) for row in rows] == [
        ("mood/dark", -1),
        ("tension/uneasy", 1),
    ]

    withdrawn = client.post(
        "/api/search/text/feedback",
        json={
            "track_uuid": track_uuid,
            "preset_keys": ["mood/dark", "tension/uneasy"],
            "analysis_family": "clap",
            "verdict": 0,
        },
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json() == {"presets": 2, "verdict": 0}
    with db.connect() as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM text_preset_feedback"
        ).fetchone()[0]
    assert remaining == 0

    missing = client.post(
        "/api/search/text/feedback",
        json={
            "track_uuid": "no-such-track",
            "preset_keys": ["mood/dark"],
            "analysis_family": "clap",
            "verdict": 1,
        },
    )
    assert missing.status_code == 404


def test_text_search_feedback_lookup_returns_only_a_settled_verdict(
    tmp_path: Path,
) -> None:
    """A page of results must come back carrying what was already said about it.

    The tab used to keep verdicts in component state only, so the same track
    returned unmarked in the next search and invited a second, blinder vote.
    Where an older selection disagrees with the current one the track is
    reported as unmarked rather than as whichever row sorted first.
    """

    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    agreed = _track_with_embedding(db, "agreed.wav", [1.0, 0.0, 0.0], "clap")
    conflicted = _track_with_embedding(db, "conflicted.wav", [0.0, 1.0, 0.0], "clap")
    silent = _track_with_embedding(db, "silent.wav", [0.0, 0.0, 1.0], "clap")
    with db.connect() as connection:
        uuids = {
            row[0]: row[1]
            for row in connection.execute(
                "SELECT track_id, track_uuid FROM tracks"
            ).fetchall()
        }
    client = TestClient(create_app(db_path))

    for keys, track_id, verdict in (
        (["mood/dark", "texture/lo-fi"], agreed, 1),
        (["mood/dark"], conflicted, 1),
        (["texture/lo-fi"], conflicted, -1),
    ):
        posted = client.post(
            "/api/search/text/feedback",
            json={
                "track_uuid": uuids[track_id],
                "preset_keys": keys,
                "analysis_family": "clap",
                "verdict": verdict,
            },
        )
        assert posted.status_code == 200

    looked_up = client.post(
        "/api/search/text/feedback/lookup",
        json={
            "track_uuids": [uuids[agreed], uuids[conflicted], uuids[silent]],
            "preset_keys": ["mood/dark", "texture/lo-fi"],
            "analysis_family": "clap",
        },
    )
    assert looked_up.status_code == 200
    # The agreed track answers, the conflicted one stays quiet, and the track
    # nobody judged is absent rather than reported as neutral.
    assert looked_up.json() == {"verdicts": {uuids[agreed]: 1}}

    # The verdict belongs to one embedding family, so the other family's tab
    # must not inherit it.
    other_family = client.post(
        "/api/search/text/feedback/lookup",
        json={
            "track_uuids": [uuids[agreed]],
            "preset_keys": ["mood/dark", "texture/lo-fi"],
            "analysis_family": "mulan",
        },
    )
    assert other_family.status_code == 200
    assert other_family.json() == {"verdicts": {}}


def test_text_search_feedback_lookup_rejects_unknown_contract_fields(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    client = TestClient(create_app(db_path))

    rejected = client.post(
        "/api/search/text/feedback/lookup",
        json={
            "track_uuids": ["whatever"],
            "preset_keys": ["mood/dark"],
            "analysis_family": "clap",
            "limit": 10,
        },
    )
    assert rejected.status_code == 422


def test_text_search_feedback_records_how_many_presets_shared_the_click(
    tmp_path: Path,
) -> None:
    """One click on a merged bank is one opinion, not one per label.

    Without the count every row of a four-label selection looked like an
    independent example of its own label, which inflates a single judgement
    fourfold and teaches three labels from a track that may have matched only
    the fourth. The column does not say which label earned it; it says the
    answer was shared, so scripts/prompt_preset_tune.py can weight it at 1/n.
    """

    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _track_with_embedding(db, "shared.wav", [1.0, 0.0, 0.0], "clap")
    with db.connect() as connection:
        track_uuid = connection.execute(
            "SELECT track_uuid FROM tracks WHERE track_id = ?",
            (track_id,),
        ).fetchone()[0]
    client = TestClient(create_app(db_path))

    shared = client.post(
        "/api/search/text/feedback",
        json={
            "track_uuid": track_uuid,
            "preset_keys": ["mood/dark", "texture/lo-fi", "rhythm/breakbeat"],
            "analysis_family": "clap",
            "verdict": 1,
        },
    )
    assert shared.status_code == 200
    with db.connect() as connection:
        rows = connection.execute(
            """
            SELECT preset_key, selection_size FROM text_preset_feedback
            ORDER BY preset_key
            """
        ).fetchall()
    assert [(row[0], row[1]) for row in rows] == [
        ("mood/dark", 3),
        ("rhythm/breakbeat", 3),
        ("texture/lo-fi", 3),
    ]

    # Judging the same track again from a narrower bank replaces the count, so
    # the sharpest answer is the one that stands.
    alone = client.post(
        "/api/search/text/feedback",
        json={
            "track_uuid": track_uuid,
            "preset_keys": ["mood/dark"],
            "analysis_family": "clap",
            "verdict": 1,
        },
    )
    assert alone.status_code == 200
    with db.connect() as connection:
        sizes = dict(
            connection.execute(
                "SELECT preset_key, selection_size FROM text_preset_feedback"
            ).fetchall()
        )
    assert sizes["mood/dark"] == 1
    assert sizes["texture/lo-fi"] == 3


def test_text_search_reports_each_label_contribution_and_credits_by_it(
    monkeypatch, tmp_path: Path
) -> None:
    """A merged bank cannot say which label a hit came from; naming them can.

    Without this a verdict is split evenly across everything that happened to
    be selected, which teaches the labels that did not match. With each label's
    own bank named, the search reports how well each one matched, and the click
    is credited in that proportion.
    """

    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    # The track sits exactly on the axis that "broken drums." names and square
    # to the one that "straight house groove." names.
    track_id = _track_with_embedding(db, "broken.wav", [1.0, 0.0, 0.0], "clap")
    with db.connect() as connection:
        track_uuid = connection.execute(
            "SELECT track_uuid FROM tracks WHERE track_id = ?",
            (track_id,),
        ).fetchone()[0]
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)
    client = TestClient(create_app(db_path))

    found = client.post(
        "/api/search/text",
        json={
            "analysis_family": "clap",
            "positive_queries": ["broken drums.", "straight house groove."],
            "preset_banks": [
                {"key": "rhythm/breakbeat", "positive_queries": ["broken drums."]},
                {"key": "rhythm/four-on-the-floor", "positive_queries": ["straight house groove."]},
            ],
            "limit": 5,
        },
    )
    assert found.status_code == 200
    hit = found.json()[0]
    contributions = hit["preset_scores"]
    assert set(contributions) == {"rhythm/breakbeat", "rhythm/four-on-the-floor"}
    # The breakbeat bank points at the track; the four-on-the-floor bank is
    # orthogonal to it, so it contributed nothing.
    assert contributions["rhythm/breakbeat"] > contributions["rhythm/four-on-the-floor"]

    judged = client.post(
        "/api/search/text/feedback",
        json={
            "track_uuid": track_uuid,
            "preset_keys": ["rhythm/breakbeat", "rhythm/four-on-the-floor"],
            "analysis_family": "clap",
            "verdict": 1,
            "preset_scores": contributions,
        },
    )
    assert judged.status_code == 200
    with db.connect() as connection:
        weights = dict(
            connection.execute(
                "SELECT preset_key, weight FROM text_preset_feedback"
            ).fetchall()
        )
    # One click, one opinion: the shares add up to it, and the label that
    # matched carries almost all of it.
    assert weights["rhythm/breakbeat"] > weights["rhythm/four-on-the-floor"]
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_text_search_feedback_splits_a_click_evenly_without_contributions(
    tmp_path: Path,
) -> None:
    """Where the search did not name the banks, an even split is all that is known."""

    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _track_with_embedding(db, "even.wav", [1.0, 0.0, 0.0], "clap")
    with db.connect() as connection:
        track_uuid = connection.execute(
            "SELECT track_uuid FROM tracks WHERE track_id = ?",
            (track_id,),
        ).fetchone()[0]
    client = TestClient(create_app(db_path))

    posted = client.post(
        "/api/search/text/feedback",
        json={
            "track_uuid": track_uuid,
            "preset_keys": ["mood/dark", "texture/lo-fi", "space/roomy", "energy/loud"],
            "analysis_family": "clap",
            "verdict": -1,
        },
    )
    assert posted.status_code == 200
    with db.connect() as connection:
        weights = [
            row[0]
            for row in connection.execute("SELECT weight FROM text_preset_feedback")
        ]
    assert weights == [0.25, 0.25, 0.25, 0.25]


def test_text_search_feedback_summary_counts_what_stands_behind_each_label(
    tmp_path: Path,
) -> None:
    """The picker needs to know which labels have been judged and by which model.

    A label nobody has marked is absent rather than reported as zero, so the
    tally distinguishes "nothing here yet" from "judged and evenly split" —
    the difference that decides where comparing the two models is worth doing.
    """

    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    hit = _track_with_embedding(db, "hit.wav", [1.0, 0.0, 0.0], "clap")
    miss = _track_with_embedding(db, "miss.wav", [0.0, 1.0, 0.0], "clap")
    with db.connect() as connection:
        uuids = dict(
            connection.execute("SELECT track_id, track_uuid FROM tracks").fetchall()
        )
    client = TestClient(create_app(db_path))

    empty = client.get("/api/search/text/feedback/summary")
    assert empty.status_code == 200
    assert empty.json() == {"presets": {}}

    for track_id, family, verdict in (
        (hit, "clap", 1),
        (miss, "clap", -1),
        (hit, "mulan", 1),
    ):
        posted = client.post(
            "/api/search/text/feedback",
            json={
                "track_uuid": uuids[track_id],
                "preset_keys": ["rhythm/breakbeat"],
                "analysis_family": family,
                "verdict": verdict,
            },
        )
        assert posted.status_code == 200

    summary = client.get("/api/search/text/feedback/summary")
    assert summary.status_code == 200
    assert summary.json() == {
        "presets": {
            "rhythm/breakbeat": {
                "clap": {"relevant": 1, "irrelevant": 1},
                "mulan": {"relevant": 1, "irrelevant": 0},
            }
        }
    }


def test_text_search_pulls_the_query_toward_the_tracks_that_were_kept(
    monkeypatch, tmp_path: Path
) -> None:
    """Rocchio feedback, off by default and never silent.

    The words alone put a distractor above the judged neighbourhood. With the
    accumulated opinion allowed in, that order reverses — and the words still
    hold most of the weight, so this is an adjustment rather than a takeover.
    """

    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    # "broken drums." embeds to [1, 0, 0]. The judged tracks sit off that axis,
    # and the distractor sits slightly closer to it than they do.
    kept = [
        _track_with_embedding(db, f"kept{index}.wav", [0.5, 0.866, 0.0], "clap")
        for index in range(3)
    ]
    distractor = _track_with_embedding(db, "distractor.wav", [0.55, 0.0, 0.835], "clap")
    with db.connect() as connection:
        uuids = dict(
            connection.execute("SELECT track_id, track_uuid FROM tracks").fetchall()
        )
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)
    client = TestClient(create_app(db_path))

    for track_id in kept:
        posted = client.post(
            "/api/search/text/feedback",
            json={
                "track_uuid": uuids[track_id],
                "preset_keys": ["rhythm/breakbeat"],
                "analysis_family": "clap",
                "verdict": 1,
            },
        )
        assert posted.status_code == 200

    body = {
        "analysis_family": "clap",
        "positive_queries": ["broken drums."],
        "preset_banks": [
            {"key": "rhythm/breakbeat", "positive_queries": ["broken drums."]}
        ],
        "limit": 5,
    }
    plain = [row["track"]["track_id"] for row in client.post("/api/search/text", json={**body}).json()]
    assert plain[0] == distractor

    adjusted = [
        row["track"]["track_id"]
        for row in client.post("/api/search/text", json={**body, "use_feedback": True}).json()
    ]
    assert adjusted[0] in kept
    assert adjusted.index(distractor) > 0
    # Nothing is dropped: the shift reorders the same library rather than
    # filtering it to what was already approved.
    assert sorted(adjusted) == sorted(plain)


def test_text_search_ignores_a_history_too_small_to_mean_anything(
    monkeypatch, tmp_path: Path
) -> None:
    """Two verdicts are an afternoon, not an opinion, so the query stays put."""

    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    kept = [
        _track_with_embedding(db, f"few{index}.wav", [0.2, 0.98, 0.0], "clap")
        for index in range(2)
    ]
    on_words = _track_with_embedding(db, "words.wav", [1.0, 0.0, 0.0], "clap")
    with db.connect() as connection:
        uuids = dict(
            connection.execute("SELECT track_id, track_uuid FROM tracks").fetchall()
        )
    monkeypatch.setattr(api, "ClapEmbeddingAdapter", FakeClapAdapter)
    client = TestClient(create_app(db_path))
    for track_id in kept:
        client.post(
            "/api/search/text/feedback",
            json={
                "track_uuid": uuids[track_id],
                "preset_keys": ["rhythm/breakbeat"],
                "analysis_family": "clap",
                "verdict": 1,
            },
        )

    adjusted = client.post(
        "/api/search/text",
        json={
            "analysis_family": "clap",
            "positive_queries": ["broken drums."],
            "preset_banks": [
                {"key": "rhythm/breakbeat", "positive_queries": ["broken drums."]}
            ],
            "limit": 5,
            "use_feedback": True,
        },
    )
    assert adjusted.status_code == 200
    assert adjusted.json()[0]["track"]["track_id"] == on_words
