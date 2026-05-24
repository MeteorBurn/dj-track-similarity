from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dj_track_similarity.models import Track
from dj_track_similarity.sonara_similarity_scoring import optional_float, unwrap_feature_value

from .lab_db import RhythmLabDatabase
from .source_db import SourceDatabase


FEATURE_SETS = ("sonara", "mert", "maest", "combined")
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
    "spectral_contrast_mean",
)
SONARA_VECTOR_FIELDS = {
    "mfcc_mean": 13,
    "chroma_mean": 12,
}


@dataclass(frozen=True)
class FeatureMatrix:
    track_ids: list[int]
    labels: list[str]
    matrix: np.ndarray
    feature_names: list[str]
    skipped_track_ids: list[int]


def build_labeled_feature_matrix(source_db_path: str | Path, labels_db_path: str | Path, feature_set: str) -> FeatureMatrix:
    source = SourceDatabase(source_db_path)
    labels = RhythmLabDatabase(labels_db_path)
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
) -> FeatureMatrix:
    if feature_set not in FEATURE_SETS:
        raise ValueError(f"Unsupported feature set: {feature_set}")
    tracks_by_id = {track.id: track for track in source.list_tracks()}
    mert_vectors = _embedding_vectors(source, "mert") if feature_set in {"mert", "combined"} else {}
    maest_vectors = _embedding_vectors(source, "maest") if feature_set in {"maest", "combined"} else {}

    rows: list[np.ndarray] = []
    labels: list[str] = []
    track_ids: list[int] = []
    skipped: list[int] = []
    feature_names = _feature_names(feature_set, mert_vectors, maest_vectors)
    for track_id, label in labels_by_track.items():
        track = tracks_by_id.get(track_id)
        if track is None:
            skipped.append(track_id)
            continue
        row = _track_features(track, feature_set, mert_vectors=mert_vectors, maest_vectors=maest_vectors)
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
    feature_set: str,
    *,
    mert_vectors: dict[int, np.ndarray],
    maest_vectors: dict[int, np.ndarray],
) -> np.ndarray | None:
    parts: list[np.ndarray] = []
    if feature_set in {"sonara", "combined"}:
        sonara = _sonara_features(track)
        if sonara is None:
            return None
        parts.append(sonara)
    if feature_set in {"mert", "combined"}:
        vector = mert_vectors.get(track.id)
        if vector is None:
            return None
        parts.append(vector)
    if feature_set in {"maest", "combined"}:
        vector = maest_vectors.get(track.id)
        if vector is None:
            return None
        parts.append(vector)
    return np.concatenate(parts).astype(np.float32) if parts else None


def _sonara_features(track: Track) -> np.ndarray | None:
    metadata = track.metadata or {}
    raw_features = metadata.get("sonara_features")
    if not isinstance(raw_features, dict):
        return None
    values: list[float] = []
    for field in SONARA_SCALAR_FIELDS:
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


def _feature_names(feature_set: str, mert_vectors: dict[int, np.ndarray], maest_vectors: dict[int, np.ndarray]) -> list[str]:
    names: list[str] = []
    if feature_set in {"sonara", "combined"}:
        names.extend(f"sonara:{field}" for field in SONARA_SCALAR_FIELDS)
        for field, length in SONARA_VECTOR_FIELDS.items():
            names.extend(f"sonara:{field}:{index}" for index in range(length))
    if feature_set in {"mert", "combined"}:
        dim = _embedding_dim(mert_vectors)
        names.extend(f"mert:{index}" for index in range(dim))
    if feature_set in {"maest", "combined"}:
        dim = _embedding_dim(maest_vectors)
        names.extend(f"maest:{index}" for index in range(dim))
    return names


def _embedding_dim(vectors: dict[int, np.ndarray]) -> int:
    if not vectors:
        return 0
    return int(next(iter(vectors.values())).shape[0])
