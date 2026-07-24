from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dj_track_similarity import api as api_module
from dj_track_similarity import api_routes_set_builder as routes_module
from dj_track_similarity.api_schemas import SetBuilderGenerateRequest
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.set_builder import SetBuilderConfig
from dj_track_similarity.track_models import FileTags, ScannedFile


def _client(monkeypatch, db_path: Path) -> TestClient:
    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg")
    return TestClient(api_module.create_app(db_path))


def _track(database: LibraryDatabase, path: Path):
    path.write_bytes(b"audio")
    stat = path.stat()
    return database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
            audio_codec="pcm_s16le",
            sample_rate_hz=44_100,
            channel_count=2,
            audio_duration_seconds=1.0,
        ),
        tags=FileTags(
            title=path.stem,
            artist="Set Builder Fixture",
            tag_bpm=128.0,
            tag_key="8A",
        ),
    ).identity


def test_set_builder_endpoint_forwards_validated_v7_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def fake_generate(_builder, config: SetBuilderConfig) -> dict[str, object]:
        captured["config"] = config
        return {
            "mode": config.mode,
            "seed_mode": config.seed_mode,
            "seed_track_ids": config.seed_track_ids,
            "coverage": {"tracks": 0, "eligible_tracks": 0},
            "items": [],
        }

    monkeypatch.setattr(routes_module.SmartSetBuilder, "generate", fake_generate)
    monkeypatch.setattr(
        api_module,
        "promoted_classifiers",
        lambda: [{"classifier_key": "break_energy"}],
    )
    response = _client(monkeypatch, tmp_path / "library.sqlite").post(
        "/api/set-builder/generate",
        json={
            "seed_mode": "manual",
            "seed_track_ids": [7],
            "limit": 12,
            "bpm_mode": "low_to_high",
            "bpm_change": "slow",
            "bpm_start": 90,
            "bpm_target": 150,
            "classifier_preferences": {"break_energy": 0.8},
            "classifier_flows": {"break_energy": "rise"},
            "random_seed": 42,
        },
    )

    assert response.status_code == 200
    assert response.json()["seed_track_ids"] == [7]
    config = captured["config"]
    assert isinstance(config, SetBuilderConfig)
    assert config.seed_track_ids == [7]
    assert config.limit == 12
    assert config.bpm_mode == "low_to_high"
    assert config.bpm_change == "slow"
    assert config.bpm_start == 90
    assert config.bpm_target == 150
    assert config.classifier_preferences == {"break_energy": 0.8}
    assert config.classifier_flows == {"break_energy": "rise"}
    assert config.random_seed == 42


def test_set_builder_api_defaults_match_backend_config() -> None:
    request = SetBuilderGenerateRequest()
    config = SetBuilderConfig()

    assert request.seed_mode == config.seed_mode == "manual"
    assert request.seed_track_ids == config.seed_track_ids == []
    assert request.auto_seed_count == config.auto_seed_count == 5
    assert request.mode == config.mode == "balanced_set"
    assert request.limit == config.limit == 24
    assert request.diversity == config.diversity == 0.35
    assert request.energy_curve == config.energy_curve == "balanced"
    assert request.bpm_mode == config.bpm_mode == "general"
    assert request.bpm_change == config.bpm_change == "medium"
    assert request.bpm_start == config.bpm_start is None
    assert request.bpm_target == config.bpm_target is None
    assert request.classifier_preferences == config.classifier_preferences == {}
    assert request.classifier_flows == config.classifier_flows == {}


def test_set_builder_endpoint_rejects_invalid_manual_seed_count(
    monkeypatch,
    tmp_path: Path,
) -> None:
    response = _client(monkeypatch, tmp_path / "library.sqlite").post(
        "/api/set-builder/generate",
        json={"seed_mode": "manual", "seed_track_ids": []},
    )

    assert response.status_code == 400
    assert "1-5 seed tracks" in response.json()["detail"]


def test_set_builder_endpoint_rejects_unknown_classifier(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(api_module, "promoted_classifiers", lambda: [])
    response = _client(monkeypatch, tmp_path / "library.sqlite").post(
        "/api/set-builder/generate",
        json={
            "seed_mode": "manual",
            "seed_track_ids": [1],
            "classifier_preferences": {"missing": 0.7},
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "Unknown classifier: missing"}


def test_set_builder_endpoint_rejects_incompatible_classifier_manifest(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        api_module,
        "promoted_classifiers",
        lambda: [
            {
                "classifier_key": "draft_profile",
                "name": "Draft",
                "is_scoring_compatible": False,
            }
        ],
    )
    response = _client(monkeypatch, tmp_path / "library.sqlite").post(
        "/api/set-builder/generate",
        json={
            "seed_mode": "manual",
            "seed_track_ids": [1],
            "classifier_flows": {"draft_profile": "rise"},
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "detail": "Classifier manifest is invalid: draft_profile"
    }


def test_set_builder_endpoint_rejects_extra_fields(
    monkeypatch,
    tmp_path: Path,
) -> None:
    response = _client(monkeypatch, tmp_path / "library.sqlite").post(
        "/api/set-builder/generate",
        json={"seed_mode": "auto", "unexpected": True},
    )

    assert response.status_code == 422


def test_set_builder_endpoint_reports_missing_current_analysis(
    monkeypatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    identity = _track(LibraryDatabase(db_path), tmp_path / "seed.wav")

    response = _client(monkeypatch, db_path).post(
        "/api/set-builder/generate",
        json={
            "seed_mode": "manual",
            "seed_track_ids": [identity.track_id],
        },
    )

    assert response.status_code == 400
    assert "reanalysis is required" in response.json()["detail"]
