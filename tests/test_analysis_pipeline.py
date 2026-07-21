import threading
import time
from types import SimpleNamespace

from dj_track_similarity.analysis_pipeline import AnalysisPipelineManager
from dj_track_similarity.analysis_queue import AnalysisStageQueue


class FakeJobs:
    def __init__(self, states):
        self.states = list(states)
        self.created = []
        self.cancelled = []

    def validate_sonara_preflight(self):
        return None

    def create_job(self, **kwargs):
        job_id = f"child-{len(self.created) + 1}"
        self.created.append((job_id, kwargs))
        return job_id

    def run_job(self, job_id):
        return SimpleNamespace(state=self.states.pop(0))

    def cancel(self, job_id):
        self.cancelled.append(job_id)


def test_pipeline_uses_fixed_order_and_continues_after_completed_per_file_failures() -> None:
    audio = FakeJobs(["completed", "completed"])
    classifiers = FakeJobs(["completed"])
    manager = AnalysisPipelineManager(audio, classifiers, AnalysisStageQueue())
    job_id = manager.create_job(
        stages=["classifiers", "ml", "sonara"],
        limit=10,
        sonara={"outputs": ["core"], "batch_size": 16},
        ml={"models": ["mert"]},
        classifiers={"classifier_keys": ["demo"]},
    )

    status = manager.run_job(job_id)

    assert status.state == "completed"
    assert status.order == ["sonara", "ml", "classifiers"]
    assert [stage.state for stage in status.stages.values()] == ["completed", "completed", "completed"]
    assert len(audio.created) == 2
    assert len(classifiers.created) == 1


def test_pipeline_stops_after_fatal_stage_failure() -> None:
    audio = FakeJobs(["completed", "failed"])
    classifiers = FakeJobs(["completed"])
    manager = AnalysisPipelineManager(audio, classifiers, AnalysisStageQueue())
    job_id = manager.create_job(
        stages=["sonara", "ml", "classifiers"],
        limit=None,
        classifiers={"classifier_keys": ["demo"]},
    )

    status = manager.run_job(job_id)

    assert status.state == "failed"
    assert status.stages["sonara"].state == "completed"
    assert status.stages["ml"].state == "failed"
    assert status.stages["classifiers"].state == "pending"
    assert classifiers.created == []


def test_parent_cancel_before_start_removes_pending_stages() -> None:
    manager = AnalysisPipelineManager(FakeJobs([]), FakeJobs([]), AnalysisStageQueue())
    job_id = manager.create_job(stages=["ml", "classifiers"], limit=None)
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
    classifiers = FakeJobs([])
    manager = AnalysisPipelineManager(audio, classifiers, AnalysisStageQueue())
    parent_id = manager.create_job(
        stages=["ml", "classifiers"],
        limit=None,
        ml={"models": ["mert"]},
        classifiers={"classifier_keys": ["demo"]},
    )
    holder.update(manager=manager, parent_id=parent_id)

    status = manager.run_job(parent_id)

    assert status.state == "cancelled"
    assert audio.cancelled == ["child-1"]
    assert status.stages["ml"].state == "cancelled"
    assert status.stages["classifiers"].state == "cancelled"
    assert classifiers.created == []


def test_shared_analysis_queue_runs_callbacks_sequentially() -> None:
    stage_queue = AnalysisStageQueue()
    lock = threading.Lock()
    finished = threading.Event()
    active = 0
    max_active = 0
    order = []

    def callback(name):
        def run():
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
                order.append(f"{name}:start")
            time.sleep(0.02)
            with lock:
                order.append(f"{name}:end")
                active -= 1
                if name == "second":
                    finished.set()
        return run

    stage_queue.submit(callback("first"))
    stage_queue.submit(callback("second"))
    assert finished.wait(1.0)
    assert max_active == 1
    assert order == ["first:start", "first:end", "second:start", "second:end"]
