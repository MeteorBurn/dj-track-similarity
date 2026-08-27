from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dj_track_similarity import api as api_module
from dj_track_similarity.audio_dedup_bridge import load_audio_dedup_core
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.track_models import FileTags, ScannedFile, TrackIdentity


def _client(monkeypatch, db_path: Path, out_dir: Path) -> TestClient:
    monkeypatch.setattr(api_module, "configure_shared_ffmpeg_runtime", lambda: db_path.parent)
    core = load_audio_dedup_core()
    out_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core, "DEFAULT_OUT_DIR", out_dir)
    return TestClient(api_module.create_app(db_path))


def _add_track(database: LibraryDatabase, path: Path, *, title: str) -> TrackIdentity:
    path.write_bytes(b"audio payload")
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
        tags=FileTags(title=title, artist="Dedup Fixture", album="Dedup"),
    ).identity


def _track_entry(identity: TrackIdentity, path: Path) -> dict:
    stat = path.stat()
    return {
        "track_id": identity.track_id,
        "catalog_uuid": identity.catalog_uuid,
        "track_uuid": identity.track_uuid,
        "path": str(path),
        "artist": "Dedup Fixture",
        "title": path.stem,
        "album": "Dedup",
        "duration": 1.0,
        "bpm": None,
        "musical_key": None,
        "size": stat.st_size,
        "mtime": stat.st_mtime,
        "file_modified_ns": stat.st_mtime_ns,
        "format_rank": 60,
        "size_per_second": float(stat.st_size),
        "metadata_completeness": 3,
        "embeddings": [],
        "spectral_cutoff_hz": 22050.0,
        "spectral_sharpness_db": None,
        "suspected_transcode": False,
        "spectral_note": "full band",
    }


def _write_report(
    out_dir: Path,
    *,
    database: LibraryDatabase,
    root: Path,
    keeper: tuple[TrackIdentity, Path],
    duplicate: tuple[TrackIdentity, Path],
) -> str:
    keeper_entry = _track_entry(keeper[0], keeper[1])
    duplicate_entry = _track_entry(duplicate[0], duplicate[1])
    candidate = {
        **duplicate_entry,
        "role": "DUPLICATE",
        "decision": "review",
        "action": "REVIEW MANUALLY",
        "score_vs_keeper": 1.0,
        "content_similarity_vs_keeper": None,
        "safe_to_delete": "false",
        "blocked_reasons": ["SONARA fingerprint-only candidate requires manual review"],
        "why_delete_or_review": ["Manual review required: fingerprint-only candidate."],
    }
    payload = {
        "mode": "report-only",
        "generated_at": "2026-08-27T12:00:00",
        "database_path": str(database.path),
        "root": str(root),
        "path_contains": [],
        "sources": [],
        "weights": {},
        "preset": "safe",
        "min_score": 0.965,
        "min_similarity": 0.985,
        "search_mode": "fingerprint",
        "database_track_count": 2,
        "scoped_track_count": 2,
        "track_count": 2,
        "group_count": 1,
        "statistics": {
            "candidate_count": 1,
            "duplicate_track_count": 1,
            "safe_candidate_count": 0,
            "review_candidate_count": 1,
            "fake_bitrate_candidate_count": 0,
            "fake_bitrate_group_count": 0,
        },
        "groups": [
            {
                "group_id": 1,
                "score": 1.0,
                "confidence": "high",
                "preset": "safe",
                "blocked_reasons": ["missing content similarity"],
                "suggested_keeper": {
                    **keeper_entry,
                    "role": "KEEP",
                    "decision": "keep",
                    "keeper_reasons": {},
                    "why_keep": ["Highest keeper ranking inside this duplicate group."],
                },
                "candidate_deletes": [candidate],
                "tracks": [
                    {**keeper_entry, "role": "KEEP", "decision": None},
                    {**duplicate_entry, "role": "DUPLICATE", "decision": None},
                ],
                "pairwise_evidence": [
                    {
                        "left_track_id": keeper[0].track_id,
                        "right_track_id": duplicate[0].track_id,
                        "score": 1.0,
                        "content_similarity": None,
                        "mert_similarity": None,
                        "maest_similarity": None,
                        "muq_similarity": None,
                        "clap_similarity": None,
                        "sonara_similarity": 1.0,
                        "fingerprint_similarity": 1.0,
                        "candidate_sources": ["fingerprint_lsh"],
                        "duration_diff_seconds": 0.0,
                        "duration_diff_ratio": 0.0,
                        "blocked_reasons": ["missing content similarity"],
                    }
                ],
            }
        ],
    }
    report_id = "audio_dedup_report_20260827_120000"
    (out_dir / f"{report_id}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report_id


def _fixture(tmp_path: Path):
    db_path = tmp_path / "library.sqlite"
    audio_dir = tmp_path / "Music"
    audio_dir.mkdir()
    out_dir = tmp_path / "reports"
    out_dir.mkdir()
    database = LibraryDatabase(db_path)
    keeper_path = audio_dir / "keeper.flac"
    duplicate_path = audio_dir / "duplicate.flac"
    keeper = _add_track(database, keeper_path, title="keeper")
    duplicate = _add_track(database, duplicate_path, title="duplicate")
    report_id = _write_report(
        out_dir,
        database=database,
        root=audio_dir,
        keeper=(keeper, keeper_path),
        duplicate=(duplicate, duplicate_path),
    )
    return db_path, out_dir, audio_dir, keeper, duplicate, keeper_path, duplicate_path, report_id


def test_audio_dedup_report_groups_expose_evidence_and_live_staleness(tmp_path, monkeypatch) -> None:
    db_path, out_dir, _, keeper, duplicate, _, duplicate_path, report_id = _fixture(tmp_path)
    client = _client(monkeypatch, db_path, out_dir)

    listing = client.get("/api/audio-dedup/reports")
    assert listing.status_code == 200
    assert [item["report_id"] for item in listing.json()] == [report_id]
    assert listing.json()[0]["review_candidate_count"] == 1

    page = client.get(f"/api/audio-dedup/reports/{report_id}/groups")
    assert page.status_code == 200
    body = page.json()
    assert body["total_groups"] == 1
    assert body["search_mode"] == "fingerprint"
    group = body["groups"][0]
    assert group["fingerprint_similarity"] == 1.0
    files = {item["track_id"]: item for item in group["files"]}
    assert files[keeper.track_id]["role"] == "keeper"
    assert files[duplicate.track_id]["role"] == "duplicate"
    assert files[duplicate.track_id]["safe_to_delete"] is False
    assert files[duplicate.track_id]["stale"] is False
    assert files[duplicate.track_id]["playable"] is True

    duplicate_path.unlink()
    stale_page = client.get(f"/api/audio-dedup/reports/{report_id}/groups")
    stale_files = {item["track_id"]: item for item in stale_page.json()["groups"][0]["files"]}
    assert stale_files[duplicate.track_id]["stale"] is True
    assert stale_files[duplicate.track_id]["playable"] is False


def test_audio_dedup_delete_requires_the_confirmation_phrase(tmp_path, monkeypatch) -> None:
    db_path, out_dir, _, _, duplicate, _, duplicate_path, report_id = _fixture(tmp_path)
    client = _client(monkeypatch, db_path, out_dir)

    response = client.post(
        f"/api/audio-dedup/reports/{report_id}/delete",
        json={
            "selections": [{"group_id": 1, "track_ids": [duplicate.track_id]}],
            "deletion_mode": "permanent",
            "confirmation": "delete",
        },
    )

    assert response.status_code == 400
    assert "APPLY DELETE" in response.json()["detail"]
    assert duplicate_path.exists()


def test_audio_dedup_delete_rejects_a_track_outside_its_group(tmp_path, monkeypatch) -> None:
    db_path, out_dir, _, _, _, keeper_path, duplicate_path, report_id = _fixture(tmp_path)
    client = _client(monkeypatch, db_path, out_dir)

    response = client.post(
        f"/api/audio-dedup/reports/{report_id}/delete",
        json={
            "selections": [{"group_id": 1, "track_ids": [9999]}],
            "deletion_mode": "permanent",
            "confirmation": "APPLY DELETE",
        },
    )

    assert response.status_code == 400
    assert keeper_path.exists()
    assert duplicate_path.exists()


def test_audio_dedup_delete_removes_the_confirmed_selection(tmp_path, monkeypatch) -> None:
    db_path, out_dir, _, _, duplicate, keeper_path, duplicate_path, report_id = _fixture(tmp_path)
    client = _client(monkeypatch, db_path, out_dir)

    response = client.post(
        f"/api/audio-dedup/reports/{report_id}/delete",
        json={
            "selections": [{"group_id": 1, "track_ids": [duplicate.track_id]}],
            "deletion_mode": "permanent",
            "confirmation": "APPLY DELETE",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["deleted_track_ids"] == [duplicate.track_id]
    assert body["failed"] == []
    assert not duplicate_path.exists()
    assert keeper_path.exists()


def test_audio_dedup_scan_rejects_sources_without_embedding_mode(tmp_path, monkeypatch) -> None:
    db_path, out_dir, audio_dir, *_ = _fixture(tmp_path)
    client = _client(monkeypatch, db_path, out_dir)

    response = client.post(
        "/api/audio-dedup/jobs",
        json={"root": str(audio_dir), "search_mode": "fingerprint", "sources": ["mert"]},
    )

    assert response.status_code == 400
