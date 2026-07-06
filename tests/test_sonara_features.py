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
    file_calls = []
    signal_calls = []

    @classmethod
    def reset(cls):
        cls.file_calls = []
        cls.signal_calls = []

    @staticmethod
    def analyze_file(
        path: str,
        sr: int = 22050,
        mode: str = "playlist",
        *,
        features: list[str] | None = None,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
    ):
        assert mode == "playlist"
        FakeSonara.file_calls.append(
            {
                "path": path,
                "sr": sr,
                "mode": mode,
                "features": list(features) if features is not None else None,
                "bpm_min": bpm_min,
                "bpm_max": bpm_max,
            }
        )
        # sonara 2.0 default playlist output: base fields plus the new default extras
        # (bpm_raw, bpm_candidates, key_camelot) that arrive without any opt-in request.
        analysis = {
            "bpm": 126.4,
            "bpm_raw": 126.4,
            "bpm_candidates": [[126.4, 4.1], [63.2, 3.7], [252.8, 2.9]],
            "key": "A minor",
            "key_camelot": "8A",
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
        # Opt-in families only appear when explicitly requested via features=[...],
        # mirroring sonara 2.0 where features REPLACES the mode preset.
        requested = set(features or ())
        if "structure" in requested:
            analysis.update(
                {
                    "energy_curve": [float(i) / 100.0 for i in range(385)],
                    "energy_curve_hop_sec": 0.51,
                    "energy_level": 9,
                    "intro_end_sec": 14.3,
                    "outro_start_sec": 182.4,
                    "segments": [
                        {"start_sec": 0.0, "end_sec": 26.0, "energy": 0.41},
                        {"start_sec": 26.0, "end_sec": 82.0, "energy": 0.59},
                    ],
                }
            )
        if "loudness" in requested:
            analysis.update(
                {
                    "true_peak_db": 0.19,
                    "replaygain_db": -5.46,
                    "loudness_curve": [-17.0 + float(i) / 100.0 for i in range(195)],
                    "loudness_momentary_max_db": -9.6,
                    "loudness_range_lu": 2.68,
                }
            )
        if "beatgrid" in requested:
            analysis.update(
                {
                    "downbeats": list(range(61, 61 + 104)),
                    "grid_offset_sec": 0.07,
                    "grid_stability": 1.0,
                }
            )
        if "key_candidates" in requested:
            analysis["key_candidates"] = [
                ["A minor", "8A", 0.73],
                ["F major", "7B", 0.72],
                ["C minor", "5A", 0.63],
            ]
        if "vocalness" in requested:
            analysis["vocalness"] = 0.61
        if "silence" in requested:
            analysis.update({"leading_silence_sec": 0.0, "trailing_silence_sec": 7.08})
        return analysis

    @staticmethod
    def load(path: str, sr: int = 22050):
        return np.ones(22050, dtype=np.float32), sr

    @staticmethod
    def analyze_signal(
        y,
        sr: int = 22050,
        mode: str = "playlist",
        *,
        features: list[str] | None = None,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
    ):
        assert sr == 22050
        FakeSonara.signal_calls.append(
            {
                "sr": sr,
                "mode": mode,
                "features": list(features) if features is not None else None,
                "bpm_min": bpm_min,
                "bpm_max": bpm_max,
            }
        )
        return FakeSonara.analyze_file(
            "from-signal", sr=sr, mode=mode, features=features, bpm_min=bpm_min, bpm_max=bpm_max
        )

    @staticmethod
    def melspectrogram(y, sr: float):
        return np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    @staticmethod
    def power_to_db(values):
        return np.asarray(values, dtype=np.float32) - 10


class FakeFallbackSonara(FakeSonara):
    file_calls = []
    signal_calls = []

    @staticmethod
    def analyze_file(
        path: str,
        sr: int = 22050,
        mode: str = "playlist",
        *,
        features: list[str] | None = None,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
    ):
        FakeFallbackSonara.file_calls.append(
            {
                "path": path,
                "sr": sr,
                "mode": mode,
                "features": list(features) if features is not None else None,
                "bpm_min": bpm_min,
                "bpm_max": bpm_max,
            }
        )
        raise OSError("Audio decoding error: Failed to read enough bytes.")

    @staticmethod
    def analyze_signal(
        y,
        sr: int = 22050,
        mode: str = "playlist",
        *,
        features: list[str] | None = None,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
    ):
        assert sr == 22050
        FakeFallbackSonara.signal_calls.append(
            {
                "sr": sr,
                "mode": mode,
                "features": list(features) if features is not None else None,
                "bpm_min": bpm_min,
                "bpm_max": bpm_max,
            }
        )
        return FakeSonara.analyze_file("from-signal", mode=mode, features=features, bpm_min=bpm_min, bpm_max=bpm_max)

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


def test_analyze_and_store_sonara_features_passes_project_bpm_range(tmp_path: Path) -> None:
    FakeSonara.reset()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "Artist - Track.wav"
    _write_wav(audio_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})

    analyze_and_store_sonara_features(
        db,
        db.get_track(track_id),
        sonara_module=FakeSonara,
    )

    assert FakeSonara.file_calls[-1]["bpm_min"] == 79.0
    assert FakeSonara.file_calls[-1]["bpm_max"] == 192.0


def test_analyze_sonara_features_from_audio_passes_project_bpm_range() -> None:
    FakeSonara.reset()
    decoded = DecodedAudio(path="shared.wav", audio=np.ones(22050, dtype=np.float32), sample_rate=22050, detail="shared")

    analyze_sonara_features_from_audio(decoded, sonara_module=FakeSonara)

    assert FakeSonara.signal_calls[-1]["bpm_min"] == 79.0
    assert FakeSonara.signal_calls[-1]["bpm_max"] == 192.0


def test_analyze_sonara_wav_fallback_passes_project_bpm_range(tmp_path: Path) -> None:
    FakeFallbackSonara.reset()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "truncated.wav"
    _write_wav(audio_path)
    original = audio_path.read_bytes()
    audio_path.write_bytes(original[: len(original) // 2])
    db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Broken"})

    analyze_and_store_sonara_features(
        db,
        db.list_tracks()[0],
        sonara_module=FakeFallbackSonara,
    )

    assert FakeFallbackSonara.file_calls[-1]["bpm_min"] == 79.0
    assert FakeFallbackSonara.file_calls[-1]["bpm_max"] == 192.0
    assert FakeFallbackSonara.signal_calls[-1]["bpm_min"] == 79.0
    assert FakeFallbackSonara.signal_calls[-1]["bpm_max"] == 192.0


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
        "bpm_raw",
        "bpm_candidates",
        "key_camelot",
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


def test_default_analysis_requests_no_optin_features_and_stores_no_curves(tmp_path: Path) -> None:
    FakeSonara.reset()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "Artist - Track.wav"
    _write_wav(audio_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})

    analyze_and_store_sonara_features(db, db.get_track(track_id), sonara_module=FakeSonara)

    # No family requested -> sonara runs plain playlist mode (no features kwarg forwarded).
    assert FakeSonara.file_calls[-1]["features"] is None
    features = db.get_track(track_id).metadata["sonara_features"]
    # Default 2.0 extras land in the hot path; opt-in families do not appear.
    assert "key_camelot" in features
    assert "bpm_raw" in features
    assert "bpm_candidates" in features
    for optin in ("energy_curve", "energy_level", "vocalness", "true_peak_db", "grid_stability", "key_candidates"):
        assert optin not in features
    assert db.load_sonara_curves(track_id) is None


def test_optin_families_split_light_into_features_and_curves_out_of_band(tmp_path: Path) -> None:
    FakeSonara.reset()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "Artist - Track.wav"
    _write_wav(audio_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})

    analyze_and_store_sonara_features(
        db,
        db.get_track(track_id),
        sonara_module=FakeSonara,
        feature_families=["structure", "loudness", "beatgrid", "key_candidates", "vocalness", "silence"],
    )

    # sonara features REPLACES the mode preset, so a request must carry the full playlist set
    # plus the requested opt-in families, and must not drop base fields.
    requested = FakeSonara.file_calls[-1]["features"]
    assert requested is not None
    assert "key" in requested and "mfcc" in requested and "chroma" in requested
    for family in ("structure", "loudness", "beatgrid", "key_candidates", "vocalness", "silence"):
        assert family in requested

    features = db.get_track(track_id).metadata["sonara_features"]
    # Light opt-in fields live in the hot-path JSON.
    assert features["energy_level"]["value"] == 9
    assert features["true_peak_db"]["value"] == 0.19
    assert features["grid_stability"]["value"] == 1.0
    assert features["vocalness"]["value"] == 0.61
    assert features["leading_silence_sec"]["value"] == 0.0
    assert features["key_candidates"]["length"] == 3
    assert features["segments"]["length"] == 2
    # Heavy curves are NOT in the hot-path JSON.
    for curve in ("energy_curve", "loudness_curve", "downbeats"):
        assert curve not in features

    # Heavy curves are stored whole (not truncated) in the out-of-band table.
    curves = db.load_sonara_curves(track_id)
    assert curves is not None
    assert len(curves["energy_curve"]["value"]) == 385
    assert len(curves["loudness_curve"]["value"]) == 195
    assert len(curves["downbeats"]["value"]) == 104


def test_reset_sonara_clears_curves_table(tmp_path: Path) -> None:
    FakeSonara.reset()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "Artist - Track.wav"
    _write_wav(audio_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})

    analyze_and_store_sonara_features(
        db, db.get_track(track_id), sonara_module=FakeSonara, feature_families=["structure"]
    )
    assert db.load_sonara_curves(track_id) is not None

    db.reset_analysis("sonara")

    assert db.load_sonara_curves(track_id) is None
    assert db.get_track(track_id).metadata.get("sonara_features") is None
