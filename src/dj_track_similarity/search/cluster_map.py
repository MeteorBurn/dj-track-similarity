"""Cluster map of a REFERENCE seed search.

Pure analysis over vectors and SONARA rows the caller has already loaded:
nothing is read from or written to a library. Points orbit the seed core:
the radius is ``1 - similarity`` to the normalised seed mean, the query the
search ranks by, and the angle comes from a PCA of the residuals around it,
so candidates spread by how they differ from each other. scikit-learn does
the analysis: KMeans splits the candidates' residual directions into a fixed
number of clusters, a StandardScaler fitted on the whole library puts the
SONARA features on one scale, and IsolationForest flags the tracks whose
SONARA profile stands out. Every returned number is a plain Python ``int`` or
``float``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from ..library_models import TrackSummary


CLUSTER_COUNT = 4
TOP_GENRES = 3
TOP_OUTLIER_FEATURES = 3

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
    """A SONARA feature as stored and its distance from the map's mean in library sigma."""

    feature: str
    group: str
    value: float
    delta: float


@dataclass(frozen=True, slots=True)
class ClusterMapPoint:
    """One map point, in input order; ``angle`` is in radians.

    ``cluster`` is ``None`` for seeds. ``outlier_score`` is IsolationForest's
    ``score_samples``: the lower, the more unusual.
    """

    track: TrackSummary
    seed: bool
    similarity: float
    angle: float
    cluster: int | None
    outlier: bool
    outlier_score: float
    outlier_features: tuple[ClusterMapFeatureValue, ...]


@dataclass(frozen=True, slots=True)
class ClusterMapGroupSpread:
    """Mean standard deviation of a group's features, in library sigma."""

    group: str
    std: float


@dataclass(frozen=True, slots=True)
class ClusterMapGenreShare:
    """A full MAEST label's share of the cluster's summed genre scores."""

    genre_name: str
    share: float


@dataclass(frozen=True, slots=True)
class ClusterMapCluster:
    """``profile`` runs from the group the cluster holds tightest to the loosest."""

    size: int
    median_similarity: float
    representative_track_id: int
    profile: tuple[ClusterMapGroupSpread, ...]
    maest_genres: tuple[ClusterMapGenreShare, ...]


@dataclass(frozen=True, slots=True)
class ClusterMapDrift:
    """Candidates' mean minus the seeds' mean for one feature, in library sigma."""

    feature: str
    group: str
    delta: float


@dataclass(frozen=True, slots=True)
class ClusterMap:
    """Clusters run nearest to the core first and ``point.cluster`` indexes them.

    ``center_similarity`` is the similarity of the candidates' centre of mass
    to the core; ``drift`` runs from the largest shift to the smallest.
    """

    silhouette: float
    angle_variance_kept: float
    center_similarity: float
    points: tuple[ClusterMapPoint, ...]
    clusters: tuple[ClusterMapCluster, ...]
    drift: tuple[ClusterMapDrift, ...]


def build_cluster_map(
    tracks: Sequence[ClusterMapTrack],
    library_sonara: Sequence[Mapping[str, object]],
) -> ClusterMap:
    """Build the cluster map of one seed search.

    ``library_sonara`` holds the ``SonaraFeatureRow.values`` of every current
    SONARA track in the library; it fits the scale of each feature.
    """

    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    from sklearn.ensemble import IsolationForest
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler, normalize

    items = tuple(tracks)
    seeds = np.array([item.seed for item in items], dtype=bool)
    candidates = ~seeds
    if not seeds.any() or not candidates.any():
        raise ValueError("A cluster map needs seed tracks and candidates")
    matrix = np.vstack([np.asarray(item.vector, dtype=np.float64) for item in items])

    core = _unit(matrix[seeds].mean(axis=0))
    similarity = matrix @ core
    residuals = matrix - np.outer(similarity, core)
    # Centred on the candidates, so the angle shows how they differ from each other.
    pca = PCA(n_components=2, random_state=0).fit(residuals[candidates])
    plane = pca.transform(residuals)
    angles = np.arctan2(plane[:, 1], plane[:, 0])
    center_similarity = float(_unit(matrix[candidates].mean(axis=0)) @ core)

    # Unit residual directions make KMeans a cosine clustering.
    directions = normalize(residuals)
    candidate_indices = np.flatnonzero(candidates)
    labels = KMeans(n_clusters=CLUSTER_COUNT, n_init=10, random_state=0).fit_predict(
        directions[candidates]
    )
    groups = sorted(
        (candidate_indices[labels == label] for label in np.unique(labels)),
        key=lambda members: -float(np.median(similarity[members])),
    )
    cluster_of: list[int | None] = [None] * len(items)
    for position, members in enumerate(groups):
        for index in members:
            cluster_of[index] = position
    silhouette = float(silhouette_score(directions[candidates], labels, metric="cosine"))

    scaler = StandardScaler().fit(_feature_matrix(library_sonara))
    raw = _feature_matrix([item.sonara for item in items])
    scaled = scaler.transform(raw)
    forest = IsolationForest(random_state=0).fit(scaled)
    outliers = forest.predict(scaled) == -1
    outlier_scores = forest.score_samples(scaled)
    deviation = scaled - scaled.mean(axis=0)

    points = tuple(
        ClusterMapPoint(
            track=item.track,
            seed=bool(seeds[index]),
            similarity=float(similarity[index]),
            angle=float(angles[index]),
            cluster=cluster_of[index],
            outlier=bool(outliers[index]),
            outlier_score=float(outlier_scores[index]),
            outlier_features=(
                _top_features(raw[index], deviation[index])
                if outliers[index]
                else ()
            ),
        )
        for index, item in enumerate(items)
    )
    clusters = tuple(
        ClusterMapCluster(
            size=int(members.size),
            median_similarity=float(np.median(similarity[members])),
            representative_track_id=items[
                _representative(members, directions)
            ].track.track_id,
            profile=_profile(scaled[members]),
            maest_genres=_genre_shares(members, items),
        )
        for members in groups
    )
    shift = scaled[candidates].mean(axis=0) - scaled[seeds].mean(axis=0)
    drift = tuple(
        ClusterMapDrift(feature=feature, group=group, delta=float(shift[position]))
        for position, (feature, group) in sorted(
            enumerate(FEATURE_GROUPS.items()),
            key=lambda entry: -abs(shift[entry[0]]),
        )
    )
    return ClusterMap(
        silhouette=silhouette,
        angle_variance_kept=float(np.sum(pca.explained_variance_ratio_)),
        center_similarity=center_similarity,
        points=points,
        clusters=clusters,
        drift=drift,
    )


def _unit(vector: np.ndarray) -> np.ndarray:
    return vector / np.linalg.norm(vector)


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


def _top_features(
    values: np.ndarray,
    deviation: np.ndarray,
) -> tuple[ClusterMapFeatureValue, ...]:
    """The features that lie farthest from the map's mean, farthest first."""

    names = tuple(FEATURE_GROUPS.items())
    return tuple(
        ClusterMapFeatureValue(
            feature=names[position][0],
            group=names[position][1],
            value=float(values[position]),
            delta=float(deviation[position]),
        )
        for position in np.argsort(-np.abs(deviation))[:TOP_OUTLIER_FEATURES]
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


def _representative(members: np.ndarray, directions: np.ndarray) -> int:
    """The member whose residual points closest to the cluster's mean direction."""

    member_directions = directions[members]
    return int(members[int(np.argmax(member_directions @ _unit(member_directions.mean(axis=0))))])


def _genre_shares(
    members: np.ndarray,
    items: Sequence[ClusterMapTrack],
) -> tuple[ClusterMapGenreShare, ...]:
    totals: dict[str, float] = {}
    for index in members:
        for genre in items[int(index)].track.maest_genres:
            totals[genre.genre_name] = totals.get(genre.genre_name, 0.0) + float(
                genre.score
            )
    total = sum(totals.values())
    if total <= 0.0:
        return ()
    ranked = sorted(totals.items(), key=lambda entry: (-entry[1], entry[0]))
    return tuple(
        ClusterMapGenreShare(genre_name=name, share=score / total)
        for name, score in ranked[:TOP_GENRES]
    )
