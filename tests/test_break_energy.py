from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import fields, replace
from pathlib import Path

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient

from dj_track_similarity import api as api_module
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    EmbeddingOutput,
    EmbeddingWrite,
    SonaraWrite,
    current_embedding_spec,
)
from dj_track_similarity.classifier_jobs import ClassifierJobManager
from dj_track_similarity.classifier_scoring import (
    ClassifierScorer,
    default_classifier_model_path,
    load_classifier_requirements,
    promoted_classifiers,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db_ddl import SonaraRow


_NOW = "2026-07-24T14:00:00.000000Z"


class _FixedProbabilityModel:
    n_features_in_ = 1
    classes_ = np.asarray(["straight", "broken"], dtype=object)

    def __init__(self, broken_probability: float = 0.87) -> None:
        self.broken_probability = broken_probability

    def predict_proba(self, matrix: np.ndarray) -> np.ndarray:
        probabilities = np.asarray(
            [1.0 - self.broken_probability, self.broken_probability],
            dtype=np.float64,
        )
        return np.tile(probabilities, (matrix.shape[0], 1))


def _mert_output() -> AnalysisOutput:
    return AnalysisOutput("mert", "embedding")


def _insert_track(db: LibraryDatabase) -> AnalysisTarget:
    track_uuid = str(uuid.uuid4())
    with db.connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO tracks (
                track_uuid, file_path, file_size_bytes, file_modified_ns,
                content_generation, last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, 1024, 123456789, 1, ?, ?, ?)
            """,
            (
                track_uuid,
                f"C:/music/{track_uuid}.wav",
                _NOW,
                _NOW,
                _NOW,
            ),
        )
        track_id = int(cursor.lastrowid)
    return AnalysisTarget(
        catalog_uuid=db.catalog_uuid,
        track_id=track_id,
        track_uuid=track_uuid,
        content_generation=1,
    )


def _write_embedding(
    db: LibraryDatabase,
    target: AnalysisTarget,
    output: AnalysisOutput,
) -> None:
    vector = np.zeros(current_embedding_spec(output.analysis_family).dimension, dtype=np.float32)
    vector[0] = 1.0
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
    assert result.ok


def _write_sonara_core(
    db: LibraryDatabase,
    target: AnalysisTarget,
) -> None:
    values = {field.name: None for field in fields(SonaraRow)}
    values.update(
        {
            "track_id": target.track_id,
            "content_generation": target.content_generation,
            "detected_bpm": 128.0,
            "bpm_confidence": 0.95,
            "detected_key_name": "A minor",
            "detected_key_camelot": "8A",
            "key_confidence": 0.9,
            "energy_score": 0.7,
            "danceability_score": 0.8,
            "valence_score": 0.6,
            "acousticness_score": 0.2,
            "mfcc_mean_blob": np.full(13, 0.5, dtype="<f4").tobytes(),
            "chroma_mean_blob": np.full(12, 0.5, dtype="<f4").tobytes(),
            "spectral_contrast_mean_blob": np.full(
                7, 0.5, dtype="<f4"
            ).tobytes(),
            "analyzed_at": _NOW,
        }
    )
    result = db.save_sonara_results(
        (SonaraWrite(target=target, core=SonaraRow(**values)),)
    )[0]
    assert result.ok, result.error


def _write_model(
    root: Path,
    output: AnalysisOutput,
    *,
    broken_probability: float = 0.87,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    model_path = root / "model.joblib"
    joblib.dump(
        {
            "classifier_key": "break_energy",
            "feature_set": "mert",
            "feature_names": ["mert:0"],
            "feature_count": 1,
            "label_order": ["straight", "broken"],
            "positive_label": "broken",
            "model": _FixedProbabilityModel(broken_probability),
        },
        model_path,
    )
    artifact_hash = f"sha256:{hashlib.sha256(model_path.read_bytes()).hexdigest()}"

    manifest = {
        "classifier_key": "break_energy",
        "profile_name": "Break Energy",
        "artifact_hash": artifact_hash,
        "feature_set": "mert",
        "feature_names": ["mert:0"],
        "feature_count": 1,
        "label_order": ["straight", "broken"],
        "negative_label": "straight",
        "positive_label": "broken",
        "production": {
            "score_semantics": "positive_label_probability",
            "calibration": {"status": "uncalibrated"},
        },
    }
    model_path.with_name("model.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return model_path


def test_classifier_artifact_loads_without_version_or_contract_identity(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    model_path = _write_model(tmp_path / "break-energy", _mert_output())

    metadata = json.loads(model_path.with_name("model.json").read_text(encoding="utf-8"))
    requirements = load_classifier_requirements(
        db,
        "break_energy",
        model_path=model_path,
    )

    assert "manifest_version" not in metadata
    assert "feature_manifest_hash" not in metadata
    assert "required_outputs" not in metadata["production"]
    assert requirements.feature_names == ("mert:0",)


def test_break_energy_job_aggregates_only_feature_ready_tracks(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    ready = _insert_track(db)
    missing = _insert_track(db)
    _write_sonara_core(db, ready)
    _write_embedding(db, ready, output)
    model_path = _write_model(tmp_path / "break-energy", output)
    requirements = load_classifier_requirements(
        db,
        "break_energy",
        model_path=model_path,
    )
    manager = ClassifierJobManager(
        db,
        requirements_loader=lambda key: requirements,
    )

    job_id = manager.create_job(classifier="break_energy")
    queued = manager.get(job_id)

    assert queued.total == 1
    assert queued.required_families == ("mert",)
    assert queued.readiness["break_energy"] == {
        "candidates": 2,
        "ready": 1,
        "not_ready": 1,
        "selected": 1,
    }

    completed = manager.run_job(job_id)

    assert completed.state == "completed"
    assert (completed.processed, completed.analyzed, completed.failed) == (
        1,
        1,
        0,
    )
    ready_detail = db.get_track_detail(
        ready.track_id,
        classifier_specifications=(requirements.specification,),
    ).classifier_scores_detail
    assert len(ready_detail) == 1
    assert ready_detail[0].classifier_key == "break_energy"
    assert ready_detail[0].score == pytest.approx(0.87)
    assert ready_detail[0].predicted_class == "broken"
    assert ready_detail[0].score_bucket == "high"
    assert (
        db.get_track_detail(
            missing.track_id,
            classifier_specifications=(requirements.specification,),
        ).classifier_scores_detail
        == ()
    )


def test_break_energy_public_scorer_preserves_probability_precision(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_embedding(db, target, output)
    model_path = _write_model(
        tmp_path / "break-energy",
        output,
        broken_probability=0.99999999,
    )
    requirements = load_classifier_requirements(
        db,
        "break_energy",
        model_path=model_path,
    )
    row = db.load_classifier_feature_rows(
        requirements.specification,
        targets=(target,),
    )[0]

    write = ClassifierScorer(requirements).score_row(row, analyzed_at=_NOW)

    assert write.score.score == pytest.approx(0.99999999)
    assert write.score.confidence == pytest.approx(0.99999999)
    assert json.loads(write.score.probabilities_json) == pytest.approx(
        {
            "straight": 0.00000001,
            "broken": 0.99999999,
        }
    )


def _score_break_energy_track(
    db: LibraryDatabase,
    target: AnalysisTarget,
    model_path: Path,
):
    requirements = load_classifier_requirements(
        db,
        "break_energy",
        model_path=model_path,
    )
    row = db.load_classifier_feature_rows(
        requirements.specification,
        targets=(target,),
    )[0]
    write = ClassifierScorer(requirements).score_row(row, analyzed_at=_NOW)
    result = db.save_classifier_scores((write,))[0]
    assert result.ok
    return requirements


def test_classifier_score_uuid_rebound_is_noncurrent_and_candidate(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_embedding(db, target, output)
    model_path = _write_model(tmp_path / "break-energy", output)
    requirements = _score_break_energy_track(db, target, model_path)
    rebound_uuid = str(uuid.uuid4())

    with db.connect() as connection:
        connection.execute(
            "UPDATE tracks SET track_uuid = ? WHERE track_id = ?",
            (rebound_uuid, target.track_id),
        )
    with db.connect_artifacts() as connection:
        connection.execute(
            "UPDATE mert_embeddings SET track_uuid = ? WHERE track_id = ?",
            (rebound_uuid, target.track_id),
        )

    candidates = db.list_classifier_candidates(requirements.specification)
    assert [candidate.target.track_uuid for candidate in candidates] == [
        rebound_uuid
    ]
    detail = db.get_track_detail(
        target.track_id,
        classifier_specifications=(requirements.specification,),
    )
    summary = db.list_track_summaries(
        classifier_specifications=(requirements.specification,),
    )[0]

    assert detail.classifier_scores_detail == ()
    assert summary.classifier_scores == ()


def test_changed_ordered_feature_names_are_noncurrent_and_candidate(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_embedding(db, target, output)
    model_path = _write_model(tmp_path / "break-energy", output)
    requirements = _score_break_energy_track(db, target, model_path)
    changed = replace(
        requirements.specification,
        feature_names=("mert:1",),
    )

    candidates = db.list_classifier_candidates(changed)
    assert [candidate.target.track_uuid for candidate in candidates] == [
        target.track_uuid
    ]
    detail = db.get_track_detail(
        target.track_id,
        classifier_specifications=(changed,),
    )
    summary = db.list_track_summaries(
        classifier_specifications=(changed,),
    )[0]
    selected_summary = db.get_track_summaries(
        (target.track_id,),
        classifier_specifications=(changed,),
    )[0]
    paged_summary = db.paginate_track_summaries(
        classifier_specifications=(changed,),
    ).items[0]
    filtered_summary = db.filter_track_summaries(
        classifier_specifications=(changed,),
    )[0]
    filtered_by_stale_score = db.filter_track_summaries(
        classifier_min_scores={"break_energy": 0.5},
        classifier_specifications=(changed,),
    )

    assert detail.classifier_scores_detail == ()
    assert summary.classifier_scores == ()
    assert selected_summary.classifier_scores == ()
    assert paged_summary.classifier_scores == ()
    assert filtered_summary.classifier_scores == ()
    assert filtered_by_stale_score == ()
    assert db.prepare_classifier_rescore(changed) == 1
    assert db.get_track_detail(target.track_id).classifier_scores_detail == ()


def test_unchanged_uuid_generation_and_feature_names_remain_current(
    tmp_path: Path,
) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_embedding(db, target, output)
    model_path = _write_model(tmp_path / "break-energy", output)
    requirements = _score_break_energy_track(db, target, model_path)

    candidates = db.list_classifier_candidates(requirements.specification)
    detail = db.get_track_detail(
        target.track_id,
        classifier_specifications=(requirements.specification,),
    )
    summary = db.list_track_summaries(
        classifier_specifications=(requirements.specification,),
    )[0]
    with db.connect() as connection:
        stored_identity = tuple(
            connection.execute(
                """
                SELECT track_uuid, feature_names_json
                FROM classifier_scores
                WHERE track_id = ? AND classifier_key = 'break_energy'
                """,
                (target.track_id,),
            ).fetchone()
        )

    assert candidates == []
    assert stored_identity == (target.track_uuid, '["mert:0"]')
    assert tuple(
        score.classifier_key for score in detail.classifier_scores_detail
    ) == ("break_energy",)
    assert tuple(
        score.classifier_key for score in summary.classifier_scores
    ) == ("break_energy",)
    assert db.get_track_detail(target.track_id).classifier_scores_detail == ()


def test_library_api_uses_current_promoted_classifier_recipe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    output = _mert_output()
    db.register_analysis_outputs((output,))
    target = _insert_track(db)
    _write_embedding(db, target, output)
    models_root = tmp_path / "models"
    model_path = _write_model(models_root / "break-energy", output)
    _score_break_energy_track(db, target, model_path)
    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        api_module,
        "promoted_classifiers",
        lambda: promoted_classifiers(models_root),
    )
    client = TestClient(api_module.create_app(db_path))
    liked_payload = {
        "catalog_uuid": target.catalog_uuid,
        "track_uuid": target.track_uuid,
        "expected_content_generation": target.content_generation,
        "liked": True,
    }

    page = client.get("/api/tracks").json()
    detail = client.get(f"/api/tracks/{target.track_id}").json()
    filtered = client.post(
        "/api/tracks/filtered",
        json={"classifier_min_scores": {"break_energy": 0.8}},
    ).json()
    liked = client.post(
        f"/api/tracks/{target.track_id}/liked",
        json=liked_payload,
    ).json()
    summary = client.get("/api/library/summary").json()

    assert [score["classifier_key"] for score in page["items"][0]["classifier_scores"]] == [
        "break_energy"
    ]
    assert [
        score["classifier_key"] for score in detail["classifier_scores_detail"]
    ] == ["break_energy"]
    assert [track["track_id"] for track in filtered] == [target.track_id]
    assert [score["classifier_key"] for score in liked["classifier_scores"]] == [
        "break_energy"
    ]
    assert summary["classifiers"] == 1

    manifest_path = model_path.with_name("model.json")
    changed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed_manifest["feature_names"] = ["mert:1"]
    manifest_path.write_text(json.dumps(changed_manifest), encoding="utf-8")

    changed_page = client.get("/api/tracks").json()
    changed_detail = client.get(f"/api/tracks/{target.track_id}").json()
    changed_filtered = client.post(
        "/api/tracks/filtered",
        json={"classifier_min_scores": {"break_energy": 0.8}},
    ).json()
    changed_liked = client.post(
        f"/api/tracks/{target.track_id}/liked",
        json={**liked_payload, "liked": False},
    ).json()
    changed_summary = client.get("/api/library/summary").json()

    assert changed_page["items"][0]["classifier_scores"] == []
    assert changed_detail["classifier_scores_detail"] == []
    assert changed_filtered == []
    assert changed_liked["classifier_scores"] == []
    assert changed_summary["classifiers"] == 0


def _classifier_search_fixture(
    tmp_path: Path,
) -> tuple[
    Path,
    dict[str, AnalysisTarget],
    Path,
]:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    mert_output = _mert_output()
    db.register_analysis_outputs(
        (mert_output, AnalysisOutput("sonara", "core"))
    )
    targets = {
        name: _insert_track(db)
        for name in ("seed", "high", "low")
    }
    for target in targets.values():
        _write_embedding(db, target, mert_output)
        _write_sonara_core(db, target)

    models_root = tmp_path / "models"
    promoted_model = _write_model(
        models_root / "break-energy",
        mert_output,
        broken_probability=0.9,
    )
    low_model = _write_model(
        tmp_path / "low-model",
        mert_output,
        broken_probability=0.1,
    )
    _score_break_energy_track(db, targets["high"], promoted_model)
    _score_break_energy_track(db, targets["low"], low_model)
    return db_path, targets, promoted_model.with_name("model.json")


def _classifier_api_client(
    monkeypatch: pytest.MonkeyPatch,
    db_path: Path,
    models_root: Path,
) -> TestClient:
    monkeypatch.setattr(api_module, "require_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(
        api_module,
        "promoted_classifiers",
        lambda: promoted_classifiers(models_root),
    )
    return TestClient(api_module.create_app(db_path))


def _change_classifier_recipe(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["feature_names"] = ["mert:1"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_hybrid_api_uses_only_current_promoted_classifier_recipe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path, targets, manifest_path = _classifier_search_fixture(tmp_path)
    client = _classifier_api_client(
        monkeypatch,
        db_path,
        tmp_path / "models",
    )
    request = {
        "seed_track_ids": [targets["seed"].track_id],
        "sources": ["mert"],
        "weights": {"mert": 1.0},
        "per_source": 3,
        "limit": 2,
        "classifier_preferences": {"break_energy": 1.0},
        "classifier_risk_weights": {"break_energy": 0.2},
    }

    current_response = client.post("/api/search/hybrid", json=request)

    assert current_response.status_code == 200
    current_rows = current_response.json()["results"]
    assert current_rows[0]["track"]["track_id"] == targets["high"].track_id
    support_by_track = {
        row["track"]["track_id"]: row["classifier_support"]["break_energy"]
        for row in current_rows
    }
    assert support_by_track[targets["high"].track_id]["score"] == pytest.approx(
        0.9
    )
    assert support_by_track[targets["high"].track_id][
        "score_contribution"
    ] > 0.0
    assert support_by_track[targets["high"].track_id][
        "risk_contribution"
    ] == pytest.approx(0.18)
    assert support_by_track[targets["low"].track_id]["score"] == pytest.approx(
        0.1
    )
    assert support_by_track[targets["low"].track_id][
        "score_contribution"
    ] < 0.0

    _change_classifier_recipe(manifest_path)
    changed_response = client.post("/api/search/hybrid", json=request)

    assert changed_response.status_code == 200
    for row in changed_response.json()["results"]:
        support = row["classifier_support"]["break_energy"]
        assert support["available"] is False
        assert support["score"] is None
        assert support["risk_contribution"] is None
        assert "classifier_break_energy" not in row["score_breakdown"]


def test_set_api_uses_only_current_promoted_classifier_recipe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    db_path, targets, manifest_path = _classifier_search_fixture(tmp_path)
    client = _classifier_api_client(
        monkeypatch,
        db_path,
        tmp_path / "models",
    )
    request = {
        "seed_mode": "manual",
        "seed_track_ids": [targets["seed"].track_id],
        "sources": ["mert"],
        "mode": "similar_crate",
        "limit": 2,
        "diversity": 0.0,
        "classifier_preferences": {"break_energy": 1.0},
        "random_seed": 7,
    }

    current_response = client.post("/api/set-builder/generate", json=request)

    assert current_response.status_code == 200
    current_candidate = current_response.json()["items"][1]
    assert current_candidate["track"]["track_id"] == targets["high"].track_id
    assert current_candidate["classifier_scores"]["break_energy"] == pytest.approx(
        0.9
    )
    assert current_candidate["score_breakdown"][
        "classifier_preference"
    ] == pytest.approx(0.8)
    assert current_candidate["score_breakdown"][
        "classifier_confidence"
    ] == pytest.approx(1.0)

    _change_classifier_recipe(manifest_path)
    changed_response = client.post("/api/set-builder/generate", json=request)

    assert changed_response.status_code == 200
    changed_candidate = changed_response.json()["items"][1]
    assert changed_candidate["classifier_scores"] == {}
    assert changed_candidate["score_breakdown"]["classifier_preference"] == 0.0
    assert changed_candidate["score_breakdown"]["classifier_confidence"] == 0.0


def test_default_classifier_model_path_uses_classifier_slug() -> None:
    assert (
        default_classifier_model_path("live_instrumentation")
        .as_posix()
        .endswith("models/classifiers/live-instrumentation/model.joblib")
    )
