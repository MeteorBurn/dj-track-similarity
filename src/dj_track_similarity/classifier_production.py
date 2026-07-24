from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import math
from typing import Mapping, Sequence

from .classifier_manifest import (
    ClassifierManifestSummary,
    classifier_manifest_from_info,
    load_classifier_manifest_summary,
)
from .classifier_scoring import default_classifier_model_path
from .database import LibraryDatabase
from .library_models import ClassifierScoreDetail, TrackSummary


LABEL_SUGGESTION_MODES = (
    "uncertainty",
    "hard_negative",
    "diversity",
    "disagreement",
    "high_impact_unlabeled",
)
DEFAULT_SUGGESTION_LIMIT = 25
DEFAULT_MIN_FEEDBACK_FOR_CLASSIFIER_CALIBRATION = 30


@dataclass(frozen=True)
class ClassifierScoreRow:
    track_id: int
    path: str
    artist: str | None
    title: str | None
    album: str | None
    bpm: float | None
    musical_key: str | None
    energy: float | None
    score: float
    label: str
    confidence: float
    probabilities: dict[str, object]
    feature_set: str
    feature_manifest_hash: str
    required_outputs_hash: str
    model_id: str
    uses_sonara: bool
    sonara_release_hash: str | None
    positive_label: str
    analyzed_at: str
    liked: bool
    feedback_count: int
    positive_feedback_count: int
    negative_feedback_count: int
    average_rating: float | None

    @property
    def uncertainty(self) -> float:
        return abs(self.score - 0.5)

    @property
    def is_unlabeled(self) -> bool:
        return self.feedback_count == 0


@dataclass(frozen=True)
class _FeedbackAggregate:
    feedback_count: int
    positive_feedback_count: int
    negative_feedback_count: int
    average_rating: float | None


def build_classifier_calibration_report(
    db: LibraryDatabase,
    classifier_key: str,
    *,
    classifier_info: Mapping[str, object] | None = None,
    min_feedback: int = DEFAULT_MIN_FEEDBACK_FOR_CLASSIFIER_CALIBRATION,
) -> dict[str, object]:
    key = _clean_classifier_key(classifier_key)
    manifest = _manifest_for_classifier(key, classifier_info)
    track_summaries = db.list_track_summaries()
    liked_track_ids = frozenset(db.list_liked_track_ids())
    pair_feedback = db.get_pair_feedback_map()
    total_tracks = len(track_summaries)
    score_rows = _load_classifier_score_rows(
        db,
        key,
        track_summaries=track_summaries,
        liked_track_ids=liked_track_ids,
        pair_feedback=pair_feedback,
    )
    scores = [row.score for row in score_rows]
    feedback = _classifier_feedback_summary(
        db,
        score_rows,
        pair_feedback=pair_feedback,
        liked_track_ids=liked_track_ids,
    )
    freshness = _score_freshness(manifest, score_rows)
    status = _calibration_report_status(
        manifest,
        score_rows,
        feedback["candidate_feedback_count"],
        min_feedback,
        stale_scores=freshness["stale_scores"],
    )
    warnings = [*manifest.warnings]
    if not manifest.has_calibrated_probability:
        warnings.append(
            "Stored classifier scores are model output probabilities, not calibrated probabilities."
        )
    if freshness["stale_scores"]:
        warnings.append(
            "Stored classifier scores were produced by a different full "
            "classifier identity and are stale until this classifier is "
            "rescored."
        )
    if feedback["candidate_feedback_count"] < min_feedback:
        warnings.append(
            f"Only {feedback['candidate_feedback_count']} candidate feedback rows are available; "
            f"{min_feedback} are requested before calibration diagnostics are considered usable."
        )
    return {
        "classifier_key": key,
        "status": status,
        "manifest": manifest.to_api_dict(),
        "coverage": {
            "tracks_total": total_tracks,
            "tracks_scored": len(score_rows),
            **freshness,
            "coverage_ratio": _ratio(len(score_rows), total_tracks),
            "feature_sets": _count_values(row.feature_set for row in score_rows),
            "feature_manifest_hashes": _count_values(
                row.feature_manifest_hash for row in score_rows
            ),
            "required_outputs_hashes": _count_values(
                row.required_outputs_hash for row in score_rows
            ),
            "model_ids": _count_values(row.model_id for row in score_rows),
            "sonara_release_hashes": _count_values(
                row.sonara_release_hash
                for row in score_rows
                if row.sonara_release_hash is not None
            ),
        },
        "score_distribution": {
            "count": len(scores),
            "quantiles": _quantiles(scores),
            "buckets": _score_buckets(scores),
            "labels": _count_values(row.label for row in score_rows),
            "probability_keys": _probability_key_counts(score_rows),
        },
        "available_labels_feedback": feedback,
        "status_gate": {
            "manifest_scoring_compatible": manifest.is_scoring_compatible,
            "calibrated_probability_available": manifest.has_calibrated_probability
            and freshness["stale_scores"] == 0
            and bool(score_rows),
            "min_feedback_requested": max(1, int(min_feedback)),
            "feedback_rows_available": feedback["candidate_feedback_count"],
            "fresh_scores": freshness["fresh_scores"],
            "stale_scores": freshness["stale_scores"],
            "can_claim_benchmark_quality": False,
            "decision": _status_gate_decision(
                manifest,
                score_rows,
                feedback["candidate_feedback_count"],
                min_feedback,
                stale_scores=freshness["stale_scores"],
            ),
        },
        "warnings": warnings,
        "limitations": [
            "This report uses stored SQLite classifier scores and available app feedback only.",
            "It does not decode audio, retrain a model, or benchmark the classifier against an external dataset.",
            "Pair feedback was collected for search/audit workflows and is not the same as Rhythm Lab training labels.",
        ],
    }


def suggest_classifier_labels(
    db: LibraryDatabase,
    classifier_key: str,
    *,
    mode: str = "uncertainty",
    limit: int = DEFAULT_SUGGESTION_LIMIT,
    random_seed: int = 123,
    classifier_info: Mapping[str, object] | None = None,
) -> dict[str, object]:
    key = _clean_classifier_key(classifier_key)
    clean_mode = normalize_label_suggestion_mode(mode)
    clean_limit = max(1, int(limit))
    clean_seed = int(random_seed)
    manifest = _manifest_for_classifier(key, classifier_info)
    warnings = list(manifest.warnings)
    if not manifest.is_scoring_compatible:
        return {
            "classifier_key": key,
            "mode": clean_mode,
            "random_seed": clean_seed,
            "limit": clean_limit,
            "status": "invalid_manifest",
            "manifest": manifest.to_api_dict(),
            "suggestions": [],
            "warnings": warnings,
        }

    track_summaries = db.list_track_summaries()
    rows = _load_classifier_score_rows(
        db,
        key,
        track_summaries=track_summaries,
        liked_track_ids=frozenset(db.list_liked_track_ids()),
        pair_feedback=db.get_pair_feedback_map(),
    )
    fresh_rows = _fresh_score_rows(manifest, rows)
    stale_count = len(rows) - len(fresh_rows)
    if stale_count:
        warnings.append(
            f"{stale_count} stored classifier score rows do not match the "
            "current full classifier identity and were excluded."
        )
    if not fresh_rows:
        return {
            "classifier_key": key,
            "mode": clean_mode,
            "random_seed": clean_seed,
            "limit": clean_limit,
            "status": "insufficient_data",
            "manifest": manifest.to_api_dict(),
            "suggestions": [],
            "warnings": [
                *warnings,
                "No current classifier scores are available for label suggestions.",
            ],
        }
    ordered_rows = _ordered_suggestion_rows(
        fresh_rows,
        classifier_key=key,
        mode=clean_mode,
        random_seed=clean_seed,
    )
    if clean_mode == "hard_negative" and not any(
        row.negative_feedback_count for row in fresh_rows
    ):
        warnings.append(
            "No negative feedback rows are available; hard_negative mode falls back to high-score unlabeled tracks."
        )
    return {
        "classifier_key": key,
        "mode": clean_mode,
        "random_seed": clean_seed,
        "limit": clean_limit,
        "status": "ok",
        "manifest": manifest.to_api_dict(),
        "suggestions": [
            _suggestion_payload(row, rank=index + 1, mode=clean_mode)
            for index, row in enumerate(ordered_rows[:clean_limit])
        ],
        "warnings": warnings,
        "limitations": [
            "Suggestions are deterministic rankings over stored classifier scores and feedback rows only.",
            "They are not an active-learning model retraining step and do not write a queue table.",
        ],
    }


def normalize_label_suggestion_mode(mode: str) -> str:
    clean_mode = str(mode or "").strip().lower().replace("-", "_")
    if clean_mode in LABEL_SUGGESTION_MODES:
        return clean_mode
    raise ValueError(f"Unknown classifier label suggestion mode: {mode}")


def _manifest_for_classifier(
    classifier_key: str,
    classifier_info: Mapping[str, object] | None,
) -> ClassifierManifestSummary:
    if classifier_info is not None:
        summary = classifier_manifest_from_info(classifier_info)
        if summary is not None:
            return summary
    return load_classifier_manifest_summary(
        default_classifier_model_path(classifier_key),
        expected_classifier_key=classifier_key,
    )


def _load_classifier_score_rows(
    db: LibraryDatabase,
    classifier_key: str,
    *,
    track_summaries: Sequence[TrackSummary],
    liked_track_ids: frozenset[int],
    pair_feedback: Mapping[
        tuple[int, int, str],
        Mapping[str, object],
    ],
) -> list[ClassifierScoreRow]:
    feedback_by_track = _candidate_feedback_aggregates(pair_feedback)
    score_rows: list[ClassifierScoreRow] = []
    for track in track_summaries:
        if not any(
            score.classifier_key == classifier_key for score in track.classifier_scores
        ):
            continue
        detail = db.get_track_detail(track.track_id)
        score = _classifier_score_detail(
            detail.classifier_scores_detail, classifier_key
        )
        if score is None:
            continue
        feedback = feedback_by_track.get(
            track.track_id,
            _FeedbackAggregate(0, 0, 0, None),
        )
        energy = (
            detail.sonara_core.energy_score if detail.sonara_core is not None else None
        )
        score_rows.append(
            ClassifierScoreRow(
                track_id=track.track_id,
                path=track.file_path,
                artist=track.artist,
                title=track.title,
                album=track.album,
                bpm=_optional_float(track.tag_bpm),
                musical_key=track.tag_key,
                energy=_optional_float(energy),
                score=_finite_score(score.score),
                label=score.predicted_class,
                confidence=_finite_score(score.confidence),
                probabilities={
                    str(label): _finite_score(probability)
                    for label, probability in score.probabilities.items()
                },
                feature_set=score.feature_set,
                feature_manifest_hash=score.feature_manifest_hash,
                required_outputs_hash=score.required_outputs_hash,
                model_id=score.model_id,
                uses_sonara=score.uses_sonara,
                sonara_release_hash=score.sonara_release_hash,
                positive_label=score.positive_label,
                analyzed_at=score.analyzed_at,
                liked=track.track_id in liked_track_ids,
                feedback_count=feedback.feedback_count,
                positive_feedback_count=feedback.positive_feedback_count,
                negative_feedback_count=feedback.negative_feedback_count,
                average_rating=feedback.average_rating,
            )
        )
    return score_rows


def _classifier_score_detail(
    scores: Sequence[ClassifierScoreDetail],
    classifier_key: str,
) -> ClassifierScoreDetail | None:
    matches = [score for score in scores if score.classifier_key == classifier_key]
    if len(matches) > 1:
        raise ValueError(
            f"Multiple current scores exist for classifier {classifier_key!r}"
        )
    return matches[0] if matches else None


def _candidate_feedback_aggregates(
    pair_feedback: Mapping[
        tuple[int, int, str],
        Mapping[str, object],
    ],
) -> dict[int, _FeedbackAggregate]:
    ratings_by_track: dict[int, list[int]] = {}
    for key, feedback in pair_feedback.items():
        candidate_track_id = int(feedback.get("candidate_track_id", key[1]))
        ratings_by_track.setdefault(candidate_track_id, []).append(
            int(feedback["rating"])
        )
    return {
        track_id: _FeedbackAggregate(
            feedback_count=len(ratings),
            positive_feedback_count=sum(1 for rating in ratings if rating >= 2),
            negative_feedback_count=sum(1 for rating in ratings if rating <= 1),
            average_rating=sum(ratings) / len(ratings) if ratings else None,
        )
        for track_id, ratings in ratings_by_track.items()
    }


def _classifier_feedback_summary(
    db: LibraryDatabase,
    score_rows: Sequence[ClassifierScoreRow],
    *,
    pair_feedback: Mapping[
        tuple[int, int, str],
        Mapping[str, object],
    ],
    liked_track_ids: frozenset[int],
) -> dict[str, object]:
    scored_track_ids = {row.track_id for row in score_rows}
    rating_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    for key, feedback in pair_feedback.items():
        candidate_track_id = int(feedback.get("candidate_track_id", key[1]))
        if candidate_track_id not in scored_track_ids:
            continue
        rating = str(int(feedback["rating"]))
        source = str(feedback.get("source", key[2]))
        rating_counts[rating] = rating_counts.get(rating, 0) + 1
        source_counts[source] = source_counts.get(source, 0) + 1
    evaluation_counts = db.count_evaluation_rows()
    transition_count = int(evaluation_counts.get("transition_feedback", 0))
    return {
        "candidate_feedback_count": sum(rating_counts.values()),
        "candidate_feedback_rating_counts": dict(sorted(rating_counts.items())),
        "candidate_feedback_source_counts": dict(sorted(source_counts.items())),
        "liked_scored_tracks": len(scored_track_ids & liked_track_ids),
        "transition_feedback_rows_touching_scored_tracks": None,
        "transition_feedback_rows_total": transition_count,
        "transition_feedback_scope_note": (
            "The v7 repository exposes the total transition-feedback count, "
            "not a classifier-scoped transition-feedback reader."
        ),
        "label_source_note": (
            "No main-app classifier label repository exists; Rhythm Lab "
            "labels stay in the separate lab database."
        ),
    }


def _calibration_report_status(
    manifest: ClassifierManifestSummary,
    score_rows: Sequence[ClassifierScoreRow],
    feedback_count: int,
    min_feedback: int,
    *,
    stale_scores: int = 0,
) -> str:
    if not manifest.is_scoring_compatible:
        return "invalid_manifest"
    if score_rows and stale_scores > 0:
        return "stale"
    if not score_rows or feedback_count < max(1, int(min_feedback)):
        return "insufficient_data"
    return "diagnostic_only"


def _status_gate_decision(
    manifest: ClassifierManifestSummary,
    score_rows: Sequence[ClassifierScoreRow],
    feedback_count: int,
    min_feedback: int,
    *,
    stale_scores: int = 0,
) -> str:
    if not manifest.is_scoring_compatible:
        return "Classifier scoring is blocked until the promoted manifest is fixed."
    if not score_rows:
        return "No stored classifier scores are available yet."
    if stale_scores:
        return (
            "Stored classifier scores are stale for the current full "
            "manifest identity; rescore this classifier before treating "
            "them as fresh calibrated evidence."
        )
    if feedback_count < max(1, int(min_feedback)):
        return "Insufficient app feedback for calibration diagnostics; use this as a coverage report only."
    return "Enough app feedback exists for diagnostics, but this report still does not prove benchmark quality."


def _score_freshness(
    manifest: ClassifierManifestSummary,
    score_rows: Sequence[ClassifierScoreRow],
) -> dict[str, object]:
    expected_identity = _manifest_score_identity(manifest)
    if expected_identity is None:
        return {
            "expected_model_id": manifest.model_id,
            "expected_identity": None,
            "fresh_scores": 0,
            "stale_scores": 0,
            "unknown_freshness_scores": len(score_rows),
            "stale_model_ids": {},
            "stale_identity_fields": {},
        }
    stale_rows: list[ClassifierScoreRow] = []
    mismatch_counts: dict[str, int] = {}
    for row in score_rows:
        row_identity = _score_row_identity(row)
        mismatched_fields = [
            field_name
            for field_name, expected_value in expected_identity.items()
            if row_identity[field_name] != expected_value
        ]
        if not mismatched_fields:
            continue
        stale_rows.append(row)
        for field_name in mismatched_fields:
            mismatch_counts[field_name] = mismatch_counts.get(field_name, 0) + 1
    stale_model_ids = _count_values(
        row.model_id
        for row in stale_rows
        if row.model_id != expected_identity["model_id"]
    )
    stale_scores = len(stale_rows)
    return {
        "expected_model_id": expected_identity["model_id"],
        "expected_identity": expected_identity,
        "fresh_scores": len(score_rows) - stale_scores,
        "stale_scores": stale_scores,
        "unknown_freshness_scores": 0,
        "stale_model_ids": stale_model_ids,
        "stale_identity_fields": dict(sorted(mismatch_counts.items())),
    }


def _manifest_score_identity(
    manifest: ClassifierManifestSummary,
) -> dict[str, object] | None:
    model_id = _optional_text(manifest.model_id)
    feature_set = _optional_text(manifest.feature_set)
    feature_manifest_hash = _optional_text(manifest.feature_manifest_hash)
    required_outputs_hash = _optional_text(manifest.required_outputs_hash)
    positive_label = _optional_text(manifest.positive_label)
    uses_sonara = manifest.uses_sonara
    sonara_release_hash = _optional_text(manifest.sonara_release_hash)
    if not all(
        (
            model_id,
            feature_set,
            feature_manifest_hash,
            required_outputs_hash,
            positive_label,
        )
    ):
        return None
    if uses_sonara and sonara_release_hash is None:
        return None
    return {
        "model_id": model_id,
        "feature_set": feature_set,
        "feature_manifest_hash": feature_manifest_hash,
        "required_outputs_hash": required_outputs_hash,
        "uses_sonara": uses_sonara,
        "sonara_release_hash": (sonara_release_hash if uses_sonara else None),
        "positive_label": positive_label,
    }


def _score_row_identity(
    row: ClassifierScoreRow,
) -> dict[str, object]:
    return {
        "model_id": row.model_id,
        "feature_set": row.feature_set,
        "feature_manifest_hash": row.feature_manifest_hash,
        "required_outputs_hash": row.required_outputs_hash,
        "uses_sonara": row.uses_sonara,
        "sonara_release_hash": (row.sonara_release_hash if row.uses_sonara else None),
        "positive_label": row.positive_label,
    }


def _fresh_score_rows(
    manifest: ClassifierManifestSummary,
    rows: Sequence[ClassifierScoreRow],
) -> list[ClassifierScoreRow]:
    expected_identity = _manifest_score_identity(manifest)
    if expected_identity is None:
        return []
    return [row for row in rows if _score_row_identity(row) == expected_identity]


def _ordered_suggestion_rows(
    rows: Sequence[ClassifierScoreRow],
    *,
    classifier_key: str,
    mode: str,
    random_seed: int,
) -> list[ClassifierScoreRow]:
    if mode == "diversity":
        return _diverse_suggestion_order(
            rows, classifier_key=classifier_key, mode=mode, random_seed=random_seed
        )
    return sorted(
        rows,
        key=lambda row: _suggestion_sort_key(
            row, classifier_key=classifier_key, mode=mode, random_seed=random_seed
        ),
    )


def _suggestion_sort_key(
    row: ClassifierScoreRow,
    *,
    classifier_key: str,
    mode: str,
    random_seed: int,
) -> tuple[object, ...]:
    tie_breaker = _stable_tie_breaker(classifier_key, mode, row.track_id, random_seed)
    if mode == "hard_negative":
        if row.negative_feedback_count:
            return (
                -row.negative_feedback_count,
                -row.score,
                row.uncertainty,
                tie_breaker,
                row.track_id,
            )
        return (
            1,
            0 if row.is_unlabeled else 1,
            -row.score,
            row.uncertainty,
            tie_breaker,
            row.track_id,
        )
    if mode == "disagreement":
        disagreement = _disagreement_score(row)
        return (
            -disagreement,
            0 if row.is_unlabeled else 1,
            row.uncertainty,
            tie_breaker,
            row.track_id,
        )
    if mode == "high_impact_unlabeled":
        impact = 1.0 - min(1.0, row.uncertainty * 2.0)
        return (
            0 if row.is_unlabeled else 1,
            -impact,
            -row.confidence,
            tie_breaker,
            row.track_id,
        )
    return (
        0 if row.is_unlabeled else 1,
        row.uncertainty,
        -row.confidence,
        tie_breaker,
        row.track_id,
    )


def _diverse_suggestion_order(
    rows: Sequence[ClassifierScoreRow],
    *,
    classifier_key: str,
    mode: str,
    random_seed: int,
) -> list[ClassifierScoreRow]:
    buckets: dict[int, list[ClassifierScoreRow]] = {}
    for row in rows:
        bucket = min(4, max(0, int(row.score * 5)))
        buckets.setdefault(bucket, []).append(row)
    for bucket_rows in buckets.values():
        bucket_rows.sort(
            key=lambda row: _suggestion_sort_key(
                row,
                classifier_key=classifier_key,
                mode="uncertainty",
                random_seed=random_seed,
            )
        )
    bucket_order = sorted(buckets, key=lambda bucket: (abs(bucket - 2), bucket))
    if bucket_order:
        offset = random_seed % len(bucket_order)
        bucket_order = [*bucket_order[offset:], *bucket_order[:offset]]
    ordered: list[ClassifierScoreRow] = []
    while any(buckets.values()):
        for bucket in bucket_order:
            bucket_rows = buckets.get(bucket) or []
            if bucket_rows:
                ordered.append(bucket_rows.pop(0))
    return ordered


def _suggestion_payload(
    row: ClassifierScoreRow, *, rank: int, mode: str
) -> dict[str, object]:
    return {
        "rank": rank,
        "track": {
            "id": row.track_id,
            "path": row.path,
            "artist": row.artist,
            "title": row.title,
            "album": row.album,
            "bpm": row.bpm,
            "musical_key": row.musical_key,
            "energy": row.energy,
        },
        "score": row.score,
        "label": row.label,
        "confidence": row.confidence,
        "uncertainty": row.uncertainty,
        "feedback_count": row.feedback_count,
        "positive_feedback_count": row.positive_feedback_count,
        "negative_feedback_count": row.negative_feedback_count,
        "average_rating": row.average_rating,
        "liked": row.liked,
        "label_status": "unlabeled" if row.is_unlabeled else "feedback_available",
        "reason": _suggestion_reason(row, mode),
    }


def _suggestion_reason(row: ClassifierScoreRow, mode: str) -> str:
    if mode == "hard_negative" and row.negative_feedback_count:
        return "High classifier score conflicts with negative app feedback."
    if mode == "disagreement" and row.feedback_count:
        return "Stored app feedback and classifier score disagree enough to review."
    if mode == "diversity":
        return "Selected from a score bucket to keep the next labels spread across classifier coverage."
    if row.is_unlabeled:
        return "No app feedback is stored for this scored track, and the score is informative for review."
    return (
        "Existing feedback is sparse; the score remains useful for another review pass."
    )


def _disagreement_score(row: ClassifierScoreRow) -> float:
    if row.negative_feedback_count:
        return row.score * row.negative_feedback_count
    if row.positive_feedback_count:
        return (1.0 - row.score) * row.positive_feedback_count
    return 1.0 - min(1.0, row.uncertainty * 2.0)


def _stable_tie_breaker(
    classifier_key: str, mode: str, track_id: int, random_seed: int
) -> int:
    text = f"{classifier_key}:{mode}:{random_seed}:{track_id}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(text, digest_size=8).digest(), "big")


def _quantiles(values: Sequence[float]) -> dict[str, float | None]:
    clean_values = sorted(value for value in values if math.isfinite(value))
    if not clean_values:
        return {key: None for key in ("min", "p10", "p25", "p50", "p75", "p90", "max")}
    return {
        "min": clean_values[0],
        "p10": _quantile(clean_values, 0.10),
        "p25": _quantile(clean_values, 0.25),
        "p50": _quantile(clean_values, 0.50),
        "p75": _quantile(clean_values, 0.75),
        "p90": _quantile(clean_values, 0.90),
        "max": clean_values[-1],
    }


def _quantile(values: Sequence[float], percentile: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * percentile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1.0 - weight) + values[upper] * weight


def _score_buckets(values: Sequence[float]) -> list[dict[str, object]]:
    buckets = [0, 0, 0, 0, 0]
    for value in values:
        if math.isfinite(value):
            buckets[min(4, max(0, int(value * 5)))] += 1
    return [
        {"range": f"{index / 5:.1f}-{(index + 1) / 5:.1f}", "count": count}
        for index, count in enumerate(buckets)
    ]


def _probability_key_counts(rows: Sequence[ClassifierScoreRow]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for key in row.probabilities:
            counts[str(key)] = counts.get(str(key), 0) + 1
    return dict(sorted(counts.items()))


def _count_values(values: Iterable[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _finite_score(value: object) -> float:
    score = float(value)
    if not math.isfinite(score):
        raise ValueError("Classifier score rows must contain finite scores")
    return score


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_classifier_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Classifier key is required")
    return text
