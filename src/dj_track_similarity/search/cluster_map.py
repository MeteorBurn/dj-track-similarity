"""Cluster map of a REFERENCE seed search.

Pure analysis over vectors and SONARA rows the caller has already loaded:
nothing is read from or written to a library. Every point sits on an orbit
around the seed core (radius ``1 - similarity``) at an angle taken from the
leading residual directions; clusters group the candidates' residual
directions in the full layer space and the seeds join them; SONARA evidence,
scaled by the whole library, explains clusters and outliers. Every returned
number is a plain Python ``int`` or ``float``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from typing import Literal

import numpy as np

from ..library_models import TrackSummary
from ..tempo_resolution import (
    LOW_BPM_CONFIDENCE,
    TEMPO_MATCH_WINDOW_BPM,
    best_tempo_distance,
    resolve_tempo_evidence_from_values,
)


MAX_CLUSTERS = 6
POINTS_PER_CLUSTER = 4
SILHOUETTE_FLOOR = 0.15
MILD_SIGMA = 2.5
STRONG_SIGMA = 3.5
TRAIT_MIN_SIGMA = 0.5
TOP_TRAITS = 3
TOP_GENRES = 3
# Octave-aware tempo gaps: half the tempo match window is mild, all of it strong.
TEMPO_MILD_BPM = TEMPO_MATCH_WINDOW_BPM / 2.0
TEMPO_STRONG_BPM = TEMPO_MATCH_WINDOW_BPM
# Residual norm below which a point sits on the core.
ON_CORE_EPSILON = 1e-6
# Trace, eigenvalue or spread at or below which a quantity is numerically zero.
NUMERIC_EPSILON = 1e-12
MAD_TO_SIGMA = 1.4826

# Analysed sonara_features columns and their evidence groups, in response
# order. Left out on purpose: key and chroma (key does not matter here),
# vocal_probability (unreliable), the aggression family, and energy_level
# (duplicates energy_score).
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
    "mfcc_mean_blob": "timbral",
    "energy_score": "perceptual",
    "danceability_score": "perceptual",
    "valence_score": "perceptual",
    "acousticness_score": "perceptual",
    "mood_happy_score": "mood",
    "mood_aggressive_score": "mood",
    "mood_relaxed_score": "mood",
    "mood_sad_score": "mood",
}
_TEMPO_FEATURE = "detected_bpm"
_TIMBRE_FEATURE = "mfcc_mean_blob"
_MFCC_SIZE = 13
# Features measured by their linear distance to the seeds' range.
_LINEAR_FEATURES = tuple(
    feature
    for feature in SONARA_FEATURE_GROUPS
    if feature not in (_TEMPO_FEATURE, _TIMBRE_FEATURE)
)

AnomalySeverity = Literal["mild", "strong"]


@dataclass(frozen=True, slots=True)
class ClusterMapTrack:
    """One map input: seeds first in request order, then candidates by rank.

    ``vector`` is the stored unit-L2 row of the searched family and layer and
    is used as stored. ``sonara`` is the track's ``SonaraFeatureRow.values``,
    or ``None`` when the track has no current SONARA row.
    """

    track: TrackSummary
    seed: bool
    vector: np.ndarray
    sonara: Mapping[str, object] | None


@dataclass(frozen=True, slots=True)
class ClusterMapReason:
    """One SONARA feature on which a candidate leaves the seeds' range.

    ``z`` is the distance in library sigma. ``delta`` is the signed distance
    to the range in native units (positive above it), except for tempo, where
    it is the octave-aware gap in BPM, and timbre, where it equals ``z`` and
    there is no single value or range.
    """

    feature: str
    group: str
    value: float | None
    reference_low: float | None
    reference_high: float | None
    delta: float
    z: float
    severity: AnomalySeverity


@dataclass(frozen=True, slots=True)
class ClusterMapPoint:
    """One map point, in input order; ``angle`` is in radians."""

    track: TrackSummary
    seed: bool
    similarity: float
    angle: float
    cluster: int
    has_sonara: bool
    anomalies: tuple[ClusterMapReason, ...]


@dataclass(frozen=True, slots=True)
class ClusterMapTrait:
    """How the cluster's candidates differ from the other candidates, in sigma.

    ``rest_median`` is the median of the candidates outside this cluster. Both
    medians cover candidates with SONARA only; the seeds are the core.
    """

    feature: str
    group: str
    cluster_median: float
    rest_median: float
    delta: float


@dataclass(frozen=True, slots=True)
class ClusterMapGenreShare:
    """A full MAEST label's share of the cluster's summed genre scores.

    Scores come from the cluster's candidates, or all members if it has none.
    """

    genre_name: str
    share: float


@dataclass(frozen=True, slots=True)
class ClusterMapCluster:
    """``size`` counts every member, joined seeds included.

    ``median_similarity`` covers the candidates alone unless there are none.
    """

    size: int
    median_similarity: float
    representative_track_id: int
    traits: tuple[ClusterMapTrait, ...]
    maest_genres: tuple[ClusterMapGenreShare, ...]


@dataclass(frozen=True, slots=True)
class ClusterMapFeature:
    """One analysed feature: library sigma, the seeds' range, median gaps to it.

    Timbre distances are already in sigma, so timbre reports a scale of 1.0
    and no range.
    """

    feature: str
    group: str
    library_scale: float | None
    core_low: float | None
    core_high: float | None
    results_gap: float | None
    library_gap: float | None


@dataclass(frozen=True, slots=True)
class ClusterMap:
    """``silhouette`` is the best one tried, ``None`` when none was tried.

    Clusters are ordered nearest to the core first; ``point.cluster`` indexes
    that order.
    """

    silhouette: float | None
    angle_variance_kept: float | None
    points: tuple[ClusterMapPoint, ...]
    clusters: tuple[ClusterMapCluster, ...]
    features: tuple[ClusterMapFeature, ...]


@dataclass(frozen=True, slots=True)
class _Evidence:
    """One analysed feature measured against the seeds and the library.

    ``values`` and ``gaps`` hold one entry per map point and ``library_gaps``
    one per library row; NaN marks a missing value or an unknown gap.
    """

    feature: str
    group: str
    scale: float | None
    low: float | None
    high: float | None
    values: np.ndarray
    gaps: np.ndarray
    library_gaps: np.ndarray


def build_cluster_map(
    tracks: Sequence[ClusterMapTrack],
    library_sonara: Sequence[Mapping[str, object]],
) -> ClusterMap:
    """Build the cluster map of one seed search.

    The core is the normalised mean of the seed vectors, the query vector
    ``SimilaritySearch.search`` ranks by, so ``similarity`` repeats the search
    score. ``library_sonara`` holds the ``SonaraFeatureRow.values`` of every
    current SONARA track in the library and sets each feature's scale.
    """

    items = tuple(tracks)
    seeds = np.array([bool(item.seed) for item in items], dtype=bool)
    if not seeds.any():
        raise ValueError("A cluster map needs at least one seed track")
    matrix = _stacked_vectors(items)
    core = matrix[seeds].mean(axis=0)
    core_norm = float(np.linalg.norm(core))
    if not core_norm > 0.0:
        raise ValueError("Seed vectors average to zero; the core is undefined")
    core /= core_norm
    similarity = matrix @ core
    residuals = matrix - np.outer(similarity, core)
    radii = np.linalg.norm(residuals, axis=1)
    off_core = radii >= ON_CORE_EPSILON
    directions = np.zeros_like(residuals)
    directions[off_core] = residuals[off_core] / radii[off_core, None]

    angles, angle_variance_kept = _orbit_angles(residuals, off_core)
    labels, silhouette = _cluster_labels(matrix, directions, off_core, seeds)
    groups = sorted(
        (np.flatnonzero(labels == label) for label in np.unique(labels)),
        key=lambda members: _cluster_rank(members, seeds, similarity),
    )
    cluster_of = np.zeros(len(items), dtype=np.int64)
    for position, members in enumerate(groups):
        cluster_of[members] = position

    evidence, tempo_reliability = _sonara_evidence(items, seeds, library_sonara)
    points = tuple(
        ClusterMapPoint(
            track=item.track,
            seed=bool(seeds[index]),
            similarity=float(similarity[index]),
            angle=float(angles[index]),
            cluster=int(cluster_of[index]),
            has_sonara=item.sonara is not None,
            anomalies=(
                ()
                if seeds[index] or item.sonara is None
                else _anomalies(index, evidence, float(tempo_reliability[index]))
            ),
        )
        for index, item in enumerate(items)
    )
    candidates = ~seeds
    clusters = tuple(
        ClusterMapCluster(
            size=int(members.size),
            median_similarity=float(np.median(similarity[ranked])),
            representative_track_id=items[
                _representative(members, directions, off_core, seeds)
            ].track.track_id,
            traits=_traits(ranked, evidence, candidates),
            maest_genres=_genre_shares(ranked, items),
        )
        for members, ranked in (
            (group, _ranked_members(group, seeds)) for group in groups
        )
    )
    return ClusterMap(
        silhouette=silhouette,
        angle_variance_kept=angle_variance_kept,
        points=points,
        clusters=clusters,
        features=tuple(_feature_summary(item, candidates) for item in evidence),
    )


def _stacked_vectors(items: Sequence[ClusterMapTrack]) -> np.ndarray:
    vectors = [
        np.asarray(item.vector, dtype=np.float64).reshape(-1)
        for item in items
    ]
    dimension = vectors[0].size
    if dimension == 0 or any(vector.size != dimension for vector in vectors):
        raise ValueError("Cluster map vectors must share one positive dimension")
    matrix = np.vstack(vectors)
    if not np.isfinite(matrix).all():
        raise ValueError("Cluster map vectors must be finite")
    return matrix


def _orbit_angles(
    residuals: np.ndarray,
    off_core: np.ndarray,
) -> tuple[np.ndarray, float | None]:
    """Angles in the plane of the two leading residual directions.

    The Gram matrix is deliberately uncentred: the core is the orbit's
    origin, so the plane keeps the residuals' offset from it.
    """

    count = residuals.shape[0]
    gram = residuals @ residuals.T
    trace = float(np.trace(gram))
    if trace <= NUMERIC_EPSILON:
        return np.zeros(count), None
    eigenvalues, eigenvectors = np.linalg.eigh(gram)
    leading = np.maximum(eigenvalues[::-1][:2], 0.0)
    scores = np.zeros((count, 2))
    for axis, eigenvalue in enumerate(leading):
        if eigenvalue <= NUMERIC_EPSILON:
            continue
        column = eigenvectors[:, count - 1 - axis] * math.sqrt(eigenvalue)
        if column[int(np.argmax(np.abs(column)))] < 0.0:
            column = -column
        scores[:, axis] = column
    angles = np.where(off_core, np.arctan2(scores[:, 1], scores[:, 0]), 0.0)
    return angles, float(leading.sum() / trace)


def _cluster_labels(
    matrix: np.ndarray,
    directions: np.ndarray,
    off_core: np.ndarray,
    seeds: np.ndarray,
) -> tuple[np.ndarray, float | None]:
    """Cluster labels for every point plus the best silhouette tried.

    Only off-core candidates are clustered: a seed is the core, not a style of
    its own. Off-core seeds then join the cluster whose normalised mean
    candidate direction is closest to their own direction; on-core points,
    which have none, join the cluster whose normalised mean full candidate
    vector is closest to their full vector.
    """

    labels = np.zeros(matrix.shape[0], dtype=np.int64)
    fitted_indices = np.flatnonzero(off_core & ~seeds)
    fitted, silhouette = _fit_directions(directions[fitted_indices])
    if fitted is None:
        return labels, silhouette
    labels[fitted_indices] = fitted
    values = np.unique(fitted)
    members = [fitted_indices[fitted == value] for value in values]
    off_core_seeds = np.flatnonzero(off_core & seeds)
    if off_core_seeds.size:
        labels[off_core_seeds] = values[
            _nearest_cluster(off_core_seeds, directions, members)
        ]
    on_core = np.flatnonzero(~off_core)
    if on_core.size:
        labels[on_core] = values[_nearest_cluster(on_core, matrix, members)]
    return labels, silhouette


def _nearest_cluster(
    points: np.ndarray,
    space: np.ndarray,
    members: Sequence[np.ndarray],
) -> np.ndarray:
    """Per point, the member group whose normalised mean row is most cosine-similar."""

    centres = np.vstack([space[indices].mean(axis=0) for indices in members])
    centres /= np.linalg.norm(centres, axis=1, keepdims=True)
    return np.argmax(space[points] @ centres.T, axis=1)


def _ranked_members(members: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """The members a cluster is ranked by: its candidates, or all if it has none."""

    candidates = members[~seeds[members]]
    return candidates if candidates.size else members


def _cluster_rank(
    members: np.ndarray,
    seeds: np.ndarray,
    similarity: np.ndarray,
) -> tuple[float, int, int]:
    """Sort key: nearest to the core first, then larger, then earlier."""

    ranked = _ranked_members(members, seeds)
    return -float(np.median(similarity[ranked])), -int(ranked.size), int(ranked[0])


def _fit_directions(
    directions: np.ndarray,
) -> tuple[np.ndarray | None, float | None]:
    """KMeans over unit residual directions, k chosen by cosine silhouette.

    ``None`` labels mean one cluster: too few points or distinct directions
    to try k >= 2, or no k reaching ``SILHOUETTE_FLOOR``.
    """

    max_k = min(MAX_CLUSTERS, directions.shape[0] // POINTS_PER_CLUSTER)
    if max_k >= 2:
        max_k = min(max_k, np.unique(directions, axis=0).shape[0])
    if max_k < 2:
        return None, None
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    best_labels: np.ndarray | None = None
    best_score: float | None = None
    for k in range(2, max_k + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=0).fit_predict(
            directions
        )
        if np.unique(labels).size < 2:
            continue
        score = float(silhouette_score(directions, labels, metric="cosine"))
        if best_score is None or score > best_score:
            best_labels, best_score = labels, score
    if best_score is None or best_score < SILHOUETTE_FLOOR:
        return None, best_score
    return best_labels, best_score


def _representative(
    members: np.ndarray,
    directions: np.ndarray,
    off_core: np.ndarray,
    seeds: np.ndarray,
) -> int:
    """The off-core member nearest the members' mean direction, candidates first."""

    directed = members[off_core[members]]
    if directed.size == 0:
        return int(members[0])
    eligible = directed[~seeds[directed]]
    if eligible.size == 0:
        eligible = directed
    mean_direction = directions[directed].mean(axis=0)
    norm = float(np.linalg.norm(mean_direction))
    if norm < ON_CORE_EPSILON:
        return int(eligible[0])
    cosines = directions[eligible] @ (mean_direction / norm)
    return int(eligible[int(np.argmax(cosines))])


def _sonara_evidence(
    items: Sequence[ClusterMapTrack],
    seeds: np.ndarray,
    library_sonara: Sequence[Mapping[str, object]],
) -> tuple[list[_Evidence], np.ndarray]:
    """Per-feature evidence plus each map point's tempo evidence reliability."""

    map_columns, map_mfcc, tempo_reliability = _sonara_columns(
        [item.sonara for item in items],
        [item.track.tag_bpm for item in items],
    )
    library_columns, library_mfcc, _ = _sonara_columns(
        library_sonara,
        [None] * len(library_sonara),
    )
    evidence = [
        _timbre_evidence(group, map_mfcc, library_mfcc, seeds)
        if feature == _TIMBRE_FEATURE
        else _scalar_evidence(
            feature,
            group,
            map_columns[feature],
            library_columns[feature],
            seeds,
        )
        for feature, group in SONARA_FEATURE_GROUPS.items()
    ]
    return evidence, tempo_reliability


def _sonara_columns(
    rows: Sequence[Mapping[str, object] | None],
    tag_bpms: Sequence[float | None],
) -> tuple[dict[str, np.ndarray], np.ndarray, np.ndarray]:
    """Scalar columns, MFCC 1-12 and tempo reliability, NaN where missing.

    Tempo is the resolved evidence BPM. MFCC coefficient 0 is dropped because
    it follows level rather than timbre.
    """

    count = len(rows)
    missing = (None,) * len(_LINEAR_FEATURES)
    missing_mfcc = (math.nan,) * _MFCC_SIZE
    linear_rows: list[object] = []
    mfcc_rows: list[object] = []
    bpm = np.full(count, math.nan)
    reliability = np.zeros(count)
    for index, (row, tag_bpm) in enumerate(zip(rows, tag_bpms)):
        if row is None:
            linear_rows.append(missing)
            mfcc_rows.append(missing_mfcc)
            continue
        linear_rows.append([row.get(feature) for feature in _LINEAR_FEATURES])
        vector = row.get(_TIMBRE_FEATURE)
        mfcc_rows.append(missing_mfcc if vector is None else vector)
        evidence = resolve_tempo_evidence_from_values(row, tag_bpm)
        if evidence.bpm is not None:
            bpm[index] = evidence.bpm
            reliability[index] = evidence.reliability
    # float64 conversion turns None into NaN.
    linear = np.array(linear_rows, dtype=np.float64).reshape(
        count, len(_LINEAR_FEATURES)
    )
    mfcc = np.array(mfcc_rows, dtype=np.float64).reshape(count, _MFCC_SIZE)[:, 1:]
    linear[~np.isfinite(linear)] = math.nan
    mfcc[~np.isfinite(mfcc)] = math.nan
    columns = {_TEMPO_FEATURE: bpm, **dict(zip(_LINEAR_FEATURES, linear.T))}
    return columns, mfcc, reliability


def _scalar_evidence(
    feature: str,
    group: str,
    values: np.ndarray,
    library_values: np.ndarray,
    seeds: np.ndarray,
) -> _Evidence:
    scale = _robust_scale(library_values)
    seed_values = values[seeds & np.isfinite(values)]
    if seed_values.size == 0:
        return _Evidence(
            feature=feature,
            group=group,
            scale=scale,
            low=None,
            high=None,
            values=values,
            gaps=_unknown(values.size),
            library_gaps=_unknown(library_values.size),
        )
    low = float(seed_values.min())
    high = float(seed_values.max())
    return _Evidence(
        feature=feature,
        group=group,
        scale=scale,
        low=low,
        high=high,
        values=values,
        gaps=_range_gaps(feature, values, low, high),
        library_gaps=np.abs(_range_gaps(feature, library_values, low, high)),
    )


def _timbre_evidence(
    group: str,
    mfcc: np.ndarray,
    library_mfcc: np.ndarray,
    seeds: np.ndarray,
) -> _Evidence:
    """RMS over MFCC 1-12 of each coefficient's gap to the seeds' range in sigma."""

    scales = [_robust_scale(column) for column in library_mfcc.T]
    usable = np.array([scale is not None for scale in scales], dtype=bool)
    seed_rows = mfcc[seeds & np.isfinite(mfcc).all(axis=1)]
    if not usable.any() or seed_rows.shape[0] == 0:
        unknown = _unknown(mfcc.shape[0])
        return _Evidence(
            feature=_TIMBRE_FEATURE,
            group=group,
            scale=1.0 if usable.any() else None,
            low=None,
            high=None,
            values=unknown,
            gaps=unknown,
            library_gaps=_unknown(library_mfcc.shape[0]),
        )
    sigma = np.array([scale for scale in scales if scale is not None])
    low = seed_rows.min(axis=0)[usable]
    high = seed_rows.max(axis=0)[usable]
    distances = _timbre_distances(mfcc[:, usable], low, high, sigma)
    return _Evidence(
        feature=_TIMBRE_FEATURE,
        group=group,
        scale=1.0,
        low=None,
        high=None,
        values=distances,
        gaps=distances,
        library_gaps=_timbre_distances(library_mfcc[:, usable], low, high, sigma),
    )


def _robust_scale(values: np.ndarray) -> float | None:
    """Library sigma: MAD x 1.4826, the standard deviation when the MAD is zero."""

    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None
    scale = float(np.median(np.abs(finite - np.median(finite)))) * MAD_TO_SIGMA
    if scale <= NUMERIC_EPSILON:
        scale = float(np.std(finite))
    return scale if scale > NUMERIC_EPSILON else None


def _range_gaps(
    feature: str,
    values: np.ndarray,
    low: float,
    high: float,
) -> np.ndarray:
    """Distance to ``[low, high]``: 0 inside, signed native units outside.

    Tempo uses the octave-aware gap instead, which is never negative.
    """

    if feature == _TEMPO_FEATURE:
        return np.array(
            [_tempo_gap(value, low, high) for value in values.tolist()],
            dtype=np.float64,
        )
    return np.minimum(values - low, 0.0) + np.maximum(values - high, 0.0)


def _tempo_gap(bpm: float, low: float, high: float) -> float:
    """0 inside the range at x1, x2 or x1/2, else the octave-aware distance."""

    if math.isnan(bpm):
        return math.nan
    if any(low <= option <= high for option in (bpm, bpm * 2.0, bpm / 2.0)):
        return 0.0
    return min(best_tempo_distance(bpm, low), best_tempo_distance(bpm, high))


def _timbre_distances(
    mfcc: np.ndarray,
    low: np.ndarray,
    high: np.ndarray,
    sigma: np.ndarray,
) -> np.ndarray:
    ratios = (np.maximum(low - mfcc, 0.0) + np.maximum(mfcc - high, 0.0)) / sigma
    return np.sqrt(np.mean(ratios * ratios, axis=1))


def _unknown(size: int) -> np.ndarray:
    return np.full(size, math.nan)


def _anomalies(
    index: int,
    evidence: Sequence[_Evidence],
    tempo_reliability: float,
) -> tuple[ClusterMapReason, ...]:
    """The strongest out-of-range reason per group, strongest first."""

    strongest: dict[str, ClusterMapReason] = {}
    for item in evidence:
        gap = float(item.gaps[index])
        if item.scale is None or math.isnan(gap):
            continue
        z = abs(gap) / item.scale
        if item.feature == _TEMPO_FEATURE:
            severity = _severity(gap, TEMPO_MILD_BPM, TEMPO_STRONG_BPM)
            if severity == "strong" and tempo_reliability < LOW_BPM_CONFIDENCE:
                severity = "mild"
        else:
            severity = _severity(z, MILD_SIGMA, STRONG_SIGMA)
        if severity is None:
            continue
        reason = ClusterMapReason(
            feature=item.feature,
            group=item.group,
            value=(
                None
                if item.feature == _TIMBRE_FEATURE
                else float(item.values[index])
            ),
            reference_low=item.low,
            reference_high=item.high,
            delta=gap,
            z=z,
            severity=severity,
        )
        current = strongest.get(item.group)
        if current is None or _strength(reason) > _strength(current):
            strongest[item.group] = reason
    return tuple(
        sorted(
            strongest.values(),
            key=lambda reason: (reason.severity != "strong", -reason.z),
        )
    )


def _severity(amount: float, mild: float, strong: float) -> AnomalySeverity | None:
    if amount >= strong:
        return "strong"
    if amount >= mild:
        return "mild"
    return None


def _strength(reason: ClusterMapReason) -> tuple[bool, float]:
    return reason.severity == "strong", reason.z


def _traits(
    members: np.ndarray,
    evidence: Sequence[_Evidence],
    candidates: np.ndarray,
) -> tuple[ClusterMapTrait, ...]:
    """The cluster's candidates against the candidates outside it; none if no rest."""

    rest = candidates.copy()
    rest[members] = False
    traits: list[ClusterMapTrait] = []
    for item in evidence:
        if item.scale is None:
            continue
        cluster = item.values[members]
        cluster = cluster[np.isfinite(cluster)]
        others = item.values[rest]
        others = others[np.isfinite(others)]
        if cluster.size == 0 or others.size == 0:
            continue
        cluster_median = float(np.median(cluster))
        rest_median = float(np.median(others))
        delta = (cluster_median - rest_median) / item.scale
        if abs(delta) >= TRAIT_MIN_SIGMA:
            traits.append(
                ClusterMapTrait(
                    feature=item.feature,
                    group=item.group,
                    cluster_median=cluster_median,
                    rest_median=rest_median,
                    delta=delta,
                )
            )
    traits.sort(key=lambda trait: -abs(trait.delta))
    return tuple(traits[:TOP_TRAITS])


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


def _feature_summary(item: _Evidence, candidates: np.ndarray) -> ClusterMapFeature:
    results = np.abs(item.gaps[candidates])
    results = results[np.isfinite(results)]
    library = item.library_gaps[np.isfinite(item.library_gaps)]
    return ClusterMapFeature(
        feature=item.feature,
        group=item.group,
        library_scale=item.scale,
        core_low=item.low,
        core_high=item.high,
        results_gap=float(np.median(results)) if results.size else None,
        library_gap=float(np.median(library)) if library.size else None,
    )
