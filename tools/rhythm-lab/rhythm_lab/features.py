from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
import math
from pathlib import Path
from types import MappingProxyType

import numpy as np

from .lab_db import RhythmLabDatabase, TrackIdentity, track_identity
from .source_db import SourceDatabase, SourceTrack


SONARA_SOURCE_VARIANTS = ("sonara", "sonara2", "sonara2vocal")
EMBEDDING_FEATURE_SOURCES = ("mert", "maest", "clap", "muq")
BASE_FEATURE_SOURCES = ("sonara", *EMBEDDING_FEATURE_SOURCES)
SUPPORTED_FEATURE_SOURCES = (*SONARA_SOURCE_VARIANTS, *EMBEDDING_FEATURE_SOURCES)
FEATURE_SOURCE_ALIASES = {"sonara2": "sonara", "sonara2vocal": "sonara"}
MODERN_FULL_FEATURE_SET = "sonara2vocal+mert+maest+clap+muq"
DEFAULT_TRAINING_FEATURE_SET = MODERN_FULL_FEATURE_SET
FEATURE_SETS = ("sonara", "mert", "maest", "muq", "combined")
FEATURE_RECIPE_OPTIONS = (
    "combined",
    DEFAULT_TRAINING_FEATURE_SET,
    "sonara2vocal",
    "sonara2",
    *(
        "+".join(sources)
        for size in range(1, len(BASE_FEATURE_SOURCES) + 1)
        for sources in combinations(BASE_FEATURE_SOURCES, size)
    ),
)
_LEGACY_ABLATION_EMBEDDING_SOURCES = ("mert", "maest", "clap")
_LEGACY_ABLATION_FEATURE_SETS = tuple(
    "combined" if sources == ("sonara", "mert", "maest") else "+".join(sources)
    for sonara_source in ("", *SONARA_SOURCE_VARIANTS)
    for size in range(0, len(_LEGACY_ABLATION_EMBEDDING_SOURCES) + 1)
    for embedding_sources in combinations(_LEGACY_ABLATION_EMBEDDING_SOURCES, size)
    if sonara_source or embedding_sources
    for sources in (((sonara_source,) if sonara_source else ()) + embedding_sources,)
)
ABLATION_FEATURE_SETS = (
    *_LEGACY_ABLATION_FEATURE_SETS,
    "muq",
    "sonara+muq",
    "mert+muq",
    "sonara+mert+maest+clap+muq",
    MODERN_FULL_FEATURE_SET,
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
    source_dimensions: Mapping[str, int]


def build_labeled_feature_matrix(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    feature_set: str,
    *,
    classifier_key: str,
) -> FeatureMatrix:
    source = SourceDatabase(source_db_path)
    labels = RhythmLabDatabase(labels_db_path, classifier_key=classifier_key)
    return build_labeled_feature_matrix_from_sources(
        source,
        labels,
        feature_set,
    )


def build_labeled_feature_matrix_from_sources(
    source: SourceDatabase,
    labels: RhythmLabDatabase,
    feature_set: str,
) -> FeatureMatrix:
    labels_by_identity = labels.training_labels()
    return build_feature_matrix(
        source,
        feature_set,
        labels_by_identity=labels_by_identity,
        tracks=source.tracks_by_identities(labels_by_identity),
    )


def build_unlabeled_feature_matrix(
    source_db_path: str | Path,
    feature_set: str,
    *,
    expected_feature_names: object | None = None,
) -> FeatureMatrix:
    source = SourceDatabase(source_db_path)
    tracks = source.list_tracks()
    labels = {track_identity(track): "" for track in tracks}
    return build_feature_matrix(
        source,
        feature_set,
        labels_by_identity=labels,
        tracks=tracks,
        expected_feature_names=expected_feature_names,
    )


def build_feature_matrix(
    source: SourceDatabase,
    feature_set: str,
    *,
    labels_by_identity: Mapping[TrackIdentity, str],
    tracks: Sequence[SourceTrack] | None = None,
    embedding_cache: dict[str, tuple[int, dict[int, np.ndarray]]] | None = None,
    expected_feature_names: object | None = None,
) -> FeatureMatrix:
    sources = feature_sources(feature_set)
    scalar_fields = _sonara_scalar_fields(feature_set)
    current_tracks = tuple(tracks if tracks is not None else source.list_tracks())
    by_identity = {track_identity(track): track for track in current_tracks}
    cache = embedding_cache if embedding_cache is not None else {}
    selected_track_ids = tuple(track.track_id for track in current_tracks)
    embeddings = {
        family: _cached_embedding_vectors(
            source,
            family,
            cache,
            track_ids=selected_track_ids,
        )
        for family in sources
        if family != "sonara"
    }
    feature_names = _feature_names(
        sources,
        scalar_fields=scalar_fields,
        embeddings=embeddings,
    )
    expected = _parse_feature_names(expected_feature_names)
    if expected is not None and feature_names != expected:
        raise ValueError(
            "Prediction artifact feature_names do not match current source dimensions"
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
        source_dimensions=MappingProxyType(
            {
                source: (
                    len(_sonara_feature_names(scalar_fields))
                    if source == "sonara"
                    else embeddings[source][0]
                )
                for source in sources
            }
        ),
    )


def _track_features(
    track: SourceTrack,
    sources: tuple[str, ...],
    *,
    scalar_fields: tuple[str, ...],
    embeddings: Mapping[str, tuple[int, dict[int, np.ndarray]]],
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
    if features is None:
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
    cache: dict[str, tuple[int, dict[int, np.ndarray]]],
    *,
    track_ids: Sequence[int],
) -> tuple[int, dict[int, np.ndarray]]:
    cached = cache.get(family)
    missing_ids = (
        list(track_ids)
        if cached is None
        else [track_id for track_id in track_ids if track_id not in cached[1]]
    )
    if cached is None or missing_ids:
        loaded = source.load_embedding_matrix(  # type: ignore[arg-type]
            family,
            track_ids=missing_ids,
        )
        loaded_vectors = {
            track.track_id: loaded.matrix[index].astype(np.float32, copy=True)
            for index, track in enumerate(loaded.tracks)
        }
        if cached is None:
            cache[family] = (loaded.dimension, loaded_vectors)
        else:
            if loaded.dimension != cached[0]:
                raise ValueError(
                    f"{family.upper()} source dimension changed while building features"
                )
            cached[1].update(loaded_vectors)
    return cache[family]


def _parse_feature_names(value: object) -> list[str] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError("feature_names must be a non-empty ordered list of unique strings")
    return list(value)


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


def feature_recipe_readiness(
    feature_set: str,
    feature_states: Mapping[str, object],
) -> dict[str, object]:
    """Describe readiness strictly for the selected feature recipe."""

    required_sources = feature_sources(feature_set)
    selected_states: dict[str, dict[str, object]] = {}
    blocking: list[dict[str, object]] = []
    for source in required_sources:
        state = _feature_state_payload(feature_states.get(source), source=source)
        selected_states[source] = state
        if state["status"] != "current":
            blocking.append({"source": source, **state})
    return {
        "feature_set": str(feature_set).strip().lower(),
        "required_sources": list(required_sources),
        "ready": not blocking,
        "sources": selected_states,
        "blocking": blocking,
    }


def _feature_state_payload(value: object, *, source: str) -> dict[str, object]:
    if isinstance(value, Mapping):
        status = str(value.get("status") or "missing")
        reason = value.get("reason")
    else:
        status = str(getattr(value, "status", "missing"))
        reason = getattr(value, "reason", None)
    if status not in {"current", "missing"}:
        status = "missing"
        reason = f"{source.upper()} feature status is unavailable."
    return {
        "status": status,
        "reason": None if reason is None else str(reason),
    }


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
    embeddings: Mapping[str, tuple[int, dict[int, np.ndarray]]],
) -> list[str]:
    names = _sonara_feature_names(scalar_fields) if "sonara" in sources else []
    for family in EMBEDDING_FEATURE_SOURCES:
        if family in sources:
            names.extend(f"{family}:{index}" for index in range(embeddings[family][0]))
    return names


def _sonara_feature_names(scalar_fields: tuple[str, ...]) -> list[str]:
    names: list[str] = []
    names.extend(f"sonara:{field}" for field in scalar_fields)
    for field, length in SONARA_VECTOR_FIELDS.items():
        names.extend(f"sonara:{field}:{index}" for index in range(length))
    return names


def _finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
