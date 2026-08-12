from __future__ import annotations

import base64
import logging
import struct
import uuid

import numpy as np
import dj_track_similarity.sonara_features as sonara_features_module

from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
    AnalysisWriteResult,
    SonaraWrite,
)
from dj_track_similarity.sonara_runtime import (
    SONARA_CORE_REQUESTED_FEATURES,
    sonara_requested_features,
)
from dj_track_similarity.sonara_features import (
    SonaraBatchMetrics,
    analyze_sonara_genre_batch,
    analysis_outputs_for_sonara_runtime,
    analyze_and_store_sonara_batch,
)


_BUILD_ID = "sha256:" + "1" * 64
_VOCAL_BUILD_ID = "sha256:" + "2" * 64


class TrackAnalysis(dict):
    @property
    def failed(self) -> bool:
        return "error" in self


class FakeSonara:
    __version__ = "arbitrary-future-release"
    SIMILARITY_VERSION = 2
    __sonara_build_id__ = _BUILD_ID
    __sonara_vocalness_model_id__ = "sonara-vocalness-v2"
    __sonara_vocalness_model_build_id__ = _VOCAL_BUILD_ID
    calls: list[dict[str, object]] = []

    @classmethod
    def analyze_batch(cls, paths, **kwargs):
        cls.calls.append({"paths": list(paths), **kwargs})
        return [
            _raw_analysis(path, features=tuple(kwargs["features"])) for path in paths
        ]


class BoundarySonara(FakeSonara):
    @classmethod
    def analyze_batch(cls, paths, **kwargs):
        cls.calls.append({"paths": list(paths), **kwargs})
        results = [
            _raw_analysis(path, features=tuple(kwargs["features"])) for path in paths
        ]
        results[0]["energy"] = np.float32(1.001)
        results[1]["energy"] = np.nextafter(
            np.float32(1.001),
            np.float32(np.inf),
        )
        return results


class GenreSonara(FakeSonara):
    @classmethod
    def analyze_batch(cls, paths, **kwargs):
        results = super().analyze_batch(paths, **kwargs)
        for result in results:
            result["genre"] = "broken"
            result["genre_confidence"] = 0.75
        return results


class FallbackSonara(FakeSonara):
    signal_calls: list[dict[str, object]] = []
    resample_calls: list[dict[str, object]] = []

    @classmethod
    def analyze_batch(cls, paths, **kwargs):
        cls.calls.append({"paths": list(paths), **kwargs})
        return [
            TrackAnalysis(path=path, error_kind="decode", error="native decoder rejected input")
            for path in paths
        ]

    @classmethod
    def resample(cls, audio, *, orig_sr, target_sr):
        cls.resample_calls.append(
            {"audio": audio, "orig_sr": orig_sr, "target_sr": target_sr}
        )
        return audio

    @classmethod
    def analyze_signal(cls, audio, **kwargs):
        cls.signal_calls.append({"audio": audio, **kwargs})
        return _raw_analysis("ffmpeg-pcm", features=tuple(kwargs["features"]))


class RecordingRepository:
    def __init__(self) -> None:
        self.register_calls: list[tuple[AnalysisOutput, ...]] = []
        self.save_calls: list[tuple[SonaraWrite, ...]] = []

    def register_analysis_outputs(self, outputs):
        selected = tuple(outputs)
        self.register_calls.append(selected)
        return tuple(
            f"{output.analysis_family}/{output.output_kind}" for output in selected
        )

    def save_sonara_results(self, writes):
        selected = tuple(writes)
        self.save_calls.append(selected)
        return tuple(
            AnalysisWriteResult(
                target=write.target,
                written_outputs=write.outputs,
            )
            for write in selected
        )


def _candidate(index: int) -> AnalysisCandidate:
    outputs = analysis_outputs_for_sonara_runtime(FakeSonara)
    return AnalysisCandidate(
        target=AnalysisTarget(
            catalog_uuid=str(uuid.UUID(int=1)),
            track_id=index,
            track_uuid=str(uuid.UUID(int=100 + index)),
        ),
        file_path=f"/music/track-{index}.wav",
        file_size_bytes=1_000 * index,
        file_modified_ns=10_000 * index,
        missing_outputs=outputs,
    )


def _raw_analysis(path: str, *, features: tuple[str, ...]) -> TrackAnalysis:
    result = TrackAnalysis(
        path=path,
        bpm=126.4,
        bpm_raw=126.4,
        bpm_confidence=0.88,
        energy=0.74,
        duration_sec=180.0,
        key="A minor",
        key_camelot="8A",
        mfcc_mean=np.arange(13, dtype=np.float32),
        chroma_mean=np.arange(12, dtype=np.float32) / 12.0,
        spectral_contrast_mean=np.arange(7, dtype=np.float32) / 7.0,
        energy_curve=np.asarray([0.2, 0.5, 0.8], dtype=np.float32),
        energy_curve_hop_sec=0.5,
        beats=np.asarray([0, 22, 43], dtype=np.int64),
        n_beats=3,
        provenance={
            "future_analyzer_parameter": "accepted",
            "sample_rate": 22_050,
            "hop_length": 512,
            "mode": "playlist",
            "requested_features": list(features),
            "vocalness_model_id": "sonara-vocalness-v2",
        },
    )
    if any(
        feature in features
        for feature in (
            "onsets",
            "chords",
            "tempo_curve",
            "beatgrid",
            "structure",
            "loudness",
        )
    ):
        result.update(
            onset_frames=np.asarray([0, 10], dtype=np.int64),
            chord_sequence=["Am", "F"],
            chord_events=[{"label": "Am", "start_sec": 0.0, "end_sec": 8.0}],
            tempo_curve=np.asarray([126.4, 126.5], dtype=np.float32),
            downbeats=np.asarray([0, 43], dtype=np.int64),
            segments=[{"start_sec": 0.0, "end_sec": 16.0, "energy": 0.5}],
            loudness_curve=np.asarray([-10.0, -9.0], dtype=np.float32),
        )
    if "embedding" in features:
        result["embedding"] = np.linspace(0.05, 0.95, 48, dtype=np.float32)
        result["embedding_version"] = 2
    if "fingerprint" in features:
        result["fingerprint"] = base64.b64encode(struct.pack("<2I", 1, 2)).decode(
            "ascii"
        )
        result["fingerprint_version"] = 1
    return result


def test_default_batch_requests_registers_and_writes_core_with_embedding() -> None:
    FakeSonara.calls.clear()
    repository = RecordingRepository()
    candidates = (_candidate(1), _candidate(2))
    observed_metrics: list[SonaraBatchMetrics] = []

    results = analyze_and_store_sonara_batch(
        repository,
        candidates,
        sonara_module=FakeSonara,
        metrics=observed_metrics.append,
    )

    assert [result.target.track_id for result in results] == [1, 2]
    assert all(result.error is None for result in results)
    assert len(repository.register_calls) == 1
    assert [output.output_kind for output in repository.register_calls[0]] == [
        "core",
        "embedding",
    ]
    assert len(repository.save_calls) == 1
    assert len(repository.save_calls[0]) == 2
    assert all(not hasattr(write, "timeline") for write in repository.save_calls[0])
    assert all(write.embedding is not None for write in repository.save_calls[0])
    assert all(write.embedding.vector.shape == (48,) for write in repository.save_calls[0])
    assert all(not hasattr(write, "fingerprint") for write in repository.save_calls[0])

    call = FakeSonara.calls[-1]
    assert call["paths"] == [candidate.file_path for candidate in candidates]
    assert call["sr"] == 22_050
    assert call["mode"] == "playlist"
    assert (call["bpm_min"], call["bpm_max"]) == (70, 180)
    assert call["vocalness_model"] == "bundled"
    assert tuple(call["features"]) == (*SONARA_CORE_REQUESTED_FEATURES, "embedding")
    assert tuple(call["features"]) == sonara_requested_features()
    assert "vocalness" in call["features"]
    assert "aggression" in call["features"]
    assert "embedding" in call["features"]
    assert "fingerprint" not in call["features"]
    assert "instrumentalness" not in call["features"]

    assert len(observed_metrics) == 1
    measurement = observed_metrics[0]
    assert measurement.track_count == 2
    assert measurement.source_bytes == 3_000
    assert measurement.analyze_seconds >= 0
    assert measurement.prepare_seconds >= 0
    assert measurement.store_seconds >= 0


def test_sonara_genre_batch_requests_native_embedding_and_returns_scores() -> None:
    GenreSonara.calls.clear()
    candidates = (_candidate(1), _candidate(2))

    results = analyze_sonara_genre_batch(
        candidates,
        genre_model_path="C:/models/break-energy.json",
        sonara_module=GenreSonara,
    )

    assert [result.target.track_id for result in results] == [1, 2]
    assert [(result.label, result.confidence) for result in results] == [
        ("broken", 0.75),
        ("broken", 0.75),
    ]
    call = GenreSonara.calls[-1]
    assert tuple(call["features"]) == ("embedding",)
    assert call["genre_model"] == "C:/models/break-energy.json"


def test_batch_clamps_float32_boundary_and_isolates_outside_epsilon_error() -> None:
    BoundarySonara.calls.clear()
    repository = RecordingRepository()

    results = analyze_and_store_sonara_batch(
        repository,
        (_candidate(1), _candidate(2)),
        sonara_module=BoundarySonara,
    )

    assert results[0].error is None
    assert results[1].error is not None
    assert "allowed epsilon" in str(results[1].error)
    assert len(repository.save_calls) == 1
    assert len(repository.save_calls[0]) == 1
    assert repository.save_calls[0][0].target.track_id == 1
    assert repository.save_calls[0][0].core.energy_score == 1.0


def test_batch_recovers_native_sonara_failure_with_ffmpeg_pcm_and_logs(
    monkeypatch,
    caplog,
) -> None:
    FallbackSonara.calls.clear()
    FallbackSonara.signal_calls.clear()
    FallbackSonara.resample_calls.clear()
    repository = RecordingRepository()
    decoded_pcm = np.asarray([0.1, -0.2, 0.3], dtype=np.float32)
    monkeypatch.setattr(
        sonara_features_module,
        "load_audio_mono_with_ffmpeg",
        lambda path: (decoded_pcm, 44_100, "ffmpeg decode (arithmetic channel mean)"),
    )

    with caplog.at_level(logging.WARNING, logger="dj_track_similarity.sonara_features"):
        results = analyze_and_store_sonara_batch(
            repository,
            (_candidate(1),),
            sonara_module=FallbackSonara,
        )

    assert results[0].error is None
    assert results[0].used_ffmpeg_fallback
    assert len(repository.save_calls[0]) == 1
    assert FallbackSonara.resample_calls == [
        {"audio": decoded_pcm, "orig_sr": 44_100, "target_sr": 22_050}
    ]
    assert len(FallbackSonara.signal_calls) == 1
    signal_call = FallbackSonara.signal_calls[0]
    assert signal_call["sr"] == 22_050
    assert signal_call["mode"] == "playlist"
    assert tuple(signal_call["features"]) == (
        *SONARA_CORE_REQUESTED_FEATURES,
        "embedding",
    )
    assert "SONARA analysis recovered through FFmpeg PCM fallback" in caplog.text
    assert "native decoder rejected input" in caplog.text


def test_analysis_output_helper_is_unversioned_and_ignores_runtime_metadata() -> None:
    outputs = analysis_outputs_for_sonara_runtime(FakeSonara)

    assert tuple(output.key for output in outputs) == (
        ("sonara", "core"),
        ("sonara", "embedding"),
    )


def test_empty_batch_performs_no_runtime_or_repository_work() -> None:
    repository = RecordingRepository()
    FakeSonara.calls.clear()

    assert (
        analyze_and_store_sonara_batch(
            repository,
            [],
            sonara_module=FakeSonara,
        )
        == []
    )
    assert repository.register_calls == []
    assert repository.save_calls == []
    assert FakeSonara.calls == []
