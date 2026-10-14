"""Build a DJ set along a planned development from SONARA Core and Timeline.

A preset is a list of stages, each with its share of the set and the intensity
and BPM at its two ends. Every slot gets a BPM target and an intensity target
from them; a beam search picks tracks that hit those targets while each
transition stays mixable: small BPM steps in the planned direction, matching
edge loudness, a similar timbre, and a "drop & switch" through a low-energy
breakdown wherever the plan steps the tempo down hard. Tonality is not used:
the DJ syncs key.

Reference tracks narrow the candidates before the search: the nearest tracks
of one embedding model (the breed), then an optional one-axis shift against
the references. Both are gates, never score terms. Nothing is written; the
weights and thresholds are heuristics that are expected to change after
listening.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
import re
import secrets
import time
from typing import TYPE_CHECKING, Literal, cast
import unicodedata

import numpy as np
import numpy.typing as npt

from ..analysis.model_runners import current_embedding_analysis_output
from ..analysis_models import AnalysisTarget, SonaraFeatureRow
from ..search.engine import EmbeddingFamily, SimilaritySearch
from ..search.sonara import SonaraSimilaritySearch
from ..search.sonara_scoring import MODIFIER_FIELDS

if TYPE_CHECKING:
    from ..database import LibraryDatabase

# A slot this calm prefers quiet masters, one this dense the least danceable push.
CALM_INTENSITY = 0.30
CLIMAX_INTENSITY = 0.85
# A planned tempo step down of this size or more is a "drop & switch".
DROP_ENTRY_STEP = 0.035
# Each "push" signal is counted once; percentiles are taken inside the candidate pool.
INTENSITY_WEIGHTS = {
    "integrated_loudness_lufs": 0.40,
    "energy_curve_mean": 0.25,
    "onset_density_per_second": 0.20,
    "aggression_score": 0.15,
}
REQUIRED_FIELDS = (
    "detected_bpm",
    "bpm_confidence",
    "beat_grid_stability",
    "integrated_loudness_lufs",
    "energy_curve_mean",
    "energy_curve_stddev",
    "onset_density_per_second",
    "aggression_score",
    "danceability_score",
    "mood_relaxed_score",
    "spectral_centroid_hz",
    "intro_end_seconds",
    "outro_start_seconds",
    "energy_score",
    "mfcc_mean_blob",
    "spectral_contrast_mean_blob",
)
# The owner hears no usable difference on the vocal axis, so it is not offered.
DIRECTION_AXES: Mapping[str, str] = {
    axis: column for axis, column in MODIFIER_FIELDS.items() if axis != "vocalness"
}
MIN_BPM_CONFIDENCE = 0.6
MAX_FOLDED_BPM_DELTA = 1.0
GRID_STABILITY_PERCENTILE = 20
INTENSITY_TOLERANCE = 0.12
BPM_FIT_TOLERANCE = 0.012
FLAVOUR_WEIGHT = 0.5
BPM_WINDOWS = (0.02, 0.03, 0.04, 0.06)
MIN_SLOT_CANDIDATES = 60
SHORTLIST = 250
BEAM_WIDTH = 60
CHILDREN_PER_STATE = 25
STEP_TOLERANCE = 0.03
DROP_STEP_TOLERANCE = 0.07
BREAKDOWN_MIN_LU = 6.0
BREAKDOWN_MIN_SECONDS = 12.0
EDGE_MIN_SECONDS = 16.0
TAIL_SECONDS = 60.0
TRANSITION_WEIGHT = 0.5
ARTIST_REPEAT_WINDOW = 3
ARTIST_REPEAT_PENALTY = 5.0
TIMELINE_CHUNK = 500

ReferenceRole = Literal["reference", "pinned"]
DirectionRelation = Literal["lower", "similar", "higher"]
Floats = npt.NDArray[np.float64]
Indexes = npt.NDArray[np.intp]


@dataclass(frozen=True, slots=True)
class SetStage:
    """One stretch of the set: its share of the tracks (a relative weight) and
    the targets at its first and last slot. Intensity runs calm 0 to dense 1;
    slots in between are spaced evenly."""

    key: str
    share: float
    intensity_start: float
    intensity_end: float
    bpm_start: float
    bpm_end: float
    # Camelot steps from the key the set opens in; None leaves the key free.
    key_step: int | None = None
    # Whether the mode flips against that opening key (A <-> B).
    key_flip: bool = False
    # Classifier score ranges every track of the stage sits in: (key, low, high).
    classifiers: tuple[tuple[str, float, float], ...] = ()


# How a set develops, in the order of the owner's concepts. Every preset is
# only its numbers and stage rules: the search knows no preset by name.
PRESETS: Mapping[str, tuple[SetStage, ...]] = {
    "hypnotic_loop": (
        SetStage("start", 25.0, 0.15, 0.30, 124.0, 124.0),
        SetStage("texture", 30.0, 0.40, 0.65, 124.5, 124.5),
        SetStage("peak", 25.0, 0.78, 0.86, 125.0, 125.0),
        SetStage("outro", 20.0, 0.68, 0.52, 124.0, 123.5),
    ),
    # One tempo and one atmosphere; only the groove changes, straight to broken.
    "textural_blend": (
        SetStage(
            "straight", 50.0, 0.45, 0.55, 125.0, 125.0,
            classifiers=(("break_energy", 0.0, 0.2), ("minimal_deep_tech", 0.6, 1.0)),
        ),
        SetStage(
            "broken", 50.0, 0.55, 0.62, 125.0, 125.0,
            classifiers=(("break_energy", 0.6, 1.0), ("minimal_deep_tech", 0.3, 1.0)),
        ),
    ),
    "melancholic_plateau": (
        SetStage("start", 20.0, 0.45, 0.50, 123.5, 123.5),
        SetStage("deepening", 20.0, 0.55, 0.62, 123.5, 123.5),
        SetStage("dip", 20.0, 0.40, 0.34, 123.5, 123.5),
        SetStage("drive", 20.0, 0.58, 0.66, 123.5, 123.5),
        SetStage("resolution", 20.0, 0.48, 0.38, 123.5, 123.5),
    ),
    "progressive_acceleration": (
        SetStage("groove", 25.0, 0.20, 0.32, 118.0, 120.5),
        SetStage("build", 25.0, 0.40, 0.55, 121.5, 124.0),
        SetStage("tension", 25.0, 0.62, 0.78, 125.0, 127.5),
        SetStage("peak", 25.0, 0.85, 0.95, 128.5, 130.0),
    ),
    "arch": (
        SetStage("calm", 20.0, 0.10, 0.25, 120.0, 121.5),
        SetStage("development", 25.0, 0.35, 0.75, 123.0, 128.0),
        SetStage("climax", 20.0, 0.88, 0.95, 128.0, 128.0),
        SetStage("decline", 20.0, 0.70, 0.40, 122.0, 120.0),
        SetStage("closing", 15.0, 0.30, 0.08, 119.0, 118.0),
    ),
    "twin_summits": (
        SetStage("opening", 20.0, 0.28, 0.50, 124.0, 126.0),
        SetStage("summit_1", 20.0, 0.78, 0.86, 127.5, 128.0),
        SetStage("valley", 20.0, 0.50, 0.38, 126.0, 125.0),
        SetStage("summit_2", 25.0, 0.82, 0.97, 127.5, 130.0),
        SetStage("release", 15.0, 0.65, 0.45, 128.0, 126.0),
    ),
    "staircase": (
        SetStage("terrace_1", 25.0, 0.26, 0.26, 122.0, 122.0),
        SetStage("terrace_2", 25.0, 0.52, 0.52, 125.0, 125.0),
        SetStage("terrace_3", 25.0, 0.76, 0.76, 128.0, 128.0),
        SetStage("terrace_4", 25.0, 0.92, 0.92, 131.0, 131.0),
    ),
    # Tempo holds; the key walks the Camelot wheel and comes back two steps up.
    "harmonic_spiral": (
        SetStage("anchor", 20.0, 0.42, 0.48, 126.0, 126.0, key_step=0),
        SetStage("step", 20.0, 0.52, 0.60, 126.0, 126.0, key_step=1),
        SetStage("flip", 20.0, 0.66, 0.74, 126.0, 126.0, key_step=1, key_flip=True),
        SetStage("wide", 20.0, 0.80, 0.86, 126.0, 126.0, key_step=2, key_flip=True),
        SetStage("back", 20.0, 0.70, 0.60, 126.0, 126.0, key_step=2),
    ),
    "long_descent": (
        SetStage("inherit", 20.0, 0.95, 0.88, 130.0, 129.0),
        SetStage("strip_1", 20.0, 0.80, 0.70, 128.0, 126.5),
        SetStage("strip_2", 20.0, 0.62, 0.50, 125.5, 124.0),
        SetStage("strip_3", 20.0, 0.42, 0.30, 123.0, 120.5),
        SetStage("finish", 20.0, 0.24, 0.10, 119.0, 115.0),
    ),
    # Intensity only edges up; the set leaves minimal/deep-tech for broken rhythm.
    "genre_drift": (
        SetStage(
            "home", 20.0, 0.40, 0.45, 124.0, 124.5,
            classifiers=(("minimal_deep_tech", 0.7, 1.0), ("break_energy", 0.0, 0.2)),
        ),
        SetStage(
            "neighbour", 20.0, 0.48, 0.52, 125.0, 125.5,
            classifiers=(("minimal_deep_tech", 0.45, 0.8), ("break_energy", 0.0, 0.35)),
        ),
        SetStage(
            "crossover", 20.0, 0.56, 0.62, 126.0, 127.0,
            classifiers=(("minimal_deep_tech", 0.25, 0.6), ("break_energy", 0.2, 0.7)),
        ),
        SetStage(
            "territory", 20.0, 0.68, 0.74, 128.0, 129.0,
            classifiers=(("minimal_deep_tech", 0.05, 0.4), ("break_energy", 0.5, 1.0)),
        ),
        SetStage(
            "arrival", 20.0, 0.78, 0.82, 129.5, 130.0,
            classifiers=(("minimal_deep_tech", 0.0, 0.25), ("break_energy", 0.7, 1.0)),
        ),
    ),
}
MAX_STAGES = 8


@dataclass(frozen=True, slots=True)
class SetReference:
    """A track the recipe names: ``reference`` steers and stays out of the set,
    ``pinned`` is placed in it, at ``slot`` (1-based) when one is given."""

    track_id: int
    role: ReferenceRole
    slot: int | None = None


@dataclass(frozen=True, slots=True)
class SetDirection:
    """Shift every candidate along one SONARA axis against the references.

    ``margin`` is in library percentile points: the minimum shift for
    ``lower``/``higher``, the allowed distance for ``similar``.
    """

    axis: str
    relation: DirectionRelation
    margin: float


@dataclass(frozen=True, slots=True)
class SetRecipe:
    tracks: int = 15
    preset: str = "arch"
    # None builds on the preset's own stages.
    stages: tuple[SetStage, ...] | None = None
    references: tuple[SetReference, ...] = ()
    pool_model: EmbeddingFamily = "mert_v2"
    pool_size: int = 2000
    direction: SetDirection | None = None
    variety: float = 0.35
    seed: int | None = None

    def resolved_stages(self) -> tuple[SetStage, ...]:
        return self.stages if self.stages is not None else PRESETS[self.preset]

    def __post_init__(self) -> None:
        if self.preset not in PRESETS:
            raise ValueError(f"unknown preset: {self.preset}")
        stages = self.resolved_stages()
        if not 2 <= len(stages) <= MAX_STAGES:
            raise ValueError(f"a set has between 2 and {MAX_STAGES} stages")
        if self.tracks < len(stages):
            raise ValueError(f"tracks must be at least {len(stages)}, one per stage")
        if len({stage.key for stage in stages}) != len(stages):
            raise ValueError("stages must have distinct keys")
        for stage in stages:
            if not stage.share > 0:
                raise ValueError(f"the share of stage {stage.key} must be positive")
            if not (0.0 <= stage.intensity_start <= 1.0 and 0.0 <= stage.intensity_end <= 1.0):
                raise ValueError(f"the intensity targets of stage {stage.key} must be between 0 and 1")
            if not (60.0 <= stage.bpm_start <= 200.0 and 60.0 <= stage.bpm_end <= 200.0):
                raise ValueError(f"the BPM targets of stage {stage.key} must be between 60 and 200")
            if stage.key_step is not None and not -11 <= stage.key_step <= 11:
                raise ValueError(f"the key step of stage {stage.key} must be between -11 and 11")
            for classifier, low, high in stage.classifiers:
                if not classifier or not 0.0 <= low <= high <= 1.0:
                    raise ValueError(f"a classifier range of stage {stage.key} must be 0 <= low <= high <= 1")
        track_ids = [reference.track_id for reference in self.references]
        if len(set(track_ids)) != len(track_ids):
            raise ValueError("references must name each track once")
        slots = [reference.slot for reference in self.references if reference.slot is not None]
        if any(reference.slot is not None and reference.role != "pinned" for reference in self.references):
            raise ValueError("only a pinned reference can take a slot")
        if len(set(slots)) != len(slots):
            raise ValueError("two pinned references cannot take the same slot")
        if any(slot < 1 or slot > self.tracks for slot in slots):
            raise ValueError(f"a pinned slot must be between 1 and {self.tracks}")
        if sum(reference.role == "pinned" for reference in self.references) > self.tracks:
            raise ValueError("more pinned references than tracks in the set")
        if self.direction is not None:
            if self.direction.axis not in DIRECTION_AXES:
                raise ValueError(f"unknown direction axis: {self.direction.axis}")
            if not any(reference.role == "reference" for reference in self.references):
                raise ValueError("a direction needs at least one reference track to compare against")


@dataclass(frozen=True, slots=True)
class FunnelStage:
    key: str
    remaining: int


@dataclass(frozen=True, slots=True)
class SetSlot:
    slot: int
    stage: str
    drop_entry: bool
    pinned: bool
    target: AnalysisTarget
    score: float
    score_breakdown: Mapping[str, float]
    out_of_tolerance: bool


@dataclass(frozen=True, slots=True)
class SetAudit:
    transitions: int
    out_of_tolerance: int
    worst_slot: int | None


@dataclass(frozen=True, slots=True)
class SetBuild:
    seed: int
    preset: str
    stages: tuple[SetStage, ...]
    funnel: tuple[FunnelStage, ...]
    failure: str | None
    slots: tuple[SetSlot, ...]
    audit: SetAudit
    elapsed_seconds: float


class _Unbuildable(Exception):
    """The gates or the slots left nothing to choose from; the funnel says where."""


@dataclass(frozen=True)
class _Slot:
    index: int
    stage: str
    bpm_target: float
    intensity_target: float
    # The plan steps the tempo down hard into this slot: "drop & switch".
    drop_entry: bool
    # The stage rules every track of the slot has to meet.
    rules: SetStage


class _Pool:
    """Candidate and pinned tracks as parallel columns, ordered by track id."""

    def __init__(self, rows: Sequence[SonaraFeatureRow]) -> None:
        self.targets = [row.target for row in rows]
        self.values = {
            name: np.array([_number(row, name) for row in rows])
            for name in REQUIRED_FIELDS
            if not name.endswith("_blob")
        }
        self.bpm = self.values["detected_bpm"]
        self.intensity: Floats = np.sum(
            [weight * _percentile(self.values[name]) for name, weight in INTENSITY_WEIGHTS.items()],
            axis=0,
        )
        # The owner hears low LUFS as the calm opening and the fading close, so
        # quiet masters are preferred there on top of the intensity target.
        self.calm_flavour = (
            _percentile(self.values["integrated_loudness_lufs"])
            + _percentile(self.values["energy_curve_stddev"])
            + (1.0 - _percentile(self.values["mood_relaxed_score"]))
        )
        self.climax_flavour = 1.0 - _percentile(self.values["danceability_score"])
        timbre = np.column_stack(
            [
                np.array([_vector(row, "mfcc_mean_blob")[1:] for row in rows], dtype=np.float64),
                np.array([_vector(row, "spectral_contrast_mean_blob") for row in rows], dtype=np.float64),
                np.log(np.maximum(self.values["spectral_centroid_hz"], 1.0)),
            ]
        )
        spread = timbre.std(axis=0)
        self.timbre = (timbre - timbre.mean(axis=0)) / np.where(spread > 0, spread, 1.0)
        pair_rng = np.random.default_rng(0)
        left = pair_rng.integers(0, len(rows), 5000)
        right = pair_rng.integers(0, len(rows), 5000)
        median = float(np.median(np.linalg.norm(self.timbre[left] - self.timbre[right], axis=1)))
        self.timbre_median = median if median > 0 else 1.0
        size = len(rows)
        self.has_shape = np.zeros(size, dtype=bool)
        self.edge_in = np.full(size, np.nan)
        self.edge_out = np.full(size, np.nan)
        self.breakdown_lu = np.zeros(size)
        self.tail_ratio = np.ones(size)
        self.artist_keys: list[frozenset[str]] = [frozenset()] * size
        self.song_keys: list[tuple[str, str]] = [("#", str(target.track_id)) for target in self.targets]
        # Read only by stage rules: the detected Camelot key ("" when unknown)
        # and, per classifier key, the stored score (NaN when the track has none).
        self.camelot = np.array([str(row.values.get("detected_key_camelot") or "") for row in rows])
        self.classifier: dict[str, Floats] = {}

    def __len__(self) -> int:
        return len(self.targets)


def _number(row: SonaraFeatureRow, name: str) -> float:
    return float(cast("float", row.values[name]))


def _vector(row: SonaraFeatureRow, name: str) -> Sequence[float]:
    return cast("Sequence[float]", row.values[name])


def build_set(database: LibraryDatabase, recipe: SetRecipe) -> SetBuild:
    """Build one set; the same recipe, seed and library give the same set."""

    started = time.monotonic()
    seed = recipe.seed if recipe.seed is not None else secrets.randbits(32)
    rng = np.random.default_rng(seed)
    output = SonaraSimilaritySearch(database).active_output()
    rows = database.load_sonara_feature_rows(output)
    row_by_id = {row.target.track_id: row for row in rows}

    anchors = [reference for reference in recipe.references if reference.role == "reference"]
    pinned = [reference for reference in recipe.references if reference.role == "pinned"]
    for reference in recipe.references:
        row = row_by_id.get(reference.track_id)
        if row is None:
            raise ValueError(f"Track {reference.track_id} is not a current track with SONARA Core")
        if reference.role == "pinned" and any(row.values.get(name) is None for name in REQUIRED_FIELDS):
            raise ValueError(f"Pinned track {reference.track_id} lacks a SONARA field the builder scores")

    stages = recipe.resolved_stages()
    slots = _plan_slots(recipe.tracks, stages)
    classifier_scores = database.classifier_score_values(
        sorted({key for stage in stages for key, _low, _high in stage.classifiers})
    )
    for classifier, scores in classifier_scores.items():
        if not scores:
            raise ValueError(f"A stage reads {classifier} classifier scores, and this library has none")
    funnel: list[FunnelStage] = []

    def finish(slots: Sequence[SetSlot], audit: SetAudit, failure: str | None) -> SetBuild:
        return SetBuild(
            seed=seed,
            preset=recipe.preset,
            stages=stages,
            funnel=tuple(funnel),
            failure=failure,
            slots=tuple(slots),
            audit=audit,
            elapsed_seconds=round(time.monotonic() - started, 1),
        )

    try:
        bpm_targets = [slot.bpm_target for slot in slots]
        candidates = _gate_candidates(
            database, recipe, rows, anchors, min(bpm_targets) * 0.97, max(bpm_targets) * 1.03, funnel
        )
        named = {reference.track_id for reference in recipe.references}
        pool_rows = [row for row in candidates if row.target.track_id not in named]
        if len(pool_rows) + len(pinned) < recipe.tracks:
            raise _Unbuildable(
                f"{len(pool_rows)} candidates remain after the gates; the set needs {recipe.tracks} tracks"
            )
        pool_rows += [row_by_id[reference.track_id] for reference in pinned]
        pool_rows.sort(key=lambda row: row.target.track_id)
        pool = _Pool(pool_rows)
        index_by_id = {target.track_id: index for index, target in enumerate(pool.targets)}
        for classifier, scores in classifier_scores.items():
            pool.classifier[classifier] = np.array(
                [scores.get(target.track_id, np.nan) for target in pool.targets], dtype=np.float64
            )
        fixed = _place_pinned(pool, slots, pinned, index_by_id)
        noise = rng.gumbel(size=(len(slots), len(pool)))
        shortlists = _shortlist_slots(
            pool, slots, fixed, noise, recipe.variety, _opening_key(pool, slots, fixed, rng)
        )
        _load_shapes_and_tags(database, pool, {int(index) for shortlist in shortlists for index in shortlist})
        for slot_index, index in fixed.items():
            if not pool.has_shape[index]:
                raise ValueError(
                    f"Pinned track {pool.targets[index].track_id} has no usable SONARA Timeline"
                )
            shortlists[slot_index] = np.array([index])
        shortlists = [shortlist[pool.has_shape[shortlist]] for shortlist in shortlists]
        for slot, shortlist in zip(slots, shortlists):
            if not len(shortlist):
                raise _Unbuildable(
                    f"No candidates for slot {slot.index + 1} ({slot.stage}) near {slot.bpm_target:g} BPM"
                )
        path = _beam_search(pool, slots, shortlists, fixed, noise, recipe.variety, rng)
    except _Unbuildable as failure:
        return finish((), SetAudit(0, 0, None), str(failure))

    described = _describe_path(pool, slots, path, set(fixed.values()))
    over = [slot for slot in described if slot.out_of_tolerance]
    costs = [
        sum(value for key, value in slot.score_breakdown.items() if key.startswith("transition_"))
        for slot in described[1:]
    ]
    worst = described[1 + int(np.argmax(costs))].slot if costs else None
    return finish(described, SetAudit(len(described) - 1, len(over), worst), None)


def _gate_candidates(
    database: LibraryDatabase,
    recipe: SetRecipe,
    rows: Sequence[SonaraFeatureRow],
    anchors: Sequence[SetReference],
    bpm_low: float,
    bpm_high: float,
    funnel: list[FunnelStage],
) -> list[SonaraFeatureRow]:
    """Apply every gate in order, recording how many candidates each one leaves."""

    scored = [row for row in rows if all(row.values.get(name) is not None for name in REQUIRED_FIELDS)]
    funnel.append(FunnelStage("sonara", len(scored)))
    kept = [row for row in scored if bpm_low <= _number(row, "detected_bpm") <= bpm_high]
    funnel.append(FunnelStage("bpm_band", len(kept)))
    kept = [
        row
        for row in kept
        if _number(row, "bpm_confidence") >= MIN_BPM_CONFIDENCE
        and (
            row.values.get("raw_bpm") is None
            or abs(_number(row, "raw_bpm") - _number(row, "detected_bpm")) <= MAX_FOLDED_BPM_DELTA
        )
    ]
    funnel.append(FunnelStage("tempo", len(kept)))
    if kept:
        grid_floor = float(
            np.percentile([_number(row, "beat_grid_stability") for row in kept], GRID_STABILITY_PERCENTILE)
        )
        kept = [row for row in kept if _number(row, "beat_grid_stability") >= grid_floor]
    funnel.append(FunnelStage("grid", len(kept)))
    if not anchors:
        return kept

    searcher = SimilaritySearch(
        database,
        recipe.pool_model,
        analysis_output=current_embedding_analysis_output(recipe.pool_model),
    )
    anchor_targets = searcher.resolve_targets([reference.track_id for reference in anchors])
    allowed = {row.target for row in kept}
    breed: set[AnalysisTarget] = set()
    for result in searcher.search(anchor_targets, limit=len(searcher.current_targets())):
        if result.target in allowed:
            breed.add(result.target)
            if len(breed) == recipe.pool_size:
                break
    kept = [row for row in kept if row.target in breed]
    funnel.append(FunnelStage("pool", len(kept)))

    direction = recipe.direction
    if direction is None:
        return kept
    column = DIRECTION_AXES[direction.axis]
    library = np.sort([_number(row, column) for row in scored if row.values.get(column) is not None])

    def library_percentile(row: SonaraFeatureRow) -> float:
        return 100.0 * float(np.searchsorted(library, _number(row, column), side="right")) / len(library)

    anchor_ids = {target.track_id for target in anchor_targets}
    anchor_rows = [row for row in rows if row.target.track_id in anchor_ids]
    if not len(library) or any(row.values.get(column) is None for row in anchor_rows):
        raise ValueError(f"A reference track has no SONARA value on the {direction.axis} axis")
    centre = float(np.median([library_percentile(row) for row in anchor_rows]))

    def shifted(row: SonaraFeatureRow) -> bool:
        if row.values.get(column) is None:
            return False
        position = library_percentile(row)
        if direction.relation == "lower":
            return position <= centre - direction.margin
        if direction.relation == "higher":
            return position >= centre + direction.margin
        return abs(position - centre) <= direction.margin

    kept = [row for row in kept if shifted(row)]
    funnel.append(FunnelStage("direction", len(kept)))
    return kept


def _percentile(values: Floats) -> Floats:
    ranks = np.argsort(np.argsort(values, kind="stable"), kind="stable")
    return (ranks + 0.5) / len(values)


def _artist_key(artist: str | None) -> frozenset[str]:
    if not artist:
        return frozenset()
    parts = re.split(r"\s*(?:,|&|\bfeat\.?|\bft\.?|\bvs\.?|\bx\b)\s*", artist.lower())
    return frozenset(part.strip() for part in parts if part.strip())


def _song_key(artist: str | None, title: str | None, track_id: int) -> tuple[str, str]:
    """One song across its versions: the artists plus the title without bracketed suffixes.

    A track without both tags keeps a key of its own, so the rule never
    merges tracks it cannot name.
    """

    if not artist or not title:
        return ("#", str(track_id))
    base = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", title)
    normalized = "".join(
        character for character in unicodedata.normalize("NFKD", base).casefold() if character.isalnum()
    )
    if not normalized:
        return ("#", str(track_id))
    return ("|".join(sorted(_artist_key(artist))), normalized)


def _stage_counts(tracks: int, stages: Sequence[SetStage]) -> list[int]:
    """Slots per stage: at least one each, the rest by share."""

    total = sum(stage.share for stage in stages)
    raw = [stage.share / total * tracks for stage in stages]
    counts = [max(1, math.floor(value)) for value in raw]
    while sum(counts) < tracks:
        counts[max(range(len(raw)), key=lambda i: raw[i] - counts[i])] += 1
    while sum(counts) > tracks:
        counts[min((i for i in range(len(raw)) if counts[i] > 1), key=lambda i: raw[i] - counts[i])] -= 1
    return counts


def _plan_slots(tracks: int, stages: Sequence[SetStage]) -> list[_Slot]:
    """One target pair per slot; a stage's slots run evenly from its start to its end."""

    targets: list[tuple[SetStage, float, float]] = []
    for stage, count in zip(stages, _stage_counts(tracks, stages)):
        for position in range(count):
            fraction = 0.5 if count == 1 else position / (count - 1)
            targets.append(
                (
                    stage,
                    stage.intensity_start + (stage.intensity_end - stage.intensity_start) * fraction,
                    stage.bpm_start + (stage.bpm_end - stage.bpm_start) * fraction,
                )
            )
    slots: list[_Slot] = []
    for index, (stage, intensity, bpm) in enumerate(targets):
        previous_bpm = targets[index - 1][2] if index else bpm
        slots.append(
            _Slot(
                index,
                stage.key,
                round(bpm, 2),
                round(intensity, 3),
                (previous_bpm - bpm) / previous_bpm >= DROP_ENTRY_STEP,
                stage,
            )
        )
    return slots


def _shift_camelot(key: str, steps: int, flip: bool) -> str:
    """Walk the Camelot wheel: ``steps`` around it, and across to the other mode on ``flip``."""

    number, mode = int(key[:-1]), key[-1]
    if flip:
        mode = "B" if mode == "A" else "A"
    return f"{(number - 1 + steps) % 12 + 1}{mode}"


def _meets_rules(pool: _Pool, slot: _Slot, indexes: Indexes, opening_key: str | None) -> npt.NDArray[np.bool_]:
    """Which of ``indexes`` the stage rules of ``slot`` let in.

    A track without the score or the key a rule reads is left out: an explicit
    rule never guesses.
    """

    allowed = np.ones(len(indexes), dtype=bool)
    for classifier, low, high in slot.rules.classifiers:
        scores = pool.classifier[classifier][indexes]
        allowed &= (scores >= low) & (scores <= high)
    if slot.rules.key_step is not None and opening_key is not None:
        allowed &= pool.camelot[indexes] == _shift_camelot(opening_key, slot.rules.key_step, slot.rules.key_flip)
    return allowed


def _opening_key(
    pool: _Pool,
    slots: Sequence[_Slot],
    fixed: Mapping[int, int],
    rng: np.random.Generator,
) -> str | None:
    """The key a key-walking set opens in, or None when no free slot walks.

    A track pinned to slot 1 sets it. Otherwise the seed draws it from the keys
    that leave every walking slot a full shortlist; when none does, the key
    whose scarcest slot has the most candidates is taken.
    """

    walking = [slot for slot in slots if slot.rules.key_step is not None and slot.index not in fixed]
    if not walking:
        return None
    if 0 in fixed:
        key = str(pool.camelot[fixed[0]])
        if not key:
            raise ValueError("The track pinned to slot 1 has no detected key to start the key walk from")
        return key
    free = np.setdiff1d(np.arange(len(pool)), np.fromiter(fixed.values(), dtype=int))
    scarcest: dict[str, int] = {}
    for key in (f"{number}{mode}" for mode in "AB" for number in range(1, 13)):
        scarcest[key] = min(
            int(
                np.count_nonzero(
                    _meets_rules(pool, slot, free, key)
                    & (np.abs(pool.bpm[free] - slot.bpm_target) <= BPM_WINDOWS[-1] * slot.bpm_target)
                )
            )
            for slot in walking
        )
    roomy = [key for key, count in scarcest.items() if count >= MIN_SLOT_CANDIDATES]
    if roomy:
        return roomy[int(rng.integers(len(roomy)))]
    best = max(scarcest, key=lambda key: scarcest[key])
    if not scarcest[best]:
        raise _Unbuildable("No opening key leaves every stage of the key walk a candidate")
    return best


def _slot_fit(pool: _Pool, slot: _Slot, indexes: Indexes) -> Floats:
    fit = ((pool.intensity[indexes] - slot.intensity_target) / INTENSITY_TOLERANCE) ** 2
    fit += ((pool.bpm[indexes] - slot.bpm_target) / (BPM_FIT_TOLERANCE * slot.bpm_target)) ** 2
    if slot.intensity_target <= CALM_INTENSITY:
        fit += FLAVOUR_WEIGHT * pool.calm_flavour[indexes]
    elif slot.intensity_target >= CLIMAX_INTENSITY:
        fit += FLAVOUR_WEIGHT * pool.climax_flavour[indexes]
    return fit


def _place_pinned(
    pool: _Pool,
    slots: Sequence[_Slot],
    pinned: Sequence[SetReference],
    index_by_id: Mapping[int, int],
) -> dict[int, int]:
    """Slot index -> pool index: named slots first, the rest where each track fits best."""

    fixed = {reference.slot - 1: index_by_id[reference.track_id] for reference in pinned if reference.slot}
    for reference in pinned:
        if reference.slot:
            continue
        index = np.array([index_by_id[reference.track_id]])
        free = [slot for slot in slots if slot.index not in fixed]
        best = min(free, key=lambda slot: float(_slot_fit(pool, slot, index)[0]))
        fixed[best.index] = int(index[0])
    return fixed


def _shortlist_slots(
    pool: _Pool,
    slots: Sequence[_Slot],
    fixed: Mapping[int, int],
    noise: Floats,
    variety: float,
    opening_key: str | None,
) -> list[Indexes]:
    free = np.setdiff1d(np.arange(len(pool)), np.fromiter(fixed.values(), dtype=int))
    shortlists: list[Indexes] = []
    for slot in slots:
        if slot.index in fixed:
            shortlists.append(np.array([fixed[slot.index]]))
            continue
        eligible = free[_meets_rules(pool, slot, free, opening_key)]
        if not len(eligible):
            raise _Unbuildable(
                f"No candidates for slot {slot.index + 1} ({slot.stage}): the stage rules leave none"
            )
        inside = eligible[:0]
        for window in BPM_WINDOWS:
            inside = eligible[np.abs(pool.bpm[eligible] - slot.bpm_target) <= window * slot.bpm_target]
            if len(inside) >= MIN_SLOT_CANDIDATES:
                break
        if not len(inside):
            raise _Unbuildable(
                f"No candidates for slot {slot.index + 1} ({slot.stage}) within "
                f"{BPM_WINDOWS[-1]:.0%} of {slot.bpm_target:g} BPM"
            )
        scores = _slot_fit(pool, slot, inside) - variety * noise[slot.index, inside]
        shortlists.append(inside[np.argsort(scores, kind="stable")[:SHORTLIST]])
    return shortlists


def _median_filter(values: Floats, width: int = 5) -> Floats:
    if len(values) < width:
        return values
    padded = np.pad(values, width // 2, mode="edge")
    return np.median(np.lib.stride_tricks.sliding_window_view(padded, width), axis=1)


def _track_shape(
    payload: Mapping[str, object],
    frame_seconds: float,
    intro_end: float,
    outro_start: float,
) -> tuple[float, float, float, float]:
    """Edge-in LUFS, edge-out LUFS, breakdown depth in LU, tail-to-body onset ratio."""

    energy = cast("Sequence[float]", payload["energy_curve"])
    duration = len(energy) * float(cast("float", payload["energy_curve_hop_seconds"]))
    loudness = _median_filter(
        np.asarray(cast("Sequence[float]", payload["loudness_curve"]), dtype=np.float64)
    )
    if duration <= 0 or not len(loudness) or not np.isfinite(loudness).all():
        raise ValueError("timeline has no usable loudness curve")
    hop = duration / len(loudness)
    times = (np.arange(len(loudness)) + 0.5) * hop
    in_body = (times >= intro_end) & (times <= outro_start)
    if in_body.sum() * hop < 30.0:
        in_body = np.ones(len(loudness), dtype=bool)
    body = float(np.percentile(loudness[in_body], 80))
    head = times <= max(intro_end, EDGE_MIN_SECONDS)
    tail = times >= duration - max(duration - outro_start, EDGE_MIN_SECONDS)
    edge_in = float(np.median(loudness[head])) if head.any() else float(loudness[0])
    edge_out = float(np.median(loudness[tail])) if tail.any() else float(loudness[-1])

    breakdown_lu, best_length = 0.0, 0.0
    quiet = np.append(loudness < body - BREAKDOWN_MIN_LU, False)
    run_start = None
    for position, is_quiet in enumerate(quiet):
        if is_quiet and run_start is None:
            run_start = position
        elif not is_quiet and run_start is not None:
            length = (position - run_start) * hop
            centre = (run_start + position) / 2 * hop / duration
            if length >= BREAKDOWN_MIN_SECONDS and 0.45 <= centre <= 0.9 and length > best_length:
                best_length = length
                breakdown_lu = body - float(np.median(loudness[run_start:position]))
            run_start = None

    onsets = np.asarray(cast("Sequence[float]", payload["onsets"]), dtype=np.float64) * frame_seconds
    body_seconds = max(outro_start - intro_end, 1.0)
    body_rate = np.count_nonzero((onsets >= intro_end) & (onsets <= outro_start)) / body_seconds
    tail_rate = np.count_nonzero(onsets >= duration - TAIL_SECONDS) / TAIL_SECONDS
    return edge_in, edge_out, breakdown_lu, tail_rate / body_rate if body_rate > 0 else 1.0


def _load_shapes_and_tags(database: LibraryDatabase, pool: _Pool, indexes: set[int]) -> None:
    """Read what only shortlisted tracks need: the Timeline shape and the artist/title tags."""

    ordered = sorted(indexes)
    by_target = {pool.targets[index]: index for index in ordered}
    for start in range(0, len(ordered), TIMELINE_CHUNK):
        chunk = [pool.targets[index] for index in ordered[start : start + TIMELINE_CHUNK]]
        for target, (payload, frame_seconds) in database.load_sonara_timeline_frames(chunk).items():
            index = by_target[target]
            try:
                shape = _track_shape(
                    payload,
                    frame_seconds,
                    float(pool.values["intro_end_seconds"][index]),
                    float(pool.values["outro_start_seconds"][index]),
                )
            except (KeyError, TypeError, ValueError, IndexError):
                continue
            pool.edge_in[index], pool.edge_out[index], pool.breakdown_lu[index], pool.tail_ratio[index] = shape
            pool.has_shape[index] = True
    tags = database.get_track_artist_titles([pool.targets[index].track_id for index in ordered])
    for index in ordered:
        track_id = pool.targets[index].track_id
        artist, title = tags.get(track_id, (None, None))
        pool.artist_keys[index] = _artist_key(artist)
        pool.song_keys[index] = _song_key(artist, title, track_id)


def _step_tolerance(slot: _Slot, previous: _Slot) -> float:
    """Relative BPM step that mixes cleanly; a short set may plan wider steps."""

    if slot.drop_entry:
        return DROP_STEP_TOLERANCE
    planned = abs(slot.bpm_target - previous.bpm_target) / previous.bpm_target
    return max(STEP_TOLERANCE, planned + 0.01)


def _transition_costs(
    pool: _Pool,
    a: int,
    b: Indexes,
    slot: _Slot,
    previous: _Slot,
) -> tuple[dict[str, Floats], npt.NDArray[np.bool_]]:
    """Cost of mixing track ``a`` into each track of ``b`` for ``slot``, in tolerance
    units, and which of those steps leave the tempo tolerance."""

    bpm_a, bpm_b = pool.bpm[a], pool.bpm[b]
    planned = slot.bpm_target - previous.bpm_target
    tolerance = _step_tolerance(slot, previous)
    relative_step = np.abs(bpm_b - bpm_a) / bpm_a
    over = relative_step > tolerance
    bpm = (relative_step / tolerance) ** 2 + 3.0 * over
    step = bpm_b - bpm_a
    if planned > 0.25:
        bpm = bpm + (step < -0.5)
    elif planned < -0.25:
        bpm = bpm + (step > 0.5)
    if slot.drop_entry and pool.breakdown_lu[a] < BREAKDOWN_MIN_LU:
        bpm = bpm + 2.0

    handoff = 0.3 * np.minimum(4.0, (np.abs(pool.edge_out[a] - pool.edge_in[b]) / 4.0) ** 2)

    planned_intensity = slot.intensity_target - previous.intensity_target
    change = pool.intensity[b] - pool.intensity[a]
    if planned_intensity > 0:
        direction = np.maximum(0.0, -change - 0.05) / 0.1
    elif planned_intensity < 0:
        direction = np.maximum(0.0, change - 0.05) / 0.1
    else:
        direction = np.zeros(len(b))

    distance = np.linalg.norm(pool.timbre[b] - pool.timbre[a], axis=1)
    timbre = 0.2 * np.maximum(0.0, distance / pool.timbre_median - 1.0)
    return {"bpm": bpm, "handoff": handoff, "direction": direction, "timbre": timbre}, over


def _beam_search(
    pool: _Pool,
    slots: Sequence[_Slot],
    shortlists: Sequence[Indexes],
    fixed: Mapping[int, int],
    noise: Floats,
    variety: float,
    rng: np.random.Generator,
) -> list[int]:
    """Fewest out-of-tolerance tempo steps first, then the lowest total cost."""

    pinned_indexes = set(fixed.values())
    pinned_songs = {pool.song_keys[index] for index in pinned_indexes}
    first = shortlists[0]
    if 0 in fixed:
        start = fixed[0]
    else:
        open_first = np.array(
            [index for index in first if pool.song_keys[index] not in pinned_songs], dtype=int
        )
        if not len(open_first):
            raise _Unbuildable(f"No candidates for slot 1 ({slots[0].stage})")
        scores = _slot_fit(pool, slots[0], open_first) - variety * noise[0, open_first]
        order = np.argsort(scores, kind="stable")[:20]
        top = scores[order]
        weights = np.exp(-(top - top.min()) / max(variety, 1e-3))
        start = int(open_first[order][rng.choice(len(order), p=weights / weights.sum())])

    beam: list[tuple[int, float, tuple[int, ...]]] = [(0, 0.0, (start,))]
    for slot in slots[1:]:
        previous = slots[slot.index - 1]
        candidates = shortlists[slot.index]
        base = _slot_fit(pool, slot, candidates) - variety * noise[slot.index, candidates]
        # A set that ends calm closes on a track whose own tail thins out.
        if slot.index == slots[-1].index and slot.intensity_target <= CALM_INTENSITY:
            base = base + FLAVOUR_WEIGHT * np.minimum(pool.tail_ratio[candidates], 1.5)
        slot_is_fixed = slot.index in fixed
        children: dict[tuple[int, frozenset[int]], tuple[int, float, tuple[int, ...]]] = {}
        for violations, score, path in beam:
            costs, over = _transition_costs(pool, path[-1], candidates, slot, previous)
            total = base + TRANSITION_WEIGHT * sum(costs.values())
            if not slot_is_fixed:
                used = set(path)
                used_songs = {pool.song_keys[index] for index in path} | pinned_songs
                recent: set[str] = set()
                for index in path[-ARTIST_REPEAT_WINDOW:]:
                    recent |= pool.artist_keys[index]
                if recent:
                    total = total + ARTIST_REPEAT_PENALTY * np.array(
                        [bool(pool.artist_keys[index] & recent) for index in candidates]
                    )
                allowed = np.array(
                    [index not in used and pool.song_keys[index] not in used_songs for index in candidates]
                )
                total = np.where(allowed, total, np.inf)
            taken = 0
            for position in np.lexsort((total, over)):
                if not np.isfinite(total[position]):
                    continue
                child = int(candidates[position])
                new_path = (*path, child)
                key = (child, frozenset(new_path))
                entry = (violations + int(over[position]), score + float(total[position]), new_path)
                if key not in children or entry[:2] < children[key][:2]:
                    children[key] = entry
                taken += 1
                if taken == CHILDREN_PER_STATE:
                    break
        if not children:
            raise _Unbuildable(f"No candidates left for slot {slot.index + 1} ({slot.stage})")
        beam = sorted(children.values())[:BEAM_WIDTH]
    return list(beam[0][2])


def _describe_path(
    pool: _Pool,
    slots: Sequence[_Slot],
    path: Sequence[int],
    pinned_indexes: set[int],
) -> list[SetSlot]:
    """Re-score the chosen order on its own, slot by slot, for the response."""

    described: list[SetSlot] = []
    for slot, index in zip(slots, path):
        breakdown = {
            "bpm": round(float(pool.bpm[index]), 2),
            "bpm_target": slot.bpm_target,
            "intensity_target": slot.intensity_target,
            "slot_fit": round(float(_slot_fit(pool, slot, np.array([index]))[0]), 3),
        }
        out_of_tolerance = False
        if slot.index > 0:
            costs, over = _transition_costs(
                pool, path[slot.index - 1], np.array([index]), slot, slots[slot.index - 1]
            )
            breakdown |= {f"transition_{name}": round(float(value[0]), 3) for name, value in costs.items()}
            out_of_tolerance = bool(over[0])
        described.append(
            SetSlot(
                slot=slot.index + 1,
                stage=slot.stage,
                drop_entry=slot.drop_entry,
                pinned=index in pinned_indexes,
                target=pool.targets[index],
                score=round(float(pool.intensity[index]), 3),
                score_breakdown=breakdown,
                out_of_tolerance=out_of_tolerance,
            )
        )
    return described
