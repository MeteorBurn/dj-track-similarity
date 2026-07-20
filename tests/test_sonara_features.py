import json
from pathlib import Path
import wave

import numpy as np
import pytest

from dj_track_similarity.audio_loader import DecodedAudio
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.sonara_contract import SONARA_ANALYSIS_SIGNATURE_KEY, sonara_analysis_signature_errors
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
        vocalness_model: str | None = None,
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
                "vocalness_model": vocalness_model,
            }
        )
        # SONARA default playlist output: base fields plus extras that arrive without opt-in.
        analysis = {
            "bpm": 126.4,
            "bpm_raw": 126.4,
            "bpm_confidence": 0.88,
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
            "chord_events": [
                {"label": "Am", "start_sec": 0.0, "end_sec": 46.0},
                {"label": "F", "start_sec": 46.0, "end_sec": 92.0},
            ],
            "predominant_chord": "Am",
            "chord_change_rate": 0.43,
            "dissonance": 0.18,
            "spectral_bandwidth_mean": 2110.0,
            "spectral_rolloff_mean": 6400.0,
            "spectral_flatness_mean": 0.06,
            "spectral_contrast_mean": np.array([12.0, 10.0, 8.0, 7.0, 6.0, 5.0, 4.0], dtype=np.float32),
            "mfcc_mean": np.array([1.0, 2.0, 3.0], dtype=np.float32),
            "chroma_mean": np.array([0.1, 0.2], dtype=np.float32),
        }
        # Opt-in families only appear when explicitly requested via features=[...],
        # mirroring sonara 2.0 where features REPLACES the mode preset.
        requested = set(features or ())
        analysis["provenance"] = {
            "schema_version": 4,
            "sample_rate": sr,
            "hop_length": 512,
            "mode": mode,
            **({"requested_features": sorted(requested)} if features is not None else {}),
            **({"vocalness_model_id": "sonara-vocalness-v2"} if vocalness_model == "bundled" else {}),
        }
        if "tempo_curve" in requested:
            analysis.update({"tempo_curve": [126.0, 127.0], "tempo_variability": 0.04})
        if "time_signature" in requested:
            analysis.update({"time_signature": "4/4", "time_signature_confidence": 0.91})
        if "embedding" in requested:
            analysis.update({"embedding": [float(index) / 47.0 for index in range(48)], "embedding_version": 2})
        if "fingerprint" in requested:
            analysis.update({"fingerprint": "AQIDBAUGBwg=", "fingerprint_version": 1})
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
        if "mood" in requested:
            analysis.update(
                {
                    "mood_happy": 0.71,
                    "mood_aggressive": 0.30,
                    "mood_relaxed": 0.55,
                    "mood_sad": 0.12,
                }
            )
        if "instrumentalness" in requested:
            analysis["instrumentalness"] = 0.39
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
        vocalness_model: str | None = None,
    ):
        assert sr == 22050
        FakeSonara.signal_calls.append(
            {
                "sr": sr,
                "mode": mode,
                "features": list(features) if features is not None else None,
                "bpm_min": bpm_min,
                "bpm_max": bpm_max,
                "vocalness_model": vocalness_model,
            }
        )
        return FakeSonara.analyze_file(
            "from-signal",
            sr=sr,
            mode=mode,
            features=features,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            vocalness_model=vocalness_model,
        )

    @staticmethod
    def melspectrogram(y, sr: float):
        return np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    @staticmethod
    def power_to_db(values):
        return np.asarray(values, dtype=np.float32) - 10


class FakeCurrentSonara(FakeSonara):
    __version__ = "0.2.9"


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
        vocalness_model: str | None = None,
    ):
        FakeFallbackSonara.file_calls.append(
            {
                "path": path,
                "sr": sr,
                "mode": mode,
                "features": list(features) if features is not None else None,
                "bpm_min": bpm_min,
                "bpm_max": bpm_max,
                "vocalness_model": vocalness_model,
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
        vocalness_model: str | None = None,
    ):
        assert sr == 22050
        FakeFallbackSonara.signal_calls.append(
            {
                "sr": sr,
                "mode": mode,
                "features": list(features) if features is not None else None,
                "bpm_min": bpm_min,
                "bpm_max": bpm_max,
                "vocalness_model": vocalness_model,
            }
        )
        return FakeSonara.analyze_file(
            "from-signal",
            mode=mode,
            features=features,
            bpm_min=bpm_min,
            bpm_max=bpm_max,
            vocalness_model=vocalness_model,
        )

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

    assert FakeSonara.file_calls[-1]["bpm_min"] == 70.0
    assert FakeSonara.file_calls[-1]["bpm_max"] == 180.0


def test_analyze_sonara_features_from_audio_passes_project_bpm_range() -> None:
    FakeSonara.reset()
    decoded = DecodedAudio(path="shared.wav", audio=np.ones(22050, dtype=np.float32), sample_rate=22050, detail="shared")

    analyze_sonara_features_from_audio(decoded, sonara_module=FakeSonara)

    assert FakeSonara.signal_calls[-1]["bpm_min"] == 70.0
    assert FakeSonara.signal_calls[-1]["bpm_max"] == 180.0


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

    assert FakeFallbackSonara.file_calls[-1]["bpm_min"] == 70.0
    assert FakeFallbackSonara.file_calls[-1]["bpm_max"] == 180.0
    assert FakeFallbackSonara.signal_calls[-1]["bpm_min"] == 70.0
    assert FakeFallbackSonara.signal_calls[-1]["bpm_max"] == 180.0


def test_analyze_and_store_sonara_features_writes_metadata_and_json_dump(tmp_path: Path) -> None:
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "Artist - Track.wav"
    _write_wav(audio_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})

    result = analyze_and_store_sonara_features(
        db,
        db.get_track(track_id),
        sonara_module=FakeCurrentSonara,
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
    assert {
        "bpm",
        "onset_density",
        "rms_mean",
        "energy",
        "key",
        "spectral_contrast_mean",
        "mfcc_mean",
        "chroma_mean",
        "vocalness",
        "time_signature",
        "energy_curve_summary",
    }.issubset(track.metadata["sonara_features"])
    assert track.metadata["sonara_features"]["spectral_contrast_mean"]["value"] == pytest.approx(
        [12.0, 10.0, 8.0, 7.0, 6.0, 5.0, 4.0]
    )
    assert track.metadata["sonara_features"]["mfcc_mean"]["value"] == pytest.approx([1.0, 2.0, 3.0])
    assert track.metadata["sonara_features"]["chroma_mean"]["value"] == pytest.approx([0.1, 0.2])
    assert not {"beats", "onset_frames", "chord_sequence", "segments", "embedding", "fingerprint"}.intersection(
        track.metadata["sonara_features"]
    )
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
        sonara_module=FakeCurrentSonara,
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


def test_default_analysis_writes_only_core_output(tmp_path: Path) -> None:
    FakeSonara.reset()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "Artist - Track.wav"
    _write_wav(audio_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})

    analyze_and_store_sonara_features(db, db.get_track(track_id), sonara_module=FakeCurrentSonara)

    requested = FakeSonara.file_calls[-1]["features"]
    assert requested is not None
    assert "key" in requested and "mfcc" in requested and "vocalness" in requested
    assert "embedding" not in requested and "fingerprint" not in requested
    assert FakeSonara.file_calls[-1]["vocalness_model"] == "bundled"
    features = db.get_track(track_id).metadata["sonara_features"]
    assert "key_camelot" in features
    assert "bpm_raw" in features
    assert features["bpm_confidence"]["value"] == 0.88
    assert "bpm_candidates" in features
    assert db.get_track(track_id).metadata["sonara_provenance"] == {
        "schema_version": 4,
        "sample_rate": 22050,
        "hop_length": 512,
        "mode": "playlist",
        "requested_features": sorted(requested),
        "vocalness_model_id": "sonara-vocalness-v2",
        "package_version": "0.2.9",
    }
    signature = db.get_track(track_id).metadata[SONARA_ANALYSIS_SIGNATURE_KEY]
    assert signature["sonara_version"] == "0.2.9"
    assert signature["schema_version"] == 4
    assert signature["bpm_range"] == [70, 180]
    assert signature["project_feature_revision"] == 2
    assert "embedding" not in signature["requested_features"]
    assert sonara_analysis_signature_errors(signature) == ()
    assert db.load_sonara_timeline(track_id) is None
    assert db.embedding_vector(track_id, "sonara") is None
    stored_track = db.get_track(track_id)
    assert stored_track.timeline_fields is None
    assert stored_track.representation_fields is None


def test_all_outputs_split_core_timeline_and_representations_across_databases(tmp_path: Path) -> None:
    FakeSonara.reset()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "Artist - Track.wav"
    _write_wav(audio_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})

    analyze_and_store_sonara_features(
        db,
        db.get_track(track_id),
        sonara_module=FakeCurrentSonara,
        outputs=["core", "timeline", "representations"],
    )

    requested = FakeSonara.file_calls[-1]["features"]
    assert requested is not None
    assert "key" in requested and "mfcc" in requested and "chroma" in requested
    for archival in ("tempo_curve", "time_signature", "embedding", "fingerprint"):
        assert archival in requested
    assert FakeSonara.file_calls[-1]["vocalness_model"] == "bundled"

    features = db.get_track(track_id).metadata["sonara_features"]
    # Light opt-in fields live in the hot-path JSON.
    assert features["energy_level"]["value"] == 9
    assert features["true_peak_db"]["value"] == 0.19
    assert features["replaygain_db"]["value"] == -5.46
    assert features["grid_stability"]["value"] == 1.0
    assert features["vocalness"]["value"] == 0.61
    assert features["mood_happy"]["value"] == 0.71
    assert features["mood_aggressive"]["value"] == 0.30
    assert features["mood_relaxed"]["value"] == 0.55
    assert features["mood_sad"]["value"] == 0.12
    assert features["instrumentalness"]["value"] == 0.39
    assert features["tempo_variability"]["value"] == 0.04
    assert features["time_signature"]["value"] == "4/4"
    assert features["time_signature_confidence"]["value"] == 0.91
    assert features["leading_silence_sec"]["value"] == 0.0
    assert features["key_candidates"]["length"] == 3
    assert features["energy_curve_summary"]["value"] is None
    assert features["energy_curve_summary"]["summary"]["mean"] == pytest.approx(1.92)
    for curve in ("energy_curve", "loudness_curve", "downbeats", "segments", "embedding", "fingerprint"):
        assert curve not in features

    timeline = db.load_sonara_timeline(track_id)
    assert timeline is not None
    assert len(timeline["energy_curve"]["value"]) == 385
    assert len(timeline["loudness_curve"]["value"]) == 195
    assert len(timeline["downbeats"]["value"]) == 104
    assert timeline["beats"]["value"] == [1, 2, 3]
    assert timeline["chord_events"]["value"][0]["label"] == "Am"
    assert timeline["tempo_curve"]["value"] == [126.0, 127.0]
    assert db.embedding_vector(track_id, "sonara") == pytest.approx(
        [float(index) / 47.0 for index in range(48)]
    )
    stored_track = db.get_track(track_id)
    assert stored_track.timeline_fields == sorted(timeline)
    assert stored_track.representation_fields == ["embedding", "fingerprint"]
    with db.connect() as connection:
        fingerprint = json.loads(
            connection.execute(
                "SELECT payload_json FROM representations.fingerprints WHERE track_id = ?",
                (track_id,),
            ).fetchone()["payload_json"]
        )
    assert fingerprint["value"] == "AQIDBAUGBwg="


def test_reset_sonara_clears_all_three_output_stores(tmp_path: Path) -> None:
    FakeSonara.reset()
    db = LibraryDatabase(tmp_path / "library.sqlite")
    audio_path = tmp_path / "Artist - Track.wav"
    _write_wav(audio_path)
    track_id = db.upsert_track(path=audio_path, size=audio_path.stat().st_size, mtime=1, metadata={"title": "Track"})

    analyze_and_store_sonara_features(
        db,
        db.get_track(track_id),
        sonara_module=FakeCurrentSonara,
        outputs=["core", "timeline", "representations"],
    )
    assert db.load_sonara_timeline(track_id) is not None
    assert db.embedding_vector(track_id, "sonara") is not None

    db.reset_analysis("sonara")

    assert db.load_sonara_timeline(track_id) is None
    assert db.embedding_vector(track_id, "sonara") is None
    assert db.get_track(track_id).timeline_fields is None
    assert db.get_track(track_id).representation_fields is None
    metadata = db.get_track(track_id).metadata
    assert metadata.get("sonara_features") is None
    assert metadata.get("sonara_provenance") is None
    assert metadata.get(SONARA_ANALYSIS_SIGNATURE_KEY) is None
