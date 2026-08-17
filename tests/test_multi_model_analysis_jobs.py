from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from dj_track_similarity.analysis_job_batch import AnalysisBatchItem
from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.analysis_model_runners import (
    MaestModelRunner,
    SonaraModelRunner,
    current_embedding_analysis_output,
)
from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
)
from dj_track_similarity.audio_loader import DecodedAudio
from dj_track_similarity.sonara_staging import (
    SonaraStagingConfig,
    StagedSonaraCandidate,
    StagedSonaraResult,
)
from dj_track_similarity.sonara_features import SonaraBatchMetrics


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
        return tuple(
            f"{output.analysis_family}/{output.output_kind}" for output in selected
        )

    def active_analysis_output(
        self,
        analysis_family: str,
        output_kind: str,
    ) -> AnalysisOutput | None:
        return self.active_by_key.get((analysis_family, output_kind))

    def current_sonara_track_count(self) -> int:
        return 1

    def list_analysis_candidates(
        self,
        outputs: Sequence[AnalysisOutput],
        *,
        limit: int | None = None,
        require_current_sonara: bool = False,
    ) -> list[AnalysisCandidate]:
        self.events.append(
            (
                "candidates",
                (tuple(outputs), limit, require_current_sonara),
            )
        )
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
        self.batch_sizes: list[int] = []

    def preflight(self) -> None:
        if self.preflight_error is not None:
            raise self.preflight_error

    def analyze_batch(
        self,
        _repository: _Repository,
        items: Sequence[AnalysisBatchItem],
    ) -> list[None]:
        self.batch_sizes.append(len(items))
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


def test_sonara_ffmpeg_recovery_is_marked_in_final_track_event() -> None:
    output = AnalysisOutput("sonara", "core")
    runner = _Runner("sonara", output)
    runner.last_ffmpeg_fallback_track_ids = frozenset({1})
    repository = _Repository([_candidate(1, (output,))])

    status = AnalysisJobManager(
        repository,
        model_runners={"sonara": runner},
    ).run_sync(models=("sonara",), device="cpu")

    assert status.state == "completed"
    track_events = [event for event in status.events if event.track_id == 1]
    assert [event.message for event in track_events] == [
        "[ffmpeg] Track analyzed"
    ]


def test_sonara_batch_summary_omits_ffmpeg_fallback_count() -> None:
    output = AnalysisOutput("sonara", "core")

    class _MetricSonaraRunner(_Runner):
        def analyze_batch(self, repository, items):
            results = super().analyze_batch(repository, items)
            self.last_metrics = SonaraBatchMetrics(
                track_count=len(items),
                source_bytes=sum(item.candidate.file_size_bytes for item in items),
                analyze_seconds=1.0,
                prepare_seconds=0.1,
                store_seconds=0.1,
                ffmpeg_fallback_count=1,
            )
            self.last_ffmpeg_fallback_track_ids = frozenset(
                {items[0].candidate.target.track_id}
            )
            return results

    repository = _Repository([_candidate(1, (output,)), _candidate(2, (output,))])
    status = AnalysisJobManager(
        repository,
        model_runners={"sonara": _MetricSonaraRunner("sonara", output)},
    ).run_sync(models=("sonara",), device="cpu")

    batch_events = [event for event in status.events if event.message.startswith("SONARA batch:")]
    assert len(batch_events) == 1
    assert "FFmpeg fallback" not in batch_events[0].message


def test_direct_sonara_uses_configured_batches_while_staged_uses_one_queue(
    tmp_path: Path,
) -> None:
    output = AnalysisOutput("sonara", "core")
    candidates = [_candidate(track_id, (output,)) for track_id in range(1, 6)]

    direct_runner = _Runner("sonara", output)
    direct_status = AnalysisJobManager(
        _Repository(candidates),
        model_runners={"sonara": direct_runner},
    ).run_sync(
        models=("sonara",),
        sonara_mode="direct",
        sonara_batch_size=2,
    )

    staged_runner = _Runner("sonara", output)
    staged_status = AnalysisJobManager(
        _Repository(candidates),
        model_runners={"sonara": staged_runner},
    ).run_sync(
        models=("sonara",),
        sonara_mode="staged",
        sonara_batch_size=4,
        sonara_staging_config=SonaraStagingConfig(root=tmp_path),
    )

    assert direct_status.state == "completed"
    assert direct_runner.batch_sizes == [2, 2, 1]
    assert staged_status.state == "completed"
    assert staged_runner.batch_sizes == [5]


def test_staged_sonara_emits_track_event_before_runner_returns_without_duplicates() -> None:
    observed_during_runner: list[str] = []
    manager: AnalysisJobManager

    class _IncrementalSonaraRunner(SonaraModelRunner):
        def __init__(self) -> None:
            super().__init__(sonara_module=object())

        def analyze_batch(self, repository, items):
            del repository
            self.incremental_results_emitted = True
            assert self.track_result is not None
            item = StagedSonaraCandidate(
                candidate=items[0].candidate,
                source_path=Path(items[0].candidate.file_path),
                path=Path("C:/TracksTemp/staged.wav"),
            )
            self.track_result(StagedSonaraResult(item=item))
            observed_during_runner.extend(
                event.message
                for event in manager.latest().events
                if event.track_id == items[0].candidate.target.track_id
            )
            return [None]

    runner = _IncrementalSonaraRunner()
    repository = _Repository([_candidate(1, runner.active_outputs)])
    manager = AnalysisJobManager(
        repository,
        model_runners={"sonara": runner},
    )

    status = manager.run_sync(models=("sonara",), device="cpu")

    assert observed_during_runner == ["Track analyzed"]
    assert (status.processed, status.analyzed, status.failed) == (1, 1, 0)
    assert [event.message for event in status.events if event.track_id == 1] == [
        "Track analyzed"
    ]
