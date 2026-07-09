from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np

from dj_track_similarity.models import Track
from dj_track_similarity.sonara_similarity_scoring import optional_float, unwrap_feature_value

from .lab_db import RhythmLabDatabase
from .source_db import SourceDatabase


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
    "key_confidence",
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
# spectral_contrast_mean is a per-band vector (7 sub-band contrast values), not a scalar. It used to
# sit in SONARA_SCALAR_FIELDS, where optional_float() on a list returned None and every track got a
# constant 0.0 for it - one dead feature in every trained model. It belongs here with the other
# vector features so all 7 bands contribute.
SONARA_VECTOR_FIELDS = {
    "mfcc_mean": 13,
    "chroma_mean": 12,
    "spectral_contrast_mean": 7,
}


@dataclass(frozen=True)
class FeatureMatrix:
    track_ids: list[int]
    labels: list[str]
    matrix: np.ndarray
    feature_names: list[str]
    skipped_track_ids: list[int]


def build_labeled_feature_matrix(
    source_db_path: str | Path,
    labels_db_path: str | Path,
    feature_set: str,
    *,
    classifier_key: str,
) -> FeatureMatrix:
    source = SourceDatabase(source_db_path)
    labels = RhythmLabDatabase(labels_db_path, classifier_key=classifier_key)
    labels_by_track = labels.training_labels()
    return build_feature_matrix(source, feature_set, labels_by_track=labels_by_track)


def build_unlabeled_feature_matrix(source_db_path: str | Path, feature_set: str) -> FeatureMatrix:
    source = SourceDatabase(source_db_path)
    labels_by_track = {track.id: "" for track in source.list_tracks()}
    return build_feature_matrix(source, feature_set, labels_by_track=labels_by_track)


def build_feature_matrix(
    source: SourceDatabase,
    feature_set: str,
    *,
    labels_by_track: dict[int, str],
    tracks_by_id: dict[int, Track] | None = None,
    embedding_vectors: dict[str, dict[int, np.ndarray]] | None = None,
) -> FeatureMatrix:
    sources = feature_sources(feature_set)
    sonara_scalar_fields = _sonara_scalar_fields(feature_set)
    tracks_by_id = tracks_by_id or {track.id: track for track in source.list_tracks()}
    embedding_vectors = embedding_vectors if embedding_vectors is not None else {}
    mert_vectors = _cached_embedding_vectors(source, "mert", embedding_vectors) if "mert" in sources else {}
    maest_vectors = _cached_embedding_vectors(source, "maest", embedding_vectors) if "maest" in sources else {}
    clap_vectors = _cached_embedding_vectors(source, "clap", embedding_vectors) if "clap" in sources else {}

    rows: list[np.ndarray] = []
    labels: list[str] = []
    track_ids: list[int] = []
    skipped: list[int] = []
    feature_names = _feature_names(sources, mert_vectors, maest_vectors, clap_vectors, sonara_scalar_fields=sonara_scalar_fields)
    for track_id, label in labels_by_track.items():
        track = tracks_by_id.get(track_id)
        if track is None:
            skipped.append(track_id)
            continue
        row = _track_features(
            track,
            sources,
            sonara_scalar_fields=sonara_scalar_fields,
            mert_vectors=mert_vectors,
            maest_vectors=maest_vectors,
            clap_vectors=clap_vectors,
        )
        if row is None:
            skipped.append(track_id)
            continue
        rows.append(row)
        labels.append(label)
        track_ids.append(track_id)
    matrix = np.vstack(rows).astype(np.float32) if rows else np.zeros((0, len(feature_names)), dtype=np.float32)
    return FeatureMatrix(track_ids=track_ids, labels=labels, matrix=matrix, feature_names=feature_names, skipped_track_ids=skipped)


def _track_features(
    track: Track,
    sources: tuple[str, ...],
    *,
    sonara_scalar_fields: tuple[str, ...],
    mert_vectors: dict[int, np.ndarray],
    maest_vectors: dict[int, np.ndarray],
    clap_vectors: dict[int, np.ndarray],
) -> np.ndarray | None:
    parts: list[np.ndarray] = []
    if "sonara" in sources:
        sonara = _sonara_features(track, sonara_scalar_fields=sonara_scalar_fields)
        if sonara is None:
            return None
        parts.append(sonara)
    if "mert" in sources:
        vector = mert_vectors.get(track.id)
        if vector is None:
            return None
        parts.append(vector)
    if "maest" in sources:
        vector = maest_vectors.get(track.id)
        if vector is None:
            return None
        parts.append(vector)
    if "clap" in sources:
        vector = clap_vectors.get(track.id)
        if vector is None:
            return None
        parts.append(vector)
    return np.concatenate(parts).astype(np.float32) if parts else None


def _sonara_features(track: Track, *, sonara_scalar_fields: tuple[str, ...]) -> np.ndarray | None:
    metadata = track.metadata or {}
    raw_features = metadata.get("sonara_features")
    if not isinstance(raw_features, dict):
        return None
    values: list[float] = []
    for field in sonara_scalar_fields:
        values.append(_numeric_feature(raw_features.get(field)))
    for field, length in SONARA_VECTOR_FIELDS.items():
        values.extend(_numeric_vector(raw_features.get(field), length))
    return np.asarray(values, dtype=np.float32)


def _numeric_feature(value: object) -> float:
    number = optional_float(unwrap_feature_value(value))
    return float(number) if number is not None else 0.0


def _numeric_vector(value: object, length: int) -> list[float]:
    unwrapped = unwrap_feature_value(value)
    result: list[float] = []
    if isinstance(unwrapped, (list, tuple)):
        for item in unwrapped[:length]:
            number = optional_float(item)
            result.append(float(number) if number is not None else 0.0)
    while len(result) < length:
        result.append(0.0)
    return result


def _embedding_vectors(source: SourceDatabase, embedding_key: str) -> dict[int, np.ndarray]:
    tracks, matrix = source.load_embedding_matrix(embedding_key)
    return {track.id: matrix[index].astype(np.float32, copy=True) for index, track in enumerate(tracks)}


def _cached_embedding_vectors(
    source: SourceDatabase,
    embedding_key: str,
    cache: dict[str, dict[int, np.ndarray]],
) -> dict[int, np.ndarray]:
    if embedding_key not in cache:
        cache[embedding_key] = _embedding_vectors(source, embedding_key)
    return cache[embedding_key]


def feature_sources(feature_set: str) -> tuple[str, ...]:
    clean = str(feature_set or "").strip().lower()
    if clean == "combined":
        return ("sonara", "mert", "maest")
    raw_sources = tuple(part.strip() for part in clean.split("+") if part.strip())
    if not raw_sources:
        raise ValueError("Feature set is required")
    unsupported = sorted(set(raw_sources) - set(SUPPORTED_FEATURE_SOURCES))
    if unsupported:
        raise ValueError(f"Unsupported feature source: {', '.join(unsupported)}")
    normalized_sources = tuple(FEATURE_SOURCE_ALIASES.get(source, source) for source in raw_sources)
    duplicates = sorted(source for source in set(normalized_sources) if normalized_sources.count(source) > 1)
    if duplicates:
        raise ValueError(f"Duplicate feature source: {', '.join(duplicates)}")
    return tuple(source for source in BASE_FEATURE_SOURCES if source in normalized_sources)


def _sonara_scalar_fields(feature_set: str) -> tuple[str, ...]:
    raw_sources = tuple(part.strip() for part in str(feature_set or "").strip().lower().split("+") if part.strip())
    if "sonara2vocal" in raw_sources:
        return SONARA2VOCAL_SCALAR_FIELDS
    if "sonara2" in raw_sources:
        return SONARA2_SCALAR_FIELDS
    return SONARA_SCALAR_FIELDS


def _feature_names(
    sources: tuple[str, ...],
    mert_vectors: dict[int, np.ndarray],
    maest_vectors: dict[int, np.ndarray],
    clap_vectors: dict[int, np.ndarray],
    *,
    sonara_scalar_fields: tuple[str, ...],
) -> list[str]:
    names: list[str] = []
    if "sonara" in sources:
        names.extend(f"sonara:{field}" for field in sonara_scalar_fields)
        for field, length in SONARA_VECTOR_FIELDS.items():
            names.extend(f"sonara:{field}:{index}" for index in range(length))
    if "mert" in sources:
        dim = _embedding_dim(mert_vectors)
        names.extend(f"mert:{index}" for index in range(dim))
    if "maest" in sources:
        dim = _embedding_dim(maest_vectors)
        names.extend(f"maest:{index}" for index in range(dim))
    if "clap" in sources:
        dim = _embedding_dim(clap_vectors)
        names.extend(f"clap:{index}" for index in range(dim))
    return names


def _embedding_dim(vectors: dict[int, np.ndarray]) -> int:
    if not vectors:
        return 0
    return int(next(iter(vectors.values())).shape[0])
