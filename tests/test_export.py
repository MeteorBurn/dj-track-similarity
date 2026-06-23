from pathlib import Path

from fastapi.testclient import TestClient

from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.exporter import export_tracks


def test_export_tracks_writes_m3u_and_csv_without_saved_playlist_storage(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first = db.upsert_track(
        path=Path("C:/music/one.wav"),
        size=10,
        mtime=1,
        metadata={"artist": "A", "title": "One"},
        bpm=124,
        musical_key="6A",
        energy=0.4,
    )
    second = db.upsert_track(
        path=Path("C:/music/two.wav"),
        size=20,
        mtime=1,
        metadata={"artist": "B", "title": "Two"},
        bpm=126,
        musical_key="7A",
        energy=0.5,
    )
    tracks = [db.get_track(first), db.get_track(second)]

    m3u_path = export_tracks("seamless", tracks, tmp_path, "m3u")
    csv_path = export_tracks("seamless", tracks, tmp_path, "csv")

    assert m3u_path.read_text(encoding="utf-8").splitlines() == [
        "#EXTM3U",
        "#EXTINF:-1,A - One",
        "C:/music/one.wav",
        "#EXTINF:-1,B - Two",
        "C:/music/two.wav",
    ]
    csv_text = csv_path.read_text(encoding="utf-8")
    assert "artist,title,bpm,key,energy,path" in csv_text
    assert "A,One,124.0,6A,0.4,C:/music/one.wav" in csv_text
    assert "B,Two,126.0,7A,0.5,C:/music/two.wav" in csv_text


def test_export_endpoint_writes_current_track_list_without_saving_playlist(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    first = db.upsert_track(
        path=Path("C:/music/one.wav"),
        size=10,
        mtime=1,
        metadata={"artist": "A", "title": "One"},
    )
    second = db.upsert_track(
        path=Path("C:/music/two.wav"),
        size=20,
        mtime=1,
        metadata={"artist": "B", "title": "Two"},
    )
    client = TestClient(create_app(db_path))

    response = client.post(
        "/api/export",
        json={"name": "live set", "track_ids": [second, first], "output_dir": str(tmp_path), "format": "m3u"},
    )

    assert response.status_code == 200
    export_path = Path(response.json()["path"])
    assert export_path.name == "live_set.m3u"
    assert export_path.read_text(encoding="utf-8").splitlines() == [
        "#EXTM3U",
        "#EXTINF:-1,B - Two",
        "C:/music/two.wav",
        "#EXTINF:-1,A - One",
        "C:/music/one.wav",
    ]
    with db.connect() as connection:
        tables = {row["name"] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "playlists" not in tables
    assert "playlist_tracks" not in tables


def test_saved_playlist_endpoint_is_not_available(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/playlists", json={"name": "old", "track_ids": []})

    assert response.status_code == 404
