from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from .analysis_models import current_embedding_spec


CLASSIFIER_SUPPORTED_INPUTS = ("sonara", "mert", "maest", "clap", "muq")
CLASSIFIER_SCORE_SEMANTICS = "positive_label_probability"
COMPATIBLE_MANIFEST_STATUSES = {"valid"}
MODEL_KIND_JOBLIB = "joblib"
MODEL_KIND_SONARA_GENRE = "sonara_genre"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_OUTPUT_KIND_BY_FEATURE_SOURCE = {
    "sonara": "core",
    "mert": "embedding",
    "maest": "embedding",
    "clap": "embedding",
    "muq": "embedding",
}


@dataclass(frozen=True)
class ClassifierArtifactPaths:
    model_path: Path
    metadata_path: Path


@dataclass(frozen=True)
class ClassifierManifestSummary:
    classifier_key: str
    metadata_path: Path | None
    model_path: Path
    status: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    profile_name: str | None = None
    profile_description: str | None = None
    profile_type: str | None = None
    artifact_prefix: str | None = None
    feature_set: str | None = None
    feature_names: tuple[str, ...] = ()
    feature_count: int | None = None
    label_order: tuple[str, ...] = ()
    positive_label: str | None = None
    negative_label: str | None = None
    trained_label_counts: dict[str, int] | None = None
    artifact_hash: str | None = None
    promoted_at: str | None = None
    score_semantics: str = CLASSIFIER_SCORE_SEMANTICS
    calibration_status: str = "uncalibrated"
    calibration: dict[str, Any] | None = None
    model_kind: str = MODEL_KIND_JOBLIB
    sonara_genre_model: str | None = None

    @property
    def is_scoring_compatible(self) -> bool:
        return self.status in COMPATIBLE_MANIFEST_STATUSES

    @property
    def has_calibrated_probability(self) -> bool:
        return self.calibration_status == "calibrated"

    @property
    def production_status(self) -> str:
        if self.status != "valid":
            return self.status
        if self.calibration_status == "calibrated":
            return "valid_calibrated"
        if self.calibration_status == "experimental":
            return "experimental"
        return "valid_uncalibrated"

    @property
    def required_inputs(self) -> tuple[str, ...]:
        """Analysis families in first-occurrence feature order."""

        result: list[str] = []
        for feature_name in self.feature_names:
            source, separator, _key = feature_name.partition(":")
            if separator and source not in result:
                result.append(source)
        return tuple(result)

    def to_api_dict(self) -> dict[str, object]:
        return {
            "classifier_key": self.classifier_key,
            "metadata_path": (
                str(self.metadata_path) if self.metadata_path is not None else None
            ),
            "model_path": str(self.model_path),
            "manifest_status": self.status,
            "manifest_errors": list(self.errors),
            "manifest_warnings": list(self.warnings),
            "is_scoring_compatible": self.is_scoring_compatible,
            "profile_name": self.profile_name,
            "profile_description": self.profile_description,
            "profile_type": self.profile_type,
            "artifact_prefix": self.artifact_prefix,
            "feature_set": self.feature_set,
            "feature_names": list(self.feature_names),
            "feature_count": self.feature_count,
            "label_order": list(self.label_order),
            "positive_label": self.positive_label,
            "negative_label": self.negative_label,
            "trained_label_counts": dict(self.trained_label_counts or {}),
            "artifact_hash": self.artifact_hash,
            "promoted_at": self.promoted_at,
            "score_semantics": self.score_semantics,
            "calibration_status": self.calibration_status,
            "production_status": self.production_status,
            "calibration": dict(self.calibration or {}),
            "has_calibrated_probability": self.has_calibrated_probability,
            "required_inputs": list(self.required_inputs),
            "model_kind": self.model_kind,
            "sonara_genre_model": self.sonara_genre_model,
        }


def resolve_classifier_artifact_paths(
    model_path: str | Path,
    *,
    metadata_path: str | Path | None = None,
) -> ClassifierArtifactPaths:
    """Resolve the root model and its matching root manifest."""

    selected_model = Path(model_path)
    if metadata_path is not None:
        return ClassifierArtifactPaths(
            model_path=selected_model,
            metadata_path=Path(metadata_path),
        )
    if selected_model.name != "model.joblib":
        return ClassifierArtifactPaths(
            model_path=selected_model,
            metadata_path=selected_model.with_name("model.json"),
        )

    return ClassifierArtifactPaths(
        model_path=selected_model,
        metadata_path=selected_model.with_name("model.json"),
    )


def load_classifier_manifest_summary(
    model_path: str | Path,
    *,
    expected_classifier_key: str,
    metadata_path: str | Path | None = None,
) -> ClassifierManifestSummary:
    clean_key = _clean_classifier_key(expected_classifier_key)
    resolved = resolve_classifier_artifact_paths(
        model_path,
        metadata_path=metadata_path,
    )
    clean_model_path = resolved.model_path
    clean_metadata_path = resolved.metadata_path
    artifact_prefix = clean_model_path.parent.name or None
    if not clean_metadata_path.exists():
        return _invalid_manifest(
            clean_key,
            clean_model_path,
            clean_metadata_path,
            artifact_prefix,
            "model.json manifest is required; re-train and re-promote this classifier",
        )

    try:
        payload = json.loads(clean_metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return _invalid_manifest(
            clean_key,
            clean_model_path,
            clean_metadata_path,
            artifact_prefix,
            f"model.json is invalid JSON: {error.msg}",
        )
    except OSError as error:
        return _invalid_manifest(
            clean_key,
            clean_model_path,
            clean_metadata_path,
            artifact_prefix,
            f"model.json could not be read: {error}",
        )
    if not isinstance(payload, Mapping):
        return _invalid_manifest(
            clean_key,
            clean_model_path,
            clean_metadata_path,
            artifact_prefix,
            "model.json must contain a JSON object",
        )
    return _parse_manifest_payload(
        payload,
        clean_key,
        clean_model_path,
        clean_metadata_path,
        artifact_prefix,
    )


def require_scoring_compatible_manifest(
    model_path: str | Path,
    *,
    expected_classifier_key: str,
    metadata_path: str | Path | None = None,
) -> ClassifierManifestSummary:
    summary = load_classifier_manifest_summary(
        model_path,
        expected_classifier_key=expected_classifier_key,
        metadata_path=metadata_path,
    )
    if summary.is_scoring_compatible:
        return summary
    raise ValueError(_manifest_error_text(summary))


def classifier_manifest_from_info(
    classifier_info: Mapping[str, object],
) -> ClassifierManifestSummary | None:
    classifier_key = str(classifier_info.get("classifier_key") or "").strip()
    model_path = classifier_info.get("model_path")
    if not classifier_key or model_path is None:
        return None
    metadata_path = classifier_info.get("metadata_path")
    return load_classifier_manifest_summary(
        str(model_path),
        expected_classifier_key=classifier_key,
        metadata_path=str(metadata_path) if metadata_path else None,
    )


def classifier_manifest_api_fields(
    summary: ClassifierManifestSummary,
) -> dict[str, object]:
    return {
        "manifest_status": summary.status,
        "manifest_errors": list(summary.errors),
        "manifest_warnings": list(summary.warnings),
        "is_scoring_compatible": summary.is_scoring_compatible,
        "profile_name": summary.profile_name,
        "profile_description": summary.profile_description,
        "profile_type": summary.profile_type,
        "negative_label": summary.negative_label,
        "trained_label_counts": dict(summary.trained_label_counts or {}),
        "artifact_hash": summary.artifact_hash,
        "promoted_at": summary.promoted_at,
        "feature_names": list(summary.feature_names),
        "score_semantics": summary.score_semantics,
        "calibration_status": summary.calibration_status,
        "production_status": summary.production_status,
        "calibration": dict(summary.calibration or {}),
        "has_calibrated_probability": summary.has_calibrated_probability,
        "required_inputs": list(summary.required_inputs),
        "model_kind": summary.model_kind,
        "sonara_genre_model": summary.sonara_genre_model,
    }


def _parse_manifest_payload(
    payload: Mapping[str, Any],
    expected_classifier_key: str,
    model_path: Path,
    metadata_path: Path,
    artifact_prefix: str | None,
) -> ClassifierManifestSummary:
    errors: list[str] = []
    warnings: list[str] = []
    classifier_key = _required_text_field(
        payload.get("classifier_key"),
        "classifier_key",
        errors,
    )
    if classifier_key is None:
        classifier_key = expected_classifier_key
    elif classifier_key != expected_classifier_key:
        errors.append(
            f"model.json classifier_key {classifier_key!r} does not match "
            f"requested classifier {expected_classifier_key!r}"
        )

    artifact_hash = _required_sha256(
        payload.get("artifact_hash"),
        "artifact_hash",
        errors,
    )
    publication_status = payload.get("publication_status")
    if publication_status is not None and publication_status != "ready":
        errors.append("model.json publication_status must be 'ready' before scoring")
    model_kind = _optional_text(payload.get("model_kind")) or MODEL_KIND_JOBLIB
    if model_kind not in {MODEL_KIND_JOBLIB, MODEL_KIND_SONARA_GENRE}:
        errors.append(f"Unsupported model_kind: {model_kind!r}")
    sonara_genre_model = _optional_text(payload.get("sonara_genre_model"))
    if model_kind == MODEL_KIND_SONARA_GENRE and sonara_genre_model is None:
        errors.append("model.json sonara_genre_model is required for sonara_genre")
    feature_set = _required_text_field(
        payload.get("feature_set"),
        "feature_set",
        errors,
    )
    feature_names = _strict_string_tuple(
        payload.get("feature_names"),
        "feature_names",
        errors,
    )
    feature_count = _required_positive_int(
        payload.get("feature_count"),
        "feature_count",
        errors,
    )
    if (
        feature_count is not None
        and feature_names
        and feature_count != len(feature_names)
    ):
        errors.append(
            "model.json feature_count must exactly match the ordered feature_names"
        )
    label_order = _strict_string_tuple(
        payload.get("label_order"),
        "label_order",
        errors,
    )
    if label_order and len(label_order) < 2:
        errors.append("model.json label_order must contain at least two labels")
    positive_label = _required_text_field(
        payload.get("positive_label"),
        "positive_label",
        errors,
    )
    if positive_label is not None and label_order and positive_label not in label_order:
        errors.append("model.json positive_label must be present in label_order")
    negative_label = _optional_text(payload.get("negative_label"))
    if negative_label is not None and label_order and negative_label not in label_order:
        errors.append("model.json negative_label must be present in label_order")
    if (
        negative_label is not None
        and positive_label is not None
        and negative_label == positive_label
    ):
        errors.append("model.json negative_label must differ from positive_label")

    production = payload.get("production")
    score_semantics = CLASSIFIER_SCORE_SEMANTICS
    calibration_status = "uncalibrated"
    calibration_payload: dict[str, Any] | None = None
    if not isinstance(production, Mapping):
        errors.append("model.json production must be an object")
    else:
        score_semantics_value = _required_text_field(
            production.get("score_semantics"),
            "production.score_semantics",
            errors,
        )
        if score_semantics_value is not None:
            score_semantics = score_semantics_value
            if score_semantics != CLASSIFIER_SCORE_SEMANTICS:
                errors.append(
                    f"Unsupported classifier score semantics: {score_semantics!r}"
                )
        calibration = production.get("calibration")
        if calibration is None:
            warnings.append(
                "model.json production.calibration is missing; scores are not "
                "calibrated probabilities"
            )
        elif not isinstance(calibration, Mapping):
            errors.append("model.json production.calibration must be an object")
        else:
            calibration_status = (
                _optional_text(calibration.get("status")) or "uncalibrated"
            )
            calibration_payload = dict(calibration)

    if model_kind == MODEL_KIND_SONARA_GENRE:
        _validate_sonara_native_feature_names(feature_names, errors)
    else:
        _feature_sources(feature_names, errors)
        _validate_embedding_feature_indices(
            feature_names=feature_names,
            errors=errors,
        )

    trained_label_counts = _trained_label_counts(
        payload.get("trained_label_counts"),
        warnings,
    )
    status = "invalid" if errors else "valid"
    return ClassifierManifestSummary(
        classifier_key=classifier_key,
        metadata_path=metadata_path,
        model_path=model_path,
        status=status,
        errors=tuple(errors),
        warnings=tuple(warnings),
        profile_name=_optional_text(payload.get("profile_name")),
        profile_description=_optional_text(payload.get("profile_description")),
        profile_type=_optional_text(payload.get("profile_type")),
        artifact_prefix=artifact_prefix,
        feature_set=feature_set,
        feature_names=feature_names,
        feature_count=feature_count,
        label_order=label_order,
        positive_label=positive_label,
        negative_label=negative_label,
        trained_label_counts=trained_label_counts,
        artifact_hash=artifact_hash,
        promoted_at=_optional_text(payload.get("promoted_at")),
        score_semantics=score_semantics,
        calibration_status=calibration_status,
        calibration=calibration_payload,
        model_kind=model_kind,
        sonara_genre_model=sonara_genre_model,
    )


def _feature_sources(
    feature_names: Sequence[str],
    errors: list[str],
) -> tuple[str, ...]:
    sources: list[str] = []
    for feature_name in feature_names:
        source, separator, key = feature_name.partition(":")
        if (
            not separator
            or not source
            or not key
            or source not in CLASSIFIER_SUPPORTED_INPUTS
        ):
            errors.append(
                f"model.json feature_names contains unsupported feature "
                f"{feature_name!r}; expected "
                "<sonara|mert|maest|clap|muq>:<key>"
            )
            continue
        if source not in sources:
            sources.append(source)
    return tuple(sources)


def _validate_embedding_feature_indices(
    *,
    feature_names: Sequence[str],
    errors: list[str],
) -> None:
    for feature_name in feature_names:
        source, separator, key = feature_name.partition(":")
        if (
            not separator
            or source == "sonara"
            or source not in CLASSIFIER_SUPPORTED_INPUTS
        ):
            continue
        if not key.isdigit() or str(int(key)) != key:
            errors.append(
                f"model.json embedding feature {feature_name!r} must use a "
                "canonical non-negative integer index"
            )
            continue
        index = int(key)
        dimension = current_embedding_spec(source).dimension
        if index >= dimension:
            errors.append(
                f"model.json embedding feature {feature_name!r} is outside "
                f"the current {source} dimension {dimension}"
            )


def _validate_sonara_native_feature_names(
    feature_names: Sequence[str],
    errors: list[str],
) -> None:
    expected = tuple(f"sonara48d:{index}" for index in range(48))
    if tuple(feature_names) != expected:
        errors.append(
            "sonara_genre model.json feature_names must be canonical "
            "sonara48d:0 through sonara48d:47"
        )


def _invalid_manifest(
    classifier_key: str,
    model_path: Path,
    metadata_path: Path,
    artifact_prefix: str | None,
    error: str,
) -> ClassifierManifestSummary:
    return ClassifierManifestSummary(
        classifier_key=classifier_key,
        metadata_path=metadata_path,
        model_path=model_path,
        status="invalid",
        errors=(error,),
        artifact_prefix=artifact_prefix,
    )


def _manifest_error_text(summary: ClassifierManifestSummary) -> str:
    errors = "; ".join(summary.errors) if summary.errors else "unknown manifest error"
    return f"Classifier manifest is invalid for {summary.classifier_key!r}: {errors}"


def _clean_classifier_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Classifier key is required")
    return text


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _required_text_field(
    value: object,
    field_name: str,
    errors: list[str],
) -> str | None:
    text = _optional_text(value)
    if text is None or text != value:
        errors.append(
            f"model.json {field_name} must be a non-empty string without "
            "surrounding whitespace"
        )
        return None
    return text


def _strict_string_tuple(
    value: object,
    field_name: str,
    errors: list[str],
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        errors.append(f"model.json {field_name} must be a non-empty list")
        return ()
    cleaned: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            errors.append(
                f"model.json {field_name}[{index}] must be a non-empty string "
                "without surrounding whitespace"
            )
            continue
        cleaned.append(item)
    if len(cleaned) != len(set(cleaned)):
        errors.append(f"model.json {field_name} must not contain duplicates")
    return tuple(cleaned)


def _required_positive_int(
    value: object,
    field_name: str,
    errors: list[str],
) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        errors.append(f"model.json {field_name} must be a positive integer")
        return None
    return value


def _required_sha256(
    value: object,
    field_name: str,
    errors: list[str],
) -> str | None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        errors.append(
            f"model.json {field_name} must be a lowercase sha256:<64 hex> digest"
        )
        return None
    return value


def _trained_label_counts(
    value: object,
    warnings: list[str],
) -> dict[str, int] | None:
    if value is None:
        warnings.append(
            "model.json has no trained_label_counts; label coverage is unknown"
        )
        return None
    if not isinstance(value, Mapping):
        warnings.append(
            "model.json trained_label_counts is not an object; label coverage is unknown"
        )
        return None
    counts: dict[str, int] = {}
    for key, raw_count in value.items():
        label = _optional_text(key)
        if label is None:
            continue
        if (
            isinstance(raw_count, bool)
            or not isinstance(raw_count, int)
            or raw_count < 0
        ):
            warnings.append(
                f"model.json trained_label_counts[{label!r}] is not a "
                "non-negative integer"
            )
            continue
        counts[label] = raw_count
    return counts
