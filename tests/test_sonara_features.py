from __future__ import annotations

import base64
import struct
import uuid
from dataclasses import replace

import numpy as np
import pytest

from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
    AnalysisWriteResult,
    SonaraWrite,
)
from dj_track_similarity.sonara_contract import (
    SONARA_EXPECTED_SCHEMA_VERSION,
    SONARA_EXPECTED_VERSION,
    SONARA_OUTPUT_KINDS,
    sonara_requested_features,
    sonara_runtime_contracts,
)
from dj_track_similarity.sonara_features import (
    SonaraBatchMetrics,
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
    __version__ = SONARA_EXPECTED_VERSION
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


class RecordingRepository:
    def __init__(self) -> None:
        self.register_calls: list[tuple[AnalysisOutput, ...]] = []
        self.save_calls: list[tuple[SonaraWrite, ...]] = []

    def register_analysis_outputs(self, outputs):
        selected = tuple(outputs)
        self.register_calls.append(selected)
        return tuple(output.contract_hash for output in selected)

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
            content_generation=1,
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
            "schema_version": SONARA_EXPECTED_SCHEMA_VERSION,
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


def test_default_batch_registers_complete_release_and_writes_core_once() -> None:
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
    assert [output.contract.output_kind for output in repository.register_calls[0]] == [
        "core",
        "timeline",
        "embedding",
        "fingerprint",
    ]
    assert len(repository.save_calls) == 1
    assert len(repository.save_calls[0]) == 2
    assert all(write.timeline is None for write in repository.save_calls[0])
    assert all(write.similarity_embedding is None for write in repository.save_calls[0])
    assert all(write.fingerprint is None for write in repository.save_calls[0])

    call = FakeSonara.calls[-1]
    assert call["paths"] == [candidate.file_path for candidate in candidates]
    assert call["sr"] == 22_050
    assert call["mode"] == "playlist"
    assert (call["bpm_min"], call["bpm_max"]) == (70, 180)
    assert call["vocalness_model"] == "bundled"
    contracts = sonara_runtime_contracts(FakeSonara)
    assert tuple(call["features"]) == sonara_requested_features(
        runtime=contracts.runtime
    )
    assert "vocalness" in call["features"]
    assert "embedding" in call["features"]
    assert "fingerprint" in call["features"]
    assert "instrumentalness" not in call["features"]

    assert len(observed_metrics) == 1
    measurement = observed_metrics[0]
    assert measurement.track_count == 2
    assert measurement.source_bytes == 3_000
    assert measurement.analyze_seconds >= 0
    assert measurement.prepare_seconds >= 0
    assert measurement.store_seconds >= 0


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


def test_all_four_outputs_are_converted_in_one_repository_call() -> None:
    repository = RecordingRepository()
    candidate = _candidate(1)

    result = analyze_and_store_sonara_batch(
        repository,
        [candidate],
        sonara_module=FakeSonara,
        outputs=("core", "timeline", "embedding", "fingerprint"),
    )

    assert result[0].error is None
    assert len(repository.save_calls) == 1
    write = repository.save_calls[0][0]
    assert write.timeline is not None
    assert write.similarity_embedding is not None
    assert write.similarity_embedding.contract.normalization == "none"
    assert write.fingerprint is not None
    assert write.fingerprint.words.tolist() == [1, 2]


def test_output_selection_changes_persistence_not_native_request_or_core() -> None:
    FakeSonara.calls.clear()
    candidate = _candidate(1)
    core_repository = RecordingRepository()
    all_repository = RecordingRepository()

    core_result = analyze_and_store_sonara_batch(
        core_repository,
        [candidate],
        sonara_module=FakeSonara,
        outputs=("core",),
    )
    all_result = analyze_and_store_sonara_batch(
        all_repository,
        [candidate],
        sonara_module=FakeSonara,
        outputs=SONARA_OUTPUT_KINDS,
    )

    contracts = sonara_runtime_contracts(FakeSonara)
    expected_features = sonara_requested_features(runtime=contracts.runtime)
    assert len(FakeSonara.calls) == 2
    assert tuple(FakeSonara.calls[0]["features"]) == expected_features
    assert tuple(FakeSonara.calls[1]["features"]) == expected_features
    assert core_repository.register_calls == all_repository.register_calls

    assert core_result[0].error is None
    assert all_result[0].error is None
    core_write = core_repository.save_calls[0][0]
    all_write = all_repository.save_calls[0][0]
    assert core_write.core_contract == all_write.core_contract == contracts.core
    assert replace(core_write.core, analyzed_at="") == replace(
        all_write.core,
        analyzed_at="",
    )
    assert tuple(output.contract.output_kind for output in core_write.outputs) == (
        "core",
    )
    assert tuple(output.contract.output_kind for output in all_write.outputs) == (
        SONARA_OUTPUT_KINDS
    )


def test_analysis_output_helper_uses_same_runtime_contract_factory() -> None:
    outputs = analysis_outputs_for_sonara_runtime(FakeSonara)
    contracts = sonara_runtime_contracts(FakeSonara)

    assert tuple(output.contract for output in outputs) == contracts.identities


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


def test_representations_alias_is_rejected_before_analysis() -> None:
    repository = RecordingRepository()
    FakeSonara.calls.clear()

    with pytest.raises(ValueError, match="unsupported SONARA output"):
        analyze_and_store_sonara_batch(
            repository,
            [_candidate(1)],
            sonara_module=FakeSonara,
            outputs=("representations",),
        )

    assert repository.register_calls == []
    assert repository.save_calls == []
    assert FakeSonara.calls == []
