from __future__ import annotations

import hashlib
import io
import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import numpy as np

from .analysis_contracts import utc_timestamp
from .analysis_model_runners import current_embedding_analysis_output
from .analysis_models import (
    AnalysisOutput,
    AnalysisWriteResult,
    ClassifierFeatureRow,
    ClassifierScoreWrite,
    ClassifierSpecification,
    classifier_required_outputs_hash,
)
from .classifier_manifest import (
    ClassifierManifestSummary,
    CLASSIFIER_PUBLICATION_POINTER_NAME,
    classifier_feature_manifest_hash,
    classifier_manifest_api_fields,
    load_classifier_manifest_summary,
    resolve_classifier_artifact_paths,
    require_scoring_compatible_manifest,
)
from .database import LibraryDatabase
from .db_schema_v7 import ClassifierScoreV7, SonaraRowV7


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SUPPORTED_FEATURE_FAMILIES = ("sonara", "mert", "maest", "clap")
_SONARA_VECTOR_DIMS = {
    "mfcc_mean_blob": 13,
    "chroma_mean_blob": 12,
    "spectral_contrast_mean_blob": 7,
}
_SONARA_NON_NUMERIC_FIELDS = {
    "track_id",
    "content_generation",
    "contract_hash",
    "bpm_candidates_json",
    "detected_key_name",
    "detected_key_camelot",
    "predominant_chord",
    "key_candidates_json",
    "analyzed_at",
    *_SONARA_VECTOR_DIMS,
}
_SONARA_SCALAR_FEATURES = {
    field.name for field in fields(SonaraRowV7)
} - _SONARA_NON_NUMERIC_FIELDS


def classifier_artifact_slug(classifier_key: str) -> str:
    return classifier_key.strip().replace("_", "-")


def default_classifier_model_path(classifier_key: str) -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "models"
        / "classifiers"
        / classifier_artifact_slug(classifier_key)
        / "model.joblib"
    )


def default_classifier_models_root() -> Path:
    return Path(__file__).resolve().parents[2] / "models" / "classifiers"


def promoted_classifiers(
    root: str | Path | None = None,
) -> list[dict[str, object]]:
    models_root = Path(root) if root is not None else default_classifier_models_root()
    if not models_root.exists():
        return []
    artifact_dirs = sorted(
        {
            path.parent
            for path in (
                *models_root.glob("*/model.joblib"),
                *models_root.glob("*/model.json"),
                *models_root.glob(f"*/{CLASSIFIER_PUBLICATION_POINTER_NAME}"),
            )
        }
    )
    classifiers: list[dict[str, object]] = []
    for artifact_dir in artifact_dirs:
        selected_model_path = artifact_dir / "model.joblib"
        try:
            resolved = resolve_classifier_artifact_paths(selected_model_path)
        except ValueError as error:
            summary = ClassifierManifestSummary(
                classifier_key=artifact_dir.name.replace("-", "_"),
                metadata_path=artifact_dir / CLASSIFIER_PUBLICATION_POINTER_NAME,
                model_path=selected_model_path,
                status="invalid",
                errors=(str(error),),
                artifact_prefix=artifact_dir.name,
            )
            classifiers.append(
                _promoted_classifier_payload(
                    summary,
                    model_path_exists=False,
                )
            )
            continue
        model_path = resolved.model_path
        metadata_path = resolved.metadata_path
        classifier_key = _classifier_key_from_metadata_or_slug(
            metadata_path,
            artifact_dir.name,
        )
        summary = load_classifier_manifest_summary(
            model_path,
            expected_classifier_key=classifier_key,
            metadata_path=metadata_path,
        )
        artifact_error: str | None = None
        if summary.is_scoring_compatible and model_path.is_file():
            try:
                _verify_artifact_sha256(
                    model_path,
                    summary.artifact_hash or "",
                )
            except (OSError, ValueError) as error:
                artifact_error = str(error)
        classifiers.append(
            _promoted_classifier_payload(
                summary,
                model_path_exists=model_path.exists(),
                artifact_error=artifact_error,
            )
        )
    return classifiers


@dataclass(frozen=True)
class ClassifierRequirements:
    """Fully validated immutable inputs for one promoted classifier."""

    manifest: ClassifierManifestSummary
    specification: ClassifierSpecification
    model_path: Path
    artifact_hash: str
    label_order: tuple[str, ...]
    manifest_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_path", Path(self.model_path))
        artifact_hash = _validated_sha256(self.artifact_hash)
        object.__setattr__(self, "artifact_hash", artifact_hash)
        labels = tuple(str(label).strip() for label in self.label_order)
        if not labels or any(not label for label in labels):
            raise ValueError("classifier label_order must contain labels")
        if len(set(labels)) != len(labels):
            raise ValueError("classifier label_order must not contain duplicates")
        if self.specification.positive_label not in labels:
            raise ValueError("classifier positive_label is absent from label_order")
        if self.specification.label_order != labels:
            raise ValueError(
                "classifier specification label_order does not match requirements"
            )
        object.__setattr__(self, "label_order", labels)
        object.__setattr__(
            self,
            "manifest_warnings",
            tuple(str(value) for value in self.manifest_warnings),
        )

    @property
    def classifier_key(self) -> str:
        return self.specification.classifier_key

    @property
    def model_id(self) -> str:
        return self.specification.model_id

    @property
    def feature_set(self) -> str:
        return self.specification.feature_set

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self.specification.feature_names

    @property
    def required_outputs(self):
        return self.specification.required_outputs

    @property
    def required_inputs(self) -> tuple[str, ...]:
        return tuple(
            output.contract.analysis_family
            for output in self.specification.required_outputs
        )

    @property
    def positive_label(self) -> str:
        return self.specification.positive_label

    @property
    def uses_sonara(self) -> bool:
        return self.specification.sonara_release_hash is not None


def load_classifier_requirements(
    db: LibraryDatabase,
    classifier: str,
    *,
    model_path: str | Path | None = None,
) -> ClassifierRequirements:
    """Validate a v2 manifest, exact active contracts, features, and artifact.

    This function is deliberately read-only.  In particular, it performs the
    artifact SHA-256 check but never loads the joblib payload and never deletes
    classifier scores.
    """

    path = (
        Path(model_path)
        if model_path is not None
        else default_classifier_model_path(classifier)
    )
    manifest = require_scoring_compatible_manifest(
        path,
        expected_classifier_key=classifier,
    )
    path = manifest.model_path
    specification = _specification_from_manifest(manifest)
    _validate_feature_contracts(specification)
    _require_exact_active_outputs(db, specification)
    _verify_artifact_sha256(path, manifest.artifact_hash or "")
    return ClassifierRequirements(
        manifest=manifest,
        specification=specification,
        model_path=path,
        artifact_hash=manifest.artifact_hash or "",
        label_order=manifest.label_order,
        manifest_warnings=manifest.warnings,
    )


def analyze_classifier(
    db: LibraryDatabase,
    *,
    classifier: str,
    model_path: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    """Score the current ready population through the v7 repository boundary."""

    requirements = load_classifier_requirements(
        db,
        classifier,
        model_path=model_path,
    )
    # This performs a second SHA check over the exact bytes passed to joblib and
    # validates the loaded model.  No score deletion may precede this line.
    scorer = ClassifierScorer(requirements)
    specification = requirements.specification

    deleted_stale = db.prepare_classifier_rescore(specification)
    readiness = db.classifier_candidate_readiness(specification)
    candidates = db.list_classifier_candidates(specification, limit=limit)
    rows = db.load_classifier_feature_rows(
        specification,
        targets=tuple(candidate.target for candidate in candidates),
    )
    feature_not_ready = len(candidates) - len(rows)

    writes: list[ClassifierScoreWrite] = []
    scoring_errors: list[dict[str, object]] = []
    for row in rows:
        try:
            writes.append(scorer.score_row(row))
        except Exception as error:
            scoring_errors.append(
                {
                    "track_id": row.target.track_id,
                    "error": str(error),
                }
            )

    results = db.save_classifier_scores(writes)
    write_errors = [
        {
            "track_id": result.target.track_id,
            "error": result.error,
        }
        for result in results
        if not result.ok
    ]
    errors = [*scoring_errors, *write_errors]
    output: dict[str, object] = {
        "classifier": requirements.classifier_key,
        "scored": sum(result.ok for result in results),
        "skipped": len(candidates) - len(rows),
        "failed": len(errors),
        "deleted_stale": deleted_stale,
        "not_ready": readiness.missing_input_tracks + feature_not_ready,
        "already_scored": readiness.already_scored_tracks,
        "model": str(requirements.model_path),
        "model_id": requirements.model_id,
        "feature_manifest_hash": specification.feature_manifest_hash,
    }
    if errors:
        output["errors"] = errors
    if requirements.manifest_warnings:
        output["warnings"] = list(requirements.manifest_warnings)
    return output


class ClassifierScorer:
    """Loaded classifier whose inputs and model identity are already fenced."""

    def __init__(self, requirements: ClassifierRequirements) -> None:
        if not isinstance(requirements, ClassifierRequirements):
            raise TypeError(
                "ClassifierScorer requires validated ClassifierRequirements"
            )
        self.requirements = requirements
        self.specification = requirements.specification
        self.path = requirements.model_path
        self.classifier_key = requirements.classifier_key
        self.model_id = requirements.model_id
        self.feature_set = requirements.feature_set
        self.feature_names = requirements.feature_names
        self.label_order = requirements.label_order
        self.positive_label = requirements.positive_label
        self.manifest = requirements.manifest
        self.manifest_warnings = requirements.manifest_warnings

        payload = _load_payload(
            requirements.model_path,
            expected_artifact_hash=requirements.artifact_hash,
        )
        _validate_payload_identity(payload, requirements)
        self.payload = payload
        self.model = payload["model"]
        _validate_model(
            self.model,
            feature_count=len(self.feature_names),
            label_order=self.label_order,
        )

    @property
    def model_name(self) -> str:
        return str(self.path)

    def score_row(
        self,
        row: ClassifierFeatureRow,
        *,
        analyzed_at: str | None = None,
    ) -> ClassifierScoreWrite:
        if not isinstance(row, ClassifierFeatureRow):
            raise TypeError("row must be a ClassifierFeatureRow")
        if row.specification != self.specification:
            raise ValueError(
                "classifier feature row does not match the loaded specification"
            )
        vector = np.asarray(row.vector, dtype=np.float32)
        expected_shape = (len(self.feature_names),)
        if vector.shape != expected_shape or not bool(np.all(np.isfinite(vector))):
            raise ValueError(
                "classifier feature vector is incomplete or has invalid values"
            )
        probabilities = _predict_probabilities(
            self.model,
            vector.reshape(1, -1),
            list(self.label_order),
        )[0]
        score = float(probabilities[self.positive_label])
        confidence = float(max(probabilities.values()))
        predicted_class = _argmax_with_tiebreak(
            probabilities,
            list(self.label_order),
        )
        score_row = ClassifierScoreV7(
            track_id=row.target.track_id,
            classifier_key=self.classifier_key,
            content_generation=row.target.content_generation,
            model_id=self.model_id,
            feature_set=self.feature_set,
            feature_manifest_hash=self.specification.feature_manifest_hash,
            required_outputs_hash=self.specification.required_outputs_hash,
            uses_sonara=int(self.requirements.uses_sonara),
            sonara_release_hash=self.specification.sonara_release_hash,
            positive_label=self.positive_label,
            predicted_class=predicted_class,
            score_bucket=_score_bucket_from_score(score),
            score=score,
            confidence=confidence,
            probabilities_json=json.dumps(
                probabilities,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            ),
            analyzed_at=analyzed_at or utc_timestamp(),
        )
        return ClassifierScoreWrite(
            target=row.target,
            specification=self.specification,
            score=score_row,
        )

    def score_rows(
        self,
        rows: Iterable[ClassifierFeatureRow],
    ) -> tuple[ClassifierScoreWrite, ...]:
        return tuple(self.score_row(row) for row in rows)


def save_classifier_score_v7(
    repository: LibraryDatabase,
    write: ClassifierScoreWrite,
) -> AnalysisWriteResult:
    """Persist one already-derived score through the v7 repository only."""

    results = repository.save_classifier_scores((write,))
    if len(results) != 1:
        raise RuntimeError("classifier repository returned an invalid result count")
    return results[0]


def _specification_from_manifest(
    manifest: ClassifierManifestSummary,
) -> ClassifierSpecification:
    if not manifest.model_id:
        raise ValueError("classifier manifest model_id is required")
    if not manifest.feature_set:
        raise ValueError("classifier manifest feature_set is required")
    if not manifest.feature_names:
        raise ValueError("classifier manifest feature_names must not be empty")
    expected_hash = classifier_feature_manifest_hash(manifest.feature_names)
    if manifest.feature_manifest_hash != expected_hash:
        raise ValueError(
            "classifier manifest feature_manifest_hash does not match the "
            "canonical ordered feature_names"
        )
    if not manifest.positive_label:
        raise ValueError("classifier manifest positive_label is required")
    if not manifest.required_outputs:
        raise ValueError("classifier manifest required_outputs must not be empty")
    return ClassifierSpecification(
        classifier_key=manifest.classifier_key,
        model_id=manifest.model_id,
        feature_set=manifest.feature_set,
        feature_manifest_hash=expected_hash,
        required_outputs_hash=classifier_required_outputs_hash(
            manifest.required_outputs
        ),
        feature_names=manifest.feature_names,
        required_outputs=manifest.required_outputs,
        label_order=manifest.label_order,
        positive_label=manifest.positive_label,
    )


def _require_exact_active_outputs(
    db: LibraryDatabase,
    specification: ClassifierSpecification,
) -> None:
    for expected in specification.required_outputs:
        require_current_classifier_output(expected)
        active = db.active_analysis_output(*expected.key)
        family, kind = expected.key
        if active is None:
            raise ValueError(f"classifier input is not active: {family}/{kind}")
        if (
            active.contract_hash != expected.contract_hash
            or active.contract.canonical_payload_json
            != expected.contract.canonical_payload_json
        ):
            raise ValueError(
                "classifier input contract is not the exact active identity: "
                f"{family}/{kind}"
            )


def require_current_classifier_output(expected: AnalysisOutput) -> None:
    """Reject classifier manifests pinned to a superseded ML adapter contract."""

    family, kind = expected.key
    if family == "sonara":
        return
    if kind != "embedding" or family not in {"maest", "mert", "muq", "clap"}:
        raise ValueError(
            f"classifier input is not a supported production output: {family}/{kind}"
        )
    current = current_embedding_analysis_output(family)
    if (
        expected.contract_hash != current.contract_hash
        or expected.contract.canonical_payload_json
        != current.contract.canonical_payload_json
    ):
        raise ValueError(
            "classifier input contract does not match the current adapter identity: "
            f"{family}/{kind}"
        )


def _validate_feature_contracts(
    specification: ClassifierSpecification,
) -> None:
    outputs_by_family = {
        output.contract.analysis_family: output
        for output in specification.required_outputs
    }
    feature_families: list[str] = []
    for feature_name in specification.feature_names:
        family, separator, key = feature_name.partition(":")
        if not separator or family not in _SUPPORTED_FEATURE_FAMILIES or not key:
            raise ValueError(f"unsupported classifier feature: {feature_name}")
        if family not in feature_families:
            feature_families.append(family)
        output = outputs_by_family.get(family)
        if output is None:
            raise ValueError(
                f"classifier feature has no required output: {feature_name}"
            )
        if family == "sonara":
            if output.key != ("sonara", "core"):
                raise ValueError(
                    "SONARA classifier features require the SONARA core output"
                )
            _validate_sonara_feature(feature_name, key)
            continue
        if output.contract.output_kind != "embedding":
            raise ValueError(
                f"{family} classifier features require an embedding output"
            )
        if not key.isdigit():
            raise ValueError(
                f"classifier embedding feature index is invalid: {feature_name}"
            )
        index = int(key)
        dim = output.contract.dim
        if dim is None or not 0 <= index < dim:
            raise ValueError(
                f"classifier embedding feature is out of range: {feature_name}"
            )

    required_families = [
        output.contract.analysis_family for output in specification.required_outputs
    ]
    if feature_families != required_families:
        raise ValueError(
            "classifier required_outputs must follow exact feature source order"
        )


def _validate_sonara_feature(feature_name: str, key: str) -> None:
    field_name, separator, index_text = key.rpartition(":")
    if separator:
        dim = _SONARA_VECTOR_DIMS.get(field_name)
        if dim is None or not index_text.isdigit() or not 0 <= int(index_text) < dim:
            raise ValueError(
                f"SONARA classifier feature is out of range: {feature_name}"
            )
        return
    if key not in _SONARA_SCALAR_FEATURES:
        raise ValueError(f"unsupported SONARA classifier feature: {feature_name}")


def _validated_sha256(value: str) -> str:
    normalized = str(value).strip()
    if not _SHA256_RE.fullmatch(normalized):
        raise ValueError("classifier artifact_hash must be sha256:<64 lowercase hex>")
    return normalized


def _verify_artifact_sha256(path: Path, expected_hash: str) -> None:
    expected = _validated_sha256(expected_hash)
    if not path.is_file():
        raise FileNotFoundError(f"Classifier model not found: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = f"sha256:{digest.hexdigest()}"
    if actual != expected:
        raise ValueError(
            f"Classifier artifact SHA-256 mismatch for {path.name}: "
            f"expected {expected!r}, got {actual!r}"
        )


def _load_payload(
    path: Path,
    *,
    expected_artifact_hash: str,
) -> dict[str, Any]:
    expected = _validated_sha256(expected_artifact_hash)
    if not path.is_file():
        raise FileNotFoundError(f"Classifier model not found: {path}")
    artifact_bytes = path.read_bytes()
    actual = f"sha256:{hashlib.sha256(artifact_bytes).hexdigest()}"
    if actual != expected:
        raise ValueError(
            f"Classifier artifact SHA-256 mismatch for {path.name}: "
            f"expected {expected!r}, got {actual!r}"
        )
    try:
        import joblib
    except ImportError as error:  # pragma: no cover - supported env dependency.
        raise RuntimeError("Classifier analysis requires joblib") from error
    payload = joblib.load(io.BytesIO(artifact_bytes))
    if not isinstance(payload, dict) or "model" not in payload:
        raise ValueError(
            "Classifier model artifact must be a joblib payload with a model"
        )
    return payload


def _validate_payload_identity(
    payload: Mapping[str, object],
    requirements: ClassifierRequirements,
) -> None:
    expected: dict[str, object] = {
        "classifier_key": requirements.classifier_key,
        "model_id": requirements.model_id,
        "feature_set": requirements.feature_set,
        "feature_names": list(requirements.feature_names),
        "feature_manifest_hash": (requirements.specification.feature_manifest_hash),
        "label_order": list(requirements.label_order),
        "positive_label": requirements.positive_label,
        "feature_count": len(requirements.feature_names),
    }
    for key, expected_value in expected.items():
        if key not in payload:
            continue
        actual = payload[key]
        if key in {"feature_names", "label_order"}:
            if isinstance(actual, (str, bytes)) or not isinstance(
                actual,
                Sequence,
            ):
                raise ValueError(
                    f"{requirements.classifier_key} artifact {key} is invalid"
                )
            actual = [str(value) for value in actual]
        elif key == "feature_count":
            if isinstance(actual, bool):
                raise ValueError(
                    f"{requirements.classifier_key} artifact {key} is invalid"
                )
            try:
                actual = int(actual)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{requirements.classifier_key} artifact {key} is invalid"
                ) from error
        else:
            actual = str(actual)
        if actual != expected_value:
            raise ValueError(
                f"{requirements.classifier_key} model artifact {key} "
                "does not match model.json"
            )


def _validate_model(
    model: object,
    *,
    feature_count: int,
    label_order: Sequence[str],
) -> None:
    predict_proba = getattr(model, "predict_proba", None)
    predict = getattr(model, "predict", None)
    if not callable(predict_proba) and not callable(predict):
        raise ValueError("Classifier model must implement predict_proba() or predict()")
    model_feature_count = getattr(model, "n_features_in_", None)
    if model_feature_count is not None:
        if isinstance(model_feature_count, bool):
            raise ValueError("classifier model n_features_in_ is invalid")
        try:
            parsed_count = int(model_feature_count)
        except (TypeError, ValueError) as error:
            raise ValueError("classifier model n_features_in_ is invalid") from error
        if parsed_count != feature_count:
            raise ValueError("classifier model feature count does not match model.json")
    model_classes = getattr(model, "classes_", None)
    if model_classes is not None:
        classes = _model_class_order(model_classes)
        if len(classes) != len(label_order) or set(classes) != set(label_order):
            raise ValueError(
                "classifier model classes do not match manifest label_order"
            )


def _model_class_order(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ValueError("classifier model classes_ is invalid")
    classes = tuple(str(label) for label in value)
    if not classes or any(not label for label in classes):
        raise ValueError("classifier model classes_ is invalid")
    if len(set(classes)) != len(classes):
        raise ValueError("classifier model classes_ contains duplicates")
    return classes


def _predict_probabilities(
    model: object,
    matrix: np.ndarray,
    label_order: list[str],
) -> list[dict[str, float]]:
    values = np.asarray(matrix, dtype=np.float32)
    if values.ndim != 2 or not bool(np.all(np.isfinite(values))):
        raise ValueError("classifier input matrix must be finite and two-dimensional")
    predict_proba = getattr(model, "predict_proba", None)
    if callable(predict_proba):
        raw = np.asarray(predict_proba(values), dtype=np.float64)
        if raw.shape != (values.shape[0], len(label_order)):
            raise ValueError(
                "classifier predict_proba output shape does not match label_order"
            )
        classes_value = getattr(model, "classes_", None)
        classes = (
            tuple(label_order)
            if classes_value is None
            else _model_class_order(classes_value)
        )
        if len(classes) != len(label_order) or set(classes) != set(label_order):
            raise ValueError(
                "classifier model classes do not match manifest label_order"
            )
        if not bool(np.all(np.isfinite(raw))):
            raise ValueError("classifier probabilities must be finite")
        if bool(np.any(raw < 0.0)) or bool(np.any(raw > 1.0)):
            raise ValueError("classifier probabilities must be between 0 and 1")
        if not bool(
            np.allclose(
                raw.sum(axis=1),
                np.ones(values.shape[0]),
                rtol=1e-6,
                atol=1e-6,
            )
        ):
            raise ValueError("classifier probabilities must sum to 1")
        column_by_label = {label: index for index, label in enumerate(classes)}
        return [
            {
                label: float(raw[row_index, column_by_label[label]])
                for label in label_order
            }
            for row_index in range(raw.shape[0])
        ]

    predict = getattr(model, "predict", None)
    if not callable(predict):
        raise ValueError("Classifier model must implement predict_proba() or predict()")
    predictions = np.asarray(predict(values), dtype=object)
    if predictions.shape != (values.shape[0],):
        raise ValueError("classifier predict output shape does not match input rows")
    result: list[dict[str, float]] = []
    for raw_label in predictions:
        predicted = str(raw_label)
        if predicted not in label_order:
            raise ValueError(f"classifier predicted unknown label: {predicted!r}")
        result.append(
            {label: 1.0 if label == predicted else 0.0 for label in label_order}
        )
    return result


def _score_bucket_from_score(score: float) -> str:
    value = float(score)
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError("classifier score must be between 0 and 1")
    if value >= 0.7:
        return "high"
    if value >= 0.3:
        return "medium"
    return "low"


def _argmax_with_tiebreak(
    probabilities: Mapping[str, float],
    manifest_label_order: Sequence[str],
) -> str:
    labels = tuple(manifest_label_order)
    if not labels or len(set(labels)) != len(labels):
        raise ValueError("manifest_label_order must contain unique labels")
    if set(probabilities) != set(labels):
        raise ValueError("probability labels must exactly match manifest_label_order")
    values: dict[str, float] = {}
    for label in labels:
        raw = probabilities[label]
        if isinstance(raw, bool):
            raise ValueError("classifier probabilities must be finite numbers")
        value = float(raw)
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("classifier probabilities must be between 0 and 1")
        values[label] = value
    if not math.isclose(
        sum(values.values()),
        1.0,
        rel_tol=1e-6,
        abs_tol=1e-6,
    ):
        raise ValueError("classifier probabilities must sum to 1")
    maximum = max(values.values())
    return next(label for label in labels if values[label] == maximum)


def _classifier_key_from_metadata_or_slug(
    metadata_path: Path,
    artifact_slug: str,
) -> str:
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
        if isinstance(metadata, dict):
            classifier_key = str(metadata.get("classifier_key") or "").strip()
            if classifier_key:
                return classifier_key
    return artifact_slug.strip().replace("-", "_")


def _promoted_classifier_payload(
    summary: ClassifierManifestSummary,
    *,
    model_path_exists: bool,
    artifact_error: str | None = None,
) -> dict[str, object]:
    payload = {
        "classifier_key": summary.classifier_key,
        "name": str(
            summary.profile_name or summary.classifier_key.replace("_", " ").title()
        ),
        "artifact_prefix": (summary.artifact_prefix or summary.model_path.parent.name),
        "positive_label": summary.positive_label,
        "label_order": list(summary.label_order),
        "feature_set": summary.feature_set,
        "feature_count": summary.feature_count,
        "feature_names": list(summary.feature_names),
        "feature_manifest_hash": summary.feature_manifest_hash,
        "model_path": str(summary.model_path),
        "metadata_path": (
            str(summary.metadata_path)
            if summary.metadata_path is not None and summary.metadata_path.exists()
            else None
        ),
        **classifier_manifest_api_fields(summary),
    }
    discovery_errors: list[str] = []
    if not model_path_exists:
        discovery_errors.append("model.joblib is missing")
    if artifact_error is not None:
        discovery_errors.append(artifact_error)
    if discovery_errors:
        payload["manifest_status"] = "invalid"
        manifest_errors = payload["manifest_errors"]
        if not isinstance(manifest_errors, list):
            raise RuntimeError("classifier manifest errors payload is invalid")
        payload["manifest_errors"] = [
            *manifest_errors,
            *discovery_errors,
        ]
        payload["is_scoring_compatible"] = False
        payload["production_status"] = "invalid"
    return payload
