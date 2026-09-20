"""Typed analysis repository records.

The models in this module deliberately carry the complete library track
identity. A numeric ``track_id`` alone is not a safe write target because it
does not distinguish another library catalog, a replaced track UUID, or a
newer content generation.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal

import numpy as np

from .analysis.sonara_runtime import SONARA_UNIT_INTERVAL_EPSILON
from .db.ddl import (
    FLOAT32_LE,
    FLOAT32_LE_BYTES,
    ClassifierScoreRecord,
    SonaraRow,
)
from .scalars import (
    finite_number,
    positive_int,
)

OUTPUT_KINDS_BY_FAMILY: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        "sonara": frozenset({"core", "embedding", "fingerprint", "timeline"}),
        "maest": frozenset({"analysis", "embedding"}),
        "mert_v2": frozenset({"embedding"}),
        "muq": frozenset({"embedding"}),
        "mulan": frozenset({"embedding"}),
        "clap": frozenset({"embedding"}),
    }
)

MAEST_MODEL_NAME = "discogs-maest-30s-pw-129e-519l"
MERT_V2_MODEL_NAME = "m-a-p/MERT-v2-FullSong"
MUQ_MODEL_NAME = "OpenMuQ/MuQ-large-msd-iter"
MULAN_MODEL_NAME = "OpenMuQ/MuQ-MuLan-large"
MULAN_TEXT_MODEL_NAME = "xlm-roberta-base"
CLAP_MODEL_NAME = "lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt"
CLAP_TEXT_MODEL_NAME = "roberta-base"

MAEST_MODEL_VERSION = "v0.0.0-beta"
MERT_V2_MODEL_REVISION = "d8ba1c745e733b3908ce6ad16ebeb17ac7600a42"
MUQ_MODEL_REVISION = "0562a57814f6f8bbd9fdea0a25921a2fce1a841a"
MULAN_MODEL_REVISION = "57b8af8e903a6fa28b6ba1d7a1578b4d68fcc918"
MULAN_TEXT_MODEL_REVISION = "e73636d4f797dec63c3081bb6ed5c7b0bb3f2089"
CLAP_MODEL_REVISION = "b3708341862f581175dba5c356a4ebf74a9b6651"
CLAP_TEXT_MODEL_REVISION = "e2da8e2f811d1448a5b465c236feacd80ffbac7b"

MAEST_CHECKPOINT_ID = (
    "sha256:d6044e642b6ae295ee1164cc52b33ac663e247f03b4b100a0af1a5edfab18cdb"
)
MERT_V2_CHECKPOINT_ID = (
    "sha256:e6dd2ab187d6dd62b6521cd7d8f932e237acf0c5757745a7232082e28391350d"
)
MUQ_CHECKPOINT_ID = (
    "sha256:273febab2be02872c37d2c37e48a9d6c52c1c9392f3eeeabd498efa281ccb7a6"
)
MULAN_CHECKPOINT_ID = (
    "sha256:5fe234bbc5f183a9f4275fb292f54a30cb3a8ce75f82f1a43410ee6044d71d59"
)
CLAP_CHECKPOINT_ID = (
    "sha256:fae3e9c087f2909c28a09dc31c8dfcdacbc42ba44c70e972b58c1bd1caf6dedd"
)

MERT_V2_SNAPSHOT_SHA256 = (
    (
        "config.json",
        "f2e194895f58be3ddba327255db129ff0e3bee550cc0ecf08e4d22d79ce3bca3",
    ),
    (
        "configuration_mert2.py",
        "77b53ec9d7ee31a599d744fb006e812c7eeaf7390deb46e2f460cf8c17b00bd6",
    ),
    (
        "modeling_mert2.py",
        "b1a3174e5649c4b26b0c90d8626f0adacfbbba111a58ed3bb72ad651945a2f5c",
    ),
    (
        "preprocessor_config.json",
        "fc7337f113b71062b8efd03f8a43a07aa769ce85c6a53fdc0b3bb90c299fe63f",
    ),
    ("model.safetensors", MERT_V2_CHECKPOINT_ID.removeprefix("sha256:")),
)
MUQ_SNAPSHOT_SHA256 = (
    (
        "config.json",
        "237335ee27d8fb951ce778701a12a79e06c51ae636dd786f97e45f51ce532543",
    ),
    ("model.safetensors", MUQ_CHECKPOINT_ID.removeprefix("sha256:")),
)
MULAN_SNAPSHOT_SHA256 = (
    (
        "config.json",
        "8fefc545ef87ecd9bcde7417dd03464370c48c321f36dcff20266a752079e468",
    ),
    ("model.safetensors", MULAN_CHECKPOINT_ID.removeprefix("sha256:")),
)
MULAN_TEXT_SNAPSHOT_SHA256 = (
    (
        "config.json",
        "d66ed8cd4f2a93b358c245e50736fa389ed4f35c0bae7aad0b32abb20c62b579",
    ),
    (
        "model.safetensors",
        "6fd4797bc397c3b8b55d6bb5740366b57e6a3ce91c04c77f22aafc0c128e6feb",
    ),
    (
        "sentencepiece.bpe.model",
        "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865",
    ),
    (
        "tokenizer.json",
        "a898ea75433890f6610f4e470b8ebeb0c21dce5c8dd61f892eb09eb5919d2e2c",
    ),
    (
        "tokenizer_config.json",
        "994f46754c5bf4014f1aa92d34b1374319c3a6b3f702105cd5b742beaecd18ce",
    ),
)
CLAP_TEXT_SNAPSHOT_SHA256 = (
    (
        "config.json",
        "ef0185e2aae6e06c5f105a285006952c340e20c7dbf43c86ec82601b13fc45e9",
    ),
    (
        "merges.txt",
        "1ce1664773c50f3e0cc8842619a93edc4624525b728b188a9e0be33b7726adc5",
    ),
    (
        "model.safetensors",
        "5bde1d28afb363d0103324efeb5afc8b2b397fe5e04beabb9b1ef355255ade81",
    ),
    (
        "tokenizer_config.json",
        "994f46754c5bf4014f1aa92d34b1374319c3a6b3f702105cd5b742beaecd18ce",
    ),
    (
        "tokenizer.json",
        "847bbeab6174d66a88898f729d52fa8d355fafe1bea101cf960dd404581df70e",
    ),
    (
        "vocab.json",
        "9e7f63c2d15d666b52e21d250d2e513b87c9b713cfa6987a82ed89e5e6e50655",
    ),
)

MAEST_PREPROCESSING = "shared-mono/maest-16khz-native-full-track"
MERT_V2_PREPROCESSING = "shared-mono/mert-v2-24khz-amplitude-preserved-360s-last-layer-frame-weighted"
MUQ_PREPROCESSING = "shared-mono/muq-24khz-float32-consecutive-windows"
MULAN_PREPROCESSING = "shared-mono/muq-mulan-24khz-float32-full-track"
CLAP_PREPROCESSING = "shared-mono/clap-48khz-native-full-signal"

MAEST_EMBEDDING_DIM = 768
MERT_V2_EMBEDDING_DIM = 1024
MUQ_EMBEDDING_DIM = 1024
MULAN_EMBEDDING_DIM = 512
CLAP_EMBEDDING_DIM = 512
SONARA_EMBEDDING_DIM = 48


EmbeddingNormalization = Literal["l2", "none"]


@dataclass(frozen=True, slots=True)
class EmbeddingFamilySpec:
    dimension: int
    normalization: EmbeddingNormalization


CURRENT_EMBEDDING_SPECS: Mapping[str, EmbeddingFamilySpec] = MappingProxyType(
    {
        "maest": EmbeddingFamilySpec(MAEST_EMBEDDING_DIM, "l2"),
        "mert_v2": EmbeddingFamilySpec(MERT_V2_EMBEDDING_DIM, "l2"),
        "muq": EmbeddingFamilySpec(MUQ_EMBEDDING_DIM, "l2"),
        "mulan": EmbeddingFamilySpec(MULAN_EMBEDDING_DIM, "l2"),
        "clap": EmbeddingFamilySpec(CLAP_EMBEDDING_DIM, "l2"),
        "sonara": EmbeddingFamilySpec(SONARA_EMBEDDING_DIM, "none"),
    }
)


def current_embedding_spec(family: str) -> EmbeddingFamilySpec:
    clean_family = _required_text(family, "family").lower()
    try:
        return CURRENT_EMBEDDING_SPECS[clean_family]
    except KeyError as error:
        raise ValueError(
            f"unsupported embedding family: {clean_family!r}"
        ) from error


_EMBEDDING_DIM_BY_FAMILY = {
    family: spec.dimension
    for family, spec in CURRENT_EMBEDDING_SPECS.items()
}


class StaleAnalysisTargetError(RuntimeError):
    """Raised when a write target no longer names the current track content."""


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _canonical_text(value: object, field_name: str) -> str:
    """Identity text: non-empty and already canonical, never normalized."""

    text = _required_text(value, field_name)
    if text != value:
        raise ValueError(f"{field_name} must not contain surrounding whitespace")
    return text


@dataclass(frozen=True)
class AnalysisTarget:
    catalog_uuid: str
    track_id: int
    track_uuid: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "catalog_uuid",
            _canonical_text(self.catalog_uuid, "catalog_uuid"),
        )
        object.__setattr__(
            self,
            "track_id",
            positive_int(self.track_id, "track_id"),
        )
        object.__setattr__(
            self,
            "track_uuid",
            _canonical_text(self.track_uuid, "track_uuid"),
        )


@dataclass(frozen=True, slots=True)
class AnalysisOutput:
    analysis_family: str
    output_kind: str

    def __post_init__(self) -> None:
        family = _required_text(self.analysis_family, "analysis_family").lower()
        kind = _required_text(self.output_kind, "output_kind").lower()
        supported_kinds = OUTPUT_KINDS_BY_FAMILY.get(family)
        if supported_kinds is None:
            raise ValueError(f"unsupported analysis_family: {family!r}")
        if kind not in supported_kinds:
            raise ValueError(
                f"unsupported output_kind {kind!r} "
                f"for analysis_family {family!r}"
            )
        object.__setattr__(self, "analysis_family", family)
        object.__setattr__(self, "output_kind", kind)

    @property
    def key(self) -> tuple[str, str]:
        return self.analysis_family, self.output_kind


@dataclass(frozen=True)
class AnalysisCandidate:
    target: AnalysisTarget
    file_path: str
    file_size_bytes: int
    file_modified_ns: int
    missing_outputs: tuple[AnalysisOutput, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "file_path",
            _required_text(self.file_path, "file_path"),
        )
        if (
            isinstance(self.file_size_bytes, bool)
            or not isinstance(self.file_size_bytes, int)
            or self.file_size_bytes < 0
        ):
            raise ValueError("file_size_bytes must be a non-negative integer")
        if (
            isinstance(self.file_modified_ns, bool)
            or not isinstance(self.file_modified_ns, int)
            or self.file_modified_ns < 0
        ):
            raise ValueError("file_modified_ns must be a non-negative integer")
        missing = tuple(self.missing_outputs)
        if not missing:
            raise ValueError("analysis candidate must have at least one missing output")
        object.__setattr__(self, "missing_outputs", missing)


def _validate_short_float_blob(blob: bytes, *, dim: int, field_name: str) -> None:
    if not isinstance(blob, bytes) or len(blob) != dim * FLOAT32_LE_BYTES:
        raise ValueError(f"{field_name} must contain exactly {dim} float32-le values")
    vector = np.frombuffer(blob, dtype=FLOAT32_LE)
    if vector.shape != (dim,) or not bool(np.all(np.isfinite(vector))):
        raise ValueError(f"{field_name} must contain only finite float32-le values")


def _readonly_float32_vector(
    value: Sequence[float] | np.ndarray,
    *,
    family: str,
) -> np.ndarray:
    spec = current_embedding_spec(family)
    expected_dim = spec.dimension
    vector = np.asarray(value, dtype=FLOAT32_LE)
    if vector.ndim != 1 or vector.shape != (expected_dim,):
        raise ValueError(
            f"embedding shape {vector.shape} does not match "
            f"{family} dimension {expected_dim}"
        )
    if not bool(np.all(np.isfinite(vector))):
        raise ValueError("embedding contains non-finite values")
    if spec.normalization == "l2":
        norm = float(np.linalg.norm(vector.astype(np.float64, copy=False)))
        if not math.isfinite(norm) or not np.isclose(
            norm,
            1.0,
            rtol=1e-4,
            atol=1e-5,
        ):
            raise ValueError("l2 embedding must be unit-normalized")
    result = np.ascontiguousarray(vector, dtype=FLOAT32_LE).copy()
    result.setflags(write=False)
    return result


@dataclass(frozen=True, slots=True)
class EmbeddingOutput:
    family: str
    vector: Sequence[float] | np.ndarray
    analyzed_at: str
    layer_vectors: tuple[np.ndarray, ...] | None = None

    def __post_init__(self) -> None:
        family = _required_text(self.family, "family").lower()
        if family not in _EMBEDDING_DIM_BY_FAMILY:
            raise ValueError(f"unsupported embedding family: {family!r}")
        object.__setattr__(self, "family", family)
        object.__setattr__(
            self,
            "analyzed_at",
            _required_text(self.analyzed_at, "analyzed_at"),
        )
        object.__setattr__(
            self,
            "vector",
            _readonly_float32_vector(self.vector, family=family),
        )
        if self.layer_vectors is not None:
            if family != "mert_v2" or len(self.layer_vectors) != 24:
                raise ValueError("layer_vectors requires all 24 MERT-v2 layers in order")
            layers = tuple(
                _readonly_float32_vector(vector, family=family)
                for vector in self.layer_vectors
            )
            if not np.array_equal(layers[-1], self.vector):
                raise ValueError("MERT-v2 layer 24 must equal the primary embedding")
            object.__setattr__(self, "layer_vectors", layers)


@dataclass(frozen=True, slots=True)
class FingerprintOutput:
    """One versioned SONARA acoustic fingerprint in native base64 form."""

    value: str
    version: int
    analyzed_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValueError("fingerprint.value must be a base64 string")
        try:
            decoded = base64.b64decode(self.value, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("fingerprint.value must be valid base64") from error
        if len(decoded) % 4:
            raise ValueError("fingerprint.value must encode whole uint32 values")
        if (
            isinstance(self.version, bool)
            or not isinstance(self.version, int)
            or self.version <= 0
        ):
            raise ValueError("fingerprint.version must be a positive integer")
        if not isinstance(self.analyzed_at, str) or not self.analyzed_at.strip():
            raise ValueError("fingerprint.analyzed_at must be a non-empty string")


SONARA_TIMELINE_KEYS = frozenset(
    {
        "beats",
        "onsets",
        "chord_events",
        "downbeats",
        "energy_curve",
        "energy_curve_hop_seconds",
        "loudness_curve",
        "segments",
        "tempo_curve",
    }
)


@dataclass(frozen=True, slots=True)
class TimelineOutput:
    """SONARA time-resolved structure of one track.

    ``beats``, ``onsets`` and ``downbeats`` are frame indices: seconds are
    ``frame * hop_length / sample_rate_hz``. The analyzer result is validated
    here before it is written; stored rows are only identity-checked for
    readiness until something reads them.
    """

    payload: Mapping[str, object]
    sample_rate_hz: int
    hop_length: int
    analyzed_at: str

    def __post_init__(self) -> None:
        positive_int(self.sample_rate_hz, "timeline.sample_rate_hz")
        positive_int(self.hop_length, "timeline.hop_length")
        object.__setattr__(
            self,
            "analyzed_at",
            _required_text(self.analyzed_at, "timeline.analyzed_at"),
        )
        object.__setattr__(
            self,
            "payload",
            MappingProxyType(_timeline_payload(self.payload)),
        )

    @property
    def payload_json(self) -> str:
        return json.dumps(
            dict(self.payload),
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )


def _timeline_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping) or set(payload) != SONARA_TIMELINE_KEYS:
        raise ValueError(
            "timeline must contain exactly: " + ", ".join(sorted(SONARA_TIMELINE_KEYS))
        )
    beats = _timeline_frames(payload["beats"], "timeline.beats")
    downbeats = _timeline_frames(payload["downbeats"], "timeline.downbeats")
    if not set(downbeats).issubset(beats):
        raise ValueError("timeline.downbeats must be a subset of timeline.beats")
    tempo_curve = [
        _timeline_number(value, f"timeline.tempo_curve[{index}]", positive=True)
        for index, value in enumerate(_timeline_sequence(payload["tempo_curve"], "timeline.tempo_curve"))
    ]
    if len(tempo_curve) != max(len(beats) - 1, 0):
        raise ValueError("timeline.tempo_curve length must equal max(len(beats) - 1, 0)")
    energy_curve = [
        sonara_unit_interval(value, f"timeline.energy_curve[{index}]")
        for index, value in enumerate(_timeline_sequence(payload["energy_curve"], "timeline.energy_curve"))
    ]
    if not energy_curve:
        raise ValueError("timeline.energy_curve must not be empty")
    segments = _timeline_spans(
        payload["segments"],
        "timeline.segments",
        extra_key="energy",
    )
    if not segments:
        raise ValueError("timeline.segments must not be empty")
    return {
        "beats": beats,
        "onsets": _timeline_frames(payload["onsets"], "timeline.onsets"),
        "chord_events": _timeline_spans(
            payload["chord_events"],
            "timeline.chord_events",
            extra_key="label",
        ),
        "downbeats": downbeats,
        "energy_curve": energy_curve,
        "energy_curve_hop_seconds": _timeline_number(
            payload["energy_curve_hop_seconds"],
            "timeline.energy_curve_hop_seconds",
            positive=True,
        ),
        "loudness_curve": [
            _timeline_number(value, f"timeline.loudness_curve[{index}]")
            for index, value in enumerate(_timeline_sequence(payload["loudness_curve"], "timeline.loudness_curve"))
        ],
        "segments": segments,
        "tempo_curve": tempo_curve,
    }


def _timeline_sequence(value: object, field_name: str) -> list[object]:
    if isinstance(value, np.ndarray):
        if value.ndim != 1:
            raise ValueError(f"{field_name} must be one-dimensional")
        return value.tolist()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a sequence")
    return list(value)


def _timeline_frames(value: object, field_name: str) -> list[int]:
    frames: list[int] = []
    for index, raw in enumerate(_timeline_sequence(value, field_name)):
        if isinstance(raw, bool) or not isinstance(raw, (int, np.integer)) or raw < 0:
            raise ValueError(f"{field_name}[{index}] must be a non-negative frame integer")
        if frames and int(raw) <= frames[-1]:
            raise ValueError(f"{field_name} must be strictly increasing")
        frames.append(int(raw))
    return frames


def _timeline_number(value: object, field_name: str, *, positive: bool = False) -> float:
    if not isinstance(value, (int, float, np.integer, np.floating)):
        raise ValueError(f"{field_name} must be a finite number")
    number = finite_number(value, field_name)
    if positive and number <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return number


def sonara_unit_interval(value: object, field_name: str) -> float:
    number = _timeline_number(value, field_name)
    # SONARA reports f32, so the tolerance boundary is compared in f32 too.
    if not (
        float(np.float32(-SONARA_UNIT_INTERVAL_EPSILON))
        <= number
        <= float(np.float32(1.0 + SONARA_UNIT_INTERVAL_EPSILON))
    ):
        raise ValueError(
            f"{field_name} is outside the unit interval by more than "
            f"the allowed epsilon {SONARA_UNIT_INTERVAL_EPSILON:g}"
        )
    return min(1.0, max(0.0, number))


def _timeline_spans(
    value: object,
    field_name: str,
    *,
    extra_key: Literal["energy", "label"],
) -> list[dict[str, object]]:
    spans: list[dict[str, object]] = []
    previous_end = 0.0
    for index, raw in enumerate(_timeline_sequence(value, field_name)):
        name = f"{field_name}[{index}]"
        if not isinstance(raw, Mapping) or set(raw) != {"start_sec", "end_sec", extra_key}:
            raise ValueError(f"{name} must contain exactly start_sec, end_sec and {extra_key}")
        start = _timeline_number(raw["start_sec"], f"{name}.start_sec")
        end = _timeline_number(raw["end_sec"], f"{name}.end_sec")
        if start < previous_end:
            raise ValueError(f"{field_name} must not overlap and must start at or after 0")
        if end < start or (extra_key == "energy" and end == start):
            raise ValueError(f"{name}.end_sec must follow start_sec")
        extra = (
            sonara_unit_interval(raw["energy"], f"{name}.energy")
            if extra_key == "energy"
            else _required_text(raw["label"], f"{name}.label")
        )
        spans.append({"start_sec": start, "end_sec": end, extra_key: extra})
        previous_end = end
    return spans


@dataclass(frozen=True)
class SonaraWrite:
    """One SONARA run for one track.

    Every output is required and written together, so a track never mixes
    outputs of different runs.
    """

    target: AnalysisTarget
    core: SonaraRow
    timeline: TimelineOutput
    embedding: EmbeddingOutput
    fingerprint: FingerprintOutput

    def __post_init__(self) -> None:
        if self.core.track_id != self.target.track_id:
            raise ValueError("SONARA Core track_id does not match target")
        _required_text(self.core.analyzed_at, "core.analyzed_at")
        _validate_short_float_blob(
            self.core.mfcc_mean_blob,
            dim=13,
            field_name="core.mfcc_mean_blob",
        )
        _validate_short_float_blob(
            self.core.chroma_mean_blob,
            dim=12,
            field_name="core.chroma_mean_blob",
        )
        _validate_short_float_blob(
            self.core.spectral_contrast_mean_blob,
            dim=7,
            field_name="core.spectral_contrast_mean_blob",
        )
        if not isinstance(self.timeline, TimelineOutput):
            raise TypeError("SONARA timeline output must be a TimelineOutput")
        if not isinstance(self.embedding, EmbeddingOutput):
            raise TypeError("SONARA embedding output must be an EmbeddingOutput")
        if self.embedding.family != "sonara":
            raise ValueError("SONARA embedding output must use family='sonara'")
        if not isinstance(self.fingerprint, FingerprintOutput):
            raise TypeError("SONARA fingerprint output must be a FingerprintOutput")

    @property
    def outputs(self) -> tuple[AnalysisOutput, ...]:
        return (
            AnalysisOutput("sonara", "core"),
            AnalysisOutput("sonara", "timeline"),
            AnalysisOutput("sonara", "embedding"),
            AnalysisOutput("sonara", "fingerprint"),
        )


@dataclass(frozen=True)
class MaestGenreScore:
    label: str
    score: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _required_text(self.label, "label"))
        score = finite_number(self.score, "score")
        if not 0.0 <= score <= 1.0:
            raise ValueError("score must be between 0 and 1")
        object.__setattr__(self, "score", score)


@dataclass(frozen=True)
class MaestWrite:
    target: AnalysisTarget
    genres: tuple[MaestGenreScore, ...]
    syncopated_rhythm: bool | None
    analyzed_at: str
    embedding: EmbeddingOutput | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "genres", tuple(self.genres))
        if self.syncopated_rhythm is not None and not isinstance(
            self.syncopated_rhythm,
            bool,
        ):
            raise ValueError("syncopated_rhythm must be bool or None")
        object.__setattr__(
            self,
            "analyzed_at",
            _required_text(self.analyzed_at, "analyzed_at"),
        )
        if self.embedding is not None and self.embedding.family != "maest":
            raise ValueError("embedding must use family='maest'")

    @property
    def outputs(self) -> tuple[AnalysisOutput, ...]:
        outputs = [AnalysisOutput("maest", "analysis")]
        if self.embedding is not None:
            outputs.append(AnalysisOutput("maest", "embedding"))
        return tuple(outputs)

    @property
    def genres_json(self) -> str:
        return json.dumps(
            [{"label": genre.label, "score": genre.score} for genre in self.genres],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )


@dataclass(frozen=True)
class EmbeddingWrite:
    target: AnalysisTarget
    output: EmbeddingOutput

    def __post_init__(self) -> None:
        if self.output.family not in {"mert_v2", "muq", "mulan", "clap"}:
            raise ValueError(
                "standalone embedding writes support only MERT-v2, MuQ, MuQ-MuLan, or CLAP"
            )


@dataclass(frozen=True)
class AnalysisWriteResult:
    target: AnalysisTarget
    written_outputs: tuple[AnalysisOutput, ...] = ()
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True)
class AnalysisVectorRow:
    target: AnalysisTarget
    output: AnalysisOutput
    vector: np.ndarray


@dataclass(frozen=True)
class SonaraFeatureRow:
    target: AnalysisTarget
    output: AnalysisOutput
    values: Mapping[str, object]


@dataclass(frozen=True)
class ClassifierSpecification:
    classifier_key: str
    feature_set: str
    feature_names: tuple[str, ...]
    required_outputs: tuple[AnalysisOutput, ...]
    label_order: tuple[str, ...]
    positive_label: str

    def __post_init__(self) -> None:
        for field_name in (
            "classifier_key",
            "feature_set",
            "positive_label",
        ):
            object.__setattr__(
                self,
                field_name,
                _required_text(getattr(self, field_name), field_name),
            )
        feature_names = tuple(
            _required_text(value, "feature_names[]") for value in self.feature_names
        )
        if not feature_names:
            raise ValueError("feature_names must not be empty")
        if len(set(feature_names)) != len(feature_names):
            raise ValueError("feature_names must not contain duplicates")
        object.__setattr__(self, "feature_names", feature_names)
        outputs = tuple(self.required_outputs)
        if not outputs:
            raise ValueError("required_outputs must not be empty")
        keys = [output.key for output in outputs]
        if len(set(keys)) != len(keys):
            raise ValueError(
                "required_outputs must contain at most one entry per output"
            )
        object.__setattr__(self, "required_outputs", outputs)
        labels = tuple(
            _required_text(value, "label_order[]") for value in self.label_order
        )
        if not labels:
            raise ValueError("label_order must not be empty")
        if len(set(labels)) != len(labels):
            raise ValueError("label_order must not contain duplicates")
        if self.positive_label not in labels:
            raise ValueError("positive_label must be present in label_order")
        object.__setattr__(self, "label_order", labels)

@dataclass(frozen=True)
class ClassifierCandidate:
    target: AnalysisTarget
    file_path: str
    file_size_bytes: int
    file_modified_ns: int


@dataclass(frozen=True)
class ClassifierFeatureRow:
    target: AnalysisTarget
    specification: ClassifierSpecification
    vector: np.ndarray


@dataclass(frozen=True)
class ClassifierScoreWrite:
    target: AnalysisTarget
    specification: ClassifierSpecification
    score: ClassifierScoreRecord

    def __post_init__(self) -> None:
        if not isinstance(self.specification, ClassifierSpecification):
            raise TypeError("specification must be a ClassifierSpecification")
        if self.score.track_id != self.target.track_id:
            raise ValueError("classifier score track_id does not match target")
        if self.score.track_uuid != self.target.track_uuid:
            raise ValueError("classifier score track_uuid does not match target")
        expected_identity = (
            self.specification.classifier_key,
            self.specification.feature_set,
            self.specification.positive_label,
        )
        score_identity = (
            self.score.classifier_key,
            self.score.feature_set,
            self.score.positive_label,
        )
        if score_identity != expected_identity:
            raise ValueError(
                "classifier score identity does not match its specification"
            )
        expected_feature_names_json = json.dumps(
            list(self.specification.feature_names),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if self.score.feature_names_json != expected_feature_names_json:
            raise ValueError(
                "classifier score feature_names_json does not match its specification"
            )


@dataclass(frozen=True)
class AnalysisResetResult:
    feature_rows_deleted: int = 0
    embedding_rows_deleted: int = 0
    classifier_rows_deleted: int = 0
