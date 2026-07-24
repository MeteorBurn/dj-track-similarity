from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from dj_track_similarity import api as api_module
from dj_track_similarity import media_preview as media_preview_module
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.track_models import FileTags, ScannedFile, TrackIdentity


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg")
    return TestClient(api_module.create_app(db_path))


def _add_track(
    database: LibraryDatabase,
    path: Path,
    *,
    artist: str,
    title: str,
    comment: str | None = None,
) -> TrackIdentity:
    path.write_bytes(b"audio")
    stat = path.stat()
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format=path.suffix.lstrip("."),
            audio_codec="pcm_s16le",
            sample_rate_hz=44_100,
            channel_count=2,
            bit_rate_bps=1_411_200,
            audio_duration_seconds=1.0,
        ),
        tags=FileTags(
            title=title,
            artist=artist,
            album="API Fixtures",
            tag_bpm=128.0,
            tag_key="8A",
            comment=comment,
            genres=("House",),
        ),
    ).identity


def _liked_payload(identity: TrackIdentity, liked: bool) -> dict[str, object]:
    return {
        "catalog_uuid": identity.catalog_uuid,
        "track_uuid": identity.track_uuid,
        "expected_content_generation": identity.content_generation,
        "liked": liked,
    }


def test_tracks_endpoint_returns_paginated_typed_v7_summaries(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    _add_track(
        database,
        tmp_path / "alpha.wav",
        artist="Artist A",
        title="Alpha",
    )
    beta = _add_track(
        database,
        tmp_path / "beta.wav",
        artist="Artist B",
        title="Beta",
    )
    gamma = _add_track(
        database,
        tmp_path / "gamma.wav",
        artist="Artist C",
        title="Gamma",
    )

    response = _client(monkeypatch, db_path).get(
        "/api/tracks",
        params={"limit": 2, "offset": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 1
    assert [item["title"] for item in payload["items"]] == ["Beta", "Gamma"]
    assert [item["track_id"] for item in payload["items"]] == [
        beta.track_id,
        gamma.track_id,
    ]
    assert all(item["catalog_uuid"] == beta.catalog_uuid for item in payload["items"])
    assert all(item["content_generation"] == 1 for item in payload["items"])
    assert all("metadata" not in item and "id" not in item for item in payload["items"])


def test_tracks_endpoints_return_empty_v7_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    client = _client(monkeypatch, tmp_path / "library.sqlite")

    page = client.get("/api/tracks", params={"limit": 50, "offset": 0})
    filtered = client.post(
        "/api/tracks/filtered",
        json={"query": "missing", "liked": True},
    )

    assert page.status_code == 200
    assert page.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}
    assert filtered.status_code == 200
    assert filtered.json() == []


def test_tracks_endpoint_keeps_like_default_and_supports_fts(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    substring = _add_track(
        database,
        tmp_path / "substring.wav",
        artist="DJ One",
        title="AlphaBeta",
    )
    token = _add_track(
        database,
        tmp_path / "token.wav",
        artist="DJ Two",
        title="Deep House",
    )
    client = _client(monkeypatch, db_path)

    like_payload = client.get("/api/tracks", params={"q": "phaB"}).json()
    fts_substring = client.get(
        "/api/tracks",
        params={"q": "phaB", "search_mode": "fts"},
    ).json()
    fts_token = client.get(
        "/api/tracks",
        params={"q": "deep house", "search_mode": "fts"},
    ).json()
    invalid = client.get(
        "/api/tracks",
        params={"q": "deep", "search_mode": "legacy"},
    )

    assert [item["track_id"] for item in like_payload["items"]] == [
        substring.track_id
    ]
    assert fts_substring["total"] == 0
    assert [item["track_id"] for item in fts_token["items"]] == [token.track_id]
    assert invalid.status_code == 422


def test_tracks_endpoint_liked_mutation_uses_composite_cas(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    identity = _add_track(
        LibraryDatabase(db_path),
        tmp_path / "liked.wav",
        artist="DJ",
        title="Liked",
    )
    client = _client(monkeypatch, db_path)
    url = f"/api/tracks/{identity.track_id}/liked"

    stale = client.post(
        url,
        json={
            **_liked_payload(identity, True),
            "expected_content_generation": identity.content_generation + 1,
        },
    )
    liked = client.post(url, json=_liked_payload(identity, True))
    liked_page = client.get("/api/tracks", params={"liked": "true"})
    unliked = client.post(url, json=_liked_payload(identity, False))

    assert stale.status_code == 409
    assert liked.status_code == 200
    assert liked.json()["liked"] is True
    assert liked.json()["track_uuid"] == identity.track_uuid
    assert [
        item["track_id"] for item in liked_page.json()["items"]
    ] == [identity.track_id]
    assert unliked.status_code == 200
    assert unliked.json()["liked"] is False


def test_track_detail_endpoint_returns_full_typed_tags(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    identity = _add_track(
        LibraryDatabase(db_path),
        tmp_path / "alpha.wav",
        artist="Artist",
        title="Alpha",
        comment="stored comment",
    )

    response = _client(monkeypatch, db_path).get(
        f"/api/tracks/{identity.track_id}"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["track_id"] == identity.track_id
    assert payload["catalog_uuid"] == identity.catalog_uuid
    assert payload["track_uuid"] == identity.track_uuid
    assert payload["content_generation"] == identity.content_generation
    assert payload["file_tags"]["comment"] == "stored comment"
    assert payload["file"]["file_size_bytes"] == 5


def test_library_summary_uses_split_v7_analysis_families(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    _add_track(
        LibraryDatabase(db_path),
        tmp_path / "track.wav",
        artist="Artist",
        title="Track",
    )

    response = _client(monkeypatch, db_path).get("/api/library/summary")

    assert response.status_code == 200
    assert response.json() == {
        "tracks": 1,
        "sonara": 0,
        "maest_analysis": 0,
        "maest_embedding": 0,
        "mert": 0,
        "muq": 0,
        "clap": 0,
        "liked": 0,
        "classifiers": 0,
    }


def test_media_endpoint_reports_missing_audio_file_without_traceback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    source = tmp_path / "missing.wav"
    identity = _add_track(
        LibraryDatabase(db_path),
        source,
        artist="Artist",
        title="Missing",
    )
    source.unlink()

    response = _client(
        monkeypatch,
        db_path,
    ).get(f"/media/{identity.track_id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Audio file is missing"}
    assert "Traceback" not in response.text


def test_media_endpoint_transcodes_aiff_without_modifying_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    source = tmp_path / "preview.aiff"
    identity = _add_track(
        LibraryDatabase(db_path),
        source,
        artist="Artist",
        title="Preview",
    )
    source_bytes = source.read_bytes()
    calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        stderr: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        Path(command[-1]).write_bytes(b"RIFFbrowser-compatible-wav")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg-test")
    monkeypatch.setattr(media_preview_module.subprocess, "run", fake_run)

    response = TestClient(api_module.create_app(db_path)).get(
        f"/media/{identity.track_id}"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFFbrowser-compatible-wav"
    assert source.read_bytes() == source_bytes
    assert calls[0][0] == "ffmpeg-test"
    assert calls[0][2].casefold() == str(source).casefold()
    assert Path(calls[0][-1]) != source
    assert not Path(calls[0][-1]).exists()


def test_media_endpoint_reports_transcode_failure_without_traceback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    identity = _add_track(
        LibraryDatabase(db_path),
        tmp_path / "broken.aiff",
        artist="Artist",
        title="Broken",
    )

    def fail_run(
        command: list[str],
        *,
        stderr: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.CalledProcessError(
            1,
            command,
            stderr=b"Invalid data found when processing input",
        )

    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg-test")
    monkeypatch.setattr(media_preview_module.subprocess, "run", fail_run)

    response = TestClient(
        api_module.create_app(db_path),
        raise_server_exceptions=False,
    ).get(f"/media/{identity.track_id}")

    assert response.status_code == 422
    assert "Audio preview failed" in response.json()["detail"]
    assert "Invalid data found when processing input" in response.json()["detail"]
    assert "Traceback" not in response.text
