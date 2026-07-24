from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.analysis_pipeline import AnalysisPipelineManager


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(api, "require_ffmpeg", lambda: "ffmpeg")
    return TestClient(api.create_app(tmp_path / "library.sqlite"))


def _analysis_start(calls: list[dict[str, object]]):
    def start(_manager: AnalysisJobManager, **kwargs: object) -> dict[str, object]:
        calls.append(dict(kwargs))
        return {
            "job_id": "analysis-job",
            "state": "queued",
            **kwargs,
        }

    return start


def test_api_starts_selected_ml_job_without_classifier_fields(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(AnalysisJobManager, "start", _analysis_start(calls))
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/jobs",
        json={
            "models": ["maest", "mert"],
            "limit": 0,
            "device": "cpu",
            "top_k": 4,
            "track_batch_size": 5,
            "inference_batch_size": 18,
        },
    )

    assert response.status_code == 200
    assert response.json()["models"] == ["maest", "mert"]
    assert "classifier_keys" not in response.json()
    assert calls == [
        {
            "models": ["maest", "mert"],
            "limit": 0,
            "track_batch_size": 5,
            "inference_batch_size": 18,
            "sonara_batch_size": 8,
            "device": "cpu",
            "top_k": 4,
            "sonara_outputs": [],
        }
    ]


def test_api_rejects_classifier_scoring_inside_audio_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/jobs",
        json={"models": ["mert"], "classifier_keys": ["voice_presence"]},
    )

    assert response.status_code == 422


def test_api_normalizes_exact_sonara_outputs_and_native_batch_size(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        AnalysisJobManager,
        "validate_sonara_preflight",
        lambda _manager: None,
    )
    monkeypatch.setattr(AnalysisJobManager, "start", _analysis_start(calls))
    client = _client(monkeypatch, tmp_path)

    defaulted = client.post(
        "/api/analysis/jobs",
        json={"models": ["sonara"], "limit": 0},
    )
    explicit = client.post(
        "/api/analysis/jobs",
        json={
            "models": ["sonara"],
            "limit": 0,
            "sonara_outputs": ["fingerprint", "timeline", "embedding"],
            "sonara_batch_size": 12,
        },
    )

    assert defaulted.status_code == 200
    assert defaulted.json()["sonara_outputs"] == ["core"]
    assert defaulted.json()["sonara_batch_size"] == 8
    assert explicit.status_code == 200
    assert explicit.json()["sonara_outputs"] == [
        "core",
        "timeline",
        "embedding",
        "fingerprint",
    ]
    assert explicit.json()["sonara_batch_size"] == 12
    assert [call["sonara_outputs"] for call in calls] == [
        ["core"],
        ["core", "timeline", "embedding", "fingerprint"],
    ]


def test_api_rejects_removed_representations_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/jobs",
        json={"models": ["sonara"], "sonara_outputs": ["representations"]},
    )

    assert response.status_code == 400
    assert "representations" in response.json()["detail"]


def test_api_defaults_audio_job_to_ml_models_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(AnalysisJobManager, "start", _analysis_start(calls))

    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/jobs",
        json={"limit": 0},
    )

    assert response.status_code == 200
    assert response.json()["models"] == ["maest", "mert", "muq", "clap"]
    assert calls[0]["sonara_outputs"] == []


def test_api_pipeline_preserves_fixed_stage_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured: list[dict[str, object]] = []

    def start(
        _manager: AnalysisPipelineManager,
        **kwargs: object,
    ) -> dict[str, object]:
        captured.append(dict(kwargs))
        return {
            "job_id": "pipeline-job",
            "state": "queued",
            "order": [
                stage
                for stage in ("sonara", "ml", "classifiers")
                if stage in kwargs["stages"]
            ],
        }

    monkeypatch.setattr(AnalysisPipelineManager, "start", start)
    monkeypatch.setattr(
        api,
        "promoted_classifiers",
        lambda: [{"classifier_key": "voice_presence"}],
    )
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stages": ["classifiers", "ml"],
            "limit": 0,
            "ml": {
                "models": ["mert"],
                "device": "cpu",
                "top_k": 3,
                "track_batch_size": 2,
                "inference_batch_size": 4,
            },
            "classifiers": {"classifier_keys": ["voice_presence"]},
        },
    )

    assert response.status_code == 200
    assert response.json()["order"] == ["ml", "classifiers"]
    assert captured[0]["ml"] == {
        "models": ["mert"],
        "device": "cpu",
        "top_k": 3,
        "track_batch_size": 2,
        "inference_batch_size": 4,
    }


def test_api_sonara_preflight_returns_409_before_starting_job(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []

    def reject(_manager: AnalysisJobManager) -> None:
        events.append("preflight")
        raise RuntimeError(
            "SONARA_RELEASE_PREPARATION_REQUIRED: exact release is inactive"
        )

    def start(_manager: AnalysisJobManager, **_kwargs: object) -> dict[str, object]:
        events.append("start")
        return {"job_id": "should-not-start"}

    monkeypatch.setattr(AnalysisJobManager, "validate_sonara_preflight", reject)
    monkeypatch.setattr(AnalysisJobManager, "start", start)
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/jobs",
        json={"models": ["sonara"], "limit": 0},
    )

    assert response.status_code == 409
    assert response.json()["detail"].startswith(
        "SONARA_RELEASE_PREPARATION_REQUIRED:"
    )
    assert events == ["preflight"]


def test_api_classifier_preflight_errors_preserve_manifest_reason(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        api,
        "promoted_classifiers",
        lambda: [
            {
                "classifier_key": "voice_presence",
                "is_scoring_compatible": False,
                "manifest_errors": ["MERT contract is inactive"],
            }
        ],
    )
    response = _client(monkeypatch, tmp_path).post(
        "/api/classifiers/analyze",
        json={"classifier_keys": ["voice_presence"], "limit": 0},
    )

    assert response.status_code == 400
    assert "MERT contract is inactive" in response.json()["detail"]


def test_api_reset_uses_v7_analysis_family_and_rejects_legacy_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _client(monkeypatch, tmp_path)

    reset = client.post("/api/analysis/reset", json={"analysis_family": "mert"})
    legacy = client.post("/api/analysis/reset", json={"adapter": "mert"})

    assert reset.status_code == 200
    assert reset.json() == {
        "core_rows_deleted": 0,
        "artifact_rows_deleted": 0,
        "classifier_rows_deleted": 0,
    }
    assert legacy.status_code == 422


def test_api_rejects_legacy_batch_size_and_unknown_device(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _client(monkeypatch, tmp_path)

    assert client.post(
        "/api/analysis/jobs",
        json={"models": ["mert"], "batch_size": 4},
    ).status_code == 422
    assert client.post(
        "/api/analysis/jobs",
        json={"models": ["mert"], "device": "gpu"},
    ).status_code == 422
