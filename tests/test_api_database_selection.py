from pathlib import Path

from fastapi.testclient import TestClient

import dj_track_similarity.api as api
import dj_track_similarity.api_state as api_state
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase


def test_app_without_db_starts_unselected_and_blocks_database_endpoints() -> None:
    client = TestClient(create_app())

    current = client.get("/api/database/current")
    summary = client.get("/api/library/summary")

    assert current.status_code == 200
    assert current.json() == {"path": None, "selected": False, "music_root": None}
    assert summary.status_code == 400
    assert summary.json()["detail"] == "Database is not selected"


def test_database_switch_creates_new_sqlite_file(tmp_path: Path) -> None:
    db_path = tmp_path / "new-library.sqlite"
    client = TestClient(create_app())

    response = client.post("/api/database/switch", json={"path": str(db_path)})

    assert response.status_code == 200
    assert response.json() == {"path": str(db_path.resolve()), "selected": True, "music_root": None}
    assert db_path.exists()
    assert client.get("/api/library/summary").json() == {
        "tracks": 0,
        "sonara": 0,
        "maest": 0,
        "mert": 0,
        "clap": 0,
        "liked": 0,
        "classifiers": 0,
    }


def test_database_switch_to_existing_sqlite_reads_existing_tracks(tmp_path: Path) -> None:
    db_path = tmp_path / "existing.sqlite"
    audio_path = tmp_path / "track.wav"
    audio_path.write_bytes(b"audio")
    db = LibraryDatabase(db_path)
    db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Stored Track"})
    db.set_library_root(tmp_path / "music")
    client = TestClient(create_app())

    response = client.post("/api/database/switch", json={"path": str(db_path)})

    assert response.status_code == 200
    assert response.json()["music_root"] == (tmp_path / "music").as_posix()
    tracks = client.get("/api/tracks").json()
    assert tracks["total"] == 1
    assert tracks["items"][0]["title"] == "Stored Track"


def test_database_file_dialog_switches_to_selected_path(monkeypatch, tmp_path: Path) -> None:
    selected = tmp_path / "picked.sqlite"
    monkeypatch.setattr(api, "open_database_file_dialog", lambda: selected, raising=False)
    client = TestClient(create_app())

    response = client.post("/api/database/dialog")

    assert response.status_code == 200
    assert response.json() == {"path": str(selected.resolve()), "selected": True, "music_root": None}
    assert selected.exists()


def test_scan_saves_library_root_in_database(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    music_root = tmp_path / "music"
    music_root.mkdir()
    client = TestClient(create_app(db_path))

    response = client.post("/api/library/scan", json={"root": str(music_root), "workers": 1})

    assert response.status_code == 200
    assert client.get("/api/database/current").json()["music_root"] == music_root.as_posix()
    assert LibraryDatabase(db_path).get_library_root() == music_root.as_posix()


def test_scan_rejects_missing_library_root_without_saving_it(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    missing_root = tmp_path / "missing"
    client = TestClient(create_app(db_path))

    response = client.post("/api/library/scan", json={"root": str(missing_root), "workers": 1})

    assert response.status_code == 400
    assert "missing" in response.json()["detail"]
    assert client.get("/api/database/current").json()["music_root"] is None
    assert LibraryDatabase(db_path).get_library_root() is None


def test_library_root_endpoint_is_absent_and_cannot_save_root(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    music_root = tmp_path / "music"
    music_root.mkdir()
    client = TestClient(create_app(db_path))

    response = client.post("/api/library/root", json={"root": str(music_root)})

    # With a built frontend bundle, Starlette's static mount can answer unknown
    # POST routes with 405 instead of FastAPI's 404. Either code proves there is
    # no successful API endpoint for saving the root outside a scan.
    assert response.status_code in {404, 405}
    assert client.get("/api/database/current").json()["music_root"] is None
    assert LibraryDatabase(db_path).get_library_root() is None


def test_database_switch_is_rejected_while_scan_job_is_queued(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    next_db_path = tmp_path / "next.sqlite"
    music_root = tmp_path / "music"
    music_root.mkdir()

    def queue_without_running(self: api_state.ScanJobManager, root: str | Path, *, workers: int = 1):
        job_id = self.create_job(root, workers=workers)
        return self.get(job_id)

    monkeypatch.setattr(api_state.ScanJobManager, "start", queue_without_running)
    client = TestClient(create_app(db_path))

    scan_response = client.post("/api/library/scan", json={"root": str(music_root), "workers": 1})
    switch_response = client.post("/api/database/switch", json={"path": str(next_db_path)})

    assert scan_response.status_code == 200
    assert scan_response.json()["state"] == "queued"
    assert switch_response.status_code == 409
    assert switch_response.json()["detail"] == "Cannot switch database while jobs are running"
