"""Cluster map of a REFERENCE seed search.

Pure analysis over vectors and SONARA rows the caller has already loaded:
nothing is read from or written to a library. The map measures the searched
layer by its own geometry. Points orbit the seed core: the radius is
``1 - similarity`` to the normalised seed mean, the query the search ranks by,
and the angle comes from an uncentred two-component SVD of the residuals
around it, so candidates that differ from the references the same way gather
in one swarm. LocalOutlierFactor, on the cosine the search ranks by, marks the
candidates that do not fit in with the rest in the layer's full space: tracks
the layer pulls in for another reason. SONARA only explains: a StandardScaler
fitted on the whole library puts its features on one scale, and every track
shows where it differs from the references' mean. Every returned number is a
plain Python ``int`` or ``float``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from ..library_models import TrackSummary


TOP_GAPS = 3

# Analysed sonara_features columns and their groups, in response order. Left
# out on purpose: key and chroma (categorical, and key does not matter here),
# vocal_probability (unreliable), the aggression family (unused) and
# energy_level (duplicates energy_score).
SONARA_FEATURE_GROUPS: dict[str, str] = {
    "detected_bpm": "tempo",
    "onset_density_per_second": "tempo",
    "dissonance_score": "tonal",
    "chord_changes_per_second": "tonal",
    "integrated_loudness_lufs": "loudness",
    "dynamic_range_db": "loudness",
    "spectral_centroid_hz": "spectral",
    "spectral_flatness": "spectral",
    "zero_crossing_rate": "spectral",
    "energy_score": "perceptual",
    "danceability_score": "perceptual",
    "valence_score": "perceptual",
    "acousticness_score": "perceptual",
    "mood_happy_score": "mood",
    "mood_aggressive_score": "mood",
    "mood_relaxed_score": "mood",
    "mood_sad_score": "mood",
}
# MFCC 1-12 from mfcc_mean_blob form the timbral group; coefficient 0 follows
# level rather than timbre.
_MFCC_FEATURES = tuple(f"mfcc_{index}" for index in range(1, 13))
FEATURE_GROUPS: dict[str, str] = {
    **SONARA_FEATURE_GROUPS,
    **{feature: "timbral" for feature in _MFCC_FEATURES},
}


@dataclass(frozen=True, slots=True)
class ClusterMapTrack:
    """One map input: seeds first in request order, then candidates by rank.

    ``vector`` is the stored unit-L2 row of the searched family and layer and
    is used as stored. ``sonara`` is the track's ``SonaraFeatureRow.values``:
    ML analysis only runs on tracks with a current SONARA Core.
    """

    track: TrackSummary
    seed: bool
    vector: np.ndarray
    sonara: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ClusterMapFeatureValue:
    """A SONARA feature as stored and its gap from the references' mean in library sigma."""

    feature: str
    group: str
    value: float
    delta: float


@dataclass(frozen=True, slots=True)
class ClusterMapPoint:
    """One map point, in input order; ``angle`` is in radians.

    ``exception`` marks a candidate that LocalOutlierFactor finds apart from
    the other candidates in the layer's space, and is never set on a seed.
    ``sonara_gaps`` explain the track in SONARA terms: each group's widest gap
    from the references, the widest groups first.
    """

    track: TrackSummary
    seed: bool
    similarity: float
    angle: float
    exception: bool
    sonara_gaps: tuple[ClusterMapFeatureValue, ...]


@dataclass(frozen=True, slots=True)
class ClusterMapGroupSpread:
    """Mean standard deviation of a group's features across the candidates, in library sigma."""

    group: str
    std: float


@dataclass(frozen=True, slots=True)
class ClusterMapCenter:
    """The candidates' centre of mass on the orbit."""

    similarity: float
    angle: float


@dataclass(frozen=True, slots=True)
class ClusterMapDrift:
    """Candidates' mean minus the seeds' mean for one feature, in library sigma."""

    feature: str
    group: str
    delta: float


@dataclass(frozen=True, slots=True)
class ClusterMap:
    """``profile`` runs from the SONARA group the candidates hold tightest to
    the loosest, ``drift`` from the largest shift to the smallest.
    """

    angle_variance_kept: float
    candidates_center: ClusterMapCenter
    points: tuple[ClusterMapPoint, ...]
    profile: tuple[ClusterMapGroupSpread, ...]
    drift: tuple[ClusterMapDrift, ...]


def build_cluster_map(
    tracks: Sequence[ClusterMapTrack],
    library_sonara: Sequence[Mapping[str, object]],
) -> ClusterMap:
    """Build the cluster map of one seed search.

    ``library_sonara`` holds the ``SonaraFeatureRow.values`` of every current
    SONARA track in the library; it fits the scale of each feature.
    """

    from sklearn.decomposition import TruncatedSVD
    from sklearn.neighbors import LocalOutlierFactor
    from sklearn.preprocessing import StandardScaler

    items = tuple(tracks)
    seeds = np.array([item.seed for item in items], dtype=bool)
    candidates = ~seeds
    if not seeds.any() or not candidates.any():
        raise ValueError("A cluster map needs seed tracks and candidates")
    matrix = np.vstack([np.asarray(item.vector, dtype=np.float64) for item in items])

    core = _unit(matrix[seeds].mean(axis=0))
    similarity = matrix @ core
    residuals = matrix - np.outer(similarity, core)
    # Uncentred on purpose: the core stays the origin of the orbit.
    svd = TruncatedSVD(n_components=2, random_state=0).fit(residuals)
    angles = _angles(svd.transform(residuals))
    center = _unit(matrix[candidates].mean(axis=0))
    center_similarity = float(center @ core)
    center_angle = _angles(svd.transform((center - center_similarity * core)[None, :]))[0]

    # Each candidate is weighed against its neighbours. With the default 20 of
    # them and 20 candidates, every neighbourhood is the whole set and nothing
    # can stand apart, so the neighbourhood is half the candidates at most.
    exceptions = np.zeros(len(items), dtype=bool)
    exceptions[candidates] = (
        LocalOutlierFactor(
            n_neighbors=min(20, int(candidates.sum()) // 2),
            metric="cosine",
        ).fit_predict(matrix[candidates])
        == -1
    )

    scaler = StandardScaler().fit(_feature_matrix(library_sonara))
    raw = _feature_matrix([item.sonara for item in items])
    scaled = scaler.transform(raw)
    gaps = scaled - scaled[seeds].mean(axis=0)

    points = tuple(
        ClusterMapPoint(
            track=item.track,
            seed=bool(seeds[index]),
            similarity=float(similarity[index]),
            angle=float(angles[index]),
            exception=bool(exceptions[index]),
            sonara_gaps=_top_gaps(raw[index], gaps[index]),
        )
        for index, item in enumerate(items)
    )
    shift = gaps[candidates].mean(axis=0)
    drift = tuple(
        ClusterMapDrift(feature=feature, group=group, delta=float(shift[position]))
        for position, (feature, group) in sorted(
            enumerate(FEATURE_GROUPS.items()),
            key=lambda entry: -abs(shift[entry[0]]),
        )
    )
    return ClusterMap(
        angle_variance_kept=float(
            np.sum(svd.singular_values_**2) / np.sum(residuals * residuals)
        ),
        candidates_center=ClusterMapCenter(
            similarity=center_similarity,
            angle=float(center_angle),
        ),
        points=points,
        profile=_profile(scaled[candidates]),
        drift=drift,
    )


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


def _angles(plane: np.ndarray) -> np.ndarray:
    return np.arctan2(plane[:, 1], plane[:, 0])


def _feature_matrix(rows: Sequence[Mapping[str, object]]) -> np.ndarray:
    """One row per track: the scalar features as stored, then MFCC 1-12."""

    return np.array(
        [
            [row[feature] for feature in SONARA_FEATURE_GROUPS]
            + list(row["mfcc_mean_blob"][1:13])
            for row in rows
        ],
        dtype=np.float64,
    ).reshape(len(rows), len(FEATURE_GROUPS))


def _top_gaps(
    values: np.ndarray,
    gaps: np.ndarray,
) -> tuple[ClusterMapFeatureValue, ...]:
    """Each group's widest gap from the references, the widest groups first."""

    names = tuple(FEATURE_GROUPS.items())
    widest: dict[str, int] = {}
    for position, (_, group) in enumerate(names):
        if group not in widest or abs(gaps[position]) > abs(gaps[widest[group]]):
            widest[group] = position
    ranked = sorted(widest.values(), key=lambda position: -abs(gaps[position]))
    return tuple(
        ClusterMapFeatureValue(
            feature=names[position][0],
            group=names[position][1],
            value=float(values[position]),
            delta=float(gaps[position]),
        )
        for position in ranked[:TOP_GAPS]
    )


def _profile(scaled: np.ndarray) -> tuple[ClusterMapGroupSpread, ...]:
    """Each group's mean feature standard deviation, tightest group first."""

    spread = scaled.std(axis=0)
    groups = tuple(FEATURE_GROUPS.values())
    by_group = {
        group: float(np.mean([std for std, owner in zip(spread, groups) if owner == group]))
        for group in dict.fromkeys(groups)
    }
    return tuple(
        ClusterMapGroupSpread(group=group, std=std)
        for group, std in sorted(by_group.items(), key=lambda entry: entry[1])
    )
