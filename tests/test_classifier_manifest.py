from __future__ import annotations

import json
from pathlib import Path

import pytest

from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import AnalysisOutput
from dj_track_similarity.classifier_manifest import (
    classifier_feature_manifest_hash,
    load_classifier_manifest_summary,
    require_scoring_compatible_manifest,
)


_ARTIFACT_HASH = "sha256:" + "a" * 64


def _mert_output() -> AnalysisOutput:
    return current_embedding_analysis_output("mert", device="cpu")


def _clap_output() -> AnalysisOutput:
    return current_embedding_analysis_output("clap", device="cpu")


def _output_payload(output: AnalysisOutput) -> dict[str, object]:
    return {
        "contract_hash": output.contract_hash,
        "canonical_payload": output.contract.canonical_payload,
    }


def _manifest_payload(
    *,
    feature_names: list[str] | None = None,
    required_outputs: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    names = feature_names or ["mert:0"]
    outputs = required_outputs or [_output_payload(_mert_output())]
    return {
        "manifest_version": 2,
        "classifier_key": "test_classifier",
        "model_id": "model-v2",
        "artifact_hash": _ARTIFACT_HASH,
        "feature_set": "contract-backed",
        "feature_names": names,
        "feature_count": len(names),
        "feature_manifest_hash": classifier_feature_manifest_hash(names),
        "label_order": ["negative", "positive"],
        "negative_label": "negative",
        "positive_label": "positive",
        "production": {
            "score_semantics": "positive_label_probability",
            "required_outputs": outputs,
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


@pytest.mark.parametrize(
    "payload",
    (
        {"manifest_version": 1},
        {},
    ),
)
def test_v1_and_unversioned_manifests_are_hard_rejected(
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    model_path, manifest_path = _write_manifest(tmp_path, payload)

    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="test_classifier",
        metadata_path=manifest_path,
    )

    assert summary.status == "unsupported"
    assert not summary.is_scoring_compatible
    assert "no longer supported" in summary.errors[0]
    with pytest.raises(ValueError, match="Re-train and re-promote"):
        require_scoring_compatible_manifest(
            model_path,
            expected_classifier_key="test_classifier",
            metadata_path=manifest_path,
        )


def test_legacy_required_inputs_and_sonara_signature_are_rejected(
    tmp_path: Path,
) -> None:
    payload = _manifest_payload()
    production = dict(payload["production"])
    production["required_inputs"] = ["mert"]
    production["sonara_analysis_signature"] = {"schema_version": 4}
    payload["production"] = production
    model_path, manifest_path = _write_manifest(tmp_path, payload)

    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="test_classifier",
        metadata_path=manifest_path,
    )

    assert summary.status == "invalid"
    assert any(
        "production.required_inputs is not supported" in error
        for error in summary.errors
    )
    assert any(
        "production.sonara_analysis_signature is not supported" in error
        for error in summary.errors
    )


def test_required_outputs_are_canonical_self_hashed_and_source_ordered(
    tmp_path: Path,
) -> None:
    mert = _mert_output()
    clap = _clap_output()
    payload = _manifest_payload(
        feature_names=["mert:1", "clap:2"],
        required_outputs=[_output_payload(mert), _output_payload(clap)],
    )
    model_path, manifest_path = _write_manifest(tmp_path, payload)

    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="test_classifier",
        metadata_path=manifest_path,
    )

    assert summary.status == "valid"
    assert tuple(output.key for output in summary.required_outputs) == (
        ("mert", "embedding"),
        ("clap", "embedding"),
    )
    assert summary.required_inputs == ("mert", "clap")
    assert summary.to_api_dict()["required_outputs"] == [
        _output_payload(mert),
        _output_payload(clap),
    ]

    wrong_hash = _manifest_payload()
    wrong_outputs = list(wrong_hash["production"]["required_outputs"])
    wrong_outputs[0] = {
        **wrong_outputs[0],
        "contract_hash": "sha256:" + "0" * 64,
    }
    wrong_hash["production"] = {
        **wrong_hash["production"],
        "required_outputs": wrong_outputs,
    }
    _model_path, wrong_path = _write_manifest(tmp_path / "wrong-hash", wrong_hash)
    wrong_summary = load_classifier_manifest_summary(
        _model_path,
        expected_classifier_key="test_classifier",
        metadata_path=wrong_path,
    )
    assert any(
        "does not match canonical_payload" in error for error in wrong_summary.errors
    )

    reversed_payload = _manifest_payload(
        feature_names=["mert:1", "clap:2"],
        required_outputs=[_output_payload(clap), _output_payload(mert)],
    )
    reversed_model, reversed_path = _write_manifest(
        tmp_path / "reversed",
        reversed_payload,
    )
    reversed_summary = load_classifier_manifest_summary(
        reversed_model,
        expected_classifier_key="test_classifier",
        metadata_path=reversed_path,
    )
    assert any(
        "first-occurrence feature source order" in error
        for error in reversed_summary.errors
    )

    string_payload = _manifest_payload()
    output = _output_payload(mert)
    output["canonical_payload_json"] = json.dumps(output.pop("canonical_payload"))
    string_payload["production"] = {
        **string_payload["production"],
        "required_outputs": [output],
    }
    string_model, string_path = _write_manifest(
        tmp_path / "string-contract",
        string_payload,
    )
    string_summary = load_classifier_manifest_summary(
        string_model,
        expected_classifier_key="test_classifier",
        metadata_path=string_path,
    )
    assert any("keys must be exactly" in error for error in string_summary.errors)


def test_feature_manifest_hash_preserves_order_and_manifest_must_match(
    tmp_path: Path,
) -> None:
    forward = ["mert:0", "mert:1"]
    reversed_names = list(reversed(forward))

    assert classifier_feature_manifest_hash(
        forward
    ) != classifier_feature_manifest_hash(reversed_names)

    payload = _manifest_payload(feature_names=forward)
    payload["feature_manifest_hash"] = classifier_feature_manifest_hash(reversed_names)
    model_path, manifest_path = _write_manifest(tmp_path, payload)
    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="test_classifier",
        metadata_path=manifest_path,
    )

    assert summary.status == "invalid"
    assert any("canonical ordered feature_names" in error for error in summary.errors)
