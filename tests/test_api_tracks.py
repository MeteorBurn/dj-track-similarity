from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

import numpy as np

import dj_track_similarity.api as api_module
import dj_track_similarity.database as database_module
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase


def test_tracks_endpoint_returns_paginated_slim_items_and_total(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    _add_track(db, tmp_path, "alpha.wav", "Artist A", "Alpha", {"comment": "large metadata"})
    _add_track(db, tmp_path, "beta.wav", "Artist B", "Beta", {"comment": "large metadata"})
    _add_track(db, tmp_path, "gamma.wav", "Artist C", "Gamma", {"comment": "large metadata"})

    response = TestClient(create_app(db_path)).get("/api/tracks?limit=2&offset=1&include_metadata=false")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert [item["title"] for item in payload["items"]] == ["Beta", "Gamma"]
    assert all(item["metadata"] is None for item in payload["items"])


def test_tracks_endpoint_does_not_parse_metadata_for_slim_items(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "analyzed.wav", "Artist", "Analyzed", {"comment": "large metadata"})
    db.save_sonara_features(track_id, {"energy": 0.7}, energy=0.7, model_name="sonara-test")
    db.save_genres(track_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    db.save_embedding(track_id, np.asarray([0.0, 1.0], dtype=np.float32), model_name="maest-test", embedding_key="maest")
    db.save_embedding(track_id, np.asarray([1.0, 0.0], dtype=np.float32), model_name="mert-test", embedding_key="mert")

    def fail_if_metadata_parsed(_metadata_json: object) -> dict[str, object]:
        raise AssertionError("slim track rows must not parse metadata_json")

    monkeypatch.setattr(database_module, "metadata_from_json", fail_if_metadata_parsed)

    response = TestClient(create_app(db_path)).get("/api/tracks?limit=1&include_metadata=false")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["metadata"] is None
    assert item["analyses"] == ["sonara", "maest", "mert"]


def test_tracks_endpoint_filters_by_query_and_syncopated_preset(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    house_id = _add_track(db, tmp_path, "house.wav", "DJ One", "Deep House", {})
    breaks_id = _add_track(db, tmp_path, "breaks.wav", "DJ Two", "Broken Rhythm", {})
    db.save_genres(house_id, [{"label": "House", "score": 0.8}], model_name="maest")
    db.save_genres(breaks_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest")
    client = TestClient(create_app(db_path))

    query_payload = client.get("/api/tracks?q=two").json()
    preset_payload = client.get("/api/tracks?preset=syncopated").json()

    assert query_payload["total"] == 1
    assert query_payload["items"][0]["id"] == breaks_id
    assert preset_payload["total"] == 1
    assert preset_payload["items"][0]["id"] == breaks_id


def test_tracks_endpoint_filters_by_min_break_energy(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    low_id = _add_track(db, tmp_path, "low.wav", "DJ One", "Low Energy", {})
    high_id = _add_track(db, tmp_path, "high.wav", "DJ Two", "High Energy", {})
    db.save_classifier_score(
        low_id,
        classifier="break_energy",
        score=0.71,
        label="medium",
        confidence=0.71,
        probabilities={"break_energy": 0.71, "straight_energy": 0.29},
        feature_set="combined",
        model_id="model.joblib",
    )
    db.save_classifier_score(
        high_id,
        classifier="break_energy",
        score=0.93,
        label="high",
        confidence=0.93,
        probabilities={"break_energy": 0.93, "straight_energy": 0.07},
        feature_set="combined",
        model_id="model.joblib",
    )
    client = TestClient(create_app(db_path))

    response = client.get("/api/tracks?min_break_energy=0.9")
    filtered = client.post("/api/tracks/filtered", json={"min_break_energy": 0.9})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["id"] == high_id
    assert payload["items"][0]["classifier_scores"]["break_energy"]["score"] == 0.93
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [high_id]


def test_filtered_tracks_endpoint_returns_all_matching_tracks_without_pagination(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    house_id = _add_track(db, tmp_path, "house.wav", "DJ One", "Deep House", {})
    breaks_id = _add_track(db, tmp_path, "breaks.wav", "DJ Two", "Broken Rhythm", {})
    garage_id = _add_track(db, tmp_path, "garage.wav", "DJ Three", "Broken Garage", {})
    db.save_genres(house_id, [{"label": "House", "score": 0.8}], model_name="maest")
    db.save_genres(breaks_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest")
    db.save_genres(garage_id, [{"label": "UK Garage", "score": 0.9}], model_name="maest")
    client = TestClient(create_app(db_path))

    response = client.post("/api/tracks/filtered", json={"query": "broken", "preset": "syncopated"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert [item["id"] for item in payload["items"]] == [garage_id, breaks_id]
    assert all(item["metadata"] is None for item in payload["items"])


def test_syncopated_preset_ignores_non_genre_metadata_text(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    house_id = _add_track(
        db,
        tmp_path,
        "house.wav",
        "DJ One",
        "Deep House",
        {"sonara_features": {"acousticness": {"description": "Acoustic versus electronic character estimate."}}},
    )
    db.save_genres(house_id, [{"label": "Tech House", "score": 0.8}], model_name="maest")
    client = TestClient(create_app(db_path))

    preset_payload = client.get("/api/tracks?preset=syncopated").json()

    assert preset_payload["total"] == 0
    assert preset_payload["items"] == []


def test_syncopated_preset_uses_stored_maest_syncopated_flag(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    legacy_breaks_id = _add_track(
        db,
        tmp_path,
        "legacy-breaks.wav",
        "DJ One",
        "Legacy Breaks",
        {"maest_genres": [{"label": "Breakbeat", "score": 0.9}], "maest_model": "legacy-maest"},
    )
    flagged_house_id = _add_track(
        db,
        tmp_path,
        "flagged-house.wav",
        "DJ Two",
        "Flagged House",
        {"maest_genres": [{"label": "House", "score": 0.8}], "maest_model": "maest", "maest_syncopated_rhythm": True},
    )
    client = TestClient(create_app(db_path))

    preset_payload = client.get("/api/tracks?preset=syncopated").json()

    assert preset_payload["total"] == 1
    assert preset_payload["items"][0]["id"] == flagged_house_id
    assert legacy_breaks_id != flagged_house_id


def test_track_detail_endpoint_returns_full_metadata(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "alpha.wav", "Artist", "Alpha", {"comment": "stored comment"})

    response = TestClient(create_app(db_path)).get(f"/api/tracks/{track_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == track_id
    assert payload["metadata"]["comment"] == "stored comment"


def test_library_summary_counts_tracks_and_analysis_families(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    sonara_id = _add_track(db, tmp_path, "sonara.wav", "Artist", "Sonara", {})
    maest_id = _add_track(db, tmp_path, "maest.wav", "Artist", "Maest", {})
    maest_genres_only_id = _add_track(db, tmp_path, "maest-genres-only.wav", "Artist", "Maest Genres Only", {})
    mert_id = _add_track(db, tmp_path, "mert.wav", "Artist", "Mert", {})
    db.save_sonara_features(sonara_id, {"energy": 0.7}, energy=0.7, model_name="sonara-test")
    db.save_genres(maest_id, [{"label": "Breakbeat", "score": 0.9}], model_name="maest-test")
    db.save_embedding(maest_id, np.asarray([0.0, 1.0], dtype=np.float32), model_name="maest-test", embedding_key="maest")
    db.save_genres(maest_genres_only_id, [{"label": "House", "score": 0.8}], model_name="maest-test")
    db.save_embedding(mert_id, np.asarray([1.0, 0.0], dtype=np.float32), model_name="mert-test", embedding_key="mert")

    response = TestClient(create_app(db_path)).get("/api/library/summary")

    assert response.status_code == 200
    assert response.json() == {"tracks": 4, "sonara": 1, "maest": 1, "mert": 1, "clap": 0}


def test_media_endpoint_transcodes_aiff_preview_to_browser_playable_wav(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _add_track(db, tmp_path, "preview.aiff", "Artist", "Preview", {})
    calls: list[list[str]] = []

    class FakeStdout:
        def __init__(self) -> None:
            self._chunks = [b"RIFF....WAVE", b""]

        def read(self, _size: int) -> bytes:
            return self._chunks.pop(0)

    class FakeProcess:
        def __init__(self, command: list[str], **_kwargs: object) -> None:
            calls.append(command)
            self.stdout = FakeStdout()

        def wait(self) -> int:
            return 0

        def poll(self) -> int:
            return 0

        def kill(self) -> None:
            raise AssertionError("completed transcode should not be killed")

    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg-test")
    monkeypatch.setattr(api_module, "subprocess", SimpleNamespace(Popen=FakeProcess, PIPE=-1, DEVNULL=-3), raising=False)

    response = TestClient(create_app(db_path)).get(f"/media/{track_id}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFF....WAVE"
    assert calls == [[
        "ffmpeg-test",
        "-v",
        "error",
        "-i",
        str(tmp_path / "preview.aiff"),
        "-vn",
        "-f",
        "wav",
        "-codec:a",
        "pcm_s16le",
        "pipe:1",
    ]]


def _add_track(
    db: LibraryDatabase,
    tmp_path: Path,
    filename: str,
    artist: str,
    title: str,
    metadata: dict[str, object],
) -> int:
    path = tmp_path / filename
    path.write_bytes(b"audio")
    return db.upsert_track(
        path=path,
        size=path.stat().st_size,
        mtime=1,
        metadata={"artist": artist, "title": title, **metadata},
    )
