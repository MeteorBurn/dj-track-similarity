from pathlib import Path
from types import SimpleNamespace

import numpy as np

from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.database import LibraryDatabase


def _track(db: LibraryDatabase, tmp_path: Path, name: str) -> int:
    path = tmp_path / name
    path.write_bytes(b"RIFF0000WAVE")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=path.stat().st_mtime, metadata={"title": name})


def _mark_analyzed(db: LibraryDatabase, track_id: int, model: str) -> None:
    if model == "sonara":
        db.save_sonara_features(track_id, {"bpm": {"value": 128.0}}, model_name="fake-sonara")
        return
    if model == "maest":
        db.save_genres(track_id, [{"label": "Techno", "score": 0.9}], model_name="fake-maest")
        db.save_embedding(track_id, np.asarray([1.0, 0.0, 0.0], dtype=np.float32), "fake-maest", embedding_key="maest")
        return
    db.save_embedding(track_id, np.asarray([1.0, 0.0, 0.0], dtype=np.float32), f"fake-{model}", embedding_key=model)


class FakeModelRunner:
    def __init__(self, model: str, *, fail_names: set[str] | None = None) -> None:
        self.model = model
        self.model_name = f"fake-{model}"
        self.device = "cpu"
        self.calls: list[list[str]] = []
        self.fail_names = fail_names or set()

    def analyze_batch(self, db: LibraryDatabase, items) -> None:
        names = [Path(item.track.path).name for item in items]
        self.calls.append(names)
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


def test_multi_model_job_selects_tracks_missing_selected_models_and_skips_existing(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    missing_mert = _track(db, tmp_path, "a-missing-mert.wav")
    missing_sonara = _track(db, tmp_path, "b-missing-sonara.wav")
    complete_selected = _track(db, tmp_path, "c-complete-selected.wav")
    missing_unselected = _track(db, tmp_path, "d-missing-unselected-clap.wav")
    _mark_analyzed(db, missing_mert, "sonara")
    _mark_analyzed(db, missing_sonara, "mert")
    for model in ("sonara", "mert"):
        _mark_analyzed(db, complete_selected, model)
        _mark_analyzed(db, missing_unselected, model)
    runners = {model: FakeModelRunner(model) for model in ("sonara", "mert")}
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["sonara", "mert"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.total == 2
    assert status.processed == 2
    assert status.analyzed == 2
    assert status.failed == 0
    assert status.skipped == 0
    assert status.model_progress["sonara"].total == 1
    assert status.model_progress["sonara"].analyzed == 1
    assert status.model_progress["mert"].total == 1
    assert status.model_progress["mert"].analyzed == 1
    assert decoder.calls == ["a-missing-mert.wav", "b-missing-sonara.wav"]
    assert runners["sonara"].calls == [["b-missing-sonara.wav"]]
    assert runners["mert"].calls == [["a-missing-mert.wav"]]


def test_multi_model_limit_counts_candidate_tracks_not_per_model_totals(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    existing = _track(db, tmp_path, "a-existing.wav")
    for model in ("sonara", "mert"):
        _mark_analyzed(db, existing, model)
    for name in ["b-candidate.wav", "c-candidate.wav", "d-candidate.wav"]:
        _track(db, tmp_path, name)
    runners = {model: FakeModelRunner(model) for model in ("sonara", "mert")}
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=4)

    status = manager.run_sync(models=["sonara", "mert"], limit=2, device="cpu", track_batch_size=4)

    assert status.total == 2
    assert status.processed == 2
    assert status.analyzed == 2
    assert status.failed == 0
    assert status.skipped == 0
    assert decoder.calls == ["b-candidate.wav", "c-candidate.wav"]
    assert runners["sonara"].calls == [["b-candidate.wav", "c-candidate.wav"]]
    assert runners["mert"].calls == [["b-candidate.wav", "c-candidate.wav"]]


def test_multi_model_job_uses_lean_analysis_candidates(tmp_path: Path, monkeypatch) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a-candidate.wav")
    runners = {model: FakeModelRunner(model) for model in ("sonara", "mert")}
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=2)
    original_candidates = db.list_analysis_candidates
    calls: list[tuple[tuple[str, ...], int | None]] = []

    def spy_candidates(models, *, limit=None):
        calls.append((tuple(models), limit))
        return original_candidates(models, limit=limit)

    monkeypatch.setattr(db, "list_analysis_candidates", spy_candidates)

    status = manager.run_sync(models=["sonara", "mert"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.total == 1
    assert calls == [(("sonara", "mert"), None)]
    assert decoder.calls == ["a-candidate.wav"]


def test_multi_model_job_logs_track_success_once_after_all_models_complete(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a-candidate.wav")
    runners = {model: FakeModelRunner(model) for model in ("sonara", "mert")}
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=1)

    status = manager.run_sync(models=["sonara", "mert"], device="cpu", track_batch_size=1)

    track_events = [event for event in status.events if event.message == "Track analyzed"]
    assert [(Path(event.path or "").name, event.model) for event in track_events] == [("a-candidate.wav", None)]


def test_multi_model_failure_is_model_scoped_and_other_models_continue(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    good = _track(db, tmp_path, "a-good.wav")
    bad = _track(db, tmp_path, "b-bad.wav")
    runners = {
        "sonara": FakeModelRunner("sonara", fail_names={"b-bad.wav"}),
        "mert": FakeModelRunner("mert"),
    }
    decoder = DecodeRecorder()
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["sonara", "mert"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.total == 2
    assert status.processed == 2
    assert status.analyzed == 1
    assert status.failed == 1
    assert status.skipped == 0
    assert status.model_progress["sonara"].analyzed == 1
    assert status.model_progress["sonara"].failed == 1
    assert status.model_progress["mert"].analyzed == 2
    assert status.model_progress["mert"].failed == 0
    assert [(error.model, Path(error.path).name) for error in status.errors] == [("sonara", "b-bad.wav")]
    assert decoder.calls == ["a-good.wav", "b-bad.wav"]
    assert runners["sonara"].calls == [["a-good.wav", "b-bad.wav"], ["a-good.wav"], ["b-bad.wav"]]
    assert runners["mert"].calls == [["a-good.wav", "b-bad.wav"]]
    assert "sonara" in (db.get_track(good).analyses or [])
    assert "sonara" not in (db.get_track(bad).analyses or [])
    assert "mert" in (db.get_track(bad).analyses or [])


def test_multi_model_decode_failure_marks_missing_selected_models_failed(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a-good.wav")
    _track(db, tmp_path, "b-undecodable.wav")
    runners = {model: FakeModelRunner(model) for model in ("sonara", "mert")}
    decoder = DecodeRecorder(fail_names={"b-undecodable.wav"})
    manager = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["sonara", "mert"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.processed == 2
    assert status.analyzed == 1
    assert status.failed == 1
    assert status.skipped == 0
    assert status.model_progress["sonara"].analyzed == 1
    assert status.model_progress["sonara"].failed == 1
    assert status.model_progress["mert"].analyzed == 1
    assert status.model_progress["mert"].failed == 1
    assert [(error.model, Path(error.path).name) for error in status.errors] == [
        ("sonara", "b-undecodable.wav"),
        ("mert", "b-undecodable.wav"),
    ]
    failure_events = [event for event in status.events if event.level == "error"]
    assert [(Path(event.path or "").name, event.message, event.model) for event in failure_events] == [
        ("b-undecodable.wav", "Track decode failed: decode failed", None)
    ]
    assert runners["sonara"].calls == [["a-good.wav"]]
    assert runners["mert"].calls == [["a-good.wav"]]


def test_multi_model_runner_factory_loads_only_models_with_work(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "a-missing-sonara.wav")
    _mark_analyzed(db, track_id, "mert")
    created: list[str] = []
    decoder = DecodeRecorder()

    def runner_factory(model: str, device: str, inference_batch_size: int, top_k: int):
        created.append(model)
        if model == "mert":
            raise AssertionError("runner with no missing model work should not be initialized")
        return FakeModelRunner(model)

    manager = AnalysisJobManager(db, runner_factory=runner_factory, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["sonara", "mert"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert created == ["sonara"]
    assert status.model_progress["sonara"].analyzed == 1
    assert status.model_progress["mert"].total == 0


def test_multi_model_runner_init_failure_marks_only_that_model_failed(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "a-track.wav")
    decoder = DecodeRecorder()

    def runner_factory(model: str, device: str, inference_batch_size: int, top_k: int):
        if model == "maest":
            raise RuntimeError("maest init failed")
        return FakeModelRunner(model)

    manager = AnalysisJobManager(db, runner_factory=runner_factory, decode_audio=decoder, track_batch_size=2)

    status = manager.run_sync(models=["sonara", "maest"], device="cpu", track_batch_size=2)

    assert status.state == "completed"
    assert status.processed == 1
    assert status.analyzed == 0
    assert status.failed == 1
    assert status.skipped == 0
    assert status.model_progress["sonara"].analyzed == 1
    assert status.model_progress["maest"].failed == 1
    assert [(error.model, Path(error.path).name, error.error) for error in status.errors] == [
        ("maest", "a-track.wav", "maest init failed")
    ]
    assert db.get_track(track_id).analyses == ["sonara"]


def test_multi_model_track_batch_and_inference_batch_are_independent(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for name in ["a.wav", "b.wav", "c.wav", "d.wav", "e.wav"]:
        _track(db, tmp_path, name)
    decoder = DecodeRecorder()
    created: list[tuple[str, str, int, int]] = []
    runners: dict[str, FakeModelRunner] = {}

    def runner_factory(model: str, device: str, inference_batch_size: int, top_k: int):
        created.append((model, device, inference_batch_size, top_k))
        runner = FakeModelRunner(model)
        runners[model] = runner
        return runner

    manager = AnalysisJobManager(db, runner_factory=runner_factory, decode_audio=decoder, track_batch_size=2, inference_batch_size=9)

    status = manager.run_sync(models=["mert"], device="cpu", top_k=5, track_batch_size=2, inference_batch_size=9)

    assert status.track_batch_size == 2
    assert status.inference_batch_size == 9
    assert status.batch_size == 2
    assert status.workers == 2
    assert created == [("mert", "cpu", 9, 5)]
    assert runners["mert"].calls == [["a.wav", "b.wav"], ["c.wav", "d.wav"], ["e.wav"]]
