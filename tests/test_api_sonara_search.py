from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    SonaraWrite,
    current_embedding_spec,
)
from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.api import create_app
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_ddl import SonaraRow
from dj_track_similarity.track_models import FileTags, ScannedFile


_NOW = "2026-07-24T12:00:00.000000Z"


def test_sonara_search_endpoint_uses_stored_sonara_features(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = _sonara_library(db_path)
    seed = _add_sonara_track(
        db,
        tmp_path,
        "seed.wav",
        {"energy": 0.8, "danceability": 0.8, "valence": 0.25, "acousticness": 0.1},
    )
    close = _add_sonara_track(
        db,
        tmp_path,
        "close.wav",
        {"energy": 0.78, "danceability": 0.79, "valence": 0.27, "acousticness": 0.12},
    )
    far = _add_sonara_track(
        db,
        tmp_path,
        "far.wav",
        {"energy": 0.15, "danceability": 0.2, "valence": 0.8, "acousticness": 0.65},
    )

    response = TestClient(create_app(db_path)).post(
        "/api/search/sonara",
        json={
            "seed_track_ids": [seed.track_id],
            "mode": "vibe",
            "limit": 5,
            "min_similarity": 0.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["track_id"] for item in payload] == [
        close.track_id,
        far.track_id,
    ]
    assert payload[0]["score"] > payload[1]["score"]


def test_generic_search_endpoint_returns_mert_result_shape(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    output = _mert_output()
    db.register_analysis_outputs((output,))
    seed = _add_embedding_track(db, tmp_path, output, "seed.wav", [1.0, 0.0])
    candidate = _add_embedding_track(db, tmp_path, output, "candidate.wav", [0.9, 0.1])

    response = TestClient(create_app(db_path)).post(
        "/api/search",
        json={
            "seed_track_ids": [seed.track_id],
            "limit": 1,
            "min_similarity": 0.0,
            "epsilon": 0.0,
            "noise": 0.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["track"]["track_id"] == candidate.track_id
    assert payload[0]["score"] > 0.0
    assert payload[0]["score_breakdown"] is None


def test_sonara_search_endpoint_accepts_custom_mixer_and_modifiers(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = _sonara_library(db_path)
    seed = _add_sonara_track(
        db,
        tmp_path,
        "seed.wav",
        {
            "mfcc_mean": [0.2, 0.4],
            "spectral_centroid_mean": 1600,
            "valence": 0.4,
            "energy": 0.5,
        },
    )
    brighter = _add_sonara_track(
        db,
        tmp_path,
        "brighter.wav",
        {
            "mfcc_mean": [0.22, 0.41],
            "spectral_centroid_mean": 1620,
            "valence": 0.7,
            "energy": 0.5,
        },
    )
    darker = _add_sonara_track(
        db,
        tmp_path,
        "darker.wav",
        {
            "mfcc_mean": [0.21, 0.39],
            "spectral_centroid_mean": 1580,
            "valence": 0.2,
            "energy": 0.5,
        },
    )

    response = TestClient(create_app(db_path)).post(
        "/api/search/sonara",
        json={
            "seed_track_ids": [seed.track_id],
            "mode": "custom",
            "limit": 5,
            "min_similarity": 0.0,
            "mixer_weights": {
                "timbre": 1.0,
                "rhythm": 0.0,
                "dynamics": 0.0,
                "harmonic": 0.0,
                "tempo": 0.0,
            },
            "modifiers": {"valence": 1.0, "aggression": 0.0},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["track_id"] for item in payload] == [
        brighter.track_id,
        darker.track_id,
    ]
    assert "timbre" in payload[0]["score_breakdown"]
    assert "modifier_valence" in payload[0]["score_breakdown"]


def test_random_sonara_track_uses_an_unselected_current_sonara_track(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = _sonara_library(db_path)
    targets = [
        _add_sonara_track(db, tmp_path, "one.wav", {"energy": 0.2}),
        _add_sonara_track(db, tmp_path, "two.wav", {"energy": 0.5}),
        _add_sonara_track(db, tmp_path, "three.wav", {"energy": 0.8}),
    ]

    response = TestClient(create_app(db_path)).post(
        "/api/search/sonara/random-track",
        json={"exclude_track_ids": [targets[0].track_id]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["track_id"] in {target.track_id for target in targets[1:]}
    assert payload["analysis_coverage"]["sonara_core"] is True


def test_random_sonara_track_requires_an_available_sonara_track(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)

    response = TestClient(create_app(tmp_path / "library.sqlite")).post(
        "/api/search/sonara/random-track",
        json={},
    )

    assert response.status_code == 409
    assert "SONARA Core" in response.json()["detail"]


def test_random_embedding_track_uses_an_unselected_embedded_track(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    output = _mert_output()
    db.register_analysis_outputs((output,))
    targets = [
        _add_embedding_track(db, tmp_path, output, "one.wav", [1.0, 0.0]),
        _add_embedding_track(db, tmp_path, output, "two.wav", [0.9, 0.1]),
        _add_embedding_track(db, tmp_path, output, "three.wav", [0.0, 1.0]),
    ]
    _track(db, tmp_path, "without-embedding.wav")

    response = TestClient(create_app(db_path)).post(
        "/api/search/random-track",
        json={"analysis_family": "mert", "exclude_track_ids": [targets[0].track_id]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["track_id"] in {target.track_id for target in targets[1:]}
    assert payload["analysis_coverage"]["mert"] is True


def test_random_embedding_track_requires_an_available_embedded_track(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    output = _mert_output()
    db.register_analysis_outputs((output,))
    only = _add_embedding_track(db, tmp_path, output, "only.wav", [1.0, 0.0])

    response = TestClient(create_app(db_path)).post(
        "/api/search/random-track",
        json={"analysis_family": "mert", "exclude_track_ids": [only.track_id]},
    )

    assert response.status_code == 409
    assert "mert" in response.json()["detail"]


def test_search_endpoints_reject_unknown_context_parameter(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    client = TestClient(create_app(tmp_path / "library.sqlite"))
    unknown_context_key = "extra_context_track_ids"

    mert_response = client.post(
        "/api/search", json={"seed_track_ids": [], unknown_context_key: [1]}
    )
    sonara_response = client.post(
        "/api/search/sonara", json={"seed_track_ids": [], unknown_context_key: [1]}
    )

    assert mert_response.status_code == 422
    assert sonara_response.status_code == 422


def test_sonara_search_enforces_the_shared_seed_contract(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    too_many = client.post(
        "/api/search/sonara", json={"seed_track_ids": [1, 2, 3, 4, 5, 6]}
    )
    duplicates = client.post(
        "/api/search/sonara", json={"seed_track_ids": [1, 1]}
    )
    non_positive = client.post(
        "/api/search/sonara", json={"seed_track_ids": [0]}
    )

    assert too_many.status_code == 422
    assert duplicates.status_code == 422
    assert non_positive.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": 501},
        {"min_similarity": -0.1},
        {"min_similarity": 1.1},
        {"epsilon": -0.1},
        {"noise": -0.1},
        {"noise": 1.1},
    ],
)
def test_generic_search_endpoint_rejects_invalid_numeric_fields(
    monkeypatch, tmp_path: Path, payload: dict[str, float]
) -> None:
    monkeypatch.setattr(api, "configure_shared_ffmpeg_runtime", lambda: None, raising=False)
    client = TestClient(create_app(tmp_path / "library.sqlite"))

    response = client.post("/api/search", json={"seed_track_ids": [1], **payload})

    assert response.status_code == 422


def _sonara_library(db_path: Path) -> LibraryDatabase:
    return LibraryDatabase(db_path)


def _add_sonara_track(
    db: LibraryDatabase,
    root: Path,
    name: str,
    features: dict[str, float | list[float]],
) -> AnalysisTarget:
    target = _track(db, root, name)
    values = {field.name: None for field in fields(SonaraRow)}
    energy = _float(features.get("energy"))
    values.update(
        {
            "track_id": target.track_id,
            "energy_score": energy,
            "danceability_score": _float(features.get("danceability")),
            "valence_score": _float(features.get("valence")),
            "acousticness_score": _float(features.get("acousticness")),
            "spectral_centroid_hz": _float(features.get("spectral_centroid_mean")),
            "mfcc_mean_blob": _blob(features.get("mfcc_mean"), 13),
            "chroma_mean_blob": _blob(None, 12),
            "spectral_contrast_mean_blob": _blob(None, 7),
            "analysis_schema_version": 6,
            "bpm_min": 70.0,
            "bpm_max": 180.0,
            "analyzed_at": _NOW,
        }
    )
    result = db.save_sonara_results(
        (
            SonaraWrite(target=target, core=SonaraRow(**values)),
        )
    )[0]
    assert result.ok, result.error
    return target


def _add_embedding_track(
    db: LibraryDatabase,
    root: Path,
    output: AnalysisOutput,
    name: str,
    embedding: list[float],
) -> AnalysisTarget:
    target = _track(db, root, name)
    vector = np.zeros(
        current_embedding_spec(output.analysis_family).dimension,
        dtype=np.float32,
    )
    vector[: len(embedding)] = embedding
    vector /= np.linalg.norm(vector)
    result = db.save_embedding_results(
        (
            EmbeddingWrite(
                target=target,
                output=EmbeddingOutput(
                    family=output.analysis_family,
                    vector=vector,
                    analyzed_at=_NOW,
                ),
            ),
        )
    )[0]
    assert result.ok, result.error
    return target


def _track(db: LibraryDatabase, root: Path, name: str) -> AnalysisTarget:
    path = root / name
    path.write_bytes(name.encode("utf-8"))
    stat = path.stat()
    identity = db.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(path),
            file_size_bytes=stat.st_size,
            file_modified_ns=stat.st_mtime_ns,
            audio_format="wav",
        ),
        tags=FileTags(title=name),
        scanned_at=_NOW,
    ).identity
    return AnalysisTarget(
        identity.catalog_uuid,
        identity.track_id,
        identity.track_uuid,
    )


def _mert_output() -> AnalysisOutput:
    return current_embedding_analysis_output("mert")


def _float(value: float | list[float] | None) -> float | None:
    return float(value) if isinstance(value, (float, int)) else None


def _blob(value: float | list[float] | None, dim: int) -> bytes:
    values = list(value) if isinstance(value, list) else []
    values.extend([0.0] * (dim - len(values)))
    return np.asarray(values[:dim], dtype="<f4").tobytes()
