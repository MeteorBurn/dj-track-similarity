from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np

from dj_track_similarity.analysis_job_batch import AnalysisBatchItem
from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.analysis_model_runners import (
    MaestModelRunner,
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
)
from dj_track_similarity.audio_loader import DecodedAudio


def _mert_output() -> AnalysisOutput:
    return current_embedding_analysis_output("mert")


def _maest_output() -> AnalysisOutput:
    return MaestModelRunner(
        device="cpu",
        top_k=3,
        inference_batch_size=1,
    ).active_outputs[1]


def _candidate(
    track_id: int,
    missing_outputs: Sequence[AnalysisOutput],
) -> AnalysisCandidate:
    return AnalysisCandidate(
        target=AnalysisTarget(
            catalog_uuid="catalog-test",
            track_id=track_id,
            track_uuid=f"track-{track_id}",
            content_generation=1,
        ),
        file_path=f"C:/music/{track_id}.wav",
        file_size_bytes=100 + track_id,
        file_modified_ns=1_000 + track_id,
        missing_outputs=tuple(missing_outputs),
    )


@dataclass
class _Repository:
    candidates: list[AnalysisCandidate]
    active_by_key: dict[tuple[str, str], AnalysisOutput] = field(default_factory=dict)
    events: list[tuple[str, object]] = field(default_factory=list)

    def register_analysis_outputs(
        self,
        outputs: Sequence[AnalysisOutput],
    ) -> tuple[str, ...]:
        selected = tuple(outputs)
        self.events.append(("register", selected))
        self.active_by_key.update({output.key: output for output in selected})
        return tuple(output.contract_hash for output in selected)

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        return self.active_by_key.get((analysis_family, output_kind))

    def list_analysis_candidates(
        self,
        outputs: Sequence[AnalysisOutput],
        *,
        limit: int | None = None,
    ) -> list[AnalysisCandidate]:
        self.events.append(("candidates", (tuple(outputs), limit)))
        if limit is None:
            return list(self.candidates)
        return list(self.candidates[:limit])


class _Runner:
    device = "cpu"

    def __init__(
        self,
        model: str,
        output: AnalysisOutput,
        *,
        preflight_error: Exception | None = None,
    ) -> None:
        self.model = model
        self.model_name = f"test-{model}"
        self.active_outputs = (output,)
        self.candidate_outputs = (output,)
        self.preflight_error = preflight_error
        self.items: list[AnalysisBatchItem] = []

    def preflight(self) -> None:
        if self.preflight_error is not None:
            raise self.preflight_error

    def analyze_batch(
        self,
        _repository: _Repository,
        items: Sequence[AnalysisBatchItem],
    ) -> list[None]:
        self.items.extend(items)
        return [None] * len(items)


def _decoded(path: str) -> DecodedAudio:
    return DecodedAudio(
        path=path,
        audio=np.asarray([0.0, 0.1], dtype=np.float32),
        sample_rate=24_000,
        detail="test",
    )


def test_multi_model_job_aggregates_exact_missing_outputs_per_track() -> None:
    mert = _mert_output()
    maest = _maest_output()
    repository = _Repository(
        [
            _candidate(1, (mert, maest)),
            _candidate(2, (mert,)),
        ]
    )
    runners = {
        "mert": _Runner("mert", mert),
        "maest": _Runner("maest", maest),
    }
    decoded_paths: list[str] = []

    def decode(path: str) -> DecodedAudio:
        decoded_paths.append(str(path))
        return _decoded(str(path))

    status = AnalysisJobManager(
        repository,
        model_runners=runners,
        decode_audio=decode,
    ).run_sync(
        models=("maest", "mert"),
        device="cpu",
        track_batch_size=2,
    )

    assert status.state == "completed"
    assert (status.total, status.processed, status.analyzed, status.failed) == (
        2,
        2,
        2,
        0,
    )
    assert status.model_progress["mert"].analyzed == 2
    assert status.model_progress["maest"].analyzed == 1
    assert [item.candidate.target.track_id for item in runners["mert"].items] == [
        1,
        2,
    ]
    assert [item.candidate.target.track_id for item in runners["maest"].items] == [1]
    assert decoded_paths == ["C:/music/1.wav", "C:/music/2.wav"]
    assert [event[0] for event in repository.events] == [
        "register",
        "candidates",
    ]


def test_multi_model_preflight_failure_keeps_active_contract_pointer() -> None:
    old_mert = _mert_output()
    new_maest = _maest_output()
    repository = _Repository(
        [],
        active_by_key={old_mert.key: old_mert},
    )
    runner = _Runner(
        "maest",
        new_maest,
        preflight_error=RuntimeError("checkpoint SHA-256 mismatch"),
    )

    status = AnalysisJobManager(
        repository,
        model_runners={"maest": runner},
    ).run_sync(models=("maest",), device="cpu")

    assert status.state == "failed"
    assert repository.active_by_key[old_mert.key] == old_mert
    assert new_maest.key not in repository.active_by_key
    assert repository.events == []
    assert "checkpoint SHA-256 mismatch" in status.events[-1].message
