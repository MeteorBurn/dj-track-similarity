from pathlib import Path

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


def test_genre_job_saves_maest_genres_without_creating_embeddings(tmp_path: Path) -> None:
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
    assert status.model_name == "fake-maest"
    assert status.device == "cpu"
    assert track.genres == ["Techno", "Dub Techno"]
    assert len(db.list_tracks(with_embeddings=True)) == 0


def test_genre_limit_counts_tracks_without_maest_genres(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    analyzed_id = _track(db, tmp_path, "a.wav")
    _track(db, tmp_path, "b.wav")
    _track(db, tmp_path, "c.wav")
    _track(db, tmp_path, "d.wav")
    db.save_genres(analyzed_id, [{"label": "House", "score": 0.8}], model_name="fake-maest")
    adapter = FakeGenreAdapter()
    manager = GenreAnalysisJobManager(db, {"maest": lambda device=None, top_k=3: adapter})

    status = manager.run_sync(limit=2, device="cpu", top_k=1)

    assert status.total == 2
    assert status.analyzed == 2
    assert adapter.paths == ["b.wav", "c.wav"]


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
