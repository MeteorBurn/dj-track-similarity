"""Strict SONARA runtime identity and immutable v7 output contracts.

The SONARA release hash is derived here from the actual loaded package and the
complete project-owned analysis profile.  Callers never provide a release hash.
Every Core or Artifacts writer consumes one of the four
:class:`~dj_track_similarity.analysis_contracts.ContractIdentity` objects
returned by :func:`sonara_runtime_contracts`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .analysis_contracts import FLOAT32_LE_ENCODING, ContractIdentity


SONARA_EXPECTED_VERSION = "0.3.1"
SONARA_EXPECTED_SCHEMA_VERSION = 5
SONARA_ANALYSIS_MODE = "playlist"
SONARA_SAMPLE_RATE = 22_050
SONARA_BPM_MIN = 70
SONARA_BPM_MAX = 180
SONARA_PROJECT_FEATURE_REVISION = 6
SONARA_DECODER_BACKEND = "sonara-symphonia"
SONARA_EXECUTION_PATH = "analyze_batch"
SONARA_ANALYSIS_HOP_SAMPLES = 512
SONARA_MODEL_NAME = "sonara-playlist"
SONARA_VOCALNESS_MODEL_SELECTOR = "bundled"
SONARA_UNIT_INTERVAL_CLAMP_POLICY = "finite-unit-interval-epsilon-clamp-v1"
SONARA_UNIT_INTERVAL_CLAMP_EPSILON = 0.001
SONARA_UNIT_INTERVAL_CLAMP_FIELDS = (
    "acousticness",
    "bpm_confidence",
    "danceability",
    "dissonance",
    "energy",
    "energy_curve[]",
    "grid_stability",
    "key_candidates[].score",
    "key_confidence",
    "mood_aggressive",
    "mood_happy",
    "mood_relaxed",
    "mood_sad",
    "segments[].energy",
    "spectral_flatness_mean",
    "valence",
    "vocalness",
    "zero_crossing_rate",
)

SONARA_EMBEDDING_VERSION = 2
SONARA_EMBEDDING_DIM = 48
SONARA_EMBEDDING_NORMALIZATION = "none"
SONARA_EMBEDDING_ENCODING = FLOAT32_LE_ENCODING

SONARA_FINGERPRINT_VERSION = 1
SONARA_FINGERPRINT_ENCODING = "uint32-le"
SONARA_FINGERPRINT_BYTE_ORDER = "little"

SONARA_OUTPUT_KINDS = ("core", "timeline", "embedding", "fingerprint")
DEFAULT_SONARA_OUTPUTS = ("core",)

SONARA_CORE_REQUESTED_FEATURES = (
    "bpm",
    "beats",
    "rms",
    "dynamic_range",
    "centroid",
    "zcr",
    "onset_density",
    "bandwidth",
    "rolloff",
    "flatness",
    "contrast",
    "mfcc",
    "chroma",
    "chords",
    "dissonance",
    "energy",
    "danceability",
    "key",
    "valence",
    "acousticness",
    "tempo_curve",
    "beatgrid",
    "structure",
    "loudness",
    "silence",
    "key_candidates",
    "vocalness",
    "mood",
)
SONARA_TIMELINE_REQUESTED_FEATURES = (
    "beats",
    "onsets",
    "chords",
    "tempo_curve",
    "beatgrid",
    "structure",
    "loudness",
)
SONARA_EMBEDDING_REQUESTED_FEATURES = ("embedding",)
SONARA_FINGERPRINT_REQUESTED_FEATURES = ("fingerprint",)

_SHA256_PREFIX = "sha256:"
_BUILD_FILE_SUFFIXES = frozenset({".dll", ".json", ".pyd", ".py", ".pyi", ".so"})


class SonaraRuntimeIdentityError(RuntimeError):
    """Raised when the loaded SONARA runtime does not match the pinned release."""


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SonaraRuntimeIdentityError(f"{field_name} must be a non-empty string")
    return value.strip()


def _sha256_identity(value: object, field_name: str) -> str:
    text = _required_text(value, field_name).lower()
    if not text.startswith(_SHA256_PREFIX) or len(text) != len(_SHA256_PREFIX) + 64:
        raise SonaraRuntimeIdentityError(
            f"{field_name} must use the sha256:<64 lowercase hex> format"
        )
    try:
        int(text[len(_SHA256_PREFIX) :], 16)
    except ValueError as error:
        raise SonaraRuntimeIdentityError(
            f"{field_name} must use the sha256:<64 lowercase hex> format"
        ) from error
    return text


def _feature_set(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    normalized = tuple(sorted({_required_text(value, field_name) for value in values}))
    if not normalized:
        raise SonaraRuntimeIdentityError(f"{field_name} must not be empty")
    return normalized


@dataclass(frozen=True)
class SonaraRuntimeIdentity:
    """Complete immutable identity of the SONARA runtime used for analysis."""

    package_version: str
    package_build_id: str
    schema_version: int
    mode: str
    sample_rate_hz: int
    bpm_min: int
    bpm_max: int
    project_feature_revision: int
    decoder_backend: str
    execution_path: str
    analysis_hop_samples: int
    vocalness_model_id: str
    vocalness_model_build_id: str
    embedding_version: int
    embedding_dim: int
    embedding_normalization: str
    embedding_encoding: str
    fingerprint_version: int
    fingerprint_encoding: str
    fingerprint_byte_order: str
    core_requested_features: tuple[str, ...]
    timeline_requested_features: tuple[str, ...]
    embedding_requested_features: tuple[str, ...]
    fingerprint_requested_features: tuple[str, ...]
    unit_interval_clamp_policy: str = SONARA_UNIT_INTERVAL_CLAMP_POLICY
    unit_interval_clamp_epsilon: float = SONARA_UNIT_INTERVAL_CLAMP_EPSILON
    unit_interval_clamp_fields: tuple[str, ...] = SONARA_UNIT_INTERVAL_CLAMP_FIELDS

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "package_version",
            _required_text(self.package_version, "package_version"),
        )
        object.__setattr__(
            self,
            "package_build_id",
            _sha256_identity(self.package_build_id, "package_build_id"),
        )
        object.__setattr__(self, "mode", _required_text(self.mode, "mode"))
        object.__setattr__(
            self,
            "decoder_backend",
            _required_text(self.decoder_backend, "decoder_backend"),
        )
        object.__setattr__(
            self,
            "execution_path",
            _required_text(self.execution_path, "execution_path"),
        )
        object.__setattr__(
            self,
            "vocalness_model_id",
            _required_text(self.vocalness_model_id, "vocalness_model_id"),
        )
        object.__setattr__(
            self,
            "vocalness_model_build_id",
            _sha256_identity(
                self.vocalness_model_build_id,
                "vocalness_model_build_id",
            ),
        )
        object.__setattr__(
            self,
            "embedding_normalization",
            _required_text(
                self.embedding_normalization,
                "embedding_normalization",
            ).lower(),
        )
        object.__setattr__(
            self,
            "embedding_encoding",
            _required_text(self.embedding_encoding, "embedding_encoding").lower(),
        )
        object.__setattr__(
            self,
            "fingerprint_encoding",
            _required_text(self.fingerprint_encoding, "fingerprint_encoding").lower(),
        )
        object.__setattr__(
            self,
            "fingerprint_byte_order",
            _required_text(
                self.fingerprint_byte_order,
                "fingerprint_byte_order",
            ).lower(),
        )
        object.__setattr__(
            self,
            "unit_interval_clamp_policy",
            _required_text(
                self.unit_interval_clamp_policy,
                "unit_interval_clamp_policy",
            ),
        )
        if (
            isinstance(self.unit_interval_clamp_epsilon, bool)
            or not isinstance(self.unit_interval_clamp_epsilon, (int, float))
            or not 0.0 < float(self.unit_interval_clamp_epsilon) < 0.5
        ):
            raise SonaraRuntimeIdentityError(
                "unit_interval_clamp_epsilon must be finite and between 0 and 0.5"
            )
        object.__setattr__(
            self,
            "unit_interval_clamp_epsilon",
            float(self.unit_interval_clamp_epsilon),
        )
        object.__setattr__(
            self,
            "unit_interval_clamp_fields",
            _feature_set(
                self.unit_interval_clamp_fields,
                "unit_interval_clamp_fields",
            ),
        )
        for field_name in (
            "schema_version",
            "sample_rate_hz",
            "bpm_min",
            "bpm_max",
            "project_feature_revision",
            "analysis_hop_samples",
            "embedding_version",
            "embedding_dim",
            "fingerprint_version",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise SonaraRuntimeIdentityError(
                    f"{field_name} must be a positive integer"
                )
        if self.bpm_min >= self.bpm_max:
            raise SonaraRuntimeIdentityError("bpm_min must be lower than bpm_max")
        for field_name in (
            "core_requested_features",
            "timeline_requested_features",
            "embedding_requested_features",
            "fingerprint_requested_features",
        ):
            object.__setattr__(
                self,
                field_name,
                _feature_set(getattr(self, field_name), field_name),
            )

    @property
    def requested_features_by_output(self) -> dict[str, tuple[str, ...]]:
        return {
            "core": self.core_requested_features,
            "timeline": self.timeline_requested_features,
            "embedding": self.embedding_requested_features,
            "fingerprint": self.fingerprint_requested_features,
        }

    @property
    def release_payload(self) -> dict[str, object]:
        """Canonical payload from which the family-wide release hash is derived."""

        return {
            "identity_factory": "sonara-runtime-v1",
            "model_name": SONARA_MODEL_NAME,
            "package_version": self.package_version,
            "package_build_id": self.package_build_id,
            "schema_version": self.schema_version,
            "mode": self.mode,
            "sample_rate_hz": self.sample_rate_hz,
            "bpm_min": self.bpm_min,
            "bpm_max": self.bpm_max,
            "project_feature_revision": self.project_feature_revision,
            "decoder_backend": self.decoder_backend,
            "execution_path": self.execution_path,
            "analysis_hop_samples": self.analysis_hop_samples,
            "unit_interval_clamp_policy": self.unit_interval_clamp_policy,
            "unit_interval_clamp_epsilon": self.unit_interval_clamp_epsilon,
            "unit_interval_clamp_fields": list(self.unit_interval_clamp_fields),
            "vocalness_model_selector": SONARA_VOCALNESS_MODEL_SELECTOR,
            "vocalness_model_id": self.vocalness_model_id,
            "vocalness_model_build_id": self.vocalness_model_build_id,
            "outputs": {
                "core": {
                    "requested_features": list(self.core_requested_features),
                },
                "timeline": {
                    "requested_features": list(self.timeline_requested_features),
                },
                "embedding": {
                    "requested_features": list(self.embedding_requested_features),
                    "version": self.embedding_version,
                    "dim": self.embedding_dim,
                    "normalization": self.embedding_normalization,
                    "encoding": self.embedding_encoding,
                },
                "fingerprint": {
                    "requested_features": list(self.fingerprint_requested_features),
                    "version": self.fingerprint_version,
                    "encoding": self.fingerprint_encoding,
                    "byte_order": self.fingerprint_byte_order,
                },
            },
        }

    @property
    def release_hash(self) -> str:
        payload_json = json.dumps(
            self.release_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return _SHA256_PREFIX + hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SonaraContractSet:
    """The four immutable output contracts for one derived SONARA release."""

    runtime: SonaraRuntimeIdentity
    release_hash: str
    core: ContractIdentity
    timeline: ContractIdentity
    embedding: ContractIdentity
    fingerprint: ContractIdentity

    def __post_init__(self) -> None:
        if self.release_hash != self.runtime.release_hash:
            raise SonaraRuntimeIdentityError(
                "release_hash does not match the SONARA runtime identity"
            )
        expected_kinds = SONARA_OUTPUT_KINDS
        identities = self.identities
        if tuple(identity.output_kind for identity in identities) != expected_kinds:
            raise SonaraRuntimeIdentityError(
                "SONARA contract set must contain core, timeline, embedding, fingerprint"
            )
        if any(
            identity.analysis_family != "sonara"
            or identity.release_hash != self.release_hash
            for identity in identities
        ):
            raise SonaraRuntimeIdentityError(
                "all SONARA contracts must belong to the derived release"
            )

    @property
    def identities(self) -> tuple[ContractIdentity, ...]:
        return self.core, self.timeline, self.embedding, self.fingerprint

    def for_output(self, output_kind: str) -> ContractIdentity:
        clean = _required_text(output_kind, "output_kind").lower()
        if clean not in SONARA_OUTPUT_KINDS:
            raise ValueError(f"unsupported SONARA output: {output_kind!r}")
        return getattr(self, clean)


def normalize_sonara_outputs(
    outputs: Sequence[str] | None,
) -> tuple[str, ...]:
    """Return canonical output kinds, always including required Core output."""

    if outputs is None:
        return DEFAULT_SONARA_OUTPUTS
    selected: set[str] = {"core"}
    saw_value = False
    for output in outputs:
        clean = _required_text(output, "SONARA output").lower()
        saw_value = True
        if clean not in SONARA_OUTPUT_KINDS:
            raise ValueError(
                f"unsupported SONARA output {output!r}; "
                f"expected one of {SONARA_OUTPUT_KINDS}"
            )
        selected.add(clean)
    if not saw_value:
        raise ValueError("SONARA outputs must not be empty")
    return tuple(output for output in SONARA_OUTPUT_KINDS if output in selected)


def sonara_requested_features(
    *,
    runtime: SonaraRuntimeIdentity,
) -> tuple[str, ...]:
    """Return the canonical native request for the exact four-output release."""

    requested = {
        feature
        for output in SONARA_OUTPUT_KINDS
        for feature in runtime.requested_features_by_output[output]
    }
    # SONARA canonicalizes ``provenance.requested_features`` by sorting and
    # deduplicating the explicit request.  Passing that same canonical order
    # keeps invocation, provenance validation, and contract identity aligned.
    return tuple(sorted(requested))


def resolve_sonara_runtime_identity(
    sonara_module: Any | None = None,
) -> SonaraRuntimeIdentity:
    """Inspect the loaded SONARA package and return its strict runtime identity."""

    sonara = sonara_module or _import_sonara()
    version = _required_text(getattr(sonara, "__version__", None), "sonara.__version__")
    if version != SONARA_EXPECTED_VERSION:
        raise SonaraRuntimeIdentityError(
            f"SONARA {SONARA_EXPECTED_VERSION} is required; loaded {version}"
        )
    similarity_version = getattr(sonara, "SIMILARITY_VERSION", None)
    if similarity_version != SONARA_EMBEDDING_VERSION:
        raise SonaraRuntimeIdentityError(
            "loaded SONARA similarity version does not match the pinned runtime"
        )

    package_build_id = _resolve_package_build_id(sonara)
    vocalness_model_id, vocalness_model_build_id = _resolve_vocalness_model(sonara)
    return SonaraRuntimeIdentity(
        package_version=version,
        package_build_id=package_build_id,
        schema_version=SONARA_EXPECTED_SCHEMA_VERSION,
        mode=SONARA_ANALYSIS_MODE,
        sample_rate_hz=SONARA_SAMPLE_RATE,
        bpm_min=SONARA_BPM_MIN,
        bpm_max=SONARA_BPM_MAX,
        project_feature_revision=SONARA_PROJECT_FEATURE_REVISION,
        decoder_backend=SONARA_DECODER_BACKEND,
        execution_path=SONARA_EXECUTION_PATH,
        analysis_hop_samples=SONARA_ANALYSIS_HOP_SAMPLES,
        vocalness_model_id=vocalness_model_id,
        vocalness_model_build_id=vocalness_model_build_id,
        embedding_version=SONARA_EMBEDDING_VERSION,
        embedding_dim=SONARA_EMBEDDING_DIM,
        embedding_normalization=SONARA_EMBEDDING_NORMALIZATION,
        embedding_encoding=SONARA_EMBEDDING_ENCODING,
        fingerprint_version=SONARA_FINGERPRINT_VERSION,
        fingerprint_encoding=SONARA_FINGERPRINT_ENCODING,
        fingerprint_byte_order=SONARA_FINGERPRINT_BYTE_ORDER,
        core_requested_features=SONARA_CORE_REQUESTED_FEATURES,
        timeline_requested_features=SONARA_TIMELINE_REQUESTED_FEATURES,
        embedding_requested_features=SONARA_EMBEDDING_REQUESTED_FEATURES,
        fingerprint_requested_features=SONARA_FINGERPRINT_REQUESTED_FEATURES,
    )


def build_sonara_contracts(
    runtime: SonaraRuntimeIdentity,
) -> SonaraContractSet:
    """Derive the release hash and all four contracts from one runtime identity."""

    release_hash = runtime.release_hash
    preprocessing = (
        f"{runtime.decoder_backend}/{runtime.execution_path}/"
        f"{runtime.mode}-sr{runtime.sample_rate_hz}-hop{runtime.analysis_hop_samples}/"
        f"{runtime.unit_interval_clamp_policy}-"
        f"epsilon{runtime.unit_interval_clamp_epsilon:g}"
    )

    common_parameters: dict[str, object] = {
        "identity_factory": "sonara-runtime-v1",
        "package_version": runtime.package_version,
        "package_build_id": runtime.package_build_id,
        "schema_version": runtime.schema_version,
        "mode": runtime.mode,
        "sample_rate_hz": runtime.sample_rate_hz,
        "bpm_min": runtime.bpm_min,
        "bpm_max": runtime.bpm_max,
        "project_feature_revision": runtime.project_feature_revision,
        "decoder_backend": runtime.decoder_backend,
        "execution_path": runtime.execution_path,
        "analysis_hop_samples": runtime.analysis_hop_samples,
        "unit_interval_clamp_policy": runtime.unit_interval_clamp_policy,
        "unit_interval_clamp_epsilon": runtime.unit_interval_clamp_epsilon,
        "unit_interval_clamp_fields": runtime.unit_interval_clamp_fields,
        "vocalness_model_selector": SONARA_VOCALNESS_MODEL_SELECTOR,
        "vocalness_model_id": runtime.vocalness_model_id,
        "vocalness_model_build_id": runtime.vocalness_model_build_id,
    }

    def identity(
        output_kind: str,
        *,
        requested_features: tuple[str, ...],
        dim: int | None = None,
        encoding: str | None = None,
        normalization: str | None = None,
        output_parameters: dict[str, object] | None = None,
    ) -> ContractIdentity:
        parameters = {
            **common_parameters,
            "requested_features": requested_features,
            **(output_parameters or {}),
        }
        return ContractIdentity(
            analysis_family="sonara",
            output_kind=output_kind,
            model_name=SONARA_MODEL_NAME,
            model_version=runtime.package_version,
            release_hash=release_hash,
            dim=dim,
            encoding=encoding,
            normalization=normalization,
            checkpoint_id=runtime.package_build_id,
            preprocessing=preprocessing,
            parameters=parameters,
        )

    core = identity(
        "core",
        requested_features=runtime.core_requested_features,
    )
    timeline = identity(
        "timeline",
        requested_features=runtime.timeline_requested_features,
    )
    embedding = identity(
        "embedding",
        requested_features=runtime.embedding_requested_features,
        dim=runtime.embedding_dim,
        encoding=runtime.embedding_encoding,
        normalization=runtime.embedding_normalization,
        output_parameters={
            "embedding_version": runtime.embedding_version,
            "embedding_dim": runtime.embedding_dim,
            "embedding_encoding": runtime.embedding_encoding,
            "embedding_normalization": runtime.embedding_normalization,
        },
    )
    fingerprint = identity(
        "fingerprint",
        requested_features=runtime.fingerprint_requested_features,
        output_parameters={
            "fingerprint_version": runtime.fingerprint_version,
            "fingerprint_encoding": runtime.fingerprint_encoding,
            "fingerprint_byte_order": runtime.fingerprint_byte_order,
        },
    )
    return SonaraContractSet(
        runtime=runtime,
        release_hash=release_hash,
        core=core,
        timeline=timeline,
        embedding=embedding,
        fingerprint=fingerprint,
    )


def sonara_runtime_contracts(
    sonara_module: Any | None = None,
) -> SonaraContractSet:
    """Resolve the loaded runtime and derive its four immutable contracts."""

    return build_sonara_contracts(resolve_sonara_runtime_identity(sonara_module))


def _resolve_package_build_id(sonara: Any) -> str:
    module_file = getattr(sonara, "__file__", None)
    if module_file:
        package_root = Path(str(module_file)).resolve(strict=True).parent
        files = sorted(
            (
                path
                for path in package_root.rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix.lower() in _BUILD_FILE_SUFFIXES
            ),
            key=lambda path: path.relative_to(package_root).as_posix(),
        )
        if not files:
            raise SonaraRuntimeIdentityError(
                "loaded SONARA package contains no hashable runtime files"
            )
        digest = hashlib.sha256()
        digest.update(b"sonara-runtime-build-v1\0")
        for path in files:
            relative = path.relative_to(package_root).as_posix().encode("utf-8")
            payload = path.read_bytes()
            digest.update(len(relative).to_bytes(4, "little"))
            digest.update(relative)
            digest.update(len(payload).to_bytes(8, "little"))
            digest.update(payload)
        return _SHA256_PREFIX + digest.hexdigest()

    # Explicit seam for injected fake SONARA modules.  Production modules have
    # __file__ and are always hashed from their actual loaded package contents.
    return _sha256_identity(
        getattr(sonara, "__sonara_build_id__", None),
        "sonara.__sonara_build_id__",
    )


def _resolve_vocalness_model(sonara: Any) -> tuple[str, str]:
    vocal_model = getattr(sonara, "vocal_model", None)
    bundled_path = getattr(vocal_model, "bundled_path", None)
    if callable(bundled_path):
        path = Path(str(bundled_path())).resolve(strict=True)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise SonaraRuntimeIdentityError(
                "bundled SONARA vocalness model is not valid UTF-8 JSON"
            ) from error
        if not isinstance(payload, dict):
            raise SonaraRuntimeIdentityError(
                "bundled SONARA vocalness model must be a JSON object"
            )
        model_id = _required_text(payload.get("id"), "vocalness model id")
        model_build_id = _SHA256_PREFIX + hashlib.sha256(path.read_bytes()).hexdigest()
        embedding_version = payload.get("embedding_version")
        if embedding_version != SONARA_EMBEDDING_VERSION:
            raise SonaraRuntimeIdentityError(
                "bundled vocalness model has the wrong embedding version"
            )
        return model_id, model_build_id

    return (
        _required_text(
            getattr(sonara, "__sonara_vocalness_model_id__", None),
            "sonara.__sonara_vocalness_model_id__",
        ),
        _sha256_identity(
            getattr(sonara, "__sonara_vocalness_model_build_id__", None),
            "sonara.__sonara_vocalness_model_build_id__",
        ),
    )


def _import_sonara() -> Any:
    try:
        import sonara
    except ImportError as error:
        raise RuntimeError(
            'sonara is not installed. Install it with: python -m pip install -e ".[sonara,dev]"'
        ) from error
    return sonara
