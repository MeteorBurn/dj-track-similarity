from __future__ import annotations

from typing import Literal

from .database import LibraryDatabase
from .models import SearchResult
from .sonara_similarity_scoring import (
    ComparableTrack,
    centroid,
    clean_mixer_weights,
    clean_modifiers,
    custom_numeric_fields,
    numeric_dimensions,
    numeric_weights_for_mode,
    score_candidate,
    score_custom_candidate,
    sonara_features,
    tonal_context,
)


SonaraSearchMode = Literal["balanced", "vibe", "sound", "dj_transition", "custom"]


class SonaraSimilaritySearch:
    def __init__(self, db: LibraryDatabase) -> None:
        self.db = db

    def search(
        self,
        seed_track_ids: list[int],
        *,
        mode: SonaraSearchMode = "balanced",
        mixer_weights: dict[str, float] | None = None,
        modifiers: dict[str, float] | None = None,
        min_similarity: float | None = None,
        limit: int = 50,
    ) -> list[SearchResult]:
        if not seed_track_ids:
            raise ValueError("At least one seed track is required")
        if mode not in {"balanced", "vibe", "sound", "dj_transition", "custom"}:
            raise ValueError(f"Unsupported SONARA search mode: {mode}")

        all_tracks = self.db.list_tracks()
        context_ids = set(seed_track_ids)
        existing_ids = {track.id for track in all_tracks}
        unknown = [track_id for track_id in seed_track_ids if track_id not in existing_ids]
        if unknown:
            raise ValueError(f"Unknown context tracks: {unknown}")

        tracks = [ComparableTrack(track, features) for track in all_tracks if (features := sonara_features(track))]
        track_by_id = {item.track.id: item for item in tracks}
        missing = [track_id for track_id in seed_track_ids if track_id not in track_by_id]
        if missing:
            raise ValueError(f"Context tracks missing SONARA features: {missing}")
        if not tracks:
            return []

        use_custom = mode == "custom" or mixer_weights is not None or modifiers is not None
        if use_custom:
            return self._search_custom(
                tracks,
                track_by_id,
                context_ids,
                mixer_weights=mixer_weights,
                modifiers=modifiers,
                min_similarity=min_similarity,
                limit=limit,
            )

        numeric_weights = numeric_weights_for_mode(mode)
        dimensions, ranges = numeric_dimensions(tracks, numeric_weights)
        context = [track_by_id[track_id] for track_id in context_ids]
        feature_centroid = centroid(context, dimensions, ranges)
        context_tones = tonal_context(context)

        candidates: list[SearchResult] = []
        for item in tracks:
            if item.track.id in context_ids:
                continue
            score = score_candidate(item, mode, dimensions, ranges, feature_centroid, context_tones)
            if score is None:
                continue
            if min_similarity is not None and score < min_similarity:
                continue
            candidates.append(SearchResult(track=item.track, score=score))

        candidates.sort(key=lambda result: result.score, reverse=True)
        return candidates[: max(0, limit)]

    def _search_custom(
        self,
        tracks: list[ComparableTrack],
        track_by_id: dict[int, ComparableTrack],
        context_ids: set[int],
        *,
        mixer_weights: dict[str, float] | None,
        modifiers: dict[str, float] | None,
        min_similarity: float | None,
        limit: int,
    ) -> list[SearchResult]:
        clean_mixer = clean_mixer_weights(mixer_weights)
        clean_directional_modifiers = clean_modifiers(modifiers)
        numeric_weights = custom_numeric_fields(clean_mixer, clean_directional_modifiers)
        dimensions, ranges = numeric_dimensions(tracks, numeric_weights)
        context = [track_by_id[track_id] for track_id in context_ids]
        feature_centroid = centroid(context, dimensions, ranges)
        context_tones = tonal_context(context)

        candidates: list[SearchResult] = []
        for item in tracks:
            if item.track.id in context_ids:
                continue
            scored = score_custom_candidate(
                item,
                dimensions,
                ranges,
                feature_centroid,
                context_tones,
                clean_mixer,
                clean_directional_modifiers,
            )
            if scored is None:
                continue
            score, breakdown = scored
            if min_similarity is not None and score < min_similarity:
                continue
            candidates.append(SearchResult(track=item.track, score=score, score_breakdown=breakdown))

        candidates.sort(key=lambda result: result.score, reverse=True)
        return candidates[: max(0, limit)]
