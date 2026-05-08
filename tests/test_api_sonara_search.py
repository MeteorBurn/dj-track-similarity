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
