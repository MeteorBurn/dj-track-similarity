from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import math
import threading
from typing import Final, Literal, Protocol

import numpy as np
from numpy.typing import NDArray

from .analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
    current_embedding_spec,
)
from .vector_index import (
    ExactVectorSearchBackend,
    VectorIndexUnavailable,
    VectorSearchBackend,
    VectorSearchHit,
)


FloatArray = NDArray[np.float32]
EmbeddingFamily = Literal["maest", "mert", "muq", "mulan", "clap"]
CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT: Final = 0.5
_EMBEDDING_FAMILIES = frozenset({"maest", "mert", "muq", "mulan", "clap"})


class AnalysisSearchRepository(Protocol):
    """Public repository surface required by embedding search."""

    catalog_uuid: str

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        ...

    def load_analysis_vectors(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[AnalysisVectorRow, ...]:
        ...

    def random_embedding_target(
        self,
        output: AnalysisOutput,
        *,
        exclude_track_ids: Sequence[int] = (),
    ) -> AnalysisTarget | None:
        ...


@dataclass(frozen=True, slots=True)
class SearchFilters:
    """Score-domain filters applied by the vector-search layer.

    BPM, key, energy, and other library metadata filters belong to the typed
    library-query layer. That layer can pass its exact current candidate set to
    ``candidate_targets`` without making this module read legacy track DTOs.
    """

    min_similarity: float | None = None
    epsilon: float | None = None
    noise: float = 0.0

    def __post_init__(self) -> None:
        if self.min_similarity is not None:
            _finite_number(
                self.min_similarity,
                "min_similarity",
            )
        if self.epsilon is not None and _finite_number(
            self.epsilon,
            "epsilon",
        ) < 0.0:
            raise ValueError("epsilon must be non-negative")
        noise = _finite_number(self.noise, "noise")
        if not 0.0 <= noise <= 1.0:
            raise ValueError("noise must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class SimilaritySearchResult:
    """A ranked result with the full validated track identity."""

    target: AnalysisTarget
    score: float
    score_breakdown: Mapping[str, float] | None = None


class SimilaritySearch:
    """Cosine search over one current ML embedding family."""

    def __init__(
        self,
        repository: AnalysisSearchRepository,
        analysis_family: EmbeddingFamily,
        *,
        analysis_output: AnalysisOutput,
        vector_backend: VectorSearchBackend | None = None,
    ) -> None:
        family = str(analysis_family).strip().lower()
        if family not in _EMBEDDING_FAMILIES:
            valid = ", ".join(sorted(_EMBEDDING_FAMILIES))
            raise ValueError(
                f"Unsupported embedding family {analysis_family!r}; "
                f"expected one of: {valid}"
            )
        self.repository = repository
        self.analysis_family: EmbeddingFamily = family  # type: ignore[assignment]
        if analysis_output.key != (family, "embedding"):
            raise ValueError(
                "analysis_output does not match the requested "
                "embedding family"
            )
        if current_embedding_spec(family).normalization != "l2":
            raise ValueError(
                "ML search analysis_output must use "
                "normalization='l2'"
            )
        self.analysis_output = analysis_output
        self.vector_backend = (
            vector_backend
            if vector_backend is not None
            else ExactVectorSearchBackend()
        )
        self._full_rows: tuple[AnalysisOutput, tuple[AnalysisVectorRow, ...]] | None = None
        self.active_output()

    def active_output(self) -> AnalysisOutput:
        """Resolve and validate the current embedding output."""

        output = self.repository.active_analysis_output(
            self.analysis_family,
            "embedding",
        )
        if output is None:
            raise VectorIndexUnavailable(
                "No active embedding output is registered for "
                f"{self.analysis_family!r}"
            )
        if output.key != (self.analysis_family, "embedding"):
            raise RuntimeError(
                "Active embedding resolver returned the wrong output identity"
            )
        spec = current_embedding_spec(self.analysis_family)
        if spec.normalization != "l2":
            raise VectorIndexUnavailable(
                "ML cosine search requires normalization='l2', "
                f"got {spec.normalization!r}"
            )
        if spec.dimension <= 0:
            raise VectorIndexUnavailable(
                "Current embedding specification has no positive dimension"
            )
        return output

    def resolve_targets(
        self,
        track_ids: Sequence[int],
    ) -> tuple[AnalysisTarget, ...]:
        """Resolve request IDs to current, search-ready identities.

        The result preserves caller order. A missing ID is deliberately not
        guessed: it can mean an unknown track, a missing file, or a current
        track without the active embedding, and all three are not searchable.
        """

        requested = _requested_track_ids(track_ids)
        output = self.active_output()
        rows = self._load_full_rows(output)
        target_by_id = {row.target.track_id: row.target for row in rows}
        missing = [
            track_id
            for track_id in requested
            if track_id not in target_by_id
        ]
        if missing:
            raise ValueError(
                "Tracks are not current and search-ready for "
                f"{self.analysis_family!r}: {missing}"
            )
        return tuple(target_by_id[track_id] for track_id in requested)

    def random_target(
        self,
        *,
        exclude_track_ids: Sequence[int] = (),
    ) -> AnalysisTarget:
        """Choose one unselected current track with a valid embedding.

        Selection reads identities only. What makes a track seedable is the
        presence of its row under the current identity, at the dimension and
        normalization the current specification declares, and all three are
        stored columns the repository can match in one query. No vector is
        read, so the pick costs the same on a library of any size.
        """

        excluded = _optional_track_ids(exclude_track_ids)
        output = self.active_output()
        target = self.repository.random_embedding_target(
            output,
            exclude_track_ids=tuple(sorted(excluded)),
        )
        if target is None:
            raise VectorIndexUnavailable(
                "No unselected tracks have current "
                f"{self.analysis_family} embeddings"
            )
        if target.catalog_uuid != self.repository.catalog_uuid:
            raise RuntimeError(
                "Random embedding target returned the wrong catalog identity"
            )
        if target.track_id in excluded:
            raise RuntimeError(
                "Random embedding target ignored the excluded track IDs"
            )
        return target

    def search(
        self,
        seed_targets: Sequence[AnalysisTarget],
        *,
        candidate_targets: Sequence[AnalysisTarget] | None = None,
        filters: SearchFilters | None = None,
        limit: int = 50,
    ) -> list[SimilaritySearchResult]:
        seeds = _validate_targets(
            seed_targets,
            catalog_uuid=self.repository.catalog_uuid,
            field_name="seed_targets",
            require_nonempty=True,
        )
        selected_candidates = _optional_targets(
            candidate_targets,
            catalog_uuid=self.repository.catalog_uuid,
        )
        output, rows = self._load_rows(
            seeds=seeds,
            candidate_targets=selected_candidates,
        )

        prepared = _PREPARED.prepared(
            rows,
            output,
            self.repository.catalog_uuid,
        )
        target_to_index = prepared.target_to_index
        missing_seeds = [
            target
            for target in seeds
            if target not in target_to_index
        ]
        if missing_seeds:
            raise ValueError(
                "Seed tracks are missing the active embedding: "
                f"{_target_ids(missing_seeds)}"
            )
        if not rows:
            return []
        centroid = _normalize(
            np.mean(
                prepared.matrix[
                    [target_to_index[target] for target in seeds]
                ],
                axis=0,
            )
        )
        return self._rank(
            prepared,
            centroid,
            excluded=frozenset(seeds),
            filters=filters or SearchFilters(),
            limit=limit,
        )

    def search_vector(
        self,
        vector: FloatArray,
        *,
        candidate_targets: Sequence[AnalysisTarget] | None = None,
        filters: SearchFilters | None = None,
        limit: int = 50,
    ) -> list[SimilaritySearchResult]:
        selected_candidates = _optional_targets(
            candidate_targets,
            catalog_uuid=self.repository.catalog_uuid,
        )
        output, rows = self._load_rows(
            seeds=(),
            candidate_targets=selected_candidates,
        )
        if not rows:
            return []
        query = _query_for_output(vector, output)
        return self._rank(
            _PREPARED.prepared(rows, output, self.repository.catalog_uuid),
            query,
            excluded=frozenset(),
            filters=filters or SearchFilters(),
            limit=limit,
        )

    def search_contrast_vectors(
        self,
        *,
        positive_vectors: Sequence[FloatArray],
        negative_vectors: Sequence[FloatArray] | None = None,
        candidate_targets: Sequence[AnalysisTarget] | None = None,
        filters: SearchFilters | None = None,
        limit: int = 50,
        negative_weight: float = CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT,
    ) -> list[SimilaritySearchResult]:
        if not positive_vectors:
            raise ValueError(
                "At least one positive query vector is required"
            )
        selected_candidates = _optional_targets(
            candidate_targets,
            catalog_uuid=self.repository.catalog_uuid,
        )
        output, rows = self._load_rows(
            seeds=(),
            candidate_targets=selected_candidates,
        )
        if not rows:
            return []
        matrix = _PREPARED.prepared(
            rows,
            output,
            self.repository.catalog_uuid,
        ).matrix
        (
            positive_scores,
            negative_scores,
            contrast_scores,
            bounded_weight,
        ) = _contrast_vector_scores(
            matrix,
            output=output,
            positive_vectors=positive_vectors,
            negative_vectors=negative_vectors or (),
            negative_weight=negative_weight,
        )
        active_filters = filters or SearchFilters()
        candidates: list[
            tuple[
                AnalysisTarget,
                float,
                float,
                Mapping[str, float],
            ]
        ] = []
        for raw_index in np.argsort(
            -contrast_scores,
            kind="stable",
        ):
            index = int(raw_index)
            target = rows[index].target
            score = float(contrast_scores[index])
            if not _passes_score_filter(score, active_filters):
                continue
            breakdown = _contrast_score_breakdown(
                positive_scores,
                negative_scores,
                contrast_scores,
                bounded_weight,
                index,
            )
            candidates.append(
                (
                    target,
                    score,
                    _ranking_score(
                        target,
                        score,
                        active_filters.noise,
                    ),
                    breakdown,
                )
            )

        candidates = _apply_epsilon(
            candidates,
            epsilon=active_filters.epsilon,
            score_index=1,
        )
        bounded_limit = _result_limit(limit)
        ranked = sorted(
            candidates,
            key=lambda item: item[2],
            reverse=True,
        )[:bounded_limit]
        return [
            SimilaritySearchResult(
                target=target,
                score=score,
                score_breakdown=breakdown,
            )
            for target, score, _ranking, breakdown in ranked
        ]

    def _load_full_rows(
        self,
        output: AnalysisOutput,
    ) -> tuple[AnalysisVectorRow, ...]:
        """Load and validate every current vector once per search instance.

        ``resolve_targets`` and ``_load_rows`` both need the whole library
        matrix, and one instance serves exactly one request, so an uncached
        second call repeats a full table read plus a full re-validation of
        rows that were just checked.
        """

        cached = self._full_rows
        if cached is not None and cached[0] == output:
            return cached[1]
        rows = self.repository.load_analysis_vectors(output, targets=None)
        _validate_rows(
            rows,
            output=output,
            catalog_uuid=self.repository.catalog_uuid,
        )
        self._full_rows = (output, rows)
        return rows

    def _load_rows(
        self,
        *,
        seeds: tuple[AnalysisTarget, ...],
        candidate_targets: tuple[AnalysisTarget, ...] | None,
    ) -> tuple[AnalysisOutput, tuple[AnalysisVectorRow, ...]]:
        output = self.active_output()
        if candidate_targets is None:
            if seeds:
                # The returned rows are unused: this call is the staleness gate
                # that rejects a seed whose identity no longer matches the
                # library, which the full load below cannot distinguish from a
                # seed that simply has no vector.
                seed_rows = self.repository.load_analysis_vectors(
                    output,
                    targets=seeds,
                )
                _validate_rows(
                    seed_rows,
                    output=output,
                    catalog_uuid=self.repository.catalog_uuid,
                )
            return output, self._load_full_rows(output)
        rows = self.repository.load_analysis_vectors(
            output,
            targets=_merge_targets(seeds, candidate_targets),
        )
        _validate_rows(
            rows,
            output=output,
            catalog_uuid=self.repository.catalog_uuid,
        )
        return output, rows

    def _rank(
        self,
        prepared: _Prepared,
        query: FloatArray,
        *,
        excluded: frozenset[AnalysisTarget],
        filters: SearchFilters,
        limit: int,
    ) -> list[SimilaritySearchResult]:
        """Rank the library against *query*, reading only as deep as needed.

        Asking the backend for k = N built a hit object for all 45,000 tracks
        in order to return fifty of them. How deep the answer actually reaches
        is bounded: hits arrive in descending score, ``min_similarity`` and
        ``epsilon`` only ever cut a suffix of that order, the excluded seeds
        remove at most ``len(excluded)`` of them, and the deterministic noise
        jitter moves a score by at most ``noise / 2``. So a prefix suffices as
        soon as no unseen score can reach the last ranking score kept, and the
        depth grows until that holds.
        """

        bounded_limit = _result_limit(limit)
        total = len(prepared.targets)
        requested = min(total, bounded_limit + len(excluded))
        while True:
            hits = self.vector_backend.search(
                prepared.matrix,
                prepared.targets,
                query,
                limit=requested,
            )
            candidates, below_threshold = self._candidates(
                hits,
                prepared,
                excluded=excluded,
                filters=filters,
            )
            if requested >= total or _ranking_is_settled(
                hits,
                candidates,
                limit=bounded_limit,
                noise=filters.noise,
                below_threshold=below_threshold,
            ):
                break
            requested = min(total, requested * 2 if requested else 16)

        candidates = _apply_epsilon(
            candidates,
            epsilon=filters.epsilon,
            score_index=1,
        )
        ranked = sorted(
            candidates,
            key=lambda item: item[2],
            reverse=True,
        )[:bounded_limit]
        return [
            SimilaritySearchResult(target=target, score=score)
            for target, score, _ranking in ranked
        ]

    def _candidates(
        self,
        hits: Sequence[VectorSearchHit],
        prepared: _Prepared,
        *,
        excluded: frozenset[AnalysisTarget],
        filters: SearchFilters,
    ) -> tuple[list[tuple[AnalysisTarget, float, float]], bool]:
        targets = prepared.targets
        target_to_index = prepared.target_to_index
        candidates: list[tuple[AnalysisTarget, float, float]] = []
        below_threshold = False
        for hit in hits:
            target = _target_for_hit(
                hit,
                targets,
                target_to_index,
            )
            if target in excluded:
                continue
            score = float(hit.score)
            if not math.isfinite(score):
                raise ValueError(
                    "Vector search backend returned a non-finite score"
                )
            if not _passes_score_filter(score, filters):
                below_threshold = True
                continue
            candidates.append(
                (
                    target,
                    score,
                    _ranking_score(
                        target,
                        score,
                        filters.noise,
                    ),
                )
            )
        return candidates, below_threshold


class _Prepared:
    """Everything a search derives from one row set, derived once.

    The repository hands back the same rows object until the stored vectors
    change, so a second search over an unchanged library re-checked those rows,
    stacked them into a second identical matrix, and rebuilt the same target
    tuple and identity map. All four are pure functions of the rows.
    """

    __slots__ = (
        "rows",
        "output",
        "catalog_uuid",
        "_matrix",
        "_targets",
        "_target_to_index",
    )

    def __init__(
        self,
        rows: Sequence[AnalysisVectorRow],
        output: AnalysisOutput,
        catalog_uuid: str,
    ) -> None:
        self.rows = rows
        self.output = output
        self.catalog_uuid = catalog_uuid
        self._matrix: FloatArray | None = None
        self._targets: tuple[AnalysisTarget, ...] | None = None
        self._target_to_index: dict[AnalysisTarget, int] | None = None

    @property
    def matrix(self) -> FloatArray:
        matrix = self._matrix
        if matrix is None:
            matrix = _stack(self.rows, self.output)
            self._matrix = matrix
        return matrix

    @property
    def targets(self) -> tuple[AnalysisTarget, ...]:
        targets = self._targets
        if targets is None:
            targets = tuple(row.target for row in self.rows)
            self._targets = targets
        return targets

    @property
    def target_to_index(self) -> Mapping[AnalysisTarget, int]:
        index = self._target_to_index
        if index is None:
            index = {
                target: position
                for position, target in enumerate(self.targets)
            }
            self._target_to_index = index
        return index


class _PreparedRows:
    """One derived row set per distinct rows object, four at a time.

    Identity — not equality — is what makes reuse safe here: the entry holds
    the rows it was derived from, so the object cannot be collected and a later
    row set cannot land on its identity. Four entries cover one search: the
    library plus the one-row set the seed staleness gate checks, for the two
    families a comparison alternates between.
    """

    _LIMIT = 4

    def __init__(self) -> None:
        # Searches run concurrently in the API threadpool, and eviction reads
        # the dictionary while another request may be inserting into it.
        self._lock = threading.Lock()
        self._entries: dict[int, _Prepared] = {}

    def prepared(
        self,
        rows: Sequence[AnalysisVectorRow],
        output: AnalysisOutput,
        catalog_uuid: str,
    ) -> _Prepared:
        with self._lock:
            entry = self._entries.get(id(rows))
        if (
            entry is not None
            and entry.rows is rows
            and entry.output == output
            and entry.catalog_uuid == catalog_uuid
        ):
            return entry
        _check_rows(rows, output=output, catalog_uuid=catalog_uuid)
        entry = _Prepared(rows, output, catalog_uuid)
        with self._lock:
            self._entries.pop(id(rows), None)
            self._entries[id(rows)] = entry
            while len(self._entries) > self._LIMIT:
                del self._entries[next(iter(self._entries))]
        return entry


_PREPARED = _PreparedRows()


def _validate_rows(
    rows: Sequence[AnalysisVectorRow],
    *,
    output: AnalysisOutput,
    catalog_uuid: str,
) -> None:
    _PREPARED.prepared(rows, output, catalog_uuid)


def _check_rows(
    rows: Sequence[AnalysisVectorRow],
    *,
    output: AnalysisOutput,
    catalog_uuid: str,
) -> None:
    seen_targets: set[AnalysisTarget] = set()
    seen_track_ids: set[int] = set()
    for row in rows:
        if not isinstance(row, AnalysisVectorRow):
            raise TypeError(
                "Analysis repository returned a non-AnalysisVectorRow value"
            )
        if row.output.key != output.key:
            raise RuntimeError(
                "Analysis repository returned a vector from another output"
            )
        if row.target.catalog_uuid != catalog_uuid:
            raise RuntimeError(
                "Analysis repository returned a vector from another catalog"
            )
        if row.target in seen_targets:
            raise RuntimeError(
                "Analysis repository returned a duplicate target identity"
            )
        if row.target.track_id in seen_track_ids:
            raise RuntimeError(
                "Analysis repository returned conflicting identities "
                "for one track ID"
            )
        seen_targets.add(row.target)
        seen_track_ids.add(row.target.track_id)


def _stack(
    rows: Sequence[AnalysisVectorRow],
    output: AnalysisOutput,
) -> FloatArray:
    dim = current_embedding_spec(output.analysis_family).dimension
    if not rows:
        return np.empty((0, dim), dtype=np.float32)
    matrix = np.vstack(
        [
            np.asarray(row.vector, dtype=np.float32).reshape(-1)
            for row in rows
        ]
    ).astype(np.float32, copy=False)
    if matrix.shape != (len(rows), dim):
        raise ValueError(
            "Analysis repository returned an embedding matrix with "
            f"shape {matrix.shape}; expected {(len(rows), dim)}"
        )
    if not bool(np.all(np.isfinite(matrix))):
        raise ValueError(
            "Analysis repository returned non-finite embedding values"
        )
    # Squared norms via einsum stay in float32: casting the whole matrix to
    # float64 allocated a temporary twice the size of the library for a check
    # whose tolerance is four orders of magnitude looser than the error it adds.
    norms = np.sqrt(np.einsum("ij,ij->i", matrix, matrix))
    if not bool(
        np.all(np.isclose(norms, 1.0, rtol=1e-4, atol=1e-5))
    ):
        raise ValueError(
            "Active ML embedding rows are not unit-normalized"
        )
    return np.ascontiguousarray(matrix, dtype=np.float32)


def _normalize(vector: np.ndarray) -> FloatArray:
    query = np.asarray(vector, dtype=np.float32).reshape(-1)
    if not bool(np.all(np.isfinite(query))):
        raise ValueError("Cannot normalize a non-finite vector")
    norm = float(np.linalg.norm(query.astype(np.float64, copy=False)))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError("Cannot normalize zero vector")
    return np.ascontiguousarray(query / norm, dtype=np.float32)


def _query_for_output(
    vector: np.ndarray,
    output: AnalysisOutput,
) -> FloatArray:
    query = np.asarray(vector, dtype=np.float32).reshape(-1)
    dim = current_embedding_spec(output.analysis_family).dimension
    if query.shape != (dim,):
        raise ValueError(
            "Query vector dimension does not match the current family spec: "
            f"{query.shape[0]} != {dim}"
        )
    return _normalize(query)


def _normalize_matrix(
    vectors: Sequence[FloatArray],
    *,
    output: AnalysisOutput,
) -> FloatArray:
    normalized = [
        _query_for_output(vector, output)
        for vector in vectors
    ]
    if not normalized:
        dim = current_embedding_spec(output.analysis_family).dimension
        return np.empty((0, dim), dtype=np.float32)
    return np.vstack(normalized).astype(np.float32, copy=False)


def _contrast_vector_scores(
    matrix: FloatArray,
    *,
    output: AnalysisOutput,
    positive_vectors: Sequence[FloatArray],
    negative_vectors: Sequence[FloatArray],
    negative_weight: float,
) -> tuple[FloatArray, FloatArray, FloatArray, float]:
    positive_bank = _normalize(
        np.mean(
            _normalize_matrix(
                positive_vectors,
                output=output,
            ),
            axis=0,
        )
    )
    positive_scores = matrix @ positive_bank
    if negative_vectors:
        negative_bank = _normalize_matrix(
            negative_vectors,
            output=output,
        )
        # Averaging the two closest negatives asks a second prompt to agree
        # before a track is pushed down, which one badly worded negative could
        # otherwise decide alone. Measured on the labelled pool it beats the
        # maximum at every weight for both text models. A bank of one negative
        # keeps the old behaviour, since the two-column slice collapses to it.
        negative_scores = np.sort(
            matrix @ negative_bank.T,
            axis=1,
        )[:, -2:].mean(axis=1)
    else:
        negative_scores = np.zeros_like(positive_scores)
    bounded_weight = _finite_number(
        negative_weight,
        "negative_weight",
    )
    if bounded_weight < 0.0:
        raise ValueError("negative_weight must be non-negative")
    return (
        positive_scores,
        negative_scores,
        positive_scores - bounded_weight * negative_scores,
        bounded_weight,
    )


def _contrast_score_breakdown(
    positive_scores: FloatArray,
    negative_scores: FloatArray,
    contrast_scores: FloatArray,
    negative_weight: float,
    index: int,
) -> Mapping[str, float]:
    return {
        "positive": float(positive_scores[index]),
        "negative": float(negative_scores[index]),
        "contrast": float(contrast_scores[index]),
        "negative_weight": negative_weight,
    }


def _validate_targets(
    targets: Sequence[AnalysisTarget],
    *,
    catalog_uuid: str,
    field_name: str,
    require_nonempty: bool,
) -> tuple[AnalysisTarget, ...]:
    selected = tuple(targets)
    if require_nonempty and not selected:
        raise ValueError(
            f"{field_name} must contain at least one target"
        )
    if any(
        not isinstance(target, AnalysisTarget)
        for target in selected
    ):
        raise TypeError(
            f"{field_name} must contain only AnalysisTarget values"
        )
    if any(
        target.catalog_uuid != catalog_uuid
        for target in selected
    ):
        raise ValueError(
            f"{field_name} contains a target from another catalog"
        )
    if len(set(selected)) != len(selected):
        raise ValueError(
            f"{field_name} must not contain duplicate identities"
        )
    track_ids = [target.track_id for target in selected]
    if len(set(track_ids)) != len(track_ids):
        raise ValueError(
            f"{field_name} contains conflicting identities "
            "for one track ID"
        )
    return selected


def _optional_targets(
    targets: Sequence[AnalysisTarget] | None,
    *,
    catalog_uuid: str,
) -> tuple[AnalysisTarget, ...] | None:
    if targets is None:
        return None
    return _validate_targets(
        targets,
        catalog_uuid=catalog_uuid,
        field_name="candidate_targets",
        require_nonempty=False,
    )


def _merge_targets(
    first: Sequence[AnalysisTarget],
    second: Sequence[AnalysisTarget],
) -> tuple[AnalysisTarget, ...]:
    merged: list[AnalysisTarget] = []
    seen: set[AnalysisTarget] = set()
    for target in (*first, *second):
        if target in seen:
            continue
        seen.add(target)
        merged.append(target)
    return tuple(merged)


def _requested_track_ids(
    track_ids: Sequence[int],
) -> tuple[int, ...]:
    requested = tuple(track_ids)
    if not requested:
        raise ValueError("At least one track ID is required")
    if any(
        isinstance(track_id, bool)
        or not isinstance(track_id, int)
        or track_id <= 0
        for track_id in requested
    ):
        raise ValueError("Track IDs must be positive integers")
    if len(set(requested)) != len(requested):
        raise ValueError("Track IDs must not contain duplicates")
    return requested


def _optional_track_ids(
    track_ids: Sequence[int],
) -> frozenset[int]:
    requested = tuple(track_ids)
    if not requested:
        return frozenset()
    return frozenset(_requested_track_ids(requested))


def _target_for_hit(
    hit: VectorSearchHit,
    targets: Sequence[AnalysisTarget],
    target_to_index: Mapping[AnalysisTarget, int],
) -> AnalysisTarget:
    if not isinstance(hit, VectorSearchHit):
        raise TypeError(
            "Vector search backend returned a non-VectorSearchHit value"
        )
    if hit.index is not None:
        if hit.index < 0 or hit.index >= len(targets):
            raise ValueError(
                "Vector search backend returned out-of-range index: "
                f"{hit.index}"
            )
        target = targets[hit.index]
        if target != hit.target:
            raise ValueError(
                "Vector search backend returned a mismatched target/index"
            )
        return target
    if hit.target not in target_to_index:
        raise ValueError(
            "Vector search backend returned an unknown target identity"
        )
    return hit.target


def _passes_score_filter(
    score: float,
    filters: SearchFilters,
) -> bool:
    return (
        filters.min_similarity is None
        or score >= filters.min_similarity
    )


def _ranking_is_settled(
    hits: Sequence[VectorSearchHit],
    candidates: Sequence[tuple[AnalysisTarget, float, float]],
    *,
    limit: int,
    noise: float,
    below_threshold: bool,
) -> bool:
    """Whether no unseen hit could still enter the top *limit*."""

    if limit <= 0:
        return True
    if below_threshold:
        # Hits are ordered by descending score, so once one falls under
        # min_similarity every hit after it does too.
        return True
    if len(candidates) < limit:
        return False
    if not hits:
        return True
    last_score = float(hits[-1].score)
    if noise <= 0.0:
        # Ranking order is score order, and an unseen hit scores no higher
        # than the last one seen; a tie keeps the earlier hit under a stable
        # sort. The prefix already holds the answer.
        return True
    kept = sorted(
        (ranking for _target, _score, ranking in candidates),
        reverse=True,
    )[limit - 1]
    return last_score + noise / 2.0 <= kept


def _apply_epsilon(
    candidates: list[tuple],
    *,
    epsilon: float | None,
    score_index: int,
) -> list[tuple]:
    if epsilon is None or not candidates:
        return candidates
    best_score = max(
        float(candidate[score_index])
        for candidate in candidates
    )
    return [
        candidate
        for candidate in candidates
        if float(candidate[score_index]) >= best_score - epsilon
    ]


def _ranking_score(
    target: AnalysisTarget,
    score: float,
    noise: float,
) -> float:
    if noise <= 0.0:
        return score
    identity = (
        f"{target.catalog_uuid}\0{target.track_uuid}"
    ).encode("utf-8")
    digest = hashlib.sha256(identity).digest()
    fraction = int.from_bytes(digest[:8], "big") / float(2**64 - 1)
    deterministic_jitter = fraction - 0.5
    return score + deterministic_jitter * noise


def _target_ids(
    targets: Sequence[AnalysisTarget],
) -> list[int]:
    return [target.track_id for target in targets]


def _result_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError(
            "Search result limit must be a non-negative integer"
        )
    return limit


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name} must be a finite number"
        ) from error
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be a finite number")
    return number
