from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dj_track_similarity.classifier_production import (
    build_classifier_calibration_report,
    suggest_classifier_labels,
)
from dj_track_similarity.classifier_scoring import promoted_classifiers
from dj_track_similarity.library_models import (
    AnalysisCoverage,
    ClassifierScoreDetail,
    ClassifierScoreSummary,
    FileTechnical,
    TrackDetail,
    TrackSummary,
)


_NOW = "2026-07-24T12:00:00.000000Z"
_ARTIFACT_BYTES = b"fixture"
_ARTIFACT_HASH = f"sha256:{hashlib.sha256(_ARTIFACT_BYTES).hexdigest()}"


def _manifest_payload(classifier_key: str) -> dict[str, object]:
    feature_names = ("mert:0",)
    payload: dict[str, object] = {
        "classifier_key": classifier_key,
        "profile_name": classifier_key.replace("_", " ").title(),
        "profile_description": "Human-readable classifier description.",
        "artifact_hash": _ARTIFACT_HASH,
        "feature_set": "mert-features",
        "feature_names": list(feature_names),
        "feature_count": len(feature_names),
        "label_order": ["negative", "positive"],
        "negative_label": "negative",
        "positive_label": "positive",
        "trained_label_counts": {"negative": 12, "positive": 14},
        "production": {
            "score_semantics": "positive_label_probability",
            "calibration": {"status": "uncalibrated"},
        },
    }
    return payload


def _write_promoted(
    root: Path,
    classifier_key: str,
    *,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    artifact_dir = root / classifier_key.replace("_", "-")
    artifact_dir.mkdir(parents=True)
    model_path = artifact_dir / "model.joblib"
    metadata_path = artifact_dir / "model.json"
    model_path.write_bytes(_ARTIFACT_BYTES)
    metadata_path.write_text(
        json.dumps(payload or _manifest_payload(classifier_key)),
        encoding="utf-8",
    )
    return {
        "classifier_key": classifier_key,
        "model_path": str(model_path),
        "metadata_path": str(metadata_path),
    }


def _score_detail(
    classifier_key: str,
    *,
    score: float,
) -> ClassifierScoreDetail:
    probabilities = {
        "negative": 1.0 - score,
        "positive": score,
    }
    predicted = "positive" if score > 0.5 else "negative"
    return ClassifierScoreDetail(
        classifier_key=classifier_key,
        score=score,
        predicted_class=predicted,
        score_bucket=("high" if score >= 0.7 else "medium" if score >= 0.3 else "low"),
        confidence=max(probabilities.values()),
        probabilities=probabilities,
        feature_set="mert-features",
        feature_names=("mert:0",),
        positive_label="positive",
        analyzed_at=_NOW,
    )


def _track(
    track_id: int,
    *scores: ClassifierScoreDetail,
) -> tuple[TrackSummary, TrackDetail]:
    summaries = tuple(
        ClassifierScoreSummary(
            classifier_key=score.classifier_key,
            score=score.score,
            predicted_class=score.predicted_class,
            score_bucket=score.score_bucket,
            confidence=score.confidence,
        )
        for score in scores
    )
    summary = TrackSummary(
        track_id=track_id,
        catalog_uuid="catalog-current",
        track_uuid=f"track-{track_id}",
        file_path=f"C:/music/{track_id}.wav",
        title=f"Track {track_id}",
        artist="Artist",
        album="Album",
        tag_bpm=128.0,
        tag_key="8A",
        audio_duration_seconds=300.0,
        liked=False,
        analysis_coverage=AnalysisCoverage(),
        classifier_scores=summaries,
    )
    detail = TrackDetail(
        **summary.__dict__,
        file=FileTechnical(
            file_size_bytes=1024,
            file_modified_ns=123456789,
            audio_format="wav",
            sample_rate_hz=44_100,
            channel_count=2,
            bit_rate_bps=1_411_200,
            bit_depth=16,
            audio_duration_seconds=300.0,
            last_scanned_at=_NOW,
            missing_since=None,
        ),
        file_tags=None,
        sonara_core=None,
        maest=None,
        embeddings=(),
        classifier_scores_detail=tuple(scores),
    )
    return summary, detail


class _PublicClassifierReader:
    """Classifier production reader with no SQLite/direct-SQL surface."""

    def __init__(
        self,
        tracks: list[tuple[TrackSummary, TrackDetail]],
    ) -> None:
        self._summaries = [summary for summary, _detail in tracks]
        self._details = {detail.track_id: detail for _summary, detail in tracks}

    def list_track_summaries(self) -> list[TrackSummary]:
        return list(self._summaries)

    def get_track_detail(self, track_id: int) -> TrackDetail:
        return self._details[track_id]

    def list_liked_track_ids(self) -> list[int]:
        return []

    def get_pair_feedback_map(
        self,
    ) -> dict[tuple[int, int, str], dict[str, object]]:
        return {}

    def count_evaluation_rows(self) -> dict[str, int]:
        return {"transition_feedback": 0}


def test_promoted_classifiers_expose_feature_driven_manifest_fields(
    tmp_path: Path,
) -> None:
    _write_promoted(tmp_path, "valid_classifier")

    by_key = {item["classifier_key"]: item for item in promoted_classifiers(tmp_path)}

    valid = by_key["valid_classifier"]
    assert valid["manifest_status"] == "valid"
    assert valid["required_inputs"] == ["mert"]
    assert valid["feature_names"] == ["mert:0"]
    assert valid["profile_description"] == "Human-readable classifier description."
    assert valid["trained_label_counts"] == {"negative": 12, "positive": 14}


def test_reports_use_public_current_readers_and_scope_by_classifier_key(
    tmp_path: Path,
) -> None:
    first_info = _write_promoted(tmp_path, "classifier_one")
    second_info = _write_promoted(tmp_path, "classifier_two")
    first = _score_detail("classifier_one", score=0.52)
    second_on_first = _score_detail("classifier_two", score=0.91)
    second_on_second = _score_detail("classifier_two", score=0.12)
    reader = _PublicClassifierReader(
        [
            _track(1, first, second_on_first),
            _track(2, second_on_second),
        ]
    )

    report = build_classifier_calibration_report(
        reader,
        "classifier_one",
        classifier_info=first_info,
        min_feedback=1,
    )
    suggestions = suggest_classifier_labels(
        reader,
        "classifier_one",
        classifier_info=first_info,
        limit=10,
    )

    assert report["coverage"]["tracks_total"] == 2
    assert report["coverage"]["tracks_scored"] == 1
    assert report["coverage"]["fresh_scores"] == 1
    assert report["coverage"]["stale_scores"] == 0
    assert report["score_distribution"]["count"] == 1
    assert suggestions["status"] == "ok"
    assert [row["track"]["id"] for row in suggestions["suggestions"]] == [1]

    second_report = build_classifier_calibration_report(
        reader,
        "classifier_two",
        classifier_info=second_info,
        min_feedback=1,
    )
    assert second_report["coverage"]["tracks_scored"] == 2
