from pathlib import Path

import numpy as np

from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.genre_jobs import GenreAnalysisJobManager


def _track(db: LibraryDatabase, tmp_path: Path, name: str) -> int:
    path = tmp_path / name
    path.write_bytes(b"RIFF0000WAVE")
    return db.upsert_track(path=path, size=path.stat().st_size, mtime=path.stat().st_mtime, metadata={"title": name})


class FakeGenreAdapter:
    model_name = "fake-maest"
    device = "cpu"

    def __init__(self, device=None, top_k=3) -> None:
        self.device = device or "auto"
        self.top_k = top_k
        self.paths: list[str] = []

    def predict(self, path):
        self.paths.append(Path(path).name)
        return [
            {"label": "Techno", "score": 0.9},
            {"label": "Dub Techno", "score": 0.7},
        ][: self.top_k]

    def embedding_for_path(self, path):
        value = float(len(Path(path).name))
        return np.asarray([value, 1.0, 0.5], dtype=np.float32)


class BatchGenreAdapter:
    model_name = "batch-maest"
    device = "cuda"

    def __init__(self, device="auto", top_k=3) -> None:
        self.device_requested = device
        self.top_k = top_k
        self.batches: list[list[str]] = []
        self.predict_calls: list[str] = []

    def predict_batch(self, paths):
        self.batches.append([Path(path).name for path in paths])
        return [[{"label": f"Genre {index}", "score": 0.9}] for index, _path in enumerate(paths)]

    def predict(self, path):
        self.predict_calls.append(Path(path).name)
        raise AssertionError("MAEST batch job should call predict_batch")

    def embedding_for_path(self, path):
        value = float(len(Path(path).name))
        return np.asarray([value, 1.0, 0.5], dtype=np.float32)


class PartlyFailingBatchGenreAdapter:
    model_name = "batch-maest"
    device = "cpu"

    def __init__(self) -> None:
        self.batches: list[list[str]] = []

    def predict_batch(self, paths):
        names = [Path(path).name for path in paths]
        self.batches.append(names)
        if "bad.wav" in names:
            raise RuntimeError(f"Unable to decode audio: {paths[names.index('bad.wav')]}")
        return [[{"label": f"Genre {name}", "score": 0.9}] for name in names]

    def embedding_for_path(self, path):
        value = float(len(Path(path).name))
        return np.asarray([value, 1.0, 0.5], dtype=np.float32)


def test_genre_job_saves_maest_genres_and_embeddings(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_id = _track(db, tmp_path, "one.wav")
    manager = GenreAnalysisJobManager(db, {"maest": FakeGenreAdapter})

    status = manager.run_sync(limit=1, device="cpu", top_k=2)

    track = db.get_track(track_id)
    assert status.state == "completed"
    assert status.total == 1
    assert status.processed == 1
    assert status.analyzed == 1
    assert status.failed == 0
    assert status.embedding_key == "maest"
    assert status.model_name == "fake-maest"
    assert status.device == "cpu"
    assert track.genres == ["Techno", "Dub Techno"]
    tracks, matrix = db.load_embedding_matrix("maest")
    assert [track.id for track in tracks] == [track_id]
    assert matrix.shape == (1, 3)


def test_genre_limit_counts_tracks_without_maest_embeddings(monkeypatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    genre_only_id = _track(db, tmp_path, "a.wav")
    embedding_only_id = _track(db, tmp_path, "b.wav")
    _track(db, tmp_path, "c.wav")
    _track(db, tmp_path, "d.wav")
    db.save_genres(genre_only_id, [{"label": "House", "score": 0.8}], model_name="fake-maest")
    db.save_embedding(
        embedding_only_id,
        np.asarray([1.0, 0.0, 0.0], dtype=np.float32),
        "fake-maest",
        embedding_key="maest",
    )
    adapter = FakeGenreAdapter()
    manager = GenreAnalysisJobManager(db, {"maest": lambda device=None, top_k=3: adapter})

    def fail_if_full_track_scan(**_kwargs):
        raise AssertionError("genre job creation must use SQL-level missing MAEST selection")

    monkeypatch.setattr(db, "list_tracks", fail_if_full_track_scan)

    status = manager.run_sync(limit=2, device="cpu", top_k=1)

    assert status.total == 2
    assert status.analyzed == 2
    assert adapter.paths == ["a.wav", "c.wav"]


def test_genre_job_runs_maest_in_batches_and_records_progress(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    _track(db, tmp_path, "a.wav")
    _track(db, tmp_path, "b.wav")
    _track(db, tmp_path, "c.wav")
    adapter = BatchGenreAdapter(device="cpu", top_k=2)
    manager = GenreAnalysisJobManager(db, {"maest": lambda **kwargs: adapter})

    status = manager.run_sync(device="cpu", top_k=2, batch_size=2)

    assert status.state == "completed"
    assert status.total == 3
    assert status.processed == 3
    assert status.analyzed == 3
    assert status.failed == 0
    assert status.device_requested == "cpu"
    assert status.device == "cuda"
    assert status.top_k == 2
    assert status.batch_size == 2
    assert status.workers == 2
    assert adapter.batches == [["a.wav", "b.wav"], ["c.wav"]]
    assert adapter.predict_calls == []
    tracks = db.list_tracks()
    assert tracks[0].genres == ["Genre 0"]
    assert tracks[1].genres == ["Genre 1"]
    assert tracks[2].genres == ["Genre 0"]


def test_genre_job_retries_failed_maest_batch_per_track(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    good_a = _track(db, tmp_path, "a-good.wav")
    bad = _track(db, tmp_path, "bad.wav")
    good_b = _track(db, tmp_path, "c-good.wav")
    adapter = PartlyFailingBatchGenreAdapter()
    manager = GenreAnalysisJobManager(db, {"maest": lambda **kwargs: adapter})

    status = manager.run_sync(device="cpu", batch_size=3)

    assert status.state == "completed"
    assert status.processed == 3
    assert status.analyzed == 2
    assert status.failed == 1
    assert [(error.track_id, Path(error.path).name) for error in status.errors] == [(bad, "bad.wav")]
    assert db.get_track(good_a).genres == ["Genre a-good.wav"]
    assert db.get_track(bad).genres is None
    assert db.get_track(good_b).genres == ["Genre c-good.wav"]
    assert adapter.batches == [["a-good.wav", "bad.wav", "c-good.wav"], ["a-good.wav"], ["bad.wav"], ["c-good.wav"]]
