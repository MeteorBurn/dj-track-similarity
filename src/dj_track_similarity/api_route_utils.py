from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol

from fastapi import HTTPException

from .analysis_models import ClassifierSpecification
from .api_schemas import TrackIdentityRequest
from .classifier_manifest import classifier_manifest_from_info
from .classifier_scoring import classifier_specification_from_manifest
from .track_models import TrackIdentity


class _TrackIdentityRepository(Protocol):
    catalog_uuid: str

    def get_track_identity(
        self,
        track_id: int,
        *,
        include_missing: bool = False,
    ) -> TrackIdentity | None: ...


def current_classifier_specifications(
    classifier_infos: Sequence[Mapping[str, object]],
) -> tuple[ClassifierSpecification, ...]:
    specifications: list[ClassifierSpecification] = []
    for classifier_info in classifier_infos:
        if not bool(classifier_info.get("is_scoring_compatible", True)):
            continue
        try:
            manifest = classifier_manifest_from_info(classifier_info)
            if manifest is None or not manifest.is_scoring_compatible:
                continue
            specifications.append(classifier_specification_from_manifest(manifest))
        except (OSError, ValueError):
            continue
    return tuple(specifications)


def require_current_track_identity(
    repository: _TrackIdentityRepository,
    expected: TrackIdentityRequest,
) -> TrackIdentity:
    """Resolve and compare one exact current identity.

    This guard is for delayed mutations whose numeric track id may have been
    rebound by a database switch or content replacement.
    """

    current = repository.get_track_identity(expected.track_id)
    if current is None:
        raise KeyError(f"Track {expected.track_id} is not current")
    if (
        current.catalog_uuid != expected.catalog_uuid
        or current.track_uuid != expected.track_uuid
        or current.content_generation != expected.content_generation
    ):
        raise RuntimeError(
            f"Track {expected.track_id} identity is stale; refresh the current catalog"
        )
    return current


def query_classifier_min_scores(raw: str | None) -> dict[str, float]:
    if raw is None or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=422, detail="classifier_min_scores must be a JSON object") from error
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="classifier_min_scores must be a JSON object")
    return valid_classifier_min_scores(parsed)


def valid_classifier_min_scores(scores: dict[str, float]) -> dict[str, float]:
    result: dict[str, float] = {}
    for classifier, value in scores.items():
        score = float(value)
        if score < 0.0 or score > 1.0:
            raise HTTPException(status_code=422, detail=f"Classifier threshold out of range: {classifier}")
        result[str(classifier)] = score
    return result
