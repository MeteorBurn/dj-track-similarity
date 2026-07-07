from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase


def test_sonara_search_endpoint_uses_stored_sonara_features(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed = _add_sonara_track(db, "seed.wav", {"energy": 0.8, "danceability": 0.8, "valence": 0.25, "acousticness": 0.1})
    close = _add_sonara_track(db, "close.wav", {"energy": 0.78, "danceability": 0.79, "valence": 0.27, "acousticness": 0.12})
    far = _add_sonara_track(db, "far.wav", {"energy": 0.15, "danceability": 0.2, "valence": 0.8, "acousticness": 0.65})

    response = TestClient(create_app(db_path)).post(
        "/api/search/sonara",
        json={"seed_track_ids": [seed], "mode": "vibe", "limit": 5, "min_similarity": 0.0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["id"] for item in payload] == [close, far]
    assert payload[0]["score"] > payload[1]["score"]


def test_generic_search_endpoint_returns_mert_result_shape(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed_id = _add_embedding_track(db, "seed.wav", [1.0, 0.0])
    candidate_id = _add_embedding_track(db, "candidate.wav", [0.9, 0.1])

    response = TestClient(create_app(db_path)).post(
        "/api/search",
        json={"seed_track_ids": [seed_id], "limit": 1, "min_similarity": 0.0, "Epsilon": 0.0, "noise": 0.0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["track"]["id"] == candidate_id
    assert payload[0]["score"] > 0.0
    assert payload[0]["score_breakdown"] is None


def test_sonara_search_endpoint_accepts_custom_mixer_and_modifiers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    seed = _add_sonara_track(
        db,
        "seed.wav",
        {"mfcc_mean": [0.2, 0.4], "spectral_centroid_mean": 1600, "valence": 0.4, "energy": 0.5},
    )
    brighter = _add_sonara_track(
        db,
        "brighter.wav",
        {"mfcc_mean": [0.22, 0.41], "spectral_centroid_mean": 1620, "valence": 0.7, "energy": 0.5},
    )
    darker = _add_sonara_track(
        db,
        "darker.wav",
        {"mfcc_mean": [0.21, 0.39], "spectral_centroid_mean": 1580, "valence": 0.2, "energy": 0.5},
    )

    response = TestClient(create_app(db_path)).post(
        "/api/search/sonara",
        json={
            "seed_track_ids": [seed],
            "mode": "custom",
            "limit": 5,
            "min_similarity": 0.0,
            "mixer_weights": {"timbre": 1.0, "rhythm": 0.0, "dynamics": 0.0, "harmonic": 0.0, "tempo": 0.0},
            "modifiers": {"valence": 1.0},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["id"] for item in payload] == [brighter, darker]
    assert "timbre" in payload[0]["score_breakdown"]
    assert "modifier_valence" in payload[0]["score_breakdown"]


def test_search_endpoints_reject_unknown_context_parameter(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    client = TestClient(create_app(tmp_path / "library.sqlite"))
    unknown_context_key = "extra_context_track_ids"

    mert_response = client.post("/api/search", json={"seed_track_ids": [], unknown_context_key: [1]})
    sonara_response = client.post("/api/search/sonara", json={"seed_track_ids": [], unknown_context_key: [1]})

    assert mert_response.status_code == 422
    assert sonara_response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": 501},
        {"min_similarity": -0.1},
        {"min_similarity": 1.1},
        {"bpm_tolerance": -0.1},
        {"energy_min": -0.1},
        {"energy_max": 1.1},
        {"energy_min": 0.8, "energy_max": 0.2},
        {"epsilon": -0.1},
        {"noise": -0.1},
        {"noise": 1.1},
    ],
)
def test_generic_search_endpoint_rejects_invalid_numeric_fields(monkeypatch, tmp_path: Path, payload: dict[str, float]) -> None:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg", raising=False)
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/search", json={"seed_track_ids": [1], **payload})

    assert response.status_code == 422


def _add_sonara_track(db: LibraryDatabase, name: str, features: dict[str, float | str | list[float]]) -> int:
    path = Path("C:/music") / name
    track_id = db.upsert_track(path=path, size=100, mtime=1, metadata={"title": name})
    bpm = features.get("bpm")
    musical_key = features.get("key")
    energy = features.get("energy")
    duration = features.get("duration_sec")
    feature_payload: dict[str, object] = dict(features)
    db.save_sonara_features(
        track_id,
        feature_payload,
        bpm=float(bpm) if isinstance(bpm, (float, int, str)) else None,
        musical_key=str(musical_key) if musical_key else None,
        energy=float(energy) if isinstance(energy, (float, int, str)) else None,
        duration=float(duration) if isinstance(duration, (float, int, str)) else None,
    )
    return track_id


def _add_embedding_track(db: LibraryDatabase, name: str, embedding: list[float]) -> int:
    path = Path("C:/music") / name
    track_id = db.upsert_track(path=path, size=100, mtime=1, metadata={"title": name})
    db.save_embedding(track_id, np.asarray(embedding, dtype=np.float32), "mert-test", embedding_key="mert")
    return track_id
