"""Reference-centred SONARA evidence for one model ranking.

The model supplies only the candidates, their order and its pool (the tracks
it could have returned, a second percentile background by membership alone).
Everything measured here comes from SONARA and from scales fitted on a fixed
background sample of the library, never on the returned tracks or the pool, so
one output cannot calibrate its own agreement and every model and layer is
judged on the same scale for the same references.

The distance of a track is D = sqrt(sum_f W_f * d_f^2 / sum_f W_f): d_f is the
facet's weighted RMS of per-descriptor z-differences from the median reference,
divided by what a typical library track scores on that facet. The explanation
is the exact split of the same D^2 into descriptor contributions, and the map
radius is the same D.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from ..library_models import TrackSummary
from .sonara_descriptors import (
    DESCRIPTORS, FACET_KEYS, FACET_OF, FACETS, describe,
)

BACKGROUND_SIZE = 6000
# The model's pool — every track it could have returned — is compared through
# a fixed sample of this size, so a small pool is used whole.
POOL_SAMPLE = 2000
RING_PERCENTILES = (1, 5, 10, 25, 50)
GRADIENT_BINS = ((1, 20), (21, 50), (51, 100), (101, 200))
GRADIENT_DEPTH = 200
# Fixed before any search, identical for every model and layer.
SHIFT_MIN_DELTA = 0.5
SHIFT_MAX_P = 0.01
_FACET_WEIGHTS = np.array([facet.weight for facet in FACETS])
_ANCHORS = np.array([-math.pi / 2 + 2 * math.pi * k / len(FACETS) for k in range(len(FACETS))])
_CURVE_POINTS = 300


@dataclass(frozen=True, slots=True)
class ClusterMapTrack:
    track: TrackSummary
    seed: bool
    core: Mapping[str, object]
    timeline: Mapping[str, object] | None
    similarity: float | None = None
    rank: int | None = None


@dataclass(frozen=True, slots=True)
class ClusterMapFacet:
    key: str
    label: str
    weight: float
    description: str
    explained_variance: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ClusterMapDescriptor:
    key: str
    facet: int
    label: str
    unit: str
    note: str
    weight: float
    library_quantiles: tuple[float | None, ...]


@dataclass(frozen=True, slots=True)
class ClusterMapRing:
    percentile: int
    distance: float


@dataclass(frozen=True, slots=True)
class ClusterMapReference:
    centre: tuple[float | None, ...]
    core_distance: float
    rings: tuple[ClusterMapRing, ...]
    facet_rings: tuple[tuple[ClusterMapRing, ...], ...]
    facet_correlation: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class ClusterMapEvidence:
    distance: float | None
    percentile: float | None
    pool_percentile: float | None
    facet_distance: tuple[float | None, ...]
    facet_percentile: tuple[float | None, ...]
    pool_facet_percentile: tuple[float | None, ...]
    facet_share: tuple[float, ...]
    contribution: tuple[float, ...]
    delta: tuple[float | None, ...]
    rarity: tuple[float | None, ...]
    angle: float
    focus: float
    nearest_reference_id: int | None
    nearest_distance: float | None


@dataclass(frozen=True, slots=True)
class ClusterMapCurves:
    duration: float | None
    energy: tuple[float, ...]
    energy_hop: float
    loudness: tuple[float, ...]
    loudness_hop: float
    tempo_times: tuple[float, ...]
    tempo_values: tuple[float, ...]
    segments: tuple[tuple[float, float, float], ...]
    mode_runs: tuple[tuple[float, float, bool], ...]


@dataclass(frozen=True, slots=True)
class ClusterMapPoint:
    track: TrackSummary
    seed: bool
    rank: int | None
    similarity: float | None
    values: tuple[float | None, ...]
    scores: tuple[float | None, ...]
    evidence: ClusterMapEvidence
    tonic: str
    tonic_mode: str
    key_camelot: str | None
    key_confidence: float | None
    bpm_confidence: float | None
    curves: ClusterMapCurves | None


@dataclass(frozen=True, slots=True)
class ClusterMapPreservation:
    median: float | None
    mean: float | None
    p: float | None
    q: float | None


@dataclass(frozen=True, slots=True)
class ClusterMapGradientBin:
    first: int
    last: int
    facet_percentile: tuple[float | None, ...]
    percentile: float | None


@dataclass(frozen=True, slots=True)
class ClusterMapShift:
    descriptor: int
    median: float
    same_side: float
    p: float
    toward_library: bool


@dataclass(frozen=True, slots=True)
class ClusterMapSummary:
    candidate_count: int
    depth: int
    preservation: tuple[ClusterMapPreservation, ...]
    pool_size: int
    pool_count: int
    pool_preservation: tuple[ClusterMapPreservation, ...]
    gradient: tuple[ClusterMapGradientBin, ...]
    shifts: tuple[ClusterMapShift, ...]
    rank_correlation: float | None
    facet_rank_correlation: tuple[float | None, ...]


@dataclass(frozen=True, slots=True)
class ClusterMap:
    facets: tuple[ClusterMapFacet, ...]
    descriptors: tuple[ClusterMapDescriptor, ...]
    background_count: int
    library_count: int
    reference: ClusterMapReference
    points: tuple[ClusterMapPoint, ...]
    summary: ClusterMapSummary


def descriptor_matrix(
    rows: Sequence[tuple[Mapping[str, object], Mapping[str, object] | None]],
) -> np.ndarray:
    """Descriptor rows of (SONARA Core values, Timeline) pairs, in ``DESCRIPTORS`` order."""

    return np.vstack([describe(core, timeline)[0] for core, timeline in rows])


class ClusterMapBackground:
    """Library scales fitted once on a fixed sample; reused for every search."""

    def __init__(self, rows: Sequence[tuple[Mapping[str, object], Mapping[str, object] | None]], library_count: int):
        from sklearn.decomposition import PCA
        from sklearn.preprocessing import QuantileTransformer

        if len(rows) < 50:
            raise ValueError("The cluster map needs at least 50 library tracks with SONARA")
        X = descriptor_matrix(rows)
        # Normal scores against the library: 1 unit = one library standard
        # deviation for any skewed or bounded descriptor.
        self.transform = QuantileTransformer(
            n_quantiles=min(1000, len(rows)), output_distribution="normal", subsample=len(rows), random_state=0,
        ).fit(X)
        self.Z = self.scores(X)
        filled = np.where(np.isfinite(self.Z), self.Z, 0.0)
        weights = np.zeros(len(DESCRIPTORS))
        explained = []
        for index in range(len(FACETS)):
            columns = np.flatnonzero(FACET_OF == index)
            if len(columns) > 1:
                with np.errstate(invalid="ignore", divide="ignore"):
                    correlation = np.nan_to_num(np.corrcoef(filled[:, columns], rowvar=False))
                # A constant descriptor still correlates fully with itself.
                np.fill_diagonal(correlation, 1.0)
                # Near-duplicates share one vote instead of multiplying it.
                facet_weights = 1.0 / (correlation**2).sum(axis=1)
                pca = PCA(n_components=min(3, len(columns))).fit(filled[:, columns])
                explained.append(tuple(float(v) for v in pca.explained_variance_ratio_))
            else:
                facet_weights = np.ones(1)
                explained.append((1.0,))
            weights[columns] = facet_weights / facet_weights.sum()
        self.weights = weights
        self.explained = tuple(explained)
        self.quantiles = np.nanquantile(X, (0.05, 0.25, 0.5, 0.75, 0.95), axis=0)
        self.count = len(rows)
        self.library_count = library_count

    def scores(self, X: np.ndarray) -> np.ndarray:
        return np.clip(self.transform.transform(np.atleast_2d(X)), -4.0, 4.0)


def build_cluster_map(
    background: ClusterMapBackground,
    tracks: Sequence[ClusterMapTrack],
    *,
    shown: int,
    pool: np.ndarray | None = None,
    pool_size: int = 0,
) -> ClusterMap:
    """Explain the first *shown* candidates; the rest of *tracks* only feed the rank gradient.

    *pool* holds descriptor rows of a fixed sample of the tracks the model could
    have returned. Library percentiles say how close a candidate is; pool
    percentiles say whether the model chose it, since a pool that already sits
    near the references makes any random pick look close to the library.
    """

    from scipy.stats import binomtest, norm, spearmanr

    seeds = [item for item in tracks if item.seed]
    candidates = [item for item in tracks if not item.seed]
    if not seeds or not candidates:
        raise ValueError("A cluster map needs seed tracks and candidates")
    described = [describe(item.core, item.timeline) for item in tracks]
    Z = background.scores(np.vstack([values for values, _ in described]))
    raw = [values for values, _ in described]
    seed_rows = Z[[index for index, item in enumerate(tracks) if item.seed]]
    # The median, not the mean: one reference with a mis-detected value (an
    # octave BPM error) must not drag the centre away from all of them.
    with np.errstate(all="ignore"):
        centre = np.nanmedian(seed_rows, axis=0)
    w = background.weights

    library_facets = _facet_squares(background.Z, centre, w)
    scale = np.nanmedian(library_facets, axis=0)
    scale = np.where(np.isfinite(scale) & (scale > 0), scale, 1.0)
    library_D = _combine(library_facets, scale)
    sorted_D = np.sort(library_D[np.isfinite(library_D)])
    sorted_facets = [np.sort(column[np.isfinite(column)]) for column in library_facets.T]
    sorted_abs = [np.sort(column[np.isfinite(column)]) for column in np.abs(background.Z - centre).T]

    track_facets = _facet_squares(Z, centre, w)
    track_D = _combine(track_facets, scale)
    facet_percentiles = np.array([
        [_percentile(sorted_facets[f], track_facets[i, f]) for f in range(len(FACETS))]
        for i in range(len(tracks))
    ])
    D_percentiles = np.array([_percentile(sorted_D, value) for value in track_D])
    # The pool is read with the same library scales, centre and facet scale:
    # only the background a percentile counts against changes.
    if pool is not None and len(pool):
        pool_facets = _facet_squares(background.scores(pool), centre, w)
        pool_D = _combine(pool_facets, scale)
        sorted_pool_D = np.sort(pool_D[np.isfinite(pool_D)])
        sorted_pool_facets = [np.sort(column[np.isfinite(column)]) for column in pool_facets.T]
    else:
        sorted_pool_D, sorted_pool_facets = np.empty(0), [np.empty(0)] * len(FACETS)
    pool_facet_percentiles = np.array([
        [_percentile(sorted_pool_facets[f], track_facets[i, f]) for f in range(len(FACETS))]
        for i in range(len(tracks))
    ])
    pool_D_percentiles = np.array([_percentile(sorted_pool_D, value) for value in track_D])

    def evidence(index: int) -> ClusterMapEvidence:
        delta = Z[index] - centre
        contribution = np.zeros(len(DESCRIPTORS))
        available = np.isfinite(track_facets[index])
        total_weight = float((_FACET_WEIGHTS * available).sum())
        for f in range(len(FACETS)):
            columns = np.flatnonzero((FACET_OF == f) & np.isfinite(delta))
            known = float(w[columns].sum())
            if known > 0.5 and total_weight > 0:
                contribution[columns] = (
                    _FACET_WEIGHTS[f] / total_weight * w[columns] * delta[columns] ** 2 / known / scale[f]
                )
        total = float(contribution.sum())
        share = np.array([contribution[FACET_OF == f].sum() for f in range(len(FACETS))])
        if total > 0:
            share, contribution = share / total, contribution / total
        vx, vy = float(share @ np.cos(_ANCHORS)), float(share @ np.sin(_ANCHORS))
        nearest: tuple[float, int] | None = None
        for other, item in enumerate(tracks):
            if item.seed and other != index:
                row = _combine(_facet_squares(Z[index:index + 1], Z[other], w), scale)[0]
                if np.isfinite(row) and (nearest is None or row < nearest[0]):
                    nearest = (float(row), item.track.track_id)
        return ClusterMapEvidence(
            distance=_finite(track_D[index]),
            percentile=_finite(D_percentiles[index]),
            pool_percentile=_finite(pool_D_percentiles[index]),
            facet_distance=tuple(_finite(math.sqrt(v / s)) if np.isfinite(v) else None
                                 for v, s in zip(track_facets[index], scale, strict=True)),
            facet_percentile=tuple(_finite(v) for v in facet_percentiles[index]),
            pool_facet_percentile=tuple(_finite(v) for v in pool_facet_percentiles[index]),
            facet_share=tuple(float(v) for v in share),
            contribution=tuple(float(v) for v in contribution),
            delta=tuple(_finite(v) for v in delta),
            rarity=tuple(
                100.0 - _percentile(sorted_abs[j], abs(delta[j])) if np.isfinite(delta[j]) else None
                for j in range(len(DESCRIPTORS))
            ),
            angle=math.atan2(vy, vx),
            focus=math.hypot(vx, vy),
            nearest_reference_id=nearest[1] if nearest else None,
            nearest_distance=nearest[0] if nearest else None,
        )

    shown_indexes = [i for i, item in enumerate(tracks) if item.seed or (item.rank or 0) <= shown]
    points = tuple(
        ClusterMapPoint(
            track=tracks[i].track, seed=tracks[i].seed, rank=tracks[i].rank, similarity=tracks[i].similarity,
            values=tuple(_finite(v) for v in raw[i]), scores=tuple(_finite(v) for v in Z[i]),
            evidence=evidence(i), tonic=described[i][1].tonic, tonic_mode=described[i][1].mode,
            key_camelot=_text(tracks[i].core.get("detected_key_camelot")),
            key_confidence=_finite(tracks[i].core.get("key_confidence")),
            bpm_confidence=_finite(tracks[i].core.get("bpm_confidence")),
            curves=_curves(tracks[i].core, tracks[i].timeline),
        )
        for i in shown_indexes
    )

    ranked = sorted((i for i, item in enumerate(tracks) if not item.seed), key=lambda i: tracks[i].rank or 0)
    top = [i for i in ranked if (tracks[i].rank or 0) <= shown]

    def preservation(percentiles: np.ndarray) -> tuple[ClusterMapPreservation, ...]:
        rows: list[tuple[float | None, float | None, float | None]] = []
        for f in range(len(FACETS)):
            finite = percentiles[top, f][np.isfinite(percentiles[top, f])] / 100.0
            if not len(finite):
                rows.append((None, None, None))
                continue
            # Random picks from the background would spread uniformly over 0..100.
            z = (finite.mean() - 0.5) / math.sqrt(1 / (12 * len(finite)))
            rows.append((float(np.median(finite) * 100), float(finite.mean() * 100), float(norm.cdf(z))))
        q = _benjamini_hochberg([p for _, _, p in rows])
        return tuple(
            ClusterMapPreservation(median, mean, p, q_value)
            for (median, mean, p), q_value in zip(rows, q, strict=True)
        )

    gradient = []
    for first, last in GRADIENT_BINS:
        members = [i for i in ranked if first <= (tracks[i].rank or 0) <= last]
        if members:
            gradient.append(ClusterMapGradientBin(
                first=first, last=max(tracks[i].rank or 0 for i in members),
                facet_percentile=tuple(_nanmedian(facet_percentiles[members, f]) for f in range(len(FACETS))),
                percentile=_nanmedian(D_percentiles[members]),
            ))
    shifts = []
    deltas = Z[top] - centre
    for j in range(len(DESCRIPTORS)):
        column = deltas[:, j][np.isfinite(deltas[:, j])]
        if len(column) < 3 or not np.isfinite(centre[j]):
            continue
        median = float(np.median(column))
        above = int((column > 0).sum())
        p = float(binomtest(above, len(column), 0.5).pvalue)
        if abs(median) >= SHIFT_MIN_DELTA and p < SHIFT_MAX_P:
            shifts.append(ClusterMapShift(
                descriptor=j, median=median, same_side=max(above, len(column) - above) / len(column), p=p,
                toward_library=bool(np.sign(median) == -np.sign(centre[j])),
            ))
    similarities = np.array([tracks[i].similarity or 0.0 for i in ranked])

    def rank_rho(values: np.ndarray) -> float | None:
        ok = np.isfinite(values)
        if ok.sum() < 6:
            return None
        return _finite(spearmanr(similarities[ok], -values[ok]).statistic)

    library_normalized = np.sqrt(np.where(np.isfinite(library_facets), library_facets, 0.0) / scale)
    correlation = np.nan_to_num(np.corrcoef(library_normalized, rowvar=False))
    seed_distances = [track_D[i] for i, item in enumerate(tracks) if item.seed and np.isfinite(track_D[i])]
    return ClusterMap(
        facets=tuple(
            ClusterMapFacet(f.key, f.label, f.weight, f.description, background.explained[k])
            for k, f in enumerate(FACETS)
        ),
        descriptors=tuple(
            ClusterMapDescriptor(
                d.key, FACET_KEYS.index(d.facet), d.label, d.unit, d.note, float(w[j]),
                tuple(_finite(v) for v in background.quantiles[:, j]),
            )
            for j, d in enumerate(DESCRIPTORS)
        ),
        background_count=background.count,
        library_count=background.library_count,
        reference=ClusterMapReference(
            centre=tuple(_finite(v) for v in centre),
            core_distance=float(np.median(seed_distances)) if seed_distances else 0.0,
            rings=_rings(sorted_D),
            facet_rings=tuple(_rings(np.sqrt(column / scale[f])) for f, column in enumerate(sorted_facets)),
            facet_correlation=tuple(tuple(float(v) for v in row) for row in correlation),
        ),
        points=points,
        summary=ClusterMapSummary(
            candidate_count=len(top), depth=len(ranked),
            preservation=preservation(facet_percentiles),
            pool_size=pool_size,
            pool_count=0 if pool is None else len(pool),
            pool_preservation=preservation(pool_facet_percentiles),
            gradient=tuple(gradient),
            shifts=tuple(sorted(shifts, key=lambda item: -abs(item.median))),
            rank_correlation=rank_rho(D_percentiles[ranked]),
            facet_rank_correlation=tuple(rank_rho(facet_percentiles[ranked, f]) for f in range(len(FACETS))),
        ),
    )


def _facet_squares(Z: np.ndarray, centre: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Weighted mean squared z-difference per facet, over the descriptors measured."""

    squares = (Z - centre) ** 2
    valid = np.isfinite(squares)
    out = np.full((Z.shape[0], len(FACETS)), np.nan)
    for f in range(len(FACETS)):
        columns = FACET_OF == f
        known = valid[:, columns] @ weights[columns]
        total = np.where(valid[:, columns], squares[:, columns], 0.0) @ weights[columns]
        # A facet with under half of its weight measured stays unknown.
        out[:, f] = np.where(known > 0.5, total / np.where(known > 0, known, 1.0), np.nan)
    return out


def _combine(facet_squares: np.ndarray, scale: np.ndarray) -> np.ndarray:
    normalized = facet_squares / scale
    valid = np.isfinite(normalized)
    weight = valid @ _FACET_WEIGHTS
    total = np.where(valid, normalized, 0.0) @ _FACET_WEIGHTS
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.sqrt(np.where(weight > 0, total / weight, np.nan))


def _percentile(sorted_background: np.ndarray, value: float) -> float:
    """Share of the background strictly closer, in percent."""

    if not np.isfinite(value) or not len(sorted_background):
        return math.nan
    return float(np.searchsorted(sorted_background, value, side="left") / len(sorted_background) * 100)


def _rings(sorted_values: np.ndarray) -> tuple[ClusterMapRing, ...]:
    return tuple(ClusterMapRing(p, float(np.quantile(sorted_values, p / 100))) for p in RING_PERCENTILES)


def _benjamini_hochberg(pvalues: Sequence[float | None]) -> list[float | None]:
    known = sorted((p, i) for i, p in enumerate(pvalues) if p is not None)
    adjusted: list[float | None] = [None] * len(pvalues)
    running = 1.0
    for rank in range(len(known), 0, -1):
        p, index = known[rank - 1]
        running = min(running, p * len(known) / rank)
        adjusted[index] = running
    return adjusted


def _curves(core: Mapping[str, object], timeline: Mapping[str, object] | None) -> ClusterMapCurves | None:
    if timeline is None:
        return None
    duration = _finite(core.get("analyzed_duration_seconds"))
    energy = np.asarray(timeline.get("energy_curve") or [], dtype=np.float64)
    hop = float(timeline.get("energy_curve_hop_seconds") or 0.5)  # type: ignore[arg-type]
    energy_ds = _downsample(energy)
    loudness = _downsample(np.asarray(timeline.get("loudness_curve") or [], dtype=np.float64))
    # Beat frames are STFT frames of the main SONARA pass (22 050 Hz, hop 512).
    beats = np.asarray(timeline.get("beats") or [], dtype=np.float64) * 512 / 22050
    tempo = np.asarray(timeline.get("tempo_curve") or [], dtype=np.float64)
    count = min(len(beats), len(tempo))
    runs: list[list] = []
    for event in timeline.get("chord_events") or []:  # type: ignore[union-attr]
        minor = str(event["label"]).endswith("m")
        if runs and runs[-1][2] == minor:
            runs[-1][1] = float(event["end_sec"])
        else:
            runs.append([float(event["start_sec"]), float(event["end_sec"]), minor])
    return ClusterMapCurves(
        duration=duration,
        energy=tuple(energy_ds),
        energy_hop=hop * len(energy) / max(1, len(energy_ds)),
        loudness=tuple(loudness),
        loudness_hop=(duration or 0.0) / max(1, len(loudness)),
        tempo_times=tuple(_downsample(beats[:count])),
        tempo_values=tuple(_downsample(tempo[:count])),
        segments=tuple(
            (float(s["start_sec"]), float(s["end_sec"]), float(s.get("energy") or 0.0))
            for s in timeline.get("segments") or []  # type: ignore[union-attr]
        ),
        mode_runs=tuple((a, b, m) for a, b, m in runs if b - a >= 0.5),
    )


def _downsample(values: np.ndarray) -> list[float]:
    if values.size <= _CURVE_POINTS:
        return [float(v) for v in values]
    edges = np.linspace(0, values.size, _CURVE_POINTS + 1).astype(int)
    return [float(values[a:b].mean()) for a, b in zip(edges[:-1], edges[1:], strict=True)]


def _nanmedian(values: np.ndarray) -> float | None:
    finite = values[np.isfinite(values)]
    return float(np.median(finite)) if len(finite) else None


def _finite(value: object) -> float | None:
    if value is None:
        return None
    number = float(value)  # type: ignore[arg-type]
    return number if math.isfinite(number) else None


def _text(value: object) -> str | None:
    return str(value) if value else None



BANDS_HZ = ((20.0, 150.0), (150.0, 600.0), (600.0, 3000.0), (3000.0, 11025.0))


def band_curves(path: str) -> dict[str, object]:
    """Energy of four frequency bands in 2 s windows, in dB below the loudest window.

    The source is decoded read-only through the shared FFmpeg runtime. The bands
    are not calibrated on the library, so they illustrate and never enter D.
    """

    import sonara

    from ..audio.loader import load_audio_mono_with_ffmpeg

    audio, sample_rate, _detail = load_audio_mono_with_ffmpeg(path)
    hop, mels = 2048, 96
    power = sonara.melspectrogram(
        y=np.ascontiguousarray(audio, dtype=np.float32), sr=float(sample_rate), n_fft=4096, hop_length=hop, n_mels=mels,
    )
    centres = np.asarray(sonara.mel_frequencies(n_mels=mels + 2, fmin=0.0, fmax=sample_rate / 2))[1:-1]
    window = max(1, round(2.0 * sample_rate / hop))
    frames = power.shape[1] // window
    if frames < 2:
        raise ValueError("audio is too short for band curves")
    bands = np.array([
        power[(centres >= low) & (centres < high)].sum(axis=0)[: frames * window].reshape(frames, window).mean(axis=1)
        for low, high in BANDS_HZ
    ])
    loudest = float(bands.sum(axis=0).max())
    if not loudest > 0:
        raise ValueError("silent audio has no band curves")
    decibels = np.maximum(10 * np.log10(np.maximum(bands, 1e-12) / loudest), -60.0)
    return {
        "hop_seconds": window * hop / sample_rate,
        "bands": [[round(float(v), 2) for v in row] for row in decibels],
    }
