from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_features import SonaraBatchMetrics, sonara_analysis_signatures_for_outputs


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
            analysis_signature=sonara_analysis_signatures_for_outputs(["core"])["core"],
        )
    elif model == "maest":
        db.save_genres(track_id, [{"label": "Techno", "score": 0.9}], model_name="fake-maest")
        db.save_embedding(track_id, np.asarray([1.0, 0.0], dtype=np.float32), "fake-maest", embedding_key="maest")
    else:
        db.save_embedding(track_id, np.asarray([1.0, 0.0], dtype=np.float32), f"fake-{model}", embedding_key=model)


class FakeModelRunner:
    def __init__(self, model: str, *, fail_names: set[str] | None = None) -> None:
        self.model = model
        self.model_name = f"fake-{model}"
        self.device = "cpu"
        self.calls: list[list[str]] = []
        self.fail_names = fail_names or set()

    def analyze_batch(self, db: LibraryDatabase, items):
        names = [Path(item.track.path).name for item in items]
        self.calls.append(names)
        if self.model == "sonara":
            results: list[Exception | None] = []
            for item, name in zip(items, names):
                if name in self.fail_names:
                    results.append(RuntimeError("native failure"))
                else:
                    _mark_analyzed(db, item.track.id, self.model)
                    results.append(None)
            return results
        if any(name in self.fail_names for name in names):
            raise RuntimeError(f"{self.model} failed")
        for item in items:
            _mark_analyzed(db, item.track.id, self.model)
        return None


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


def test_analysis_job_rejects_mixing_sonara_with_ml_and_sonara_outputs_on_ml(tmp_path: Path) -> None:
    manager = AnalysisJobManager(LibraryDatabase(tmp_path / "library.sqlite"), model_runners={})
    with pytest.raises(ValueError, match="SONARA analysis must run alone"):
        manager.run_sync(models=["sonara", "mert"], device="cpu")
    with pytest.raises(ValueError, match="SONARA outputs can only"):
        manager.run_sync(models=["mert"], sonara_outputs=["timeline"], device="cpu")
    with pytest.raises(TypeError, match="classifier_keys"):
        manager.run_sync(models=["mert"], classifier_keys=["break_energy"])


def test_ml_job_selects_only_missing_models_and_decodes_once_per_track(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    missing_mert = _track(db, tmp_path, "a-missing-mert.wav")
    missing_maest = _track(db, tmp_path, "b-missing-maest.wav")
    complete = _track(db, tmp_path, "c-complete.wav")
    _mark_analyzed(db, missing_mert, "maest")
    _mark_analyzed(db, missing_maest, "mert")
    for model in ("maest", "mert"):
        _mark_analyzed(db, complete, model)
    runners = {model: FakeModelRunner(model) for model in ("maest", "mert")}
    decoder = DecodeRecorder()

    status = AnalysisJobManager(db, model_runners=runners, decode_audio=decoder).run_sync(
        models=["maest", "mert"], device="cpu", track_batch_size=2
    )

    assert status.state == "completed"
    assert status.total == status.processed == status.analyzed == 2
    assert decoder.calls == ["a-missing-mert.wav", "b-missing-maest.wav"]
    assert runners["maest"].calls == [["b-missing-maest.wav"]]
    assert runners["mert"].calls == [["a-missing-mert.wav"]]


def test_ml_per_file_failure_is_scoped_and_other_models_continue(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a-good.wav")
    _track(db, tmp_path, "b-bad.wav")
    runners = {
        "maest": FakeModelRunner("maest", fail_names={"b-bad.wav"}),
        "mert": FakeModelRunner("mert"),
    }

    status = AnalysisJobManager(db, model_runners=runners, decode_audio=DecodeRecorder()).run_sync(
        models=["maest", "mert"], device="cpu", track_batch_size=2
    )

    assert status.state == "completed"
    assert (status.analyzed, status.failed) == (1, 1)
    assert status.model_progress["maest"].failed == 1
    assert status.model_progress["mert"].analyzed == 2
    assert [(error.model, Path(error.path).name) for error in status.errors] == [("maest", "b-bad.wav")]


def test_ml_runner_initialization_failure_is_fatal_stage_error(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a.wav")

    def runner_factory(model, device, inference_batch_size, top_k, sonara_outputs=()):
        del device, inference_batch_size, top_k, sonara_outputs
        if model == "maest":
            raise RuntimeError("maest init failed")
        return FakeModelRunner(model)

    status = AnalysisJobManager(db, runner_factory=runner_factory, decode_audio=DecodeRecorder()).run_sync(
        models=["maest", "mert"], device="cpu"
    )

    assert status.state == "failed"
    assert any("initialization failed" in event.message for event in status.events)


def test_native_sonara_uses_own_batch_size_and_never_calls_ffmpeg_decoder(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for name in ("a.wav", "b.wav", "c.wav", "d.wav", "e.wav"):
        _track(db, tmp_path, name)
    runner = FakeModelRunner("sonara")
    decoder = DecodeRecorder()

    status = AnalysisJobManager(db, model_runners={"sonara": runner}, decode_audio=decoder).run_sync(
        models=["sonara"], sonara_batch_size=2, track_batch_size=1
    )

    assert status.state == "completed"
    assert status.sonara_batch_size == 2
    assert status.workers == 2
    assert status.events[0].message == "SONARA queued · outputs Core · batch 2"
    assert "Inference batch" not in status.events[0].message
    assert runner.calls == [["a.wav", "b.wav"], ["c.wav", "d.wav"], ["e.wav"]]
    assert decoder.calls == []


def test_native_sonara_default_chunks_paths_at_8(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for index in range(9):
        _track(db, tmp_path, f"track-{index:02d}.wav")
    runner = FakeModelRunner("sonara")

    status = AnalysisJobManager(db, model_runners={"sonara": runner}).run_sync(models=["sonara"])

    assert status.state == "completed"
    assert [len(batch) for batch in runner.calls] == [8, 1]


def test_native_sonara_rejects_batch_size_above_16(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "one.wav")

    with pytest.raises(ValueError, match="sonara_batch_size must be between 1 and 16"):
        AnalysisJobManager(db, model_runners={"sonara": FakeModelRunner("sonara")}).create_job(
            models=["sonara"], sonara_batch_size=17
        )


def test_native_sonara_failure_result_is_per_file_without_retry(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a-good.wav")
    _track(db, tmp_path, "b-bad.wav")
    runner = FakeModelRunner("sonara", fail_names={"b-bad.wav"})

    status = AnalysisJobManager(db, model_runners={"sonara": runner}).run_sync(
        models=["sonara"], sonara_batch_size=16
    )

    assert status.state == "completed"
    assert (status.analyzed, status.failed) == (1, 1)
    assert runner.calls == [["a-good.wav", "b-bad.wav"]]
    assert status.errors[0].model == "sonara"


def test_native_sonara_emits_analysis_prepare_and_store_timings(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "one.wav")

    class TimedRunner(FakeModelRunner):
        last_metrics = None

        def analyze_batch(self, db, items):
            results = super().analyze_batch(db, items)
            self.last_metrics = SonaraBatchMetrics(
                track_count=len(items),
                source_bytes=8 * 1024 * 1024,
                analyze_seconds=2.5,
                prepare_seconds=0.1,
                store_seconds=0.25,
            )
            return results

    status = AnalysisJobManager(db, model_runners={"sonara": TimedRunner("sonara")}).run_sync(
        models=["sonara"]
    )

    messages = [event.message for event in status.events]
    assert "SONARA batch: 1 tracks · analyze 2.50s (3.2 MiB/s) · prepare 0.10s · store 0.25s" in messages


def test_native_sonara_cancel_is_observed_between_chunks(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for name in ("a.wav", "b.wav", "c.wav"):
        _track(db, tmp_path, name)
    holder: dict[str, object] = {}

    class CancellingRunner(FakeModelRunner):
        def analyze_batch(self, db, items):
            result = super().analyze_batch(db, items)
            manager = holder["manager"]
            manager.cancel(holder["job_id"])
            return result

    runner = CancellingRunner("sonara")
    manager = AnalysisJobManager(db, model_runners={"sonara": runner})
    job_id = manager.create_job(models=["sonara"], sonara_batch_size=1)
    holder.update(manager=manager, job_id=job_id)

    status = manager.run_job(job_id)

    assert status.state == "cancelled"
    assert runner.calls == [["a.wav"]]


def test_track_and_inference_batch_settings_are_independent_for_ml(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for name in ("a.wav", "b.wav", "c.wav"):
        _track(db, tmp_path, name)
    created: list[tuple[str, str, int, int]] = []
    runners: dict[str, FakeModelRunner] = {}

    def runner_factory(model, device, inference_batch_size, top_k, sonara_outputs=()):
        del sonara_outputs
        created.append((model, device, inference_batch_size, top_k))
        runners[model] = FakeModelRunner(model)
        return runners[model]

    status = AnalysisJobManager(db, runner_factory=runner_factory, decode_audio=DecodeRecorder()).run_sync(
        models=["mert"], device="cpu", top_k=5, track_batch_size=2, inference_batch_size=9
    )

    assert (status.track_batch_size, status.inference_batch_size) == (2, 9)
    assert status.events[0].message == "ML queued · models MERT · Device CPU · Track batch 2 · Inference batch 9"
    assert "SONARA batch" not in status.events[0].message
    assert created == [("mert", "cpu", 9, 5)]
    assert runners["mert"].calls == [["a.wav", "b.wav"], ["c.wav"]]
