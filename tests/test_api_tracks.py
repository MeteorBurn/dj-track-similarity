from __future__ import annotations

import json
import sqlite3
import struct
import wave
from contextlib import closing
from dataclasses import fields
from pathlib import Path

import av
import numpy as np
import pytest
from fastapi.testclient import TestClient

from dj_track_similarity.api import application as api_module
from dj_track_similarity.api import media_preview as media_preview_module
from dj_track_similarity.analysis_models import (
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    MaestGenreScore,
    MaestWrite,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.ddl import SonaraRow
from sonara_test_support import complete_sonara_write, save_sonara_writes
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


def test_embedding_layers_returns_current_stored_row_counts(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "layers.sqlite"
    database = LibraryDatabase(db_path)
    identities = []
    for index in range(7):
        identity = _add_track(database, tmp_path / f"layer-{index}.wav", artist="Layers", title=str(index))
        identities.append(identity)
        vector = np.zeros(1024, dtype=np.float32)
        vector[index % 2] = 1.0
        layer_vector = np.zeros(1024, dtype=np.float32)
        layer_vector[2] = 1.0
        saved = database.save_embedding_results((EmbeddingWrite(
            target=AnalysisTarget(identity.catalog_uuid, identity.track_id, identity.track_uuid),
            output=EmbeddingOutput(family="mert_v2", vector=vector, analyzed_at="2026-09-14T00:00:00Z",
                                   layer_vectors=tuple(layer_vector if layer == 12 else vector for layer in range(1, 25))),
        ),))
        assert saved[0].ok
    database.mark_missing(identities[4].track_id)
    with closing(database.connect()) as connection, connection:
        # A stale identity on the default-layer row withdraws the whole track.
        connection.execute("UPDATE mert_v2_embeddings SET track_uuid = 'stale' WHERE track_id = ? AND layer = 24", (identities[5].track_id,))
        # Counts are row presence: a stored vector is not decoded again.
        connection.execute("UPDATE mert_v2_embeddings SET embedding_blob = ? WHERE track_id = ? AND layer = 24", (np.full(1024, np.nan, dtype=np.float32).tobytes(), identities[6].track_id))
        connection.execute("DELETE FROM mert_v2_embeddings WHERE track_id = ? AND layer = 12", (identities[6].track_id,))

    with _client(monkeypatch, db_path) as client:
        response = client.get("/api/library/embedding-layers/mert_v2")
        assert response.status_code == 200
        payload = response.json()
        assert (payload["catalog_uuid"], payload["family"], payload["default_layer"]) == (database.catalog_uuid, "mert_v2", 24)
        assert set(payload) == {"catalog_uuid", "family", "default_layer", "note", "layers"}
        assert [(row["layer"], row["track_count"]) for row in payload["layers"]] == [
            (layer, 4 if layer == 12 else 5) for layer in range(1, 25)
        ]
        assert all(set(row) == {"layer", "track_count", "label", "source"} for row in payload["layers"])
        assert client.get("/api/library/embedding-layers/clap").status_code == 404


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
    with closing(database.connect()) as connection, connection:
        connection.execute(
            "UPDATE tracks SET bit_depth = 24 WHERE track_id = ?",
            (beta.track_id,),
        )
        connection.execute(
            "UPDATE tracks SET audio_format = NULL, sample_rate_hz = NULL, bit_rate_bps = NULL WHERE track_id = ?",
            (gamma.track_id,),
        )
    sonara_values = {field.name: None for field in fields(SonaraRow)}
    sonara_values.update(
        track_id=beta.track_id,
        detected_bpm=130.25,
        detected_key_name="E minor",
        detected_key_camelot="9A",
        mfcc_mean_blob=bytes(13 * 4),
        chroma_mean_blob=bytes(12 * 4),
        spectral_contrast_mean_blob=bytes(7 * 4),
        analysis_schema_version=6,
        analyzed_at="2026-09-14T00:00:00Z",
    )
    saved = save_sonara_writes(database, (
        complete_sonara_write(
            AnalysisTarget(beta.catalog_uuid, beta.track_id, beta.track_uuid),
            SonaraRow(**sonara_values),
        ),
    ))
    assert saved[0].ok, saved[0].error
    maest_saved = database.save_maest_results((
        MaestWrite(
            target=AnalysisTarget(beta.catalog_uuid, beta.track_id, beta.track_uuid),
            genres=(
                MaestGenreScore("Electronic---Breakbeat", 0.8),
                MaestGenreScore("Electronic---House", 0.4),
            ),
            syncopated_rhythm=True,
            analyzed_at="2026-09-14T00:00:00Z",
        ),
    ))
    assert maest_saved[0].ok, maest_saved[0].error
    client = _client(monkeypatch, db_path)

    response = client.get(
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
    assert [
        (
            item["file_size_bytes"], item["audio_format"], item["sample_rate_hz"],
            item["bit_rate_bps"], item["bit_depth"],
        )
        for item in payload["items"]
    ] == [(5, "wav", 44_100, 1_411_200, 24), (5, None, None, None, None)]
    assert [
        (item["sonara_bpm"], item["sonara_key_camelot"])
        for item in payload["items"]
    ] == [(130.25, "9A"), (None, None)]
    assert [item["maest_genres"] for item in payload["items"]] == [
        [
            {"rank": 1, "genre_name": "Electronic---Breakbeat", "score": 0.8},
            {"rank": 2, "genre_name": "Electronic---House", "score": 0.4},
        ],
        [],
    ]
    assert all(
        (item["tag_bpm"], item["tag_key"]) == (128.0, "8A")
        for item in payload["items"]
    )
    filtered = client.post("/api/tracks/filtered", json={"query": "Beta"})
    assert filtered.status_code == 200
    assert filtered.json() == [payload["items"][0]]

    with closing(database.connect()) as connection, connection:
        connection.execute(
            "UPDATE sonara_features SET key_candidates_json = '[{}]' WHERE track_id = ?",
            (beta.track_id,),
        )
        connection.execute(
            "UPDATE maest_genres SET genres_json = '[{}]' WHERE track_id = ?",
            (beta.track_id,),
        )
    invalid = client.get("/api/tracks", params={"q": "Beta"})
    assert invalid.status_code == 200
    invalid_item = invalid.json()["items"][0]
    assert invalid_item["sonara_bpm"] is None
    assert invalid_item["sonara_key_camelot"] is None
    assert invalid_item["maest_genres"] == []
    assert (invalid_item["tag_bpm"], invalid_item["tag_key"]) == (128.0, "8A")


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
    padded = client.post(
        url,
        json={
            **_liked_payload(identity, True),
            "track_uuid": f" {identity.track_uuid} ",
        },
    )
    liked = client.post(url, json=_liked_payload(identity, True))
    liked_page = client.get("/api/tracks", params={"liked": "true"})
    unliked = client.post(url, json=_liked_payload(identity, False))

    assert stale.status_code == 409
    assert padded.status_code == 422
    assert liked.status_code == 200
    assert liked.json()["liked"] is True
    assert liked.json()["track_uuid"] == identity.track_uuid
    assert [
        item["track_id"] for item in liked_page.json()["items"]
    ] == [identity.track_id]
    assert unliked.status_code == 200
    assert unliked.json()["liked"] is False
    with pytest.raises(ValueError, match="track_uuid must not contain surrounding whitespace"):
        TrackIdentity(identity.catalog_uuid, identity.track_id, f" {identity.track_uuid} ")


def _seed_evaluation_rows(database: LibraryDatabase, identity: TrackIdentity) -> None:
    # Session 1 is seeded by the track; in session 2 it is only a candidate.
    deleted = (identity.track_id, identity.track_uuid)
    other_seed = (identity.track_id + 1, "other-seed-uuid")
    candidate = (identity.track_id + 2, "candidate-uuid")
    connection = database.connect_evaluation(create=True)
    assert connection is not None
    with connection:
        connection.executemany(
            """
            INSERT INTO search_sessions(session_id, mode, request_json, created_at)
            VALUES (?, 'seed', ?, '2026-08-27T00:00:00Z')
            """,
            [
                (
                    session_id,
                    json.dumps(
                        {
                            "seed_identities": [
                                {
                                    "catalog_uuid": identity.catalog_uuid,
                                    "track_id": seed[0],
                                    "track_uuid": seed[1],
                                }
                            ]
                        }
                    ),
                )
                for session_id, seed in ((1, deleted), (2, other_seed))
            ],
        )
        connection.executemany(
            """
            INSERT INTO search_session_seeds(session_id, position, track_id, track_uuid)
            VALUES (?, 0, ?, ?)
            """,
            [(1, *deleted), (2, *other_seed)],
        )
        connection.executemany(
            """
            INSERT INTO search_result_events(
                session_id, rank, track_id, track_uuid,
                total_score, score_breakdown_json, created_at
            )
            VALUES (?, ?, ?, ?, 0.9, '{}', '2026-08-27T00:00:00Z')
            """,
            [(1, 0, *candidate), (2, 0, *deleted), (2, 1, *candidate)],
        )
    connection.close()


def _evaluation_rows(database: LibraryDatabase) -> dict[str, list[tuple[int, ...]]]:
    connection = database.connect_evaluation(create=False)
    assert connection is not None
    try:
        return {
            table: [
                tuple(row)
                for row in connection.execute(f"SELECT {columns} FROM {table} ORDER BY {columns}")
            ]
            for table, columns in (
                ("search_sessions", "session_id"),
                ("search_session_seeds", "session_id, track_id"),
                ("search_result_events", "session_id, track_id"),
            )
        }
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
    # deleted track would otherwise keep naming itself there. The session it
    # seeded goes whole; the one it was only a candidate in keeps the rest.
    assert _evaluation_rows(database) == {
        "search_sessions": [(2,)],
        "search_session_seeds": [(2, identity.track_id + 1)],
        "search_result_events": [(2, identity.track_id + 2)],
    }


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
    assert payload["sonara_bpm"] is None
    assert payload["sonara_key_camelot"] is None
    assert payload["maest_genres"] == []
    assert "audio_codec" not in payload["file"]
    assert payload["file"]["bit_depth"] is None
    assert "catalog_number" not in payload["file_tags"]
    assert "isrc" not in payload["file_tags"]
    assert "disc_number" not in payload["file_tags"]
    assert payload["file"]["file_size_bytes"] == 5
    for field in ("file_size_bytes", "audio_format", "sample_rate_hz", "bit_rate_bps", "bit_depth"):
        assert payload[field] == payload["file"][field]


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
            file_size_bytes=5,
            audio_format="wav",
            sample_rate_hz=44_100,
            bit_rate_bps=1_411_200,
            bit_depth=16,
            title="Alpha",
            artist="Artist",
            album=None,
            tag_bpm=None,
            tag_key=None,
            sonara_bpm=None,
            sonara_key_camelot=None,
            maest_genres=(),
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
                    analysis_family="muq",
                    dim=1024,
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
                    feature_set="muq",
                    feature_names=("muq:0",),
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
            "analysis_family": "muq",
            "dim": 1024,
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
            "feature_set": "muq",
            "feature_names": ["muq:0"],
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


def test_media_endpoint_streams_audio_with_binary_metadata_without_modifying_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    source = tmp_path / "preview.wav"
    identity = _add_track(
        LibraryDatabase(db_path),
        source,
        artist="Artist",
        title="Preview",
    )
    pcm = struct.pack("<hh", 1000, -1000) * 22_050
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(44_100)
        audio.writeframes(pcm)
    metadata = b"INFO" + struct.pack("<4sI", b"NITR", 8) + b"NTKB\xa7\xaa\x00\x00"
    wave_bytes = bytearray(source.read_bytes() + struct.pack("<4sI", b"LIST", len(metadata)) + metadata)
    struct.pack_into("<I", wave_bytes, 4, len(wave_bytes) - 8)
    source.write_bytes(wave_bytes)
    source_bytes = source.read_bytes()
    monkeypatch.setattr(media_preview_module, "load_project_pyav", lambda: av)
    client = _client(monkeypatch, db_path)
    info_url = f"/api/tracks/{identity.track_id}/preview-info"
    assert client.get(info_url).json() == {"duration_seconds": 0.5}
    response = client.get(f"/media/{identity.track_id}?start=0.125", headers={"Range": "bytes=0-"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/wav")
    assert "content-length" not in response.headers
    assert "accept-ranges" not in response.headers
    assert response.content[:4] == b"RIFF"
    assert response.content[44:] == pcm[round(0.125 * 44_100) * 4:]
    assert source.read_bytes() == source_bytes
    for start in (0.5, 1.0):
        beyond_end = client.get(f"/media/{identity.track_id}?start={start}")
        assert beyond_end.status_code == 422
        assert "end of the audio" in beyond_end.json()["detail"]
    monkeypatch.setattr("dj_track_similarity.api.routes_library.preview_duration_seconds", lambda _path: None)
    assert client.get(info_url).json() == {"duration_seconds": None}


def test_media_endpoint_rejects_undecodable_audio_and_invalid_start_without_traceback(
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

    monkeypatch.setattr(media_preview_module, "load_project_pyav", lambda: av)
    client = _client(monkeypatch, db_path)
    response = client.get(f"/media/{identity.track_id}")

    assert response.status_code == 422
    assert "Audio preview failed" in response.json()["detail"]
    assert "Traceback" not in response.text
    assert client.get(f"/api/tracks/{identity.track_id}/preview-info").status_code == 422
    for invalid_start in ("-1", "nan", "inf", "-inf"):
        rejected = client.get(f"/media/{identity.track_id}?start={invalid_start}")
        assert rejected.status_code == 422
        assert rejected.json()["detail"][0]["loc"] == ["query", "start"]
