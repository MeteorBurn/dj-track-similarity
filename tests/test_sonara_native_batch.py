from __future__ import annotations

import uuid

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
    AnalysisWriteResult,
)
from dj_track_similarity.analysis.sonara_features import (
    analysis_outputs_for_sonara_runtime,
    analyze_and_store_sonara_batch,
)


_BUILD_ID = "sha256:" + "1" * 64
_VOCAL_BUILD_ID = "sha256:" + "2" * 64


class FakeTrackAnalysis(dict):
    @property
    def failed(self) -> bool:
        return "error" in self


class FakeSonara:
    __version__ = "current-test-build"
    SIMILARITY_VERSION = 2
    __sonara_build_id__ = _BUILD_ID
    __sonara_vocalness_model_id__ = "sonara-vocalness-v2"
    __sonara_vocalness_model_build_id__ = _VOCAL_BUILD_ID
    calls: list[dict[str, object]] = []

    @classmethod
    def analyze_batch(cls, paths, **kwargs):
        cls.calls.append({"paths": list(paths), **kwargs})
        results = []
        for path in paths:
            if "analysis-failure" in path:
                results.append(
                    FakeTrackAnalysis(
                        path=path,
                        error="unsupported codec",
                        error_kind="decode",
                    )
                )
                continue
            result = _core_result(path, tuple(kwargs["features"]))
            if "conversion-failure" in path:
                result["mfcc_mean"] = np.zeros(12, dtype=np.float32)
            results.append(result)
        return results


class ResultCountMismatchSonara(FakeSonara):
    @classmethod
    def analyze_batch(cls, paths, **kwargs):
        return []


class RecordingRepository:
    def __init__(
        self,
        *,
        fail_track_id: int | None = None,
        truncate_results: bool = False,
        wrong_target: bool = False,
    ) -> None:
        self.fail_track_id = fail_track_id
        self.truncate_results = truncate_results
        self.wrong_target = wrong_target
        self.register_calls: list[tuple[AnalysisOutput, ...]] = []
        self.save_calls: list[tuple] = []

    def register_analysis_outputs(self, outputs):
        selected = tuple(outputs)
        self.register_calls.append(selected)
        return tuple(
            f"{output.analysis_family}/{output.output_kind}" for output in selected
        )

    def save_sonara_results(self, writes):
        selected = tuple(writes)
        self.save_calls.append(selected)
        results = [
            AnalysisWriteResult(
                target=write.target,
                written_outputs=write.outputs,
                error=(
                    "forced store failure"
                    if write.target.track_id == self.fail_track_id
                    else None
                ),
            )
            for write in selected
        ]
        if self.wrong_target and results:
            wrong = AnalysisTarget(
                catalog_uuid=results[0].target.catalog_uuid,
                track_id=999,
                track_uuid=results[0].target.track_uuid,
            )
            results[0] = AnalysisWriteResult(target=wrong)
        if self.truncate_results and results:
            results.pop()
        return tuple(results)


def _candidate(track_id: int, name: str) -> AnalysisCandidate:
    return AnalysisCandidate(
        target=AnalysisTarget(
            catalog_uuid=str(uuid.UUID(int=1)),
            track_id=track_id,
            track_uuid=str(uuid.UUID(int=100 + track_id)),
        ),
        file_path=f"/music/{name}.wav",
        file_size_bytes=1_000,
        file_modified_ns=10_000,
        missing_outputs=analysis_outputs_for_sonara_runtime(FakeSonara),
    )


def _core_result(path: str, features: tuple[str, ...]) -> FakeTrackAnalysis:
    return FakeTrackAnalysis(
        path=path,
        bpm=128.0,
        bpm_raw=128.0,
        bpm_confidence=0.9,
        duration_sec=60.0,
        energy=0.7,
        beats=np.asarray([0, 22], dtype=np.int64),
        onset_frames=np.asarray([0, 10, 20], dtype=np.int64),
        n_beats=2,
        downbeats=np.asarray([0], dtype=np.int64),
        tempo_curve=np.asarray([128.0], dtype=np.float32),
        energy_curve=np.asarray([0.2, 0.8], dtype=np.float32),
        energy_curve_hop_sec=0.5,
        loudness_curve=np.asarray([-9.0], dtype=np.float32),
        segments=[{"start_sec": 0.0, "end_sec": 60.0, "energy": 0.5}],
        chord_events=[{"label": "Am", "start_sec": 0.0, "end_sec": 60.0}],
        mfcc_mean=np.arange(13, dtype=np.float32),
        chroma_mean=np.arange(12, dtype=np.float32) / 12.0,
        spectral_contrast_mean=np.arange(7, dtype=np.float32) / 7.0,
        embedding=np.linspace(-1.0, 1.0, 48, dtype=np.float32),
        fingerprint="AQAAAAIAAAA=",
        fingerprint_version=1,
        provenance={
            "schema_version": 6,
            "bpm_min": 70.0,
            "bpm_max": 180.0,
            "future_analyzer_parameter": "accepted",
            "sample_rate": 22_050,
            "hop_length": 512,
            "mode": "playlist",
            "requested_features": list(features),
            "vocalness_model_id": "sonara-vocalness-v2",
        },
    )


def test_batch_preserves_per_track_analysis_conversion_and_store_failures() -> None:
    candidates = (
        _candidate(1, "good"),
        _candidate(2, "analysis-failure"),
        _candidate(3, "conversion-failure"),
        _candidate(4, "store-failure"),
    )
    repository = RecordingRepository(fail_track_id=4)

    results = analyze_and_store_sonara_batch(
        repository,
        candidates,
        sonara_module=FakeSonara,
    )

    assert [result.target.track_id for result in results] == [1, 2, 3, 4]
    assert results[0].error is None
    assert "unsupported codec" in str(results[1].error)
    assert "exactly 13" in str(results[2].error)
    assert "forced store failure" in str(results[3].error)
    assert len(repository.save_calls) == 1
    assert [
        write.target.track_id for write in repository.save_calls[0]
    ] == [1, 4]


def test_batch_cardinality_mismatch_is_a_fatal_error() -> None:
    with pytest.raises(RuntimeError, match="result count"):
        analyze_and_store_sonara_batch(
            RecordingRepository(),
            [_candidate(1, "first")],
            sonara_module=ResultCountMismatchSonara,
        )


def test_repository_result_cardinality_mismatch_is_a_fatal_error() -> None:
    with pytest.raises(RuntimeError, match="repository result count"):
        analyze_and_store_sonara_batch(
            RecordingRepository(truncate_results=True),
            [_candidate(1, "first")],
            sonara_module=FakeSonara,
        )


def test_repository_result_for_wrong_target_is_a_fatal_error() -> None:
    with pytest.raises(RuntimeError, match="wrong target"):
        analyze_and_store_sonara_batch(
            RecordingRepository(wrong_target=True),
            [_candidate(1, "first")],
            sonara_module=FakeSonara,
        )
