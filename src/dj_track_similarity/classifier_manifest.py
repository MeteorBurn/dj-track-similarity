from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Mapping


CLASSIFIER_MANIFEST_VERSION = 1
CLASSIFIER_REQUIRED_INPUTS = ("sonara", "mert", "maest")
CLASSIFIER_SCORE_SEMANTICS = "positive_label_probability"
COMPATIBLE_MANIFEST_STATUSES = {"valid", "legacy"}
CLASSIFIER_HYBRID_SIGNAL_ROLES = ("preference_boost", "preference_penalty", "risk_penalty", "context_modifier")
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
LEGACY_HYBRID_SIGNALS: dict[str, dict[str, object]] = {
    "voice_presence": {
        "role": "risk_penalty",
        "axis": "vocalness",
        "label": "Penalize vocal risk",
        "description": "Uses stored voice_presence classifier scores as a modest vocal-conflict risk signal. Missing scores stay neutral.",
        "default_risk_weight": 1.0,
        "allowed_modes": ["hybrid"],
        "missing_score_policy": "neutral",
    },
    "abstract_edge": {
        "role": "preference_boost",
        "axis": "novelty",
        "label": "Boost abstract edge",
        "description": "Uses stored abstract_edge classifier scores as a small leftfield preference boost. Missing scores stay neutral.",
        "default_preference": 0.6,
        "allowed_modes": ["hybrid"],
        "missing_score_policy": "neutral",
    },
    "break_energy": {
        "role": "preference_boost",
        "axis": "groove",
        "label": "Boost break energy",
        "description": "Uses stored break_energy classifier scores as a small groove/rhythm preference boost. Missing scores stay neutral.",
        "default_preference": 0.6,
        "allowed_modes": ["hybrid"],
        "missing_score_policy": "neutral",
    },
    "live_instrumentation": {
        "role": "preference_boost",
        "axis": "texture",
        "label": "Boost live instrumentation",
        "description": "Uses stored live_instrumentation classifier scores as a small organic-texture preference boost. Missing scores stay neutral.",
        "default_preference": 0.4,
        "allowed_modes": ["hybrid"],
        "missing_score_policy": "neutral",
    },
}


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
    feature_count: int | None = None
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
    required_inputs: tuple[str, ...] = CLASSIFIER_REQUIRED_INPUTS
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
        if self.status in {"invalid", "legacy"}:
            return self.status
        if self.calibration_status == "calibrated":
            return "valid_calibrated"
        if self.calibration_status == "experimental":
            return "experimental"
        return "valid_uncalibrated"

    def to_api_dict(self) -> dict[str, object]:
        return {
            "classifier_key": self.classifier_key,
            "metadata_path": str(self.metadata_path) if self.metadata_path is not None else None,
            "model_path": str(self.model_path),
            "manifest_status": self.status,
            "manifest_errors": list(self.errors),
            "manifest_warnings": list(self.warnings),
            "is_scoring_compatible": self.is_scoring_compatible,
            "profile_name": self.profile_name,
            "profile_type": self.profile_type,
            "artifact_prefix": self.artifact_prefix,
            "feature_set": self.feature_set,
            "feature_count": self.feature_count,
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
            **classifier_hybrid_signal_api_fields(self),
        }


def classifier_manifest_path(model_path: str | Path) -> Path:
    return Path(model_path).with_name("model.json")


def load_classifier_manifest_summary(
    model_path: str | Path,
    *,
    expected_classifier_key: str,
    metadata_path: str | Path | None = None,
) -> ClassifierManifestSummary:
    clean_key = _clean_classifier_key(expected_classifier_key)
    clean_model_path = Path(model_path)
    clean_metadata_path = Path(metadata_path) if metadata_path is not None else classifier_manifest_path(clean_model_path)
    artifact_prefix = clean_model_path.parent.name or None
    if not clean_metadata_path.exists():
        return ClassifierManifestSummary(
            classifier_key=clean_key,
            metadata_path=clean_metadata_path,
            model_path=clean_model_path,
            status="legacy",
            warnings=(
                "model.json manifest is missing; this legacy classifier can be scored, "
                "but scores are treated as uncalibrated until the profile is promoted again.",
            ),
            artifact_prefix=artifact_prefix,
        )

    try:
        payload = json.loads(clean_metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return _invalid_manifest(clean_key, clean_model_path, clean_metadata_path, artifact_prefix, f"model.json is invalid JSON: {error.msg}")
    except OSError as error:
        return _invalid_manifest(clean_key, clean_model_path, clean_metadata_path, artifact_prefix, f"model.json could not be read: {error}")
    if not isinstance(payload, Mapping):
        return _invalid_manifest(clean_key, clean_model_path, clean_metadata_path, artifact_prefix, "model.json must contain a JSON object")
    return _parse_manifest_payload(payload, clean_key, clean_model_path, clean_metadata_path, artifact_prefix)


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


def classifier_manifest_from_info(classifier_info: Mapping[str, object]) -> ClassifierManifestSummary | None:
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


def classifier_manifest_api_fields(summary: ClassifierManifestSummary) -> dict[str, object]:
    return {
        "manifest_status": summary.status,
        "manifest_errors": list(summary.errors),
        "manifest_warnings": list(summary.warnings),
        "is_scoring_compatible": summary.is_scoring_compatible,
        "manifest_version": summary.manifest_version,
        "model_id": summary.model_id,
        "artifact_hash": summary.artifact_hash,
        "promoted_at": summary.promoted_at,
        "score_semantics": summary.score_semantics,
        "calibration_status": summary.calibration_status,
        "production_status": summary.production_status,
        "calibration": dict(summary.calibration or {}),
        "has_calibrated_probability": summary.has_calibrated_probability,
        "required_inputs": list(summary.required_inputs),
        **classifier_hybrid_signal_api_fields(summary),
    }


def legacy_hybrid_signal_for_classifier(classifier_key: str) -> dict[str, object] | None:
    signal = LEGACY_HYBRID_SIGNALS.get(str(classifier_key).strip())
    return dict(signal) if signal is not None else None


def classifier_hybrid_signal_api_fields(summary: ClassifierManifestSummary) -> dict[str, object]:
    signal = summary.hybrid_signal
    source = summary.hybrid_signal_source
    if signal is None:
        signal = legacy_hybrid_signal_for_classifier(summary.classifier_key)
        source = "legacy_fallback" if signal is not None else None
    return {
        "hybrid_signal": dict(signal) if signal is not None else None,
        "hybrid_signal_source": source,
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
    classifier_key = _optional_text(payload.get("classifier_key"))
    if classifier_key is None:
        errors.append("model.json classifier_key is required")
        classifier_key = expected_classifier_key
    elif classifier_key != expected_classifier_key:
        errors.append(f"model.json classifier_key {classifier_key!r} does not match requested classifier {expected_classifier_key!r}")

    feature_set = _optional_text(payload.get("feature_set"))
    if feature_set is None:
        errors.append("model.json feature_set is required")
    elif feature_set != "combined":
        errors.append(f"model.json feature_set must be 'combined', got {feature_set!r}")

    label_order = _string_tuple(payload.get("label_order"), "label_order", errors)
    positive_label = _optional_text(payload.get("positive_label"))
    if positive_label is None:
        errors.append("model.json positive_label is required")
    elif label_order and positive_label not in label_order:
        errors.append("model.json positive_label must be present in label_order")

    feature_count = _optional_int(payload.get("feature_count"), "feature_count", errors)
    if feature_count is not None and feature_count <= 0:
        errors.append("model.json feature_count must be positive")

    trained_label_counts = _trained_label_counts(payload.get("trained_label_counts"), warnings)
    profile_name = _optional_text(payload.get("profile_name"))
    profile_type = _optional_text(payload.get("profile_type"))
    negative_label = _optional_text(payload.get("negative_label"))
    manifest_version = _optional_int(payload.get("manifest_version"), "manifest_version", errors)
    model_id = _optional_text(payload.get("model_id"))
    artifact_hash = _optional_text(payload.get("artifact_hash"))
    promoted_at = _optional_text(payload.get("promoted_at"))
    production = payload.get("production")
    score_semantics = CLASSIFIER_SCORE_SEMANTICS
    calibration_status = "uncalibrated"
    calibration_payload: dict[str, Any] | None = None
    required_inputs = CLASSIFIER_REQUIRED_INPUTS
    hybrid_signal = _hybrid_signal(payload.get("hybrid_signal"), errors, warnings)

    if manifest_version is None:
        warnings.append("model.json has no manifest_version; treating it as a legacy-compatible production manifest")
    elif manifest_version != CLASSIFIER_MANIFEST_VERSION:
        errors.append(f"model.json manifest_version {manifest_version!r} is not supported")

    if production is None:
        warnings.append("model.json has no production metadata; scores are not calibrated probabilities")
    elif not isinstance(production, Mapping):
        errors.append("model.json production metadata must be an object")
    else:
        score_semantics = _optional_text(production.get("score_semantics")) or CLASSIFIER_SCORE_SEMANTICS
        if score_semantics != CLASSIFIER_SCORE_SEMANTICS:
            errors.append(f"Unsupported classifier score semantics: {score_semantics!r}")
        required_inputs = _production_required_inputs(production.get("required_inputs"), errors)
        calibration = production.get("calibration")
        if calibration is None:
            warnings.append("model.json production.calibration is missing; scores are not calibrated probabilities")
        elif not isinstance(calibration, Mapping):
            errors.append("model.json production.calibration must be an object")
        else:
            calibration_status = _optional_text(calibration.get("status")) or "uncalibrated"
            calibration_payload = dict(calibration)

    status = "invalid" if errors else "valid"
    return ClassifierManifestSummary(
        classifier_key=classifier_key,
        metadata_path=metadata_path,
        model_path=model_path,
        status=status,
        errors=tuple(errors),
        warnings=tuple(warnings),
        profile_name=profile_name,
        profile_type=profile_type,
        artifact_prefix=artifact_prefix,
        feature_set=feature_set,
        feature_count=feature_count,
        label_order=label_order,
        positive_label=positive_label,
        negative_label=negative_label,
        trained_label_counts=trained_label_counts,
        manifest_version=manifest_version,
        model_id=model_id,
        artifact_hash=artifact_hash,
        promoted_at=promoted_at,
        score_semantics=score_semantics,
        calibration_status=calibration_status,
        calibration=calibration_payload,
        required_inputs=required_inputs,
        hybrid_signal=hybrid_signal,
        hybrid_signal_source="manifest" if hybrid_signal is not None else None,
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
    text = str(value).strip()
    return text or None


def _string_tuple(value: object, field_name: str, errors: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        errors.append(f"model.json {field_name} must be a non-empty list")
        return ()
    cleaned = tuple(text for item in value if (text := _optional_text(item)) is not None)
    if not cleaned:
        errors.append(f"model.json {field_name} must be a non-empty list")
    return cleaned


def _optional_int(value: object, field_name: str, errors: list[str]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        errors.append(f"model.json {field_name} must be an integer")
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        errors.append(f"model.json {field_name} must be an integer")
        return None


def _trained_label_counts(value: object, warnings: list[str]) -> dict[str, int] | None:
    if value is None:
        warnings.append("model.json has no trained_label_counts; label coverage is unknown")
        return None
    if not isinstance(value, Mapping):
        warnings.append("model.json trained_label_counts is not an object; label coverage is unknown")
        return None
    counts: dict[str, int] = {}
    for key, raw_count in value.items():
        label = _optional_text(key)
        if label is None:
            continue
        try:
            counts[label] = max(0, int(raw_count))
        except (TypeError, ValueError):
            warnings.append(f"model.json trained_label_counts[{label!r}] is not an integer")
    return counts


def _production_required_inputs(value: object, errors: list[str]) -> tuple[str, ...]:
    if value is None:
        return CLASSIFIER_REQUIRED_INPUTS
    if not isinstance(value, list):
        errors.append("model.json production.required_inputs must be a list")
        return CLASSIFIER_REQUIRED_INPUTS
    cleaned = tuple(text for item in value if (text := _optional_text(item)) is not None)
    unknown = [item for item in cleaned if item not in CLASSIFIER_REQUIRED_INPUTS]
    if unknown:
        errors.append(f"model.json production.required_inputs contains unsupported inputs: {', '.join(unknown)}")
    return cleaned or CLASSIFIER_REQUIRED_INPUTS


def _hybrid_signal(value: object, errors: list[str], warnings: list[str]) -> dict[str, Any] | None:
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
    if role is None or axis is None or role not in CLASSIFIER_HYBRID_SIGNAL_ROLES or axis not in CLASSIFIER_HYBRID_SIGNAL_AXES:
        return None

    signal: dict[str, Any] = {
        "role": role,
        "axis": axis,
    }
    for field_name in ("label", "description"):
        text = _optional_text(value.get(field_name))
        if text is not None:
            signal[field_name] = text

    if "enabled_by_default" in value:
        if isinstance(value.get("enabled_by_default"), bool):
            signal["enabled_by_default"] = bool(value["enabled_by_default"])
        else:
            warnings.append("model.json hybrid_signal.enabled_by_default is not a boolean")

    for field_name in ("default_preference", "default_risk_weight"):
        if field_name not in value:
            continue
        number = _optional_float(value.get(field_name), f"hybrid_signal.{field_name}", warnings)
        if number is None:
            continue
        if field_name == "default_preference":
            signal[field_name] = max(-1.0, min(1.0, number))
        else:
            signal[field_name] = max(0.0, min(1.0, number))

    allowed_modes = _optional_string_list(value.get("allowed_modes"), "hybrid_signal.allowed_modes", warnings)
    if allowed_modes is not None:
        signal["allowed_modes"] = allowed_modes

    policy = _optional_text(value.get("missing_score_policy"))
    if policy is not None:
        if policy not in CLASSIFIER_HYBRID_SIGNAL_MISSING_POLICIES:
            warnings.append(f"model.json hybrid_signal.missing_score_policy {policy!r} is not supported")
        else:
            signal["missing_score_policy"] = policy

    return signal


def _optional_float(value: object, field_name: str, warnings: list[str]) -> float | None:
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


def _optional_string_list(value: object, field_name: str, warnings: list[str]) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        warnings.append(f"model.json {field_name} must be a list")
        return None
    return [text for item in value if (text := _optional_text(item)) is not None]
