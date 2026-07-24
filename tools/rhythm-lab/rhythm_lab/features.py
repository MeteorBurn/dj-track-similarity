from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
import json
import math
from pathlib import Path

import numpy as np

from dj_track_similarity.analysis_contracts import ContractIdentity

from .lab_db import RhythmLabDatabase, TrackIdentity, track_identity
from .source_db import SONARA_CORE_OUTPUT, SourceDatabase, SourceTrack


SONARA_SOURCE_VARIANTS = ("sonara", "sonara2", "sonara2vocal")
EMBEDDING_FEATURE_SOURCES = ("mert", "maest", "clap")
BASE_FEATURE_SOURCES = ("sonara", *EMBEDDING_FEATURE_SOURCES)
SUPPORTED_FEATURE_SOURCES = (*SONARA_SOURCE_VARIANTS, *EMBEDDING_FEATURE_SOURCES)
FEATURE_SOURCE_ALIASES = {"sonara2": "sonara", "sonara2vocal": "sonara"}
FEATURE_SETS = ("sonara", "mert", "maest", "combined")
ABLATION_FEATURE_SETS = tuple(
    "combined" if sources == ("sonara", "mert", "maest") else "+".join(sources)
    for sonara_source in ("", *SONARA_SOURCE_VARIANTS)
    for size in range(0, len(EMBEDDING_FEATURE_SOURCES) + 1)
    for embedding_sources in combinations(EMBEDDING_FEATURE_SOURCES, size)
    if sonara_source or embedding_sources
    for sources in (((sonara_source,) if sonara_source else ()) + embedding_sources,)
)
SONARA_SCALAR_FIELDS = (
    "bpm",
    "onset_density",
    "n_beats",
    "rms_mean",
    "rms_max",
    "loudness_lufs",
    "dynamic_range_db",
    "spectral_centroid_mean",
    "zero_crossing_rate",
    "duration_sec",
    "energy",
    "danceability",
    "valence",
    "acousticness",
    "chord_change_rate",
    "dissonance",
    "spectral_bandwidth_mean",
    "spectral_rolloff_mean",
    "spectral_flatness_mean",
)
SONARA2_EXTRA_SCALAR_FIELDS = (
    "bpm_raw",
    "energy_level",
    "intro_end_sec",
    "outro_start_sec",
    "energy_curve_hop_sec",
    "true_peak_db",
    "replaygain_db",
    "loudness_momentary_max_db",
    "loudness_range_lu",
    "grid_offset_sec",
    "grid_stability",
    "leading_silence_sec",
    "trailing_silence_sec",
)
SONARA2_SCALAR_FIELDS = (*SONARA_SCALAR_FIELDS, *SONARA2_EXTRA_SCALAR_FIELDS)
SONARA2VOCAL_SCALAR_FIELDS = (*SONARA2_SCALAR_FIELDS, "vocalness")
SONARA_VECTOR_FIELDS = {
    "mfcc_mean": 13,
    "chroma_mean": 12,
    "spectral_contrast_mean": 7,
}
_SONARA_ATTRIBUTES = {
    "bpm": "detected_bpm",
    "onset_density": "onset_density_per_second",
    "n_beats": "beat_count",
    "rms_mean": "rms_mean",
    "rms_max": "rms_max",
    "loudness_lufs": "integrated_loudness_lufs",
    "dynamic_range_db": "dynamic_range_db",
    "spectral_centroid_mean": "spectral_centroid_hz",
    "zero_crossing_rate": "zero_crossing_rate",
    "duration_sec": "analyzed_duration_seconds",
    "energy": "energy_score",
    "danceability": "danceability_score",
    "valence": "valence_score",
    "acousticness": "acousticness_score",
    "chord_change_rate": "chord_changes_per_second",
    "dissonance": "dissonance_score",
    "spectral_bandwidth_mean": "spectral_bandwidth_hz",
    "spectral_rolloff_mean": "spectral_rolloff_hz",
    "spectral_flatness_mean": "spectral_flatness",
    "bpm_raw": "raw_bpm",
    "energy_level": "energy_level",
    "intro_end_sec": "intro_end_seconds",
    "outro_start_sec": "outro_start_seconds",
    "energy_curve_hop_sec": "energy_curve_hop_seconds",
    "true_peak_db": "true_peak_dbtp",
    "replaygain_db": "replay_gain_db",
    "loudness_momentary_max_db": "max_momentary_loudness_lufs",
    "loudness_range_lu": "loudness_range_lu",
    "grid_offset_sec": "beat_grid_offset_seconds",
    "grid_stability": "beat_grid_stability",
    "leading_silence_sec": "leading_silence_seconds",
    "trailing_silence_sec": "trailing_silence_seconds",
    "vocalness": "vocal_probability",
}


@dataclass(frozen=True)
class FeatureMatrix:
    tracks: tuple[SourceTrack, ...]
    labels: list[str]
    matrix: np.ndarray
    feature_names: list[str]
    skipped_identities: tuple[TrackIdentity, ...]
    required_outputs: tuple[ContractIdentity, ...]


def build_labeled_feature_matrix(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    feature_set: str,
    *,
    classifier_key: str,
) -> FeatureMatrix:
    source = SourceDatabase(source_db_path)
    labels = RhythmLabDatabase(labels_db_path, classifier_key=classifier_key)
    return build_feature_matrix(
        source,
        feature_set,
        labels_by_identity=labels.training_labels(),
    )


def build_unlabeled_feature_matrix(
    source_db_path: str | Path,
    feature_set: str,
    *,
    expected_required_outputs: object | None = None,
) -> FeatureMatrix:
    source = SourceDatabase(source_db_path)
    tracks = source.list_tracks()
    labels = {track_identity(track): "" for track in tracks}
    return build_feature_matrix(
        source,
        feature_set,
        labels_by_identity=labels,
        tracks=tracks,
        expected_required_outputs=expected_required_outputs,
    )


def build_feature_matrix(
    source: SourceDatabase,
    feature_set: str,
    *,
    labels_by_identity: Mapping[TrackIdentity, str],
    tracks: Sequence[SourceTrack] | None = None,
    embedding_cache: dict[str, tuple[ContractIdentity, dict[int, np.ndarray]]] | None = None,
    expected_required_outputs: object | None = None,
) -> FeatureMatrix:
    sources = feature_sources(feature_set)
    scalar_fields = _sonara_scalar_fields(feature_set)
    current_tracks = tuple(tracks if tracks is not None else source.list_tracks())
    by_identity = {track_identity(track): track for track in current_tracks}
    cache = embedding_cache if embedding_cache is not None else {}
    embeddings = {
        family: _cached_embedding_vectors(source, family, cache)
        for family in sources
        if family != "sonara"
    }
    required_outputs = _required_outputs(
        source,
        sources,
        embeddings=embeddings,
    )
    expected = _parse_required_outputs(expected_required_outputs)
    if expected is not None and not _contracts_equal(required_outputs, expected):
        raise ValueError(
            "Prediction artifact required_outputs do not match the active source contracts"
        )

    feature_names = _feature_names(
        sources,
        scalar_fields=scalar_fields,
        contracts=required_outputs,
    )
    selected_tracks: list[SourceTrack] = []
    rows: list[np.ndarray] = []
    labels: list[str] = []
    skipped: list[TrackIdentity] = []
    for identity, label in labels_by_identity.items():
        track = by_identity.get(identity)
        if track is None:
            skipped.append(identity)
            continue
        row = _track_features(
            track,
            sources,
            scalar_fields=scalar_fields,
            embeddings=embeddings,
        )
        if row is None:
            skipped.append(identity)
            continue
        selected_tracks.append(track)
        rows.append(row)
        labels.append(str(label))
    matrix = (
        np.vstack(rows).astype(np.float32, copy=False)
        if rows
        else np.empty((0, len(feature_names)), dtype=np.float32)
    )
    return FeatureMatrix(
        tracks=tuple(selected_tracks),
        labels=labels,
        matrix=matrix,
        feature_names=feature_names,
        skipped_identities=tuple(skipped),
        required_outputs=required_outputs,
    )


def required_outputs_payload(
    contracts: Sequence[ContractIdentity],
) -> list[dict[str, object]]:
    return [
        {
            "contract_hash": contract.contract_hash,
            "canonical_payload": contract.canonical_payload,
        }
        for contract in contracts
    ]


def _track_features(
    track: SourceTrack,
    sources: tuple[str, ...],
    *,
    scalar_fields: tuple[str, ...],
    embeddings: Mapping[
        str, tuple[ContractIdentity, dict[int, np.ndarray]]
    ],
) -> np.ndarray | None:
    parts: list[np.ndarray] = []
    if "sonara" in sources:
        values = _sonara_features(track, scalar_fields=scalar_fields)
        if values is None:
            return None
        parts.append(values)
    for family in EMBEDDING_FEATURE_SOURCES:
        if family not in sources:
            continue
        vector = embeddings[family][1].get(track.track_id)
        if vector is None:
            return None
        parts.append(vector)
    return np.concatenate(parts).astype(np.float32, copy=False) if parts else None


def _sonara_features(
    track: SourceTrack,
    *,
    scalar_fields: tuple[str, ...],
) -> np.ndarray | None:
    features = track.sonara_features
    if features is None or track.sonara_contract is None:
        return None
    values: list[float] = []
    for field in scalar_fields:
        value = getattr(features, _SONARA_ATTRIBUTES[field])
        number = _finite_float(value)
        if number is None:
            return None
        values.append(number)
    for field, length in SONARA_VECTOR_FIELDS.items():
        vector = getattr(features, field)
        if len(vector) != length:
            return None
        converted = [_finite_float(value) for value in vector]
        if any(value is None for value in converted):
            return None
        values.extend(float(value) for value in converted if value is not None)
    return np.asarray(values, dtype=np.float32)


def _cached_embedding_vectors(
    source: SourceDatabase,
    family: str,
    cache: dict[str, tuple[ContractIdentity, dict[int, np.ndarray]]],
) -> tuple[ContractIdentity, dict[int, np.ndarray]]:
    if family not in cache:
        loaded = source.load_embedding_matrix(family)  # type: ignore[arg-type]
        cache[family] = (
            loaded.contract,
            {
                track.track_id: loaded.matrix[index].astype(np.float32, copy=True)
                for index, track in enumerate(loaded.tracks)
            },
        )
    return cache[family]


def _required_outputs(
    source_database: SourceDatabase,
    sources: tuple[str, ...],
    *,
    embeddings: Mapping[str, tuple[ContractIdentity, dict[int, np.ndarray]]],
) -> tuple[ContractIdentity, ...]:
    contracts: list[ContractIdentity] = []
    for source in sources:
        if source == "sonara":
            contract = source_database.active_contract(SONARA_CORE_OUTPUT)
            if contract is None:
                raise ValueError("SONARA features require one active current contract")
            contracts.append(contract)
        else:
            contracts.append(embeddings[source][0])
    return tuple(contracts)


def _parse_required_outputs(value: object) -> tuple[ContractIdentity, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ValueError("required_outputs must be a non-empty ordered list")
    result: list[ContractIdentity] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) != {
            "contract_hash",
            "canonical_payload",
        }:
            raise ValueError(
                f"required_outputs[{index}] must contain exactly contract_hash and canonical_payload"
            )
        payload = item["canonical_payload"]
        if not isinstance(payload, Mapping):
            raise ValueError(f"required_outputs[{index}].canonical_payload must be an object")
        canonical_json = json.dumps(
            dict(payload),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        contract = ContractIdentity.from_canonical_payload_json(canonical_json)
        if item["contract_hash"] != contract.contract_hash:
            raise ValueError(
                f"required_outputs[{index}].contract_hash does not match canonical_payload"
            )
        result.append(contract)
    return tuple(result)


def _contracts_equal(
    left: Sequence[ContractIdentity],
    right: Sequence[ContractIdentity],
) -> bool:
    return [contract.canonical_payload_json for contract in left] == [
        contract.canonical_payload_json for contract in right
    ]


def feature_sources(feature_set: str) -> tuple[str, ...]:
    clean = str(feature_set or "").strip().lower()
    if clean == "combined":
        return ("sonara", "mert", "maest")
    raw = tuple(part.strip() for part in clean.split("+") if part.strip())
    if not raw:
        raise ValueError("Feature set is required")
    unsupported = sorted(set(raw) - set(SUPPORTED_FEATURE_SOURCES))
    if unsupported:
        raise ValueError(f"Unsupported feature source: {', '.join(unsupported)}")
    normalized = tuple(FEATURE_SOURCE_ALIASES.get(source, source) for source in raw)
    duplicates = sorted(
        source for source in set(normalized) if normalized.count(source) > 1
    )
    if duplicates:
        raise ValueError(f"Duplicate feature source: {', '.join(duplicates)}")
    return tuple(source for source in BASE_FEATURE_SOURCES if source in normalized)


def _sonara_scalar_fields(feature_set: str) -> tuple[str, ...]:
    raw = tuple(
        part.strip()
        for part in str(feature_set or "").strip().lower().split("+")
        if part.strip()
    )
    if "sonara2vocal" in raw:
        return SONARA2VOCAL_SCALAR_FIELDS
    if "sonara2" in raw:
        return SONARA2_SCALAR_FIELDS
    return SONARA_SCALAR_FIELDS


def _feature_names(
    sources: tuple[str, ...],
    *,
    scalar_fields: tuple[str, ...],
    contracts: Sequence[ContractIdentity],
) -> list[str]:
    by_family = {contract.analysis_family: contract for contract in contracts}
    names: list[str] = []
    if "sonara" in sources:
        names.extend(f"sonara:{field}" for field in scalar_fields)
        for field, length in SONARA_VECTOR_FIELDS.items():
            names.extend(f"sonara:{field}:{index}" for index in range(length))
    for family in EMBEDDING_FEATURE_SOURCES:
        if family in sources:
            dim = by_family[family].dim
            if dim is None:
                raise ValueError(f"{family} embedding contract has no dimension")
            names.extend(f"{family}:{index}" for index in range(dim))
    return names


def _finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
