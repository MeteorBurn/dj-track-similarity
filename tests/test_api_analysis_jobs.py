from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.analysis_pipeline import AnalysisPipelineManager
from dj_track_similarity.database import LibraryDatabase


def _client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None)
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


def test_api_rejects_obsolete_sonara_outputs_field(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/jobs",
        json={"models": ["sonara"], "sonara_outputs": ["timeline"]},
    )

    assert response.status_code == 422


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
    assert response.json()["models"] == ["maest", "mert", "muq", "mulan", "clap"]
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
            "stages": ["ml"],
            "limit": 0,
            "ml": {
                "models": ["mert"],
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
            "stages": ["ml"],
            "limit": 0,
            "sonara": {},
            "ml": {
                "models": ["mert"],
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
            "stages": ["ml"],
            "ml": {
                "models": ["mert"],
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
                    "preflight_copy_enabled": True,
                    "preflight_copy_count": 12,
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
    assert staging.preflight_copy_enabled is True
    assert staging.preflight_copy_count == 12


def test_api_pipeline_rejects_unknown_ml_staged_setting(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    staging_root = tmp_path / "ml-staging"
    staging_root.mkdir()

    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stages": ["ml"],
            "ml": {
                "models": ["mert"],
                "mode": "staged",
                "staged": {
                    "folder": str(staging_root),
                    "copy_workers": 4,
                    "decode_workers": 4,
                    "stage_size": 64,
                    "inference_batch_size": 16,
                    "preflight_copy_enabled": True,
                    "preflight_copy_count": 64,
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
            "stages": ["sonara"],
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
            "stages": ["sonara"],
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
        "staging_config": None,
    }


def test_api_pipeline_requires_selected_folder_for_staged_sonara(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stages": ["sonara"],
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


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("processes", 0),
        ("processes", 17),
        ("threads", 65),
        ("batch_size", 17),
        ("stage_size", 0),
        ("stage_size", 513),
    ),
)
def test_api_pipeline_rejects_out_of_range_staged_sonara_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    field: str,
    value: int,
) -> None:
    staged = {
        "folder": str(tmp_path),
        "processes": 4,
        "threads": 4,
        "batch_size": 4,
        "stage_size": 32,
    }
    staged[field] = value

    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/pipelines",
        json={
            "stages": ["sonara"],
            "sonara": {
                "mode": "staged",
                "direct_batch_size": 8,
                "staged": staged,
            },
        },
    )

    assert response.status_code == 422


def test_api_sonara_job_starts_without_release_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    events: list[str] = []

    def reject(_manager: AnalysisJobManager) -> None:
        events.append("preflight")
        raise AssertionError("release preflight must not run")

    def start(_manager: AnalysisJobManager, **_kwargs: object) -> dict[str, object]:
        events.append("start")
        return {"job_id": "should-not-start"}

    monkeypatch.setattr(
        AnalysisJobManager,
        "validate_sonara_preflight",
        reject,
        raising=False,
    )
    monkeypatch.setattr(AnalysisJobManager, "start", start)
    response = _client(monkeypatch, tmp_path).post(
        "/api/analysis/jobs",
        json={"models": ["sonara"], "limit": 0},
    )

    assert response.status_code == 200
    assert response.json()["job_id"] == "should-not-start"
    assert events == ["start"]


def test_api_sonara_status_returns_neutral_coverage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def sonara_status(_manager: AnalysisJobManager) -> dict[str, object]:
        calls.append("status")
        return {
            "catalog_uuid": "catalog-current",
            "total_tracks": 3,
            "outputs": [
                {"output_kind": "core", "present_count": 2, "missing_count": 1},
                {
                    "output_kind": "fingerprint",
                    "present_count": 1,
                    "missing_count": 2,
                },
            ],
        }

    monkeypatch.setattr(AnalysisJobManager, "sonara_status", sonara_status, raising=False)

    response = _client(monkeypatch, tmp_path).get("/api/analysis/sonara/status")

    assert response.status_code == 200
    assert response.json() == {
        "catalog_uuid": "catalog-current",
        "total_tracks": 3,
        "outputs": [
            {"output_kind": "core", "present_count": 2, "missing_count": 1},
            {
                "output_kind": "fingerprint",
                "present_count": 1,
                "missing_count": 2,
            },
        ],
    }


def test_api_does_not_register_bulk_classifier_analysis(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    response = _client(monkeypatch, tmp_path).post(
        "/api/classifiers/analyze",
        json={"classifier_keys": ["voice_presence"], "limit": 0},
    )

    assert response.status_code == 405


def test_api_reset_uses_current_analysis_family_and_rejects_legacy_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = _client(monkeypatch, tmp_path)

    reset = client.post("/api/analysis/reset", json={"analysis_family": "mert"})
    legacy = client.post("/api/analysis/reset", json={"adapter": "mert"})

    assert reset.status_code == 200
    assert reset.json() == {
        "feature_rows_deleted": 0,
        "embedding_rows_deleted": 0,
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
