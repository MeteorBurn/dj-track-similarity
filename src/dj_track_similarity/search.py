from __future__ import annotations

from dataclasses import dataclass
from math import inf

import numpy as np

from .database import LibraryDatabase
from .models import SearchResult, Track


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
    def __init__(self, db: LibraryDatabase, *, embedding_key: str = "mert") -> None:
        self.db = db
        self.embedding_key = embedding_key

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
        tracks, matrix = self.db.load_embedding_matrix(self.embedding_key)
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
        scores = matrix @ centroid
        seed_tracks = [track_by_id[track_id] for track_id in context_set]

        candidates: list[tuple[Track, float, float]] = []
        for index in np.argsort(-scores):
            track = tracks[int(index)]
            score = float(scores[int(index)])
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
        vector: np.ndarray,
        *,
        filters: SearchFilters | None = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        filters = filters or SearchFilters()
        tracks, matrix = self.db.load_embedding_matrix(self.embedding_key)
        if matrix.size == 0:
            return []

        query = _normalize(np.asarray(vector, dtype=np.float32).reshape(-1))
        scores = matrix @ query
        candidates: list[tuple[Track, float, float]] = []
        for index in np.argsort(-scores):
            track = tracks[int(index)]
            score = float(scores[int(index)])
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


def _normalize(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        raise ValueError("Cannot normalize zero vector")
    return (vector / norm).astype(np.float32)


def _passes_filters(track: Track, seeds: list[Track], score: float, filters: SearchFilters) -> bool:
    if filters.min_similarity is not None and score < filters.min_similarity:
        return False
    if filters.energy_min is not None and (track.energy is None or track.energy < filters.energy_min):
        return False
    if filters.energy_max is not None and (track.energy is None or track.energy > filters.energy_max):
        return False
    if filters.bpm_tolerance is not None and not _bpm_compatible(track, seeds, filters.bpm_tolerance):
        return False
    if filters.key_compatibility == "compatible" and not _key_compatible(track, seeds):
        return False
    return True


def _ranking_score(track: Track, score: float, noise: float) -> float:
    if noise <= 0:
        return score
    bounded_noise = max(0.0, min(1.0, noise))
    deterministic_jitter = ((track.id % 97) / 96.0) - 0.5
    return score + deterministic_jitter * bounded_noise


def _bpm_compatible(track: Track, seeds: list[Track], tolerance: float) -> bool:
    if track.bpm is None:
        return False
    seed_bpms = [seed.bpm for seed in seeds if seed.bpm is not None]
    if not seed_bpms:
        return True
    return min(_tempo_distance(track.bpm, seed_bpm) for seed_bpm in seed_bpms) <= tolerance


def _tempo_distance(candidate_bpm: float, seed_bpm: float) -> float:
    candidate_variants = [candidate_bpm / 2, candidate_bpm, candidate_bpm * 2]
    seed_variants = [seed_bpm / 2, seed_bpm, seed_bpm * 2]
    best = inf
    for candidate in candidate_variants:
        for seed in seed_variants:
            best = min(best, abs(candidate - seed))
    return best


def _key_compatible(track: Track, seeds: list[Track]) -> bool:
    if not track.musical_key:
        return False
    seed_keys = [seed.musical_key for seed in seeds if seed.musical_key]
    if not seed_keys:
        return True
    return any(_camelot_compatible(track.musical_key or "", seed_key or "") for seed_key in seed_keys)


def _camelot_compatible(candidate: str, seed: str) -> bool:
    parsed_candidate = _parse_camelot(candidate)
    parsed_seed = _parse_camelot(seed)
    if parsed_candidate is None or parsed_seed is None:
        return candidate.strip().lower() == seed.strip().lower()
    candidate_number, candidate_letter = parsed_candidate
    seed_number, seed_letter = parsed_seed
    if candidate_number == seed_number:
        return True
    if candidate_letter != seed_letter:
        return False
    return candidate_number in {_wrap_camelot(seed_number - 1), _wrap_camelot(seed_number + 1)}


def _parse_camelot(value: str) -> tuple[int, str] | None:
    text = value.strip().upper()
    if len(text) not in {2, 3}:
        return None
    number_text, letter = text[:-1], text[-1]
    if letter not in {"A", "B"}:
        return None
    try:
        number = int(number_text)
    except ValueError:
        return None
    if number < 1 or number > 12:
        return None
    return number, letter


def _wrap_camelot(number: int) -> int:
    return ((number - 1) % 12) + 1
