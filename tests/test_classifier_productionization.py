from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dj_track_similarity.analysis_model_runners import (
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisOutput,
    classifier_required_outputs_hash,
)
from dj_track_similarity.classifier_manifest import (
    classifier_feature_manifest_hash,
)
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
    OptionalOutputs,
    TrackDetail,
    TrackSummary,
)


_NOW = "2026-07-24T12:00:00.000000Z"
_ARTIFACT_BYTES = b"fixture"
_ARTIFACT_HASH = f"sha256:{hashlib.sha256(_ARTIFACT_BYTES).hexdigest()}"


def _mert_output() -> AnalysisOutput:
    return current_embedding_analysis_output("mert", device="cpu")


def _manifest_payload(
    classifier_key: str,
    output: AnalysisOutput,
    *,
    model_id: str | None = None,
    hybrid_signal: dict[str, object] | None = None,
) -> dict[str, object]:
    feature_names = ("mert:0",)
    payload: dict[str, object] = {
        "manifest_version": 2,
        "classifier_key": classifier_key,
        "profile_name": classifier_key.replace("_", " ").title(),
        "model_id": model_id or f"{classifier_key}-model",
        "artifact_hash": _ARTIFACT_HASH,
        "feature_set": "mert-contract",
        "feature_names": list(feature_names),
        "feature_count": len(feature_names),
        "feature_manifest_hash": classifier_feature_manifest_hash(feature_names),
        "label_order": ["negative", "positive"],
        "negative_label": "negative",
        "positive_label": "positive",
        "production": {
            "score_semantics": "positive_label_probability",
            "required_outputs": [
                {
                    "contract_hash": output.contract_hash,
                    "canonical_payload": output.contract.canonical_payload,
                }
            ],
            "calibration": {"status": "uncalibrated"},
        },
    }
    if hybrid_signal is not None:
        payload["hybrid_signal"] = hybrid_signal
    return payload


def _write_promoted(
    root: Path,
    classifier_key: str,
    output: AnalysisOutput,
    *,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    artifact_dir = root / classifier_key.replace("_", "-")
    artifact_dir.mkdir(parents=True)
    model_path = artifact_dir / "model.joblib"
    metadata_path = artifact_dir / "model.json"
    model_path.write_bytes(_ARTIFACT_BYTES)
    metadata_path.write_text(
        json.dumps(payload or _manifest_payload(classifier_key, output)),
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
    model_id: str | None = None,
    feature_manifest_hash: str | None = None,
    required_outputs_hash: str | None = None,
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
        feature_set="mert-contract",
        feature_manifest_hash=(
            feature_manifest_hash or classifier_feature_manifest_hash(("mert:0",))
        ),
        required_outputs_hash=(
            required_outputs_hash or classifier_required_outputs_hash((_mert_output(),))
        ),
        model_id=model_id or f"{classifier_key}-model",
        uses_sonara=False,
        sonara_release_hash=None,
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
        catalog_uuid="catalog-v7",
        track_uuid=f"track-{track_id}",
        content_generation=1,
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
            audio_codec="pcm_s16le",
            sample_rate_hz=44_100,
            channel_count=2,
            bit_rate_bps=1_411_200,
            audio_duration_seconds=300.0,
            last_scanned_at=_NOW,
            missing_since=None,
        ),
        file_tags=None,
        sonara_core=None,
        maest=None,
        embeddings=(),
        classifier_scores_detail=tuple(scores),
        optional_outputs=OptionalOutputs(
            timeline_fields=(),
            sonara_embedding_available=False,
            audio_fingerprint_available=False,
        ),
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


def test_promoted_classifiers_expose_only_v7_contract_manifest_fields(
    tmp_path: Path,
) -> None:
    output = _mert_output()
    _write_promoted(tmp_path, "valid_classifier", output)
    v1_payload = {"manifest_version": 1}
    _write_promoted(
        tmp_path,
        "old_classifier",
        output,
        payload=v1_payload,
    )

    by_key = {item["classifier_key"]: item for item in promoted_classifiers(tmp_path)}

    valid = by_key["valid_classifier"]
    assert valid["manifest_status"] == "valid"
    assert valid["required_inputs"] == ["mert"]
    assert valid["required_outputs"] == [
        {
            "contract_hash": output.contract_hash,
            "canonical_payload": output.contract.canonical_payload,
        }
    ]
    assert "sonara_analysis_signature" not in valid
    assert "embedding_key" not in valid

    unsupported = by_key["old_classifier"]
    assert unsupported["manifest_status"] == "unsupported"
    assert not unsupported["is_scoring_compatible"]
    assert "no longer supported" in unsupported["manifest_errors"][0]


def test_hybrid_signal_is_manifest_only_without_legacy_fallback(
    tmp_path: Path,
) -> None:
    output = _mert_output()
    _write_promoted(
        tmp_path,
        "manifest_signal",
        output,
        payload=_manifest_payload(
            "manifest_signal",
            output,
            hybrid_signal={
                "role": "preference_boost",
                "axis": "groove",
                "label": "Boost groove",
                "missing_score_policy": "neutral",
            },
        ),
    )
    _write_promoted(tmp_path, "break_energy", output)

    by_key = {item["classifier_key"]: item for item in promoted_classifiers(tmp_path)}

    assert by_key["manifest_signal"]["hybrid_signal"] == {
        "role": "preference_boost",
        "axis": "groove",
        "label": "Boost groove",
        "missing_score_policy": "neutral",
    }
    assert by_key["manifest_signal"]["hybrid_signal_source"] == "manifest"
    assert by_key["break_energy"]["hybrid_signal"] is None
    assert by_key["break_energy"]["hybrid_signal_source"] is None
    assert all("legacy_hybrid_signal" not in item for item in by_key.values())


def test_reports_use_public_v7_readers_and_scope_by_classifier_key(
    tmp_path: Path,
) -> None:
    output = _mert_output()
    first_info = _write_promoted(tmp_path, "classifier_one", output)
    second_info = _write_promoted(tmp_path, "classifier_two", output)
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


def test_report_freshness_uses_full_persisted_classifier_identity(
    tmp_path: Path,
) -> None:
    output = _mert_output()
    info = _write_promoted(tmp_path, "test_classifier", output)
    stale_hash = _score_detail(
        "test_classifier",
        score=0.8,
        feature_manifest_hash="sha256:" + "f" * 64,
    )
    stale_model = _score_detail(
        "test_classifier",
        score=0.2,
        model_id="old-model",
    )
    stale_outputs = _score_detail(
        "test_classifier",
        score=0.6,
        required_outputs_hash="sha256:" + "e" * 64,
    )
    reader = _PublicClassifierReader(
        [
            _track(1, stale_hash),
            _track(2, stale_model),
            _track(3, stale_outputs),
        ]
    )

    report = build_classifier_calibration_report(
        reader,
        "test_classifier",
        classifier_info=info,
        min_feedback=1,
    )
    suggestions = suggest_classifier_labels(
        reader,
        "test_classifier",
        classifier_info=info,
    )

    assert report["status"] == "stale"
    assert report["coverage"]["fresh_scores"] == 0
    assert report["coverage"]["stale_scores"] == 3
    assert report["coverage"]["stale_model_ids"] == {"old-model": 1}
    assert report["coverage"]["stale_identity_fields"] == {
        "feature_manifest_hash": 1,
        "model_id": 1,
        "required_outputs_hash": 1,
    }
    assert suggestions["status"] == "insufficient_data"
    assert suggestions["suggestions"] == []
    assert any(
        "current full classifier identity" in warning
        for warning in suggestions["warnings"]
    )
