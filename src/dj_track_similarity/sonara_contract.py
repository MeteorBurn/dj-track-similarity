from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence


SONARA_ANALYSIS_SIGNATURE_KEY = "sonara_analysis_signature"
SONARA_EXPECTED_VERSION = "0.2.9"
SONARA_EXPECTED_SCHEMA_VERSION = 4
SONARA_ANALYSIS_MODE = "playlist"
SONARA_SAMPLE_RATE = 22_050
SONARA_BPM_MIN = 70
SONARA_BPM_MAX = 180
SONARA_PROJECT_FEATURE_REVISION = 3

_SIGNATURE_FIELDS = (
    "sonara_version",
    "schema_version",
    "mode",
    "sample_rate",
    "bpm_range",
    "requested_features",
    "project_feature_revision",
)


def build_sonara_analysis_signature(
    *,
    requested_features: Sequence[str] | None,
    provenance: Mapping[str, object] | None = None,
    sonara_version: str | None = None,
) -> dict[str, object]:
    """Build the deterministic project contract recorded with one SONARA result.

    Provenance wins for values reported by SONARA. Project-owned call settings remain explicit so
    changing the BPM range or feature extraction revision necessarily changes the signature.
    """
    source = provenance or {}
    version = _optional_text(source.get("package_version")) or _optional_text(source.get("sonara_version"))
    version = version or _optional_text(sonara_version) or "unknown"
    schema_version = _optional_int(source.get("schema_version"))
    mode = _optional_text(source.get("mode")) or SONARA_ANALYSIS_MODE
    sample_rate = _optional_int(source.get("sample_rate"))
    provenance_features = source.get("requested_features")
    effective_features = requested_features
    if effective_features is None and isinstance(provenance_features, (list, tuple)):
        effective_features = provenance_features
    payload: dict[str, object] = {
        "sonara_version": version,
        "schema_version": schema_version,
        "mode": mode,
        "sample_rate": sample_rate,
        "bpm_range": [SONARA_BPM_MIN, SONARA_BPM_MAX],
        "requested_features": _sorted_feature_profile(effective_features),
        "project_feature_revision": SONARA_PROJECT_FEATURE_REVISION,
    }
    payload["signature_id"] = sonara_analysis_signature_id(payload)
    return payload


def expected_sonara_analysis_signature(requested_features: Sequence[str] | None) -> dict[str, object]:
    return build_sonara_analysis_signature(
        requested_features=requested_features,
        provenance={
            "package_version": SONARA_EXPECTED_VERSION,
            "schema_version": SONARA_EXPECTED_SCHEMA_VERSION,
            "mode": SONARA_ANALYSIS_MODE,
            "sample_rate": SONARA_SAMPLE_RATE,
        },
    )


def sonara_analysis_signature_id(signature: Mapping[str, object]) -> str:
    canonical = {field: _canonical_signature_value(field, signature.get(field)) for field in _SIGNATURE_FIELDS}
    encoded = json.dumps(canonical, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def sonara_analysis_signature_errors(
    signature: object,
    *,
    require_current_contract: bool = True,
) -> tuple[str, ...]:
    if not isinstance(signature, Mapping):
        return ("SONARA analysis signature must be an object",)
    errors: list[str] = []
    version = _optional_text(signature.get("sonara_version"))
    schema_version = _optional_int(signature.get("schema_version"))
    mode = _optional_text(signature.get("mode"))
    sample_rate = _optional_int(signature.get("sample_rate"))
    bpm_range = _number_pair(signature.get("bpm_range"))
    requested_features = signature.get("requested_features")
    project_revision = _optional_int(signature.get("project_feature_revision"))
    signature_id = _optional_text(signature.get("signature_id"))

    if version is None:
        errors.append("sonara_version is required")
    if schema_version is None:
        errors.append("schema_version is required")
    if mode is None:
        errors.append("mode is required")
    if sample_rate is None:
        errors.append("sample_rate is required")
    if bpm_range is None:
        errors.append("bpm_range must contain two finite numbers")
    if not isinstance(requested_features, list) or any(not isinstance(item, str) for item in requested_features):
        errors.append("requested_features must be a list of strings")
    elif requested_features != sorted(set(requested_features)):
        errors.append("requested_features must be sorted and unique")
    if project_revision is None:
        errors.append("project_feature_revision is required")
    if signature_id is None:
        errors.append("signature_id is required")
    elif signature_id != sonara_analysis_signature_id(signature):
        errors.append("signature_id does not match the SONARA analysis contract")

    if require_current_contract:
        expected_values = {
            "sonara_version": SONARA_EXPECTED_VERSION,
            "schema_version": SONARA_EXPECTED_SCHEMA_VERSION,
            "mode": SONARA_ANALYSIS_MODE,
            "sample_rate": SONARA_SAMPLE_RATE,
            "bpm_range": (float(SONARA_BPM_MIN), float(SONARA_BPM_MAX)),
            "project_feature_revision": SONARA_PROJECT_FEATURE_REVISION,
        }
        actual_values = {
            "sonara_version": version,
            "schema_version": schema_version,
            "mode": mode,
            "sample_rate": sample_rate,
            "bpm_range": bpm_range,
            "project_feature_revision": project_revision,
        }
        for field, expected in expected_values.items():
            if actual_values[field] != expected:
                errors.append(f"{field} does not match the current project contract ({expected!r})")
    return tuple(errors)


def sonara_analysis_signatures_match(left: object, right: object) -> bool:
    if not isinstance(left, Mapping) or not isinstance(right, Mapping):
        return False
    if sonara_analysis_signature_errors(left, require_current_contract=False):
        return False
    if sonara_analysis_signature_errors(right, require_current_contract=False):
        return False
    return all(
        _canonical_signature_value(field, left.get(field)) == _canonical_signature_value(field, right.get(field))
        for field in _SIGNATURE_FIELDS
    )


def sonara_analysis_is_compatible(metadata: Mapping[str, object] | None, expected_signature: object) -> bool:
    if not isinstance(metadata, Mapping) or not isinstance(metadata.get("sonara_features"), Mapping):
        return False
    actual = metadata.get(SONARA_ANALYSIS_SIGNATURE_KEY)
    return not sonara_analysis_signature_errors(actual) and sonara_analysis_signatures_match(actual, expected_signature)


def sonara_analysis_is_current(metadata: Mapping[str, object] | None) -> bool:
    """Return whether stored SONARA data satisfies the current contract, for any valid profile."""

    if not isinstance(metadata, Mapping) or not isinstance(metadata.get("sonara_features"), Mapping):
        return False
    return not sonara_analysis_signature_errors(metadata.get(SONARA_ANALYSIS_SIGNATURE_KEY))


def sonara_analysis_json_is_current(metadata_json: object) -> int:
    """SQLite-safe wrapper for exposing the current-analysis contract in queries."""

    if not isinstance(metadata_json, (str, bytes, bytearray)):
        return 0
    try:
        metadata = json.loads(metadata_json)
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        return 0
    return int(sonara_analysis_is_current(metadata if isinstance(metadata, Mapping) else None))


def current_sonara_features(
    metadata: Mapping[str, object] | None,
    *,
    allow_unsigned: bool = False,
) -> Mapping[str, object] | None:
    """Return SONARA features only when persisted provenance satisfies the current contract.

    ``allow_unsigned`` is reserved for explicit in-memory mappings used by pure scoring helpers;
    database-backed :class:`Track` objects must always carry the persisted signature.
    """

    if not isinstance(metadata, Mapping):
        return None
    if SONARA_ANALYSIS_SIGNATURE_KEY in metadata:
        if not sonara_analysis_is_current(metadata):
            return None
    elif not allow_unsigned:
        return None
    features = metadata.get("sonara_features")
    return features if isinstance(features, Mapping) else None


def feature_set_uses_sonara(feature_set: object) -> bool:
    clean = str(feature_set or "").strip().lower()
    if clean == "combined":
        return True
    sources = {part.strip() for part in clean.split("+") if part.strip()}
    return any(source.startswith("sonara") for source in sources)


def _canonical_signature_value(field: str, value: object) -> object:
    if field in {"schema_version", "sample_rate", "project_feature_revision"}:
        return _optional_int(value)
    if field == "bpm_range":
        pair = _number_pair(value)
        return list(pair) if pair is not None else None
    if field == "requested_features":
        if not isinstance(value, (list, tuple)):
            return []
        return _sorted_feature_profile(value)
    return _optional_text(value)


def _sorted_feature_profile(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return sorted({text for item in value if (text := _optional_text(item)) is not None})


def _number_pair(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        pair = (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None
    return pair if all(math.isfinite(item) for item in pair) else None


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
