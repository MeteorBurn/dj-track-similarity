from pathlib import Path

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.exporter import export_playlist


def test_export_playlist_writes_m3u_and_csv(tmp_path: Path) -> None:
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
    playlist_id = db.create_playlist("seamless", [first, second])

    m3u_path = export_playlist(db, playlist_id, tmp_path, "m3u")
    csv_path = export_playlist(db, playlist_id, tmp_path, "csv")

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
