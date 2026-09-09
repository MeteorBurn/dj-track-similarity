from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
import gc
from pathlib import Path
import threading
import weakref

import numpy as np
import pytest

from dj_track_similarity.analysis import model_runners as runner_module
from dj_track_similarity.analysis.config import build_analysis_job_config
from dj_track_similarity.analysis.job_batch import AnalysisBatchItem, DecodeFailure
from dj_track_similarity.analysis.jobs import AnalysisJobManager
from dj_track_similarity.analysis.ml_staging import MLStagingConfig, MLStagingSession
from dj_track_similarity.analysis.queue import AnalysisStageQueue
from dj_track_similarity.analysis.model_runners import (
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
from dj_track_similarity.audio.loader import DecodedAudio
from dj_track_similarity.database import LibraryDatabase
from dj_track_similarity.db.embeddings import read_valid_embeddings
from dj_track_similarity.embedding.contracts import EmbeddingCancelledError
from dj_track_similarity.embedding.clap import ClapEmbeddingAdapter
from dj_track_similarity.embedding.maest import MaestAnalysisResult
from dj_track_similarity.embedding.maest import MaestEmbeddingAdapter
from dj_track_similarity.embedding.mert import MertEmbeddingAdapter
from dj_track_similarity.embedding.mulan import MuqMulanEmbeddingAdapter
from dj_track_similarity.track_models import FileTags, ScannedFile, TrackIdentity


def _mert_output() -> AnalysisOutput:
    return current_embedding_analysis_output("mert", device="cpu")


def _clap_output() -> AnalysisOutput:
    return current_embedding_analysis_output("clap", device="cpu")


def _stored_embedding(
    database: LibraryDatabase,
    identity: TrackIdentity,
    *,
    family: str,
) -> np.ndarray | None:
    with database.connect() as connection:
        return read_valid_embeddings(
            family=family,
            identities={identity.track_id: identity.track_uuid},
            catalog_uuid=identity.catalog_uuid,
            connection=connection,
        ).get(identity.track_id)


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

    def claim_sonara_analysis_range(
        self,
        bpm_min: float,
        bpm_max: float,
    ) -> tuple[float, float]:
        return (bpm_min, bpm_max)

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
    assert status.phase == "analyzing"
    messages = [event.message for event in status.events]
    assert messages.index("Model warm-up started: mert, clap") < messages.index(
        "Analysis candidates ready: 1"
    )
    assert all(runner.preflight_calls == 1 for runner in runners.values())
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


@pytest.mark.parametrize("failure_origin", ["result", "mert_batch", "mert_staged"])
def test_per_file_runner_failure_does_not_fail_the_job(failure_origin: str, tmp_path: Path) -> None:
    output = _mert_output()
    candidates = [_candidate(1, (output,)), _candidate(2, (output,))]
    repository = _FakeRepository(candidates)
    runner = _FakeRunner(
        "mert",
        (output,),
        errors=(None, RuntimeError("stale target")),
    )
    if failure_origin != "result":
        class FailingMertAdapter(_FakeMertAdapter):
            def embed_decoded_batch(self, decoded_items, *, cancelled=None):
                if any(Path(item.path).stem == "2" for item in decoded_items):
                    raise RuntimeError("stale target")
                return super().embed_decoded_batch(decoded_items, cancelled=cancelled)

        runner = EmbeddingModelRunner(
            "mert", device="cpu", inference_batch_size=2, adapter=FailingMertAdapter(),
        )
        write_repository = _EmbeddingWriteRepository()
        repository.save_embedding_results = write_repository.save_embedding_results
    runners = {"mert": runner}
    staging_config = None
    if failure_origin == "mert_staged":
        clap_output = _clap_output()
        runners["clap"] = _FakeRunner("clap", (clap_output,))
        for index, candidate in enumerate(candidates):
            path = tmp_path / f"{candidate.target.track_id}.wav"
            path.write_text(f"{candidate.target.track_id}.wav")
            candidates[index] = replace(
                candidate, file_path=str(path), missing_outputs=(output, clap_output),
            )
        staging_config = MLStagingConfig(
            root=tmp_path / "staging", copy_workers=1, decode_workers=1,
            stage_size=2, inference_batch_size=2,
        )

    status = AnalysisJobManager(
        repository,
        model_runners=runners,
        decode_audio=lambda path: _decoded(Path(path).read_text() if staging_config else str(path)),
    ).run_sync(models=list(runners), device="cpu", ml_staging_config=staging_config)

    assert status.state == "completed"
    assert status.processed == 2
    if failure_origin != "result":
        assert [write.target.track_id for write in write_repository.writes] == [1]
    assert status.analyzed == 1
    assert status.failed == 1
    assert status.model_progress["mert"].analyzed == 1
    assert status.model_progress["mert"].failed == 1
    assert status.errors[0].track_id == 2
    assert "stale target" in status.errors[0].error
    if failure_origin == "mert_staged":
        assert status.model_progress["clap"].analyzed == 2
        assert status.model_progress["clap"].failed == 0
        assert [error.model for error in status.errors] == ["mert"]


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


@pytest.mark.parametrize("error_type", [OSError, KeyboardInterrupt])
def test_staging_entry_failure_finishes_job_and_releases_execution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error_type: type[BaseException],
) -> None:
    output = _mert_output()
    repository = _FakeRepository([_candidate(1, (output,))])
    runner = _FakeRunner("mert", (output,))
    manager = AnalysisJobManager(repository, model_runners={"mert": runner})
    job_id = manager.create_job(
        models=["mert"], device="cpu", ml_staging_config=MLStagingConfig(root=tmp_path)
    )
    error = error_type("staging unavailable")
    payload = manager._payload(job_id)

    def fail_enter(_session: MLStagingSession) -> MLStagingSession:
        assert payload.candidates and payload.targets_by_track and payload.track_outcomes
        raise error

    monkeypatch.setattr(MLStagingSession, "__enter__", fail_enter)
    if isinstance(error, Exception):
        status = manager.run_job(job_id)
    else:
        with pytest.raises(error_type) as caught:
            manager.run_job(job_id)
        assert caught.value is error
        status = manager.get(job_id)

    assert repository.events[-1][0] == "candidates"
    assert status.state == "failed"
    assert status.finished_at is not None
    assert status.current_path is None
    assert status.current_model is None
    assert status.events[-1].level == "error"
    assert "staging unavailable" in status.events[-1].message
    assert payload.candidates == []
    assert payload.targets_by_track == {}
    assert payload.track_outcomes == {}
    closed = threading.Event()
    closer = threading.Thread(target=lambda: (manager.close(), closed.set()), daemon=True)
    closer.start()
    closer.join(5)
    assert closed.is_set()


@pytest.mark.parametrize(
    ("mode", "cancel_at"),
    [
        ("direct", None),
        ("direct", "inference"),
        ("direct", "retry"),
        ("direct", "recovery"),
        ("direct", "before_write"),
        ("staged", "inference"),
    ],
)
def test_finished_job_releases_track_data_but_retains_status_and_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, cancel_at: str | None,
) -> None:
    output = _mert_output()
    maest_runner = (
        MaestModelRunner(device="cpu", top_k=3, inference_batch_size=2, adapter=_FakeMaestAdapter())
        if mode == "staged" else None
    )
    outputs = (output,) if maest_runner is None else (*maest_runner.candidate_outputs, output)
    repository = _FakeRepository([])
    for track_id in range(1, 5):
        path = tmp_path / f"{track_id}.wav"
        path.write_text(str(track_id))
        repository.candidates.append(replace(_candidate(track_id, outputs), file_path=str(path)))
    candidate_ref = weakref.ref(repository.candidates[0])
    outcome_refs = []
    audio_refs = []
    partial_results = []
    calls: list[tuple[int, ...]] = []
    fallback_calls: list[int] = []
    writes: list[EmbeddingWrite] = []
    maest_writes: list[MaestWrite] = []

    def save_embedding_results(selected):
        writes.extend(selected)
        return tuple(
            AnalysisWriteResult(target=write.target, written_outputs=(output,))
            for write in selected
        )

    repository.save_embedding_results = save_embedding_results

    def save_maest_results(selected):
        maest_writes.extend(selected)
        return tuple(
            AnalysisWriteResult(target=write.target, written_outputs=write.outputs)
            for write in selected
        )

    if maest_runner is not None:
        repository.save_maest_results = save_maest_results

    def decode_audio(path):
        track_id = int(Path(path).read_text())
        if cancel_at == "recovery" and track_id == 3:
            raise RuntimeError("broken decode")
        audio = np.asarray([track_id], dtype=np.float32)
        audio_refs.append(weakref.ref(audio))
        return DecodedAudio(
            path=str(path), audio=audio,
            sample_rate=24_000, detail="test",
        )

    def fallback_audio(path):
        track_id = int(Path(path).read_text())
        fallback_calls.append(track_id)
        return DecodedAudio(
            path=str(path), audio=np.asarray([track_id], dtype=np.float32),
            sample_rate=24_000, detail="ffmpeg",
        )

    monkeypatch.setattr(runner_module, "load_decoded_audio_with_ffmpeg", fallback_audio)

    class ReleasingMertAdapter(_FakeMertAdapter):
        def embed_decoded_batch(self, decoded_items, *, cancelled=None):
            payload = manager._payload(job_id)
            outcome_refs.extend(weakref.ref(value) for value in payload.track_outcomes.values())
            repository.candidates.clear()
            track_ids = tuple(int(item.audio[0]) for item in decoded_items)
            calls.append(track_ids)
            if cancel_at and 3 in track_ids:
                if cancel_at == "retry" and len(track_ids) > 1:
                    raise ValueError("retry this batch per track")
                manager.cancel(job_id)
                if cancel_at != "before_write":
                    assert cancelled is not None and cancelled()
                    raise EmbeddingCancelledError("MERT analysis cancelled")
            return super().embed_decoded_batch(decoded_items)

    runner = EmbeddingModelRunner(
        "mert", device="cpu", inference_batch_size=2, adapter=ReleasingMertAdapter(),
    )
    runners = {"mert": runner}
    if maest_runner is not None:
        runners["maest"] = maest_runner
    manager = AnalysisJobManager(
        repository,
        model_runners=runners,
        decode_audio=decode_audio,
    )
    if mode == "staged":
        record_staged = manager._record_staged_ml_result

        def retain_partial_result(job_id, result):
            if set(result.model_errors) == {"maest"}:
                partial_results.append(result)
            record_staged(job_id, result)

        monkeypatch.setattr(manager, "_record_staged_ml_result", retain_partial_result)
    staging_config = (
        MLStagingConfig(
            root=tmp_path / "staging", copy_workers=1, decode_workers=1,
            stage_size=2, inference_batch_size=2,
        )
        if mode == "staged" else None
    )
    job_id = manager.create_job(
        models=list(runners), device="cpu", track_batch_size=2, ml_staging_config=staging_config,
    )
    status = manager.run_job(job_id)

    assert status.state == ("cancelled" if cancel_at else "completed")
    assert status.failed == 0
    assert status.errors == []
    assert status.analyzed == len(writes)
    assert fallback_calls == ([3] if cancel_at == "recovery" else [])
    assert [write.target.track_id for write in writes] == ([1, 2] if cancel_at else [1, 2, 3, 4])
    assert calls.count((3, 4)) <= 1
    if cancel_at == "retry":
        assert calls == [(1, 2), (3, 4), (3,)]
    if cancel_at == "inference":
        assert calls == [(1, 2), (3, 4)]
    if mode == "staged":
        assert [write.target.track_id for write in maest_writes] == [1, 2, 3, 4]
        assert status.model_progress["maest"].processed == status.model_progress["maest"].analyzed == 4
        assert status.model_progress["mert"].processed == status.model_progress["mert"].analyzed == 2
        assert status.model_progress["maest"].failed == status.model_progress["mert"].failed == 0
        assert status.total == 4
        assert status.processed == status.analyzed == 2
        assert status.skipped == 0
        assert [result.target.track_id for result in partial_results] == [3, 4]
        assert all(not result.track_complete for result in partial_results)
        assert all(result.error is None and result.model_errors == {"maest": None} for result in partial_results)
        gc.collect()
        assert len(audio_refs) == 4 and all(ref() is None for ref in audio_refs)
    assert candidate_ref() is None
    assert outcome_refs and all(ref() is None for ref in outcome_refs)
    assert manager.get(job_id) == status
    assert manager.latest() == status
    assert manager._payload(job_id).targets_by_track == {}
    assert manager.run_job(job_id).state == status.state
    manager.close()

    clap_cancel_points = (
        ("inference", "retry", "recovery", "before_write")
        if mode == "staged" else (cancel_at,)
    )
    for clap_cancel_at in clap_cancel_points:
        _assert_clap_job_cancellation(tmp_path, monkeypatch, mode, clap_cancel_at)


def _assert_clap_job_cancellation(tmp_path, monkeypatch, mode, cancel_at) -> None:
    torch = pytest.importorskip("torch")
    root = tmp_path / f"clap-{cancel_at}"
    root.mkdir()
    output = _clap_output()
    repository = _FakeRepository([])
    for track_id in range(1, 5):
        path = root / f"{track_id}.wav"
        path.write_text(str(track_id))
        repository.candidates.append(replace(_candidate(track_id, (output,)), file_path=str(path)))
    writes: list[EmbeddingWrite] = []
    fallback_calls: list[int] = []
    native_calls_at_cancel = None

    def save_embedding_results(selected):
        writes.extend(selected)
        return tuple(
            AnalysisWriteResult(target=write.target, written_outputs=(output,))
            for write in selected
        )

    repository.save_embedding_results = save_embedding_results

    def decoded_track(path):
        track_id = int(Path(path).read_text())
        # Track 3 needs more than one native batch. Cancelling its first batch
        # must discard its partial window pool and prevent the following batch.
        length = 3 * 480_000 if track_id == 3 else 48_000
        return DecodedAudio(
            path=str(path), audio=torch.full((length,), float(track_id)),
            sample_rate=48_000, detail="synthetic",
        )

    def decode_audio(path):
        if cancel_at == "recovery" and int(Path(path).read_text()) >= 3:
            raise RuntimeError("synthetic full decode failure")
        return decoded_track(path)

    def fallback_audio(path):
        fallback_calls.append(int(Path(path).read_text()))
        return decoded_track(path)

    monkeypatch.setattr(runner_module, "load_decoded_audio_with_ffmpeg", fallback_audio)
    adapter = _WindowedClapAdapter()

    def cancel_job():
        nonlocal native_calls_at_cancel
        manager.cancel(job_id)
        if native_calls_at_cancel is None:
            native_calls_at_cancel = tuple(adapter.native_calls)

    def before_native(windows):
        if cancel_at in {"inference", "retry", "recovery"} and any(row[0] == 3 for row in windows):
            cancel_job()
            if cancel_at == "retry":
                # A generic native failure concurrent with cancellation must
                # not enter per-track retry or FFmpeg recovery.
                raise ValueError("native failure after cancellation")

    adapter.before_native = before_native
    if cancel_at == "before_write":
        embed_decoded_batch = adapter.embed_decoded_batch

        def cancel_after_embedding(decoded_items, **kwargs):
            vectors = embed_decoded_batch(decoded_items, **kwargs)
            if any(item.audio[0] == 3 for item in decoded_items):
                cancel_job()
            return vectors

        monkeypatch.setattr(adapter, "embed_decoded_batch", cancel_after_embedding)

    runner = EmbeddingModelRunner("clap", device="cpu", inference_batch_size=2, adapter=adapter)
    manager = AnalysisJobManager(repository, model_runners={"clap": runner}, decode_audio=decode_audio)
    staging_config = (
        MLStagingConfig(
            root=root / "staging", copy_workers=1, decode_workers=1,
            stage_size=2, inference_batch_size=2,
        )
        if mode == "staged" else None
    )
    job_id = manager.create_job(
        models=["clap"], device="cpu", track_batch_size=2,
        inference_batch_size=2, ml_staging_config=staging_config,
    )
    try:
        status = manager.run_job(job_id)
        assert status.state == ("cancelled" if cancel_at else "completed")
        assert status.failed == 0 and status.errors == []
        assert sorted(write.target.track_id for write in writes) == ([1, 2] if cancel_at else [1, 2, 3, 4])
        assert status.analyzed == len(writes)
        assert fallback_calls == ([3] if cancel_at == "recovery" else [])
        if cancel_at:
            assert native_calls_at_cancel is not None
            assert tuple(adapter.native_calls) == native_calls_at_cancel
        if cancel_at in {"inference", "retry", "recovery"}:
            assert sum(any(row[0] == 3 for row in call) for call in adapter.native_calls) == 1
    finally:
        manager.close()


def test_ml_runtime_runner_is_reused_after_its_first_successful_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
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

    runner_ref = weakref.ref(created.pop())
    manager.close()
    manager.close()
    assert runner_ref() is None
    assert manager.get(first.job_id).state == "completed"
    with pytest.raises(RuntimeError, match="closed"):
        manager.start(models=["mert"], device="cpu")
    with pytest.raises(RuntimeError, match="closed"):
        manager.run_sync(models=["mert"], device="cpu")
    with pytest.raises(RuntimeError, match="closed"):
        manager.run_job(first.job_id)

    for mode in ("direct", "staged"):
        _assert_cached_clap_cancellation_is_job_scoped(tmp_path, monkeypatch, mode)


def _assert_cached_clap_cancellation_is_job_scoped(tmp_path, monkeypatch, mode) -> None:
    torch = pytest.importorskip("torch")
    root = tmp_path / mode
    root.mkdir()
    path = root / "1.wav"
    path.write_text("synthetic")
    output = _clap_output()
    repository = _FakeRepository([replace(_candidate(1, (output,)), file_path=str(path))])
    created: list[_WindowedClapAdapter] = []
    writes: list[EmbeddingWrite] = []
    native_entered = threading.Event()
    release_native = threading.Event()
    second_warming = threading.Event()
    errors: list[BaseException] = []

    def before_native(_windows):
        native_entered.set()
        assert release_native.wait(10), "native inference was not released"

    def factory(model, device, batch_size, _top_k):
        adapter = _WindowedClapAdapter(batch_size)
        adapter.before_native = before_native
        created.append(adapter)
        return EmbeddingModelRunner(model, device=device, inference_batch_size=batch_size, adapter=adapter)

    def save_embedding_results(selected):
        writes.extend(selected)
        return tuple(AnalysisWriteResult(target=write.target, written_outputs=(output,)) for write in selected)

    repository.save_embedding_results = save_embedding_results
    manager = AnalysisJobManager(
        repository, runner_factory=factory,
        decode_audio=lambda source: DecodedAudio(
            path=str(source), audio=torch.ones(48_000), sample_rate=48_000, detail="synthetic",
        ),
    )
    staging = (
        MLStagingConfig(
            root=root / "staging", copy_workers=1, decode_workers=1,
            stage_size=1, inference_batch_size=2,
        )
        if mode == "staged" else None
    )
    first_id = manager.create_job(models=["clap"], device="cpu", inference_batch_size=2, ml_staging_config=staging)
    second_id = manager.create_job(models=["clap"], device="cpu", inference_batch_size=2)
    warm_up = manager._warm_up_models

    def observe_warm_up(job_id, models, lifecycle):
        if job_id == second_id:
            # Preparation has selected the shared runner; actual warm-up may
            # now wait on the handle held by the first job's native inference.
            second_warming.set()
        return warm_up(job_id, models, lifecycle)

    monkeypatch.setattr(manager, "_warm_up_models", observe_warm_up)

    def run(job_id):
        try:
            manager.run_job(job_id)
        except BaseException as error:
            errors.append(error)

    first_thread = threading.Thread(target=run, args=(first_id,), daemon=True)
    second_thread = threading.Thread(target=run, args=(second_id,), daemon=True)
    try:
        first_thread.start()
        assert native_entered.wait(10), "first job did not reach native inference"
        second_thread.start()
        assert second_warming.wait(10), "second job did not reach shared runner warm-up"
        manager.cancel(second_id)
        release_native.set()
        first_thread.join(10)
        second_thread.join(10)
        assert not first_thread.is_alive() and not second_thread.is_alive()
        assert errors == []
        first = manager.get(first_id)
        second = manager.get(second_id)
        assert (first.state, first.cancel_requested) == ("completed", False)
        assert (second.state, second.cancel_requested) == ("cancelled", True)
        assert first.analyzed == 1 and second.analyzed == 0
        assert [write.target.track_id for write in writes] == [1]
        expected = np.zeros(512, dtype=np.float32)
        expected[:3] = [4, 5, 0.1]
        expected /= np.linalg.norm(expected)
        np.testing.assert_allclose(writes[0].output.vector, expected, rtol=1e-6, atol=1e-7)
        assert len(created) == 1 and created[0].preflight_calls == 1
        assert len(created[0].native_calls) == 1
    finally:
        release_native.set()
        for thread in (first_thread, second_thread):
            if thread.ident is not None:
                thread.join(10)
        if not first_thread.is_alive() and not second_thread.is_alive():
            manager.close()


class _WindowedClapAdapter(ClapEmbeddingAdapter):
    """Exercise production windowing while replacing only native inference."""

    def __init__(self, inference_batch_size: int = 2) -> None:
        super().__init__(device="cpu", inference_batch_size=inference_batch_size)
        self.preflight_calls = 0
        self.native_calls: list[tuple[tuple[float, float, int], ...]] = []
        self.before_native: Callable | None = None

    def preflight(self) -> None:
        self.preflight_calls += 1
        self._load_model()

    def _load_model(self) -> None:
        self._torch = pytest.importorskip("torch")
        self._model = self
        self.device = "cpu"

    def get_audio_embedding_from_data(self, x, use_tensor=False):
        assert not use_tensor
        self.native_calls.append(tuple((float(row[0]), float(row[-1]), len(row)) for row in x))
        if self.before_native is not None:
            self.before_native(x)
        rows = np.zeros((len(x), 512), dtype=np.float32)
        rows[:, 0] = [row[0] + 3.0 for row in x]
        rows[:, 1] = [row[-1] + 4.0 for row in x]
        rows[:, 2] = [len(row) / 480_000 for row in x]
        return rows


def test_ml_runtime_runner_is_not_reused_across_runtime_settings(tmp_path: Path) -> None:
    torch = pytest.importorskip("torch")
    output = _clap_output()
    repository = _FakeRepository([])
    created: dict[int, _WindowedClapAdapter] = {}
    writes: dict[int, np.ndarray] = {}
    audio_by_track = {
        1: torch.linspace(0.1, 0.9, 1_200_000),
        2: torch.linspace(-0.7, -0.2, 48_001, dtype=torch.float64),
    }
    expected = {}
    for track_id, audio in audio_by_track.items():
        path = tmp_path / f"{track_id}.wav"
        path.write_text(str(track_id))
        repository.candidates.append(replace(_candidate(track_id, (output,)), file_path=str(path)))
        bounds = [(0, 480_000), (480_000, 960_000), (720_000, 1_200_000)] if track_id == 1 else [(0, 48_001)]
        rows = np.asarray([
            [float(audio[start].float()) + 3.0, float(audio[end - 1].float()) + 4.0, (end - start) / 480_000]
            for start, end in bounds
        ], dtype=np.float64)
        rows /= np.linalg.norm(rows, axis=1, keepdims=True)
        pooled = rows.mean(axis=0)
        expected[track_id] = pooled / np.linalg.norm(pooled)

    def save_embedding_results(selected):
        for write in selected:
            assert write.output.family == "clap"
            writes[write.target.track_id] = write.output.vector.copy()
        return tuple(AnalysisWriteResult(target=write.target, written_outputs=(output,)) for write in selected)

    repository.save_embedding_results = save_embedding_results

    def decode_audio(path):
        track_id = int(Path(path).read_text())
        return DecodedAudio(path=str(path), audio=audio_by_track[track_id].clone(), sample_rate=48_000, detail="synthetic")

    def factory(model: str, device: str, batch_size: int, _top_k: int) -> EmbeddingModelRunner:
        assert model == "clap" and device == "cpu"
        assert batch_size not in created
        adapter = _WindowedClapAdapter(batch_size)
        created[batch_size] = adapter
        return EmbeddingModelRunner(model, device=device, inference_batch_size=batch_size, adapter=adapter)

    manager = AnalysisJobManager(repository, runner_factory=factory, decode_audio=decode_audio)
    reference: dict[int, np.ndarray] = {}
    try:
        for general_limit, staged_limit in ((3, None), (16, 1), (1, 16), (1, None), (3, None), (8, 2)):
            effective = general_limit if staged_limit is None else min(general_limit, staged_limit)
            staging = None if staged_limit is None else MLStagingConfig(
                root=tmp_path / "staging", copy_workers=1, decode_workers=1,
                stage_size=2, inference_batch_size=staged_limit,
            )
            writes.clear()
            for adapter in created.values():
                adapter.native_calls.clear()
            status = manager.run_sync(
                models=["clap"], device="cpu", track_batch_size=2,
                inference_batch_size=general_limit, ml_staging_config=staging,
            )
            assert status.state == "completed" and status.failed == 0
            assert status.analyzed == status.processed == 2
            calls = [call for adapter in created.values() for call in adapter.native_calls]
            assert max(map(len, calls)) <= effective
            assert sum(map(len, calls)) == 4
            assert status.inference_batch_size == effective
            assert set(writes) == {1, 2}
            for track_id, vector in writes.items():
                assert vector.shape == (512,) and vector.dtype == np.float32
                np.testing.assert_allclose(vector[:3], expected[track_id], rtol=1e-6, atol=1e-7)
                assert not np.count_nonzero(vector[3:])
                assert np.linalg.norm(vector) == pytest.approx(1.0)
                if track_id in reference:
                    np.testing.assert_array_equal(vector, reference[track_id])
                else:
                    reference[track_id] = vector.copy()
        assert set(created) == {1, 2, 3}
        assert all(adapter.preflight_calls == 1 for adapter in created.values())
    finally:
        manager.close()


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
        default_model_runners(model, "cpu", 7, 11)
        for model in ("maest", "mert", "muq", "mulan", "clap")
    ]

    assert [runner.model for runner in runners] == [
        "maest",
        "mert",
        "muq",
        "mulan",
        "clap",
    ]
    assert {
        runner.model: tuple(output.key for output in runner.active_outputs)
        for runner in runners
    } == {
        "maest": (("maest", "analysis"), ("maest", "embedding")),
        "mert": (("mert", "embedding"),),
        "muq": (("muq", "embedding"),),
        "mulan": (("mulan", "embedding"),),
        "clap": (("clap", "embedding"),),
    }
    expected_dimensions = {
        "maest": 768,
        "mert": 768,
        "muq": 1024,
        "mulan": 512,
        "clap": 512,
    }
    for runner in runners:
        assert getattr(runner.adapter, "_model") is None
        assert runner.adapter.inference_batch_size == 7
        for output in runner.active_outputs:
            if output.output_kind == "embedding":
                spec = current_embedding_spec(output.analysis_family)
                assert spec.dimension == expected_dimensions[output.analysis_family]
                assert spec.normalization == "l2"
    assert runners[0].adapter.runtime_parameters()["top_k"] == 11


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


def test_sonara_runner_exposes_default_core_and_embedding_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = (_sonara_output("core"), _sonara_output("embedding"))
    monkeypatch.setattr(
        runner_module,
        "analysis_outputs_for_sonara_runtime",
        lambda _module=None: outputs,
    )

    runner = SonaraModelRunner(sonara_module=object())

    assert [output.key for output in runner.active_outputs] == [
        ("sonara", "core"),
        ("sonara", "embedding"),
    ]
    assert [output.key for output in runner.candidate_outputs] == [
        ("sonara", "core"),
        ("sonara", "embedding"),
    ]
    assert not hasattr(build_analysis_job_config(models=["sonara"]), "sonara_outputs")


def _sonara_output(kind: str) -> AnalysisOutput:
    return AnalysisOutput("sonara", kind)


class _FakeMertAdapter(MertEmbeddingAdapter):
    def __init__(self) -> None:
        super().__init__(
            device="cpu",
            inference_batch_size=2,
        )

    def preflight(self) -> None:
        pass

    def embed_decoded_batch(
        self,
        decoded_items: Sequence[DecodedAudio],
        *,
        cancelled: Callable[[], bool] | None = None,
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


class _FakeMulanAdapter(MuqMulanEmbeddingAdapter):
    def __init__(self) -> None:
        super().__init__(device="cpu")

    def preflight(self) -> None:
        pass

    def embed_decoded_batch(
        self,
        decoded_items: Sequence[DecodedAudio],
    ) -> list[np.ndarray]:
        vector = np.zeros(512, dtype=np.float32)
        vector[0] = 1.0
        return [vector.copy() for _item in decoded_items]

def test_mulan_runner_writes_its_own_typed_embedding_output() -> None:
    runner = EmbeddingModelRunner(
        "mulan",
        device="cpu",
        inference_batch_size=2,
        adapter=_FakeMulanAdapter(),  # type: ignore[arg-type]
    )
    candidate = _candidate(1, runner.candidate_outputs)
    repository = _EmbeddingWriteRepository()

    results = runner.analyze_batch(
        repository,  # type: ignore[arg-type]
        (
            AnalysisBatchItem(
                candidate=candidate,
                decoded=_decoded(candidate.file_path),
                models=("mulan",),
            ),
        ),
    )

    assert results == [None]
    assert repository.writes[0].output.family == "mulan"
    assert repository.writes[0].output.vector.shape == (512,)


def test_mulan_runner_uses_ffmpeg_after_full_decode_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = EmbeddingModelRunner(
        "mulan",
        device="cpu",
        inference_batch_size=2,
        adapter=_FakeMulanAdapter(),  # type: ignore[arg-type]
    )
    candidate = _candidate(1, runner.candidate_outputs)
    repository = _EmbeddingWriteRepository()
    calls: list[str] = []

    monkeypatch.setattr(
        runner_module,
        "load_decoded_audio_with_ffmpeg",
        lambda path: (
            calls.append(f"ffmpeg:{path}"),
            _decoded(path),
        )[1],
    )

    results = runner.analyze_batch(
        repository,  # type: ignore[arg-type]
        (
            AnalysisBatchItem(
                candidate=candidate,
                decoded=DecodeFailure(RuntimeError("bad final packet")),
                models=("mulan",),
            ),
        ),
    )

    assert results == [None]
    assert calls == [f"ffmpeg:{candidate.file_path}"]
    assert repository.writes[0].output.vector[0] == pytest.approx(1.0)
    assert runner.last_ffmpeg_fallback_track_ids == frozenset({candidate.target.track_id})


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
                INSERT INTO sonara_features(
                track_id, mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analysis_schema_version,
                analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                mutation.identity.track_id,
                np.zeros(13, dtype="<f4").tobytes(),
                np.zeros(12, dtype="<f4").tobytes(),
                np.zeros(7, dtype="<f4").tobytes(),
                6,
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
    assert [event.message for event in status.events if event.track_id is not None] == [
        "[torchcodec] Track analyzed"
    ]
    assert database.list_analysis_candidates(runner.candidate_outputs) == []
    vector = _stored_embedding(database, mutation.identity, family="mert")
    assert vector is not None
    assert vector.shape == (768,)
    assert vector[0] == pytest.approx(1.0)


def test_job_defers_full_decode_failure_to_mulan_ffmpeg_recovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database = LibraryDatabase(tmp_path / "library.sqlite")
    mutation = database.upsert_scanned_track(
        file=ScannedFile(
            file_path=str(tmp_path / "track.flac"),
            file_size_bytes=128,
            file_modified_ns=1_000,
            audio_format="flac",
            sample_rate_hz=24_000,
            channel_count=2,
            audio_duration_seconds=30.0,
        ),
        tags=FileTags(title="FFmpeg recovery"),
    )
    with database.connect() as connection:
        connection.execute(
            """
                INSERT INTO sonara_features(
                track_id, mfcc_mean_blob, chroma_mean_blob,
                spectral_contrast_mean_blob, analysis_schema_version,
                analyzed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                mutation.identity.track_id,
                np.zeros(13, dtype="<f4").tobytes(),
                np.zeros(12, dtype="<f4").tobytes(),
                np.zeros(7, dtype="<f4").tobytes(),
                6,
                "2026-07-30T00:00:00.000000Z",
            ),
        )
    runner = EmbeddingModelRunner(
        "mulan",
        device="cpu",
        inference_batch_size=2,
        adapter=_FakeMulanAdapter(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        runner_module,
        "load_decoded_audio_with_ffmpeg",
        lambda path: _decoded(path),
    )

    status = AnalysisJobManager(
        database,
        model_runners={"mulan": runner},
        decode_audio=lambda _path: (_ for _ in ()).throw(RuntimeError("bad tail")),
    ).run_sync(models=["mulan"], device="cpu")

    assert status.state == "completed"
    assert status.analyzed == 1
    assert status.failed == 0
    assert [event.message for event in status.events if event.track_id is not None] == [
        "[ffmpeg] Track analyzed"
    ]
    vector = _stored_embedding(database, mutation.identity, family="mulan")
    assert vector is not None
    assert vector[0] == pytest.approx(1.0)


class _FakeMaestAdapter(MaestEmbeddingAdapter):
    def __init__(self) -> None:
        super().__init__(
            device="cpu",
            top_k=3,
        )

    def preflight(self) -> None:
        pass

    def analyze_decoded_batch(
        self,
        decoded_items: Sequence[DecodedAudio],
    ) -> list[MaestAnalysisResult]:
        results: list[MaestAnalysisResult] = []
        for item in decoded_items:
            vector = np.zeros(768, dtype=np.float32)
            vector[:2] = (3.0, 4.0)
            results.append(
                MaestAnalysisResult(
                    genres=[{"label": "Electronic---Breaks", "score": 0.9}],
                    embedding=vector,
                )
            )
        return results


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


@pytest.mark.parametrize("mode", ["run_job", "run_sync", "threaded", "queued"])
def test_manager_close_waits_for_execution_before_releasing_runners(monkeypatch, mode) -> None:
    output = _mert_output()
    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    closing = threading.Event()
    stage_queue = AnalysisStageQueue() if mode == "queued" else None
    results = []

    class BlockingRunner(_FakeRunner):
        def preflight(self):
            with pytest.raises(RuntimeError, match="executing job"):
                manager.close()
            entered.set()
            assert release.wait(5)
            super().preflight()

    runner = BlockingRunner("mert", (output,))
    runner_ref = weakref.ref(runner)
    manager = AnalysisJobManager(
        _FakeRepository([]), model_runners={"mert": runner}, stage_queue=stage_queue,
    )
    del runner
    # An undispatched status must not leave close waiting forever.
    unused = manager.create_job(models=["mert"], device="cpu")
    close_errors = []
    interrupt = KeyboardInterrupt("manager close interrupted")
    interrupted = threading.Event()
    second_closed = threading.Event()
    wait = manager._lifecycle.wait

    def interrupt_wait(*args, **kwargs):
        if mode == "run_job" and not interrupted.is_set():
            interrupted.set()
            raise interrupt
        return wait(*args, **kwargs)

    monkeypatch.setattr(manager._lifecycle, "wait", interrupt_wait)

    def run():
        if mode == "run_job":
            results.append(manager.run_job(unused))
        else:
            results.append(manager.run_sync(models=["mert"], device="cpu"))

    def close():
        closing.set()
        try:
            manager.close()
        except BaseException as error:
            close_errors.append(error.with_traceback(None))
        finally:
            if stage_queue is not None:
                stage_queue.close()
        closed.set()

    worker = None
    closer = threading.Thread(target=close, daemon=True)
    second_close = threading.Thread(target=lambda: (manager.close(), second_closed.set()), daemon=True)
    try:
        if mode in {"queued", "threaded"}:
            results.append(manager.start(models=["mert"], device="cpu"))
        else:
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
        assert entered.wait(5)
        closer.start()
        assert closing.wait(5)
        if mode == "run_job":
            assert interrupted.wait(5)
        second_close.start()
        assert not closed.wait(0.1)
        assert not second_closed.is_set()
        assert runner_ref() is not None
    finally:
        release.set()
        if worker is not None and worker.ident is not None:
            worker.join(5)
        if closer.ident is None:
            closer.start()
        closer.join(5)
        if second_close.ident is not None:
            second_close.join(5)
    assert worker is None or not worker.is_alive()
    assert not closer.is_alive()
    assert closed.is_set()
    assert second_closed.is_set()
    assert close_errors == ([interrupt] if mode == "run_job" else [])
    assert runner_ref() is None
    assert manager.get(results[0].job_id).state == "completed"
    with pytest.raises(RuntimeError, match="closed"):
        manager.create_job(models=["mert"], device="cpu")


@pytest.mark.parametrize("mode", ["queued", "threaded"])
def test_manager_close_in_dispatch_gap_preserves_accepted_work(monkeypatch, mode) -> None:
    from types import SimpleNamespace
    from dj_track_similarity.analysis import jobs as jobs_module

    entered = threading.Event()
    release = threading.Event()
    closing = threading.Event()
    closed = threading.Event()
    statuses = []
    output = _mert_output()
    runner = _FakeRunner("mert", (output,))
    stage_queue = AnalysisStageQueue() if mode == "queued" else None
    manager = AnalysisJobManager(
        _FakeRepository([]), model_runners={"mert": runner}, stage_queue=stage_queue,
    )

    def hold_dispatch():
        entered.set()
        assert release.wait(5)

    if stage_queue is not None:
        submit = stage_queue.submit

        def delayed_submit(callback):
            hold_dispatch()
            submit(callback)

        monkeypatch.setattr(stage_queue, "submit", delayed_submit)
    else:
        class DelayedThread(threading.Thread):
            def start(self):
                hold_dispatch()
                super().start()

        monkeypatch.setattr(jobs_module, "threading", SimpleNamespace(
            Thread=DelayedThread, get_ident=threading.get_ident,
        ))

    starter = threading.Thread(target=lambda: statuses.append(
        manager.start(models=["mert"], device="cpu")
    ), daemon=True)

    def close():
        closing.set()
        try:
            manager.close()
        finally:
            if stage_queue is not None:
                stage_queue.close()
        closed.set()

    closer = threading.Thread(target=close, daemon=True)
    try:
        starter.start()
        assert entered.wait(5)
        closer.start()
        assert closing.wait(5)
        assert not closed.wait(0.1)
    finally:
        release.set()
        if starter.ident is not None:
            starter.join(5)
        if closer.ident is None:
            closer.start()
        closer.join(5)
    assert not starter.is_alive()
    assert not closer.is_alive()
    assert closed.is_set()
    assert manager.get(statuses[0].job_id).state == "completed"
    assert runner.preflight_calls == 1


def test_rejected_queue_dispatch_finishes_job_and_releases_reservation() -> None:
    stage_queue = AnalysisStageQueue()
    manager = AnalysisJobManager(_FakeRepository([]), stage_queue=stage_queue)
    stage_queue.close()
    with pytest.raises(RuntimeError, match="closed"):
        manager.start(models=["mert"], device="cpu")
    assert manager.latest().state == "failed"
    closed = threading.Event()
    closer = threading.Thread(target=lambda: (manager.close(), closed.set()), daemon=True)
    closer.start()
    closer.join(5)
    assert not closer.is_alive()
    assert closed.is_set()
