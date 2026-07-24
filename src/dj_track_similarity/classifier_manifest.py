from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

from .analysis_contracts import ContractIdentity
from .analysis_models import (
    AnalysisOutput,
    classifier_required_outputs_hash,
    validate_production_contract,
)


CLASSIFIER_MANIFEST_VERSION = 2
CLASSIFIER_SUPPORTED_MANIFEST_VERSIONS = (CLASSIFIER_MANIFEST_VERSION,)
CLASSIFIER_SUPPORTED_INPUTS = ("sonara", "mert", "maest", "clap")
CLASSIFIER_SCORE_SEMANTICS = "positive_label_probability"
COMPATIBLE_MANIFEST_STATUSES = {"valid"}
CLASSIFIER_PUBLICATION_POINTER_VERSION = 1
CLASSIFIER_PUBLICATION_POINTER_NAME = "current.json"
CLASSIFIER_PUBLICATION_GENERATIONS_DIR = "generations"
CLASSIFIER_HYBRID_SIGNAL_ROLES = (
    "preference_boost",
    "preference_penalty",
    "risk_penalty",
    "context_modifier",
)
CLASSIFIER_HYBRID_SIGNAL_AXES = (
    "groove",
    "density",
    "texture",
    "mood",
    "tonal",
    "vocalness",
    "energy_flow",
    "novelty",
)
CLASSIFIER_HYBRID_SIGNAL_MISSING_POLICIES = ("neutral",)

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_GENERATION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_OUTPUT_KIND_BY_FEATURE_SOURCE = {
    "sonara": "core",
    "mert": "embedding",
    "maest": "embedding",
    "clap": "embedding",
}


class ManifestVersionError(ValueError):
    """Signal that a classifier artifact requires re-training and re-promotion."""

    status: str = "unsupported"


@dataclass(frozen=True)
class ClassifierArtifactPaths:
    model_path: Path
    metadata_path: Path
    pointer_path: Path | None = None
    generation_id: str | None = None


@dataclass(frozen=True)
class ClassifierManifestSummary:
    classifier_key: str
    metadata_path: Path | None
    model_path: Path
    status: str
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    profile_name: str | None = None
    profile_type: str | None = None
    artifact_prefix: str | None = None
    feature_set: str | None = None
    feature_names: tuple[str, ...] = ()
    feature_count: int | None = None
    feature_manifest_hash: str | None = None
    required_outputs: tuple[AnalysisOutput, ...] = ()
    label_order: tuple[str, ...] = ()
    positive_label: str | None = None
    negative_label: str | None = None
    trained_label_counts: dict[str, int] | None = None
    manifest_version: int | None = None
    model_id: str | None = None
    artifact_hash: str | None = None
    promoted_at: str | None = None
    score_semantics: str = CLASSIFIER_SCORE_SEMANTICS
    calibration_status: str = "uncalibrated"
    calibration: dict[str, Any] | None = None
    hybrid_signal: dict[str, Any] | None = None
    hybrid_signal_source: str | None = None

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
        """Analysis families in the manifest's authoritative source order."""

        return tuple(
            output.contract.analysis_family for output in self.required_outputs
        )

    @property
    def uses_sonara(self) -> bool:
        return any(source == "sonara" for source in self.required_inputs)

    @property
    def required_outputs_hash(self) -> str | None:
        if not self.required_outputs:
            return None
        return classifier_required_outputs_hash(self.required_outputs)

    @property
    def sonara_release_hash(self) -> str | None:
        releases = {
            output.contract.release_hash
            for output in self.required_outputs
            if output.contract.analysis_family == "sonara"
        }
        releases.discard(None)
        if not releases:
            return None
        if len(releases) != 1:
            return None
        return next(iter(releases))

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
            "profile_type": self.profile_type,
            "artifact_prefix": self.artifact_prefix,
            "feature_set": self.feature_set,
            "feature_names": list(self.feature_names),
            "feature_count": self.feature_count,
            "feature_manifest_hash": self.feature_manifest_hash,
            "required_outputs": _required_outputs_api_payload(self.required_outputs),
            "required_outputs_hash": self.required_outputs_hash,
            "label_order": list(self.label_order),
            "positive_label": self.positive_label,
            "negative_label": self.negative_label,
            "trained_label_counts": dict(self.trained_label_counts or {}),
            "manifest_version": self.manifest_version,
            "model_id": self.model_id,
            "artifact_hash": self.artifact_hash,
            "promoted_at": self.promoted_at,
            "score_semantics": self.score_semantics,
            "calibration_status": self.calibration_status,
            "production_status": self.production_status,
            "calibration": dict(self.calibration or {}),
            "has_calibrated_probability": self.has_calibrated_probability,
            "required_inputs": list(self.required_inputs),
            "uses_sonara": self.uses_sonara,
            "sonara_release_hash": self.sonara_release_hash,
            **classifier_hybrid_signal_api_fields(self),
        }


def resolve_classifier_artifact_paths(
    model_path: str | Path,
    *,
    metadata_path: str | Path | None = None,
) -> ClassifierArtifactPaths:
    """Resolve an immutable promoted generation without a mixed-pair fallback."""

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

    pointer_path = selected_model.parent / CLASSIFIER_PUBLICATION_POINTER_NAME
    if not pointer_path.exists():
        return ClassifierArtifactPaths(
            model_path=selected_model,
            metadata_path=selected_model.with_name("model.json"),
        )

    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Classifier publication pointer is unreadable: {pointer_path}"
        ) from error
    if not isinstance(pointer, Mapping):
        raise ValueError("Classifier publication pointer must contain an object")
    if pointer.get("publication_version") != CLASSIFIER_PUBLICATION_POINTER_VERSION:
        raise ValueError("Classifier publication pointer version is unsupported")

    generation_id = pointer.get("generation_id")
    if (
        not isinstance(generation_id, str)
        or _GENERATION_ID_RE.fullmatch(generation_id) is None
        or generation_id in {".", ".."}
    ):
        raise ValueError("Classifier publication pointer generation_id is invalid")
    artifact_hash = pointer.get("artifact_hash")
    manifest_hash = pointer.get("manifest_hash")
    if (
        not isinstance(artifact_hash, str)
        or _SHA256_RE.fullmatch(artifact_hash) is None
    ):
        raise ValueError("Classifier publication pointer artifact_hash is invalid")
    if (
        not isinstance(manifest_hash, str)
        or _SHA256_RE.fullmatch(manifest_hash) is None
    ):
        raise ValueError("Classifier publication pointer manifest_hash is invalid")

    generation = (
        selected_model.parent / CLASSIFIER_PUBLICATION_GENERATIONS_DIR / generation_id
    )
    generation_model = generation / "model.joblib"
    generation_metadata = generation / "model.json"
    if not generation_model.is_file() or not generation_metadata.is_file():
        raise ValueError(
            f"Classifier publication generation is incomplete: {generation_id}"
        )
    try:
        manifest_bytes = generation_metadata.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"Classifier publication manifest is unreadable: {generation_metadata}"
        ) from error
    actual_manifest_hash = f"sha256:{hashlib.sha256(manifest_bytes).hexdigest()}"
    if actual_manifest_hash != manifest_hash:
        raise ValueError(
            "Classifier publication manifest SHA-256 does not match current.json"
        )
    if not isinstance(manifest, Mapping):
        raise ValueError("Classifier publication manifest must contain an object")
    if manifest.get("artifact_hash") != artifact_hash:
        raise ValueError(
            "Classifier publication artifact hash does not match current.json"
        )
    return ClassifierArtifactPaths(
        model_path=generation_model,
        metadata_path=generation_metadata,
        pointer_path=pointer_path,
        generation_id=generation_id,
    )


def classifier_feature_manifest_hash(feature_names: Iterable[str]) -> str:
    """Hash the canonical JSON representation of an ordered feature-name list."""

    if isinstance(feature_names, (str, bytes, bytearray)):
        raise TypeError("feature_names must be an iterable of feature-name strings")
    names = tuple(feature_names)
    if not names:
        raise ValueError("feature_names must not be empty")
    if any(not isinstance(name, str) or not name.strip() for name in names):
        raise ValueError("feature_names must contain only non-empty strings")
    if any(name != name.strip() for name in names):
        raise ValueError("feature_names must not contain surrounding whitespace")
    if len(set(names)) != len(names):
        raise ValueError("feature_names must not contain duplicates")
    payload = json.dumps(
        list(names),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return f"sha256:{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


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
    artifact_prefix = (
        resolved.pointer_path.parent.name
        if resolved.pointer_path is not None
        else clean_model_path.parent.name
    ) or None
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
    try:
        return _parse_manifest_payload(
            payload,
            clean_key,
            clean_model_path,
            clean_metadata_path,
            artifact_prefix,
        )
    except ManifestVersionError as error:
        raw_version = payload.get("manifest_version")
        manifest_version = (
            raw_version
            if isinstance(raw_version, int) and not isinstance(raw_version, bool)
            else None
        )
        return ClassifierManifestSummary(
            classifier_key=clean_key,
            metadata_path=clean_metadata_path,
            model_path=clean_model_path,
            status=error.status,
            errors=(str(error),),
            artifact_prefix=artifact_prefix,
            manifest_version=manifest_version,
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
        "manifest_version": summary.manifest_version,
        "model_id": summary.model_id,
        "artifact_hash": summary.artifact_hash,
        "promoted_at": summary.promoted_at,
        "feature_names": list(summary.feature_names),
        "feature_manifest_hash": summary.feature_manifest_hash,
        "required_outputs": _required_outputs_api_payload(summary.required_outputs),
        "required_outputs_hash": summary.required_outputs_hash,
        "score_semantics": summary.score_semantics,
        "calibration_status": summary.calibration_status,
        "production_status": summary.production_status,
        "calibration": dict(summary.calibration or {}),
        "has_calibrated_probability": summary.has_calibrated_probability,
        "required_inputs": list(summary.required_inputs),
        "uses_sonara": summary.uses_sonara,
        "sonara_release_hash": summary.sonara_release_hash,
        **classifier_hybrid_signal_api_fields(summary),
    }


def classifier_hybrid_signal_api_fields(
    summary: ClassifierManifestSummary,
) -> dict[str, object]:
    return {
        "hybrid_signal": (
            dict(summary.hybrid_signal) if summary.hybrid_signal is not None else None
        ),
        "hybrid_signal_source": summary.hybrid_signal_source,
    }


def _parse_manifest_payload(
    payload: Mapping[str, Any],
    expected_classifier_key: str,
    model_path: Path,
    metadata_path: Path,
    artifact_prefix: str | None,
) -> ClassifierManifestSummary:
    raw_version = payload.get("manifest_version")
    if (
        isinstance(raw_version, bool)
        or not isinstance(raw_version, int)
        or raw_version != CLASSIFIER_MANIFEST_VERSION
    ):
        if raw_version in (None, 1):
            raise ManifestVersionError(
                "Manifest version 1 or an unversioned manifest is no longer "
                "supported. Re-train and re-promote the classifier."
            )
        raise ManifestVersionError(
            f"Manifest version {raw_version!r} is not supported; expected "
            f"{CLASSIFIER_MANIFEST_VERSION}. Re-train and re-promote the classifier."
        )

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

    model_id = _required_text_field(payload.get("model_id"), "model_id", errors)
    artifact_hash = _required_sha256(
        payload.get("artifact_hash"),
        "artifact_hash",
        errors,
    )
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
    feature_manifest_hash = (
        classifier_feature_manifest_hash(feature_names) if feature_names else None
    )
    raw_feature_hash = payload.get("feature_manifest_hash")
    if raw_feature_hash is not None:
        declared_feature_hash = _required_sha256(
            raw_feature_hash,
            "feature_manifest_hash",
            errors,
        )
        if (
            declared_feature_hash is not None
            and feature_manifest_hash is not None
            and declared_feature_hash != feature_manifest_hash
        ):
            errors.append(
                "model.json feature_manifest_hash does not match the canonical "
                "ordered feature_names"
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
    required_outputs: tuple[AnalysisOutput, ...] = ()
    if not isinstance(production, Mapping):
        errors.append("model.json production must be an object")
    else:
        if "required_inputs" in production:
            errors.append(
                "model.json production.required_inputs is not supported; "
                "use production.required_outputs"
            )
        if "sonara_analysis_signature" in production:
            errors.append(
                "model.json production.sonara_analysis_signature is not supported; "
                "use the canonical SONARA contract in production.required_outputs"
            )
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
        required_outputs = _production_required_outputs(
            production.get("required_outputs"),
            errors,
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

    feature_sources = _feature_sources(feature_names, errors)
    _validate_required_output_order(
        feature_sources=feature_sources,
        required_outputs=required_outputs,
        errors=errors,
    )
    _validate_embedding_feature_indices(
        feature_names=feature_names,
        required_outputs=required_outputs,
        errors=errors,
    )

    trained_label_counts = _trained_label_counts(
        payload.get("trained_label_counts"),
        warnings,
    )
    hybrid_signal = _hybrid_signal(
        payload.get("hybrid_signal"),
        errors,
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
        profile_type=_optional_text(payload.get("profile_type")),
        artifact_prefix=artifact_prefix,
        feature_set=feature_set,
        feature_names=feature_names,
        feature_count=feature_count,
        feature_manifest_hash=feature_manifest_hash,
        required_outputs=required_outputs,
        label_order=label_order,
        positive_label=positive_label,
        negative_label=negative_label,
        trained_label_counts=trained_label_counts,
        manifest_version=raw_version,
        model_id=model_id,
        artifact_hash=artifact_hash,
        promoted_at=_optional_text(payload.get("promoted_at")),
        score_semantics=score_semantics,
        calibration_status=calibration_status,
        calibration=calibration_payload,
        hybrid_signal=hybrid_signal,
        hybrid_signal_source="manifest" if hybrid_signal is not None else None,
    )


def _production_required_outputs(
    value: object,
    errors: list[str],
) -> tuple[AnalysisOutput, ...]:
    if not isinstance(value, list) or not value:
        errors.append(
            "model.json production.required_outputs must be a non-empty ordered list"
        )
        return ()

    outputs: list[AnalysisOutput] = []
    for index, raw_output in enumerate(value):
        field_name = f"production.required_outputs[{index}]"
        if not isinstance(raw_output, Mapping):
            errors.append(f"model.json {field_name} must be an object")
            continue
        actual_keys = set(raw_output)
        expected_keys = {"contract_hash", "canonical_payload"}
        if actual_keys != expected_keys:
            missing = sorted(expected_keys - actual_keys)
            extra = sorted(actual_keys - expected_keys)
            errors.append(
                f"model.json {field_name} keys must be exactly "
                f"contract_hash and canonical_payload; missing={missing}, extra={extra}"
            )
            continue
        contract_hash = _required_sha256(
            raw_output.get("contract_hash"),
            f"{field_name}.contract_hash",
            errors,
        )
        canonical_payload = raw_output.get("canonical_payload")
        if not isinstance(canonical_payload, Mapping):
            errors.append(
                f"model.json {field_name}.canonical_payload must be an object"
            )
            continue
        try:
            canonical_json = json.dumps(
                dict(canonical_payload),
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            contract = ContractIdentity.from_canonical_payload_json(canonical_json)
            validate_production_contract(contract)
        except (TypeError, ValueError) as error:
            errors.append(
                f"model.json {field_name}.canonical_payload is not a valid "
                f"production contract: {error}"
            )
            continue
        if contract_hash is not None and contract_hash != contract.contract_hash:
            errors.append(
                f"model.json {field_name}.contract_hash does not match "
                "canonical_payload"
            )
            continue
        outputs.append(AnalysisOutput(contract))

    keys = [output.key for output in outputs]
    if len(keys) != len(set(keys)):
        errors.append(
            "model.json production.required_outputs must not repeat an output"
        )
    return tuple(outputs)


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
                f"{feature_name!r}; expected <sonara|mert|maest|clap>:<key>"
            )
            continue
        if source not in sources:
            sources.append(source)
    return tuple(sources)


def _validate_required_output_order(
    *,
    feature_sources: Sequence[str],
    required_outputs: Sequence[AnalysisOutput],
    errors: list[str],
) -> None:
    if not feature_sources or not required_outputs:
        return
    expected = tuple(
        (source, _OUTPUT_KIND_BY_FEATURE_SOURCE[source]) for source in feature_sources
    )
    actual = tuple(output.key for output in required_outputs)
    if actual != expected:
        errors.append(
            "model.json production.required_outputs must exactly follow the "
            "first-occurrence feature source order; "
            f"expected={list(expected)!r}, actual={list(actual)!r}"
        )


def _validate_embedding_feature_indices(
    *,
    feature_names: Sequence[str],
    required_outputs: Sequence[AnalysisOutput],
    errors: list[str],
) -> None:
    contracts = {
        output.contract.analysis_family: output.contract for output in required_outputs
    }
    for feature_name in feature_names:
        source, separator, key = feature_name.partition(":")
        if not separator or source == "sonara":
            continue
        contract = contracts.get(source)
        if contract is None:
            continue
        if not key.isdigit() or str(int(key)) != key:
            errors.append(
                f"model.json embedding feature {feature_name!r} must use a "
                "canonical non-negative integer index"
            )
            continue
        index = int(key)
        if contract.dim is None or index >= contract.dim:
            errors.append(
                f"model.json embedding feature {feature_name!r} is outside "
                f"the declared contract dimension {contract.dim!r}"
            )


def _required_outputs_api_payload(
    outputs: Sequence[AnalysisOutput],
) -> list[dict[str, object]]:
    return [
        {
            "contract_hash": output.contract_hash,
            "canonical_payload": output.contract.canonical_payload,
        }
        for output in outputs
    ]


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


def _hybrid_signal(
    value: object,
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        errors.append("model.json hybrid_signal must be an object")
        return None

    role = _optional_text(value.get("role"))
    axis = _optional_text(value.get("axis"))
    if role is None:
        errors.append("model.json hybrid_signal.role is required")
    elif role not in CLASSIFIER_HYBRID_SIGNAL_ROLES:
        errors.append(f"model.json hybrid_signal.role {role!r} is not supported")
    if axis is None:
        errors.append("model.json hybrid_signal.axis is required")
    elif axis not in CLASSIFIER_HYBRID_SIGNAL_AXES:
        errors.append(f"model.json hybrid_signal.axis {axis!r} is not supported")
    if (
        role is None
        or axis is None
        or role not in CLASSIFIER_HYBRID_SIGNAL_ROLES
        or axis not in CLASSIFIER_HYBRID_SIGNAL_AXES
    ):
        return None

    signal: dict[str, Any] = {"role": role, "axis": axis}
    for field_name in ("label", "description"):
        text = _optional_text(value.get(field_name))
        if text is not None:
            signal[field_name] = text

    if "enabled_by_default" in value:
        if isinstance(value.get("enabled_by_default"), bool):
            signal["enabled_by_default"] = bool(value["enabled_by_default"])
        else:
            warnings.append(
                "model.json hybrid_signal.enabled_by_default is not a boolean"
            )

    for field_name in ("default_preference", "default_risk_weight"):
        if field_name not in value:
            continue
        number = _optional_float(
            value.get(field_name),
            f"hybrid_signal.{field_name}",
            warnings,
        )
        if number is None:
            continue
        if field_name == "default_preference":
            signal[field_name] = max(-1.0, min(1.0, number))
        else:
            signal[field_name] = max(0.0, min(1.0, number))

    allowed_modes = _optional_string_list(
        value.get("allowed_modes"),
        "hybrid_signal.allowed_modes",
        warnings,
    )
    if allowed_modes is not None:
        signal["allowed_modes"] = allowed_modes

    policy = _optional_text(value.get("missing_score_policy"))
    if policy is not None:
        if policy not in CLASSIFIER_HYBRID_SIGNAL_MISSING_POLICIES:
            warnings.append(
                f"model.json hybrid_signal.missing_score_policy {policy!r} "
                "is not supported"
            )
        else:
            signal["missing_score_policy"] = policy

    return signal


def _optional_float(
    value: object,
    field_name: str,
    warnings: list[str],
) -> float | None:
    if value is None or isinstance(value, bool):
        warnings.append(f"model.json {field_name} must be a number")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        warnings.append(f"model.json {field_name} must be a number")
        return None
    if not math.isfinite(number):
        warnings.append(f"model.json {field_name} must be finite")
        return None
    return number


def _optional_string_list(
    value: object,
    field_name: str,
    warnings: list[str],
) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        warnings.append(f"model.json {field_name} must be a list")
        return None
    result: list[str] = []
    for item in value:
        text = _optional_text(item)
        if text is not None:
            result.append(text)
    return result
