import json
from pathlib import Path
import wave

import numpy as np

from dj_track_similarity.audio_loader import DecodedAudio
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_features import (
    analyze_and_store_sonara_features,
    analyze_and_store_sonara_features_from_audio,
    analyze_sonara_features_from_audio,
)


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
            "beats": [1, 2, 3],
            "onset_frames": [1, 4, 8],
            "onset_density": 2.4,
            "n_beats": 3,
            "rms_mean": 0.21,
            "rms_max": 0.83,
            "loudness_lufs": -9.4,
            "dynamic_range_db": 11.2,
            "spectral_centroid_mean": 3200.0,
            "zero_crossing_rate": 0.08,
            "duration_sec": 183.5,
            "chord_sequence": ["Am", "F", "C", "G"],
            "predominant_chord": "Am",
            "chord_change_rate": 0.43,
            "dissonance": 0.18,
            "spectral_bandwidth_mean": 2110.0,
            "spectral_rolloff_mean": 6400.0,
            "spectral_flatness_mean": 0.06,
            "spectral_contrast_mean": np.array([12.0, 10.0, 8.0, 7.0, 6.0, 5.0, 4.0], dtype=np.float32),
            "mfcc_mean": np.array([1.0, 2.0, 3.0], dtype=np.float32),
            "chroma_mean": np.array([0.1, 0.2], dtype=np.float32),
            "tempo_curve": [126.0, 127.0],
            "time_signature": "4/4",
        }

    @staticmethod
    def load(path: str, sr: int = 22050):
        return np.ones(22050, dtype=np.float32), sr

    @staticmethod
    def analyze_signal(y, sr: int = 22050, mode: str = "playlist"):
        assert sr == 22050
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
    assert track.musical_key == "A minor"
    assert track.energy == 0.74
    assert track.analyses == ["sonara"]
    assert "camelot_key" not in track.metadata["sonara_features"]
    assert track.metadata["sonara_features"]["key"]["value"] == "A minor"
    assert track.metadata["sonara_features"]["danceability"]["value"] == 0.68
    assert "description" not in track.metadata["sonara_features"]["onset_density"]
    assert "chord_sequence" not in track.metadata["sonara_features"]
    assert track.metadata["sonara_features"]["mfcc_mean"]["summary"]["mean"] == 2.0
    assert list(track.metadata["sonara_features"]) == [
        "bpm",
        "beats",
        "onset_frames",
        "onset_density",
        "n_beats",
        "rms_mean",
        "rms_max",
        "loudness_lufs",
        "dynamic_range_db",
        "spectral_centroid_mean",
        "zero_crossing_rate",
        "duration_sec",
        "energy",
        "danceability",
        "valence",
        "acousticness",
        "key",
        "key_confidence",
        "predominant_chord",
        "chord_change_rate",
        "dissonance",
        "spectral_bandwidth_mean",
        "spectral_rolloff_mean",
        "spectral_flatness_mean",
        "spectral_contrast_mean",
        "mfcc_mean",
        "chroma_mean",
    ]
    with db.connect() as connection:
        metadata_json = connection.execute("SELECT metadata_json FROM tracks WHERE id = ?", (track_id,)).fetchone()["metadata_json"]
    stored_features = json.loads(metadata_json)["sonara_features"]
    assert list(stored_features) == list(track.metadata["sonara_features"])
    assert "detect_time_signature" not in track.metadata["sonara_features"]
    assert "requested_feature_count" not in track.metadata["sonara_features"]
    assert "tempo_curve" not in track.metadata["sonara_features"]
    assert "yin" not in track.metadata["sonara_features"]
    assert all(
        payload.get("type") != "unavailable"
        for payload in track.metadata["sonara_features"].values()
        if isinstance(payload, dict)
    )
    assert "sonara_features_file" not in track.metadata


def test_analyze_sonara_uses_shared_decoded_audio_without_file_decode(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "Artist - Shared.wav"
    audio_path.write_bytes(b"not decoded by sonara")
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Shared"})
    decoded = DecodedAudio(path=str(audio_path), audio=np.ones(22050, dtype=np.float32), sample_rate=22050, detail="shared")

    result = analyze_and_store_sonara_features_from_audio(
        db,
        db.get_track(track_id),
        decoded,
        sonara_module=FakeSonara,
    )

    track = db.get_track(track_id)
    assert result.elapsed_seconds >= 0
    assert track.bpm == 126.4
    assert track.analyses == ["sonara"]


def test_analyze_sonara_features_from_audio_is_pure_compute() -> None:
    decoded = DecodedAudio(path="shared.wav", audio=np.ones(22050, dtype=np.float32), sample_rate=22050, detail="shared")

    analysis, elapsed = analyze_sonara_features_from_audio(decoded, sonara_module=FakeSonara)

    assert elapsed >= 0
    assert analysis["bpm"] == 126.4
    assert analysis["key"] == "A minor"


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
    assert track.musical_key == "A minor"
    assert track.metadata["sonara_features"]["energy"]["value"] == 0.74
    assert "decode_path" not in track.metadata["sonara_features"]
