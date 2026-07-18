from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pytest

from dj_track_similarity.classifier_jobs import ClassifierJobManager
from dj_track_similarity.classifier_scoring import (
    ClassifierScorer,
    _embedding_vectors,
    analyze_classifier,
    default_classifier_model_path,
)
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_contract import expected_sonara_analysis_signature, feature_set_uses_sonara


class FixedProbabilityModel:
    classes_ = np.asarray(["broken", "straight"])

    def predict_proba(self, matrix):
        return np.tile(np.asarray([[0.87, 0.13]], dtype=np.float64), (matrix.shape[0], 1))

    def predict(self, matrix):
        return np.asarray(["broken"] * matrix.shape[0])


class AlmostCertainModel:
    classes_ = np.asarray(["broken", "straight"])

    def predict_proba(self, matrix):
        return np.tile(np.asarray([[0.99999999, 0.00000001]], dtype=np.float64), (matrix.shape[0], 1))

    def predict(self, matrix):
        return np.asarray(["broken"] * matrix.shape[0])


def test_analyze_classifier_scores_feature_complete_tracks_and_skips_missing_features(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    complete_id = _track(db, tmp_path, "complete.wav")
    missing_id = _track(db, tmp_path, "missing.wav")
    _save_sonara_features(db, complete_id)
    db.save_embedding(complete_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(complete_id, np.asarray([1.0], dtype=np.float32), "maest-test", embedding_key="maest")
    model_path = _write_model(tmp_path / "model.joblib")

    result = analyze_classifier(db, classifier="break_energy", model_path=model_path)

    assert result == {"classifier": "break_energy", "scored": 1, "skipped": 1, "model": str(model_path)}
    score = db.classifier_score(complete_id, "break_energy")
    assert score is not None
    assert score["score"] == 0.87
    assert score["confidence"] == 0.87
    assert score["label"] == "high"
    assert score["probabilities"] == {
        "broken": 0.87,
        "straight": 0.13,
    }
    assert score["feature_set"] == "combined"
    assert score["model_id"] == str(model_path)
    assert db.classifier_score(missing_id, "break_energy") is None


def test_analyze_classifier_scores_non_combined_clap_feature_set(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    complete_id = _track(db, tmp_path, "complete-clap.wav")
    missing_id = _track(db, tmp_path, "missing-clap.wav")
    db.save_embedding(complete_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(complete_id, np.asarray([1.0], dtype=np.float32), "clap-test", embedding_key="clap")
    db.save_embedding(missing_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    model_path = _write_model(
        tmp_path / "model.joblib",
        feature_set="mert+clap",
        feature_names=["mert:0", "clap:0"],
    )

    result = analyze_classifier(db, classifier="break_energy", model_path=model_path)

    assert result == {"classifier": "break_energy", "scored": 1, "skipped": 1, "model": str(model_path)}
    score = db.classifier_score(complete_id, "break_energy")
    assert score is not None
    assert score["score"] == 0.87
    assert score["feature_set"] == "mert+clap"
    assert db.classifier_score(missing_id, "break_energy") is None


def test_analyze_classifier_skips_tracks_with_existing_classifier_score(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    existing_id = _complete_track(db, tmp_path, "existing.wav")
    missing_id = _complete_track(db, tmp_path, "missing.wav")
    db.save_classifier_score(
        existing_id,
        classifier="break_energy",
        score=0.42,
        label="low",
        confidence=0.58,
        probabilities={"broken": 0.42, "straight": 0.58},
        feature_set="combined",
        model_id="old-model.joblib",
    )
    model_path = _write_model(tmp_path / "model.joblib")

    result = analyze_classifier(db, classifier="break_energy", model_path=model_path)

    assert result["scored"] == 1
    assert db.classifier_score(existing_id, "break_energy")["score"] == 0.42
    assert db.classifier_score(missing_id, "break_energy")["score"] == 0.87


def test_analyze_classifier_treats_other_classifier_scores_as_missing_for_requested_key(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _complete_track(db, tmp_path, "other-classifier.wav")
    db.save_classifier_score(
        track_id,
        classifier="live_instrumentation",
        score=0.91,
        label="high",
        confidence=0.91,
        probabilities={"live": 0.91, "synthetic": 0.09},
        feature_set="combined",
        model_id="live-model.joblib",
    )
    model_path = _write_model(tmp_path / "model.joblib")

    result = analyze_classifier(db, classifier="break_energy", model_path=model_path)
    break_score = db.classifier_score(track_id, "break_energy")
    live_score = db.classifier_score(track_id, "live_instrumentation")

    assert result["scored"] == 1
    assert break_score is not None
    assert break_score["score"] == 0.87
    assert live_score is not None
    assert live_score["score"] == 0.91


def test_analyze_classifier_preserves_high_confidence_probability_precision(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "complete.wav")
    _save_sonara_features(db, track_id)
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "maest-test", embedding_key="maest")
    model_path = _write_model(tmp_path / "model.joblib", model=AlmostCertainModel())

    analyze_classifier(db, classifier="break_energy", model_path=model_path)

    score = db.classifier_score(track_id, "break_energy")
    assert score is not None
    assert score["score"] == 0.99999999
    assert score["confidence"] == 0.99999999
    assert score["probabilities"] == {
        "broken": 0.99999999,
        "straight": 0.00000001,
    }


def test_break_energy_filter_orders_tracks_by_score(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    low_id = _track(db, tmp_path, "low.wav", title="Low")
    high_id = _track(db, tmp_path, "high.wav", title="High")
    db.save_classifier_score(
        low_id,
        classifier="break_energy",
        score=0.72,
        label="medium",
        confidence=0.72,
        probabilities={"break_energy": 0.72, "straight_energy": 0.28},
        feature_set="combined",
        model_id="model.joblib",
    )
    db.save_classifier_score(
        high_id,
        classifier="break_energy",
        score=0.94,
        label="high",
        confidence=0.94,
        probabilities={"break_energy": 0.94, "straight_energy": 0.06},
        feature_set="combined",
        model_id="model.joblib",
    )

    page = db.list_tracks_page(classifier_min_scores={"break_energy": 0.8})
    filtered = db.list_filtered_tracks(classifier_min_scores={"break_energy": 0.8})

    assert [track.id for track in page["items"]] == [high_id]
    assert page["items"][0].classifier_scores["break_energy"]["score"] == 0.94
    assert [track.id for track in filtered["items"]] == [high_id]


def test_generic_classifier_filter_orders_tracks_by_score(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    low_id = _track(db, tmp_path, "low-live.wav", title="Low")
    high_id = _track(db, tmp_path, "high-live.wav", title="High")
    db.save_classifier_score(
        low_id,
        classifier="live_instrumentation",
        score=0.51,
        label="medium",
        confidence=0.51,
        probabilities={"live_instrument": 0.51, "no_instrument": 0.49},
        feature_set="combined",
        model_id="model.joblib",
    )
    db.save_classifier_score(
        high_id,
        classifier="live_instrumentation",
        score=0.91,
        label="high",
        confidence=0.91,
        probabilities={"live_instrument": 0.91, "no_instrument": 0.09},
        feature_set="combined",
        model_id="model.joblib",
    )

    page = db.list_tracks_page(classifier_min_scores={"live_instrumentation": 0.8})
    filtered = db.list_filtered_tracks(classifier_min_scores={"live_instrumentation": 0.8})

    assert [track.id for track in page["items"]] == [high_id]
    assert page["items"][0].classifier_scores["live_instrumentation"]["score"] == 0.91
    assert [track.id for track in filtered["items"]] == [high_id]


def test_reset_classifier_scores_is_db_only_and_scoped_by_classifier_key(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "classifier-reset.wav")
    audio_path = tmp_path / "classifier-reset.wav"
    original_audio = audio_path.read_bytes()
    db.save_classifier_score(
        track_id,
        classifier="break_energy",
        score=0.94,
        label="high",
        confidence=0.94,
        probabilities={"break_energy": 0.94, "straight_energy": 0.06},
        feature_set="combined",
        model_id="model.joblib",
    )
    db.save_classifier_score(
        track_id,
        classifier="live_instrumentation",
        score=0.81,
        label="high",
        confidence=0.81,
        probabilities={"live_instrument": 0.81, "no_instrument": 0.19},
        feature_set="combined",
        model_id="model.joblib",
    )

    result = db.reset_classifier_scores(["break_energy"])

    assert result == {"classifiers": ["break_energy"], "scores_deleted": 1}
    assert db.classifier_score(track_id, "break_energy") is None
    remaining_score = db.classifier_score(track_id, "live_instrumentation")
    assert remaining_score is not None
    assert remaining_score["score"] == 0.81
    assert db.get_track(track_id).path == audio_path.as_posix()
    assert audio_path.read_bytes() == original_audio


def test_classifier_filter_page_uses_score_lookup_index(tmp_path: Path, monkeypatch) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for index, score in enumerate((0.1, 0.9, 0.8), start=1):
        track_id = _track(db, tmp_path, f"track-{index}.wav", title=f"Track {index}")
        db.save_classifier_score(
            track_id,
            classifier="break_energy",
            score=score,
            label="high" if score >= 0.8 else "low",
            confidence=score,
            probabilities={"break_energy": score, "straight_energy": 1.0 - score},
            feature_set="combined",
            model_id="model.joblib",
        )
    statements: list[str] = []
    original_connect = db.connect

    def traced_connect():
        connection = original_connect()
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(db, "connect", traced_connect)

    db.list_tracks_page(classifier_min_scores={"break_energy": 0.8})

    page_statements = [
        statement
        for statement in statements
        if "LEFT JOIN embeddings" in statement and "LIMIT" in statement and "OFFSET" in statement
    ]
    assert page_statements
    assert "FROM track_classifier_scores" in page_statements[0]
    assert "SCAN t" not in _query_plan_details(db, page_statements[0])
    assert "idx_classifier_scores_lookup" in _query_plan_details(db, page_statements[0])


def test_classifier_jobs_are_scoped_by_classifier_key(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "one.wav")
    manager = ClassifierJobManager(db)

    break_job = manager.create_job(classifier="break_energy")
    live_job = manager.create_job(classifier="live_instrumentation")

    assert manager.latest(classifier="break_energy").job_id == break_job
    assert manager.latest(classifier="live_instrumentation").job_id == live_job
    assert manager.get(break_job, classifier="break_energy").adapter_name == "break_energy"
    with pytest.raises(KeyError):
        manager.get(live_job, classifier="break_energy")
    with pytest.raises(KeyError):
        manager.cancel(live_job, classifier="break_energy")
    assert manager.get(live_job).cancel_requested is False


def test_classifier_job_total_counts_only_missing_classifier_scores(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    existing_id = _track(db, tmp_path, "existing.wav")
    _track(db, tmp_path, "missing.wav")
    db.save_classifier_score(
        existing_id,
        classifier="break_energy",
        score=0.81,
        label="high",
        confidence=0.81,
        probabilities={"broken": 0.81, "straight": 0.19},
        feature_set="combined",
        model_id="model.joblib",
    )
    manager = ClassifierJobManager(db)

    job_id = manager.create_job(classifier="break_energy")

    assert manager.get(job_id).total == 1


def test_default_classifier_model_path_points_to_profile_classifier_asset() -> None:
    assert default_classifier_model_path("live_instrumentation").as_posix().endswith(
        "models/classifiers/live-instrumentation/model.joblib"
    )


def test_classifier_embedding_vector_map_reuses_cached_matrix_rows(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "one.wav")
    db.save_embedding(track_id, np.asarray([1.0, 2.0], dtype=np.float32), "mert-test", embedding_key="mert")
    _, matrix = db.load_embedding_matrix("mert")

    vectors = _embedding_vectors(db, "mert")

    assert np.shares_memory(vectors[track_id], matrix)


def test_classifier_scorer_loads_embeddings_created_after_scorer_initialization(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "later-ready.wav")
    _save_sonara_features(db, track_id)
    model_path = _write_model(tmp_path / "model.joblib")
    scorer = ClassifierScorer(db, classifier="break_energy", model_path=model_path)

    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "maest-test", embedding_key="maest")

    assert scorer.score_track(db.get_track(track_id)) == {"broken": 0.87, "straight": 0.13}


def _track(db: LibraryDatabase, tmp_path: Path, filename: str, title: str | None = None) -> int:
    path = tmp_path / filename
    path.write_bytes(b"audio")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=1.0, metadata={"title": title or filename})


def _complete_track(db: LibraryDatabase, tmp_path: Path, filename: str) -> int:
    track_id = _track(db, tmp_path, filename)
    _save_sonara_features(db, track_id)
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "mert-test", embedding_key="mert")
    db.save_embedding(track_id, np.asarray([1.0], dtype=np.float32), "maest-test", embedding_key="maest")
    return track_id


def _save_sonara_features(db: LibraryDatabase, track_id: int) -> None:
    db.save_sonara_features(
        track_id,
        {"bpm": {"type": "float", "value": 128.0}},
        model_name="sonara-test",
        analysis_signature=expected_sonara_analysis_signature([]),
    )


def _write_model(
    path: Path,
    *,
    model: object | None = None,
    feature_set: str = "combined",
    feature_names: list[str] | None = None,
) -> Path:
    uses_sonara = feature_set_uses_sonara(feature_set)
    signature = expected_sonara_analysis_signature([]) if uses_sonara else None
    effective_feature_names = feature_names or ["sonara:bpm", "mert:0", "maest:0"]
    payload = {
        "model": model or FixedProbabilityModel(),
        "feature_set": feature_set,
        "feature_names": effective_feature_names,
        "label_order": ["broken", "straight"],
        "classifier_key": "break_energy",
        "positive_label": "broken",
        **({"sonara_analysis_signature": signature} if signature is not None else {}),
    }
    joblib.dump(payload, path)
    required_inputs = sorted({name.split(":", 1)[0] for name in effective_feature_names})
    path.with_name("model.json").write_text(
        json.dumps(
            {
                "classifier_key": "break_energy",
                "manifest_version": 2,
                "profile_name": "Break Energy",
                "profile_type": "binary",
                "feature_set": feature_set,
                "feature_count": len(effective_feature_names),
                "label_order": ["broken", "straight"],
                "positive_label": "broken",
                "negative_label": "straight",
                "trained_label_counts": {"broken": 10, "straight": 10},
                "production": {
                    "score_semantics": "positive_label_probability",
                    "required_inputs": required_inputs,
                    "calibration": {"status": "uncalibrated", "method": None, "report": None},
                    **({"sonara_analysis_signature": signature} if signature is not None else {}),
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _query_plan_details(db: LibraryDatabase, sql: str) -> str:
    with db.connect() as connection:
        rows = connection.execute(f"EXPLAIN QUERY PLAN {sql}").fetchall()
    return "\n".join(str(row["detail"]) for row in rows)
