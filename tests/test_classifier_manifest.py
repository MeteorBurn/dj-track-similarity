from __future__ import annotations

import json
from pathlib import Path

from dj_track_similarity.classifier_manifest import (
    load_classifier_manifest_summary,
)


_ARTIFACT_HASH = "sha256:" + "a" * 64


def _manifest_payload(
    *,
    feature_names: list[str] | None = None,
) -> dict[str, object]:
    names = feature_names or ["mert:0"]
    return {
        "classifier_key": "test_classifier",
        "artifact_hash": _ARTIFACT_HASH,
        "feature_set": "embedding-features",
        "feature_names": names,
        "feature_count": len(names),
        "label_order": ["negative", "positive"],
        "negative_label": "negative",
        "positive_label": "positive",
        "production": {
            "score_semantics": "positive_label_probability",
            "calibration": {"status": "uncalibrated"},
        },
    }


def _write_manifest(
    tmp_path: Path,
    payload: dict[str, object],
) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    model_path = tmp_path / "model.joblib"
    manifest_path = tmp_path / "model.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    return model_path, manifest_path


def test_manifest_derives_input_families_from_ordered_feature_names(
    tmp_path: Path,
) -> None:
    names = ["mert:1", "clap:2", "mert:0"]
    model_path, manifest_path = _write_manifest(
        tmp_path,
        _manifest_payload(feature_names=names),
    )

    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="test_classifier",
        metadata_path=manifest_path,
    )

    assert summary.status == "valid", summary.errors
    assert summary.feature_names == tuple(names)
    assert summary.required_inputs == ("mert", "clap")
    assert summary.to_api_dict()["required_inputs"] == ["mert", "clap"]


def test_muq_manifest_checks_current_embedding_dimension(
    tmp_path: Path,
) -> None:
    names = ["muq:0", "muq:1023", "mert:1"]
    model_path, manifest_path = _write_manifest(
        tmp_path,
        _manifest_payload(feature_names=names),
    )

    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="test_classifier",
        metadata_path=manifest_path,
    )

    assert summary.status == "valid", summary.errors
    assert summary.required_inputs == ("muq", "mert")

    invalid_model, invalid_manifest = _write_manifest(
        tmp_path / "invalid-index",
        _manifest_payload(feature_names=["muq:1024"]),
    )
    invalid_summary = load_classifier_manifest_summary(
        invalid_model,
        expected_classifier_key="test_classifier",
        metadata_path=invalid_manifest,
    )

    assert invalid_summary.status == "invalid"
    assert any(
        "outside the current muq dimension 1024" in error
        for error in invalid_summary.errors
    )


def test_manifest_rejects_duplicate_feature_names(tmp_path: Path) -> None:
    model_path, manifest_path = _write_manifest(
        tmp_path,
        _manifest_payload(feature_names=["mert:0", "mert:0"]),
    )

    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="test_classifier",
        metadata_path=manifest_path,
    )

    assert summary.status == "invalid"
    assert "model.json feature_names must not contain duplicates" in summary.errors


def test_manifest_rejects_unknown_embedding_source_without_raising(
    tmp_path: Path,
) -> None:
    model_path, manifest_path = _write_manifest(
        tmp_path,
        _manifest_payload(feature_names=["sonara48d:0"]),
    )

    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="test_classifier",
        metadata_path=manifest_path,
    )

    assert summary.status == "invalid"
    assert any("unsupported feature 'sonara48d:0'" in error for error in summary.errors)


def test_manifest_accepts_sonara_native_48d_classifier(tmp_path: Path) -> None:
    names = [f"sonara48d:{index}" for index in range(48)]
    payload = _manifest_payload(feature_names=names)
    payload["model_kind"] = "sonara_genre"
    payload["sonara_genre_model"] = "sonara-genre-model.json"
    model_path, manifest_path = _write_manifest(tmp_path, payload)

    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="test_classifier",
        metadata_path=manifest_path,
    )

    assert summary.status == "valid", summary.errors
    assert summary.model_kind == "sonara_genre"
    assert summary.sonara_genre_model == "sonara-genre-model.json"
