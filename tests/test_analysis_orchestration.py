from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

from dj_track_similarity import analysis_model_runners as runner_module
from dj_track_similarity.analysis_config import build_analysis_job_config
from dj_track_similarity.analysis_job_batch import AnalysisBatchItem
from dj_track_similarity.analysis_jobs import AnalysisJobManager
from dj_track_similarity.analysis_model_runners import (
    EmbeddingModelRunner,
    MaestModelRunner,
    SonaraModelRunner,
    current_embedding_analysis_output,
    default_model_runners,
)
from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
    AnalysisWriteResult,
    EmbeddingWrite,
    MaestWrite,
    current_embedding_spec,
)
from dj_track_similarity.audio_loader import DecodedAudio
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.embedding import MertEmbeddingAdapter
from dj_track_similarity.genres import MaestGenreAdapter
from dj_track_similarity.maest_windows import MaestWindowContext
from dj_track_similarity.track_models import FileTags, ScannedFile


def _mert_output() -> AnalysisOutput:
    return current_embedding_analysis_output("mert", device="cpu")


def _clap_output() -> AnalysisOutput:
    return current_embedding_analysis_output("clap", device="cpu")


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
        file_path=f"C:/Music/{track_id}.wav",
        file_size_bytes=100 + track_id,
        file_modified_ns=1_000 + track_id,
        missing_outputs=tuple(missing_outputs),
    )


def _decoded(path: str) -> DecodedAudio:
    return DecodedAudio(
        path=path,
        audio=np.asarray([0.0, 0.1], dtype=np.float32),
        sample_rate=24_000,
        detail="test",
    )


@dataclass
class _FakeRepository:
    candidates: list[AnalysisCandidate]
    sonara_count: int = 1
    events: list[tuple[str, object]] = field(default_factory=list)
    active_by_key: dict[tuple[str, str], AnalysisOutput] = field(
        default_factory=dict,
    )

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
        return self.sonara_count

    def list_analysis_candidates(
        self,
        outputs: Sequence[AnalysisOutput],
        *,
        limit: int | None = None,
        require_current_sonara: bool = False,
    ) -> list[AnalysisCandidate]:
        assert self.events and self.events[0][0] == "register"
        self.events.append(
            (
                "candidates",
                (tuple(outputs), limit, require_current_sonara),
            )
        )
        selected = self.candidates if limit is None else self.candidates[:limit]
        return list(selected)

    def save_sonara_results(self, writes):
        raise AssertionError(f"unexpected SONARA writes: {writes!r}")

    def save_maest_results(self, writes):
        raise AssertionError(f"unexpected MAEST writes: {writes!r}")

    def save_embedding_results(self, writes):
        raise AssertionError(f"unexpected embedding writes: {writes!r}")


class _FakeRunner:
    device = "cpu"

    def __init__(
        self,
        model: str,
        outputs: Sequence[AnalysisOutput],
        *,
        errors: Sequence[Exception | None] | None = None,
        preflight_error: Exception | None = None,
    ) -> None:
        self.model = model
        self.model_name = f"test-{model}"
        self.active_outputs = tuple(outputs)
        self.candidate_outputs = tuple(outputs)
        self._errors = None if errors is None else tuple(errors)
        self._preflight_error = preflight_error
        self.preflight_calls = 0
        self.items: list[AnalysisBatchItem] = []

    def preflight(self) -> None:
        self.preflight_calls += 1
        if self._preflight_error is not None:
            raise self._preflight_error

    def analyze_batch(self, _repository, items):
        self.items.extend(items)
        if self._errors is None:
            return [None] * len(items)
        return self._errors[: len(items)]


def test_job_registers_exact_outputs_before_candidate_selection() -> None:
    mert = _mert_output()
    clap = _clap_output()
    candidate = _candidate(1, (mert, clap))
    repository = _FakeRepository([candidate])
    runners = {
        "mert": _FakeRunner("mert", (mert,)),
        "clap": _FakeRunner("clap", (clap,)),
    }

    status = AnalysisJobManager(
        repository,
        model_runners=runners,
        decode_audio=lambda path: _decoded(str(path)),
    ).run_sync(models=["clap", "mert"], device="cpu")

    assert [event[0] for event in repository.events] == [
        "register",
        "candidates",
    ]
    registered = repository.events[0][1]
    assert isinstance(registered, tuple)
    assert [output.key for output in registered] == [
        ("mert", "embedding"),
        ("clap", "embedding"),
    ]
    assert repository.events[1][1] == (
        (mert, clap),
        None,
        True,
    )
    assert status.state == "completed"
    assert status.total == 1
    assert status.processed == 1
    assert status.analyzed == 1
    assert status.failed == 0
    assert not hasattr(status, "embedding_key")
    assert runners["mert"].items[0].candidate is candidate
    assert runners["clap"].items[0].candidate is candidate


def test_ml_job_is_unavailable_without_current_sonara() -> None:
    repository = _FakeRepository([], sonara_count=0)
    manager = AnalysisJobManager(repository)

    with pytest.raises(
        ValueError,
        match="ML analysis requires at least one track with current SONARA",
    ):
        manager.create_job(models=["mert"], device="cpu")

    assert repository.events == []


def test_per_file_runner_failure_does_not_fail_the_job() -> None:
    output = _mert_output()
    candidates = [_candidate(1, (output,)), _candidate(2, (output,))]
    repository = _FakeRepository(candidates)
    runner = _FakeRunner(
        "mert",
        (output,),
        errors=(None, RuntimeError("stale target")),
    )

    status = AnalysisJobManager(
        repository,
        model_runners={"mert": runner},
        decode_audio=lambda path: _decoded(str(path)),
    ).run_sync(models=["mert"], device="cpu")

    assert status.state == "completed"
    assert status.processed == 2
    assert status.analyzed == 1
    assert status.failed == 1
    assert status.model_progress["mert"].analyzed == 1
    assert status.model_progress["mert"].failed == 1
    assert status.errors[0].track_id == 2
    assert "stale target" in status.errors[0].error


def test_runner_initialization_failure_is_fatal_before_activation() -> None:
    repository = _FakeRepository([])

    def fail_factory(*_args):
        raise RuntimeError("identity is unavailable")

    status = AnalysisJobManager(
        repository,
        runner_factory=fail_factory,
    ).run_sync(models=["mert"], device="cpu")

    assert status.state == "failed"
    assert status.processed == 0
    assert repository.events == []
    assert "identity is unavailable" in status.events[-1].message


def test_ml_runtime_runner_is_reused_after_its_first_successful_preflight() -> None:
    output = _mert_output()
    repository = _FakeRepository([])
    created: list[_FakeRunner] = []

    def factory(model: str, _device: str, _batch_size: int, _top_k: int) -> _FakeRunner:
        assert model == "mert"
        runner = _FakeRunner(model, (output,))
        created.append(runner)
        return runner

    manager = AnalysisJobManager(repository, runner_factory=factory)

    first = manager.run_sync(models=["mert"], device="cpu")
    second = manager.run_sync(models=["mert"], device="cpu")

    assert first.state == second.state == "completed"
    assert len(created) == 1
    assert created[0].preflight_calls == 1


def test_ml_runtime_runner_is_not_reused_across_runtime_settings() -> None:
    output = _mert_output()
    repository = _FakeRepository([])
    created: list[_FakeRunner] = []

    def factory(model: str, _device: str, _batch_size: int, _top_k: int) -> _FakeRunner:
        runner = _FakeRunner(model, (output,))
        created.append(runner)
        return runner

    manager = AnalysisJobManager(repository, runner_factory=factory)

    manager.run_sync(models=["mert"], device="cpu", inference_batch_size=8)
    manager.run_sync(models=["mert"], device="cpu", inference_batch_size=16)

    assert len(created) == 2
    assert [runner.preflight_calls for runner in created] == [1, 1]


def test_model_preflight_failure_preserves_prior_active_output() -> None:
    old_output = _mert_output()
    new_output = AnalysisOutput("mert", "embedding")
    repository = _FakeRepository(
        [],
        active_by_key={old_output.key: old_output},
    )
    runner = _FakeRunner(
        "mert",
        (new_output,),
        preflight_error=RuntimeError("checkpoint SHA-256 mismatch"),
    )

    status = AnalysisJobManager(
        repository,
        model_runners={"mert": runner},
    ).run_sync(models=["mert"], device="cpu")

    assert status.state == "failed"
    assert repository.events == []
    assert (
        repository.active_analysis_output("mert", "embedding")
        is old_output
    )
    assert "preflight failed" in status.events[-1].message
    assert "checkpoint SHA-256 mismatch" in status.events[-1].message


def test_default_ml_runners_declare_current_outputs_before_model_load() -> None:
    runners = [
        default_model_runners(model, "cpu", 2, 3)
        for model in ("maest", "mert", "muq", "clap")
    ]

    assert [runner.model for runner in runners] == [
        "maest",
        "mert",
        "muq",
        "clap",
    ]
    assert {
        runner.model: tuple(output.key for output in runner.active_outputs)
        for runner in runners
    } == {
        "maest": (("maest", "analysis"), ("maest", "embedding")),
        "mert": (("mert", "embedding"),),
        "muq": (("muq", "embedding"),),
        "clap": (("clap", "embedding"),),
    }
    expected_dimensions = {
        "maest": 768,
        "mert": 768,
        "muq": 1024,
        "clap": 512,
    }
    for runner in runners:
        assert getattr(runner.adapter, "_model") is None
        for output in runner.active_outputs:
            if output.output_kind == "embedding":
                spec = current_embedding_spec(output.analysis_family)
                assert spec.dimension == expected_dimensions[output.analysis_family]
                assert spec.normalization == "l2"


def test_cancelled_queued_job_performs_no_repository_work() -> None:
    output = _mert_output()
    repository = _FakeRepository([_candidate(1, (output,))])
    manager = AnalysisJobManager(
        repository,
        model_runners={"mert": _FakeRunner("mert", (output,))},
    )
    job_id = manager.create_job(models=["mert"], device="cpu")

    manager.cancel(job_id)
    status = manager.run_job(job_id)

    assert status.state == "cancelled"
    assert repository.events == []


def test_sonara_runner_exposes_only_core_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = (_sonara_output("core"),)
    monkeypatch.setattr(
        runner_module,
        "analysis_outputs_for_sonara_runtime",
        lambda _module=None: outputs,
    )

    runner = SonaraModelRunner(sonara_module=object())

    assert [output.key for output in runner.active_outputs] == [("sonara", "core")]
    assert [output.key for output in runner.candidate_outputs] == [("sonara", "core")]
    assert not hasattr(build_analysis_job_config(models=["sonara"]), "sonara_outputs")


def _sonara_output(kind: str) -> AnalysisOutput:
    return AnalysisOutput("sonara", kind)


class _FakeMertAdapter(MertEmbeddingAdapter):
    def __init__(self) -> None:
        super().__init__(
            device="cpu",
            window_seconds=5.0,
            max_windows=5,
            inference_batch_size=2,
        )

    def preflight(self) -> None:
        pass

    def embed_decoded_batch(
        self,
        decoded_items: Sequence[DecodedAudio],
    ) -> list[np.ndarray]:
        vector = np.zeros(768, dtype=np.float32)
        vector[0] = 1.0
        return [vector.copy() for _item in decoded_items]


@dataclass
class _EmbeddingWriteRepository:
    writes: tuple[EmbeddingWrite, ...] = ()

    def save_embedding_results(
        self,
        writes: Sequence[EmbeddingWrite],
    ) -> tuple[AnalysisWriteResult, ...]:
        self.writes = tuple(writes)
        return tuple(
            AnalysisWriteResult(
                target=write.target,
                written_outputs=(
                    AnalysisOutput(write.output.family, "embedding"),
                ),
            )
            for write in self.writes
        )


def test_embedding_runner_writes_typed_contract_output_only() -> None:
    runner = EmbeddingModelRunner(
        "mert",
        device="cpu",
        inference_batch_size=2,
        adapter=_FakeMertAdapter(),  # type: ignore[arg-type]
    )
    candidate = _candidate(1, runner.candidate_outputs)
    repository = _EmbeddingWriteRepository()

    results = runner.analyze_batch(
        repository,  # type: ignore[arg-type]
        (
            AnalysisBatchItem(
                candidate=candidate,
                decoded=_decoded(candidate.file_path),
                models=("mert",),
            ),
        ),
    )

    assert results == [None]
    assert len(repository.writes) == 1
    write = repository.writes[0]
    assert write.target == candidate.target
    assert write.output.family == runner.active_outputs[0].analysis_family
    assert write.output.vector.shape == (768,)
    assert np.linalg.norm(write.output.vector) == pytest.approx(1.0)


def test_fresh_current_database_runs_candidate_to_typed_embedding_write(
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    mutation = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / "track.wav"),
            file_size_bytes=128,
            file_modified_ns=1_000,
            audio_format="wav",
            sample_rate_hz=24_000,
            channel_count=2,
            audio_duration_seconds=30.0,
        ),
        tags=FileTags(title="Typed analysis"),
    )
    with database.connect() as connection:
        connection.execute(
            """
            INSERT INTO sonara(
                track_id, content_generation,
                mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                mutation.identity.track_id,
                mutation.identity.content_generation,
                np.zeros(13, dtype="<f4").tobytes(),
                np.zeros(12, dtype="<f4").tobytes(),
                np.zeros(7, dtype="<f4").tobytes(),
                "2026-07-30T00:00:00.000000Z",
            ),
        )
    runner = EmbeddingModelRunner(
        "mert",
        device="cpu",
        inference_batch_size=2,
        adapter=_FakeMertAdapter(),  # type: ignore[arg-type]
    )

    status = AnalysisJobManager(
        database,
        model_runners={"mert": runner},
        decode_audio=lambda path: _decoded(str(path)),
    ).run_sync(models=["mert"], device="cpu")

    assert status.state == "completed"
    assert status.total == 1
    assert status.analyzed == 1
    assert database.list_analysis_candidates(runner.candidate_outputs) == []
    vector = database.read_artifact_embedding(
        family="mert",
        track_id=mutation.identity.track_id,
    )
    assert vector is not None
    assert vector.shape == (768,)
    assert vector[0] == pytest.approx(1.0)


class _FakeMaestAdapter(MaestGenreAdapter):
    _vectors: dict[str, np.ndarray]
    received_window_contexts: tuple[MaestWindowContext | None, ...]

    def __init__(self) -> None:
        super().__init__(
            device="cpu",
            top_k=3,
            inference_batch_size=2,
        )
        self._vectors = {}
        self.received_window_contexts = ()

    def preflight(self) -> None:
        pass

    def predict_decoded_batch(
        self,
        decoded_items: Sequence[DecodedAudio],
        *,
        window_contexts: Sequence[MaestWindowContext | None] | None = None,
    ) -> list[list[dict[str, object]]]:
        self.received_window_contexts = tuple(window_contexts or ())
        for item in decoded_items:
            vector = np.zeros(768, dtype=np.float32)
            vector[:2] = (3.0, 4.0)
            self._vectors[item.path] = vector
        return [[{"label": "Electronic---Breaks", "score": 0.9}] for _item in decoded_items]

    def embedding_for_path(self, path: str) -> np.ndarray | None:
        return self._vectors.get(path)


@dataclass
class _MaestWriteRepository:
    writes: tuple[MaestWrite, ...] = ()

    def save_maest_results(
        self,
        writes: Sequence[MaestWrite],
    ) -> tuple[AnalysisWriteResult, ...]:
        self.writes = tuple(writes)
        return tuple(
            AnalysisWriteResult(
                target=write.target,
                written_outputs=write.outputs,
            )
            for write in self.writes
        )


def test_maest_runner_persists_analysis_and_normalized_embedding_atomically() -> None:
    context = MaestWindowContext(
        leading_silence_seconds=5.0,
        trailing_silence_seconds=10.0,
        intro_end_seconds=40.0,
        outro_start_seconds=170.0,
    )
    adapter = _FakeMaestAdapter()
    runner = MaestModelRunner(
        device="cpu",
        top_k=3,
        inference_batch_size=2,
        adapter=adapter,  # type: ignore[arg-type]
    )
    base_candidate = _candidate(1, (runner.candidate_outputs[1],))
    candidate = AnalysisCandidate(
        target=base_candidate.target,
        file_path=base_candidate.file_path,
        file_size_bytes=base_candidate.file_size_bytes,
        file_modified_ns=base_candidate.file_modified_ns,
        missing_outputs=(runner.candidate_outputs[1],),
        maest_window_context=context,
    )
    repository = _MaestWriteRepository()

    results = runner.analyze_batch(
        repository,  # type: ignore[arg-type]
        (
            AnalysisBatchItem(
                candidate=candidate,
                decoded=_decoded(candidate.file_path),
                models=("maest",),
            ),
        ),
    )

    assert results == [None]
    assert len(repository.writes) == 1
    write = repository.writes[0]
    assert [output.key for output in write.outputs] == [
        ("maest", "analysis"),
        ("maest", "embedding"),
    ]
    assert write.syncopated_rhythm is True
    assert write.embedding is not None
    assert np.linalg.norm(write.embedding.vector) == pytest.approx(1.0)
    assert adapter.received_window_contexts == (context,)
