from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_contract import expected_sonara_analysis_signature


def _track(db: LibraryDatabase, tmp_path: Path, name: str) -> int:
    path = tmp_path / name
    path.write_bytes(b"RIFF0000WAVE")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=path.stat().st_mtime, metadata={"title": name})


def _mark_analyzed(db: LibraryDatabase, track_id: int, model: str) -> None:
    if model == "sonara":
        db.save_sonara_features(
            track_id,
            {"bpm": {"value": 128.0}},
            model_name="fake-sonara",
            analysis_signature=expected_sonara_analysis_signature([]),
        )
        return
    if model == "maest":
        db.save_genres(track_id, [{"label": "Techno", "score": 0.9}], model_name="fake-maest")
        db.save_embedding(track_id, np.asarray([1.0, 0.0, 0.0], dtype=np.float32), "fake-maest", embedding_key="maest")
        return
    db.save_embedding(track_id, np.asarray([1.0, 0.0, 0.0], dtype=np.float32), f"fake-{model}", embedding_key=model)


class FakeModelRunner:
    def __init__(self, model: str, *, fail_names: set[str] | None = None, order: list[str] | None = None) -> None:
        self.model = model
        self.model_name = f"fake-{model}"
        self.device = "cpu"
        self.calls: list[list[str]] = []
        self.fail_names = fail_names or set()
        self.order = order

    def analyze_batch(self, db: LibraryDatabase, items) -> None:
        names = [Path(item.track.path).name for item in items]
        self.calls.append(names)
        if self.order is not None:
            self.order.append(self.model)
        if any(name in self.fail_names for name in names):
            raise RuntimeError(f"{self.model} failed")
        for item in items:
            _mark_analyzed(db, item.track.id, self.model)


class DecodeRecorder:
    def __init__(self, *, fail_names: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.fail_names = fail_names or set()

    def __call__(self, path: str | Path):
        name = Path(path).name
        self.calls.append(name)
        if name in self.fail_names:
            raise RuntimeError("decode failed")
        return SimpleNamespace(path=str(path), audio=np.ones(48_000, dtype=np.float32), sample_rate=48_000, detail="fake")


class FakeClassifierScorer:
    def __init__(self, db: LibraryDatabase, classifier: str, order: list[str]) -> None:
        self.db = db
        self.classifier_key = classifier
        self.order = order

    def score_track(self, track):
        analyses = set(track.analyses or [])
        if {"sonara", "maest", "mert"}.issubset(analyses):
            self.order.append(f"{self.classifier_key}:score")
            return {"positive": 0.9, "negative": 0.1}
        return None

    def save_score(self, track, probabilities) -> None:
        self.order.append(f"{self.classifier_key}:save")
        self.db.save_classifier_score(
            track.id,
            classifier=self.classifier_key,
            score=probabilities["positive"],
            label="high",
            confidence=probabilities["positive"],
            probabilities=probabilities,
            feature_set="combined",
            model_id="fake-classifier",
        )


def test_analysis_job_rejects_mixing_sonara_with_ml_or_classifiers(tmp_path: Path) -> None:
    manager = AnalysisJobManager(LibraryDatabase(tmp_path / "library.sqlite"), model_runners={})

    with pytest.raises(ValueError, match="SONARA analysis must run alone"):
        manager.run_sync(models=["sonara", "mert"], device="cpu")

    with pytest.raises(ValueError, match="cannot be combined with classifiers"):
        manager.run_sync(models=["sonara"], classifier_keys=["break_energy"], device="cpu")

    with pytest.raises(ValueError, match="feature families can only"):
        manager.run_sync(models=["mert"], sonara_features=["vocalness"], device="cpu")


def test_multi_model_job_selects_tracks_missing_selected_models_and_skips_existing(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    missing_mert = _track(db, tmp_path, "a-missing-mert.wav")
    missing_maest = _track(db, tmp_path, "b-missing-maest.wav")
    complete_selected = _track(db, tmp_path, "c-complete-selected.wav")
    missing_unselected = _track(db, tmp_path, "d-missing-unselected-clap.wav")
    _mark_analyzed(db, missing_mert, "maest")
    _mark_analyzed(db, missing_maest, "mert")
    for model in ("maest", "mert"):
        _mark_analyzed(db, complete_selected, model)
        _mark_analyzed(db, missing_unselected, model)
    runners = {model: FakeModelRunner(model) for model in ("maest", "mert")}
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["maest", "mert"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.total == 2
    assert status.processed == 2
    assert status.analyzed == 2
    assert status.failed == 0
    assert status.skipped == 0
    assert status.model_progress["maest"].total == 1
    assert status.model_progress["maest"].analyzed == 1
    assert status.model_progress["mert"].total == 1
    assert status.model_progress["mert"].analyzed == 1
    assert decoder.calls == ["a-missing-mert.wav", "b-missing-maest.wav"]
    assert runners["maest"].calls == [["b-missing-maest.wav"]]
    assert runners["mert"].calls == [["a-missing-mert.wav"]]


def test_multi_model_job_treats_muq_as_independent_audio_model(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    missing_muq = _track(db, tmp_path, "a-missing-muq.wav")
    present_muq = _track(db, tmp_path, "b-present-muq.wav")
    _mark_analyzed(db, missing_muq, "mert")
    _mark_analyzed(db, present_muq, "muq")
    runners = {"muq": FakeModelRunner("muq")}
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["muq"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.total == 1
    assert status.model_progress["muq"].total == 1
    assert status.model_progress["muq"].analyzed == 1
    assert decoder.calls == ["a-missing-muq.wav"]
    assert runners["muq"].calls == [["a-missing-muq.wav"]]
    assert db.get_track(missing_muq).analyses == ["mert", "muq"]
    assert db.get_track(present_muq).analyses == ["muq"]


def test_multi_model_limit_counts_candidate_tracks_not_per_model_totals(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    existing = _track(db, tmp_path, "a-existing.wav")
    for model in ("maest", "mert"):
        _mark_analyzed(db, existing, model)
    for name in ["b-candidate.wav", "c-candidate.wav", "d-candidate.wav"]:
        _track(db, tmp_path, name)
    runners = {model: FakeModelRunner(model) for model in ("maest", "mert")}
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=4)

    status = manager.run_sync(models=["maest", "mert"], limit=2, device="cpu", track_batch_size=4)

    assert status.total == 2
    assert status.processed == 2
    assert status.analyzed == 2
    assert status.failed == 0
    assert status.skipped == 0
    assert decoder.calls == ["b-candidate.wav", "c-candidate.wav"]
    assert runners["maest"].calls == [["b-candidate.wav", "c-candidate.wav"]]
    assert runners["mert"].calls == [["b-candidate.wav", "c-candidate.wav"]]


def test_multi_model_job_uses_lean_analysis_candidates(tmp_path: Path, monkeypatch) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a-candidate.wav")
    runners = {model: FakeModelRunner(model) for model in ("maest", "mert")}
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=2)
    original_candidates = db.list_analysis_candidates
    calls: list[tuple[tuple[str, ...], int | None]] = []

    def spy_candidates(models, *, limit=None, expected_sonara_signature=None):
        calls.append((tuple(models), limit))
        return original_candidates(
            models,
            limit=limit,
            expected_sonara_signature=expected_sonara_signature,
        )

    monkeypatch.setattr(db, "list_analysis_candidates", spy_candidates)

    status = manager.run_sync(models=["maest", "mert"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.total == 1
    assert calls == [(("maest", "mert"), None)]
    assert decoder.calls == ["a-candidate.wav"]


def test_multi_model_job_logs_track_success_once_after_all_models_complete(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a-candidate.wav")
    runners = {model: FakeModelRunner(model) for model in ("maest", "mert")}
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=1)

    status = manager.run_sync(models=["maest", "mert"], device="cpu", track_batch_size=1)

    track_events = [event for event in status.events if event.message == "Track analyzed"]
    assert [(Path(event.path or "").name, event.model) for event in track_events] == [("a-candidate.wav", None)]


def test_multi_model_job_scores_classifiers_after_all_selected_audio_models_complete(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "a-candidate.wav")
    order: list[str] = []
    _mark_analyzed(db, track_id, "sonara")
    runners = {model: FakeModelRunner(model, order=order) for model in ("maest", "mert", "clap")}
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(
        db,
        model_runners=runners,
        decode_audio=decoder,
        track_batch_size=1,
        classifier_scorer_factory=lambda classifier: FakeClassifierScorer(db, classifier, order),
    )

    status = manager.run_sync(
        models=["maest", "mert", "clap"],
        classifier_keys=["break_energy"],
        device="cpu",
        track_batch_size=1,
    )

    assert status.state == "completed"
    assert db.classifier_score(track_id, "break_energy")["score"] == 0.9
    assert order.index("break_energy:save") > order.index("clap")
    assert any(event.message == "Classifier analyzed" and event.model == "break_energy" for event in status.events)


def test_multi_model_job_scores_classifiers_after_each_audio_batch_completes(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    first_id = _track(db, tmp_path, "a-candidate.wav")
    second_id = _track(db, tmp_path, "b-candidate.wav")
    _mark_analyzed(db, first_id, "sonara")
    _mark_analyzed(db, second_id, "sonara")
    order: list[str] = []
    runners = {
        model: FakeModelRunner(model, order=order)
        for model in ("maest", "mert", "clap")
    }
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(
        db,
        model_runners=runners,
        decode_audio=decoder,
        track_batch_size=1,
        classifier_scorer_factory=lambda classifier: FakeClassifierScorer(db, classifier, order),
    )

    status = manager.run_sync(
        models=["maest", "mert", "clap"],
        classifier_keys=["break_energy"],
        device="cpu",
        track_batch_size=1,
    )

    second_maest_index = [index for index, step in enumerate(order) if step == "maest"][1]
    first_classifier_save_index = order.index("break_energy:save")
    assert status.state == "completed"
    assert first_classifier_save_index < second_maest_index


def test_multi_model_job_scores_classifiers_after_selected_required_models_when_clap_not_selected(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "a-candidate.wav")
    _mark_analyzed(db, track_id, "sonara")
    order: list[str] = []
    runners = {
        model: FakeModelRunner(model, order=order)
        for model in ("maest", "mert")
    }
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(
        db,
        model_runners=runners,
        decode_audio=decoder,
        track_batch_size=1,
        classifier_scorer_factory=lambda classifier: FakeClassifierScorer(db, classifier, order),
    )

    status = manager.run_sync(
        models=["maest", "mert"],
        classifier_keys=["break_energy"],
        device="cpu",
        track_batch_size=1,
    )

    assert status.state == "completed"
    assert db.classifier_score(track_id, "break_energy")["score"] == 0.9
    assert order == ["maest", "mert", "break_energy:score", "break_energy:save"]
    assert "clap" not in order


def test_multi_model_job_tracks_classifier_only_work_as_unified_progress(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "a-classifier-ready.wav")
    for model in ("sonara", "maest", "mert"):
        _mark_analyzed(db, track_id, model)
    order: list[str] = []
    runners = {
        model: FakeModelRunner(model, order=order)
        for model in ("sonara", "maest", "mert")
    }
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(
        db,
        model_runners=runners,
        decode_audio=decoder,
        track_batch_size=1,
        classifier_scorer_factory=lambda classifier: FakeClassifierScorer(db, classifier, order),
    )

    status = manager.run_sync(
        models=[],
        classifier_keys=["break_energy"],
        device="cpu",
        track_batch_size=1,
    )

    assert status.state == "completed"
    assert status.total == 1
    assert status.processed == 1
    assert status.analyzed == 1
    assert status.model_progress["break_energy"].total == 1
    assert status.model_progress["break_energy"].analyzed == 1
    assert db.classifier_score(track_id, "break_energy")["score"] == 0.9
    assert decoder.calls == []
    assert order == ["break_energy:score", "break_energy:save"]


def test_multi_model_job_scores_only_missing_new_classifier_when_old_scores_exist(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "a-classifier-ready.wav")
    for model in ("sonara", "maest", "mert"):
        _mark_analyzed(db, track_id, model)
    db.save_classifier_score(
        track_id,
        classifier="break_energy",
        score=0.81,
        label="high",
        confidence=0.81,
        probabilities={"positive": 0.81, "negative": 0.19},
        feature_set="combined",
        model_id="old-break-energy",
    )
    order: list[str] = []
    manager = AnalysisJobManager(
        db,
        model_runners={},
        decode_audio=DecodeRecorder(),
        track_batch_size=1,
        classifier_scorer_factory=lambda classifier: FakeClassifierScorer(db, classifier, order),
    )

    status = manager.run_sync(
        models=[],
        classifier_keys=["break_energy", "abstract_edge"],
        device="cpu",
        track_batch_size=1,
    )

    assert status.state == "completed"
    assert status.total == 1
    assert status.model_progress["break_energy"].total == 0
    assert status.model_progress["abstract_edge"].total == 1
    assert order == ["abstract_edge:score", "abstract_edge:save"]
    assert db.classifier_score(track_id, "break_energy")["model_id"] == "old-break-energy"
    assert db.classifier_score(track_id, "abstract_edge")["score"] == 0.9


def test_multi_model_job_rejects_classifier_candidates_missing_unselected_required_models(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "a-needs-classifier-dependencies.wav")
    order: list[str] = []
    runners = {
        model: FakeModelRunner(model, order=order)
        for model in ("sonara", "maest", "mert", "clap")
    }
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(
        db,
        model_runners=runners,
        decode_audio=decoder,
        track_batch_size=1,
        classifier_scorer_factory=lambda classifier: FakeClassifierScorer(db, classifier, order),
    )

    with pytest.raises(ValueError, match="CLASSIFIERS require SONARA, MAEST, and MERT"):
        manager.run_sync(
            models=["clap"],
            classifier_keys=["break_energy"],
            device="cpu",
            track_batch_size=1,
        )

    assert db.classifier_score(track_id, "break_energy") is None
    assert order == []


def test_multi_model_failure_is_model_scoped_and_other_models_continue(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    good = _track(db, tmp_path, "a-good.wav")
    bad = _track(db, tmp_path, "b-bad.wav")
    runners = {
        "maest": FakeModelRunner("maest", fail_names={"b-bad.wav"}),
        "mert": FakeModelRunner("mert"),
    }
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["maest", "mert"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.total == 2
    assert status.processed == 2
    assert status.analyzed == 1
    assert status.failed == 1
    assert status.skipped == 0
    assert status.model_progress["maest"].analyzed == 1
    assert status.model_progress["maest"].failed == 1
    assert status.model_progress["mert"].analyzed == 2
    assert status.model_progress["mert"].failed == 0
    assert [(error.model, Path(error.path).name) for error in status.errors] == [("maest", "b-bad.wav")]
    assert decoder.calls == ["a-good.wav", "b-bad.wav"]
    assert runners["maest"].calls == [["a-good.wav", "b-bad.wav"], ["a-good.wav"], ["b-bad.wav"]]
    assert runners["mert"].calls == [["a-good.wav", "b-bad.wav"]]
    assert "maest" in (db.get_track(good).analyses or [])
    assert "maest" not in (db.get_track(bad).analyses or [])
    assert "mert" in (db.get_track(bad).analyses or [])


def test_multi_model_decode_failure_marks_missing_selected_models_failed(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a-good.wav")
    _track(db, tmp_path, "b-undecodable.wav")
    runners = {model: FakeModelRunner(model) for model in ("maest", "mert")}
    decoder = DecodeRecorder(fail_names={"b-undecodable.wav"})
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["maest", "mert"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.processed == 2
    assert status.analyzed == 1
    assert status.failed == 1
    assert status.skipped == 0
    assert status.model_progress["maest"].analyzed == 1
    assert status.model_progress["maest"].failed == 1
    assert status.model_progress["mert"].analyzed == 1
    assert status.model_progress["mert"].failed == 1
    assert [(error.model, Path(error.path).name) for error in status.errors] == [
        ("maest", "b-undecodable.wav"),
        ("mert", "b-undecodable.wav"),
    ]
    failure_events = [event for event in status.events if event.level == "error"]
    assert [(Path(event.path or "").name, event.message, event.model) for event in failure_events] == [
        ("b-undecodable.wav", "Track decode failed: decode failed", None)
    ]
    assert runners["maest"].calls == [["a-good.wav"]]
    assert runners["mert"].calls == [["a-good.wav"]]


def test_multi_model_runner_factory_loads_only_models_with_work(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "a-missing-maest.wav")
    _mark_analyzed(db, track_id, "mert")
    created: list[str] = []
    decoder = DecodeRecorder()

    def runner_factory(model: str, device: str, inference_batch_size: int, top_k: int, sonara_features: tuple[str, ...] = ()):
        created.append(model)
        if model == "mert":
            raise AssertionError("runner with no missing model work should not be initialized")
        return FakeModelRunner(model)

    manager = AnalysisJobManager(db, runner_factory=runner_factory, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["maest", "mert"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert created == ["maest"]
    assert status.model_progress["maest"].analyzed == 1
    assert status.model_progress["mert"].total == 0


def test_multi_model_job_preserves_sonara_feature_families_for_runner(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a-missing-sonara.wav")
    observed: list[tuple[str, ...]] = []

    def runner_factory(model: str, device: str, inference_batch_size: int, top_k: int, sonara_features: tuple[str, ...] = ()):
        observed.append(sonara_features)
        return FakeModelRunner(model)

    manager = AnalysisJobManager(db, runner_factory=runner_factory, sonara_decode_audio=DecodeRecorder(), track_batch_size=1)

    status = manager.run_sync(models=["sonara"], device="cpu", sonara_features=["vocalness"])

    assert status.state == "completed"
    assert status.sonara_features == ["vocalness"]
    assert observed == [("vocalness",)]


def test_multi_model_runner_init_failure_marks_only_that_model_failed(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "a-track.wav")
    decoder = DecodeRecorder()

    def runner_factory(model: str, device: str, inference_batch_size: int, top_k: int, sonara_features: tuple[str, ...] = ()):
        if model == "maest":
            raise RuntimeError("maest init failed")
        return FakeModelRunner(model)

    manager = AnalysisJobManager(db, runner_factory=runner_factory, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["mert", "maest"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.processed == 1
    assert status.analyzed == 0
    assert status.failed == 1
    assert status.skipped == 0
    assert status.model_progress["mert"].analyzed == 1
    assert status.model_progress["maest"].failed == 1
    assert [(error.model, Path(error.path).name, error.error) for error in status.errors] == [
        ("maest", "a-track.wav", "maest init failed")
    ]
    assert db.get_track(track_id).analyses == ["mert"]


def test_multi_model_track_batch_and_inference_batch_are_independent(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for name in ["a.wav", "b.wav", "c.wav", "d.wav", "e.wav"]:
        _track(db, tmp_path, name)
    decoder = DecodeRecorder()
    created: list[tuple[str, str, int, int]] = []
    runners: dict[str, FakeModelRunner] = {}

    def runner_factory(model: str, device: str, inference_batch_size: int, top_k: int, sonara_features: tuple[str, ...] = ()):
        created.append((model, device, inference_batch_size, top_k))
        runner = FakeModelRunner(model)
        runners[model] = runner
        return runner

    manager = AnalysisJobManager(db, runner_factory=runner_factory, decode_audio=decoder, track_batch_size=2, inference_batch_size=9)

    status = manager.run_sync(models=["mert"], device="cpu", top_k=5, track_batch_size=2, inference_batch_size=9)

    assert status.track_batch_size == 2
    assert status.inference_batch_size == 9
    assert not hasattr(status, "batch_size")
    assert status.workers == 2
    assert created == [("mert", "cpu", 9, 5)]
    assert runners["mert"].calls == [["a.wav", "b.wav"], ["c.wav", "d.wav"], ["e.wav"]]
