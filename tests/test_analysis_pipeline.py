import threading
import weakref
from types import SimpleNamespace

import pytest

from dj_track_similarity.analysis.pipeline import AnalysisPipelineManager
from dj_track_similarity.analysis.queue import AnalysisStageQueue
from dj_track_similarity.analysis.ml_staging import MLStagingConfig
from dj_track_similarity.analysis.sonara_staging import SonaraStagingConfig


class FakeJobs:
    def __init__(self, states, *, sonara_count=1):
        self.states = list(states)
        self.sonara_count = sonara_count
        self.created = []
        self.cancelled = []

    def current_sonara_track_count(self):
        return self.sonara_count

    def create_job(self, **kwargs):
        job_id = f"child-{len(self.created) + 1}"
        self.created.append((job_id, kwargs))
        return job_id

    def run_job(self, job_id):
        return SimpleNamespace(state=self.states.pop(0))

    def cancel(self, job_id):
        self.cancelled.append(job_id)


def test_pipeline_uses_fixed_order_and_continues_after_completed_per_file_failures() -> None:
    audio = FakeJobs(["completed", "completed"], sonara_count=0)
    stage_queue = AnalysisStageQueue()
    manager = AnalysisPipelineManager(audio, stage_queue)
    queued = manager.start(
        stages=["ml", "sonara"],
        limit=10,
        sonara={"batch_size": 16},
        ml={"models": ["mert"]},
    )

    stage_queue.close()
    status = manager.get(queued.job_id)

    assert status.state == "completed"
    assert status.order == ["sonara", "ml"]
    assert [stage.state for stage in status.stages.values()] == ["completed", "completed"]
    assert len(audio.created) == 2


def test_pipeline_forwards_staged_sonara_configuration_to_child_job(tmp_path) -> None:
    audio = FakeJobs(["completed"])
    manager = AnalysisPipelineManager(audio, AnalysisStageQueue())
    staging = SonaraStagingConfig(
        root=tmp_path,
        processes=4,
        rayon_threads=4,
        max_native_batch_size=4,
        stage_size=32,
    )
    job_id = manager.create_job(
        stages=["sonara"],
        limit=None,
        sonara={
            "mode": "staged",
            "batch_size": 4,
            "staging_config": staging,
        },
    )

    manager.run_job(job_id)

    assert audio.created == [
        (
            "child-1",
            {
                "models": ["sonara"],
                "limit": None,
                "sonara_mode": "staged",
                "sonara_batch_size": 4,
                "sonara_bpm_min": None,
                "sonara_bpm_max": None,
                "sonara_staging_config": staging,
            },
        )
    ]


def test_pipeline_forwards_staged_ml_configuration_to_child_job(tmp_path) -> None:
    audio = FakeJobs(["completed"])
    manager = AnalysisPipelineManager(audio, AnalysisStageQueue())
    staging = MLStagingConfig(
        root=tmp_path,
        copy_workers=4,
        decode_workers=4,
        stage_size=64,
        inference_batch_size=16,
        preflight_copy_enabled=True,
        preflight_copy_count=64,
    )
    job_id = manager.create_job(
        stages=["ml"],
        limit=None,
        ml={
            "models": ["mert"],
            "device": "auto",
            "top_k": 3,
            "track_batch_size": 8,
            "inference_batch_size": 16,
            "ml_staging_config": staging,
        },
    )

    manager.run_job(job_id)

    assert audio.created == [
        (
            "child-1",
            {
                "models": ["mert"],
                "limit": None,
                "device": "auto",
                "top_k": 3,
                "track_batch_size": 8,
                "inference_batch_size": 16,
                "ml_staging_config": staging,
            },
        )
    ]


def test_pipeline_stops_after_fatal_stage_failure() -> None:
    audio = FakeJobs(["completed", "failed"])
    manager = AnalysisPipelineManager(audio, AnalysisStageQueue())
    job_id = manager.create_job(
        stages=["sonara", "ml"],
        limit=None,
    )

    status = manager.run_job(job_id)

    assert status.state == "failed"
    assert status.stages["sonara"].state == "completed"
    assert status.stages["ml"].state == "failed"


def test_pipeline_without_sonara_stage_requires_existing_sonara() -> None:
    audio = FakeJobs([], sonara_count=0)
    manager = AnalysisPipelineManager(audio, AnalysisStageQueue())

    with pytest.raises(
        ValueError,
        match="ML pipeline stage requires at least one track with current SONARA",
    ):
        manager.create_job(stages=["ml"], limit=None)

    assert audio.created == []


def test_parent_cancel_before_start_removes_pending_stages() -> None:
    manager = AnalysisPipelineManager(FakeJobs([]), AnalysisStageQueue())
    job_id = manager.create_job(stages=["ml"], limit=None)
    cancelled = manager.cancel(job_id)

    assert cancelled.state == "cancelled"
    assert all(stage.state == "cancelled" for stage in cancelled.stages.values())

    status = manager.run_job(job_id)

    assert status.state == "cancelled"
    assert all(stage.state == "cancelled" for stage in status.stages.values())


def test_parent_cancel_propagates_to_current_child_and_cancels_pending_stages() -> None:
    holder = {}

    class CancelDuringRun(FakeJobs):
        def run_job(self, job_id):
            holder["manager"].cancel(holder["parent_id"])
            return SimpleNamespace(state="cancelled")

    audio = CancelDuringRun(["cancelled"])
    manager = AnalysisPipelineManager(audio, AnalysisStageQueue())
    parent_id = manager.create_job(
        stages=["sonara", "ml"],
        limit=None,
        ml={"models": ["mert"]},
    )
    holder.update(manager=manager, parent_id=parent_id)

    status = manager.run_job(parent_id)

    assert status.state == "cancelled"
    assert audio.cancelled == ["child-1"]
    assert status.stages["sonara"].state == "cancelled"
    assert status.stages["ml"].state == "cancelled"


def test_shared_analysis_queue_runs_callbacks_sequentially(monkeypatch) -> None:
    stage_queue = AnalysisStageQueue()
    entered = threading.Event()
    release = threading.Event()
    joining = threading.Event()
    released_owner = threading.Event()
    order = []
    join = stage_queue._thread.join
    interrupt = KeyboardInterrupt("queue close interrupted")
    join_interrupted = False
    close_errors = []
    close_done = threading.Event()

    def observe_join(*args, **kwargs):
        nonlocal join_interrupted
        joining.set()
        if not join_interrupted:
            join_interrupted = True
            raise interrupt
        if not release.is_set():
            # An interrupted CPython join may subsequently report completion
            # even while the callback is still running.
            return None
        return join(*args, **kwargs)

    monkeypatch.setattr(stage_queue._thread, "join", observe_join)

    def first():
        order.append("first:start")
        entered.set()
        assert release.wait(5)
        with pytest.raises(RuntimeError, match="worker"):
            stage_queue.close()
        order.append("first:end")
        raise RuntimeError("failed callback must not prevent queue drain")

    def interrupted():
        order.append("interrupted")
        raise KeyboardInterrupt("interrupted callback must not prevent queue drain")

    class LastCallback:
        def __call__(self):
            order.append("second")

    owner = LastCallback()
    owner_ref = weakref.ref(owner)
    weakref.finalize(owner, released_owner.set)
    stage_queue.submit(first)
    stage_queue.submit(interrupted)
    stage_queue.submit(owner)
    del owner

    def close():
        try:
            stage_queue.close()
        except BaseException as error:
            close_errors.append(error.with_traceback(None))
        finally:
            close_done.set()

    closer = threading.Thread(target=close, daemon=True)
    try:
        assert entered.wait(5)
        closer.start()
        assert joining.wait(5)
        with pytest.raises(RuntimeError, match="closed"):
            stage_queue.submit(lambda: order.append("late"))
        assert not close_done.wait(0.1)
    finally:
        release.set()
        if closer.ident is None:
            closer.start()
        closer.join(5)
    assert not closer.is_alive()
    assert close_done.is_set()
    assert not stage_queue._thread.is_alive()
    assert order == ["first:start", "first:end", "interrupted", "second"]
    assert close_errors == [interrupt]
    assert released_owner.wait(5)
    assert owner_ref() is None
    stage_queue.close()

    # Also prove release before an open queue waits for its next callback.
    idle_queue = AnalysisStageQueue()
    owner = LastCallback()
    owner_ref = weakref.ref(owner)
    released_owner.clear()
    weakref.finalize(owner, released_owner.set)
    idle_queue.submit(owner)
    del owner
    try:
        assert released_owner.wait(5)
        assert owner_ref() is None
        assert idle_queue._thread.is_alive()
    finally:
        idle_queue.close()
