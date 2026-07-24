from __future__ import annotations

from collections.abc import Sequence
import math
from typing import Literal, Protocol

from .analysis_models import (
    AnalysisOutput,
    AnalysisTarget,
    SonaraFeatureRow,
)
from .search import SimilaritySearchResult
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
    tonal_context,
)


SonaraSearchMode = Literal[
    "balanced",
    "vibe",
    "sound",
    "dj_transition",
    "custom",
]
_SONARA_SEARCH_MODES = frozenset(
    {"balanced", "vibe", "sound", "dj_transition", "custom"}
)


class SonaraSearchRepository(Protocol):
    """Public repository surface required by SONARA Core search."""

    catalog_uuid: str

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        ...

    def load_sonara_feature_rows(
        self,
        output: AnalysisOutput,
        *,
        targets: Sequence[AnalysisTarget] | None = None,
    ) -> tuple[SonaraFeatureRow, ...]:
        ...


class SonaraSearchUnavailable(RuntimeError):
    """Raised when no exact active SONARA Core output can serve search."""


class SonaraSimilaritySearch:
    """SONARA feature-mixer search over the exact active Core contract.

    The separate 48-dimensional SONARA representation remains data-only and is
    intentionally not exposed as a public search mode.
    """

    def __init__(
        self,
        repository: SonaraSearchRepository,
        *,
        analysis_output: AnalysisOutput | None = None,
    ) -> None:
        if (
            analysis_output is not None
            and analysis_output.key != ("sonara", "core")
        ):
            raise ValueError(
                "analysis_output must be a SONARA Core output"
            )
        self.repository = repository
        self.analysis_output = analysis_output

    def active_output(self) -> AnalysisOutput:
        output = self.repository.active_analysis_output(
            "sonara",
            "core",
        )
        if output is None:
            raise SonaraSearchUnavailable(
                "No active SONARA Core contract is registered"
            )
        if output.key != ("sonara", "core"):
            raise RuntimeError(
                "Active SONARA resolver returned the wrong output identity"
            )
        if self.analysis_output is None:
            return output
        if (
            self.analysis_output.contract_hash != output.contract_hash
            or self.analysis_output.contract.canonical_payload_json
            != output.contract.canonical_payload_json
        ):
            raise SonaraSearchUnavailable(
                "Requested SONARA Core contract is no longer active"
            )
        return self.analysis_output

    def resolve_targets(
        self,
        track_ids: Sequence[int],
    ) -> tuple[AnalysisTarget, ...]:
        """Resolve request IDs to current tracks with active SONARA Core."""

        requested = _requested_track_ids(track_ids)
        output = self.active_output()
        rows = self.repository.load_sonara_feature_rows(output)
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
                "Tracks are not current and SONARA-ready: "
                f"{missing}"
            )
        return tuple(target_by_id[track_id] for track_id in requested)

    def search(
        self,
        seed_targets: Sequence[AnalysisTarget],
        *,
        candidate_targets: Sequence[AnalysisTarget] | None = None,
        mode: SonaraSearchMode = "balanced",
        mixer_weights: dict[str, float] | None = None,
        modifiers: dict[str, float] | None = None,
        min_similarity: float | None = None,
        limit: int = 50,
    ) -> list[SimilaritySearchResult]:
        if mode not in _SONARA_SEARCH_MODES:
            raise ValueError(
                f"Unsupported SONARA search mode: {mode}"
            )
        if min_similarity is not None and not math.isfinite(
            float(min_similarity)
        ):
            raise ValueError("min_similarity must be finite")
        bounded_limit = _result_limit(limit)
        seeds = _validate_targets(
            seed_targets,
            catalog_uuid=self.repository.catalog_uuid,
            field_name="seed_targets",
            require_nonempty=True,
        )
        candidates = _optional_targets(
            candidate_targets,
            catalog_uuid=self.repository.catalog_uuid,
        )
        output = self.active_output()
        requested = (
            None
            if candidates is None
            else _merge_targets(seeds, candidates)
        )
        if requested is None:
            seed_rows = self.repository.load_sonara_feature_rows(
                output,
                targets=seeds,
            )
            _validate_rows(
                seed_rows,
                output=output,
                catalog_uuid=self.repository.catalog_uuid,
            )
        rows = self.repository.load_sonara_feature_rows(
            output,
            targets=requested,
        )
        _validate_rows(
            rows,
            output=output,
            catalog_uuid=self.repository.catalog_uuid,
        )
        tracks = [
            ComparableTrack(row.target, row.values)
            for row in rows
        ]
        track_by_target = {
            item.target: item for item in tracks
        }
        missing_seeds = [
            target
            for target in seeds
            if target not in track_by_target
        ]
        if missing_seeds:
            raise ValueError(
                "Seed tracks are missing active SONARA Core features: "
                f"{[target.track_id for target in missing_seeds]}"
            )

        use_custom = (
            mode == "custom"
            or mixer_weights is not None
            or modifiers is not None
        )
        if use_custom:
            return self._search_custom(
                tracks,
                track_by_target,
                seeds,
                mixer_weights=mixer_weights,
                modifiers=modifiers,
                min_similarity=min_similarity,
                limit=bounded_limit,
            )

        numeric_weights = numeric_weights_for_mode(mode)
        dimensions, ranges = numeric_dimensions(
            tracks,
            numeric_weights,
        )
        context = [
            track_by_target[target] for target in seeds
        ]
        feature_centroid = centroid(
            context,
            dimensions,
            ranges,
        )
        context_tones = tonal_context(context)

        ranked: list[SimilaritySearchResult] = []
        for item in tracks:
            if item.target in seeds:
                continue
            score = score_candidate(
                item,
                mode,
                dimensions,
                ranges,
                feature_centroid,
                context_tones,
                tempo_context=context,
            )
            if score is None:
                continue
            if (
                min_similarity is not None
                and score < min_similarity
            ):
                continue
            ranked.append(
                SimilaritySearchResult(
                    target=item.target,
                    score=score,
                )
            )

        ranked.sort(
            key=lambda result: result.score,
            reverse=True,
        )
        return ranked[:bounded_limit]

    def _search_custom(
        self,
        tracks: list[ComparableTrack],
        track_by_target: dict[AnalysisTarget, ComparableTrack],
        context_targets: tuple[AnalysisTarget, ...],
        *,
        mixer_weights: dict[str, float] | None,
        modifiers: dict[str, float] | None,
        min_similarity: float | None,
        limit: int,
    ) -> list[SimilaritySearchResult]:
        clean_mixer = clean_mixer_weights(mixer_weights)
        clean_directional_modifiers = clean_modifiers(modifiers)
        numeric_weights = custom_numeric_fields(
            clean_mixer,
            clean_directional_modifiers,
        )
        dimensions, ranges = numeric_dimensions(
            tracks,
            numeric_weights,
        )
        context = [
            track_by_target[target]
            for target in context_targets
        ]
        context_set = frozenset(context_targets)
        feature_centroid = centroid(
            context,
            dimensions,
            ranges,
        )
        context_tones = tonal_context(context)

        ranked: list[SimilaritySearchResult] = []
        for item in tracks:
            if item.target in context_set:
                continue
            scored = score_custom_candidate(
                item,
                dimensions,
                ranges,
                feature_centroid,
                context_tones,
                clean_mixer,
                clean_directional_modifiers,
                tempo_context=context,
            )
            if scored is None:
                continue
            score, breakdown = scored
            if (
                min_similarity is not None
                and score < min_similarity
            ):
                continue
            ranked.append(
                SimilaritySearchResult(
                    target=item.target,
                    score=score,
                    score_breakdown=breakdown,
                )
            )

        ranked.sort(
            key=lambda result: result.score,
            reverse=True,
        )
        return ranked[:limit]


def _validate_rows(
    rows: Sequence[SonaraFeatureRow],
    *,
    output: AnalysisOutput,
    catalog_uuid: str,
) -> None:
    seen_targets: set[AnalysisTarget] = set()
    seen_track_ids: set[int] = set()
    for row in rows:
        if not isinstance(row, SonaraFeatureRow):
            raise TypeError(
                "Analysis repository returned a non-SonaraFeatureRow value"
            )
        if (
            row.output.contract_hash != output.contract_hash
            or row.output.contract.canonical_payload_json
            != output.contract.canonical_payload_json
        ):
            raise RuntimeError(
                "Analysis repository returned SONARA features "
                "from another contract"
            )
        if row.target.catalog_uuid != catalog_uuid:
            raise RuntimeError(
                "Analysis repository returned SONARA features "
                "from another catalog"
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


def _result_limit(limit: int) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError(
            "SONARA search result limit must be a non-negative integer"
        )
    return limit
