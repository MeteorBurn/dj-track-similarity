from __future__ import annotations

from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api_test_support import create_api_client
import dj_track_similarity.api.application as api
from dj_track_similarity.analysis.jobs import AnalysisJobManager
from dj_track_similarity.analysis.pipeline import AnalysisPipelineManager
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.analysis.sonara_runtime import (
    DEFAULT_SONARA_BPM_MAX,
    DEFAULT_SONARA_BPM_MIN,
)


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    return create_api_client(monkeypatch, tmp_path / "library.sqlite")


def _analysis_start(calls: list[dict[str, object]]):
    def start(_manager: AnalysisJobManager, **kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return {
            "job_id": "analysis-job",
            "state": "queued",
            **kwargs,
        }

    return start


def test_api_lists_classifier_manifests_with_direct_score_counts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    classifiers = [
        {
            "classifier_key": "voice_presence",
            "name": "Voice Presence",
            "is_scoring_compatible": True,
        }
    ]
    monkeypatch.setattr(api, "promoted_classifiers", lambda: classifiers)

    def score_counts(
        _database: LibraryDatabase,
        classifier_keys: tuple[str, ...],
    ) -> dict[str, int]:
        assert classifier_keys == ("voice_presence",)
        return {"voice_presence": 1}

    monkeypatch.setattr(LibraryDatabase, "classifier_score_counts", score_counts)

    response = _client(monkeypatch, tmp_path).get("/api/classifiers")

    assert response.status_code == 200
    assert response.json() == [{**classifiers[0], "scored_tracks": 1}]


def test_api_starts_selected_ml_job_without_classifier_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(AnalysisJobManager, "start", _analysis_start(calls))
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/jobs",
        json={
            "models": ["maest", "muq", "mert_v2"],
            "limit": 0,
            "device": "cpu",
            "top_k": 4,
            "track_batch_size": 5,
            "inference_batch_size": 18,
        },
    )

    assert response.status_code == 200
    assert response.json()["models"] == ["maest", "mert_v2", "muq"]
    assert "classifier_keys" not in response.json()
    assert calls == [
        {
            "models": ["maest", "mert_v2", "muq"],
            "limit": 0,
            "track_batch_size": 5,
            "inference_batch_size": 18,
            "sonara_batch_size": 8,
            "sonara_bpm_min": None,
            "sonara_bpm_max": None,
            "device": "cpu",
            "top_k": 4,
        }
    ]


def test_api_rejects_classifier_scoring_inside_audio_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/jobs",
        json={"models": ["muq"], "classifier_keys": ["voice_presence"]},
    )

    assert response.status_code == 422


def test_api_sonara_job_uses_default_outputs_and_keeps_native_batch_size(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(AnalysisJobManager, "start", _analysis_start(calls))
    client = _client(monkeypatch, tmp_path)

    defaulted = client.post(
        "/api/analysis/jobs",
        json={"models": ["sonara"], "limit": 0},
    )
    obsolete = client.post(
        "/api/analysis/jobs",
        json={
            "models": ["sonara"],
            "limit": 0,
            "sonara_outputs": ["fingerprint"],
            "sonara_batch_size": 12,
        },
    )

    assert defaulted.status_code == 200
    assert "sonara_outputs" not in defaulted.json()
    assert defaulted.json()["sonara_batch_size"] == 8
    assert obsolete.status_code == 422
    assert len(calls) == 1
    assert "sonara_outputs" not in calls[0]


def test_api_pipeline_starts_ml_with_direct_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: list[dict[str, object]] = []

    def start(
        _manager: AnalysisPipelineManager,
        **kwargs: object,
    ) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {"job_id": "pipeline-job", "state": "queued"}

    monkeypatch.setattr(AnalysisPipelineManager, "start", start)
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stage": "ml",
            "limit": 0,
            "ml": {
                "models": ["muq"],
                "device": "cpu",
                "top_k": 3,
                "track_batch_size": 2,
                "inference_batch_size": 4,
            },
        },
    )

    assert response.status_code == 200
    assert captured == [
        {
            "stage": "ml",
            "limit": 0,
            "sonara": {},
            "ml": {
                "models": ["muq"],
                "device": "cpu",
                "top_k": 3,
                "track_batch_size": 2,
                "inference_batch_size": 4,
                "mode": "direct",
                "ml_staging_config": None,
            },
        }
    ]


def test_api_pipeline_builds_staged_ml_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: list[dict[str, object]] = []
    staging_root = tmp_path / "ml-staging"
    staging_root.mkdir()

    def start(_manager: AnalysisPipelineManager, **kwargs: object) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {"job_id": "pipeline-job", "state": "queued"}

    monkeypatch.setattr(AnalysisPipelineManager, "start", start)
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stage": "ml",
            "ml": {
                "models": ["muq"],
                "device": "cpu",
                "top_k": 3,
                "track_batch_size": 2,
                "inference_batch_size": 4,
                "mode": "staged",
                "staged": {
                    "folder": str(staging_root),
                    "copy_workers": 3,
                    "decode_workers": 5,
                    "stage_size": 40,
                    "inference_batch_size": 4,
                },
            },
        },
    )

    assert response.status_code == 200
    settings = captured[0]["ml"]
    assert isinstance(settings, dict)
    assert settings["mode"] == "staged"
    staging = settings["ml_staging_config"]
    assert staging.root == staging_root
    assert staging.copy_workers == 3
    assert staging.decode_workers == 5
    assert staging.stage_size == 40
    assert staging.inference_batch_size == 4


def test_api_pipeline_rejects_unknown_ml_staged_setting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staging_root = tmp_path / "ml-staging"
    staging_root.mkdir()

    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stage": "ml",
            "ml": {
                "models": ["muq"],
                "mode": "staged",
                "staged": {
                    "folder": str(staging_root),
                    "copy_workers": 4,
                    "decode_workers": 4,
                    "stage_size": 64,
                    "inference_batch_size": 16,
                    "unexpected": True,
                },
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "ml", "staged", "unexpected"]
    assert response.json()["detail"][0]["type"] == "extra_forbidden"


def test_api_pipeline_rejects_classifier_stage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: list[dict[str, object]] = []

    def start(_manager: AnalysisPipelineManager, **kwargs: object) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {"job_id": "pipeline-job", "state": "queued"}

    monkeypatch.setattr(AnalysisPipelineManager, "start", start)
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stage": "classifiers",
            "limit": 0,
            "ml": {
                "models": ["muq"],
                "device": "cpu",
                "top_k": 3,
                "track_batch_size": 2,
                "inference_batch_size": 4,
            },
            "classifiers": {"classifier_keys": ["voice_presence"]},
        },
    )

    assert response.status_code == 422
    assert captured == []


def test_api_pipeline_builds_staged_sonara_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: list[dict[str, object]] = []
    staging_root = tmp_path / "staging"
    staging_root.mkdir()

    def start(_manager: AnalysisPipelineManager, **kwargs: object) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {"job_id": "pipeline-job", "state": "queued"}

    monkeypatch.setattr(AnalysisPipelineManager, "start", start)
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stage": "sonara",
            "sonara": {
                "mode": "staged",
                "direct_batch_size": 8,
                "staged": {
                    "folder": str(staging_root),
                    "processes": 4,
                    "threads": 4,
                    "batch_size": 4,
                    "stage_size": 32,
                },
            },
        },
    )

    assert response.status_code == 200
    settings = captured[0]["sonara"]
    assert isinstance(settings, dict)
    assert settings["mode"] == "staged"
    assert settings["batch_size"] == 4
    staging = settings["staging_config"]
    assert staging.root == staging_root
    assert staging.processes == 4
    assert staging.rayon_threads == 4
    assert staging.max_native_batch_size == 4
    assert staging.stage_size == 32


def test_api_pipeline_builds_direct_sonara_settings_without_staging_folder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: list[dict[str, object]] = []

    def start(_manager: AnalysisPipelineManager, **kwargs: object) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {"job_id": "pipeline-job", "state": "queued"}

    monkeypatch.setattr(AnalysisPipelineManager, "start", start)
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stage": "sonara",
            "sonara": {
                "mode": "direct",
                "direct_batch_size": 12,
                "staged": {
                    "folder": "",
                    "processes": 4,
                    "threads": 4,
                    "batch_size": 4,
                    "stage_size": 32,
                },
            },
        },
    )

    assert response.status_code == 200
    settings = captured[0]["sonara"]
    assert isinstance(settings, dict)
    assert settings == {
        "mode": "direct",
        "batch_size": 12,
        "bpm_min": DEFAULT_SONARA_BPM_MIN,
        "bpm_max": DEFAULT_SONARA_BPM_MAX,
        "staging_config": None,
    }


def test_api_pipeline_requires_selected_folder_for_staged_sonara(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stage": "sonara",
            "sonara": {
                "mode": "staged",
                "direct_batch_size": 8,
                "staged": {
                    "folder": "",
                    "processes": 4,
                    "threads": 4,
                    "batch_size": 4,
                    "stage_size": 32,
                },
            },
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Choose a staging folder before starting Staged Mode"


def test_api_reset_uses_current_analysis_family_and_rejects_legacy_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _client(monkeypatch, tmp_path)

    reset = client.post("/api/analysis/reset", json={"analysis_family": "mert_v2"})
    legacy = client.post("/api/analysis/reset", json={"adapter": "muq"})

    assert reset.status_code == 200
    assert reset.json() == {
        "feature_rows_deleted": 0,
        "embedding_rows_deleted": 0,
        "classifier_rows_deleted": 0,
    }
    assert legacy.status_code == 422

    # One SONARA run writes four outputs under one BPM range, so a SONARA
    # reset must not leave Timeline, embedding or fingerprint looking current.
    database = LibraryDatabase(tmp_path / "library.sqlite")
    sonara_tables = ("sonara_features", "sonara_timeline", "sonara_embeddings", "sonara_fingerprints")
    track_uuid = "00000000-0000-0000-0000-000000000009"
    stamp = "2026-09-15T00:00:00Z"
    with closing(database.connect()) as connection, connection:
        track_id = connection.execute(
            "INSERT INTO tracks(track_uuid, file_path, file_size_bytes, file_modified_ns, "
            "last_scanned_at, created_at, updated_at) VALUES (?, ?, 1, 1, ?, ?, ?)",
            (track_uuid, (tmp_path / "track.wav").as_posix(), stamp, stamp, stamp),
        ).lastrowid
        connection.execute(
            "INSERT INTO sonara_features(track_id, mfcc_mean_blob, chroma_mean_blob, "
            "spectral_contrast_mean_blob, analysis_schema_version, analyzed_at) VALUES (?, ?, ?, ?, 6, ?)",
            (track_id, bytes(52), bytes(48), bytes(28), stamp),
        )
        connection.execute(
            "INSERT INTO sonara_timeline VALUES (?, ?, 22050, 512, '{}', ?)",
            (track_id, track_uuid, stamp),
        )
        connection.execute(
            "INSERT INTO sonara_embeddings VALUES (?, ?, 48, 'none', ?, ?)",
            (track_id, track_uuid, bytes(192), stamp),
        )
        connection.execute(
            "INSERT INTO sonara_fingerprints VALUES (?, ?, 1, 'AQAAAA==', ?)",
            (track_id, track_uuid, stamp),
        )

    sonara = client.post("/api/analysis/reset", json={"analysis_family": "sonara"})

    assert sonara.status_code == 200
    assert sonara.json() == {
        "feature_rows_deleted": 3,
        "embedding_rows_deleted": 1,
        "classifier_rows_deleted": 0,
    }
    with closing(database.connect()) as connection:
        assert [
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in sonara_tables
        ] == [0, 0, 0, 0]
