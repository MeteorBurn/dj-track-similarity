"""Reference-anchored SONARA evidence alongside unchanged model similarities.

Library IQR scales and reference profiles never depend on the candidate batch
or on the searched model. Distances and library percentiles are descriptive,
not probabilities of a musical match. Reference envelopes are conservative:
being inside one does not establish similarity to a real track.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from ..library_models import TrackSummary


# Each scalar or complete vector is one equally weighted descriptor. Vector
# RMS prevents dimensionality alone from multiplying a descriptor's weight.
SONARA_FEATURE_GROUPS: dict[str, str] = {
    "tempo_variability": "rhythm",
    "onset_density_per_second": "rhythm",
    "dynamic_range_db": "dynamics",
    "loudness_range_lu": "dynamics",
    "energy_curve_stddev": "dynamics",
    "zero_crossing_rate": "spectral",
    "spectral_centroid_hz": "spectral",
    "spectral_bandwidth_hz": "spectral",
    "spectral_rolloff_hz": "spectral",
    "spectral_flatness": "spectral",
    "dissonance_score": "tonal",
    "chord_changes_per_second": "tonal",
}
_DESCRIPTORS = (
    *((name, name, group, 1) for name, group in SONARA_FEATURE_GROUPS.items()),
    ("chroma", "chroma_mean_blob", "tonal", 12),
    ("mfcc", "mfcc_mean_blob", "timbral", 13),
    ("spectral_contrast", "spectral_contrast_mean_blob", "spectral", 7),
)
# Exploratory effect-size rules, fixed independently of the returned tracks.
# Neither rule is a calibrated genre, mood, or musical-match decision.
DEPARTURE_THRESHOLD = 1.5
DRIFT_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class ClusterMapTrack:
    track: TrackSummary
    seed: bool
    vector: np.ndarray
    sonara: Mapping[str, object]
    similarity: float | None = None


@dataclass(frozen=True, slots=True)
class ClusterMapReferenceSimilarity:
    track_id: int
    similarity: float


@dataclass(frozen=True, slots=True)
class ClusterMapDeviation:
    descriptor: str
    group: str
    available: bool
    value: float | None
    reference_min: float | None
    reference_max: float | None
    delta_iqr: float | None
    distance: float | None
    envelope_distance: float | None
    percentile: float | None
    departure: bool | None


@dataclass(frozen=True, slots=True)
class ClusterMapSonara:
    available: bool
    distance: float | None
    percentile: float | None
    nearest_reference_id: int | None
    descriptor_count: int
    requires_listening: bool | None
    deviations: tuple[ClusterMapDeviation, ...]


@dataclass(frozen=True, slots=True)
class ClusterMapPoint:
    track: TrackSummary
    seed: bool
    similarity: float
    reference_similarities: tuple[ClusterMapReferenceSimilarity, ...]
    sonara: ClusterMapSonara


@dataclass(frozen=True, slots=True)
class ClusterMapCalibration:
    library_count: int
    complete_library_count: int
    descriptor_count: int
    total_descriptors: int
    departure_threshold: float
    drift_threshold: float


@dataclass(frozen=True, slots=True)
class ClusterMapDescriptorSummary:
    descriptor: str
    group: str
    compared_count: int
    median_distance: float | None
    median_envelope_distance: float | None
    median_delta_iqr: float | None
    above_count: int | None
    below_count: int | None
    departure_count: int
    coherent_shift_distance: float | None
    direction_count: int
    coherent_drift: bool


@dataclass(frozen=True, slots=True)
class ClusterMapSummary:
    candidate_count: int
    compared_count: int
    requires_listening_count: int
    median_distance: float | None
    median_percentile: float | None
    coherent_drift: bool
    descriptors: tuple[ClusterMapDescriptorSummary, ...]


@dataclass(frozen=True, slots=True)
class ClusterMap:
    points: tuple[ClusterMapPoint, ...]
    calibration: ClusterMapCalibration
    summary: ClusterMapSummary


def build_cluster_map(
    tracks: Sequence[ClusterMapTrack],
    library_sonara: Sequence[Mapping[str, object]],
) -> ClusterMap:
    """Compare candidates to actual references without refitting on results.

    Descriptors missing in any reference are unavailable for the whole query.
    Missing candidate measurements stay unknown. The overall score requires all
    active descriptors; its coverage can still be less than all 15 descriptors.
    """

    from sklearn.preprocessing import RobustScaler

    items = tuple(tracks)
    seeds = np.array([item.seed for item in items], dtype=bool)
    candidates = ~seeds
    if not seeds.any() or not candidates.any():
        raise ValueError("A cluster map needs seed tracks and candidates")
    matrix = np.vstack([np.asarray(item.vector, dtype=np.float64) for item in items])
    core = matrix[seeds].mean(axis=0)
    norm = float(np.linalg.norm(core))
    if not np.isfinite(matrix).all() or not np.isfinite(norm) or norm <= 0:
        raise ValueError("Reference embeddings must have a finite nonzero mean")
    similarities = matrix @ (core / norm)
    reference_similarities = matrix @ matrix[seeds].T
    reference_ids = tuple(item.track.track_id for item in items if item.seed)
    seed_count = int(seeds.sum())
    library_count = len(library_sonara)
    rows = [item.sonara for item in items]
    point_details: list[list[ClusterMapDeviation]] = [[] for _ in items]
    descriptor_summaries: list[ClusterMapDescriptorSummary] = []
    item_squared = np.zeros((len(items), seed_count), dtype=np.float64)
    library_squared = np.zeros((library_count, seed_count), dtype=np.float64)
    item_complete = np.ones(len(items), dtype=bool)
    library_complete = np.ones(library_count, dtype=bool)
    coverage = np.zeros(len(items), dtype=int)
    active_count = 0

    for descriptor, column, group, dimensions in _DESCRIPTORS:
        raw = _values(rows, column, dimensions)
        background = _values(library_sonara, column, dimensions)
        valid = np.isfinite(raw).all(axis=1)
        baseline_valid = np.isfinite(background).all(axis=1)
        active = bool(valid[seeds].all() and baseline_valid.sum() >= 2)
        if active:
            quartiles = np.quantile(background[baseline_valid], (0.25, 0.75), axis=0)
            iqr = quartiles[1] - quartiles[0]
            # Do not let RobustScaler silently replace a zero IQR with one
            # raw unit. A partly unscaled vector is unavailable as a whole.
            active = bool(np.isfinite(iqr).all() and (iqr > 10 * np.finfo(float).eps).all())
        if not active:
            for index in range(len(items)):
                point_details[index].append(ClusterMapDeviation(
                    descriptor=descriptor, group=group, available=False,
                    value=float(raw[index, 0]) if dimensions == 1 and valid[index] else None,
                    reference_min=None, reference_max=None, delta_iqr=None,
                    distance=None, envelope_distance=None, percentile=None, departure=None,
                ))
            descriptor_summaries.append(_descriptor_summary(descriptor, group, dimensions))
            continue

        scaler = RobustScaler().fit(background[baseline_valid])
        scaled = (raw - scaler.center_) / scaler.scale_
        baseline = (background - scaler.center_) / scaler.scale_
        references = scaled[seeds]
        distances = _reference_distances(scaled, references)
        baseline_distances = _reference_distances(baseline, references)
        nearest_all = np.full(len(items), np.nan)
        nearest_all[valid] = np.min(distances[valid], axis=1)
        descriptor_baseline = np.sort(np.min(baseline_distances[baseline_valid], axis=1))
        low = references.min(axis=0)
        high = references.max(axis=0)
        excursions = np.minimum(scaled - low, 0) + np.maximum(scaled - high, 0)
        envelope_distances = np.sqrt(np.mean(excursions**2, axis=1))
        raw_references = raw[seeds]
        for index in range(len(items)):
            available = bool(valid[index])
            point_details[index].append(ClusterMapDeviation(
                descriptor=descriptor, group=group, available=available,
                value=float(raw[index, 0]) if dimensions == 1 and available else None,
                reference_min=float(raw_references.min()) if dimensions == 1 else None,
                reference_max=float(raw_references.max()) if dimensions == 1 else None,
                delta_iqr=float(excursions[index, 0]) if dimensions == 1 and available else None,
                distance=float(nearest_all[index]) if available else None,
                envelope_distance=float(envelope_distances[index]) if available else None,
                percentile=_percentile(descriptor_baseline, nearest_all[index]) if available else None,
                departure=bool(envelope_distances[index] > DEPARTURE_THRESHOLD) if available else None,
            ))
        selected = candidates & valid
        descriptor_summaries.append(_descriptor_summary(
            descriptor, group, dimensions, nearest_all[selected], excursions[selected],
        ))
        active_count += 1
        coverage += valid
        item_complete &= valid
        library_complete &= baseline_valid
        item_squared += np.where(valid[:, None], distances**2, 0)
        library_squared += np.where(baseline_valid[:, None], baseline_distances**2, 0)

    complete_library_count = int(library_complete.sum()) if active_count else 0
    if active_count and complete_library_count:
        item_distances = np.sqrt(item_squared / active_count)
        library_distances = np.sort(
            np.sqrt(library_squared[library_complete] / active_count).min(axis=1)
        )
    else:
        item_complete[:] = False
        item_distances = np.zeros_like(item_squared)
        library_distances = np.empty(0)

    points = []
    for index, item in enumerate(items):
        available = bool(item_complete[index])
        nearest_index = int(np.argmin(item_distances[index])) if available else None
        distance = float(item_distances[index, nearest_index]) if available else None
        deviations = tuple(point_details[index])
        known_departure = any(detail.departure for detail in deviations)
        requires_listening = (
            True if known_departure else False if coverage[index] == len(_DESCRIPTORS) else None
        )
        points.append(ClusterMapPoint(
            track=item.track,
            seed=bool(item.seed),
            similarity=float(item.similarity if item.similarity is not None else similarities[index]),
            reference_similarities=tuple(
                ClusterMapReferenceSimilarity(track_id=track_id, similarity=float(value))
                for track_id, value in zip(reference_ids, reference_similarities[index], strict=True)
            ),
            sonara=ClusterMapSonara(
                available=available, distance=distance,
                percentile=_percentile(library_distances, distance) if distance is not None else None,
                nearest_reference_id=reference_ids[nearest_index] if nearest_index is not None else None,
                descriptor_count=int(coverage[index]), requires_listening=requires_listening,
                deviations=deviations,
            ),
        ))
    compared = [point.sonara for point in points if not point.seed and point.sonara.available]
    return ClusterMap(
        points=tuple(points),
        calibration=ClusterMapCalibration(
            library_count=library_count, complete_library_count=complete_library_count,
            descriptor_count=active_count, total_descriptors=len(_DESCRIPTORS),
            departure_threshold=DEPARTURE_THRESHOLD, drift_threshold=DRIFT_THRESHOLD,
        ),
        summary=ClusterMapSummary(
            candidate_count=int(candidates.sum()), compared_count=len(compared),
            requires_listening_count=sum(
                point.sonara.requires_listening is True for point in points if not point.seed
            ),
            median_distance=_median([point.distance for point in compared]),
            median_percentile=_median([point.percentile for point in compared]),
            coherent_drift=any(summary.coherent_drift for summary in descriptor_summaries),
            descriptors=tuple(descriptor_summaries),
        ),
    )


def _values(rows: Sequence[Mapping[str, object]], column: str, dimensions: int) -> np.ndarray:
    matrix = np.full((len(rows), dimensions), np.nan)
    for index, row in enumerate(rows):
        value = row.get(column)
        if value is None:
            continue
        try:
            vector = np.asarray(value, dtype=np.float64).reshape(-1)
        except (TypeError, ValueError):
            continue
        if vector.size == dimensions and np.isfinite(vector).all():
            matrix[index] = vector
    return matrix


def _reference_distances(matrix: np.ndarray, references: np.ndarray) -> np.ndarray:
    return np.column_stack([
        np.sqrt(np.mean((matrix - reference) ** 2, axis=1)) for reference in references
    ])


def _percentile(background: np.ndarray, distance: float) -> float:
    """Percentage strictly closer in the sorted library baseline; ties stay together."""

    return float(np.searchsorted(background, distance, side="left") / len(background) * 100)


def _median(values: Sequence[float | None]) -> float | None:
    finite = [value for value in values if value is not None]
    return float(np.median(finite)) if finite else None


def _descriptor_summary(
    descriptor: str,
    group: str,
    dimensions: int,
    distances: np.ndarray | None = None,
    excursions: np.ndarray | None = None,
) -> ClusterMapDescriptorSummary:
    count = len(distances) if distances is not None else 0
    if not count:
        return ClusterMapDescriptorSummary(
            descriptor=descriptor, group=group, compared_count=0,
            median_distance=None, median_envelope_distance=None, median_delta_iqr=None,
            above_count=None, below_count=None, departure_count=0,
            coherent_shift_distance=None, direction_count=0, coherent_drift=False,
        )
    median_excursion = np.median(excursions, axis=0)
    shift = float(np.sqrt(np.mean(median_excursion**2)))
    envelope_distances = np.sqrt(np.mean(excursions**2, axis=1))
    direction_count = int(np.count_nonzero(excursions @ median_excursion > 0))
    return ClusterMapDescriptorSummary(
        descriptor=descriptor, group=group, compared_count=count,
        median_distance=float(np.median(distances)),
        median_envelope_distance=float(np.median(envelope_distances)),
        median_delta_iqr=float(median_excursion[0]) if dimensions == 1 else None,
        above_count=int(np.count_nonzero(excursions[:, 0] > 0)) if dimensions == 1 else None,
        below_count=int(np.count_nonzero(excursions[:, 0] < 0)) if dimensions == 1 else None,
        departure_count=int(np.count_nonzero(envelope_distances > DEPARTURE_THRESHOLD)),
        coherent_shift_distance=shift, direction_count=direction_count,
        coherent_drift=bool(count >= 3 and shift > DRIFT_THRESHOLD and direction_count > count / 2),
    )
