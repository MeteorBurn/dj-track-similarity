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
from .metadata_payload import metadata_from_json


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
    model_id: str
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


def build_classifier_calibration_report(
    db: LibraryDatabase,
    classifier_key: str,
    *,
    classifier_info: Mapping[str, object] | None = None,
    min_feedback: int = DEFAULT_MIN_FEEDBACK_FOR_CLASSIFIER_CALIBRATION,
) -> dict[str, object]:
    key = _clean_classifier_key(classifier_key)
    manifest = _manifest_for_classifier(key, classifier_info)
    total_tracks = _count_tracks(db)
    score_rows = _load_classifier_score_rows(db, key)
    scores = [row.score for row in score_rows]
    feedback = _classifier_feedback_summary(db, key)
    freshness = _score_freshness(manifest, score_rows)
    status = _calibration_report_status(
        manifest,
        score_rows,
        feedback["candidate_feedback_count"],
        min_feedback,
        stale_scores=freshness["stale_scores"],
    )
    warnings = [*manifest.warnings]
    if manifest.status == "legacy":
        warnings.append("Legacy promoted classifier: re-promote from Rhythm Lab to write production metadata.")
    if not manifest.has_calibrated_probability:
        warnings.append("Stored classifier scores are model output probabilities, not calibrated probabilities.")
    if freshness["stale_scores"]:
        warnings.append("Stored classifier scores were produced by a different model identity and are stale until this classifier is rescored.")
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
            "model_ids": _count_values(row.model_id for row in score_rows),
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
            "calibrated_probability_available": manifest.has_calibrated_probability and freshness["stale_scores"] == 0 and bool(score_rows),
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

    rows = _load_classifier_score_rows(db, key)
    if not rows:
        return {
            "classifier_key": key,
            "mode": clean_mode,
            "random_seed": clean_seed,
            "limit": clean_limit,
            "status": "insufficient_data",
            "manifest": manifest.to_api_dict(),
            "suggestions": [],
            "warnings": [*warnings, "No stored classifier scores are available for label suggestions."],
        }
    ordered_rows = _ordered_suggestion_rows(rows, classifier_key=key, mode=clean_mode, random_seed=clean_seed)
    if clean_mode == "hard_negative" and not any(row.negative_feedback_count for row in rows):
        warnings.append("No negative feedback rows are available; hard_negative mode falls back to high-score unlabeled tracks.")
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


def _count_tracks(db: LibraryDatabase) -> int:
    with db.connect() as connection:
        return int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])


def _load_classifier_score_rows(db: LibraryDatabase, classifier_key: str) -> list[ClassifierScoreRow]:
    with db.connect() as connection:
        rows = connection.execute(
            """
            WITH candidate_feedback AS (
                SELECT
                    candidate_track_id AS track_id,
                    COUNT(*) AS feedback_count,
                    SUM(CASE WHEN rating >= 2 THEN 1 ELSE 0 END) AS positive_feedback_count,
                    SUM(CASE WHEN rating <= 1 THEN 1 ELSE 0 END) AS negative_feedback_count,
                    AVG(rating) AS average_rating
                FROM track_pair_feedback
                GROUP BY candidate_track_id
            )
            SELECT
                t.id, t.path, t.artist, t.title, t.album, t.bpm, t.musical_key, t.energy,
                EXISTS(SELECT 1 FROM track_likes tl WHERE tl.track_id = t.id) AS liked,
                s.score, s.label, s.confidence, s.probabilities_json, s.feature_set, s.model_id, s.analyzed_at,
                COALESCE(cf.feedback_count, 0) AS feedback_count,
                COALESCE(cf.positive_feedback_count, 0) AS positive_feedback_count,
                COALESCE(cf.negative_feedback_count, 0) AS negative_feedback_count,
                cf.average_rating AS average_rating
            FROM track_classifier_scores s
            JOIN tracks t ON t.id = s.track_id
            LEFT JOIN candidate_feedback cf ON cf.track_id = t.id
            WHERE s.classifier = ?
            ORDER BY t.id
            """,
            (classifier_key,),
        ).fetchall()
    return [_score_row_from_sql(row) for row in rows]


def _score_row_from_sql(row: object) -> ClassifierScoreRow:
    probabilities = metadata_from_json(row["probabilities_json"])
    return ClassifierScoreRow(
        track_id=int(row["id"]),
        path=str(row["path"]),
        artist=row["artist"],
        title=row["title"],
        album=row["album"],
        bpm=_optional_float(row["bpm"]),
        musical_key=row["musical_key"],
        energy=_optional_float(row["energy"]),
        score=_finite_score(row["score"]),
        label=str(row["label"]),
        confidence=_finite_score(row["confidence"]),
        probabilities=probabilities if isinstance(probabilities, dict) else {},
        feature_set=str(row["feature_set"]),
        model_id=str(row["model_id"]),
        analyzed_at=str(row["analyzed_at"]),
        liked=bool(row["liked"]),
        feedback_count=int(row["feedback_count"]),
        positive_feedback_count=int(row["positive_feedback_count"]),
        negative_feedback_count=int(row["negative_feedback_count"]),
        average_rating=_optional_float(row["average_rating"]),
    )


def _classifier_feedback_summary(db: LibraryDatabase, classifier_key: str) -> dict[str, object]:
    with db.connect() as connection:
        rating_rows = connection.execute(
            """
            SELECT f.rating, COUNT(*) AS count
            FROM track_pair_feedback f
            JOIN track_classifier_scores s ON s.track_id = f.candidate_track_id AND s.classifier = ?
            GROUP BY f.rating
            ORDER BY f.rating
            """,
            (classifier_key,),
        ).fetchall()
        source_rows = connection.execute(
            """
            SELECT f.source, COUNT(*) AS count
            FROM track_pair_feedback f
            JOIN track_classifier_scores s ON s.track_id = f.candidate_track_id AND s.classifier = ?
            GROUP BY f.source
            ORDER BY f.source
            """,
            (classifier_key,),
        ).fetchall()
        liked_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM track_likes tl
                JOIN track_classifier_scores s ON s.track_id = tl.track_id AND s.classifier = ?
                """,
                (classifier_key,),
            ).fetchone()[0]
        )
        transition_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM transition_feedback tf
                WHERE EXISTS (
                    SELECT 1 FROM track_classifier_scores s
                    WHERE s.classifier = ? AND s.track_id IN (tf.outgoing_track_id, tf.incoming_track_id)
                )
                """,
                (classifier_key,),
            ).fetchone()[0]
        )
    rating_counts = {str(int(row["rating"])): int(row["count"]) for row in rating_rows}
    source_counts = {str(row["source"]): int(row["count"]) for row in source_rows}
    return {
        "candidate_feedback_count": sum(rating_counts.values()),
        "candidate_feedback_rating_counts": rating_counts,
        "candidate_feedback_source_counts": source_counts,
        "liked_scored_tracks": liked_count,
        "transition_feedback_rows_touching_scored_tracks": transition_count,
        "label_source_note": "No main-app classifier label table exists; Rhythm Lab labels stay in the separate lab database.",
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
        return "Stored classifier scores are stale for the current manifest model identity; rescore this classifier before treating them as fresh calibrated evidence."
    if feedback_count < max(1, int(min_feedback)):
        return "Insufficient app feedback for calibration diagnostics; use this as a coverage report only."
    return "Enough app feedback exists for diagnostics, but this report still does not prove benchmark quality."


def _score_freshness(
    manifest: ClassifierManifestSummary,
    score_rows: Sequence[ClassifierScoreRow],
) -> dict[str, object]:
    expected_model_id = manifest.model_id
    if not expected_model_id:
        return {
            "expected_model_id": None,
            "fresh_scores": len(score_rows),
            "stale_scores": 0,
            "unknown_freshness_scores": len(score_rows),
            "stale_model_ids": {},
        }
    stale_model_ids = _count_values(row.model_id for row in score_rows if row.model_id != expected_model_id)
    stale_scores = sum(stale_model_ids.values())
    return {
        "expected_model_id": expected_model_id,
        "fresh_scores": len(score_rows) - stale_scores,
        "stale_scores": stale_scores,
        "unknown_freshness_scores": 0,
        "stale_model_ids": stale_model_ids,
    }


def _ordered_suggestion_rows(
    rows: Sequence[ClassifierScoreRow],
    *,
    classifier_key: str,
    mode: str,
    random_seed: int,
) -> list[ClassifierScoreRow]:
    if mode == "diversity":
        return _diverse_suggestion_order(rows, classifier_key=classifier_key, mode=mode, random_seed=random_seed)
    return sorted(rows, key=lambda row: _suggestion_sort_key(row, classifier_key=classifier_key, mode=mode, random_seed=random_seed))


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
            return (-row.negative_feedback_count, -row.score, row.uncertainty, tie_breaker, row.track_id)
        return (1, 0 if row.is_unlabeled else 1, -row.score, row.uncertainty, tie_breaker, row.track_id)
    if mode == "disagreement":
        disagreement = _disagreement_score(row)
        return (-disagreement, 0 if row.is_unlabeled else 1, row.uncertainty, tie_breaker, row.track_id)
    if mode == "high_impact_unlabeled":
        impact = 1.0 - min(1.0, row.uncertainty * 2.0)
        return (0 if row.is_unlabeled else 1, -impact, -row.confidence, tie_breaker, row.track_id)
    return (0 if row.is_unlabeled else 1, row.uncertainty, -row.confidence, tie_breaker, row.track_id)


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
        bucket_rows.sort(key=lambda row: _suggestion_sort_key(row, classifier_key=classifier_key, mode="uncertainty", random_seed=random_seed))
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


def _suggestion_payload(row: ClassifierScoreRow, *, rank: int, mode: str) -> dict[str, object]:
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
    return "Existing feedback is sparse; the score remains useful for another review pass."


def _disagreement_score(row: ClassifierScoreRow) -> float:
    if row.negative_feedback_count:
        return row.score * row.negative_feedback_count
    if row.positive_feedback_count:
        return (1.0 - row.score) * row.positive_feedback_count
    return 1.0 - min(1.0, row.uncertainty * 2.0)


def _stable_tie_breaker(classifier_key: str, mode: str, track_id: int, random_seed: int) -> int:
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


def _clean_classifier_key(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("Classifier key is required")
    return text
