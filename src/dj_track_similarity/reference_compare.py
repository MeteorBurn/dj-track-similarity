from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .database import LibraryDatabase
from .models import SearchResult, Track
from .search import SimilaritySearch
from .sonara_similarity import SonaraSimilaritySearch

ReferenceCompareModel = Literal["clap", "mert", "muq", "maest", "sonara"]
ReferenceCompareVerdict = Literal["mood", "palette", "instruments", "groove", "genre", "transition", "miss"]

DEFAULT_REFERENCE_COMPARE_MODELS: tuple[ReferenceCompareModel, ...] = ("clap", "mert", "muq", "maest", "sonara")


@dataclass(frozen=True, slots=True)
class ReferenceCompareQuery:
    seed_track_id: int
    models: tuple[ReferenceCompareModel, ...]
    limit: int


@dataclass(frozen=True, slots=True)
class ReferenceCompareGroup:
    model: ReferenceCompareModel
    available: bool
    reason: str | None
    results: tuple[SearchResult, ...]


@dataclass(frozen=True, slots=True)
class ReferenceCompareResponse:
    seed_track_id: int
    groups: tuple[ReferenceCompareGroup, ...]


@dataclass(frozen=True, slots=True)
class ReferenceCompareVerdictResult:
    id: int
    seed_track_id: int
    candidate_track_id: int
    model: ReferenceCompareModel
    verdict: ReferenceCompareVerdict
    source: str
    rating: int
    notes: str | None


def build_reference_compare(db: LibraryDatabase, query: ReferenceCompareQuery) -> ReferenceCompareResponse:
    _ = _require_track(db, query.seed_track_id)
    return ReferenceCompareResponse(
        seed_track_id=query.seed_track_id,
        groups=tuple(_reference_compare_group(db, query, model) for model in query.models),
    )


def record_reference_compare_verdict(
    db: LibraryDatabase,
    *,
    seed_track_id: int,
    candidate_track_id: int,
    model: ReferenceCompareModel,
    verdict: ReferenceCompareVerdict,
    notes: str | None,
) -> ReferenceCompareVerdictResult:
    _ = _require_track(db, seed_track_id)
    _ = _require_track(db, candidate_track_id)
    source = _feedback_source(model)
    rating = _verdict_rating(verdict)
    feedback_id = db.upsert_track_pair_feedback(
        seed_track_id,
        candidate_track_id,
        rating,
        reason_tags=(verdict,),
        notes=notes,
        source=source,
    )
    return ReferenceCompareVerdictResult(
        id=feedback_id,
        seed_track_id=seed_track_id,
        candidate_track_id=candidate_track_id,
        model=model,
        verdict=verdict,
        source=source,
        rating=rating,
        notes=notes,
    )


def _reference_compare_group(db: LibraryDatabase, query: ReferenceCompareQuery, model: ReferenceCompareModel) -> ReferenceCompareGroup:
    match model:
        case "clap" | "mert" | "muq" | "maest":
            return _embedding_group(db, query, model)
        case "sonara":
            return _sonara_group(db, query)


def _embedding_group(db: LibraryDatabase, query: ReferenceCompareQuery, model: ReferenceCompareModel) -> ReferenceCompareGroup:
    seed_track = _require_track(db, query.seed_track_id)
    if model not in (seed_track.analyses or []):
        return ReferenceCompareGroup(model=model, available=False, reason=f"Seed track is missing {model.upper()} embedding", results=())
    results = SimilaritySearch(db, embedding_key=model).search([query.seed_track_id], limit=query.limit)
    return ReferenceCompareGroup(model=model, available=True, reason=None, results=tuple(results))


def _sonara_group(db: LibraryDatabase, query: ReferenceCompareQuery) -> ReferenceCompareGroup:
    tracks, _features = db.load_sonara_feature_rows()
    if query.seed_track_id not in {track.id for track in tracks}:
        return ReferenceCompareGroup(model="sonara", available=False, reason="Seed track is missing SONARA features", results=())
    results = SonaraSimilaritySearch(db).search([query.seed_track_id], mode="balanced", min_similarity=0.0, limit=query.limit)
    return ReferenceCompareGroup(model="sonara", available=True, reason=None, results=tuple(results))


def _require_track(db: LibraryDatabase, track_id: int) -> Track:
    try:
        return db.get_track(track_id)
    except KeyError as error:
        raise ValueError(f"Unknown track: {track_id}") from error


def _feedback_source(model: ReferenceCompareModel) -> str:
    return f"reference_compare:{model}"


def _verdict_rating(verdict: ReferenceCompareVerdict) -> int:
    match verdict:
        case "miss":
            return 0
        case "mood" | "palette" | "instruments" | "groove" | "genre" | "transition":
            return 2
