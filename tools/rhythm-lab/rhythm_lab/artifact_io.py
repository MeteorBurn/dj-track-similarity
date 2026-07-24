from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import numpy as np

from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    ClassifierFeatureRow,
)
from dj_track_similarity.classifier_manifest import (
    CLASSIFIER_MANIFEST_VERSION,
    CLASSIFIER_PUBLICATION_GENERATIONS_DIR,
    CLASSIFIER_PUBLICATION_POINTER_NAME,
    CLASSIFIER_PUBLICATION_POINTER_VERSION,
    require_scoring_compatible_manifest,
)
from dj_track_similarity.classifier_scoring import (
    ClassifierScorer,
    load_classifier_requirements,
)


_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
TRAINING_METADATA_VERSION = 1


class ArtifactIntegrityError(ValueError):
    """An artifact is not bound to trusted canonical metadata."""


@dataclass(frozen=True)
class VerifiedArtifact:
    path: Path
    metadata_path: Path
    artifact_hash: str
    artifact_bytes: bytes
    payload: dict[str, object]


@dataclass(frozen=True)
class PublishedArtifact:
    model_path: Path
    metadata_path: Path
    pointer_path: Path
    generation_id: str
    artifact_hash: str
    manifest_hash: str


class _ManifestOutputRepository:
    """Expose staged manifest outputs as active for read-only scorer validation."""

    def __init__(self, outputs: Sequence[AnalysisOutput]) -> None:
        self._outputs = {output.key: output for output in outputs}

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        return self._outputs.get((analysis_family, output_kind))


def artifact_sha256(artifact_bytes: bytes) -> str:
    return f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}"


def publish_promoted_artifact(
    target: str | Path,
    *,
    artifact_bytes: bytes,
    metadata: Mapping[str, object],
    expected_classifier_key: str,
) -> PublishedArtifact:
    """Publish one immutable model/manifest generation behind an atomic pointer."""

    target_dir = Path(target)
    generations_dir = target_dir / CLASSIFIER_PUBLICATION_GENERATIONS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    generations_dir.mkdir(parents=True, exist_ok=True)

    artifact_hash = artifact_sha256(artifact_bytes)
    if metadata.get("artifact_hash") != artifact_hash:
        raise ArtifactIntegrityError(
            "Promoted metadata artifact_hash does not match exact model bytes"
        )
    manifest_bytes = (
        json.dumps(
            dict(metadata),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    manifest_hash = artifact_sha256(manifest_bytes)
    generation_id = uuid4().hex
    staging_dir = generations_dir / f".staging-{generation_id}"
    generation_dir = generations_dir / generation_id
    pointer_path = target_dir / CLASSIFIER_PUBLICATION_POINTER_NAME
    pointer_staging = target_dir / f".current-{uuid4().hex}.tmp"
    generation_published = False
    try:
        staging_dir.mkdir()
        _write_fsynced(staging_dir / "model.joblib", artifact_bytes)
        _write_fsynced(staging_dir / "model.json", manifest_bytes)
        _fsync_directory(staging_dir)
        _verify_staged_pair(
            staging_dir,
            artifact_hash=artifact_hash,
            manifest_hash=manifest_hash,
        )
        _validate_staged_classifier(
            staging_dir,
            expected_classifier_key=expected_classifier_key,
        )

        os.replace(staging_dir, generation_dir)
        generation_published = True
        _fsync_directory(generations_dir)

        pointer_bytes = (
            json.dumps(
                {
                    "artifact_hash": artifact_hash,
                    "generation_id": generation_id,
                    "manifest_hash": manifest_hash,
                    "publication_version": CLASSIFIER_PUBLICATION_POINTER_VERSION,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
        _write_fsynced(pointer_staging, pointer_bytes)
        os.replace(pointer_staging, pointer_path)
        _fsync_directory(target_dir)
    except Exception:
        pointer_staging.unlink(missing_ok=True)
        if staging_dir.exists():
            (staging_dir / "model.joblib").unlink(missing_ok=True)
            (staging_dir / "model.json").unlink(missing_ok=True)
            staging_dir.rmdir()
        raise

    if not generation_published:  # pragma: no cover - guarded by the flow above.
        raise RuntimeError("Classifier generation was not published")
    return PublishedArtifact(
        model_path=generation_dir / "model.joblib",
        metadata_path=generation_dir / "model.json",
        pointer_path=pointer_path,
        generation_id=generation_id,
        artifact_hash=artifact_hash,
        manifest_hash=manifest_hash,
    )


def _validate_staged_classifier(
    staging_dir: Path,
    *,
    expected_classifier_key: str,
) -> None:
    """Exercise the production scorer before a generation can become current."""

    model_path = staging_dir / "model.joblib"
    try:
        manifest = require_scoring_compatible_manifest(
            model_path,
            expected_classifier_key=expected_classifier_key,
        )
        repository = _ManifestOutputRepository(manifest.required_outputs)
        requirements = load_classifier_requirements(
            repository,  # type: ignore[arg-type]
            expected_classifier_key,
            model_path=model_path,
        )
        scorer = ClassifierScorer(requirements)
        scorer.score_row(
            ClassifierFeatureRow(
                target=AnalysisTarget(
                    catalog_uuid="promotion-validation",
                    track_id=1,
                    track_uuid="promotion-validation",
                    content_generation=1,
                ),
                specification=requirements.specification,
                vector=np.zeros(len(requirements.feature_names), dtype=np.float32),
            ),
            analyzed_at="1970-01-01T00:00:00+00:00",
        )
    except Exception as error:
        raise ArtifactIntegrityError(
            f"Staged promoted classifier is not scoring-ready: {error}"
        ) from error


def load_verified_artifact(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    metadata_path: str | Path | None = None,
) -> VerifiedArtifact:
    artifact = Path(path)
    expected, trusted_metadata = _trusted_expected_hash(
        artifact,
        expected_sha256=expected_sha256,
        metadata_path=metadata_path,
    )
    try:
        artifact_bytes = artifact.read_bytes()
    except OSError as error:
        raise ArtifactIntegrityError(
            f"Cannot read model artifact bytes: {artifact}"
        ) from error
    actual = artifact_sha256(artifact_bytes)
    if actual != expected:
        raise ArtifactIntegrityError(
            f"Model artifact SHA-256 mismatch: expected {expected}, got {actual}"
        )

    import joblib

    try:
        payload = joblib.load(io.BytesIO(artifact_bytes))
    except Exception as error:
        raise ArtifactIntegrityError(
            f"Verified model artifact cannot be deserialized: {artifact}"
        ) from error
    if not isinstance(payload, dict):
        raise ArtifactIntegrityError(
            f"Verified model artifact payload must be an object: {artifact}"
        )
    return VerifiedArtifact(
        path=artifact,
        metadata_path=trusted_metadata,
        artifact_hash=actual,
        artifact_bytes=artifact_bytes,
        payload=dict(payload),
    )


def _trusted_expected_hash(
    artifact: Path,
    *,
    expected_sha256: str | None,
    metadata_path: str | Path | None,
) -> tuple[str, Path]:
    if expected_sha256 is not None:
        return _required_sha256(expected_sha256), Path(
            metadata_path if metadata_path is not None else artifact
        )

    selected_metadata = (
        Path(metadata_path)
        if metadata_path is not None
        else _default_metadata_path(artifact)
    )
    try:
        raw = json.loads(selected_metadata.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ArtifactIntegrityError(
            f"Trusted artifact metadata is required before deserialization: "
            f"{selected_metadata}"
        ) from error
    except (OSError, json.JSONDecodeError) as error:
        raise ArtifactIntegrityError(
            f"Trusted artifact metadata is unreadable: {selected_metadata}"
        ) from error
    if not isinstance(raw, Mapping):
        raise ArtifactIntegrityError(
            f"Trusted artifact metadata must be an object: {selected_metadata}"
        )

    if selected_metadata.name == "model.json":
        if artifact.name != "model.joblib":
            raise ArtifactIntegrityError(
                "Promoted model metadata may bind only model.joblib"
            )
        if raw.get("manifest_version") != CLASSIFIER_MANIFEST_VERSION:
            raise ArtifactIntegrityError(
                "Promoted model metadata has an unsupported manifest_version"
            )
    else:
        if raw.get("training_metadata_version") != TRAINING_METADATA_VERSION:
            raise ArtifactIntegrityError(
                "Training metadata has an unsupported training_metadata_version"
            )
        declared_name = raw.get("artifact_filename")
        if declared_name != artifact.name:
            raise ArtifactIntegrityError(
                "Training metadata artifact_filename does not match the selected "
                "artifact"
            )
    return _required_sha256(raw.get("artifact_hash")), selected_metadata


def _default_metadata_path(artifact: Path) -> Path:
    if artifact.name == "model.joblib":
        return artifact.with_name("model.json")
    return artifact.with_suffix(".metrics.json")


def _required_sha256(value: object) -> str:
    if not isinstance(value, str) or not _SHA256_PATTERN.fullmatch(value):
        raise ArtifactIntegrityError(
            "Trusted artifact metadata must declare artifact_hash as "
            "sha256 followed by 64 lowercase hex digits"
        )
    return value


def _write_fsynced(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _verify_staged_pair(
    staging_dir: Path,
    *,
    artifact_hash: str,
    manifest_hash: str,
) -> None:
    model_bytes = (staging_dir / "model.joblib").read_bytes()
    manifest_bytes = (staging_dir / "model.json").read_bytes()
    if artifact_sha256(model_bytes) != artifact_hash:
        raise ArtifactIntegrityError(
            "Staged promoted model bytes failed the SHA-256 fence"
        )
    if artifact_sha256(manifest_bytes) != manifest_hash:
        raise ArtifactIntegrityError(
            "Staged promoted manifest bytes failed the SHA-256 fence"
        )
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactIntegrityError(
            "Staged promoted manifest is not valid UTF-8 JSON"
        ) from error
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("artifact_hash") != artifact_hash
    ):
        raise ArtifactIntegrityError(
            "Staged promoted manifest does not bind the model SHA-256"
        )
