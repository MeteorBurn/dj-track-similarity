from pathlib import Path
import threading
import time
import wave

import numpy as np
from fastapi.testclient import TestClient

import dj_track_similarity.api as api
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.key_utils import camelot_key_from_sonara_analysis
from dj_track_similarity.sonara_features import analyze_and_store_sonara_features
from dj_track_similarity.sonara_jobs import SonaraFeatureJobManager


class FakeSonara:
    __version__ = "0.test"

    @staticmethod
    def analyze_file(path: str, sr: int = 22050, mode: str = "playlist"):
        assert mode == "playlist"
        return {
            "bpm": 126.4,
            "key": "A minor",
            "key_confidence": 0.82,
            "energy": 0.74,
            "danceability": 0.68,
            "valence": 0.31,
            "acousticness": 0.12,
            "loudness_lufs": -9.4,
            "dynamic_range_db": 11.2,
            "duration_sec": 183.5,
            "mfcc_mean": np.array([1.0, 2.0, 3.0], dtype=np.float32),
            "chroma_mean": np.array([0.1, 0.2], dtype=np.float32),
        }

    @staticmethod
    def load(path: str, sr: int = 22050):
        return np.ones(22050, dtype=np.float32), sr

    @staticmethod
    def analyze_signal(y, sr: int = 22050, mode: str = "playlist"):
        return FakeSonara.analyze_file("from-signal", sr=sr, mode=mode)

    @staticmethod
    def melspectrogram(y, sr: float):
        return np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    @staticmethod
    def power_to_db(values):
        return np.asarray(values, dtype=np.float32) - 10


class FakeFallbackSonara(FakeSonara):
    @staticmethod
    def analyze_file(path: str, sr: int = 22050, mode: str = "playlist"):
        raise OSError("Audio decoding error: Failed to read enough bytes.")

    @staticmethod
    def analyze_signal(y, sr: int = 22050, mode: str = "playlist"):
        assert sr == 22050
        return FakeSonara.analyze_file("from-signal", mode=mode)

    @staticmethod
    def resample(y, *, orig_sr: int, target_sr: int):
        assert target_sr == 22050
        return np.asarray(y, dtype=np.float32)[::2]


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(22050)
        audio.writeframes(b"\x00\x00" * 22050)


def test_analyze_and_store_sonara_features_writes_metadata_and_json_dump(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "Artist - Track.wav"
    _write_wav(audio_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})

    result = analyze_and_store_sonara_features(
        db,
        db.get_track(track_id),
        sonara_module=FakeSonara,
    )

    track = db.get_track(track_id)
    assert result.elapsed_seconds >= 0
    assert track.bpm == 126.4
    assert track.musical_key == "8A"
    assert track.energy == 0.74
    assert track.analyses == ["sonara"]
    assert track.metadata["sonara_features"]["camelot_key"]["value"] == "8A"
    assert track.metadata["sonara_features"]["camelot_key"]["source_feature"] == "key"
    assert track.metadata["sonara_features"]["key"]["value"] == "A minor"
    assert track.metadata["sonara_features"]["danceability"]["value"] == 0.68
    assert track.metadata["sonara_features"]["mfcc_mean"]["summary"]["mean"] == 2.0
    assert track.metadata["sonara_features"]["detect_time_signature"]["type"] == "unavailable"
    assert "sonara_features_file" not in track.metadata


class SynchronousSonaraManager:
    last_batch_size = None

    def __init__(self, db, *args, **kwargs):
        self.db = db

    def start(self, *, limit=None, batch_size=1):
        type(self).last_batch_size = batch_size
        tracks = self.db.list_tracks()
        if limit is not None:
            tracks = tracks[:limit]
        for track in tracks:
            analyze_and_store_sonara_features(self.db, track, sonara_module=FakeSonara)
        return {
            "job_id": "sonara-job-1",
            "state": "completed",
            "adapter_name": "sonara",
            "embedding_key": "sonara",
            "model_name": "sonara-playlist-lab",
            "device": "cpu",
            "device_requested": "cpu",
            "total": len(tracks),
            "processed": len(tracks),
            "analyzed": len(tracks),
            "failed": 0,
            "current_path": None,
            "started_at": 1,
            "finished_at": 2,
            "avg_seconds_per_track": 1,
            "errors": [],
            "events": [],
            "cancel_requested": False,
            "workers": batch_size,
            "batch_size": batch_size,
        }

    def latest(self):
        return None

    def get(self, job_id):
        raise KeyError(job_id)

    def cancel(self, job_id):
        raise KeyError(job_id)


def test_api_runs_sonara_analysis_and_returns_track_features(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "library.sqlite"
    audio_path = tmp_path / "track.wav"
    _write_wav(audio_path)
    db = LibraryDatabase(db_path)
    db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})
    monkeypatch.setattr(api, "SonaraFeatureJobManager", SynchronousSonaraManager)

    client = TestClient(api.create_app(db_path))
    response = client.post("/api/sonara/analyze", json={"limit": 1, "batch_size": 3})

    assert response.status_code == 200
    assert response.json()["adapter_name"] == "sonara"
    assert response.json()["batch_size"] == 3
    assert response.json()["workers"] == 3
    assert SynchronousSonaraManager.last_batch_size == 3
    tracks = client.get("/api/tracks").json()
    assert tracks[0]["bpm"] == 126.4
    assert tracks[0]["musical_key"] == "8A"
    assert tracks[0]["analyses"] == ["sonara"]
    assert tracks[0]["metadata"]["sonara_features"]["camelot_key"]["value"] == "8A"
    assert tracks[0]["metadata"]["sonara_features"]["key"]["description"] == "Analyzed musical key, independent of file tags."


def test_analyze_sonara_falls_back_to_signal_for_truncated_wav(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "truncated.wav"
    _write_wav(audio_path)
    original = audio_path.read_bytes()
    audio_path.write_bytes(original[: len(original) // 2])
    db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Broken"})

    result = analyze_and_store_sonara_features(
        db,
        db.list_tracks()[0],
        sonara_module=FakeFallbackSonara,
    )
    track = db.list_tracks()[0]

    assert result.elapsed_seconds >= 0
    assert track.bpm == 126.4
    assert track.musical_key == "8A"
    assert "tolerant WAV fallback" in track.metadata["sonara_features"]["decode_path"]["value"]


def test_sonara_limit_counts_tracks_without_sonara_features(monkeypatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    track_ids = []
    for name in ["a.wav", "b.wav", "c.wav", "d.wav"]:
        audio_path = tmp_path / name
        _write_wav(audio_path)
        track_ids.append(
            db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": name})
        )
    db.save_sonara_features(track_ids[0], {"bpm": {"value": 120}}, model_name="sonara-test")
    processed: list[str] = []

    def fake_analyze(db, track):
        processed.append(Path(track.path).name)
        db.save_sonara_features(track.id, {"bpm": {"value": 121}}, model_name="sonara-test")

    monkeypatch.setattr("dj_track_similarity.sonara_jobs.analyze_and_store_sonara_features", fake_analyze)

    status = SonaraFeatureJobManager(db).run_sync(limit=2)

    assert status.total == 2
    assert status.analyzed == 2
    assert processed == ["b.wav", "c.wav"]


def test_sonara_batch_size_runs_tracks_in_parallel(monkeypatch, tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    for name in ["a.wav", "b.wav", "c.wav"]:
        audio_path = tmp_path / name
        _write_wav(audio_path)
        db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": name})
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_analyze(db, track):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        db.save_sonara_features(track.id, {"bpm": {"value": 121}}, model_name="sonara-test")
        with lock:
            active -= 1

    monkeypatch.setattr("dj_track_similarity.sonara_jobs.analyze_and_store_sonara_features", fake_analyze)

    status = SonaraFeatureJobManager(db).run_sync(batch_size=2)

    assert status.state == "completed"
    assert status.total == 3
    assert status.analyzed == 3
    assert status.workers == 2
    assert status.batch_size == 2
    assert max_active == 2


def test_sonara_key_conversion_to_camelot_uses_tonal_fields() -> None:
    assert camelot_key_from_sonara_analysis({"key": "A minor"}) == "8A"
    assert camelot_key_from_sonara_analysis({"key": "C major"}) == "8B"
    assert camelot_key_from_sonara_analysis({"key": "Bb minor"}) == "3A"
    assert camelot_key_from_sonara_analysis({"key": "F# major"}) == "2B"
    assert camelot_key_from_sonara_analysis({"key_detection": "D#m"}) == "2A"
    assert camelot_key_from_sonara_analysis({"predominant_chord": "G:maj"}) == "9B"
    assert camelot_key_from_sonara_analysis({"camelot_key": "08a", "key": "C major"}) == "8A"
