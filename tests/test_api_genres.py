from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.database import LibraryDatabase


class SynchronousGenreManager:
    last_batch_size = None

    def __init__(self, db):
        self.db = db

    def start(self, *, limit=None, device="auto", top_k=5, batch_size=1):
        type(self).last_batch_size = batch_size
        tracks = self.db.list_tracks()
        if limit is not None:
            tracks = tracks[:limit]
        for track in tracks:
            self.db.save_genres(track.id, [{"label": "Techno", "score": 0.95}], model_name="fake-maest")
        return {
            "job_id": "job-1",
            "state": "completed",
            "adapter_name": "maest",
            "model_name": "fake-maest",
            "device": device,
            "device_requested": device,
            "total": len(tracks),
            "processed": len(tracks),
            "analyzed": len(tracks),
            "failed": 0,
            "current_path": None,
            "started_at": 1,
            "finished_at": 2,
            "avg_seconds_per_track": 1,
            "errors": [],
            "events": [],
            "cancel_requested": False,
            "top_k": top_k,
            "batch_size": batch_size,
            "workers": batch_size,
        }

    def latest(self):
        return None

    def get(self, job_id):
        raise KeyError(job_id)

    def cancel(self, job_id):
        raise KeyError(job_id)


def test_api_runs_maest_genre_analysis_and_returns_track_genres(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    db.upsert_track(path=tmp_path / "track.wav", size=10, mtime=1, metadata={"title": "Track"})
    monkeypatch.setattr(api, "GenreAnalysisJobManager", SynchronousGenreManager)

    client = TestClient(api.create_app(db_path))
    response = client.post("/api/genres/analyze", json={"limit": 1, "device": "cpu", "top_k": 1, "batch_size": 4})

    assert response.status_code == 200
    assert response.json()["analyzed"] == 1
    assert response.json()["batch_size"] == 4
    assert response.json()["workers"] == 4
    assert SynchronousGenreManager.last_batch_size == 4
    tracks = client.get("/api/tracks").json()
    assert tracks[0]["genres"] == ["Techno"]
    assert tracks[0]["genre_scores"] == {"Techno": 0.95}
