from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.exporter import export_tracks
from dj_track_similarity.track_models import FileTags, ScannedFile, TrackIdentity


_SCANNED_AT = "2026-07-24T00:00:00.000000Z"


def _scan_track(
    database: LibraryDatabase,
    path: Path,
    *,
    artist: str,
    title: str,
    tag_bpm: float | None = None,
    tag_key: str | None = None,
) -> TrackIdentity:
    stat = path.stat()
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
        ),
        tags=FileTags(
            artist=artist,
            title=title,
            tag_bpm=tag_bpm,
            tag_key=tag_key,
        ),
        scanned_at=_SCANNED_AT,
    ).identity


def test_export_tracks_writes_m3u_and_csv_without_saved_playlist_storage(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first_path = tmp_path / "one.wav"
    second_path = tmp_path / "two.wav"
    first_path.write_bytes(b"one")
    second_path.write_bytes(b"two")
    first = _scan_track(
        db,
        first_path,
        artist="A",
        title="One",
        tag_bpm=124.0,
        tag_key="6A",
    )
    second = _scan_track(
        db,
        second_path,
        artist="B",
        title="Two",
        tag_bpm=126.0,
        tag_key="7A",
    )
    tracks = db.export_track_rows((first.track_id, second.track_id))
    source_bytes = (first_path.read_bytes(), second_path.read_bytes())

    m3u_path = export_tracks("seamless", tracks, tmp_path, "m3u")
    csv_path = export_tracks("seamless", tracks, tmp_path, "csv")

    assert m3u_path.read_text(encoding="utf-8").splitlines() == [
        "#EXTM3U",
        "#EXTINF:-1,A - One",
        tracks[0].file_path,
        "#EXTINF:-1,B - Two",
        tracks[1].file_path,
    ]
    assert csv_path.read_text(encoding="utf-8").splitlines() == [
        "artist,title,album,tag_bpm,tag_key,sonara_bpm,sonara_key,sonara_energy,file_path",
        f"A,One,,124.0,6A,,,,{tracks[0].file_path}",
        f"B,Two,,126.0,7A,,,,{tracks[1].file_path}",
    ]
    assert (first_path.read_bytes(), second_path.read_bytes()) == source_bytes


def test_export_endpoint_writes_current_track_list_without_saving_playlist(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    first_path = tmp_path / "one.wav"
    second_path = tmp_path / "two.wav"
    first_path.write_bytes(b"one")
    second_path.write_bytes(b"two")
    first = _scan_track(db, first_path, artist="A", title="One")
    second = _scan_track(db, second_path, artist="B", title="Two")

    response = TestClient(create_app(db_path)).post(
        "/api/export",
        json={
            "name": "live set",
            "track_ids": [second.track_id, first.track_id],
            "output_dir": str(tmp_path),
            "format": "m3u",
        },
    )

    assert response.status_code == 200
    export_path = Path(response.json()["path"])
    assert export_path.name == "live_set.m3u"
    tracks = db.export_track_rows((second.track_id, first.track_id))
    assert export_path.read_text(encoding="utf-8").splitlines() == [
        "#EXTM3U",
        "#EXTINF:-1,B - Two",
        tracks[0].file_path,
        "#EXTINF:-1,A - One",
        tracks[1].file_path,
    ]
    assert first_path.read_bytes() == b"one"
    assert second_path.read_bytes() == b"two"


def test_saved_playlist_endpoint_is_absent(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/playlists", json={"name": "old", "track_ids": []})

    assert response.status_code in {404, 405}
