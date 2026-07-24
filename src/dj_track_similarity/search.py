from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import math
from typing import Final, Literal, Protocol

import numpy as np
from numpy.typing import NDArray

from .analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    AnalysisVectorRow,
)
from .vector_index import (
    ExactVectorSearchBackend,
    VectorIndexUnavailable,
    VectorSearchBackend,
    VectorSearchHit,
)


FloatArray = NDArray[np.float32]
EmbeddingFamily = Literal["maest", "mert", "muq", "clap"]
CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT: Final = 0.35
_EMBEDDING_FAMILIES = frozenset({"maest", "mert", "muq", "clap"})


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
    """A ranked result with the full validated v7 track identity."""

    target: AnalysisTarget
    score: float
    score_breakdown: Mapping[str, float] | None = None


class SimilaritySearch:
    """Cosine search over one active, immutable ML embedding contract."""

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
        contract = analysis_output.contract
        if (
            contract.analysis_family != family
            or contract.output_kind != "embedding"
        ):
            raise ValueError(
                "analysis_output does not match the requested "
                "embedding family"
            )
        if contract.normalization != "l2":
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
        self.active_output()

    def active_output(self) -> AnalysisOutput:
        """Resolve and validate the exact active embedding contract."""

        output = self.repository.active_analysis_output(
            self.analysis_family,
            "embedding",
        )
        if output is None:
            raise VectorIndexUnavailable(
                "No active embedding contract is registered for "
                f"{self.analysis_family!r}"
            )
        contract = output.contract
        if (
            contract.analysis_family != self.analysis_family
            or contract.output_kind != "embedding"
        ):
            raise RuntimeError(
                "Active embedding resolver returned the wrong output identity"
            )
        if contract.normalization != "l2":
            raise VectorIndexUnavailable(
                "ML cosine search requires an active normalization='l2' "
                f"contract, got {contract.normalization!r}"
            )
        if contract.dim is None or contract.dim <= 0:
            raise VectorIndexUnavailable(
                "Active embedding contract has no positive dimension"
            )
        if (
            self.analysis_output.contract_hash != output.contract_hash
            or self.analysis_output.contract.canonical_payload_json
            != output.contract.canonical_payload_json
        ):
            raise VectorIndexUnavailable(
                "Current runtime embedding contract does not match the "
                f"active {self.analysis_family!r} contract; reanalysis "
                "is required before search"
            )
        return self.analysis_output

    def resolve_targets(
        self,
        track_ids: Sequence[int],
    ) -> tuple[AnalysisTarget, ...]:
        """Resolve request IDs to current, search-ready v7 identities.

        The result preserves caller order. A missing ID is deliberately not
        guessed: it can mean an unknown track, a missing file, or a current
        track without the active embedding, and all three are not searchable.
        """

        requested = _requested_track_ids(track_ids)
        output = self.active_output()
        rows = self.repository.load_analysis_vectors(output)
        _validate_rows(
            rows,
            output=output,
            catalog_uuid=self.repository.catalog_uuid,
        )
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

        target_to_index = {
            row.target: index for index, row in enumerate(rows)
        }
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
        matrix = _matrix(rows, output)
        centroid = _normalize(
            np.mean(
                matrix[
                    [target_to_index[target] for target in seeds]
                ],
                axis=0,
            )
        )
        return self._rank(
            rows,
            matrix,
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
            rows,
            _matrix(rows, output),
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
        matrix = _matrix(rows, output)
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

    def _load_rows(
        self,
        *,
        seeds: tuple[AnalysisTarget, ...],
        candidate_targets: tuple[AnalysisTarget, ...] | None,
    ) -> tuple[AnalysisOutput, tuple[AnalysisVectorRow, ...]]:
        output = self.active_output()
        requested: tuple[AnalysisTarget, ...] | None
        if candidate_targets is None:
            if seeds:
                seed_rows = self.repository.load_analysis_vectors(
                    output,
                    targets=seeds,
                )
                _validate_rows(
                    seed_rows,
                    output=output,
                    catalog_uuid=self.repository.catalog_uuid,
                )
            requested = None
        else:
            requested = _merge_targets(seeds, candidate_targets)
        rows = self.repository.load_analysis_vectors(
            output,
            targets=requested,
        )
        _validate_rows(
            rows,
            output=output,
            catalog_uuid=self.repository.catalog_uuid,
        )
        return output, rows

    def _rank(
        self,
        rows: tuple[AnalysisVectorRow, ...],
        matrix: FloatArray,
        query: FloatArray,
        *,
        excluded: frozenset[AnalysisTarget],
        filters: SearchFilters,
        limit: int,
    ) -> list[SimilaritySearchResult]:
        targets = tuple(row.target for row in rows)
        hits = self.vector_backend.search(
            matrix,
            targets,
            query,
            limit=len(targets),
        )
        target_to_index = {
            target: index for index, target in enumerate(targets)
        }
        candidates: list[
            tuple[AnalysisTarget, float, float]
        ] = []
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

        candidates = _apply_epsilon(
            candidates,
            epsilon=filters.epsilon,
            score_index=1,
        )
        bounded_limit = _result_limit(limit)
        ranked = sorted(
            candidates,
            key=lambda item: item[2],
            reverse=True,
        )[:bounded_limit]
        return [
            SimilaritySearchResult(target=target, score=score)
            for target, score, _ranking in ranked
        ]


def _validate_rows(
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
        if (
            row.output.contract_hash != output.contract_hash
            or row.output.contract.canonical_payload_json
            != output.contract.canonical_payload_json
        ):
            raise RuntimeError(
                "Analysis repository returned a vector from another contract"
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


def _matrix(
    rows: Sequence[AnalysisVectorRow],
    output: AnalysisOutput,
) -> FloatArray:
    dim = output.contract.dim
    if dim is None:
        raise ValueError("Embedding contract has no dimension")
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
    norms = np.linalg.norm(
        matrix.astype(np.float64, copy=False),
        axis=1,
    )
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
    if query.shape != (output.contract.dim,):
        raise ValueError(
            "Query vector dimension does not match the active contract: "
            f"{query.shape[0]} != {output.contract.dim}"
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
        dim = output.contract.dim
        assert dim is not None
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
        negative_scores = np.max(
            matrix @ negative_bank.T,
            axis=1,
        )
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
        f"{target.catalog_uuid}\0{target.track_uuid}\0"
        f"{target.content_generation}"
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
