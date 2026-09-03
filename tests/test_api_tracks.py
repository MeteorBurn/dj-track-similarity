from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.testclient import TestClient

from dj_track_similarity import api as api_module
from dj_track_similarity import media_preview as media_preview_module
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.library_models import (
    AnalysisCoverage,
    ClassifierScoreDetail,
    EmbeddingSummary,
    FileTechnical,
    TrackDetail,
)
from dj_track_similarity.track_models import FileTags, ScannedFile, TrackIdentity


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api_module, "configure_shared_ffmpeg_runtime", lambda: db_path.parent)
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
        "liked": liked,
    }


def test_tracks_endpoint_returns_paginated_typed_current_summaries(
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
    assert all("metadata" not in item and "id" not in item for item in payload["items"])


def test_tracks_endpoints_return_empty_current_contract(
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
    # MAEST genres are searchable; the file-tag genre every fixture carries
    # ("House") is not, so a query for it may only match the title above.
    genre = _add_track(
        database,
        tmp_path / "genre.wav",
        artist="DJ Three",
        title="Untitled",
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO maest_genres(track_id, syncopated_rhythm, genres_json, analyzed_at)"
            " VALUES (?, 0, ?, '2026-09-02T00:00:00Z')",
            (
                genre.track_id,
                json.dumps(
                    [{"label": "Electronic---Drum_n_Bass", "score": 0.41}],
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            ),
        )
        connection.commit()
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
    like_genre = client.get("/api/tracks", params={"q": "drum n bass"}).json()
    fts_genre = client.get(
        "/api/tracks",
        params={"q": "drum n bass", "search_mode": "fts"},
    ).json()
    like_file_genre = client.get("/api/tracks", params={"q": "House"}).json()

    assert [item["track_id"] for item in like_payload["items"]] == [
        substring.track_id
    ]
    assert fts_substring["total"] == 0
    assert [item["track_id"] for item in fts_token["items"]] == [token.track_id]
    assert invalid.status_code == 422
    assert [item["track_id"] for item in like_genre["items"]] == [genre.track_id]
    assert [item["track_id"] for item in fts_genre["items"]] == [genre.track_id]
    assert [item["track_id"] for item in like_file_genre["items"]] == [
        token.track_id
    ]


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
            "track_uuid": "stale-track-uuid",
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


def _seed_evaluation_rows(database: LibraryDatabase, identity: TrackIdentity) -> None:
    connection = database.connect_evaluation(create=True)
    assert connection is not None
    with connection:
        connection.execute(
            """
            INSERT INTO search_sessions(session_id, mode, request_json, created_at)
            VALUES (1, 'seed', '{}', '2026-08-27T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO search_session_seeds(session_id, position, track_id, track_uuid)
            VALUES (1, 0, ?, ?)
            """,
            (identity.track_id, identity.track_uuid),
        )
        connection.execute(
            """
            INSERT INTO search_result_events(
                session_id, rank, track_id, track_uuid,
                total_score, score_breakdown_json, created_at
            )
            VALUES (1, 0, ?, ?, 0.9, '{}', '2026-08-27T00:00:00Z')
            """,
            (identity.track_id, identity.track_uuid),
        )
    connection.close()


def _evaluation_track_row_count(database: LibraryDatabase) -> int:
    connection = database.connect_evaluation(create=False)
    assert connection is not None
    try:
        return sum(
            int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("search_session_seeds", "search_result_events")
        )
    finally:
        connection.close()


def test_delete_track_removes_catalog_data_but_keeps_source_audio(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    database = LibraryDatabase(db_path)
    audio_path = tmp_path / "delete-me.wav"
    identity = _add_track(
        database,
        audio_path,
        artist="DJ",
        title="Delete Me",
    )
    database.set_track_liked(expected=identity, liked=True)
    _seed_evaluation_rows(database, identity)
    client = _client(monkeypatch, db_path)

    response = client.request(
        "DELETE",
        f"/api/tracks/{identity.track_id}",
        json={
            "catalog_uuid": identity.catalog_uuid,
            "track_uuid": identity.track_uuid,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"track_id": identity.track_id}
    assert client.get("/api/tracks").json()["items"] == []
    assert client.get(
        "/api/tracks",
        params={"q": "Delete Me", "search_mode": "fts"},
    ).json()["items"] == []
    assert audio_path.read_bytes() == b"audio"
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM likes").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM track_search_fts").fetchone()[0] == 0
    # The Evaluation sidecar is a separate file, so no cascade reaches it and a
    # deleted track would otherwise keep naming itself there.
    assert _evaluation_track_row_count(database) == 0


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
    assert payload["file_tags"]["comment"] == "stored comment"
    assert "audio_codec" not in payload["file"]
    assert payload["file"]["bit_depth"] is None
    assert "catalog_number" not in payload["file_tags"]
    assert "isrc" not in payload["file_tags"]
    assert "disc_number" not in payload["file_tags"]
    assert payload["file"]["file_size_bytes"] == 5


def test_track_detail_endpoint_exposes_structural_analysis_metadata_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    identity = _add_track(
        LibraryDatabase(db_path),
        tmp_path / "alpha.wav",
        artist="Artist",
        title="Alpha",
    )

    def enriched_detail(
        database: LibraryDatabase,
        track_id: int,
    ):
        del database
        assert track_id == identity.track_id
        return TrackDetail(
            track_id=identity.track_id,
            catalog_uuid=identity.catalog_uuid,
            track_uuid=identity.track_uuid,
            file_path=str(tmp_path / "alpha.wav"),
            title="Alpha",
            artist="Artist",
            album=None,
            tag_bpm=None,
            tag_key=None,
            audio_duration_seconds=1.0,
            liked=False,
            analysis_coverage=AnalysisCoverage(),
            classifier_scores=(),
            file=FileTechnical(
                file_size_bytes=5,
                file_modified_ns=1,
                audio_format="wav",
                sample_rate_hz=44_100,
                channel_count=2,
                bit_rate_bps=1_411_200,
                bit_depth=16,
                audio_duration_seconds=1.0,
                last_scanned_at="2026-07-30T00:00:00Z",
                missing_since=None,
            ),
            file_tags=None,
            sonara_core=None,
            maest=None,
            embeddings=(
                EmbeddingSummary(
                    analysis_family="mert",
                    dim=768,
                    normalization="l2",
                    analyzed_at="2026-07-30T00:00:00Z",
                ),
            ),
            classifier_scores_detail=(
                ClassifierScoreDetail(
                    classifier_key="voice_presence",
                    score=0.75,
                    predicted_class="present",
                    score_bucket="high",
                    confidence=0.8,
                    probabilities={"absent": 0.25, "present": 0.75},
                    feature_set="mert",
                    feature_names=("mert:0",),
                    positive_label="present",
                    analyzed_at="2026-07-30T00:00:00Z",
                ),
            ),
        )

    monkeypatch.setattr(LibraryDatabase, "get_track_detail", enriched_detail)
    monkeypatch.setattr(api_module, "configure_shared_ffmpeg_runtime", lambda: None)
    response = TestClient(
        api_module.create_app(db_path),
        raise_server_exceptions=False,
    ).get(f"/api/tracks/{identity.track_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["embeddings"] == [
        {
            "analysis_family": "mert",
            "dim": 768,
            "normalization": "l2",
            "analyzed_at": "2026-07-30T00:00:00Z",
        }
    ]
    assert payload["classifier_scores_detail"] == [
        {
            "classifier_key": "voice_presence",
            "score": 0.75,
            "predicted_class": "present",
            "score_bucket": "high",
            "confidence": 0.8,
            "probabilities": {"absent": 0.25, "present": 0.75},
            "feature_set": "mert",
            "feature_names": ["mert:0"],
            "positive_label": "present",
            "analyzed_at": "2026-07-30T00:00:00Z",
        }
    ]


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


def test_reveal_track_location_uses_saved_track_path(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    source = tmp_path / "reveal.wav"
    identity = _add_track(
        LibraryDatabase(db_path),
        source,
        artist="Artist",
        title="Reveal",
    )
    revealed: list[Path] = []
    monkeypatch.setattr(
        api_module,
        "reveal_track_file",
        lambda path: revealed.append(path),
        raising=False,
    )

    response = _client(monkeypatch, db_path).post(
        f"/api/tracks/{identity.track_id}/reveal"
    )

    assert response.status_code == 200
    assert response.json() == {"path": str(source)}
    assert revealed == [source]


def test_reveal_track_file_uses_explorer_select_without_shell(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "Artist - Track.wav"
    calls: list[tuple[str, bool]] = []

    def fake_popen(command: str, *, shell: bool) -> None:
        calls.append((command, shell))

    monkeypatch.setattr(api_module.subprocess, "Popen", fake_popen)

    api_module.reveal_track_file(source)

    assert calls == [(f'explorer.exe /select,"{source}"', False)]


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
    calls: list[Path] = []
    preview = tmp_path / "preview.wav"
    preview.write_bytes(b"RIFFbrowser-compatible-wav")

    def fake_transcode(path: Path) -> FileResponse:
        calls.append(path)
        return FileResponse(preview, media_type="audio/wav")

    monkeypatch.setattr(api_module, "configure_shared_ffmpeg_runtime", lambda: tmp_path)
    monkeypatch.setattr(
        "dj_track_similarity.api_routes_library.transcoded_wav_file_response",
        fake_transcode,
    )

    response = TestClient(api_module.create_app(db_path)).get(
        f"/media/{identity.track_id}"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert response.content == b"RIFFbrowser-compatible-wav"
    assert source.read_bytes() == source_bytes
    assert calls == [source]


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

    def fail_transcode(_path: Path) -> FileResponse:
        raise media_preview_module.AudioPreviewError("Audio preview failed: Invalid data found when processing input")

    monkeypatch.setattr(api_module, "configure_shared_ffmpeg_runtime", lambda: tmp_path)
    monkeypatch.setattr(
        "dj_track_similarity.api_routes_library.transcoded_wav_file_response",
        fail_transcode,
    )

    response = TestClient(
        api_module.create_app(db_path),
        raise_server_exceptions=False,
    ).get(f"/media/{identity.track_id}")

    assert response.status_code == 422
    assert "Audio preview failed" in response.json()["detail"]
    assert "Invalid data found when processing input" in response.json()["detail"]
    assert "Traceback" not in response.text
