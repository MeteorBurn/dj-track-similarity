from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import dj_track_similarity.api as api
import dj_track_similarity.cli as cli
from dj_track_similarity.classifier_production import build_classifier_calibration_report, suggest_classifier_labels
from dj_track_similarity.classifier_scoring import ClassifierScorer, promoted_classifiers
from dj_track_similarity.database import LibraryDatabase


class FixedProbabilityModel:
    classes_ = np.asarray(["broken", "straight"])

    def predict_proba(self, matrix):
        return np.tile(np.asarray([[0.8, 0.2]], dtype=np.float64), (matrix.shape[0], 1))


def test_promoted_classifiers_report_valid_and_invalid_manifest_status(tmp_path: Path) -> None:
    root = tmp_path / "models" / "classifiers"
    valid_dir = root / "break-energy"
    invalid_dir = root / "bad-profile"
    legacy_dir = root / "legacy-profile"
    valid_dir.mkdir(parents=True)
    invalid_dir.mkdir(parents=True)
    legacy_dir.mkdir(parents=True)
    (valid_dir / "model.joblib").write_bytes(b"model")
    (invalid_dir / "model.joblib").write_bytes(b"model")
    (legacy_dir / "model.joblib").write_bytes(b"model")
    _write_manifest(valid_dir / "model.json", classifier_key="break_energy")
    (invalid_dir / "model.json").write_text(json.dumps({"classifier_key": "bad_profile"}), encoding="utf-8")

    payloads = {payload["classifier_key"]: payload for payload in promoted_classifiers(root)}

    assert payloads["break_energy"]["manifest_status"] == "valid"
    assert payloads["break_energy"]["is_scoring_compatible"] is True
    assert payloads["bad_profile"]["manifest_status"] == "invalid"
    assert payloads["bad_profile"]["is_scoring_compatible"] is False
    assert "positive_label" in "; ".join(payloads["bad_profile"]["manifest_errors"])
    assert payloads["legacy_profile"]["manifest_status"] == "legacy"
    assert payloads["legacy_profile"]["manifest_warnings"]


def test_promoted_classifiers_expose_hybrid_signal_manifest_metadata(tmp_path: Path) -> None:
    root = tmp_path / "models" / "classifiers"
    profile_dir = root / "deep-groove"
    profile_dir.mkdir(parents=True)
    (profile_dir / "model.joblib").write_bytes(b"model")
    _write_manifest(
        profile_dir / "model.json",
        classifier_key="deep_groove",
        hybrid_signal={
            "role": "preference_boost",
            "axis": "groove",
            "label": "Boost deep groove",
            "description": "Uses stored deep_groove scores as a groove preference.",
            "default_preference": 0.55,
            "allowed_modes": ["hybrid", "set"],
            "missing_score_policy": "neutral",
        },
    )

    payload = promoted_classifiers(root)[0]

    assert payload["classifier_key"] == "deep_groove"
    assert payload["hybrid_signal"] == {
        "role": "preference_boost",
        "axis": "groove",
        "label": "Boost deep groove",
        "description": "Uses stored deep_groove scores as a groove preference.",
        "default_preference": 0.55,
        "allowed_modes": ["hybrid", "set"],
        "missing_score_policy": "neutral",
    }
    assert payload["hybrid_signal_source"] == "manifest"


def test_classifier_scorer_rejects_manifest_payload_mismatch(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    model_path = _write_model(tmp_path / "models" / "classifiers" / "break-energy" / "model.joblib")
    _write_manifest(model_path.with_name("model.json"), classifier_key="break_energy", positive_label="other")

    with pytest.raises(ValueError, match="positive_label"):
        ClassifierScorer(db, classifier="break_energy", model_path=model_path)


def test_classifier_calibration_report_is_insufficient_without_feedback(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    scored_id = _track(db, tmp_path, "scored.wav")
    _track(db, tmp_path, "unscored.wav")
    _save_score(db, scored_id, "break_energy", 0.72)
    classifier_info = _classifier_info(tmp_path, "break_energy")

    report = build_classifier_calibration_report(db, "break_energy", classifier_info=classifier_info)

    assert report["status"] == "insufficient_data"
    assert report["coverage"]["tracks_total"] == 2
    assert report["coverage"]["tracks_scored"] == 1
    assert report["available_labels_feedback"]["candidate_feedback_count"] == 0
    assert report["status_gate"]["calibrated_probability_available"] is False


def test_classifier_calibration_report_marks_scores_stale_when_model_identity_changes(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "scored.wav")
    _save_score(db, track_id, "break_energy", 0.72)
    classifier_info = _classifier_info(tmp_path, "break_energy", model_id="new-model-identity")

    report = build_classifier_calibration_report(db, "break_energy", classifier_info=classifier_info)

    assert report["status"] == "stale"
    assert report["coverage"]["tracks_scored"] == 1
    assert report["coverage"]["stale_scores"] == 1
    assert report["coverage"]["fresh_scores"] == 0
    assert report["status_gate"]["calibrated_probability_available"] is False
    assert "stale" in report["status_gate"]["decision"].lower()


def test_classifier_label_suggestions_prioritize_uncertain_unlabeled_scores(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    low_id = _track(db, tmp_path, "low.wav")
    uncertain_id = _track(db, tmp_path, "uncertain.wav")
    nearest_id = _track(db, tmp_path, "nearest.wav")
    high_id = _track(db, tmp_path, "high.wav")
    _save_score(db, low_id, "break_energy", 0.10)
    _save_score(db, uncertain_id, "break_energy", 0.52)
    _save_score(db, nearest_id, "break_energy", 0.49)
    _save_score(db, high_id, "break_energy", 0.90)
    classifier_info = _classifier_info(tmp_path, "break_energy")

    report = suggest_classifier_labels(
        db,
        "break_energy",
        mode="uncertainty",
        limit=3,
        random_seed=99,
        classifier_info=classifier_info,
    )

    assert [item["track"]["id"] for item in report["suggestions"]] == [nearest_id, uncertain_id, low_id]
    assert report["suggestions"][0]["label_status"] == "unlabeled"


def test_classifier_reports_and_suggestions_are_scoped_by_classifier_key(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    break_id = _track(db, tmp_path, "break.wav")
    live_id = _track(db, tmp_path, "live.wav")
    _save_score(db, break_id, "break_energy", 0.51)
    _save_score(db, live_id, "live_instrumentation", 0.50)
    classifier_info = _classifier_info(tmp_path, "break_energy")

    report = build_classifier_calibration_report(db, "break_energy", classifier_info=classifier_info)
    suggestions = suggest_classifier_labels(db, "break_energy", classifier_info=classifier_info)

    assert report["coverage"]["tracks_scored"] == 1
    assert [item["track"]["id"] for item in suggestions["suggestions"]] == [break_id]


def test_classifier_cli_calibration_report_outputs_json(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _track(db, tmp_path, "scored.wav")
    _save_score(db, track_id, "break_energy", 0.61)

    result = CliRunner().invoke(
        cli.app,
        ["classifier", "calibration-report", "--classifier", "break_energy", "--db", str(db_path)],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["classifier_key"] == "break_energy"
    assert payload["status"] == "insufficient_data"


def test_classifier_cli_suggest_labels_outputs_ordered_json(tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    far_id = _track(db, tmp_path, "far.wav")
    near_id = _track(db, tmp_path, "near.wav")
    _save_score(db, far_id, "break_energy", 0.9)
    _save_score(db, near_id, "break_energy", 0.48)

    result = CliRunner().invoke(
        cli.app,
        ["classifier", "suggest-labels", "--classifier", "break_energy", "--db", str(db_path), "--limit", "2"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert [item["track"]["id"] for item in payload["suggestions"]] == [near_id, far_id]


def test_classifier_api_rejects_invalid_manifest_for_scoring(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    LibraryDatabase(db_path)
    monkeypatch.setattr(
        api,
        "promoted_classifiers",
        lambda: [
            {
                "classifier_key": "break_energy",
                "is_scoring_compatible": False,
                "manifest_errors": ["model.json positive_label is required"],
            }
        ],
    )
    client = TestClient(api.create_app(db_path))

    response = client.post("/api/classifiers/break_energy/analyze", json={})

    assert response.status_code == 400
    assert "positive_label" in response.json()["detail"]


def test_classifier_api_returns_label_suggestions(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    near_id = _track(db, tmp_path, "near.wav")
    far_id = _track(db, tmp_path, "far.wav")
    _save_score(db, near_id, "break_energy", 0.49)
    _save_score(db, far_id, "break_energy", 0.95)
    classifier_info = _classifier_info(tmp_path, "break_energy")
    monkeypatch.setattr(api, "promoted_classifiers", lambda: [classifier_info])
    client = TestClient(api.create_app(db_path))

    response = client.get("/api/classifiers/break_energy/label-suggestions?mode=uncertainty&limit=2&random_seed=7")

    assert response.status_code == 200
    payload = response.json()
    assert [item["track"]["id"] for item in payload["suggestions"]] == [near_id, far_id]


def test_classifier_api_returns_calibration_report(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    db = LibraryDatabase(db_path)
    track_id = _track(db, tmp_path, "scored.wav")
    _save_score(db, track_id, "break_energy", 0.62)
    classifier_info = _classifier_info(tmp_path, "break_energy")
    monkeypatch.setattr(api, "promoted_classifiers", lambda: [classifier_info])
    client = TestClient(api.create_app(db_path))

    response = client.get("/api/classifiers/break_energy/calibration-report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "insufficient_data"
    assert payload["coverage"]["tracks_scored"] == 1


def _track(db: LibraryDatabase, tmp_path: Path, filename: str) -> int:
    path = tmp_path / filename
    path.write_bytes(b"audio")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1.0, metadata={"title": filename})


def _save_score(db: LibraryDatabase, track_id: int, classifier: str, score: float) -> None:
    db.save_classifier_score(
        track_id,
        classifier=classifier,
        score=score,
        label="high" if score >= 0.8 else "medium" if score >= 0.5 else "low",
        confidence=max(score, 1.0 - score),
        probabilities={"broken": score, "straight": 1.0 - score},
        feature_set="combined",
        model_id="model.joblib",
    )


def _classifier_info(tmp_path: Path, classifier_key: str, *, model_id: str | None = None) -> dict[str, object]:
    model_path = tmp_path / "models" / "classifiers" / classifier_key.replace("_", "-") / "model.joblib"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_bytes(b"model")
    metadata_path = model_path.with_name("model.json")
    _write_manifest(metadata_path, classifier_key=classifier_key, model_id=model_id)
    return {
        "classifier_key": classifier_key,
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
        "is_scoring_compatible": True,
    }


def _write_model(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": FixedProbabilityModel(),
            "feature_set": "combined",
            "feature_names": ["sonara:bpm", "mert:0", "maest:0"],
            "label_order": ["broken", "straight"],
            "classifier_key": "break_energy",
            "positive_label": "broken",
        },
        path,
    )
    return path


def _write_manifest(
    path: Path,
    *,
    classifier_key: str,
    positive_label: str = "broken",
    model_id: str | None = None,
    hybrid_signal: dict[str, object] | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "classifier_key": classifier_key,
                "manifest_version": 1,
                "profile_name": classifier_key.replace("_", " ").title(),
                "profile_type": "binary",
                "feature_set": "combined",
                "feature_count": 3,
                "label_order": ["broken", "straight"],
                "positive_label": positive_label,
                "negative_label": "straight",
                **({"model_id": model_id} if model_id is not None else {}),
                **({"hybrid_signal": hybrid_signal} if hybrid_signal is not None else {}),
                "trained_label_counts": {"broken": 10, "straight": 10},
                "production": {
                    "score_semantics": "positive_label_probability",
                    "required_inputs": ["sonara", "mert", "maest"],
                    "calibration": {"status": "uncalibrated", "method": None, "report": None},
                },
            }
        ),
        encoding="utf-8",
    )
