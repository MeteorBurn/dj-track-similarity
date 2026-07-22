from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from .database import LibraryDatabase
from .models import SearchResult, Track
from .tempo_resolution import resolve_tempo_evidence, tempo_filter_compatible
from .track_resolution import camelot_compatible, resolve_track_camelot, resolve_track_energy
from .vector_index import ExactVectorSearchBackend, VectorSearchBackend, VectorSearchHit

FloatArray = NDArray[np.float32]
CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT: Final = 0.35


@dataclass(frozen=True)
class SearchFilters:
    bpm_tolerance: float | None = None
    key_compatibility: str | None = None
    energy_min: float | None = None
    energy_max: float | None = None
    min_similarity: float | None = None
    epsilon: float | None = None
    noise: float = 0.0


class SimilaritySearch:
    def __init__(
        self,
        db: LibraryDatabase,
        *,
        embedding_key: str = "mert",
        vector_backend: VectorSearchBackend | None = None,
    ) -> None:
        self.db = db
        self.embedding_key = embedding_key
        self.vector_backend = vector_backend if vector_backend is not None else ExactVectorSearchBackend()

    def search(
        self,
        seed_track_ids: list[int],
        *,
        filters: SearchFilters | None = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        if not seed_track_ids:
            raise ValueError("At least one seed track is required")
        filters = filters or SearchFilters()
        tracks, matrix = self.db.load_embedding_matrix(
            self.embedding_key,
            include_metadata=_needs_filter_metadata(filters),
        )
        if matrix.size == 0:
            return []

        seed_set = set(seed_track_ids)
        context_set = seed_set
        track_by_id = {track.id: track for track in tracks}
        missing = [track_id for track_id in seed_track_ids if track_id not in track_by_id]
        if missing:
            raise ValueError(f"Context tracks missing embeddings: {missing}")

        context_indices = [index for index, track in enumerate(tracks) if track.id in context_set]
        centroid = matrix[context_indices].mean(axis=0)
        centroid = _normalize(centroid)
        hits = self.vector_backend.search(matrix, _track_ids(tracks), centroid, limit=len(tracks))
        seed_tracks = [track_by_id[track_id] for track_id in context_set]

        candidates: list[tuple[Track, float, float]] = []
        for hit in hits:
            track = _track_for_hit(hit, tracks, track_by_id)
            score = hit.score
            if track.id in context_set:
                continue
            if not _passes_filters(track, seed_tracks, score, filters):
                continue
            candidates.append((track, score, _ranking_score(track, score, filters.noise)))

        if filters.epsilon is not None and candidates:
            best_score = max(score for _, score, _ in candidates)
            candidates = [candidate for candidate in candidates if candidate[1] >= best_score - filters.epsilon]

        results: list[SearchResult] = []
        for track, score, _ in sorted(candidates, key=lambda candidate: candidate[2], reverse=True):
            results.append(SearchResult(track=track, score=score))
            if len(results) >= limit:
                break
        return results

    def search_vector(
        self,
        vector: FloatArray,
        *,
        filters: SearchFilters | None = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        filters = filters or SearchFilters()
        tracks, matrix = self.db.load_embedding_matrix(
            self.embedding_key,
            include_metadata=_needs_filter_metadata(filters),
        )
        if matrix.size == 0:
            return []

        query = _normalize(np.asarray(vector, dtype=np.float32).reshape(-1))
        track_by_id = {track.id: track for track in tracks}
        hits = self.vector_backend.search(matrix, _track_ids(tracks), query, limit=len(tracks))
        candidates: list[tuple[Track, float, float]] = []
        for hit in hits:
            track = _track_for_hit(hit, tracks, track_by_id)
            score = hit.score
            if not _passes_filters(track, [], score, filters):
                continue
            candidates.append((track, score, _ranking_score(track, score, filters.noise)))

        if filters.epsilon is not None and candidates:
            best_score = max(score for _, score, _ in candidates)
            candidates = [candidate for candidate in candidates if candidate[1] >= best_score - filters.epsilon]

        results: list[SearchResult] = []
        for track, score, _ in sorted(candidates, key=lambda candidate: candidate[2], reverse=True):
            results.append(SearchResult(track=track, score=score))
            if len(results) >= limit:
                break
        return results

    def search_contrast_vectors(
        self,
        *,
        positive_vectors: list[FloatArray],
        negative_vectors: list[FloatArray] | None = None,
        filters: SearchFilters | None = None,
        limit: int = 50,
        negative_weight: float = CLAP_TEXT_NEGATIVE_WEIGHT_DEFAULT,
    ) -> list[SearchResult]:
        if not positive_vectors:
            raise ValueError("At least one positive query vector is required")
        filters = filters or SearchFilters()
        tracks, matrix = self.db.load_embedding_matrix(
            self.embedding_key,
            include_metadata=_needs_filter_metadata(filters),
        )
        if matrix.size == 0:
            return []

        positive_scores, negative_scores, contrast_scores, bounded_weight = _contrast_vector_scores(
            matrix,
            positive_vectors=positive_vectors,
            negative_vectors=negative_vectors or [],
            negative_weight=negative_weight,
        )

        candidates: list[tuple[Track, float, float, dict[str, float]]] = []
        for index in np.argsort(-contrast_scores):
            track = tracks[int(index)]
            score = float(contrast_scores[int(index)])
            if not _passes_filters(track, [], score, filters):
                continue
            breakdown = _contrast_score_breakdown(
                positive_scores,
                negative_scores,
                contrast_scores,
                bounded_weight,
                int(index),
            )
            candidates.append((track, score, _ranking_score(track, score, filters.noise), breakdown))

        if filters.epsilon is not None and candidates:
            best_score = max(score for _, score, _, _ in candidates)
            candidates = [candidate for candidate in candidates if candidate[1] >= best_score - filters.epsilon]

        results: list[SearchResult] = []
        for track, score, _, breakdown in sorted(candidates, key=lambda candidate: candidate[2], reverse=True):
            results.append(SearchResult(track=track, score=score, score_breakdown=breakdown))
            if len(results) >= limit:
                break
        return results


def _normalize(vector: FloatArray) -> FloatArray:
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        raise ValueError("Cannot normalize zero vector")
    return (vector / norm).astype(np.float32)


def _normalize_matrix(vectors: list[FloatArray]) -> FloatArray:
    normalized = [_normalize(np.asarray(vector, dtype=np.float32).reshape(-1)) for vector in vectors]
    return np.vstack(normalized).astype(np.float32)


def _contrast_vector_scores(
    matrix: FloatArray,
    *,
    positive_vectors: list[FloatArray],
    negative_vectors: list[FloatArray],
    negative_weight: float,
) -> tuple[FloatArray, FloatArray, FloatArray, float]:
    positive_bank = _normalize(np.mean(_normalize_matrix(positive_vectors), axis=0))
    positive_scores = matrix @ positive_bank
    negative_scores = np.max(matrix @ _normalize_matrix(negative_vectors).T, axis=1) if negative_vectors else np.zeros_like(positive_scores)
    bounded_weight = max(0.0, negative_weight)
    return positive_scores, negative_scores, positive_scores - bounded_weight * negative_scores, bounded_weight


def _contrast_score_breakdown(
    positive_scores: FloatArray,
    negative_scores: FloatArray,
    contrast_scores: FloatArray,
    negative_weight: float,
    index: int,
) -> dict[str, float]:
    return {
        "positive": float(positive_scores[index]),
        "negative": float(negative_scores[index]),
        "contrast": float(contrast_scores[index]),
        "negative_weight": negative_weight,
    }


def _track_ids(tracks: list[Track]) -> list[int]:
    return [track.id for track in tracks]


def _track_for_hit(hit: VectorSearchHit, tracks: list[Track], track_by_id: dict[int, Track]) -> Track:
    if hit.index is not None:
        if hit.index < 0 or hit.index >= len(tracks):
            raise ValueError(f"Vector search backend returned out-of-range index: {hit.index}")
        track = tracks[hit.index]
        if track.id != hit.track_id:
            raise ValueError(
                f"Vector search backend returned mismatched track id/index: {hit.track_id} != {track.id}",
            )
        return track
    try:
        return track_by_id[hit.track_id]
    except KeyError as error:
        raise ValueError(f"Vector search backend returned unknown track id: {hit.track_id}") from error


def _passes_filters(track: Track, seeds: list[Track], score: float, filters: SearchFilters) -> bool:
    if filters.min_similarity is not None and score < filters.min_similarity:
        return False
    energy = resolve_track_energy(track)
    if filters.energy_min is not None and (energy is None or energy < filters.energy_min):
        return False
    if filters.energy_max is not None and (energy is None or energy > filters.energy_max):
        return False
    if filters.bpm_tolerance is not None and not _bpm_compatible(track, seeds, filters.bpm_tolerance):
        return False
    if filters.key_compatibility == "compatible" and not _key_compatible(track, seeds):
        return False
    return True


def _needs_filter_metadata(filters: SearchFilters) -> bool:
    return any(
        (
            filters.bpm_tolerance is not None,
            filters.key_compatibility == "compatible",
            filters.energy_min is not None,
            filters.energy_max is not None,
        )
    )


def _ranking_score(track: Track, score: float, noise: float) -> float:
    if noise <= 0:
        return score
    bounded_noise = max(0.0, min(1.0, noise))
    deterministic_jitter = ((track.id % 97) / 96.0) - 0.5
    return score + deterministic_jitter * bounded_noise


def _bpm_compatible(track: Track, seeds: list[Track], tolerance: float) -> bool:
    candidate = resolve_tempo_evidence(track)
    if candidate.bpm is None:
        return False
    references = [evidence for seed in seeds if (evidence := resolve_tempo_evidence(seed)).bpm is not None]
    if not references:
        return True
    return any(tempo_filter_compatible(candidate, reference, tolerance) for reference in references)


def _key_compatible(track: Track, seeds: list[Track]) -> bool:
    track_key = resolve_track_camelot(track)
    if not track_key:
        return False
    seed_keys = [key for seed in seeds if (key := resolve_track_camelot(seed))]
    if not seed_keys:
        return True
    return any(camelot_compatible(track_key, seed_key) for seed_key in seed_keys)


# ---------------------------------------------------------------------------
# v7 read-path adapter — embedding search from sidecar tables (Todo 21)
# ---------------------------------------------------------------------------

def search_v7(
    family: str,
    seed_track_ids: list[int],
    artifacts_conn: "sqlite3.Connection",
    core_contracts_conn: "sqlite3.Connection",
    expected_contract_hash: str,
    limit: int = 50,
) -> list[tuple[int, float]]:
    """Search the v7 ``<family>_embeddings`` sidecar table by cosine similarity.

    Reads embeddings for all tracks from the sidecar, averages the seed vectors
    into a normalised centroid, then ranks every non-seed track by cosine
    similarity against that centroid.

    Args:
        family: Embedding family name, e.g. ``'mert'``, ``'clap'``, ``'maest'``.
        seed_track_ids: One or more track IDs to use as the query centroid.
        artifacts_conn: Open connection to the artifacts sidecar database.
        core_contracts_conn: Open connection to the Core database (for contract
            validation via :func:`read_valid_embedding`).
        expected_contract_hash: Contract hash computed from the currently
            running adapter — rows with a different hash are silently skipped.
        limit: Maximum number of results to return (default 50).

    Returns:
        A list of ``(track_id, cosine_similarity)`` tuples sorted by similarity
        descending, excluding the seed tracks themselves.  Orphan or invalid
        sidecar rows are silently ignored (Todo 10 pattern).
    """
    import sqlite3 as _sqlite3

    from .db_artifacts import read_valid_embedding

    if not seed_track_ids:
        raise ValueError("At least one seed track ID is required")

    table = f"{family}_embeddings"

    # Fetch all track_ids from the sidecar table
    try:
        all_rows = artifacts_conn.execute(
            f"SELECT track_id FROM {table}",  # noqa: S608
        ).fetchall()
    except _sqlite3.OperationalError:
        return []

    all_track_ids: list[int] = [int(row[0]) for row in all_rows]
    if not all_track_ids:
        return []

    seed_set = set(seed_track_ids)

    # Read and validate all embeddings
    track_vectors: dict[int, FloatArray] = {}
    for track_id in all_track_ids:
        vec = read_valid_embedding(
            family,
            track_id,
            artifacts_conn,
            expected_contract_hash,
            core_contracts_conn,
        )
        if vec is not None:
            track_vectors[track_id] = vec

    if not track_vectors:
        return []

    # Build normalised centroid from seed vectors
    seed_vecs = [track_vectors[tid] for tid in seed_track_ids if tid in track_vectors]
    if not seed_vecs:
        raise ValueError(f"No valid embeddings found for seed tracks: {seed_track_ids}")

    centroid = np.mean(np.vstack(seed_vecs), axis=0).astype(np.float32)
    centroid = _normalize(centroid)

    # Score all non-seed tracks
    results: list[tuple[int, float]] = []
    for track_id, vec in track_vectors.items():
        if track_id in seed_set:
            continue
        norm = float(np.linalg.norm(vec))
        if norm == 0:
            continue
        unit_vec = (vec / norm).astype(np.float32)
        score = float(np.dot(centroid, unit_vec))
        results.append((track_id, score))

    results.sort(key=lambda item: item[1], reverse=True)
    return results[:limit]
