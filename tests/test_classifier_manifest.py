import json
from pathlib import Path

import pytest

from dj_track_similarity.classifier_manifest import ManifestVersionError, load_classifier_manifest_summary


def test_v1_manifest_hard_rejected(tmp_path: Path) -> None:
    """v1 manifests must be hard-rejected: load_classifier_manifest_summary returns status='unsupported',
    not 'valid'. The underlying ManifestVersionError is caught internally and converted to a summary."""
    model_path = tmp_path / "model.joblib"
    manifest_path = tmp_path / "model.json"
    manifest_path.write_text(json.dumps({"manifest_version": 1}), encoding="utf-8")

    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key="test_classifier",
        metadata_path=manifest_path,
    )

    assert summary.status == "unsupported", f"Expected status='unsupported', got {summary.status!r}"
    assert summary.is_scoring_compatible is False, "v1 manifest must not be scoring-compatible"
