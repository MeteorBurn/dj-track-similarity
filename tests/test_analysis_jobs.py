from pathlib import Path

import numpy as np

from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.database import LibraryDatabase


def _track(db: LibraryDatabase, tmp_path: Path, name: str) -> int:
    path = tmp_path / name
    path.write_bytes(b"RIFF0000WAVE")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=path.stat().st_mtime, metadata={"title": name})


class BatchAdapter:
    model_name = "batch-model"
    dim = 3
    device = "cuda"

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def embed_batch(self, paths):
        self.batches.append([Path(path).name for path in paths])
        return [np.array([index + 1, 1, 1], dtype=np.float32) for index, _ in enumerate(paths)]

    def embed(self, path):
        return self.embed_batch([path])[0]


class FailingAdapter:
    model_name = "failing-model"
    dim = 3
    device = "cpu"

    def embed(self, path):
        if Path(path).name == "bad.wav":
            raise RuntimeError("decode failed")
        return np.array([1, 2, 3], dtype=np.float32)


class LazyDeviceAdapter:
    model_name = "lazy-device-model"
    dim = 3
    device = None

    def embed_batch(self, paths):
        self.device = "cuda"
        return [np.array([1, 0, 0], dtype=np.float32) for _ in paths]

    def embed(self, path):
        return self.embed_batch([path])[0]


def test_analysis_job_runs_in_batches_and_records_progress(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a.wav")
    _track(db, tmp_path, "b.wav")
    _track(db, tmp_path, "c.wav")
    adapter = BatchAdapter()
    manager = AnalysisJobManager(db, {"batch": lambda: adapter}, batch_size=2)

    status = manager.run_sync(adapter_name="batch")

    assert status.state == "completed"
    assert status.total == 3
    assert status.processed == 3
    assert status.analyzed == 3
    assert status.failed == 0
    assert status.device == "cuda"
    assert status.model_name == "batch-model"
    assert status.avg_seconds_per_track is not None
    assert status.events[0].message == "Analysis queued"
    assert any(event.level == "ok" and event.path.endswith("a.wav") for event in status.events)
    assert status.events[-1].message == "Analysis completed"
    assert adapter.batches == [["a.wav", "b.wav"], ["c.wav"]]
    assert len(db.list_tracks(with_embeddings=True)) == 3


def test_analysis_job_uses_requested_worker_count_as_batch_size(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a.wav")
    _track(db, tmp_path, "b.wav")
    _track(db, tmp_path, "c.wav")
    adapter = BatchAdapter()
    manager = AnalysisJobManager(db, {"batch": lambda: adapter}, batch_size=1)

    status = manager.run_sync(adapter_name="batch", workers=3)

    assert status.workers == 3
    assert adapter.batches == [["a.wav", "b.wav", "c.wav"]]


def test_analysis_job_records_per_track_errors_without_stopping(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "good.wav")
    _track(db, tmp_path, "bad.wav")
    manager = AnalysisJobManager(db, {"failing": FailingAdapter}, batch_size=1)

    status = manager.run_sync(adapter_name="failing")

    assert status.state == "completed"
    assert status.processed == 2
    assert status.analyzed == 1
    assert status.failed == 1
    assert status.errors[0].path.endswith("bad.wav")
    assert "decode failed" in status.errors[0].error
    assert any(event.level == "error" and event.path.endswith("bad.wav") for event in status.events)
    assert len(db.list_tracks(with_embeddings=True)) == 1


def test_analysis_job_can_be_cancelled_before_work_starts(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "one.wav")
    manager = AnalysisJobManager(db, {"batch": BatchAdapter}, batch_size=2)
    job_id = manager.create_job(adapter_name="batch")

    manager.cancel(job_id)
    status = manager.run_job(job_id)

    assert status.state == "cancelled"
    assert status.processed == 0
    assert status.analyzed == 0


def test_analysis_job_updates_device_after_lazy_adapter_loads(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "one.wav")
    adapter = LazyDeviceAdapter()
    manager = AnalysisJobManager(db, {"lazy": lambda: adapter}, batch_size=1)

    status = manager.run_sync(adapter_name="lazy")

    assert status.state == "completed"
    assert status.device == "cuda"
