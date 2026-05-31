from pathlib import Path

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


def _add_sonara_track(db: LibraryDatabase, name: str, features: dict[str, object]) -> int:
    path = Path("C:/music") / name
    track_id = db.upsert_track(path=path, size=100, mtime=1, metadata={"title": name})
    db.save_sonara_features(
        track_id,
        features,
        bpm=float(features["bpm"]) if "bpm" in features else None,
        musical_key=str(features["key"]) if features.get("key") else None,
        energy=float(features["energy"]) if "energy" in features else None,
        duration=float(features["duration_sec"]) if "duration_sec" in features else None,
    )
    return track_id
